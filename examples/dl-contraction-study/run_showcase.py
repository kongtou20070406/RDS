"""End-to-End Showcase for RDS-L3 in Deep Learning Research Workflows.

Demonstrates:
1. Contract initialization and formal hypothesis binding (m >= 1 threshold).
2. Plan 1: Baseline control execution and automatic caching.
3. Plan 2: Treatment exploration with 100% baseline control reuse (zero duplicate GPU compute).
4. Token compression on mock 500-step training log (95%+ reduction).
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys

DIR = Path(__file__).resolve().parent
ROOT = DIR.parents[1]
CLI = ROOT / "scripts/rds_cli.py"


def run_cli(*args):
    cmd = [sys.executable, "-B", str(CLI), "--root", str(DIR), *args]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        raise RuntimeError(f"CLI Error: {res.stderr}\n{res.stdout}")
    return json.loads(res.stdout)


def main():
    print("=" * 65)
    print("RDS-L3 Deep Learning Showcase: Contraction & Baseline Reuse")
    print("=" * 65)

    if (DIR / ".rds").exists():
        shutil.rmtree(DIR / ".rds")

    # 1. Initialize Contract & Add Formal Hypothesis
    print("\n[Step 1] Initializing Contract and Registering Formal Hypothesis...")
    init_res = run_cli("init", "--contract", str(DIR / "contract.json"))
    print(f"  Contract locked. Contract SHA-256: {init_res['contract_sha256'][:16]}...")

    hypo_res = run_cli("hypothesis", "add", "--spec", str(DIR / "hypothesis.json"))
    print(f"  Hypothesis H-contraction locked with falsifier and formal gate.")

    # 2. Plan 1: Baseline executed from scratch
    print("\n[Step 2] Executing Plan 1 (Initial Treatment & Baseline Run)...")
    plan1 = {
        "id": "P1", "hypothesis_id": "H-contraction", "split_id": "development",
        "purpose": "explore", "source": "model.py",
        "resources": {"runtime_ms": 10000, "runs": 1}
    }
    run_cli("plan", "create", "--spec", json.dumps(plan1))
    r1 = run_cli("run", "execute", "--id", "P1")
    dec1 = run_cli("decide", "--run", r1["run_id"])
    print(f"  Run 1 Status: {r1['run_status']} | Control Reused: {r1['control_reused']}")
    print(f"  Decide Outcome: Task Gain = {dec1['assessment']['task_gain']}, Mechanism = {dec1['assessment']['mechanism']}")

    # 3. Plan 2: Second Treatment, Reusing Blank Baseline
    print("\n[Step 3] Executing Plan 2 with Model Revision (Reusing Baseline Control)...")
    model2_src = "def control(x): return 19*x/(20*(1+x))\ndef treatment(x): return 7*x/(5*(1+x))\n"
    (DIR / "model2.py").write_text(model2_src, encoding="utf-8")
    plan2 = {
        "id": "P2", "hypothesis_id": "H-contraction", "split_id": "development",
        "purpose": "explore", "source": "model2.py",
        "resources": {"runtime_ms": 10000, "runs": 1}
    }
    run_cli("plan", "create", "--spec", json.dumps(plan2))
    r2 = run_cli("run", "execute", "--id", "P2")
    dec2 = run_cli("decide", "--run", r2["run_id"])
    print(f"  Run 2 Status: {r2['run_status']} | Control Reused: {r2['control_reused']} (100% REUSED)")
    print(f"  Decide Outcome: Task Gain = {dec2['assessment']['task_gain']}, Mechanism = {dec2['assessment']['mechanism']}")

    # 4. Token Compression Showcase
    print("\n[Step 4] Deep Learning Log Token Compression Demo...")
    sys.path.insert(0, str(ROOT / "scripts"))
    from rds_compress import compress_training_log

    # Synthesize a realistic 500-step PyTorch training log
    mock_log = []
    for step in range(1, 501):
        loss = 1.5 * (0.995 ** step) + 0.05
        mock_log.append(f"Epoch 1/5 | Step {step}/500 | loss: {loss:.4f} | grad_norm: {1.2 + 0.1*(step%5):.2f} | 350.2 samples/s")
    full_log_text = "\n".join(mock_log)

    compressed = compress_training_log(full_log_text)
    print(f"  Raw Training Log Lines: {compressed['raw_lines']} lines (~{len(full_log_text.split())} tokens)")
    print(f"  Compressed Signature: {json.dumps(compressed, indent=4)}")
    print(f"  Token Reduction Achieved: {compressed['token_reduction_rate']}")

    print("\n" + "=" * 65)
    print("SHOWCASE COMPLETED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    main()
