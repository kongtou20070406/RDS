"""Check the human-facing Advisor commands without initializing a project."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


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


if __name__ == '__main__':
    unittest.main()
