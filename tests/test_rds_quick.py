"""Public CLI acceptance for low-friction entry, ambiguity and preserved evidence."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from rds_project import ProjectStore


class QuickTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = {**os.environ, 'RDS_USAGE_DB': str(self.root / 'usage.sqlite3')}

    def call(self, *args, root=None, ok=True):
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/rds_cli.py'), '--root', str(root or self.root), *args],
                                capture_output=True, text=True, encoding='utf-8', env=self.env, timeout=25)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def script(self, text='print("value=" + "x" * 20000)\n'):
        (self.root / 'probe.py').write_text(text, encoding='utf-8')

    def job(self, name='probe', ok=True, *options):
        return self.call('exec', '--name', name, '--timeout', '5', *options, '--', sys.executable, '-B', 'probe.py', ok=ok)

    def initialize_ledger(self):
        self.script('print("ledger")\n')
        self.job('ledger', True, '--timeout', '30')
        self.ledger = self.root / '.rds/exec/ledger'
        self.context = {'decision': {'id': 'choose-next', 'goal_revision': 'fixed-objective', 'scope': {'domain': 'software-fixture'}},
                        'facts': {'x': {'value': False, 'source': 'reported-fixture.json'},
                                  'route-done': {'value': False, 'source': 'reported-fixture.json'}}}
        self.graph = {'nodes': [{'id': 'route', 'sources': ['fixture'], 'executable': {
            'decisions': ['choose-next'], 'preconditions': [{'fact': 'x', 'value': False}],
            'satisfied_when': [{'fact': 'route-done', 'value': True}],
            'action': {'id': 'inspect-x', 'kind': 'PAIRED_TEST', 'description': 'Inspect a reported x', 'operation': 'inspect', 'target': 'x',
                       'competing_explanations': ['first', 'second'], 'required_observables': ['x'],
                       'outcomes': [{'observation': 'first', 'next_decision': 'review first'},
                                    {'observation': 'second', 'next_decision': 'review second'}]}}}], 'edges': []}
        self.context_path = self.root / 'context.json'
        self.graph_path = self.root / 'graph.json'
        self.context_path.write_text(json.dumps(self.context), encoding='utf-8')
        self.graph_path.write_text(json.dumps(self.graph), encoding='utf-8')

    def advise(self, *tail, ok=True):
        return self.call('advise', '--context', str(self.context_path), '--graph', str(self.graph_path), *tail, root=self.ledger, ok=ok)

    def test_one_call_completes_identity_preserves_output_and_never_claims_scientific_pass(self):
        self.script()
        result = json.loads(self.job().stdout)
        self.assertEqual(result['run_status'], 'SUCCEEDED')
        self.assertNotIn('badge', result)
        self.assertEqual(result['ledger_checkpoints'], 0)
        self.assertLess(len(json.dumps(result)), 1300)
        record = Path(result['record']).read_bytes()
        self.assertEqual(hashlib.sha256(record).hexdigest(), result['sha256'])
        report = json.loads(record)
        store = ProjectStore(report['job_root'])
        state = store.snapshot(check_bindings=True)
        self.assertFalse(state['binding_check']['errors'])
        receipt = state['receipts'][0]
        self.assertEqual(receipt['assessment']['task_gain'], 'UNKNOWN')
        logs = [a for a in receipt['artifacts'] if a['kind'] == 'stdout.bin']
        self.assertGreater((Path(report['job_root']) / logs[0]['path']).stat().st_size, 20000)
        self.assertEqual(state['runs'][0]['protocol']['seed'], 'UNKNOWN')

    def test_existing_job_is_not_reexecuted_and_changed_dependency_needs_new_identity(self):
        (self.root / 'helper.py').write_text('value = 3\n', encoding='utf-8')
        self.script('import helper\nprint(helper.value)\n')
        first = json.loads(self.job().stdout)
        second = json.loads(self.job().stdout)
        full = json.loads(Path(second['record']).read_text(encoding='utf-8'))
        self.assertFalse(full['execution_started'])
        self.assertEqual(full['receipt']['sha256'], json.loads(Path(first['record']).read_text(encoding='utf-8'))['receipt']['sha256'])
        (self.root / 'helper.py').write_text('value = 4\n', encoding='utf-8')
        bad = self.job(ok=False)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn('new --name', bad.stderr)

    def test_failed_command_preserves_receipt_without_automatic_scientific_rejection(self):
        self.script('raise RuntimeError("preserved failure")\n')
        result = self.job(ok=False)
        self.assertEqual(result.returncode, 1)
        digest = json.loads(result.stdout)
        report = json.loads(Path(digest['record']).read_text(encoding='utf-8'))
        self.assertEqual(report['receipt']['run_status'], 'FAILED')
        self.assertEqual(report['receipt']['assessment']['mechanism'], 'UNKNOWN')
        self.assertFalse((Path(report['job_root']) / '.rds/project.sqlite3').is_symlink())

    def test_aliases_and_unique_prefixes_preserve_command_tail_and_values(self):
        from rds_cli import parser
        from rds_usage import _label
        self.assertEqual(_label(['--workspace', 'project', 'advisor', '--brief']), ('advise', 'command'))
        self.assertEqual(_label(['execute', '--name', 'x', '--', 'python', 'usage']), ('exec', 'command'))
        self.assertEqual(_label(['execute', '--name', 'x', '--', 'python', '--help']), ('exec', 'command'))
        self.assertEqual(_label(['misspelled', '--', 'usage']), ('other', 'command'))
        args = parser().parse_args(['proj', 'stat', '--workspace', str(self.root), '--digest'])
        self.assertEqual((args.command, args.action, args.root), ('project', 'status', str(self.root)))
        args = parser().parse_args(['deny', '--route', 'r', '--reason=--root', '--evidence', 'f'])
        self.assertEqual(args.reason, '--root')
        args = parser().parse_args(['exe', '--name', 'same', '--', 'python', 'probe.py', '--workspace', 'unchanged'])
        self.assertEqual(args.argv, ['--', 'python', 'probe.py', '--workspace', 'unchanged'])

    def test_ambiguous_prefix_cannot_mutate_or_execute(self):
        bad = self.call('adv', ok=False)
        self.assertEqual(bad.returncode, 2)
        self.assertIn('advise, advancement', bad.stderr)
        self.assertFalse((self.root / '.rds').exists())

    def test_scoped_choice_and_reject_fields_are_completed_and_consumed_by_next_advice(self):
        self.initialize_ledger()
        output = json.loads(self.advise().stdout)
        candidate = next(r for r in output['recommendations'] if r.get('type') == 'EXECUTABLE_DIRECTION_SEARCH')['search']['candidates'][0]
        recorded = json.loads(self.advise('--choose', candidate['id'], '--record', 'before', '--brief').stdout)
        self.assertEqual(recorded['checkpoint'], 'before')
        witness = self.root / 'witness.json'
        witness.write_text('{"counterexample":"declared software fixture"}', encoding='utf-8')
        result = json.loads(self.call('reject', '--route', candidate['id'], '--reason', 'scoped fixture rejection',
                                     '--evidence', str(witness), root=self.ledger).stdout)
        self.assertEqual(result['status'], 'RECORDED_REJECTION')
        after = json.loads(self.advise().stdout)
        search = next(r for r in after['recommendations'] if r.get('type') == 'EXECUTABLE_DIRECTION_SEARCH')['search']
        self.assertEqual(search['candidates'], [])
        self.assertEqual(search['blocked_candidates'][-1]['loop_review']['kind'], 'REPEAT_REJECTED_ROUTE')
        self.context['facts']['x']['source'] = {'path': 'new-witness.json', 'sha256': 'f' * 64}
        self.context_path.write_text(json.dumps(self.context), encoding='utf-8')
        reopened = json.loads(self.advise().stdout)
        search = next(r for r in reopened['recommendations'] if r.get('type') == 'EXECUTABLE_DIRECTION_SEARCH')['search']
        self.assertEqual(len(search['candidates']), 1)

    def test_prospective_exec_records_before_execution_and_unchanged_rejection_blocks_new_job(self):
        self.initialize_ledger()
        output = json.loads(self.advise().stdout)
        candidate = next(r for r in output['recommendations'] if r.get('type') == 'EXECUTABLE_DIRECTION_SEARCH')['search']['candidates'][0]
        self.script('print("actual bounded probe")\n')
        options = ['--context', str(self.context_path), '--graph', str(self.graph_path), '--choose', candidate['id'], '--ledger', str(self.ledger)]
        first = json.loads(self.job('first', True, *options).stdout)
        self.assertEqual(first['ledger_checkpoints'], 2)
        with closing(sqlite3.connect(self.ledger / '.rds/project.sqlite3')) as db:
            rows = db.execute('SELECT id,body FROM checkpoints ORDER BY rowid').fetchall()
        self.assertEqual([r[0] for r in rows], ['exec-before-first', 'exec-after-first'])
        self.assertNotIn('execution', json.loads(rows[0][1])['decision'])
        self.assertEqual(json.loads(rows[1][1])['decision']['execution']['run_status'], 'SUCCEEDED')
        witness = self.root / 'witness.json'
        witness.write_text('{}', encoding='utf-8')
        self.call('reject', '--route', candidate['id'], '--reason', 'fixture', '--evidence', str(witness), root=self.ledger)
        bad = self.job('second', False, *options)
        self.assertNotEqual(bad.returncode, 0)
        self.assertFalse((self.root / '.rds/exec/second').exists())

    def test_missing_scope_or_unrecorded_route_cannot_be_auto_invented(self):
        self.initialize_ledger()
        witness = self.root / 'witness.json'
        witness.write_text('{}', encoding='utf-8')
        bad = self.call('reject', '--route', 'unknown', '--reason', 'test', '--evidence', str(witness), root=self.ledger, ok=False)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn('No decision context', bad.stderr)

    def test_timeout_keeps_failure_logs_and_budget(self):
        self.script('import time\nprint("before timeout", flush=True)\ntime.sleep(20)\n')
        bad = self.call('exec', '--name', 'timed', '--timeout', '0.15', '--', sys.executable, '-B', 'probe.py', ok=False)
        self.assertNotEqual(bad.returncode, 0)
        report = json.loads(Path(json.loads(bad.stdout)['record']).read_text(encoding='utf-8'))
        state = ProjectStore(report['job_root']).snapshot()
        self.assertEqual(state['runs'][0]['status'], 'FAILED')
        self.assertEqual(state['budget']['wall_seconds']['reserved'], 0)
        self.assertGreater(state['budget']['wall_seconds']['spent_measured'], 0)
        self.assertIn('UNKNOWN', report['scientific_support'])

    def test_tampered_cas_cannot_be_reused(self):
        from rds_quick import cas_json
        value = {'status': 'UNKNOWN'}
        ref = cas_json(self.root, value)
        Path(ref['path']).write_bytes(b'false proof')
        with self.assertRaisesRegex(ValueError, 'CAS integrity'):
            cas_json(self.root, value)

    def test_shell_and_outside_input_are_rejected_before_launch(self):
        self.script()
        bad = self.call('exec', '--name', 'shell', '--', 'cmd' if os.name == 'nt' else 'sh', ok=False)
        self.assertNotEqual(bad.returncode, 0)
        self.assertFalse((self.root / '.rds/exec/shell').exists())
        with tempfile.TemporaryDirectory() as other:
            outside = Path(other) / 'outside.py'
            outside.write_text('print("outside")', encoding='utf-8')
            bad = self.call('exec', '--name', 'outside', '--', sys.executable, str(outside), ok=False)
            self.assertNotEqual(bad.returncode, 0)
            self.assertFalse((self.root / '.rds/exec/outside').exists())

    def test_unique_candidate_and_python_witness_completion_share_the_real_ledger(self):
        from rds_quick import record_falsification
        self.initialize_ledger()
        result = json.loads(self.advise('--record', 'unique-choice', '--brief').stdout)
        self.assertEqual(result['checkpoint'], 'unique-choice')
        self.assertEqual(result['ledger_checkpoints'], 1)
        rejected = record_falsification(self.ledger, witness={'declared_bad_case': 'synthetic'}, reason='scoped fixture')
        self.assertEqual(rejected['status'], 'RECORDED_REJECTION')
        output = json.loads(self.advise('--brief').stdout)
        self.assertIn('REPEAT_REJECTED_ROUTE', output['flags'])

    def test_prospective_job_cannot_reset_the_parent_budget(self):
        self.initialize_ledger()
        options = ['--context', str(self.context_path), '--graph', str(self.graph_path), '--ledger', str(self.ledger), '--timeout', '31']
        bad = self.job('over-budget', False, *options)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn('Insufficient parent ledger', bad.stderr)
        self.assertFalse((self.root / '.rds/exec/over-budget').exists())

    def test_ambiguous_candidate_is_not_completed(self):
        import copy
        self.initialize_ledger()
        other = copy.deepcopy(self.graph['nodes'][0])
        other['id'] = 'other-route'
        other['executable']['action']['id'] = 'inspect-y'
        self.graph['nodes'].append(other)
        self.graph_path.write_text(json.dumps(self.graph), encoding='utf-8')
        bad = self.advise('--record', 'ambiguous', ok=False)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn('ambiguous candidate', bad.stderr)


if __name__ == '__main__':
    unittest.main()
