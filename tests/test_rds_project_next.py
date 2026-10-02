"""Issue #71/#73: project next_move derivation and exact arm comparison."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rds_project import ProjectStore, _parse_rational_string

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "project-runner"
sys.path.insert(0, str(EXAMPLES))
from prepare import prepare  # noqa: E402


def metric_contract(root, name="mse", direction="min", min_useful_delta="1/100"):
    contract = json.loads((root / "contract.json").read_text(encoding="utf-8"))
    contract["primary_metric"] = {"name": name, "direction": direction,
                                  "min_useful_delta": min_useful_delta}
    return contract


class NextMoveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="rds next ")
        info = prepare(Path(self.tmp.name) / "proj")
        self.root = Path(info["root"])
        self.manifests = [Path(p) for p in info["manifests"]]
        self.store = ProjectStore(self.root)
        self.store.initialize(metric_contract(self.root))

    def tearDown(self):
        self.tmp.cleanup()

    def test_next_move_walks_the_campaign(self):
        self.assertEqual(self.store.next_move()["next_move"],
                         "register the control arm from its manifest")
        self.store.register(json.loads(self.manifests[0].read_text(encoding="utf-8")))
        self.assertIn("execute", self.store.next_move()["next_move"])
        self.store.execute("control")
        self.store.register(json.loads(self.manifests[1].read_text(encoding="utf-8")))
        move = self.store.next_move()
        self.assertIn("execute", move["next_move"])
        self.assertIn("treatment", move["next_move"])
        self.store.execute("treatment")
        move = self.store.next_move()
        self.assertIn("record the decision", move["next_move"])
        self.assertEqual(move["comparison"]["status"], "GAIN_CONFIRMED")
        self.assertIn("checkpoint save", move["command"])

    def test_next_move_requires_initialized_ledger(self):
        (Path(self.tmp.name) / "fresh").mkdir()
        fresh = ProjectStore(Path(self.tmp.name) / "fresh")
        with self.assertRaisesRegex(ValueError, "not been initialized"):
            fresh.next_move()


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="rds cmp ")
        info = prepare(Path(self.tmp.name) / "proj")
        self.root = Path(info["root"])
        self.manifests = [Path(p) for p in info["manifests"]]

    def tearDown(self):
        self.tmp.cleanup()

    def run_both_arms(self, min_useful_delta="1/100"):
        store = ProjectStore(self.root)
        store.initialize(metric_contract(self.root, min_useful_delta=min_useful_delta))
        for manifest in self.manifests:
            store.register(json.loads(manifest.read_text(encoding="utf-8")))
        store.execute("control")
        store.execute("treatment")
        return store

    def test_below_resolution_threshold_is_not_confirmed(self):
        # Real delta ~ -11.8; threshold 100 must not confirm the gain.
        store = self.run_both_arms(min_useful_delta="100")
        self.assertEqual(store.compare()["status"], "BELOW_RESOLUTION")

    def test_exact_rational_threshold_boundary(self):
        # The float delta is platform-dependent in its last ulps, so derive the
        # threshold from this platform's own recorded values: a precommitted
        # threshold that the delta exactly meets (<=) must confirm the gain,
        # proving no float re-rounding happens at the verdict.
        import json
        from fractions import Fraction
        probe = self.run_both_arms(min_useful_delta="0")
        control_raw = json.loads((self.root / "outputs" / "control.json").read_text(encoding="utf-8"))["mse"]
        treatment_raw = json.loads((self.root / "outputs" / "treatment.json").read_text(encoding="utf-8"))["mse"]
        threshold = Fraction(str(treatment_raw)) - Fraction(str(control_raw))
        self.assertLess(threshold, 0)
        info = prepare(Path(self.tmp.name) / "proj-boundary")
        root = Path(info["root"])
        store = ProjectStore(root)
        store.initialize(metric_contract(root, min_useful_delta=str(-threshold)))
        for manifest in (Path(p) for p in info["manifests"]):
            store.register(json.loads(manifest.read_text(encoding="utf-8")))
        store.execute("control")
        store.execute("treatment")
        self.assertEqual(store.compare()["status"], "GAIN_CONFIRMED")
        self.assertEqual(store.compare()["delta"], str(threshold))

    def test_missing_metric_declaration_is_unknown(self):
        store = ProjectStore(self.root)
        contract = json.loads((self.root / "contract.json").read_text(encoding="utf-8"))
        store.initialize(contract)
        for manifest in self.manifests:
            store.register(json.loads(manifest.read_text(encoding="utf-8")))
        store.execute("control")
        store.execute("treatment")
        verdict = store.compare()
        self.assertEqual(verdict["status"], "UNKNOWN")
        self.assertIn("primary_metric", verdict["reason"])

    def test_primary_metric_contract_validation(self):
        store = ProjectStore(self.root)
        bad = metric_contract(self.root)
        bad["primary_metric"]["direction"] = "up"
        with self.assertRaisesRegex(ValueError, "direction"):
            store.initialize(bad)
        bad = metric_contract(self.root, min_useful_delta="1e-3")
        with self.assertRaisesRegex(ValueError, "exponent"):
            store.initialize(bad)
        bad = metric_contract(self.root, min_useful_delta=0.01)
        with self.assertRaisesRegex(ValueError, "rational string"):
            store.initialize(bad)

    def test_parse_rational_exactness(self):
        from fractions import Fraction
        self.assertEqual(_parse_rational_string("1/100", "m"), Fraction(1, 100))
        self.assertEqual(_parse_rational_string(" 0.5 ", "m"), Fraction(1, 2))
        with self.assertRaises(ValueError):
            _parse_rational_string("nan", "m")


if __name__ == "__main__":
    unittest.main()
