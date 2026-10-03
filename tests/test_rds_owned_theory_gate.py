"""Public theory APIs cannot spend outside the program-owned Advisor route.

The fixture is the real, small CPU example. The legacy acceptance executes both
the verifier worker and the experiment; it establishes software behavior only.
"""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import rds_advisor
from rds_advisor import RDSAdvisor
from rds_project import ProjectStore


def formal_obligation():
    return {'kind': 'declarative', 'statement': {
        'schema': 1, 'kind': 'affine_dynamics',
        'model': {'matrix': [['1/2']], 'bias': ['1/2']},
        'threshold': '1', 'point': ['1']}}


class OwnedTheoryGateTests(unittest.TestCase):
    def initialize(self, *, controlled=True):
        tmp = tempfile.TemporaryDirectory(prefix='rds-owned-theory-gate-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        module_spec = importlib.util.spec_from_file_location(
            'owned_theory_example', ROOT / 'examples/owned-advisor/prepare.py')
        example = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(example)
        example.prepare(self.root)
        contract = json.loads((self.root / 'contract.json').read_text(encoding='utf-8'))
        if not controlled:
            del contract['advisor_policy']
        self.store = ProjectStore(self.root)
        self.store.initialize(contract)
        self.manifests = {name: json.loads((self.root / (name + '.json')).read_text(encoding='utf-8'))
                          for name in ('control', 'treatment')}
        self.allowance = {'wall_seconds': 2, 'cpu_seconds': 1}

    def ledger_state(self):
        with self.store._db(True) as db:
            return {name: [tuple(row) for row in db.execute('SELECT * FROM ' + name + ' ORDER BY rowid')]
                    for name in ('contract', 'budget', 'runs', 'receipts', 'events', 'exposures', 'output_claims')}

    def test_direct_allowance_rejects_before_entering_body_or_changing_ledger(self):
        self.initialize()
        before = self.ledger_state()
        entered = []
        with self.assertRaisesRegex(ValueError, 'Program-owned Advisor'):
            with self.store.theory_allowance(self.manifests['treatment'],
                                            {'formal': formal_obligation()}, self.allowance):
                entered.append(True)
        self.assertEqual(entered, [])
        self.assertEqual(self.ledger_state(), before)
        self.assertFalse((self.root / 'outputs/treatment.json').exists())

    def test_advisor_api_rejects_before_theory_worker_or_run_mutation(self):
        self.initialize()
        before = self.ledger_state()
        # Wrap the real worker, so an accidental dispatch is counted and is not
        # hidden behind a mocked formal outcome.
        with patch.object(rds_advisor, '_bounded_theory_gate',
                          wraps=rds_advisor._bounded_theory_gate) as worker:
            for name in ('control', 'treatment'):
                with self.subTest(route=name):
                    with self.assertRaisesRegex(ValueError, 'Program-owned Advisor'):
                        RDSAdvisor(self.root).execute_theory_probe(
                            self.manifests[name], formal_obligation(), theory_allowance=self.allowance)
                    worker.assert_not_called()
                    self.assertEqual(self.ledger_state(), before)
                    self.assertFalse((self.root / ('outputs/' + name + '.json')).exists())

    def test_legacy_theory_workflow_still_runs_real_verifier_and_experiment(self):
        self.initialize(controlled=False)
        with patch.object(rds_advisor, '_bounded_theory_gate',
                          wraps=rds_advisor._bounded_theory_gate) as worker:
            result = RDSAdvisor(self.root).execute_theory_probe(
                self.manifests['control'], formal_obligation(), theory_allowance=self.allowance)
            worker.assert_called_once()
        self.assertEqual(result['formal_gate']['status'], 'PASS')
        self.assertEqual(result['receipt']['run_status'], 'SUCCEEDED')
        self.assertTrue(result['receipt']['process_started'])
        self.assertTrue((self.root / 'outputs/control.json').is_file())
        state = self.store.snapshot()
        self.assertEqual(len(state['runs']), 1)
        self.assertEqual(len(state['receipts']), 1)
        self.assertGreaterEqual(state['budget']['wall_seconds']['charged_estimate'], 2)
        self.assertGreaterEqual(state['budget']['cpu_seconds']['charged_estimate'], 1)
        with self.store._db(True) as db:
            events = [json.loads(row['body']) for row in db.execute('SELECT body FROM events ORDER BY id')]
        self.assertEqual(sum(event['kind'] == 'THEORY_ALLOWANCE' for event in events), 1)
        outcome = next(event for event in events if event['kind'] == 'THEORY_OUTCOME')
        self.assertEqual(outcome['status'], 'PASS')
        self.assertEqual(outcome['worker_output']['exit_code'], 0)
        self.assertTrue(outcome['worker_output']['stdout']['base64'])


if __name__ == '__main__':
    unittest.main()
