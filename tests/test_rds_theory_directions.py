"""Theory obligations and empirical comparisons share gates, not evidence claims."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from rds_advisor_search import search_directions
from rds_advisor import RDSAdvisor


def obligation():
    return {'id': 'lemma', 'executable': {'decisions': ['next'], 'preconditions': [],
        'action': {'id': 'check', 'kind': 'OBLIGATION_CHECK', 'target': 'L1',
            'claim': 'For every rational x, x*x >= 0.', 'description': 'Check an exact certificate',
            'methods': {'purpose': 'proof', 'arithmetic': 'exact'},
            'required_observables': ['certificate', 'checker result', 'open premises'],
            'outcomes': [{'observation': label, 'next_decision': decision} for label, decision in (
                ('verified', 'review dependent claim'), ('counterexample', 'revise this claim'),
                ('unresolved', 'inspect the remaining obligation'))]}}}


class TheoryDirectionsTests(unittest.TestCase):
    def search(self, *nodes, **context):
        return search_directions({'nodes': list(nodes), 'edges': []}, {'decision': 'next', **context})

    def test_single_obligation_needs_no_invented_rivals(self):
        result = self.search(obligation())
        self.assertEqual(result['discarded_candidates'], [])
        candidate = result['candidates'][0]
        self.assertEqual(candidate['status'], 'READY')
        self.assertEqual(candidate['competing_explanations'], [])
        self.assertEqual(candidate['evidence_status'], 'INPUT_REPORTED')
        self.assertNotIn('discrimination', candidate)

    def test_theory_and_experiment_coexist_without_false_cross_ranking(self):
        empirical = obligation()
        empirical['id'] = 'experiment'
        action = empirical['executable']['action']
        action.update(kind='PAIRED_TEST', competing_explanations=['mechanism', 'noise'],
            outcomes=[{'observation': 'gain', 'next_decision': 'confirm gain'},
                      {'observation': 'no gain', 'next_decision': 'inspect mechanism'}])
        result = self.search(obligation(), empirical, costs={
            'check': {'value': 1, 'source': 'declared recipe', 'unit': 'seconds', 'comparison_group': 'host'}})
        self.assertEqual({c['id'] for c in result['candidates']}, {'lemma:check', 'experiment:check'})
        self.assertEqual(result['ranking']['dominance'], [])

    def test_scope_and_all_three_outcomes_are_required(self):
        for field in ('claim', 'target'):
            changed = obligation()
            changed['executable']['action'][field] = ''
            self.assertEqual(self.search(changed)['candidates'], [])
        for labels in (['verified', 'counterexample'], ['verified', 'FAIL', 'unresolved'],
                       ['verified', 'verified', 'unresolved']):
            changed = obligation()
            changed['executable']['action']['outcomes'] = [
                {'observation': label, 'next_decision': 'review ' + label} for label in labels]
            self.assertEqual(self.search(changed)['candidates'], [])

    def test_invalid_proof_must_have_an_unresolved_branch(self):
        changed = obligation()
        changed['executable']['action']['outcomes'][2]['observation'] = 'invalid proof'
        report = self.search(changed)
        self.assertIn('unresolved', report['discarded_candidates'][0]['reason'])
        # Actual checker semantics remain external; no process failure infers refutation.
        self.assertEqual(report['candidates'], [])

    def test_unknown_or_false_premises_do_not_enable_obligation_execution(self):
        changed = obligation()
        changed['executable']['preconditions'] = [{'fact': 'complete-domain', 'value': True}]
        report = self.search(changed)
        self.assertEqual(report['candidates'][0]['status'], 'NEEDS_EVIDENCE')
        self.assertEqual(report['queries'][0]['fact'], 'complete-domain')
        report = self.search(changed, facts={'complete-domain': {'value': False, 'source': 'original gap'}})
        self.assertEqual(report['candidates'], [])
        self.assertEqual(report['blocked_candidates'][0]['status'], 'BLOCKED_PREREQUISITE')

    def test_obligation_cannot_claim_empirical_discrimination(self):
        changed = obligation()
        changed['executable']['action']['discrimination'] = {'scope_id': 'invented'}
        report = self.search(changed)
        self.assertEqual(report['candidates'], [])
        self.assertIn('empirical', report['discarded_candidates'][0]['reason'])

    def test_empirical_actions_still_require_competing_explanations(self):
        changed = deepcopy(obligation())
        changed['executable']['action']['kind'] = 'PAIRED_TEST'
        report = self.search(changed)
        self.assertEqual(report['candidates'], [])
        self.assertIn('competing explanations', report['discarded_candidates'][0]['reason'])

    def test_explicit_modes_do_not_receive_unrelated_ml_branch_advice(self):
        with tempfile.TemporaryDirectory() as folder:
            advisor = RDSAdvisor(Path(folder))
            for mode in ('theory', 'empirical', 'mixed'):
                state = {'advisor_context': {'decision': 'next', 'research_mode': mode},
                         'active_branch': 'main', 'branches': {'main': {'stagnation_count': 3}}}
                recommendations = advisor.recommend_next_directions(state, {'nodes': [obligation()]})
                self.assertEqual([r['type'] for r in recommendations], ['EXECUTABLE_DIRECTION_SEARCH'])
                self.assertEqual(recommendations[0]['assurance'], 'HEURISTIC_ONLY')
            state['advisor_context']['research_mode'] = 'unknown-typo'
            with self.assertRaisesRegex(ValueError, 'research_mode'):
                advisor.recommend_next_directions(state, {'nodes': [obligation()]})


if __name__ == '__main__':
    unittest.main()
