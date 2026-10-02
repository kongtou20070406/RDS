"""Optional versioned native closure; Python preserves declared-label semantics.

Local libraries are trusted code, not a sandbox. Cargo alone is not availability.
"""
import ctypes
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
ABI_VERSION = 2
LIB_NAMES = {"win32": "rds_accelerator.dll", "darwin": "librds_accelerator.dylib",
             "linux": "librds_accelerator.so"}
_LOADED_LIB = None
_INIT_ATTEMPTED = False
_NO_EDGE = 2 ** 32 - 1


def _find_native_library():
    name = LIB_NAMES.get(sys.platform)
    if name is None:
        return None
    for folder in ("release", "debug"):
        path = ROOT / "native/rds_accelerator/target" / folder / name
        if path.is_file():
            return path
    return None


def get_native_cdll():
    global _LOADED_LIB, _INIT_ATTEMPTED
    if _INIT_ATTEMPTED:
        return _LOADED_LIB
    _INIT_ATTEMPTED = True
    path = _find_native_library()
    if path is None:
        return None
    try:
        lib = ctypes.CDLL(str(path.resolve()))
        lib.rds_accelerator_abi_version.argtypes = []
        lib.rds_accelerator_abi_version.restype = ctypes.c_uint32
        lib.rds_accelerator_smoke.argtypes = []
        lib.rds_accelerator_smoke.restype = ctypes.c_int32
        if lib.rds_accelerator_abi_version() != ABI_VERSION or lib.rds_accelerator_smoke() != 42:
            return None
        lib.rds_hypergraph_closure_v2.argtypes = [
            ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint8),
            ctypes.POINTER(ctypes.c_uint32), ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint32), ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t]
        lib.rds_hypergraph_closure_v2.restype = ctypes.c_int32
        _LOADED_LIB = lib
    except (OSError, AttributeError):
        _LOADED_LIB = None
    return _LOADED_LIB


def is_native_available():
    return get_native_cdll() is not None


def is_cargo_available():
    return shutil.which("cargo") is not None


def get_accelerator_status():
    native = is_native_available()
    return {"status": "AVAILABLE" if native else "UNAVAILABLE",
            "backend": "RUST_CDYLIB_NATIVE" if native else "PURE_PYTHON_FALLBACK",
            "native_library_loaded": native, "cargo_available": is_cargo_available(),
            "abi_version": ABI_VERSION if native else None,
            "assurance": "ABI_SMOKE_NOT_SCIENTIFIC_VERIFICATION"}


def _validate(nodes, edges, initial_supported):
    if len(nodes) > 4096 or len(edges) > 16384:
        raise ValueError("Closure input exceeds hypergraph hard limits")
    index = {node["id"]: node for node in nodes}
    if len(index) != len(nodes) or any(n.get("status") not in
            ("SUPPORTED", "UNKNOWN", "CONTRADICTED") for n in nodes):
        raise ValueError("Invalid/duplicate closure nodes")
    if not initial_supported <= index.keys() or any(
            index[n]["status"] == "CONTRADICTED" for n in initial_supported):
        raise ValueError("Unknown or contradicted initial support")
    if len({edge["id"] for edge in edges}) != len(edges):
        raise ValueError("Duplicate closure edge id")
    for edge in edges:
        tails = edge.get("premises", [])
        if not isinstance(tails, list) or len(tails) != len(set(tails)):
            raise ValueError("Invalid/duplicate premises")
        if edge.get("conclusion") not in index or any(p not in index for p in tails):
            raise ValueError("Unknown closure endpoint")
        if edge.get("status") not in ("SUPPORTED", "PROPOSED", "CONTRADICTED"):
            raise ValueError("Invalid closure edge status")
    return index


def python_hypergraph_closure(nodes, edges, initial_supported):
    """Original ordered fixed-point traversal, including witness selection."""
    index = _validate(nodes, edges, initial_supported)
    closure, derivations, conflicts = set(initial_supported), {}, set()
    changed = True
    while changed:
        changed = False
        for edge in edges:
            if edge["status"] != "SUPPORTED" or not set(edge.get("premises", [])) <= closure:
                continue
            head = edge["conclusion"]
            if index[head]["status"] == "CONTRADICTED":
                conflicts.add(edge["id"])
            elif head not in closure:
                closure.add(head)
                derivations[head] = edge["id"]
                changed = True
    return closure, derivations, conflicts


def compute_hypergraph_closure(nodes, edges, initial_supported):
    """Preserve closure, first derivation and conflict semantics on both backends."""
    lib = get_native_cdll()
    if lib is None:
        return python_hypergraph_closure(nodes, edges, initial_supported)
    _validate(nodes, edges, initial_supported)
    ids = [n["id"] for n in nodes]
    positions = {ident: i for i, ident in enumerate(ids)}
    active = [e for e in edges if e["status"] == "SUPPORTED"]
    flat = []
    for edge in active:
        tails = edge.get("premises", [])
        flat.extend((positions[edge["conclusion"]], len(tails)))
        flat.extend(positions[p] for p in tails)
    initial = sorted(positions[n] for n in initial_supported)
    flags = (ctypes.c_uint8 * len(nodes))(*(n["status"] == "CONTRADICTED" for n in nodes))
    init = (ctypes.c_uint32 * len(initial))(*initial)
    encoded = (ctypes.c_uint32 * len(flat))(*flat)
    closure_out = (ctypes.c_uint8 * len(nodes))()
    witness_out = (ctypes.c_uint32 * len(nodes))(*([_NO_EDGE] * len(nodes)))
    conflict_out = (ctypes.c_uint8 * len(active))()
    try:
        result = lib.rds_hypergraph_closure_v2(len(nodes), flags, init, len(initial),
                    encoded, len(flat), closure_out, witness_out, conflict_out, len(active))
        if result != 0 or any(v not in (0, 1) for v in closure_out) or any(
                v != _NO_EDGE and v >= len(active) for v in witness_out) or any(
                v not in (0, 1) for v in conflict_out):
            return python_hypergraph_closure(nodes, edges, initial_supported)
        return ({ids[i] for i, value in enumerate(closure_out) if value},
                {ids[i]: active[e]["id"] for i, e in enumerate(witness_out) if e != _NO_EDGE},
                {active[i]["id"] for i, value in enumerate(conflict_out) if value})
    except (ValueError, OSError, AttributeError):
        return python_hypergraph_closure(nodes, edges, initial_supported)
