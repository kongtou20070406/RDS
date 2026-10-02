"""Synthetic goal/observation association through the actual Advisor and CLI (#99)."""
import json
from pathlib import Path
import subprocess
import sys
import unittest


class GoalObservationLinkTests(unittest.TestCase):
    def setUp(self):
        from test_rds_progress_policy import ProgressPolicyTests
        self.case = ProgressPolicyTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def graph(self, target='application_gain', ident='probe'):
        graph = self.case.discriminated_graph()
        node = graph['nodes'][0]
        node['id'] = ident
        node['executable']['satisfied_when'] = [{'fact': target, 'value': True}]
        node['executable']['action'].update(id=ident, target=target)
        return graph

    def review(self, graph, context=None):
        before = self.case.store.snapshot()
        result = self.case.search(context or self.case.context(), graph)
        self.assertEqual(self.case.store.snapshot(), before)
        self.assertEqual(result['selection_review']['authorization'], 'UNCHANGED')
        self.assertEqual(result['selection_review']['goal']['status'], 'UNKNOWN')
        return result

    def test_unrelated_observation_keeps_candidate_available_and_goal_gap_open(self):
        for name in ('probe', 'application_gain'):
            with self.subTest(name=name):
                search = self.review(self.graph('unrelated_latency', name))
                self.assertEqual(search['candidates'][0]['status'], 'READY')
                self.assertEqual(search['selection_review']['candidates'][0]['goal_contribution']['status'], 'UNDECLARED')
                self.assertEqual(search['selection_review']['next_move']['kind'], 'RESOLVE_PREMISE')
                self.assertNotIn('resolve application_gain', search['selection_review']['next_move']['reason'])

    def test_direct_theoretical_predicate_is_a_relevant_check(self):
        context = self.case.context()
        context['research_mode'] = 'theory'
        context['decision']['goal_conditions'] = [{'fact': 'proof_obligation', 'value': True}]
        context['facts']['proof_obligation'] = {'value': None, 'source': 'synthetic missing proof'}
        review = self.review(self.graph('proof_obligation'), context)['selection_review']
        self.assertEqual(review['next_move']['kind'], 'DESIGN_DISCRIMINATOR')
        self.assertIn('probe:probe -> proof_obligation', review['next_move']['reason'])

    def test_relevant_and_unrelated_rivals_name_only_the_relevant_check(self):
        graph = self.graph(ident='related')
        graph['nodes'].extend(self.graph('unrelated_latency', 'unrelated')['nodes'])
        search = self.review(graph)
        self.assertEqual({c['status'] for c in search['candidates']}, {'READY'})
        move = search['selection_review']['next_move']
        self.assertEqual(move['kind'], 'DESIGN_DISCRIMINATOR')
        self.assertIn('related:related', move['reason'])
        self.assertNotIn('unrelated:unrelated', move['reason'])

    def test_partial_coverage_names_the_other_open_predicate(self):
        context = self.case.context()
        context['decision']['goal_conditions'].append({'fact': 'proof_obligation', 'value': True})
        search = self.review(self.graph(), context)
        reason = search['selection_review']['next_move']['reason']
        self.assertEqual(search['selection_review']['next_move']['kind'], 'DESIGN_DISCRIMINATOR')
        self.assertIn('Other unresolved predicates remain open: proof_obligation', reason)

    def test_declared_multistep_bridge_is_relevant_without_becoming_proof(self):
        graph = self.graph('lemma')
        action = graph['nodes'][0]['executable']['action']
        action['goal_contribution'] = {'target': 'application_gain',
                                       'path': ['lemma', 'intermediate', 'application_gain'],
                                       'source': 'synthetic declared bridge'}
        for mapped in (False, True):
            with self.subTest(mapped=mapped):
                context = self.case.context()
                if mapped:
                    context['dependency_map'] = {'schema': 1,
                        'nodes': [{'id': n, 'status': 'UNKNOWN', 'source': 'synthetic'}
                                  for n in ('lemma', 'intermediate', 'application_gain')],
                        'hyperedges': [{'id': str(i), 'premises': [left], 'conclusion': right,
                                        'status': 'SUPPORTED', 'source': 'synthetic'}
                                       for i, (left, right) in enumerate(
                                           [('lemma', 'intermediate'), ('intermediate', 'application_gain')])],
                        'goals': ['application_gain']}
                search = self.review(graph, context)
                report = search['selection_review']['candidates'][0]['goal_contribution']
                self.assertEqual(report['status'], 'DECLARED_PATH')
                self.assertEqual(report['assurance'], 'DECLARED_LINK_NOT_SCIENTIFIC_PROOF')
                self.assertEqual(search['selection_review']['next_move']['kind'], 'DESIGN_DISCRIMINATOR')
                self.assertNotIn('predictions resolve', search['selection_review']['next_move']['reason'])

    def test_invalid_declared_bridge_does_not_bypass_association_check(self):
        for path in (['wrong_start', 'application_gain'], ['lemma', 'wrong_end']):
            with self.subTest(path=path):
                graph = self.graph('lemma')
                graph['nodes'][0]['executable']['action']['goal_contribution'] = {
                    'target': 'application_gain', 'path': path, 'source': 'synthetic'}
                self.assertEqual(self.review(graph)['selection_review']['next_move']['kind'], 'RESOLVE_PREMISE')

    def test_unknown_mapped_bridge_is_not_used(self):
        graph = self.graph('lemma')
        graph['nodes'][0]['executable']['action']['goal_contribution'] = {
            'target': 'application_gain', 'path': ['lemma', 'application_gain'], 'source': 'synthetic'}
        context = self.case.context()
        context['dependency_map'] = {'schema': 1,
            'nodes': [{'id': n, 'status': 'UNKNOWN', 'source': 'synthetic'} for n in ('lemma', 'application_gain')],
            'hyperedges': [], 'goals': ['application_gain']}
        self.assertEqual(self.review(graph, context)['selection_review']['next_move']['kind'], 'RESOLVE_PREMISE')

    def test_obstruction_consumer_keeps_relevant_discriminator(self):
        for cause, response in (('MISSING_INPUT', 'EVIDENCE_REPAIR'), ('UNSUPPORTED_OPERATION', 'CAPABILITY_REQUIRED')):
            with self.subTest(cause=cause):
                context = self.case.context()
                context['obstructions'] = [{'id': 'missing', 'obligation': 'application_gain',
                    'cause': cause, 'source': 'synthetic',
                    'requirement': {'input': 'synthetic measurements', 'operation': 'check rivals', 'output': 'rival outcome'}}]
                review = self.review(self.graph(), context)['selection_review']
                self.assertEqual(review['next_move']['kind'], 'DESIGN_DISCRIMINATOR')
                self.assertEqual(review['next_move']['obstructions'][0]['response'], response)

    def test_real_cli_retains_unrelated_ready_route_and_unresolved_goal(self):
        root = self.case.root
        context_path, graph_path = root / 'context.json', root / 'graph.json'
        context_path.write_text(json.dumps(self.case.context()), encoding='utf-8')
        graph_path.write_text(json.dumps(self.graph('unrelated_latency')), encoding='utf-8')
        repo = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, '-B', str(repo / 'scripts/rds_cli.py'), '--root', str(root),
                                 'advise', '--research-context', str(context_path), '--graph', str(graph_path)],
                                cwd=repo, capture_output=True, encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        reports = json.loads(result.stdout)['recommendations']
        search = next(row['search'] for row in reports if row['type'] == 'EXECUTABLE_DIRECTION_SEARCH')
        self.assertEqual(search['candidates'][0]['status'], 'READY')
        self.assertEqual(search['selection_review']['next_move']['kind'], 'RESOLVE_PREMISE')


if __name__ == '__main__':
    unittest.main()
