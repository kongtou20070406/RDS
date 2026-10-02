"""Agent entry, program-owned snapshots, evidence boundaries and non-monotonic updates."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from rds_advisor_search import _dependency_review
from rds_hypergraph import analyze_hypergraph, cascade_refute, review_hypergraph
from rds_hypergraph_input import load_input


def small_input():
    return {'claims': {'a': {'state': ' supported ', 'source': 'synthetic-observation.json'}},
            'rules': [{'from': 'a', 'to': 'g', 'state': 'supported', 'source': 'synthetic-rule.json'}],
            'goal': 'g'}


class TMSBehaviorTests(unittest.TestCase):
    def test_existing_canonical_metadata_and_analysis_are_preserved(self):
        spec = review_hypergraph(small_input())['dependency_map']
        spec['nodes'][0]['name'] = 'a human description, not another ID'
        spec['nodes'][0]['state'] = {'arbitrary': 'source metadata'}
        original = deepcopy(spec)
        result = review_hypergraph(spec)
        self.assertEqual(result['dependency_map'], original)
        self.assertEqual(result['input_review']['repairs'], [])
        for key, value in analyze_hypergraph(spec).items():
            self.assertEqual(result[key], value)

    def test_program_constructs_table_and_next_consumer_uses_snapshot(self):
        value = small_input()
        original = deepcopy(value)
        result = review_hypergraph(value)
        self.assertEqual(value, original)
        self.assertEqual(result['declared_supported_closure'], ['a', 'g'])
        self.assertEqual(result['goals']['g']['status'], 'DECLARED_SUPPORTED')
        canonical = result['dependency_map']
        self.assertEqual(len(canonical['nodes']), 2)
        self.assertEqual(canonical['nodes'][1]['status'], 'UNKNOWN')
        self.assertTrue(canonical['hyperedges'][0]['id'])
        self.assertNotIn('state', canonical['hyperedges'][0])
        second = review_hypergraph(result)
        self.assertEqual(second['dependency_map'], canonical)
        advisor = _dependency_review({'dependency_map': result})
        self.assertEqual(advisor['declared_supported_closure'], ['a', 'g'])
        self.assertEqual(advisor['authorization'], 'UNCHANGED')

    def test_missing_source_and_unrecognized_status_cannot_create_support(self):
        for status in ('SUPPORTED', True, 'QUALIFIED'):
            with self.subTest(status=status):
                result = review_hypergraph({'claims': {'a': status}, 'goal': 'a'})
                self.assertEqual(result['status'], 'ANALYZED')
                self.assertEqual(result['declared_supported_closure'], [])
                self.assertEqual(result['goals']['a']['status'], 'UNKNOWN')
                self.assertTrue(result['input_review']['warnings'])
        result = review_hypergraph({'claims': {'a': {'status': 'SUPPORTED', 'source': 'observation'}},
                                   'rules': [{'from': 'a', 'to': 'g', 'status': 'SUPPORTED'}], 'goal': 'g'})
        self.assertEqual(result['declared_supported_closure'], ['a'])
        self.assertEqual(result['dependency_map']['hyperedges'][0]['status'], 'PROPOSED')
        self.assertNotIn('mastery_status', result)

    def test_partial_declarations_remain_researchable_across_domains(self):
        for name in ('held-out measurement', 'recovery invariant', 'finite proposition'):
            with self.subTest(name=name):
                result = review_hypergraph({'rules': [{'from': 'missing input', 'to': name}], 'goal': name})
                self.assertEqual(result['status'], 'ANALYZED')
                self.assertEqual(result['declared_supported_closure'], [])
                self.assertEqual(result['goals'][name]['status'], 'UNKNOWN')
                self.assertTrue(result['goals'][name]['minimal_missing_evidence_sets'])
                self.assertEqual(result['authorization'], 'UNCHANGED')

    def test_ambiguities_are_batched_and_changes_are_atomic(self):
        value = {'nodes': [{'id': 'a', 'status': 'SUPPORTED', 'state': 'UNKNOWN', 'source': 'x'},
                           {'id': 'a', 'source': 'y'}],
                 'rules': [{'to': 'g'}, {'from': 'a'}], 'goals': ['g']}
        original = deepcopy(value)
        result = review_hypergraph(value, refute_nodes=['a'])
        self.assertEqual(result['status'], 'UNKNOWN')
        self.assertGreaterEqual(len(result['input_review']['errors']), 4)
        self.assertNotIn('revision', result)
        self.assertEqual(value, original)
        unknown = review_hypergraph(small_input(), refute_nodes=['a', 'missing'], refute_rules=['missing-rule'])
        self.assertEqual(len(unknown['input_review']['errors']), 2)
        self.assertEqual(unknown['dependency_map']['nodes'][0]['status'], 'SUPPORTED')

    def test_retraction_updates_ordinary_goals_and_advisor_without_mutating_input(self):
        first = review_hypergraph(small_input())
        original = deepcopy(first)
        result = review_hypergraph(first, retract_nodes=['a'], change_source='new-observation.json', trace='g')
        self.assertEqual(result['declared_supported_closure'], [])
        self.assertEqual(result['goals']['g']['status'], 'UNKNOWN')
        self.assertEqual(result['goals']['g']['minimal_missing_evidence_sets'], [['node:a']])
        self.assertEqual(result['revision']['lost_support'], ['a', 'g'])
        self.assertFalse(result['support_cone']['supported'])
        self.assertNotIn('tms_cascade_revocation', result)
        self.assertEqual(first, original)
        expected = analyze_hypergraph(result['dependency_map'])
        for key, value in expected.items():
            self.assertEqual(result[key], value, key)
        advisor = _dependency_review({'dependency_map': result})
        self.assertEqual(advisor['goals']['g']['status'], 'UNKNOWN')
        self.assertEqual(advisor['declared_supported_closure'], [])
        # Restoring a previous immutable snapshot recovers its route without hand edits.
        self.assertEqual(review_hypergraph(first)['declared_supported_closure'], ['a', 'g'])

    def test_independent_alternative_is_kept_and_selected_witness_changes(self):
        value = small_input()
        value['claims']['b'] = {'status': 'SUPPORTED', 'source': 'independent-observation'}
        value['rules'].append({'from': 'b', 'to': 'g', 'status': 'SUPPORTED', 'source': 'independent-rule'})
        first = review_hypergraph(value)
        result = cascade_refute(first, contradicted_node_ids=['a'])
        self.assertEqual(result['declared_supported_closure'], ['b', 'g'])
        self.assertEqual(result['goals']['g']['status'], 'DECLARED_SUPPORTED')
        self.assertEqual(result['revision']['lost_support'], ['a'])
        self.assertIn('g', result['revision']['alternative_derivations'])
        self.assertEqual(result['dependency_map']['nodes'][0]['status'], 'CONTRADICTED')

    def test_cycle_loses_its_seed_and_does_not_support_itself(self):
        value = small_input()
        value['rules'].append({'from': 'g', 'to': 'a', 'status': 'SUPPORTED', 'source': 'back-edge'})
        first = review_hypergraph(value, trace='g')
        self.assertEqual(first['support_cone']['support_cone_nodes'], ['a', 'g'])
        result = review_hypergraph(first, retract_nodes=['a'])
        self.assertEqual(result['declared_supported_closure'], [])
        self.assertEqual(result['goals']['g']['status'], 'UNRESOLVED')
        self.assertEqual(result['goals']['g']['minimal_missing_evidence_sets'], [])

    def test_rule_retraction_and_refutation_have_distinct_dependency_effects(self):
        first = review_hypergraph(small_input())
        rule = first['dependency_map']['hyperedges'][0]['id']
        retracted = review_hypergraph(first, retract_rules=[rule])
        self.assertEqual(retracted['goals']['g']['minimal_missing_evidence_sets'], [['rule:' + rule]])
        refuted = review_hypergraph(first, refute_rules=[rule])
        self.assertEqual(refuted['goals']['g']['status'], 'UNRESOLVED')
        self.assertEqual(first['goals']['g']['status'], 'DECLARED_SUPPORTED')

    def test_repairs_do_not_change_receipt_bindings_or_admission_authority(self):
        value = small_input()
        binding = {'receipt_sha256': 'a' * 64, 'run_id': 'not-a-verified-receipt'}
        value['claims']['a']['evidence'] = binding
        result = _dependency_review({'dependency_map': value})
        node = next(row for row in result['reported_nodes'] if row['id'] == 'a')
        self.assertEqual(node['evidence'], binding)
        self.assertIn('a', result['receipt_blocked_node_ids'])
        self.assertEqual(result['authorization'], 'UNCHANGED')


class TMSInputAndEntryTests(unittest.TestCase):
    def test_safe_format_repairs_preserve_strings_and_reject_duplicate_keys(self):
        value, repairs = load_input('```json\n{"claims": ["comma, } and quote \\\""], "goal": "g",}\n```')
        self.assertEqual(value['claims'], ['comma, } and quote "'])
        self.assertEqual(len(repairs), 2)
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
            load_input('{"goal":"a", "goal":"b"}')
        with self.assertRaisesRegex(ValueError, 'Non-finite'):
            load_input('{"nodes":[], "value":NaN}')
        with self.assertRaisesRegex(ValueError, 'Non-finite'):
            load_input('{"nodes":[], "value":1e309}')

    def test_real_cli_reuses_saved_snapshots_for_negative_and_restored_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'small.json'
            path.write_text('```json\n' + json.dumps(small_input())[:-1] + ',}\n```', encoding='utf-8')

            def cli(source, *extra):
                return subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/rds_cli.py'),
                    '--root', str(root), 'hypergraph', '--input', str(source), *extra],
                    capture_output=True, text=True, encoding='utf-8', timeout=15,
                    env={**os.environ, 'RDS_USAGE_DB': str(root / 'usage.sqlite3')})

            first = cli(path)
            self.assertEqual(first.returncode, 0, first.stderr)
            brief = json.loads(first.stdout)
            snapshot = Path(brief['record'])
            original_bytes = snapshot.read_bytes()
            self.assertEqual(brief['goals'], {'g': 'DECLARED_SUPPORTED'})
            self.assertNotIn('dependency_map', brief)
            self.assertNotIn('reported_nodes', brief)
            second = cli(snapshot, '--retract-node', 'a')
            self.assertEqual(second.returncode, 0, second.stderr)
            digest = json.loads(second.stdout)
            result = json.loads(Path(digest['record']).read_text(encoding='utf-8'))
            self.assertEqual(digest['goals'], {'g': 'UNKNOWN'})
            self.assertEqual(result['declared_supported_closure'], [])
            self.assertEqual(result['next_step']['tokens'], ['node:a'])
            self.assertEqual(snapshot.read_bytes(), original_bytes)
            restored = cli(snapshot)
            self.assertEqual(restored.returncode, 0, restored.stderr)
            self.assertEqual(json.loads(restored.stdout)['goals'], {'g': 'DECLARED_SUPPORTED'})
            malformed = cli(snapshot, '--refute-node', 'missing', '--refute-rule', 'missing-rule')
            self.assertEqual(malformed.returncode, 2, malformed.stderr)
            self.assertEqual(json.loads(malformed.stdout)['input_issues'], 2)
            self.assertEqual(snapshot.read_bytes(), original_bytes)

    def test_real_cli_treats_imported_code_as_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, sentinel = root / 'input.json', root / 'executed'
            value = small_input()
            value['code'] = 'from pathlib import Path; Path(' + repr(str(sentinel)) + ').write_text("executed")'
            path.write_text(json.dumps(value), encoding='utf-8')
            run = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/rds_cli.py'), '--root', str(root),
                'hypergraph', '-i', str(path), '--json'], capture_output=True, text=True, encoding='utf-8',
                timeout=15, env={**os.environ, 'RDS_USAGE_DB': str(root / 'usage.sqlite3')})
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertFalse(sentinel.exists())
            self.assertEqual(json.loads(run.stdout)['assurance'], 'INPUT_REPORTED_DEPENDENCY_ANALYSIS_NOT_PROOF')


if __name__ == '__main__':
    unittest.main()
