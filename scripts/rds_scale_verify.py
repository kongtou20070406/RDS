"""Positive scaling equivariance of rational Linear/ReLU real models.

This proves F(s*x) = s*F(x) for every real x and a declared positive s.
It does not claim scale-invariant losses, normalization or training behavior.
"""
from rds_nn_verify import _validate
from rds_verify_types import MAX_CERTIFICATE_BYTES, canonical, digest, rational, require


def _facts(spec):
    require(isinstance(spec, dict) and set(spec) == {"schema", "kind", "model", "scale"},
            "Scaling statement requires schema, kind, model and scale")
    require(type(spec["schema"]) is int and spec["schema"] == 1 and spec["kind"] == "scale_equivariance",
            "Unsupported scaling statement")
    require(len(canonical(spec).encode("utf-8")) <= MAX_CERTIFICATE_BYTES, "Scaling declaration exceeds limit")
    scale = rational(spec["scale"])
    require(scale > 0, "ReLU equivariance requires a strictly positive scale")
    model = spec["model"]
    require(isinstance(model, dict), "Model must be an object")
    dimension = model.get("input_dim")
    require(type(dimension) is int and 1 <= dimension <= 64, "Input dimension must be 1..64")
    raw = model.get("layers")
    require(isinstance(raw, list) and 1 <= len(raw) <= 32, "Model must have 1..32 layers")
    width = dimension
    for layer in raw:
        require(isinstance(layer, dict), "Invalid layer")
        if layer.get("kind") == "linear":
            require(isinstance(layer.get("weight"), list) and 1 <= len(layer["weight"]) <= 64,
                    "Invalid linear layer width")
            width = len(layer["weight"])
    proxy = {"schema": 1, "kind": "network_bounds", "model": model,
             "input_box": [["-1", "1"] for _ in range(dimension)],
             "output_bounds": [["-1", "1"] for _ in range(width)]}
    layers, _, _, _, _ = _validate(proxy)
    obligations = []
    for layer in layers:
        if layer["kind"] == "linear":
            dimension = len(layer["weight"])
            obligations.append({"kind": "linear", "output_dim": dimension,
                                "zero_bias": all(b == 0 for b in layer["bias"])})
        else:
            obligations.append({"kind": "relu", "output_dim": dimension, "positive_scale": True})
    return scale, obligations


def verify(spec):
    scale, obligations = _facts(spec)
    if scale != 1 and any(item.get("zero_bias") is False for item in obligations):
        return {"status": "UNKNOWN", "assurance": "NONE", "backend": "rds_positive_homogeneity",
                "reason": "Nonzero biases need a different proof or an exact counterexample"}
    certificate = {"version": 1, "spec_sha256": digest(spec), "model_sha256": digest(spec["model"]),
                   "method": "identity_scale" if scale == 1 else "positive_homogeneity",
                   "scale": str(scale), "layers": obligations, "verdict": "PASS"}
    require(check_certificate(spec, certificate), "Generated scaling certificate failed check")
    return {"status": "PASS", "assurance": "CERTIFICATE_CHECKED", "backend": "rds_positive_homogeneity",
            "certificate": certificate}


def check_certificate(spec, certificate):
    try:
        require(isinstance(certificate, dict) and set(certificate) == {
            "version", "spec_sha256", "model_sha256", "method", "scale", "layers", "verdict"}, "Invalid scaling proof")
        require(len(canonical(certificate).encode("utf-8")) <= MAX_CERTIFICATE_BYTES, "Certificate exceeds limit")
        scale, obligations = _facts(spec)
        if scale != 1 and any(item.get("zero_bias") is False for item in obligations):
            return False
        return (type(certificate["version"]) is int and certificate["version"] == 1
                and certificate["spec_sha256"] == digest(spec)
                and certificate["model_sha256"] == digest(spec["model"])
                and certificate["method"] == ("identity_scale" if scale == 1 else "positive_homogeneity")
                and certificate["scale"] == str(scale) and certificate["layers"] == obligations
                and certificate["verdict"] == "PASS")
    except (ValueError, TypeError, KeyError, AttributeError, ZeroDivisionError, OverflowError, RecursionError):
        return False
