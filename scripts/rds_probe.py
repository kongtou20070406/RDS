#!/usr/bin/env python3
"""Bounded reference runner: a restricted rational AST, never Python eval/exec.

This checks a mathematical model, not Python floating point or a PyTorch export.
SymPy results are SYMBOLIC_CHECKED, not independently checked proof certificates.
"""
import ast
import csv
import io
import json
import re
import sys
from fractions import Fraction

FORMAL_KINDS = {"strict_algebraic_threshold", "contraction_boundary", "dynamics", "threshold_necessity"}


def formal_requirement(hypothesis):
    """Only an explicit hypothesis declaration opts into a formal backend.

    A numeric hyperparameter or metric threshold is not a mathematical claim.
    Missing declarations cannot be inferred reliably from natural language.
    """
    if "formal_claim" in hypothesis:
        raise ValueError("Declare the mathematical claim in hypothesis.formal")
    claim = hypothesis.get("formal")
    if claim is None:
        return None
    if not isinstance(claim, dict) or claim.get("kind") not in FORMAL_KINDS:
        raise ValueError("formal.kind must be strict_algebraic_threshold, contraction_boundary or dynamics")
    if claim.get("kind") != "dynamics":
        if claim.get("quantity", "scalar_property") != "scalar_property":
            raise ValueError("Reference adapter requires quantity=scalar_property; general matrix/dynamical claims need another verifier")
        if len(claim.get("domain", [])) != 2:
            raise ValueError("formal_claim requires a two-endpoint domain")
        lo, hi = map(rational, claim["domain"])
        if lo > hi:
            raise ValueError("Vacuous domain")
        rational(claim["threshold"])
        if rational(claim["max_loss"]) < 0:
            raise ValueError("Falsifier loss bound must be nonnegative")
    return claim


def admission_probe(hypothesis, source):
    """AST only for ordinary plans; symbolic feasibility for declared boundaries.

    Admission never reads confirmation targets. Observed crossings are checked
    later by the bounded runner on the committed dataset.
    """
    formal = formal_requirement(hypothesis)
    functions = parse_source(source)
    if formal is None:
        return {"status": "PASS", "assurance": "AST_ONLY", "backend": "ast",
                "reason": "Syntax checked; no formal property was declared"}
    if formal["kind"] == "dynamics":
        return {"status": "UNKNOWN", "assurance": "NONE",
                "reason": "Dynamics declared; no dynamics verifier is installed in this reference adapter"}
    try:
        return symbolic_probe(functions, formal)
    except (ImportError, NotImplementedError, ValueError, TypeError) as exc:
        return {"status": "UNKNOWN", "assurance": "NONE", "reason": str(exc)}


def rational(value):
    if type(value) is int:
        value = str(value)
    if not isinstance(value, str) or len(value) > 80 or not re.fullmatch(
        r"-?\d+(?:/\d+|\.\d+)?", value
    ):
        raise ValueError("Use a finite integer, decimal string or rational string")
    result = Fraction(value)
    if max(result.numerator.bit_length(), result.denominator.bit_length()) > 256:
        raise ValueError("Rational input too large")
    return result


def parse_source(source):
    if len(source.encode("utf-8")) > 8192:
        raise ValueError("Source exceeds the reference runner limit")
    tree = ast.parse(source)
    if len(list(ast.walk(tree))) > 160:
        raise ValueError("AST exceeds the reference runner limit")
    functions = {}
    for fn in tree.body:
        if not isinstance(fn, ast.FunctionDef) or fn.name not in {"control", "treatment"}:
            raise ValueError("Only control(x) and treatment(x) definitions are allowed")
        args = fn.args
        if (fn.name in functions or fn.decorator_list or fn.returns or fn.type_comment
                or getattr(fn, "type_params", []) or args.posonlyargs
                or [a.arg for a in args.args] != ["x"] or args.args[0].annotation
                or args.defaults or args.kw_defaults or args.kwonlyargs
                or args.vararg or args.kwarg or len(fn.body) != 1
                or not isinstance(fn.body[0], ast.Return)):
            raise ValueError("Each arm must be exactly def arm(x): return expression")
        expression = fn.body[0].value
        for node in ast.walk(expression):
            if isinstance(node, ast.Constant):
                if type(node.value) is not int or abs(node.value) > 1000000:
                    raise ValueError("AST literals must be small integers; use a/b for fractions")
            elif isinstance(node, ast.Name):
                if node.id != "x":
                    raise ValueError("Only input x is available")
            elif isinstance(node, ast.BinOp):
                if isinstance(node.op, ast.Pow) and (
                    not isinstance(node.right, ast.Constant)
                    or type(node.right.value) is not int or not 0 <= node.right.value <= 4
                ):
                    raise ValueError("Only literal powers 0..4 are allowed")
            elif not isinstance(node, (ast.UnaryOp, ast.Add, ast.Sub, ast.Mult,
                                       ast.Div, ast.Pow, ast.USub, ast.UAdd, ast.Load)):
                raise ValueError("Unsupported AST node: " + type(node).__name__)
        functions[fn.name] = expression
    if set(functions) != {"control", "treatment"}:
        raise ValueError("Both control and treatment are required")
    return functions


def evaluate(node, x):
    if isinstance(node, ast.Constant):
        return Fraction(node.value)
    if isinstance(node, ast.Name):
        return x
    if isinstance(node, ast.UnaryOp):
        value = evaluate(node.operand, x)
        return -value if isinstance(node.op, ast.USub) else value
    left, right = evaluate(node.left, x), evaluate(node.right, x)
    if isinstance(node.op, ast.Add):
        return left + right
    if isinstance(node.op, ast.Sub):
        return left - right
    if isinstance(node.op, ast.Mult):
        return left * right
    if isinstance(node.op, ast.Div):
        return left / right
    return left ** int(right)


def read_rows(raw):
    reader = csv.DictReader(io.StringIO(raw))
    if reader.fieldnames != ["sample_id", "x", "y"]:
        raise ValueError("Expected CSV columns sample_id,x,y in that order")
    rows, ids = [], set()
    for row in reader:
        sid = row["sample_id"]
        if not sid or sid in ids or None in row:
            raise ValueError("Missing/duplicate sample identity or extra CSV field")
        ids.add(sid)
        rows.append((sid, rational(row["x"]), rational(row["y"])))
        if len(rows) > 10000:
            raise ValueError("Reference runner limited to 10000 paired samples")
    if not rows:
        raise ValueError("An empty dataset cannot confirm anything")
    return rows


def symbolic_probe(functions, formal):
    import sympy as sp

    x = sp.Symbol("x", real=True)
    denominators = []

    def translate(node):
        if isinstance(node, ast.Constant):
            return sp.Integer(node.value)
        if isinstance(node, ast.Name):
            return x
        if isinstance(node, ast.UnaryOp):
            value = translate(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        a, b = translate(node.left), translate(node.right)
        if isinstance(node.op, ast.Add):
            return a + b
        if isinstance(node.op, ast.Sub):
            return a - b
        if isinstance(node.op, ast.Mult):
            return a * b
        if isinstance(node.op, ast.Div):
            # Preserve original denominator obligations BEFORE cancellation.
            denominators.append(b)
            return a / b
        return a ** b

    lo, hi = [sp.Rational(str(rational(v))) for v in formal["domain"]]
    threshold = sp.Rational(str(rational(formal["threshold"])))
    domain = [x >= lo, x <= hi]
    expressions = {k: translate(v) for k, v in functions.items()}
    if lo > hi:
        raise ValueError("Vacuous domain")
    for den in denominators:
        zeros = sp.reduce_inequalities(domain + [sp.Eq(den, 0)], x).as_set()
        if zeros.is_empty is not True:
            return {"status": "UNKNOWN", "reason": "denominator may vanish in domain",
                    "singular_set": str(zeros), "assurance": "SYMBOLIC_CHECKED"}
    # Boolean conjunctions may be contradictory without simplifying to False.
    counter = sp.reduce_inequalities(domain + [expressions["control"] >= threshold], x).as_set()
    crossing = sp.reduce_inequalities(domain + [expressions["treatment"] >= threshold], x).as_set()
    status = ("UNKNOWN" if counter.is_empty is None or crossing.is_empty is None else
              "PASS" if counter.is_empty and not crossing.is_empty else "FAIL")
    return {
        "status": status,
        "assurance": "SYMBOLIC_CHECKED", "backend": "sympy", "backend_version": sp.__version__,
        "semantics": "exact_rational_execution_and_real_symbolic_model",
        "domain": formal["domain"], "threshold": formal["threshold"],
        "control_violation_set": str(counter), "treatment_crossing_set": str(crossing),
        "expressions": {k: str(v) for k, v in expressions.items()},
        "reason": "threshold discrimination only; no causal mechanism conclusion",
    }


def execute(payload):
    formal = formal_requirement(payload.get("hypothesis", {}))
    if "formal" in payload:
        raise ValueError("Declare formal on the hypothesis, not an unbound payload.formal")
    if formal and formal["kind"] == "dynamics":
        return {"probe": {"status": "UNKNOWN", "assurance": "NONE",
                          "reason": "Dynamics verifier unavailable"}}
    functions = parse_source(payload["source"])
    rows = read_rows(payload["data"])
    observations = []
    for sid, x, target in rows:
        if formal and not rational(formal["domain"][0]) <= x <= rational(formal["domain"][1]):
            raise ValueError("Observed input outside committed formal domain")
        control, treatment = [evaluate(functions[k], x) for k in ("control", "treatment")]
        observations.append({"sample_id": sid, "x": str(x), "y": str(target),
                             "control": str(control), "treatment": str(treatment),
                             "control_loss": str((control - target) ** 2),
                             "treatment_loss": str((treatment - target) ** 2)})
    mean = lambda key: sum((Fraction(r[key]) for r in observations), Fraction()) / len(rows)
    probe = {"status": "NOT_APPLICABLE", "assurance": "NONE"}
    if formal:
        try:
            probe = symbolic_probe(functions, formal)
        except (ImportError, NotImplementedError, ValueError, TypeError) as exc:
            probe = {"status": "UNKNOWN", "reason": str(exc), "assurance": "NONE"}
        threshold, max_loss = rational(formal["threshold"]), rational(formal["max_loss"])
        crossed = [r["sample_id"] for r in observations
                   if Fraction(r["control"]) < threshold <= Fraction(r["treatment"])]
        falsifiers = [r["sample_id"] for r in observations
                      if r["sample_id"] in crossed
                      and Fraction(r["treatment_loss"]) <= max_loss
                      and Fraction(r["control_loss"]) <= max_loss]
        probe.update({"observed_crossings": crossed, "necessity_counterexamples": falsifiers})
        if probe["status"] == "PASS" and not crossed:
            probe.update(status="FAIL", reason="Crossing is possible but was never executed")
    return {"metric": "mse", "n": len(rows), "observations": observations,
            "control_mean": str(mean("control_loss")),
            "treatment_mean": str(mean("treatment_loss")),
            "gain": str(mean("control_loss") - mean("treatment_loss")), "probe": probe}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        result = (admission_probe(payload["hypothesis"], payload["source"])
                  if payload.get("operation") == "admission" else execute(payload))
        print(json.dumps(result, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "detail": str(exc)}))
        sys.exit(1)
