"""Locked publication identity and stale-revision boundaries, with real SQLite/CAS."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from rds_project import ProjectStore, canonical
from rds_tms_store import SnapshotConflict, current, save


class TMSPublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='rds-tms-publication-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.initial = {'schema': 1, 'nodes': [], 'hyperedges': [], 'goals': []}
        self.target = {**self.initial, 'nodes': [
            {'id': 'reserved', 'status': 'UNKNOWN', 'source': 'synthetic-owned-state'}]}
        self.base = save(self.root, self.initial, expected=None)

    def count(self):
        with ProjectStore(self.root)._db(True) as db:
            return db.execute('SELECT COUNT(*) FROM dependency_snapshots').fetchone()[0]

    def test_locked_duplicate_reuses_one_publication_without_appending(self):
        published = save(self.root, self.target, expected=self.base)
        checked = []

        def validate(db):
            # The callback receives the actual publication transaction.
            self.assertTrue(db.in_transaction)
            checked.append(db.execute('SELECT COUNT(*) FROM dependency_snapshots').fetchone()[0])

        self.assertEqual(save(self.root, self.target, expected=self.base,
                              validate_current=validate), published)
        self.assertEqual(checked, [2])
        self.assertEqual(self.count(), 2)
        self.assertEqual(current(self.root)['sha256'], published)

    def test_stale_publications_cannot_cross_revision_source_or_content_changes(self):
        for variant in ('generic', 'new-declaration', 'incoming-revision', 'source-base', 'different-map', 'aba'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                base = save(root, self.initial, expected=None)
                revision = {'changes': [{'kind': 'node', 'id': 'reserved', 'operation': 'declare',
                                         'status': 'UNKNOWN', 'source': 'new-declaration'}]}
                published = save(root, self.target, expected=base,
                                 revision=revision if variant == 'new-declaration' else None)
                if variant == 'aba':
                    middle = save(root, self.initial, expected=published)
                    published = save(root, self.target, expected=middle)
                spec = deepcopy(self.target)
                if variant == 'different-map':
                    spec['nodes'][0]['source'] = 'different-observation'
                before = current(root)
                with self.assertRaises(SnapshotConflict):
                    save(root, spec, expected=base,
                         revision=revision if variant == 'incoming-revision' else None,
                         source_base=root / 'other' if variant == 'source-base' else root,
                         validate_current=None if variant == 'generic' else lambda db: None)
                self.assertEqual(current(root), before)

    def test_same_map_cannot_skip_locked_ledger_revalidation(self):
        published = save(self.root, self.target, expected=self.base)

        def changed_ledger(db):
            raise ValueError('Owned state changed during evidence collection')

        with self.assertRaisesRegex(ValueError, 'Owned state changed'):
            save(self.root, self.target, expected=self.base, validate_current=changed_ledger)
        self.assertEqual(current(self.root)['sha256'], published)
        self.assertEqual(self.count(), 2)

    def test_duplicate_rejects_corrupt_current_body_or_cas(self):
        for corruption in ('body', 'cas'):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                base = save(root, self.initial, expected=None)
                save(root, self.target, expected=base)
                saved = current(root)
                if corruption == 'body':
                    body = {k: saved[k] for k in ('parent', 'map', 'source_base_dir', 'revision')}
                    with ProjectStore(root)._db() as db:
                        db.execute('INSERT INTO dependency_snapshots VALUES (?,?)', ('0' * 64, canonical(body)))
                else:
                    (root / saved['map']['path']).write_bytes(b'corrupt synthetic CAS')
                with self.assertRaisesRegex(ValueError, 'integrity'):
                    save(root, self.target, expected=base, validate_current=lambda db: None)


if __name__ == '__main__':
    unittest.main()
