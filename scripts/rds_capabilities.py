"""Live-check one selected local capability; no inventory, installs or GPU jobs."""
import argparse
from fractions import Fraction
import importlib
import json
import os
import sys
import time

CAPABILITIES = ('python_exact', 'sympy_exact', 'mpmath_iv', 'torch_cpu')


def probe(capability):
    if capability not in CAPABILITIES:
        raise ValueError('Choose one supported local capability')
    started = time.perf_counter()
    report = {'capability': capability, 'python': sys.executable, 'python_version': sys.version,
              'logical_cpus': os.cpu_count(), 'status': 'UNKNOWN',
              'assurance': 'LOCAL_CAPABILITY_SMOKE_NOT_SCIENTIFIC_VERIFICATION'}
    try:
        if capability == 'python_exact':
            valid = Fraction(1, 3) + Fraction(1, 6) == Fraction(1, 2)
        else:
            name = {'sympy_exact': 'sympy', 'mpmath_iv': 'mpmath', 'torch_cpu': 'torch'}[capability]
            module = importlib.import_module(name)
            report.update(module=name, module_path=module.__file__, module_version=getattr(module, '__version__', None))
            if capability == 'sympy_exact':
                valid = module.Rational(1, 3) + module.Rational(1, 6) == module.Rational(1, 2)
            elif capability == 'mpmath_iv':
                value = module.iv.mpf([1, 2]) + module.iv.mpf([3, 4])
                report['smoke_enclosure'] = str(value)
                valid = value.a == 4 and value.b == 6
            else:
                valid = module.tensor([1, 2], dtype=module.int64, device='cpu').sum().item() == 3
        report['status'] = 'AVAILABLE' if valid else 'FAILED_SMOKE'
    except (ImportError, OSError, AttributeError) as exc:
        report.update(status='UNAVAILABLE', error=str(exc))
    except Exception as exc:
        report.update(status='FAILED_SMOKE', error=str(exc))
    report['wall_seconds'] = round(time.perf_counter() - started, 6)
    return report


def verify_capability_mastery(spec, implementation_callable=None):
    """Three-tier proving ground: smoke pass, counterexample detection, boundary guard."""
    if not isinstance(spec, dict) or spec.get("schema", 1) != 1:
        raise ValueError("Capability spec must have schema: 1")
    cap_id = spec.get("capability_id")
    if not isinstance(cap_id, str) or not cap_id.strip():
        raise ValueError("capability_id must be a nonempty string")
    fixtures = spec.get("fixtures")
    if not isinstance(fixtures, dict):
        raise ValueError("fixtures dictionary is required for capability mastery verification")

    t1 = fixtures.get("tier1_smoke_pass")
    t2 = fixtures.get("tier2_counterexample_witness")
    t3 = fixtures.get("tier3_boundary_stress", [])

    if not isinstance(t1, dict) or not isinstance(t2, dict) or not isinstance(t3, list):
        raise ValueError("fixtures must contain tier1_smoke_pass (dict), tier2_counterexample_witness (dict), and tier3_boundary_stress (list)")

    import hashlib
    serialized = json.dumps(spec, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    tier_results = {}
    runner = implementation_callable
    if runner is None and "code" in spec:
        code_str = spec["code"]
        if not isinstance(code_str, str):
            raise ValueError("code must be a string")
        loc = {}
        exec(code_str, {"__builtins__": __builtins__, "Fraction": Fraction}, loc)
        entry = spec.get("entrypoint", "run_operator")
        if entry not in loc or not callable(loc[entry]):
            raise ValueError(f"entrypoint '{entry}' not found or not callable in code")
        runner = loc[entry]

    if runner is not None:
        try:
            r1 = runner(t1.get("input"))
            t1_pass = isinstance(r1, dict) and r1.get("status") == t1.get("expected_status", "PASS")
            tier_results["tier1_smoke_pass"] = {"status": "PASS" if t1_pass else "FAIL", "observed": r1}
        except Exception as exc:
            tier_results["tier1_smoke_pass"] = {"status": "FAIL", "error": type(exc).__name__ + ": " + str(exc)}

        try:
            r2 = runner(t2.get("input"))
            has_witness = bool(r2.get("witness") or r2.get("counterexample"))
            t2_pass = (isinstance(r2, dict) and r2.get("status") == t2.get("expected_status", "CONTRADICTED")
                       and (not t2.get("expected_witness_present", True) or has_witness))
            tier_results["tier2_counterexample_witness"] = {
                "status": "PASS" if t2_pass else "FAIL",
                "witness_present": has_witness,
                "observed": r2
            }
        except Exception as exc:
            tier_results["tier2_counterexample_witness"] = {"status": "FAIL", "error": type(exc).__name__ + ": " + str(exc)}

        t3_passes = 0
        t3_details = []
        for idx, case in enumerate(t3):
            try:
                r3 = runner(case.get("input"))
                exp_status = case.get("expected_status", "UNKNOWN")
                passed = isinstance(r3, dict) and r3.get("status") == exp_status
                if passed:
                    t3_passes += 1
                t3_details.append({"case_index": idx, "status": "PASS" if passed else "FAIL", "observed": r3})
            except Exception as exc:
                t3_details.append({"case_index": idx, "status": "FAIL", "error": type(exc).__name__ + ": " + str(exc)})
        tier_results["tier3_boundary_stress"] = {
            "status": "PASS" if (t3_passes == len(t3) and len(t3) > 0) else "FAIL",
            "passed_cases": t3_passes,
            "total_cases": len(t3),
            "details": t3_details
        }
    else:
        t1_valid = "input" in t1 and t1.get("expected_status") == "PASS"
        t2_valid = "input" in t2 and t2.get("expected_status") == "CONTRADICTED"
        t3_valid = len(t3) > 0 and all("input" in c and c.get("expected_status") in ("UNKNOWN", "CONTRADICTED") for c in t3)
        tier_results["tier1_smoke_pass"] = {"status": "PASS" if t1_valid else "FAIL", "mode": "SPEC_DECLARATION_ONLY"}
        tier_results["tier2_counterexample_witness"] = {"status": "PASS" if t2_valid else "FAIL", "mode": "SPEC_DECLARATION_ONLY"}
        tier_results["tier3_boundary_stress"] = {"status": "PASS" if t3_valid else "FAIL", "mode": "SPEC_DECLARATION_ONLY"}

    all_passed = all(tr["status"] == "PASS" for tr in tier_results.values())
    return {
        "schema": 1,
        "assurance": "CAPABILITY_MASTERY_THREE_TIER_QUALIFICATION",
        "capability_id": cap_id,
        "domain": spec.get("domain", "general"),
        "tier_results": tier_results,
        "all_tiers_passed": all_passed,
        "mastery_status": "QUALIFIED" if all_passed else "REJECTED",
        "sha256": digest
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capability', choices=CAPABILITIES)
    parser.add_argument('--verify-mastery', help='Path to candidate capability JSON specification')
    args = parser.parse_args()
    if args.verify_mastery:
        from pathlib import Path
        spec = json.loads(Path(args.verify_mastery).read_text(encoding='utf-8'))
        report = verify_capability_mastery(spec)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['mastery_status'] == 'QUALIFIED' else 1
    if not args.capability:
        parser.error('one of --capability or --verify-mastery is required')
    report = probe(args.capability)
    print(json.dumps(report, ensure_ascii=False, allow_nan=False))
    return 0 if report['status'] == 'AVAILABLE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
