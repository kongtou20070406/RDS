"""Check the human-facing Advisor commands without initializing a project."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from rds_verify_types import digest


class AdvisorCLITests(unittest.TestCase):
    def call(self, project, *args):
        proc = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/rds_cli.py'),
                               '--root', str(project), 'advise', *args],
                              cwd=ROOT, capture_output=True, encoding='utf-8', timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_fit_curve_protocol_reaches_diagnosis_and_does_not_create_ledger(self):
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            curve = project / 'curve.json'
            curve.write_text(json.dumps({'train_loss_history': [3, 2, 1],
                'val_loss_history': [1, 2, 3], 'losses_comparable': True,
                'matched_checkpoints': True, 'trend_tolerance': 0.1}), encoding='utf-8')
            single = self.call(project, '--train-loss', '1', '--val-loss', '3')
            self.assertEqual(single['verdict'], 'INSUFFICIENT_EVIDENCE')
            paired = self.call(project, '--train-loss', '1', '--val-loss', '3',
                               '--fit-telemetry', str(curve))
            self.assertEqual(paired['verdict'], 'POSSIBLE_GENERALIZATION_GAP')
            self.assertFalse((project / '.rds').exists())

    def test_literature_uses_scoped_records_without_initializing_a_ledger(self):
        # The library is resolved relative to the supplied repository/project root.
        answer = self.call(ROOT, '--literature', 'lr')
        self.assertGreater(answer['matches_count'], 0)
        self.assertEqual(answer['assurance'], 'HEURISTIC_ONLY')
        self.assertTrue(all('sources' in record for record in answer['principles']))

    def test_sourced_context_works_without_a_project_and_does_not_execute(self):
        with tempfile.TemporaryDirectory() as raw:
            answer = self.call(Path(raw), '--research-context',
                str(ROOT / 'examples/advisor-search/boundary-context.json'),
                '--graph', str(ROOT / 'references/judgment-graph.yaml'))
            search = next(row['search'] for row in answer['recommendations']
                          if row.get('type') == 'EXECUTABLE_DIRECTION_SEARCH')
            self.assertTrue(search['blocked_candidates'])
            self.assertEqual(search['candidates'][0]['evidence_status'], 'INPUT_REPORTED')
            self.assertFalse((Path(raw) / '.rds').exists())

    def test_receipt_cost_identity_conflict_reaches_advisor_without_selected_facts(self):
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            binding = {'run_id': 'run', 'code_sha256': 'a' * 64, 'config_sha256': 'b' * 64,
                       'data_sha256': 'c' * 64, 'data_split': 'development'}
            receipt = {'run_id': 'run', 'run_status': 'SUCCEEDED', 'binding': binding,
                       'resources': {'wall_seconds': {'measured': 2, 'unit': 'seconds'}}}
            receipt['sha256'] = digest(receipt)
            receipt_raw = json.dumps(receipt).encode('utf-8')
            (project / 'receipt.json').write_bytes(receipt_raw)
            graph = {'nodes': [{'id': 'inspect', 'executable': {'decisions': ['choose'],
                     'preconditions': [], 'action': {'id': 'compare', 'description': 'Inspect bounded evidence',
                     'competing_explanations': ['real improvement', 'wrong run'], 'required_observables': ['bound loss'],
                     'outcomes': [{'observation': 'improved', 'next_decision': 'continue'},
                                  {'observation': 'not improved', 'next_decision': 'stop'}]}}}]}
            graph_path = project / 'graph.json'
            graph_path.write_text(json.dumps(graph), encoding='utf-8')
            for conflicting in (False, True):
                with self.subTest(conflicting=conflicting):
                    manifest = {'schema': 'rds-artifact-manifest-v1', 'decision': 'choose',
                                'sources': [{'id': 'receipt', 'kind': 'receipt', 'path': 'receipt.json',
                                             'expected_sha256': digest(receipt_raw), 'facts': [],
                                             'binding': {**binding, 'data_split': 'holdout' if conflicting else 'development'}}],
                                'cost_bindings': [{'action_id': 'compare', 'run_id': 'run', 'resource': 'wall_seconds',
                                                   'comparison_group': 'same-protocol'}],
                                'budget': {'value': 3, 'unit': 'seconds', 'comparison_group': 'same-protocol',
                                           'source': 'predeclared test budget'}}
                    manifest_path = project / 'manifest.json'
                    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
                    imported = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/rds_cli.py'),
                        '--root', str(project), 'artifacts', 'import', '--manifest', str(manifest_path)],
                        cwd=ROOT, capture_output=True, encoding='utf-8', timeout=10)
                    self.assertEqual(imported.returncode, 0, imported.stderr)
                    self.assertEqual(json.loads(imported.stdout)['status'], 'CONFLICT' if conflicting else 'IMPORTED')
                    answer = self.call(project, '--artifacts', str(manifest_path), '--graph', str(graph_path))
                    search = next(row['search'] for row in answer['recommendations']
                                  if row.get('type') == 'EXECUTABLE_DIRECTION_SEARCH')
                    candidate = search['candidates'][0]
                    cost = answer['artifact_import']['context']['costs']['compare']
                    self.assertEqual(answer['artifact_import']['facts'], {})
                    if conflicting:
                        self.assertEqual(cost['kind'], 'UNKNOWN')
                        self.assertFalse(cost['reliable'])
                        self.assertEqual(cost['declared_value'], 2)
                        self.assertEqual(candidate['incremental_cost']['status'], 'UNKNOWN')
                        self.assertEqual(candidate['budget_status'], 'UNKNOWN')
                    else:
                        self.assertEqual(cost['value'], 2)
                        self.assertEqual(candidate['incremental_cost']['evidence_statuses'], ['ARTIFACT_OBSERVED'])
                        self.assertEqual(candidate['budget_status'], 'WITHIN_REPORTED_BUDGET')
            self.assertFalse((project / '.rds').exists())


if __name__ == '__main__':
    unittest.main()
