"""Method restrictions apply to described steps, not algorithm-name guesses."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from rds_methods import review_methods
from rds_advisor_search import search_directions
from rds_quick import choice


def policy():
    return {'method_constraints': [
        {'id': 'candidate-search', 'quote': 'No heuristic candidate search; strict assisted proof allowed',
         'source': 'user-confirmation:fixture', 'status': 'CONFIRMED',
         'when': {'purpose': 'candidate_search'}, 'forbid': {'technique': 'heuristic'}},
        {'id': 'exact-proof', 'quote': 'Proof arithmetic must be rigorous',
         'source': 'user:fixture', 'status': 'CONFIRMED',
         'when': {'purpose': 'proof'}, 'require': {'arithmetic': 'certified'}},
        {'id': 'cpu', 'quote': 'CPU only', 'source': 'user:fixture',
         'status': 'CONFIRMED', 'require': {'device': 'cpu'}}]}


def method(purpose='proof', technique='certifying_branch_bound', **fields):
    return {'purpose': purpose, 'technique': technique, 'arithmetic': 'certified', 'device': 'cpu', **fields}


def fixture(profile):
    action = {'id': 'test', 'description': 'Check a fixed declared obligation', 'target': 'claim', 'operation': 'check',
              'competing_explanations': ['supported', 'counterexample'], 'required_observables': ['certificate'],
              'outcomes': [{'observation': 'verified', 'next_decision': 'retain'},
                           {'observation': 'refuted', 'next_decision': 'revise'}]}
    if profile is not None:
        action['methods'] = profile
    graph = {'nodes': [{'id': 'rule', 'executable': {'decisions': ['next'], 'preconditions': [], 'action': action,
        'satisfied_when': [{'fact': 'done', 'value': True}]}}], 'edges': []}
    context = {**policy(), 'decision': {'id': 'next', 'goal_revision': 'fixed-goal', 'scope': {'domain': 'fixture'}},
               'facts': {'done': {'value': False, 'source': 'fixture:unfinished'}}}
    return graph, context


class MethodTests(unittest.TestCase):
    def test_execution_engine_identity_binds_the_method_checker_source(self):
        from rds_cli import engine_id
        original = Path.read_bytes
        before = engine_id()
        def changed(path):
            raw = original(path)
            return raw + b'\n# changed admission gate\n' if path.name == gate else raw
        for gate in ('rds_methods.py', 'rds_advisor_search.py', 'rds_advisor.py'):
            with patch.object(Path, 'read_bytes', changed):
                self.assertNotEqual(engine_id(), before)

    def test_verification_and_certifying_proof_are_not_candidate_search(self):
        for profile in (method('verification', 'exact_replay'), method(),
                        method('candidate_search', 'constructive_exact')):
            with self.subTest(profile=profile):
                report = review_methods(policy(), profile)
                self.assertEqual(report['status'], 'COMPATIBLE')
                self.assertEqual(report['assurance'], 'INPUT_REPORTED')
        # Deterministic or exact arithmetic alone does not change the purpose.
        self.assertEqual(review_methods(policy(), method('candidate_search', 'heuristic'))['status'], 'CONFLICT')
        self.assertEqual(review_methods(policy(), method(device='gpu'))['status'], 'CONFLICT')
        self.assertEqual(review_methods(policy(), method(arithmetic='floating_point'))['status'], 'CONFLICT')

    def test_a_bundled_search_cannot_hide_behind_a_proof_step(self):
        rows = [method(), method('candidate_search', 'heuristic')]
        before = deepcopy(rows)
        report = review_methods(policy(), rows)
        self.assertEqual(report['status'], 'CONFLICT')
        self.assertEqual(report['issues'][0]['step'], 1)
        self.assertEqual(rows, before)

    def test_missing_fields_need_description_not_invented_permission(self):
        for rows in (None, {}, {'purpose': 'proof', 'device': 'cpu'}):
            report = review_methods(policy(), rows)
            self.assertEqual(report['status'], 'UNKNOWN')
            self.assertEqual(report['questions'], [])
        with self.assertRaisesRegex(ValueError, '1..32 steps'):
            review_methods(policy(), [])

    def test_material_ambiguity_asks_once_and_unaffected_work_stays_available(self):
        context = {'method_constraints': [{'id': 'search', 'quote': 'No numerical search',
                   'source': 'user:fixture', 'status': 'UNRESOLVED',
                   'when': {'purpose': 'candidate_search'}, 'question': 'Does this include certified exhaustive proof?'}]}
        report = review_methods(context, [method('candidate_search'), method('candidate_search', 'heuristic')])
        self.assertEqual(report['status'], 'UNKNOWN')
        self.assertEqual(len(report['questions']), 1)
        self.assertEqual(report['questions'][0]['quote'], 'No numerical search')
        self.assertEqual(review_methods(context, method('verification'))['status'], 'COMPATIBLE')

    def test_confirmed_predicates_and_source_identity_are_required(self):
        for field in ('id', 'source', 'quote', 'status', 'forbid'):
            context = policy()
            del context['method_constraints'][0][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                review_methods(context, method())
        context = policy()
        context['method_constraints'].append(deepcopy(context['method_constraints'][0]))
        with self.assertRaisesRegex(ValueError, 'unique id'):
            review_methods(context, method())
        with self.assertRaisesRegex(ValueError, 'at most 32'):
            review_methods({'method_constraints': policy()['method_constraints'] * 11}, method())

    def test_conflict_wins_over_another_unknown_and_text_is_not_fuzzy_matched(self):
        context = policy()
        context['method_constraints'].append({'id': 'unclear', 'quote': 'Do it analytically',
            'source': 'user:fixture', 'status': 'UNRESOLVED'})
        self.assertEqual(review_methods(context, method(device='gpu'))['status'], 'CONFLICT')
        # These labels are caller-defined exact values; spelling differences are not corrected into grants.
        self.assertEqual(review_methods(policy(), method(device='CPU'))['status'], 'CONFLICT')

    def test_search_retains_scope_specific_alternatives_and_unknown_description(self):
        graph, context = fixture(method())
        before = deepcopy((graph, context))
        candidate = search_directions(graph, context)['candidates'][0]
        self.assertEqual(candidate['status'], 'READY')
        self.assertEqual(candidate['method_review']['status'], 'COMPATIBLE')
        self.assertEqual((graph, context), before)
        graph['nodes'][0]['executable']['action']['methods'] = method('candidate_search', 'heuristic')
        report = search_directions(graph, context)
        self.assertEqual(report['candidates'], [])
        self.assertEqual(report['blocked_candidates'][0]['status'], 'BLOCKED_METHOD')
        del graph['nodes'][0]['executable']['action']['methods']
        self.assertEqual(search_directions(graph, context)['candidates'][0]['status'], 'NEEDS_METHOD_DESCRIPTION')

    def test_choice_rechecks_a_forged_ready_label_and_keeps_original_clauses(self):
        graph, context = fixture(method())
        advice = {'recommendations': [{'type': 'EXECUTABLE_DIRECTION_SEARCH', 'search': search_directions(graph, context)}]}
        saved = choice(advice, context, 'rule:test')
        self.assertEqual(saved['method_constraints'], context['method_constraints'])
        self.assertEqual(saved['scientific_support'], 'UNKNOWN')
        candidate = advice['recommendations'][0]['search']['candidates'][0]
        candidate['action']['methods'] = [method(), method('candidate_search', 'heuristic')]
        candidate['method_review'] = {'status': 'COMPATIBLE'}
        with self.assertRaisesRegex(ValueError, 'Method scope'):
            choice(advice, context, 'rule:test')

    def test_unconstrained_legacy_context_does_not_add_a_gate(self):
        graph, context = fixture(None)
        del context['method_constraints']
        candidate = search_directions(graph, context)['candidates'][0]
        self.assertEqual(candidate['status'], 'READY')
        self.assertNotIn('method_review', candidate)


if __name__ == '__main__':
    unittest.main()
