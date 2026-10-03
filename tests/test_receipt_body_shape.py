"""A receipt body that is valid JSON but not an object is invalid, not a crash (#102).

All ledgers and maps are synthetic. A corrupted or imported ledger row is data: the shared
read reports it as RECEIPT_BODY_INVALID, every consumer stays fail-closed, and nothing is
inferred from the body or written to the named ledger.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
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
from rds_project import ReceiptIntegrityError, canonical, digest
import test_rds_project  # Module import: its TestCase classes are not collected twice.
from test_rds_capability_requirement import (DEEP_LEARNING, MATHEMATICS, SOFTWARE_TOOL, advisor_review, context,
                                             obstruction, route)

# Valid JSON bodies that are not objects, with the JSON type the status names.
NON_OBJECT = (('[]', 'array'), ('null', 'null'), ('"SUCCEEDED"', 'string'), ('7', 'number'), ('true', 'boolean'))


def writer_body(**fields):
    """The writer's shape for row r1: the body carries the digest of itself without it (#118)."""
    body = {'schema': 1, 'run_id': 'r1', **fields}
    sha = digest(body)
    return sha, json.dumps({**body, 'sha256': sha})


SHA, VALID = writer_body(run_status='SUCCEEDED')


def raw_ledger(root, *bodies, sha=SHA, typed=True):
    """The issue's minimal ledger: receipt rows whose stored bodies are given verbatim, in order.

    ``typed=False`` mimics an imported table without column types, which keeps NULL and numbers as-is.
    """
    (root / '.rds').mkdir(parents=True)
    db = sqlite3.connect(root / '.rds' / 'project.sqlite3')
    db.executescript('CREATE TABLE contract(id INTEGER PRIMARY KEY,sha256 TEXT NOT NULL,body TEXT NOT NULL);'
                     + ('CREATE TABLE receipts(run_id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,body TEXT NOT NULL);'
                        if typed else 'CREATE TABLE receipts(run_id,sha256,body);'))
    db.execute("INSERT INTO contract VALUES (1,'x','{}')")
    for index, body in enumerate(bodies, 1):
        db.execute('INSERT INTO receipts VALUES (?,?,?)', (f'r{index}', sha, body))
    db.commit()
    db.close()
    return root


def ledger_bytes(root):
    """The ledger's bytes and its directory listing: a read leaves no journal or WAL file behind."""
    state = root / '.rds'
    return (hashlib.sha256((state / 'project.sqlite3').read_bytes()).hexdigest(),
            sorted(path.name for path in state.iterdir()))


def one_node_map(project_root, sha=SHA):
    return {'schema': 1, 'goals': ['g'], 'hyperedges': [],
            'nodes': [{'id': 'g', 'status': 'SUPPORTED', 'source': 'synthetic',
                       'evidence': {'receipt': {'project_root': str(project_root), 'sha256': sha}}}]}


def advise_context(setting, ledger_root, sha):
    """One receipt read by both `advise` consumers: the dependency map and an execution-cap obstruction."""
    goal = setting[0]
    ctx = context(*setting)
    ctx['dependency_map'] = {
        'schema': 1, 'goals': [goal],
        'nodes': [{'id': 'run', 'status': 'SUPPORTED', 'source': 'synthetic-run-log.txt',
                   'evidence': {'receipt': {'project_root': str(ledger_root), 'sha256': sha}}},
                  {'id': goal, 'status': 'UNKNOWN', 'source': 'synthetic-goal.json'}],
        'hyperedges': [{'id': 'e1', 'premises': ['run'], 'conclusion': goal, 'status': 'SUPPORTED',
                        'source': 'synthetic-protocol.json'}]}
    ctx['obstructions'] = [obstruction(goal, 'EXECUTION_CAP',
                                       receipt={'project_root': str(ledger_root), 'sha256': sha})]
    ctx['audit_receipts'] = True
    return ctx


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

    def test_object_body_is_still_found_as_text_or_blob(self):
        for label, body in (('text', VALID), ('blob', VALID.encode('utf-8'))):
            with self.subTest(stored=label):
                root = raw_ledger(self.base / ('object-' + label), body)
                found = read_project_receipt(str(root), SHA)
                self.assertEqual((found['status'], found['body']['run_status']), ('RECEIPT_FOUND', 'SUCCEEDED'))

    def test_non_text_column_value_is_invalid(self):
        for value, kind in ((None, 'sqlite null'), (7, 'sqlite integer'), (1.5, 'sqlite real')):
            with self.subTest(value=value):
                root = raw_ledger(self.base / kind.replace(' ', '-'), value, typed=False)
                self.assertEqual(read_project_receipt(str(root), SHA),
                                 {'status': 'RECEIPT_BODY_INVALID', 'reason': kind})

    def test_two_rows_with_one_sha256_are_ambiguous_in_either_order(self):
        for label, rows in (('valid-first', (VALID, '[]')), ('invalid-first', ('[]', VALID)),
                            ('both-valid', (VALID, VALID))):
            with self.subTest(order=label):
                root = raw_ledger(self.base / label, *rows)
                self.assertEqual(read_project_receipt(str(root), SHA), {'status': 'RECEIPT_AMBIGUOUS'})
                self.assertEqual(audit_receipts(one_node_map(root))['grounded_receipts'], [])

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

    def test_untyped_imported_column_and_duplicate_rows_fail_closed(self):
        cases = (('int', raw_ledger(self.base / 'ledger-int', 7, typed=False), 'RECEIPT_BODY_INVALID'),
                 ('null', raw_ledger(self.base / 'ledger-null', None, typed=False), 'RECEIPT_BODY_INVALID'),
                 ('dup', raw_ledger(self.base / 'ledger-dup', '[]', VALID), 'RECEIPT_AMBIGUOUS'))
        for label, ledger_root, status in cases:
            with self.subTest(case=label):
                _, result = self.run_map(ledger_root, 'case-' + label)
                [row] = result['receipt_audit']['audits']
                self.assertEqual(row['status'], status)
                self.assertEqual(result['receipt_blocked_node_ids'], ['g'])
                self.assertEqual(result['declared_supported_closure'], [])

    def test_a_valid_succeeded_body_still_grounds(self):
        ledger_root = raw_ledger(self.base / 'ledger-ok', VALID)
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
        return advise_context(setting, self.ledger, SHA)

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

    def test_a_non_text_column_keeps_the_audit_instead_of_dropping_it(self):
        # A TypeError here used to look like an analyzer without the receipts slice, which re-ran unaudited.
        self.ledger = raw_ledger(Path(self.tmp.name) / 'untyped', 7, typed=False)
        review = advisor_review(self.ctx(DEEP_LEARNING), route(DEEP_LEARNING[0]))['selection_review']
        [row] = review['dependency_review']['receipt_audit']['audits']
        self.assertEqual((row['status'], row['reason']), ('RECEIPT_BODY_INVALID', 'sqlite integer'))
        self.assertIn('run', review['dependency_review']['receipt_blocked_node_ids'])
        self.assertEqual(review['obstruction_review'][0]['receipt_audit']['status'], 'RECEIPT_BODY_INVALID')

    def advise_cli(self, *bodies, sha=SHA):
        with tempfile.TemporaryDirectory() as raw:
            work = Path(raw)
            self.ledger = raw_ledger(work / 'ledger', *bodies, sha=sha)
            ctx = advise_context(DEEP_LEARNING, self.ledger, sha)
            (work / 'context.json').write_text(json.dumps(ctx), encoding='utf-8')
            (work / 'graph.json').write_text(json.dumps(route(DEEP_LEARNING[0])), encoding='utf-8')
            before = ledger_bytes(self.ledger)
            proc = cli(work, 'advise', '--research-context', str(work / 'context.json'),
                       '--graph', str(work / 'graph.json'))
            self.assertNotIn('Traceback', proc.stderr)
            self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
            self.assertEqual(ledger_bytes(self.ledger), before)
        return next(row['search'] for row in json.loads(proc.stdout)['recommendations']
                    if row.get('type') == 'EXECUTABLE_DIRECTION_SEARCH')['selection_review']

    def test_duplicate_receipts_leave_the_obstruction_cause_unknown_in_either_order(self):
        # Row order must not pick the timed-out receipt and turn it into a declared execution cap (#112).
        timed_sha, timed_out = writer_body(run_status='FAILED', timeout=True)
        alone = self.advise_cli(timed_out, sha=timed_sha)['obstruction_review'][0]
        self.assertEqual((alone['receipt_audit']['status'], alone['receipt_audit']['execution_cap']),
                         ('RECEIPT_FOUND', 'TIMEOUT'))
        for index, bodies in enumerate(((timed_out, VALID), (VALID, timed_out))):
            with self.subTest(order=index):
                review = self.advise_cli(*bodies)
                [row] = review['dependency_review']['receipt_audit']['audits']
                self.assertEqual(row['status'], 'RECEIPT_AMBIGUOUS')
                self.assertIn('run', review['dependency_review']['receipt_blocked_node_ids'])
                entry = review['obstruction_review'][0]
                self.assertEqual(entry['receipt_audit'], {'status': 'RECEIPT_AMBIGUOUS'})
                self.assertEqual((entry['response'], entry['cause_status']), ('DISCRIMINATING_CHECK', 'UNKNOWN'))


class OwnedIntegrityTests(unittest.TestCase):
    """#118: a row the owning ProjectStore rejects is not a receipt for any other reader.

    Each case executes one real synthetic run, then rewrites its stored row in this temporary
    ledger only (the writer never produces these rows; an import or corruption can).
    """

    def project(self, mode, forge=None):
        fixture = test_rds_project.ProjectTests('test_execution_policy_is_opt_in_and_frozen')
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        receipt = fixture.run_spec(fixture.spec(mode=mode, timeout=4))
        if forge is not None:
            with fixture.store._db() as db:
                db.execute('DROP TRIGGER receipts_no_update')
                db.execute('UPDATE receipts SET body=? WHERE run_id=?', (forge(receipt), receipt['run_id']))
        return fixture, receipt

    @staticmethod
    def rows(root):
        # closing(): a sqlite3 connection's own context manager commits but stays open (Windows cleanup).
        with closing(sqlite3.connect(root / '.rds' / 'project.sqlite3')) as db:
            return db.execute('SELECT run_id,sha256,body FROM receipts ORDER BY run_id').fetchall()

    def audit_cli(self, root, sha):
        with tempfile.TemporaryDirectory(prefix='rds118 reader ') as raw:
            reader = Path(raw)
            (reader / 'map.json').write_text(json.dumps(one_node_map(root, sha)), encoding='utf-8')
            before = self.rows(root)
            proc = cli(reader, 'hypergraph', '--input', str(reader / 'map.json'), '--audit-receipts', '--json')
            self.assertEqual(self.rows(root), before)  # The named ledger is only read.
            self.assertNotIn('Traceback', proc.stderr)
            self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
            return json.loads(proc.stdout)

    def test_rows_the_owner_rejects_ground_nothing_through_the_real_cli(self):
        cases = (
            ('nonzero', lambda r: canonical(r)[:-1] + ',"run_status":"SUCCEEDED"}', 'repeats a JSON key'),
            ('nonzero', lambda r: canonical({**r, 'run_status': 'SUCCEEDED'}), 'does not match its recorded sha256'),
            ('ok', lambda r: canonical({**r, 'run_id': 'forged-r999'}), 'names a different run'),
            ('ok', lambda r: canonical(r)[:-1] + ',"extra":NaN}',
             'has no canonical encoding (e.g. a non-finite number or an unpaired surrogate)'),
            ('ok', lambda r: canonical(r)[:-1] + ',"extra":"\\ud800"}',
             'has no canonical encoding (e.g. a non-finite number or an unpaired surrogate)'),
            ('ok', lambda r: canonical(r).encode('utf-8')[:-1] + b',"run_id":"forged-r999"}', 'repeats a JSON key'),
        )
        for index, (mode, forge, reason) in enumerate(cases):
            with self.subTest(case=index, reason=reason):
                fixture, receipt = self.project(mode, forge)
                with self.assertRaisesRegex(ReceiptIntegrityError, reason.split(' (')[0]):
                    fixture.store.snapshot()
                result = self.audit_cli(fixture.root, receipt['sha256'])
                [row] = result['receipt_audit']['audits']
                self.assertEqual((row['status'], row.get('reason')), ('RECEIPT_BODY_INVALID', reason))
                self.assertNotIn('run_id', row)  # Nothing is read out of a rejected body.
                self.assertEqual(result['receipt_audit']['grounded_receipts'], [])
                self.assertEqual(result['receipt_blocked_node_ids'], ['g'])
                self.assertEqual(result['declared_supported_closure'], [])
                self.assertNotEqual(result['goals']['g']['status'], 'DECLARED_SUPPORTED')

    def test_writer_receipts_keep_their_status_through_the_real_cli(self):
        for mode, status in (('ok', 'GROUNDED'), ('nonzero', 'RECEIPT_NOT_SUCCEEDED')):
            with self.subTest(mode=mode):
                fixture, receipt = self.project(mode)
                [row] = self.audit_cli(fixture.root, receipt['sha256'])['receipt_audit']['audits']
                self.assertEqual(row['status'], status)
                self.assertEqual(read_project_receipt(str(fixture.root), receipt['sha256'])['body'], receipt)

    def test_an_owner_parse_failure_on_decodable_json_stays_the_overdeep_status(self):
        # Only the owner's object_pairs_hook frame can fail a body the plain decode accepts (recursion
        # limit), so the status must not depend on which of the two decodes reached it first.
        root = raw_ledger(Path(tempfile.mkdtemp(prefix='rds118 depth ')), VALID)
        self.addCleanup(shutil.rmtree, root, True)
        failure = ReceiptIntegrityError('Project receipt integrity failure: run r1 body is not valid JSON; '
                                        'inspect retained state')
        with mock.patch('rds_project.ProjectStore._receipt', side_effect=failure):
            self.assertEqual(read_project_receipt(str(root), SHA),
                             {'status': 'LEDGER_UNAVAILABLE', 'reason': 'RecursionError'})

    def test_a_forged_timeout_is_not_an_execution_cap_in_advise(self):
        fixture, receipt = self.project('ok', lambda r: canonical({**r, 'timeout': True, 'run_status': 'FAILED'}))
        with tempfile.TemporaryDirectory() as raw:
            work = Path(raw)
            ctx = advise_context(DEEP_LEARNING, fixture.root, receipt['sha256'])
            (work / 'context.json').write_text(json.dumps(ctx), encoding='utf-8')
            (work / 'graph.json').write_text(json.dumps(route(DEEP_LEARNING[0])), encoding='utf-8')
            proc = cli(work, 'advise', '--research-context', str(work / 'context.json'),
                       '--graph', str(work / 'graph.json'))
        self.assertNotIn('Traceback', proc.stderr)
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        review = next(row['search'] for row in json.loads(proc.stdout)['recommendations']
                      if row.get('type') == 'EXECUTABLE_DIRECTION_SEARCH')['selection_review']
        invalid = {'status': 'RECEIPT_BODY_INVALID', 'reason': 'does not match its recorded sha256'}
        [row] = review['dependency_review']['receipt_audit']['audits']
        self.assertEqual({key: row.get(key) for key in invalid}, invalid)
        entry = review['obstruction_review'][0]
        self.assertEqual(entry['receipt_audit'], invalid)
        self.assertEqual((entry['response'], entry['cause_status']), ('DISCRIMINATING_CHECK', 'UNKNOWN'))


class GoalLinkGuardTests(unittest.TestCase):
    """`exec` with require_goal_link audits through the same consumer; an invalid receipt blocks the path."""

    @staticmethod
    def guard(ledger_root, sha):
        from rds_advisor_search import _dependency_review, _goal_contribution
        spec = {'schema': 1, 'goals': ['D'],
                'nodes': [{'id': 'B', 'status': 'SUPPORTED', 'source': 'src-B',
                           'evidence': {'receipt': {'project_root': str(ledger_root), 'sha256': sha}}},
                          {'id': 'D', 'status': 'UNKNOWN', 'source': 'src-D'}],
                'hyperedges': [{'id': 'e1', 'premises': ['B'], 'conclusion': 'D', 'status': 'SUPPORTED',
                                'source': 'src-e1'}]}
        context = {'decision': {'goal_conditions': [{'fact': 'D', 'value': True}]}, 'dependency_map': spec}
        action = {'kind': 'OBLIGATION_CHECK', 'target': 'B',
                  'goal_contribution': {'target': 'D', 'path': ['B', 'D'], 'source': 'fixture'}}
        # The exact calls the exec guard makes (rds_quick: audit_receipts=True, audit_files=True).
        dependency = _dependency_review(context, audit_receipts=True, audit_files=True)
        return dependency, _goal_contribution(action, context, dependency)['graph_path']

    def assert_refused(self, dependency, path):
        self.assertEqual(dependency['receipt_audit']['audits'][0]['status'], 'RECEIPT_BODY_INVALID')
        self.assertEqual(path['status'], 'UNKNOWN')
        self.assertEqual(path['blocked_bindings'][0]['token'], 'node:B')

    def test_route_through_an_invalid_receipt_is_refused_with_its_repair_token(self):
        with tempfile.TemporaryDirectory(prefix='rds receipt shape guard ') as raw:
            self.assert_refused(*self.guard(raw_ledger(Path(raw) / 'ledger', '[]'), SHA))

    def test_route_through_a_row_the_owner_rejects_is_refused(self):
        # #118: a FAILED run whose stored row gained a second SUCCEEDED status.
        rows = OwnedIntegrityTests('test_writer_receipts_keep_their_status_through_the_real_cli')
        self.addCleanup(rows.doCleanups)
        fixture, receipt = rows.project('nonzero', lambda r: canonical(r)[:-1] + ',"run_status":"SUCCEEDED"}')
        dependency, path = self.guard(fixture.root, receipt['sha256'])
        self.assert_refused(dependency, path)
        self.assertEqual(dependency['receipt_audit']['audits'][0]['reason'], 'repeats a JSON key')


if __name__ == '__main__':
    unittest.main()
