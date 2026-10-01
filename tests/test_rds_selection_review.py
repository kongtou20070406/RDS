"""Research choice regressions from proxy success and a single supplied route."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from rds_advisor import RDSAdvisor, _json
from rds_advisor_search import search_directions
from rds_quick import brief, choice


def fixture():
    action = {'id': 'probe', 'kind': 'PAIRED_TEST', 'description': 'Check a scoped training premise',
              'competing_explanations': ['bias', 'state-support'], 'required_observables': ['response'],
              'outcomes': [{'observation': 'positive', 'next_decision': 'review bounded successor'},
                           {'observation': 'negative', 'next_decision': 'revise premise'}]}
    graph = {'nodes': [{'id': 'route', 'executable': {'decisions': ['next'], 'preconditions': [], 'action': action}}], 'edges': []}
    context = {'decision': {'id': 'next', 'goal_revision': 'g1', 'scope': {'domain': 'synthetic'}}, 'facts': {}}
    return graph, context


class SelectionReviewTests(unittest.TestCase):
    def test_one_supplied_route_is_not_a_scientific_comparison(self):
        graph, context = fixture()
        original = deepcopy((graph, context))
        result = search_directions(graph, context)
        review = result['selection_review']
        self.assertEqual(result['candidates'][0]['status'], 'READY')
        self.assertEqual(review['basis'], 'REVIEW_ONLY')
        self.assertEqual(review['candidates'][0]['basis'], 'PROCEDURE_ONLY')
        self.assertEqual({f['kind'] for f in review['flags']}, {'SINGLE_CONFIGURED_DIRECTION', 'RIVAL_PREDICTIONS_MISSING'})
        self.assertEqual((graph, context), original)

    def test_valid_proxy_does_not_close_a_failed_task_goal_or_change_permission(self):
        graph, context = fixture()
        context['decision']['goal_conditions'] = [{'fact': 'long_chain_gain', 'op': 'gte', 'value': .05}]
        context['facts'] = {k: {'value': value, 'source': 'synthetic-terminal.json'} for k, value in (
            ('pipeline_valid', True), ('manipulation_passed', True), ('long_chain_gain', -.19))}
        with tempfile.TemporaryDirectory() as root:
            advisor = RDSAdvisor(root_dir=Path(root))
            advice = {'recommendations': advisor.recommend_next_directions({'advisor_context': context}, graph)}
            record = choice(advice, context)
        self.assertEqual(record['selection_review']['goal']['status'], 'FALSE')
        self.assertEqual(record['candidate']['status'], 'READY')
        self.assertEqual(record['scientific_support'], 'UNKNOWN')
        self.assertEqual(record['goal_conditions'], context['decision']['goal_conditions'])
        self.assertIn('GOAL_BRIDGE_OPEN', [f['kind'] for f in record['selection_review']['flags']])

    def test_missing_goal_source_remains_unknown(self):
        graph, context = fixture()
        context['decision']['goal_conditions'] = [{'fact': 'quality', 'value': True}]
        context['facts']['quality'] = {'value': True}
        review = search_directions(graph, context)['selection_review']
        self.assertEqual(review['goal']['status'], 'UNKNOWN')

    def test_reported_goal_success_is_not_independent_evidence(self):
        graph, context = fixture()
        context['decision']['goal_conditions'] = [{'fact': 'quality', 'value': True}]
        context['facts']['quality'] = {'value': True, 'source': 'reported.json'}
        review = search_directions(graph, context)['selection_review']
        self.assertEqual(review['goal']['status'], 'TRUE')
        self.assertEqual(review['goal']['assurance'], 'INPUT_REPORTED')
        self.assertNotIn('GOAL_BRIDGE_OPEN', [f['kind'] for f in review['flags']])
        self.assertEqual(review['basis'], 'REVIEW_ONLY')

    def paired(self, predictions):
        graph, context = fixture()
        action = graph['nodes'][0]['executable']['action']
        action['discrimination'] = {'scope_id': 'local-v1', 'source': 'declared-predictions.json', 'predictions': predictions}
        other = deepcopy(graph['nodes'][0]); other['id'] = 'alternative'; other['executable']['action']['id'] = 'alternative'
        graph['nodes'].append(other)
        context['costs'] = {k: {'value': v, 'resource': 'cpu', 'unit': 'seconds',
                                'comparison_group': 'same-attempt', 'source': 'declared-cost.json'} for k, v in (('probe', 1), ('alternative', 2))}
        return graph, context

    def test_supported_same_scope_predictions_and_costs_allow_conditional_comparison(self):
        graph, context = self.paired({'bias': ['positive'], 'state-support': ['negative']})
        result = search_directions(graph, context)
        self.assertEqual(result['selection_review']['basis'], 'CONDITIONAL_COMPARISON')
        self.assertEqual(result['ranking']['pareto_front'], ['route:probe'])
        self.assertEqual(result['selection_review']['assurance'], 'INPUT_REPORTED_NOT_SCIENTIFIC_VERIFICATION')

    def test_shared_pass_fail_predictions_do_not_distinguish_causes(self):
        graph, context = self.paired({'bias': ['positive', 'negative'], 'state-support': ['positive', 'negative']})
        result = search_directions(graph, context)
        self.assertEqual(result['ranking']['dominance'], [])
        self.assertEqual(result['selection_review']['basis'], 'REVIEW_ONLY')
        self.assertTrue(all(r['basis'] == 'NONDISCRIMINATING' for r in result['selection_review']['candidates']))

    def test_local_predictions_do_not_transfer_when_application_premise_fails(self):
        graph, context = self.paired({'bias': ['positive'], 'state-support': ['negative']})
        context['facts']['same_operator'] = {'value': False, 'source': 'actual-operator.json'}
        for node in graph['nodes']:
            node['executable']['action']['discrimination']['conditions'] = [{'fact': 'same_operator', 'value': True}]
        result = search_directions(graph, context)
        self.assertEqual(result['ranking']['dominance'], [])
        self.assertTrue(all(r['basis'] == 'PREDICTION_PREMISES_UNRESOLVED' for r in result['selection_review']['candidates']))

    def test_single_theory_obligation_needs_no_artificial_experiment(self):
        graph, context = fixture()
        action = graph['nodes'][0]['executable']['action']
        action.update(kind='OBLIGATION_CHECK', target='L1', claim='x*x >= 0 for rational x',
                      outcomes=[{'observation': label, 'next_decision': label} for label in ('verified', 'counterexample', 'unresolved')])
        action.pop('competing_explanations')
        review = search_directions(graph, context)['selection_review']
        self.assertEqual(review['basis'], 'SCOPED_OBLIGATION')
        self.assertEqual(review['flags'], [])

    def test_truncated_search_cannot_claim_global_best(self):
        graph, context = self.paired({'bias': ['positive'], 'state-support': ['negative']})
        review = search_directions(graph, context, max_candidates=1)['selection_review']
        self.assertIn('SEARCH_TRUNCATED', [f['kind'] for f in review['flags']])
        self.assertNotEqual(review['basis'], 'CONDITIONAL_COMPARISON')

    def test_goal_predicates_are_nonempty_bounded_and_named(self):
        graph, context = fixture()
        for value in ([], [{}], [{'fact': ''}], [{'fact': 'x'}] * 33, 'free text'):
            with self.subTest(value=value):
                context['decision']['goal_conditions'] = value
                with self.assertRaisesRegex(ValueError, 'decision.goal_conditions'):
                    search_directions(graph, context)

    def test_digest_keeps_selection_warning_and_full_record(self):
        graph, context = fixture()
        search = search_directions(graph, context)
        advice = {'recommendations': [{'search': search}]}
        with tempfile.TemporaryDirectory() as root:
            summary = brief(root, advice, '5.8.0')
            full = json.loads(Path(summary['record']).read_text(encoding='utf-8'))
        self.assertEqual(summary['selection_basis'], 'REVIEW_ONLY')
        self.assertIn('RIVAL_PREDICTIONS_MISSING', summary['flags'])
        self.assertEqual(full, advice)

    def test_oversized_context_has_exact_size_and_actionable_hint_without_mutation(self):
        facts = {'observation': {'value': 1, 'code_sha256': {'source': 'a' * 300}}}
        original = deepcopy(facts)
        with self.assertRaisesRegex(ValueError, r'byte limit \(\d+ > 128\).*manifest digest/source locator'):
            _json(facts, 128)
        self.assertEqual(facts, original)


if __name__ == '__main__':
    unittest.main()
