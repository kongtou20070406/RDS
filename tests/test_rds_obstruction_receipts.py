"""Declared obstructions cross-checked against their project-ledger receipts (#43).

All projects, commands and values are synthetic. Receipts come from real `project execute`
runs; `advise` only reads them. A receipt records execution, never why a goal is blocked:
it can hold a declared cause back, but it never fills in a cause or changes authorization.
"""
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
sys.path.insert(0, str(ROOT / 'examples' / 'project-runner'))
sys.path.insert(0, str(ROOT / 'tests'))
from prepare import prepare
from rds_project import file_sha
from test_rds_capability_requirement import (DEEP_LEARNING, MATHEMATICS, REQUIREMENT, SOFTWARE_TOOL, advisor_review,
                                             context, obstruction, route)


def cli(root, *args, timeout=60):
    return subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/rds_cli.py'), '--root', str(root), *args],
                          cwd=ROOT, capture_output=True, encoding='utf-8', timeout=timeout)


def executed_project(root, sleep_seconds=None):
    """A real project ledger with one finished `control` run; a sleeping command hits timeout_seconds."""
    prepare(root)
    manifest = json.loads((root / 'control.json').read_text(encoding='utf-8'))
    if sleep_seconds is not None:
        (root / 'slow.py').write_text(f'import time\ntime.sleep({sleep_seconds})\n', encoding='utf-8')
        protocol = json.loads((root / 'protocol.json').read_text(encoding='utf-8'))
        protocol['code_sha256'] = file_sha(root / 'slow.py')
        (root / 'protocol.json').write_text(json.dumps(protocol), encoding='utf-8')
        contract = json.loads((root / 'contract.json').read_text(encoding='utf-8'))
        for binding in contract['bindings']:
            if binding['role'] == 'code':
                binding.update(path='slow.py', sha256=file_sha(root / 'slow.py'))
            elif binding['role'] == 'protocol':
                binding['sha256'] = file_sha(root / 'protocol.json')
        argv = [sys.executable, '-B', 'slow.py']
        contract['allowed_commands'] = [argv]
        (root / 'contract.json').write_text(json.dumps(contract), encoding='utf-8')
        manifest['protocol']['sha256'] = file_sha(root / 'protocol.json')
        manifest.update(argv=argv, timeout_seconds=1, resource_estimates={'wall_seconds': 2, 'cpu_seconds': 2})
        (root / 'control.json').write_text(json.dumps(manifest), encoding='utf-8')
    for args in (('init', '--contract', str(root / 'contract.json')),
                 ('create', '--manifest', str(root / 'control.json'))):
        proc = cli(root, 'project', *args)
        assert proc.returncode == 0, proc.stderr
    proc = cli(root, 'project', 'execute', '--id', 'control')
    receipt = json.loads(proc.stdout)
    assert receipt['run_status'] == ('FAILED' if sleep_seconds else 'SUCCEEDED'), proc.stdout[-500:]
    return receipt


class ObstructionReceiptCLITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.capped_root, cls.ok_root = cls.tmp / 'capped project', cls.tmp / 'succeeded'
        cls.capped = executed_project(cls.capped_root, sleep_seconds=5)
        cls.ok = executed_project(cls.ok_root)
        assert cls.capped['timeout'] is True and cls.ok['timeout'] is False

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def ledger_digest(self):
        return {root: hashlib.sha256((root / '.rds' / 'project.sqlite3').read_bytes()).hexdigest()
                for root in (self.capped_root, self.ok_root)}

    def advise(self, ctx, graph, expect=0):
        before = self.ledger_digest()
        with tempfile.TemporaryDirectory() as raw:
            work = Path(raw)
            (work / 'context.json').write_text(json.dumps(ctx), encoding='utf-8')
            (work / 'graph.json').write_text(json.dumps(graph), encoding='utf-8')
            proc = cli(work, 'advise', '--research-context', str(work / 'context.json'),
                       '--graph', str(work / 'graph.json'), timeout=30)
            self.assertEqual(proc.returncode, expect, proc.stderr)
            self.assertFalse((work / '.rds').exists())
        self.assertEqual(self.ledger_digest(), before)  # Reading a receipt never writes a ledger.
        if expect:
            return proc
        answer = json.loads(proc.stdout)
        return next(row['search'] for row in answer['recommendations']
                    if row.get('type') == 'EXECUTABLE_DIRECTION_SEARCH')['selection_review']

    def binding(self, receipt=None, root=None):
        receipt = receipt or self.capped
        return {'project_root': str(root or self.capped_root), 'sha256': receipt['sha256']}

    def review(self, setting, records, audit=True):
        goal, op, value, fact = setting
        ctx = context(goal, op, value, fact)
        ctx['obstructions'] = records
        if audit:
            ctx['audit_receipts'] = True
        return self.advise(ctx, route(goal))

    def baseline(self, setting):
        goal, op, value, fact = setting
        return self.advise(context(goal, op, value, fact), route(goal))

    def test_deep_learning_timed_out_receipt_holds_back_a_declared_capability_gap(self):
        goal = DEEP_LEARNING[0]
        record = obstruction(goal, 'UNSUPPORTED_OPERATION', requirement=REQUIREMENT,
                             signals=['trajectory_degradation'], receipt=self.binding())
        before, review = self.baseline(DEEP_LEARNING), self.review(DEEP_LEARNING, [record])
        entry = review['obstruction_review'][0]
        self.assertEqual((entry['status'], entry['response'], entry['cause_status']),
                         ('APPLICABLE', 'DISCRIMINATING_CHECK', 'UNKNOWN'))
        self.assertNotIn('required_capability', entry)
        self.assertEqual(entry['requirement'], REQUIREMENT)  # The declared contract stays as data for the check.
        self.assertIn('records an execution cap', entry['reason'])
        audit = entry['receipt_audit']
        self.assertEqual({k: audit[k] for k in ('status', 'run_id', 'run_status', 'execution_cap')},
                         {'status': 'RECEIPT_FOUND', 'run_id': 'control', 'run_status': 'FAILED',
                          'execution_cap': 'TIMEOUT'})
        self.assertEqual(audit['assurance'], 'RECEIPT_EXECUTION_NOT_STATEMENT_VERIFICATION')
        self.assertEqual(entry['receipt'], record['receipt'])
        # A timeout is incomplete computation: the move keeps its kind and authorization.
        move = review['next_move']
        self.assertEqual(move['kind'], before['next_move']['kind'])
        self.assertNotIn('supersedes', move)
        self.assertEqual(move['authorization'], before['next_move']['authorization'])

    def test_software_tool_timed_out_receipt_is_consistent_with_a_declared_execution_cap(self):
        goal = SOFTWARE_TOOL[0]
        record = obstruction(goal, 'EXECUTION_CAP', receipt=self.binding())
        entry = self.review(SOFTWARE_TOOL, [record])['obstruction_review'][0]
        self.assertEqual((entry['response'], entry['cause_status']), ('INCOMPLETE_COMPUTATION', 'INPUT_REPORTED'))
        self.assertEqual(entry['receipt_audit']['execution_cap'], 'TIMEOUT')

    def test_mathematics_succeeded_receipt_adds_no_cause(self):
        goal = MATHEMATICS[0]
        record = obstruction(goal, 'UNSUPPORTED_OPERATION', requirement=REQUIREMENT, signals=['proof_bottleneck'],
                             receipt=self.binding(self.ok, self.ok_root))
        plain = dict(record)
        del plain['receipt']
        review, without = self.review(MATHEMATICS, [record]), self.review(MATHEMATICS, [plain])
        entry = review['obstruction_review'][0]
        self.assertEqual(entry['receipt_audit']['status'], 'RECEIPT_FOUND')
        self.assertIsNone(entry['receipt_audit']['execution_cap'])
        self.assertEqual(entry['response'], 'CAPABILITY_REQUIRED')
        self.assertEqual(review['next_move'], without['next_move'])

    def test_unreadable_receipt_fails_closed(self):
        goal = DEEP_LEARNING[0]
        missing = {'project_root': str(self.capped_root), 'sha256': 'a' * 64}
        foreign = self.binding(root=self.ok_root)  # The capped run's sha256 under another project's ledger.
        no_ledger = {'project_root': str(self.tmp / 'not-a-project'), 'sha256': self.capped['sha256']}
        for binding, status in ((missing, 'RECEIPT_NOT_FOUND'), (foreign, 'RECEIPT_NOT_FOUND'),
                                (no_ledger, 'LEDGER_UNAVAILABLE')):
            with self.subTest(status=status, root=binding['project_root']):
                record = obstruction(goal, 'MISSING_INPUT', requirement=REQUIREMENT, receipt=binding)
                entry = self.review(DEEP_LEARNING, [record])['obstruction_review'][0]
                self.assertEqual(entry['receipt_audit']['status'], status)
                self.assertEqual((entry['response'], entry['cause_status']), ('DISCRIMINATING_CHECK', 'UNKNOWN'))

    def test_without_audit_the_receipt_is_data_only(self):
        goal = DEEP_LEARNING[0]
        record = obstruction(goal, 'UNSUPPORTED_OPERATION', requirement=REQUIREMENT,
                             signals=['trajectory_degradation'], receipt=self.binding())
        plain = dict(record)
        del plain['receipt']
        review, without = self.review(DEEP_LEARNING, [record], audit=False), self.review(DEEP_LEARNING, [plain], audit=False)
        entry = review['obstruction_review'][0]
        self.assertEqual(entry['receipt_audit'], {'status': 'NOT_AUDITED'})
        self.assertEqual(entry['response'], 'CAPABILITY_REQUIRED')
        self.assertEqual(review['next_move'], without['next_move'])
        self.assertNotIn('receipt_audit', without['obstruction_review'][0])

    def test_malformed_receipt_binding_is_rejected_with_the_field_name(self):
        goal = DEEP_LEARNING[0]
        for binding in ('control', {'project_root': str(self.capped_root)},
                        {'project_root': str(self.capped_root), 'sha256': 'zz'},
                        {'project_root': ' ', 'sha256': self.capped['sha256']},
                        {**self.binding(), 'run_id': 'control'}):
            with self.subTest(binding=binding):
                ctx = context(*DEEP_LEARNING)
                ctx['obstructions'] = [obstruction(goal, 'EXECUTION_CAP', receipt=binding)]
                proc = self.advise(ctx, route(goal), expect=1)
                self.assertIn('advisor_context.obstructions[0].receipt', proc.stderr)
                self.assertNotIn('Traceback', proc.stderr)


def stopped_ledger(root, stop_reason, sha):
    """A minimal project ledger whose one receipt records a stop policy (shape of a real FAILED receipt)."""
    (root / '.rds').mkdir(parents=True)
    db = sqlite3.connect(root / '.rds' / 'project.sqlite3')
    db.executescript('CREATE TABLE contract(id INTEGER PRIMARY KEY,sha256 TEXT NOT NULL,body TEXT NOT NULL);'
                     'CREATE TABLE receipts(run_id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,body TEXT NOT NULL);')
    body = {'schema': 1, 'run_id': 'r1', 'sha256': sha, 'run_status': 'FAILED', 'timeout': False,
            'stop_reason': stop_reason}
    db.execute("INSERT INTO contract VALUES (1,'x','{}')")
    db.execute('INSERT INTO receipts VALUES (?,?,?)', ('r1', sha, json.dumps(body)))
    db.commit()
    db.close()


class ObstructionReceiptReviewTests(unittest.TestCase):
    SHA = hashlib.sha256(b'synthetic stopped receipt').hexdigest()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'project'
        stopped_ledger(self.root, 'PROGRESS_NO_GROWTH', self.SHA)

    def tearDown(self):
        self.tmp.cleanup()

    def review(self, records, scope='synthetic'):
        goal = DEEP_LEARNING[0]
        ctx = context(*DEEP_LEARNING, scope=scope)
        ctx.update(obstructions=records, audit_receipts=True)
        return advisor_review(ctx, route(goal))['selection_review']

    def capped(self, **extra):
        record = obstruction(DEEP_LEARNING[0], 'EXECUTION_CAP',
                             receipt={'project_root': str(self.root), 'sha256': self.SHA.upper()})
        record.update(extra)
        return record

    def gap(self):
        return obstruction(DEEP_LEARNING[0], 'UNSUPPORTED_OPERATION', requirement=REQUIREMENT,
                           signals=['trajectory_degradation'])

    def test_stop_policy_receipt_is_an_execution_cap_and_holds_back_other_causes(self):
        alone = self.review([self.capped()])['obstruction_review'][0]
        self.assertEqual(alone['receipt_audit']['execution_cap'], 'PROGRESS_NO_GROWTH')
        self.assertEqual(alone['response'], 'INCOMPLETE_COMPUTATION')
        entries = self.review([self.capped(), self.gap()])['obstruction_review']
        # The existing co-declared rule still holds both back; the receipt adds no precedence for its own cause.
        self.assertEqual(entries[0]['response'], 'DISCRIMINATING_CHECK')
        self.assertEqual(entries[0]['reason'], 'Co-declared UNSUPPORTED_OPERATION on this obligation must be resolved '
                                               'or ruled out before this cause is treated as established.')
        held = entries[1]
        self.assertEqual((held['response'], held['cause_status']), ('DISCRIMINATING_CHECK', 'UNKNOWN'))
        # Both the co-declared cause and the receipt are named; neither reason replaces the other.
        self.assertIn('Co-declared EXECUTION_CAP', held['reason'])
        self.assertIn('records an execution cap', held['reason'])

    def test_a_cap_receipt_from_another_scope_does_not_block_a_healthy_route(self):
        alone = self.review([self.gap()])
        scoped_out = self.review([self.capped(scope={'domain': 'elsewhere'}), self.gap()])
        self.assertEqual(scoped_out['obstruction_review'][0]['status'], 'NOT_APPLICABLE')
        self.assertEqual(scoped_out['obstruction_review'][1]['response'], 'CAPABILITY_REQUIRED')
        self.assertEqual(scoped_out['next_move']['kind'], alone['next_move']['kind'])

    def test_existing_reasons_keep_precedence_over_the_receipt(self):
        record = self.capped(cause='UNSUPPORTED_OPERATION')  # No requirement: the existing reason comes first.
        entry = self.review([record])['obstruction_review'][0]
        self.assertEqual(entry['response'], 'DISCRIMINATING_CHECK')
        self.assertTrue(entry['reason'].startswith('An unsupported operation needs requirement'))
        missing = self.capped(receipt={'project_root': str(self.root), 'sha256': 'b' * 64})
        del missing['source']
        entry = self.review([missing])['obstruction_review'][0]
        self.assertEqual(entry['receipt_audit']['status'], 'RECEIPT_NOT_FOUND')
        self.assertEqual(entry['reason'], 'No source locator was declared for this obstruction.')

    def test_each_distinct_receipt_is_read_once(self):
        import rds_hypergraph
        calls = []
        original = rds_hypergraph.read_project_receipt

        def counting(root_text, digest_sha):
            calls.append((root_text, digest_sha))
            return original(root_text, digest_sha)

        records = [dict(self.capped(), id=f'o{i}') for i in range(3)]
        with mock.patch.object(rds_hypergraph, 'read_project_receipt', counting):
            entries = self.review(records)['obstruction_review']
        self.assertEqual(calls, [(str(self.root), self.SHA)])
        self.assertTrue(all(e['receipt_audit']['status'] == 'RECEIPT_FOUND' for e in entries))


if __name__ == '__main__':
    unittest.main()
