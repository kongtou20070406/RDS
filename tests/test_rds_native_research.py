"""Native research records and real tool reuse work without MRS or containers."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import rds_math as assets
import rds_tools as tools
from rds_cli import parser
from rds_project import ProjectStore, digest
from rds_quick import execute
from rds_usage import _label


GOAL = {'schema': 'rds-objective-v1', 'question_id': 'exact-cover', 'goal_revision': '1', 'scope': {'domain': 'unit-disk'},
        'statement': 'Determine the globally optimal covering radius', 'domain': 'all allowed disk centers',
        'quantifier_order': ['for every allowed configuration'], 'assumptions': [],
        'evidence_standard': 'exact proof', 'completion_standard': 'matching global lower and upper bounds'}
SOURCE = '''from fractions import Fraction
import pathlib
pathlib.Path('MUST_NOT_EXECUTE').write_text('top-level side effect')
FACTOR = 2
def helper(x):
    return x * FACTOR
def decide(a, b):
    if b == 0:
        raise ValueError('zero denominator')
    return Fraction(helper(a), b) < 1
'''
CASES = [{'args': [1, 3], 'expected': True}, {'args': [2, 3], 'expected': False},
         {'args': [1, 0], 'expected_error': 'ValueError'}]


class NativeResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.goal = json.dumps(GOAL, ensure_ascii=False, indent=2).encode('utf-8')

    def write(self, name, value):
        path = self.root / name
        path.write_bytes(value if isinstance(value, bytes) else value.encode('utf-8'))
        return path

    def candidate(self):
        tools.extract(self.root, self.write('source.py', SOURCE), 'decide', 'compare-v1')
        return self.write('cases.json', json.dumps(CASES))

    def cli(self, *args):
        env = dict(os.environ, RDS_USAGE_DB=str(self.root / 'usage.sqlite3'), PYTHONUTF8='1')
        return subprocess.run([sys.executable, '-B', str(SCRIPTS / 'rds_cli.py'), '--root', str(self.root), *args],
                              capture_output=True, text=True, encoding='utf-8', env=env, timeout=30)

    def test_original_goal_bytes_are_immutable_and_append_only(self):
        original = assets.bind_objective(self.root, self.goal)
        self.assertEqual(assets.blob(self.root, original['asset']), self.goal)
        self.assertEqual(assets.bind_objective(self.root, self.goal), original)
        changed = dict(GOAL, completion_standard='only a local upper bound')
        with self.assertRaisesRegex(ValueError, 'immutable'):
            assets.bind_objective(self.root, json.dumps(changed).encode())
        self.assertEqual(assets.objective(self.root), original)
        db = sqlite3.connect(self.root / '.rds' / 'project.sqlite3')
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE research_records SET body='{}'")
        finally:
            db.close()
        self.assertFalse((self.root / '.rds' / 'state.sqlite3').exists())

    def test_goal_schema_missing_fields_and_duplicate_keys_are_rejected(self):
        for raw in (b'{}', b'{"schema":1,"schema":2}', json.dumps(dict(GOAL, assumptions='none')).encode()):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                assets.bind_objective(self.root, raw)
        self.assertFalse((self.root / '.rds' / 'project.sqlite3').exists())

    def test_original_assets_and_transitive_dependencies_survive_refutation(self):
        assets.bind_objective(self.root, self.goal)
        a = assets.put(self.root, 'L3', 'lemma', b'original lemma')
        assets.put(self.root, 'T1', 'lemma', b'theorem', dependencies=['L3'])
        assets.put(self.root, 'U2', 'geometry', b'upper bound', dependencies=['T1'])
        witness = self.write('witness.json', '{"counterexample": [1, 2]}')
        args = SimpleNamespace(action='refute', root=self.root, id='L3', reason='missing hypothesis', evidence=witness)
        result = assets.command(args)
        self.assertEqual(result['status'], 'DECLARED_REFUTATION')
        self.assertEqual(result['review']['affected'], ['T1', 'U2', result['record']['id']])
        self.assertEqual(assets.get(self.root, 'L3'), a)
        self.assertEqual(assets.get(self.root, 'T1')['mathematical_status'], 'UNKNOWN')

    def test_missing_and_self_dependencies_do_not_create_records(self):
        assets.bind_objective(self.root, self.goal)
        for dep in ('missing', 'new'):
            with self.subTest(dep=dep), self.assertRaises(ValueError):
                assets.put(self.root, 'new', 'lemma', b'text', dependencies=[dep])
        self.assertIsNone(assets.get(self.root, 'new'))

    def test_goal_context_and_source_integrity_are_checked(self):
        assets.bind_objective(self.root, self.goal)
        context = {'decision': {'id': 'exact-cover', 'goal_revision': '1', 'scope': GOAL['scope']}}
        assets.check_context(self.root, context)
        local = {'decision': {'id': 'local-lemma', 'goal_revision': '1', 'scope': {'domain': 'unit-disk', 'n': 6}}}
        self.assertEqual(assets.check_context(self.root, local)['sha256'], hashlib.sha256(self.goal).hexdigest())
        with self.assertRaisesRegex(ValueError, 'differs'):
            assets.check_context(self.root, {'objective_binding': {'sha256': 'wrong'}})
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            assets.check_context(self.root, {'scope': {'domain': 'other'}})
        source = assets.objective(self.root)['asset']['path']
        (self.root / source).write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            assets.objective(self.root)

    def test_extract_never_executes_source_and_freezes_local_dependencies(self):
        self.candidate()
        candidate = assets.get(self.root, 'tool:compare-v1')
        code = assets.blob(self.root, candidate['asset']).decode()
        self.assertNotIn('pathlib', code)
        self.assertIn('def helper', code)
        self.assertEqual(candidate['data']['purity'], 'NOT_PROVED')
        self.assertFalse((self.root / 'MUST_NOT_EXECUTE').exists())
        self.assertEqual(assets.blob(self.root, candidate['data']['origin']), SOURCE.encode())

    def test_unsupported_extractions_stop_without_execution(self):
        snippets = ["import os\ndef f(): return os.getcwd()", "def f(): return open('x')",
                    "@unknown\ndef f(): return 1", "def f(x=print('side effect')): return x",
                    "X = []\ndef f(): return X", "def f(x): return x.__class__",
                    "X = 1\nX = 2\ndef f(): return X", "def f():\n global X\n return 1",
                    "def f(x=[]):\n x.append(1)\n return len(x)"]
        for source in snippets:
            with self.subTest(source=source), self.assertRaises((ValueError, SyntaxError)):
                tools.extract_function(source.encode(), 'f')

    def test_real_validation_and_registered_function_reuse(self):
        cases = self.candidate()
        checked = tools.validate(self.root, 'compare-v1', cases, timeout=10)
        self.assertEqual(checked['status'], 'LOCAL_CASES_PASSED')
        registered = tools.register(self.root, 'compare-v1')
        module = runpy.run_path(registered['module'])
        self.assertTrue(module['decide'](1, 3))
        self.assertFalse(module['decide'](2, 3))
        self.assertEqual(registered['assurance'], 'LOCAL_CASES_ONLY')
        again = tools.validate(self.root, 'compare-v1', cases, timeout=10)
        self.assertFalse(again['execution_started'])
        self.assertEqual(again['id'], checked['id'])
        self.assertFalse((Path(checked['job_root']) / 'MUST_NOT_EXECUTE').exists())

    def test_failed_local_cases_cannot_register(self):
        self.candidate()
        bad = self.write('wrong.json', '[{"args":[1,3],"expected":false}]')
        checked = tools.validate(self.root, 'compare-v1', bad)
        self.assertEqual(checked['status'], 'FAILED')
        self.assertTrue((Path(checked['job_root']) / 'outputs' / 'result.json').is_file())
        with self.assertRaisesRegex(ValueError, 'passing'):
            tools.register(self.root, 'compare-v1', checked['id'])

    def test_changed_actual_validation_inputs_block_registration(self):
        checked = tools.validate(self.root, 'compare-v1', self.candidate())
        (Path(checked['job_root']) / 'candidate.py').write_text('def decide(*args): return True\n')
        with self.assertRaisesRegex(ValueError, 'bindings changed'):
            tools.register(self.root, 'compare-v1', checked['id'])

    def test_changed_original_source_and_ambiguous_validation_block_completion(self):
        cases = self.candidate()
        tools.validate(self.root, 'compare-v1', cases)
        second = self.write('second.json', '[{"args":[2,3],"expected":false}]')
        tools.validate(self.root, 'compare-v1', second)
        with self.assertRaisesRegex(ValueError, '--validation'):
            tools.register(self.root, 'compare-v1')
        candidate = assets.get(self.root, 'tool:compare-v1')
        (self.root / candidate['data']['origin']['path']).write_bytes(b'changed original')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            assets.get(self.root, 'tool:compare-v1')

    def test_explicit_record_and_case_bounds_stop_without_claiming_success(self):
        for cases in ([], [{}], [{'expected': 1, 'expected_error': 'ValueError'}],
                      [{'expected_error': 'NotAnException'}], [{'expected': True}] * 65):
            with self.subTest(cases=cases), self.assertRaises(ValueError):
                tools._cases(json.dumps(cases).encode())
        with self.assertRaisesRegex(ValueError, '512 KiB'):
            tools.extract_function(b'#' * (512 * 1024 + 1), 'f')
        with self.assertRaisesRegex(ValueError, '64 KiB'):
            assets.objective_spec(b' ' * (64 * 1024 + 1))

    def test_shadowed_builtins_are_preserved_and_exception_aliases_remain_local(self):
        source = b'def sum(x): return 7\ndef f(x):\n try: return sum(x)\n except ValueError as exc: return str(exc)\n'
        code, names = tools.extract_function(source, 'f')
        self.assertEqual(names, ['f', 'sum'])
        path = self.write('shadowed.py', code)
        self.assertEqual(runpy.run_path(str(path))['f']([1, 2]), 7)

    def test_declared_counterexample_blocks_local_reuse_without_erasing_module(self):
        checked = tools.validate(self.root, 'compare-v1', self.candidate())
        registered = tools.register(self.root, 'compare-v1', checked['id'])
        assets.put(self.root, 'refutation:bad-domain', 'refutation', b'witness',
                   dependencies=['tool:compare-v1'], data={'target': 'tool:compare-v1', 'verdict': 'DECLARED_REFUTATION'})
        with self.assertRaisesRegex(ValueError, 'refutation'):
            tools.register(self.root, 'compare-v1', checked['id'])
        self.assertTrue(Path(registered['module']).is_file())

    def test_tool_cli_and_export_are_native_and_compact(self):
        cases = self.write('cases.json', json.dumps(CASES))
        source = self.write('source.py', SOURCE)
        result = self.cli('tools', 'extract', '--source', str(source), '--entry', 'decide', '--name', 'compare-v1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(len(result.stdout), 1000)
        checked = self.cli('rsi', 'validate', '--name', 'compare-v1', '--cases', str(cases))
        self.assertEqual(checked.returncode, 0, checked.stderr)
        identity = json.loads(checked.stdout)['id']
        registered = self.cli('rsi', 'register', '--name', 'compare-v1', '--validation', identity)
        self.assertEqual(registered.returncode, 0, registered.stderr)
        exported = self.cli('rsi', 'use', '--name', 'compare-v1', '--output', 'compare.py')
        self.assertEqual(exported.returncode, 0, exported.stderr)
        self.assertTrue(runpy.run_path(str(self.root / 'compare.py'))['decide'](1, 3))
        self.write('occupied.py', 'existing user code')
        blocked = self.cli('rsi', 'use', '--name', 'compare-v1', '-o', 'occupied.py')
        self.assertNotEqual(blocked.returncode, 0)
        self.assertEqual((self.root / 'occupied.py').read_text(), 'existing user code')

    def test_goal_is_bound_before_and_after_real_quick_execution(self):
        self.write('objective.json', self.goal)
        self.write('probe.py', 'print(1)\n')
        result = self.cli('exec', '--objective', 'objective.json', '-t', '5', '--json', '--', 'probe.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        job = Path(json.loads(result.stdout)['job_root'])
        state = ProjectStore(job).snapshot(check_bindings=True)
        self.assertEqual(state['contract']['objective_sha256'], hashlib.sha256(self.goal).hexdigest())
        self.assertFalse(state['binding_check']['errors'])
        target = job / assets.objective(job)['asset']['path']
        target.write_bytes(b'changed goal')
        self.assertTrue(ProjectStore(job).snapshot(check_bindings=True)['binding_check']['errors'])

    def test_old_operational_contract_is_not_relabelled_by_a_new_goal(self):
        self.write('probe.py', 'print(1)\n')
        result = self.cli('exec', '--json', '--', 'probe.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        job = Path(json.loads(result.stdout)['job_root'])
        original = ProjectStore(job).snapshot()['contract_sha256']
        with self.assertRaisesRegex(ValueError, 'retroactively'):
            assets.bind_objective(job, self.goal)
        self.assertIsNone(assets.objective(job))
        self.assertEqual(ProjectStore(job).snapshot()['contract_sha256'], original)

    def test_aliases_and_usage_keep_new_values_and_child_arguments(self):
        args = parser().parse_args(['tools', 'extract', '--source', 'exact-path.py', '--entry', 'f', '--name', 'original'])
        self.assertEqual((args.command, args.source, args.name), ('rsi', 'exact-path.py', 'original'))
        self.assertEqual(_label(['exec', '--objective', 'goal.json', 'probe.py', '--help']), ('exec', 'command'))
        self.assertEqual(_label(['数学', 'status']), ('math', 'command'))

    def test_advisor_can_consume_a_native_goal_without_an_operational_contract(self):
        assets.bind_objective(self.root, self.goal)
        context = {'decision': {'id': 'exact-cover', 'goal_revision': '1', 'scope': GOAL['scope']}, 'facts': {}}
        path = self.write('context.json', json.dumps(context))
        graph = self.write('graph.json', '{"schema":1,"nodes":[],"edges":[]}')
        result = self.cli('advise', '--research-context', str(path), '--graph', str(graph))
        self.assertEqual(result.returncode, 0, result.stderr)
        path.write_text(json.dumps(dict(context, decision=dict(context['decision'], goal_revision='2'))))
        changed = self.cli('advise', '--research-context', str(path), '--graph', str(graph))
        self.assertNotEqual(changed.returncode, 0)
        self.assertIn('frozen objective', changed.stderr)

    def test_native_goal_is_visible_during_local_advisor_review(self):
        assets.bind_objective(self.root, self.goal)
        context = {'decision': {'id': 'local-lemma', 'goal_revision': '1', 'scope': GOAL['scope']}, 'facts': {}}
        action = {'id': 'check', 'kind': 'OBLIGATION_CHECK', 'target': 'lemma', 'claim': 'A local implication',
                  'description': 'Check one scoped lemma',
                  'required_observables': ['certificate'], 'outcomes': [
                      {'observation': label, 'next_decision': label} for label in ('verified', 'counterexample', 'unresolved')]}
        graph = {'schema': 1, 'nodes': [{'id': 'route', 'executable': {
            'decisions': ['local-lemma'], 'preconditions': [], 'action': action}}], 'edges': []}
        context_path = self.write('context.json', json.dumps(context))
        graph_path = self.write('graph.json', json.dumps(graph))
        result = self.cli('advise', '--research-context', str(context_path), '--graph', str(graph_path))
        self.assertEqual(result.returncode, 0, result.stderr)
        advice = json.loads(result.stdout)
        search = next(row['search'] for row in advice['recommendations'] if 'search' in row)
        review = search['selection_review']
        self.assertEqual(review['objective_binding'], advice['objective_binding'])
        self.assertEqual(review['next_move']['kind'], 'REVIEW_GOAL_LINK')
        self.assertEqual(search['candidates'][0]['status'], 'READY')
        self.assertEqual(json.loads(context_path.read_text()), context)

    def test_artifact_import_retains_goal_map_and_rejects_conflicting_binding(self):
        assets.bind_objective(self.root, self.goal)
        source = Path(__file__).resolve().parents[1] / 'examples/goal-linked-hypergraph.json'
        context = {'decision': {'id': 'local-lemma', 'goal_revision': '1', 'scope': GOAL['scope']},
                   'facts': {}, 'research_mode': 'theory', 'dependency_map': json.loads(source.read_text())}
        action = {'id': 'check', 'kind': 'OBLIGATION_CHECK', 'target': 'closed_small_case',
                  'claim': 'A local case', 'description': 'Check one local case', 'required_observables': ['certificate'],
                  'outcomes': [{'observation': label, 'next_decision': label}
                               for label in ('verified', 'counterexample', 'unresolved')],
                  'goal_contribution': {'target': 'completion_standard',
                      'path': ['closed_small_case', 'completion_standard'], 'source': 'synthetic contract'}}
        graph = {'schema': 1, 'nodes': [{'id': 'route', 'executable': {
            'decisions': ['local-lemma'], 'preconditions': [], 'action': action}}], 'edges': []}
        cp = self.write('context.json', json.dumps(context))
        gp = self.write('graph.json', json.dumps(graph))
        ap = self.write('artifacts.json', '{"schema":"rds-artifact-manifest-v1","sources":[]}')
        result = self.cli('advise', '--research-context', str(cp), '--graph', str(gp), '--artifacts', str(ap))
        self.assertEqual(result.returncode, 0, result.stderr)
        advice = json.loads(result.stdout)
        review = next(r['search']['selection_review'] for r in advice['recommendations'] if 'search' in r)
        self.assertEqual(review['dependency_review']['status'], 'ANALYZED')
        self.assertEqual(review['candidates'][0]['goal_contribution']['status'], 'UNKNOWN')
        self.assertEqual(review['next_move']['kind'], 'REVIEW_GOAL_LINK')
        context['objective_binding'] = {'sha256': 'conflicting supplied original goal'}
        cp.write_text(json.dumps(context))
        changed = self.cli('advise', '--research-context', str(cp), '--graph', str(gp), '--artifacts', str(ap))
        self.assertNotEqual(changed.returncode, 0)
        self.assertIn('differs', changed.stderr)
        del context['objective_binding']
        context['scope'] = {**GOAL['scope'], 'domain': 'conflicting declared original domain'}
        cp.write_text(json.dumps(context))
        for imports in ([], ['--artifacts', str(ap)]):
            with self.subTest(imports=imports):
                changed = self.cli('advise', '--research-context', str(cp), '--graph', str(gp), *imports)
                self.assertNotEqual(changed.returncode, 0)
                self.assertIn('scope conflicts', changed.stderr)


if __name__ == '__main__':
    unittest.main()
