"""Declared research obstructions reach the next move through the real Advisor entry (#43).

All goals, sources and values are synthetic. A declared obstruction is reported input:
it selects a bounded response, never a diagnosis, installation or new authorization.
"""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from rds_advisor_search import search_directions


def route(goal, decision='next', kind='PAIRED_TEST', node='route'):
    action = {'id': node + '-check', 'kind': kind, 'description': 'Synthetic bounded check',
              'target': goal, 'competing_explanations': ['premise holds', 'premise fails'],
              'required_observables': ['reported outcome'],
              'outcomes': [{'observation': 'positive', 'next_decision': 'continue'},
                           {'observation': 'negative', 'next_decision': 'revise'}],
              'goal_contribution': {'target': goal, 'path': [goal], 'source': 'synthetic-protocol.json'}}
    return {'nodes': [{'id': node, 'executable': {'decisions': [decision], 'preconditions': [], 'action': action}}],
            'edges': []}


def context(goal, op, value, fact_value=None, scope='synthetic'):
    facts = {} if fact_value is None else {goal: {'value': fact_value, 'source': 'synthetic-observation.json'}}
    return {'research_mode': 'empirical', 'facts': facts,
            'decision': {'id': 'next', 'goal_revision': 'synthetic-v1', 'scope': {'domain': scope},
                         'goal_conditions': [{'fact': goal, 'op': op, 'value': value}]}}


def obstruction(goal, cause, **extra):
    record = {'id': 'o-' + cause.lower(), 'obligation': goal, 'cause': cause, 'source': 'synthetic-run-log.txt#L7'}
    record.update(extra)
    return record


REQUIREMENT = {'input': 'aligned held-out trajectories and the declared model checkpoint',
               'operation': 'roll out the declared model on each aligned trajectory',
               'output': 'per-step error table bound to the trajectory hashes'}

# Initial acceptance settings, in the documented order; not domain restrictions.
DEEP_LEARNING = ('heldout_trajectory_error', 'lte', 0.1, 0.3)
SOFTWARE_TOOL = ('recovery_invariant_checked', 'eq', True, None)
MATHEMATICS = ('exact_identity_checked', 'eq', True, None)


class CapabilityRequirementCLITests(unittest.TestCase):
    def advise(self, ctx, graph, *extra, expect=0):
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / 'context.json').write_text(json.dumps(ctx), encoding='utf-8')
            (project / 'graph.json').write_text(json.dumps(graph), encoding='utf-8')
            (project / 'manifest.json').write_text(json.dumps({'schema': 'rds-artifact-manifest-v1', 'sources': []}),
                                                   encoding='utf-8')
            args = [a.replace('{manifest}', str(project / 'manifest.json')) for a in extra]
            proc = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/rds_cli.py'), '--root', str(project),
                                   'advise', '--research-context', str(project / 'context.json'),
                                   '--graph', str(project / 'graph.json'), *args],
                                  cwd=ROOT, capture_output=True, encoding='utf-8', timeout=20)
            self.assertEqual(proc.returncode, expect, proc.stderr)
            self.assertFalse((project / '.rds').exists())
            self.assertEqual(json.loads((project / 'context.json').read_text(encoding='utf-8')), ctx)
            if expect:
                return proc
            answer = json.loads(proc.stdout)
            return next(row['search'] for row in answer['recommendations']
                        if row.get('type') == 'EXECUTABLE_DIRECTION_SEARCH')['selection_review']

    def baseline_and_review(self, setting, records, graph=None):
        goal, op, value, fact = setting
        ctx = context(goal, op, value, fact)
        graph = graph or route(goal)
        baseline = self.advise(ctx, graph)
        ctx['obstructions'] = records
        return baseline, self.advise(ctx, graph)

    def test_deep_learning_unsupported_operation_yields_source_bound_requirement_and_keeps_move_kind(self):
        goal = DEEP_LEARNING[0]
        record = obstruction(goal, 'UNSUPPORTED_OPERATION', requirement=REQUIREMENT, signals=['trajectory_degradation'])
        baseline, review = self.baseline_and_review(DEEP_LEARNING, [record])
        self.assertEqual(review['goal']['status'], 'FALSE')
        self.assertNotIn('obstruction_review', baseline)
        self.assertNotIn('obstructions', baseline['next_move'])
        # The decision order is unchanged: the declared obstruction informs, it does not reroute.
        self.assertEqual(review['next_move']['kind'], baseline['next_move']['kind'])
        self.assertEqual(review['next_move']['authorization'], 'UNCHANGED')
        entry = review['obstruction_review'][0]
        self.assertEqual((entry['status'], entry['response']), ('APPLICABLE', 'CAPABILITY_REQUIRED'))
        self.assertEqual(entry['assurance'], 'INPUT_REPORTED_OBSTRUCTION_NOT_DIAGNOSIS')
        required = entry['required_capability']
        self.assertEqual({k: required[k] for k in ('input', 'operation', 'output')}, REQUIREMENT)
        self.assertEqual(required['obligation'], goal)
        self.assertEqual(required['obstruction_source'], record['source'])
        catalogue = required['catalogue']
        self.assertEqual(catalogue['coverage'], 'BOUNDED_CATALOGUE_NOT_EXHAUSTIVE')
        self.assertEqual(catalogue['prerequisites'], 'NOT_ASSESSED')
        self.assertTrue(catalogue['shortlist'])
        self.assertTrue(all(card['locator'].startswith('references/theory-tools.json#/cards/')
                            for card in catalogue['shortlist']))
        self.assertLessEqual(len(catalogue['shortlist']), 3)
        self.assertEqual(review['next_move']['obstructions'],
                         [{'id': record['id'], 'response': 'CAPABILITY_REQUIRED',
                           'ref': 'selection_review.obstruction_review[0]'}])
        self.assertIn('input/operation/output contract', review['next_move']['prompt'])
        self.assertIn('smallest repair', review['next_move']['prompt'])

    def test_deep_learning_missing_data_selects_evidence_repair_not_a_capability_gap(self):
        goal = DEEP_LEARNING[0]
        record = obstruction(goal, 'MISSING_INPUT', requirement=REQUIREMENT)
        baseline, review = self.baseline_and_review(DEEP_LEARNING, [record])
        entry = review['obstruction_review'][0]
        self.assertEqual(entry['response'], 'EVIDENCE_REPAIR')
        self.assertNotIn('required_capability', entry)
        self.assertIn(REQUIREMENT['input'], entry['next'])
        self.assertEqual(review['next_move']['kind'], baseline['next_move']['kind'])

    def test_software_tool_cap_dependency_and_adapter_obstructions_stay_distinct(self):
        goal = SOFTWARE_TOOL[0]
        records = [obstruction(goal, 'EXECUTION_CAP'),
                   obstruction(goal, 'DEPENDENCY_UNAVAILABLE', id='dep-known', dependency='sympy_exact'),
                   obstruction(goal, 'DEPENDENCY_UNAVAILABLE', id='dep-other', dependency='external_solver'),
                   obstruction(goal, 'ADAPTER_MISMATCH')]
        baseline, review = self.baseline_and_review(SOFTWARE_TOOL, records)
        self.assertEqual(review['goal']['status'], 'UNKNOWN')
        self.assertEqual(review['next_move']['kind'], baseline['next_move']['kind'])
        self.assertEqual(review['next_move']['kind'], 'RESOLVE_PREMISE')
        entries = {e['id']: e for e in review['obstruction_review']}
        cap = entries['o-execution_cap']
        self.assertEqual(cap['response'], 'INCOMPLETE_COMPUTATION')
        self.assertIn('not a refutation', cap['next'])
        self.assertTrue(all('required_capability' not in e for e in entries.values()))
        known, other = entries['dep-known'], entries['dep-other']
        self.assertEqual((known['response'], known['dependency']), ('DEPENDENCY_REPORT', 'sympy_exact'))
        self.assertIn('rds_capabilities.py --capability sympy_exact', known['live_check'])
        self.assertEqual((other['response'], other['dependency']), ('DEPENDENCY_REPORT', 'external_solver'))
        self.assertIsNone(other['live_check'])
        self.assertEqual(entries['o-adapter_mismatch']['response'], 'ADAPTER_REPAIR')
        self.assertIn('UNKNOWN', entries['o-adapter_mismatch']['next'])
        self.assertEqual([o['response'] for o in review['next_move']['obstructions']],
                         ['INCOMPLETE_COMPUTATION', 'DEPENDENCY_REPORT', 'DEPENDENCY_REPORT', 'ADAPTER_REPAIR'])

    def test_mathematics_unsupported_check_without_contract_or_source_keeps_the_cause_unknown(self):
        goal = MATHEMATICS[0]
        sourced = obstruction(goal, 'UNSUPPORTED_OPERATION', id='exact',
                              requirement={'input': 'the encoded statement and its allowed premises',
                                           'operation': 'exact symbolic identity check',
                                           'output': 'certificate or counterexample for the encoded statement'},
                              signals=['proof_bottleneck'])
        no_contract = obstruction(goal, 'UNSUPPORTED_OPERATION', id='vague')
        unsourced = obstruction(goal, 'UNSUPPORTED_OPERATION', id='unsourced', requirement=REQUIREMENT)
        del unsourced['source']
        undetermined = obstruction(goal, 'UNDETERMINED', id='unclear')
        _, review = self.baseline_and_review(MATHEMATICS, [sourced, no_contract, unsourced, undetermined])
        entries = {e['id']: e for e in review['obstruction_review']}
        self.assertEqual(entries['exact']['response'], 'CAPABILITY_REQUIRED')
        self.assertTrue(entries['exact']['required_capability']['catalogue']['shortlist'])
        for name in ('vague', 'unsourced', 'unclear'):
            with self.subTest(name=name):
                self.assertEqual(entries[name]['response'], 'DISCRIMINATING_CHECK')
                self.assertEqual(entries[name]['cause_status'], 'UNKNOWN')
                self.assertNotIn('required_capability', entries[name])

    def test_requirement_without_signals_reports_an_unsearched_catalogue(self):
        goal = MATHEMATICS[0]
        record = obstruction(goal, 'UNSUPPORTED_OPERATION', requirement=REQUIREMENT)
        _, review = self.baseline_and_review(MATHEMATICS, [record])
        catalogue = review['obstruction_review'][0]['required_capability']['catalogue']
        self.assertEqual(catalogue['status'], 'NOT_SEARCHED')
        self.assertEqual(catalogue['shortlist'], [])
        self.assertEqual(catalogue['coverage'], 'BOUNDED_CATALOGUE_NOT_EXHAUSTIVE')

    def test_changed_evidence_scope_or_unrelated_obligation_reopens_the_route(self):
        goal, op, value, _ = DEEP_LEARNING
        record = obstruction(goal, 'UNSUPPORTED_OPERATION', requirement=REQUIREMENT)
        cases = {
            'evidence now satisfies the goal': (context(goal, op, value, 0.05), record),
            'declared scope differs': (context(goal, op, value, 0.3), {**record, 'scope': {'domain': 'older'}}),
            'not an existing goal predicate': (context(goal, op, value, 0.3), {**record, 'obligation': 'other_goal'}),
        }
        for name, (ctx, item) in cases.items():
            with self.subTest(name):
                baseline = self.advise(ctx, route(goal))
                ctx['obstructions'] = [item]
                review = self.advise(ctx, route(goal))
                entry = review['obstruction_review'][0]
                self.assertEqual(entry['status'], 'NOT_APPLICABLE')
                self.assertNotIn('response', entry)
                self.assertEqual(review.get('next_move'), baseline.get('next_move'))
        ctx = context(goal, op, value, 0.3)
        ctx['obstructions'] = [{**record, 'scope': {'domain': 'synthetic'}}]
        self.assertEqual(self.advise(ctx, route(goal))['obstruction_review'][0]['status'], 'APPLICABLE')

    def test_artifacts_entry_keeps_declared_obstructions(self):
        goal = DEEP_LEARNING[0]
        ctx = context(*DEEP_LEARNING)
        ctx['obstructions'] = [obstruction(goal, 'MISSING_INPUT', requirement=REQUIREMENT)]
        plain = self.advise(ctx, route(goal))
        imported = self.advise(ctx, route(goal), '--artifacts', '{manifest}')
        self.assertEqual(imported['obstruction_review'], plain['obstruction_review'])
        self.assertEqual(imported['next_move'], plain['next_move'])

    def test_repeated_review_is_identical_and_brief_stays_compact(self):
        goal = DEEP_LEARNING[0]
        ctx = context(*DEEP_LEARNING)
        ctx['obstructions'] = [obstruction(goal, 'UNSUPPORTED_OPERATION', requirement=REQUIREMENT,
                                           signals=['trajectory_degradation'])]
        first, second = self.advise(ctx, route(goal)), self.advise(ctx, route(goal))
        self.assertEqual(first, second)
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / 'context.json').write_text(json.dumps(ctx), encoding='utf-8')
            (project / 'graph.json').write_text(json.dumps(route(goal)), encoding='utf-8')
            proc = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/rds_cli.py'), '--root', str(project),
                                   'advise', '--context', str(project / 'context.json'),
                                   '--graph', str(project / 'graph.json'), '--brief'],
                                  cwd=ROOT, capture_output=True, encoding='utf-8', timeout=20)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertLess(len(proc.stdout.encode('utf-8')), 1024)
            summary = json.loads(proc.stdout)
            full = json.loads(Path(summary['record']).read_text(encoding='utf-8'))
            search = next(r['search'] for r in full['recommendations'] if r['type'] == 'EXECUTABLE_DIRECTION_SEARCH')
            self.assertEqual(search['selection_review'], first)

    def test_malformed_obstructions_are_rejected_with_the_field_name(self):
        goal = DEEP_LEARNING[0]
        good = obstruction(goal, 'MISSING_INPUT')
        cases = [
            ('not a list', {'id': 'x'}, r'advisor_context\.obstructions must be a list of 1 to 8'),
            ('empty', [], r'advisor_context\.obstructions must be a list of 1 to 8'),
            ('too many', [{**good, 'id': f'o{i}'} for i in range(9)], r'list of 1 to 8'),
            ('record type', [5], r'obstructions\[0\] must be an object'),
            ('unknown field', [{**good, 'severity': 'high'}], r'obstructions\[0\] has unknown field\(s\): severity'),
            ('missing id', [{k: v for k, v in good.items() if k != 'id'}], r'obstructions\[0\]\.id'),
            ('duplicate id', [good, dict(good)], r'obstructions\[1\]\.id duplicates'),
            ('bad cause', [{**good, 'cause': 'FLAKY'}], r'obstructions\[0\]\.cause must be one of'),
            ('bad obligation', [{**good, 'obligation': ''}], r'obstructions\[0\]\.obligation'),
            ('requirement keys', [{**good, 'requirement': {'input': 'x'}}],
             r'obstructions\[0\]\.requirement must have exactly input, operation and output'),
            ('requirement text', [{**good, 'requirement': {**REQUIREMENT, 'output': ''}}],
             r'obstructions\[0\]\.requirement\.output'),
            ('misplaced dependency', [{**good, 'dependency': 'sympy_exact'}],
             r'obstructions\[0\]\.dependency is only valid for DEPENDENCY_UNAVAILABLE'),
            ('misplaced signals', [{**good, 'signals': ['proof_bottleneck']}],
             r'obstructions\[0\]\.signals is only valid for UNSUPPORTED_OPERATION'),
            ('bad signal', [obstruction(goal, 'UNSUPPORTED_OPERATION', requirement=REQUIREMENT, signals=['Bad Tag'])],
             r'obstructions\[0\]\.signals'),
            ('bad scope', [{**good, 'scope': 'synthetic'}], r'obstructions\[0\]\.scope must be an object'),
        ]
        for name, value, pattern in cases:
            with self.subTest(name):
                ctx = context(*DEEP_LEARNING)
                ctx['obstructions'] = value
                proc = self.advise(ctx, route(goal), expect=1)
                self.assertEqual(proc.stdout, '')
                self.assertRegex(proc.stderr, r'^\[RDS-REJECT\] ' + '.*' + pattern)
                self.assertNotIn('Traceback', proc.stderr)


class CapabilityRequirementReviewTests(unittest.TestCase):
    def test_no_key_keeps_the_review_unchanged(self):
        goal = DEEP_LEARNING[0]
        ctx = context(*DEEP_LEARNING)
        review = search_directions(route(goal), ctx)['selection_review']
        self.assertNotIn('obstruction_review', review)
        self.assertNotIn('obstructions', review['next_move'])

    def test_existing_goal_condition_error_keeps_precedence(self):
        goal = DEEP_LEARNING[0]
        ctx = context(*DEEP_LEARNING)
        ctx['decision']['goal_conditions'] = []
        ctx['obstructions'] = 'bad'
        with self.assertRaisesRegex(ValueError, 'decision.goal_conditions'):
            search_directions(route(goal), ctx)

    def test_healthy_scoped_obligation_is_not_blocked_by_a_completion_obstruction(self):
        graph = route('completion_standard', kind='OBLIGATION_CHECK')
        ctx = {'research_mode': 'theory', 'facts': {}, 'objective_binding': {'objective_sha256': 'a' * 64},
               'decision': {'id': 'next', 'scope': {'domain': 'synthetic'}},
               'obstructions': [obstruction('completion_standard', 'UNSUPPORTED_OPERATION', requirement=REQUIREMENT)]}
        original = deepcopy(ctx)
        result = search_directions(graph, ctx)
        review = result['selection_review']
        self.assertEqual(result['candidates'][0]['status'], 'READY')
        self.assertEqual(review['basis'], 'SCOPED_OBLIGATION')
        self.assertNotIn('next_move', review)
        self.assertEqual(review['obstruction_review'][0]['response'], 'CAPABILITY_REQUIRED')
        self.assertEqual(ctx, original)


if __name__ == '__main__':
    unittest.main()
