"""A receipt body that is valid JSON but not an object is invalid, not a crash (#102).

All ledgers and maps are synthetic. A corrupted or imported ledger row is data: the shared
read reports it as RECEIPT_BODY_INVALID, every consumer stays fail-closed, and nothing is
inferred from the body or written to the named ledger.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
from rds_hypergraph import audit_receipts, read_project_receipt, receipt_reader
from test_rds_capability_requirement import (DEEP_LEARNING, MATHEMATICS, SOFTWARE_TOOL, advisor_review, context,
                                             obstruction, route)

SHA = 'a' * 64
# Valid JSON bodies that are not objects, with the JSON type the status names.
NON_OBJECT = (('[]', 'array'), ('null', 'null'), ('"SUCCEEDED"', 'string'), ('7', 'number'), ('true', 'boolean'))


def raw_ledger(root, body_text, sha=SHA):
    """The issue's minimal ledger: one receipt row whose stored body text is given verbatim."""
    (root / '.rds').mkdir(parents=True)
    db = sqlite3.connect(root / '.rds' / 'project.sqlite3')
    db.executescript('CREATE TABLE contract(id INTEGER PRIMARY KEY,sha256 TEXT NOT NULL,body TEXT NOT NULL);'
                     'CREATE TABLE receipts(run_id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,body TEXT NOT NULL);')
    db.execute("INSERT INTO contract VALUES (1,'x','{}')")
    db.execute('INSERT INTO receipts VALUES (?,?,?)', ('r1', sha, body_text))
    db.commit()
    db.close()
    return root


def ledger_bytes(root):
    return hashlib.sha256((root / '.rds' / 'project.sqlite3').read_bytes()).hexdigest()


def one_node_map(project_root, sha=SHA):
    return {'schema': 1, 'goals': ['g'], 'hyperedges': [],
            'nodes': [{'id': 'g', 'status': 'SUPPORTED', 'source': 'synthetic',
                       'evidence': {'receipt': {'project_root': str(project_root), 'sha256': sha}}}]}


def cli(root, *args):
    return subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/rds_cli.py'), '--root', str(root), *args],
                          cwd=ROOT, capture_output=True, encoding='utf-8', timeout=60)


class SharedReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='rds receipt shape ')
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_non_object_body_is_invalid_with_its_json_type(self):
        for text, kind in NON_OBJECT:
            with self.subTest(body=text):
                root = raw_ledger(self.base / kind, text)
                self.assertEqual(read_project_receipt(str(root), SHA),
                                 {'status': 'RECEIPT_BODY_INVALID', 'reason': kind})

    def test_object_body_is_still_found(self):
        root = raw_ledger(self.base / 'object', json.dumps({'sha256': SHA, 'run_status': 'SUCCEEDED'}))
        found = read_project_receipt(str(root), SHA)
        self.assertEqual((found['status'], found['body']['run_status']), ('RECEIPT_FOUND', 'SUCCEEDED'))

    def test_malformed_and_overdeep_json_keep_the_existing_unavailable_status(self):
        for text, reason in (('{', 'JSONDecodeError'), ('[' * 200000 + ']' * 200000, 'RecursionError')):
            with self.subTest(reason=reason):
                root = raw_ledger(self.base / reason, text)
                self.assertEqual(read_project_receipt(str(root), SHA),
                                 {'status': 'LEDGER_UNAVAILABLE', 'reason': reason})

    def test_shared_reader_reuses_the_invalid_result(self):
        root = raw_ledger(self.base / 'shared', '[]')
        import rds_hypergraph
        calls, original = [], rds_hypergraph.read_project_receipt

        def counting(root_text, digest_sha):
            calls.append((root_text, digest_sha))
            return original(root_text, digest_sha)

        with mock.patch.object(rds_hypergraph, 'read_project_receipt', counting):
            read = receipt_reader()
            first, second = read(str(root), SHA), read(str(root), SHA)
        self.assertEqual(calls, [(str(root), SHA)])
        self.assertEqual(first, second)
        self.assertEqual(first['status'], 'RECEIPT_BODY_INVALID')

    def test_direct_audit_reports_invalid_and_grounds_nothing(self):
        for text, kind in NON_OBJECT:
            with self.subTest(body=text):
                root = raw_ledger(self.base / ('audit-' + kind), text)
                result = audit_receipts(one_node_map(root))
                self.assertEqual(result['audits'], [{'receipt': {'project_root': str(root), 'sha256': SHA},
                                                     'used_by': ['node:g'], 'status': 'RECEIPT_BODY_INVALID',
                                                     'reason': kind}])
                self.assertEqual(result['grounded_receipts'], [])
                self.assertFalse(result['all_receipts_grounded'])


class HypergraphCLITests(unittest.TestCase):
    """The issue's reproduction through the real `hypergraph --audit-receipts` entry point."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='rds receipt shape cli ')
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_map(self, ledger_root, label):
        reader = self.base / ('reader-' + label)
        reader.mkdir()
        (self.base / (label + '.json')).write_text(json.dumps(one_node_map(ledger_root)), encoding='utf-8')
        before = ledger_bytes(ledger_root)
        proc = cli(reader, 'hypergraph', '--input', str(self.base / (label + '.json')), '--audit-receipts', '--json')
        self.assertEqual(ledger_bytes(ledger_root), before)  # The named ledger is only read.
        self.assertNotIn('Traceback', proc.stderr)
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        return reader, json.loads(proc.stdout)

    def test_non_object_bodies_fail_closed_without_a_traceback(self):
        for text, kind in NON_OBJECT:
            with self.subTest(body=text):
                ledger_root = raw_ledger(self.base / ('ledger-' + kind), text)
                reader, result = self.run_map(ledger_root, kind)
                [row] = result['receipt_audit']['audits']
                self.assertEqual((row['status'], row['reason']), ('RECEIPT_BODY_INVALID', kind))
                self.assertNotIn('run_status', row)  # Nothing is read out of a non-object body.
                self.assertEqual(result['receipt_blocked_node_ids'], ['g'])
                self.assertEqual(result['declared_supported_closure'], [])
                self.assertNotEqual(result['goals']['g']['status'], 'DECLARED_SUPPORTED')
                # The reader's map is saved as a normal revision; re-running from it gives the same audit.
                again = cli(reader, 'hypergraph', '--audit-receipts', '--json')
                self.assertEqual(again.returncode, 0, again.stderr[-800:])
                self.assertEqual(json.loads(again.stdout)['receipt_audit']['audits'], [row])

    def test_malformed_json_body_stays_an_unavailable_ledger(self):
        ledger_root = raw_ledger(self.base / 'ledger-malformed', '{"sha256":')
        _, result = self.run_map(ledger_root, 'malformed')
        [row] = result['receipt_audit']['audits']
        self.assertEqual((row['status'], row['reason']), ('LEDGER_UNAVAILABLE', 'JSONDecodeError'))
        self.assertEqual(result['receipt_blocked_node_ids'], ['g'])

    def test_a_valid_succeeded_body_still_grounds(self):
        ledger_root = raw_ledger(self.base / 'ledger-ok', json.dumps(
            {'schema': 1, 'run_id': 'r1', 'sha256': SHA, 'run_status': 'SUCCEEDED'}))
        _, result = self.run_map(ledger_root, 'ok')
        [row] = result['receipt_audit']['audits']
        self.assertEqual((row['status'], row['run_id']), ('GROUNDED', 'r1'))
        self.assertEqual(result['declared_supported_closure'], ['g'])


class AdviseTests(unittest.TestCase):
    """`advise` reads one receipt for the dependency map and an obstruction; both stay fail-closed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='rds receipt shape advise ')
        self.ledger = raw_ledger(Path(self.tmp.name) / 'ledger', '[]')

    def tearDown(self):
        self.tmp.cleanup()

    def ctx(self, setting):
        goal = setting[0]
        ctx = context(*setting)
        ctx['dependency_map'] = {
            'schema': 1, 'goals': [goal],
            'nodes': [{'id': 'run', 'status': 'SUPPORTED', 'source': 'synthetic-run-log.txt',
                       'evidence': {'receipt': {'project_root': str(self.ledger), 'sha256': SHA}}},
                      {'id': goal, 'status': 'UNKNOWN', 'source': 'synthetic-goal.json'}],
            'hyperedges': [{'id': 'e1', 'premises': ['run'], 'conclusion': goal, 'status': 'SUPPORTED',
                            'source': 'synthetic-protocol.json'}]}
        ctx['obstructions'] = [obstruction(goal, 'EXECUTION_CAP',
                                           receipt={'project_root': str(self.ledger), 'sha256': SHA})]
        ctx['audit_receipts'] = True
        return ctx

    def check(self, review):
        dependency = review['dependency_review']
        self.assertEqual(dependency['status'], 'ANALYZED')
        [row] = dependency['receipt_audit']['audits']
        self.assertEqual((row['status'], row['reason']), ('RECEIPT_BODY_INVALID', 'array'))
        self.assertIn('run', dependency['receipt_blocked_node_ids'])
        entry = review['obstruction_review'][0]
        self.assertEqual(entry['receipt_audit'], {'status': 'RECEIPT_BODY_INVALID', 'reason': 'array'})
        self.assertEqual((entry['response'], entry['cause_status']), ('DISCRIMINATING_CHECK', 'UNKNOWN'))

    def test_real_cli_in_each_domain(self):
        for setting in (DEEP_LEARNING, SOFTWARE_TOOL, MATHEMATICS):
            with self.subTest(goal=setting[0]), tempfile.TemporaryDirectory() as raw:
                work = Path(raw)
                (work / 'context.json').write_text(json.dumps(self.ctx(setting)), encoding='utf-8')
                (work / 'graph.json').write_text(json.dumps(route(setting[0])), encoding='utf-8')
                before = ledger_bytes(self.ledger)
                proc = cli(work, 'advise', '--research-context', str(work / 'context.json'),
                           '--graph', str(work / 'graph.json'))
                self.assertNotIn('Traceback', proc.stderr)
                self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
                self.assertEqual(ledger_bytes(self.ledger), before)
                self.assertFalse((work / '.rds').exists())
                answer = json.loads(proc.stdout)
                self.check(next(row['search'] for row in answer['recommendations']
                                if row.get('type') == 'EXECUTABLE_DIRECTION_SEARCH')['selection_review'])

    def test_one_read_serves_both_consumers(self):
        import rds_hypergraph
        calls, original = [], rds_hypergraph.read_project_receipt

        def counting(root_text, digest_sha):
            calls.append((root_text, digest_sha))
            return original(root_text, digest_sha)

        for templates in (None, []):  # Direct review and the operation-cached dependency path.
            with self.subTest(templates=templates):
                calls.clear()
                ctx = self.ctx(DEEP_LEARNING)
                if templates is not None:
                    ctx['templates'] = templates
                with mock.patch.object(rds_hypergraph, 'read_project_receipt', counting):
                    review = advisor_review(ctx, route(DEEP_LEARNING[0]))['selection_review']
                self.assertEqual(calls, [(str(self.ledger), SHA)])
                self.check(review)


if __name__ == '__main__':
    unittest.main()
