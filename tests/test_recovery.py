from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import app
import csv_imports
import ownership
import recovery as rec
import workbench as wb

class Recovery(unittest.TestCase):
    def setUp(self):
        root = wb.ROOT / '.test-tmp'; root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='recovery ', dir=root)
        self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name).absolute()
        self.source = self.root / 'source'; self.db = self.source / rec.DB_NAME
        wb.ensure_database(self.db); self.output = self.root / 'backup'; self.restored = self.root / 'restored'

    def test_backup_restore_preserves_all_records_and_snapshot_payload_bytes(self):
        report = wb.report(self.db); saved = wb.save_report(self.db, wb.DEFAULT_START, wb.DEFAULT_END, report['dataset_sha256'])
        text = (wb.ROOT / 'examples/import-valid.csv').read_text(encoding='utf-8'); key = b'fictional-key'
        preview = csv_imports.preview(self.db, text, key)
        csv_imports.apply_import(self.db, text, preview['dataset_sha256'], preview['preview_token'], key)
        with closing(wb.connect(self.db)) as con:
            payload = con.execute('SELECT payload_json FROM report_runs').fetchone()[0]
        original = self.db.read_bytes()
        result = rec.backup(self.source, self.output); self.assertEqual('verified', result['status'])
        self.assertEqual(original, self.db.read_bytes())
        self.assertEqual(15, result['database']['tables']['work_orders'])
        rec.restore(self.output, self.restored); target = self.restored / rec.DB_NAME
        self.assertEqual((self.output / rec.DB_NAME).read_bytes(), target.read_bytes())
        self.assertEqual(wb.report(self.db), wb.report(target))
        self.assertEqual(saved, wb.saved_report(target, saved['run_id']))
        with closing(wb.connect(target)) as con: self.assertEqual(payload, con.execute('SELECT payload_json FROM report_runs').fetchone()[0])

    def test_baseline_can_be_restored_after_import_without_changing_imported_source(self):
        rec.backup(self.source, self.output)
        text = (wb.ROOT / 'examples/import-valid.csv').read_text(encoding='utf-8'); key = b'fictional-key'
        p = csv_imports.preview(self.db, text, key); csv_imports.apply_import(self.db, text, p['dataset_sha256'], p['preview_token'], key)
        imported = self.db.read_bytes(); rec.restore(self.output, self.restored)
        self.assertEqual(9, wb.report(self.restored / rec.DB_NAME)['metrics']['orders'])
        self.assertEqual(12, wb.report(self.db)['metrics']['orders']); self.assertEqual(imported, self.db.read_bytes())

    def test_server_and_second_server_are_refused_until_owner_closes(self):
        with app.make_server(self.db) as server:
            with self.assertRaises(wb.InputError): rec.backup(self.source, self.output)
            with self.assertRaises(wb.InputError): app.make_server(self.db)
            self.assertFalse(self.output.exists())
        self.assertTrue((self.source / ownership.LOCK_NAME).exists())
        rec.backup(self.source, self.output)

    def test_process_exit_releases_ownership_without_deleting_guard(self):
        command = 'from ownership import data_lock; import sys; owner=data_lock(sys.argv[1]); owner.__enter__(); print("ready",flush=True); sys.stdin.read()'
        child = subprocess.Popen([sys.executable, '-B', '-c', command, str(self.source)], cwd=wb.ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual('ready', child.stdout.readline().strip())
            with self.assertRaises(wb.InputError): rec.backup(self.source, self.output)
        finally:
            child.kill(); child.communicate(timeout=5)
            child.stdin.close(); child.stdout.close(); child.stderr.close()
        with ownership.data_lock(self.source): pass
        self.assertTrue((self.source / ownership.LOCK_NAME).is_file())

    def test_existing_destinations_and_nested_backup_are_preserved(self):
        rec.backup(self.source, self.output); original = (self.output / rec.DB_NAME).read_bytes()
        with self.assertRaises(wb.InputError): rec.backup(self.source, self.output)
        self.assertEqual(original, (self.output / rec.DB_NAME).read_bytes())
        with self.assertRaises(wb.InputError): rec.backup(self.source, self.source / 'nested')
        rec.restore(self.output, self.restored); original = (self.restored / rec.DB_NAME).read_bytes()
        with self.assertRaises(wb.InputError): rec.restore(self.output, self.restored)
        self.assertEqual(original, (self.restored / rec.DB_NAME).read_bytes())

    def test_relative_and_missing_parent_paths_are_refused(self):
        with self.assertRaises(wb.InputError): rec.backup(Path('relative'), self.output)
        with self.assertRaises(wb.InputError): rec.backup(self.source, self.root / 'missing' / 'backup')
        self.assertFalse((self.root / 'missing').exists())

    def test_truncated_and_changed_backup_fail_before_restore_directory_creation(self):
        rec.backup(self.source, self.output); member = self.output / rec.DB_NAME
        for content in (b'fictional corruption', member.read_bytes()[:-1]):
            member.write_bytes(content)
            with self.assertRaises(wb.InputError): rec.restore(self.output, self.restored)
            self.assertFalse(self.restored.exists())

    def test_unlisted_and_missing_members_are_refused(self):
        rec.backup(self.source, self.output)
        (self.output / 'extra').write_text('invented')
        with self.assertRaises(wb.InputError): rec.verify(self.output)
        (self.output / 'extra').unlink(); (self.output / 'manifest.json').unlink()
        with self.assertRaises(wb.InputError): rec.verify(self.output)

    def test_manifest_cannot_select_paths_or_duplicate_keys(self):
        rec.backup(self.source, self.output); p = self.output / 'manifest.json'; original = p.read_bytes()
        bad = json.loads(original); bad['database']['name'] = '../other.sqlite3'; p.write_text(json.dumps(bad))
        with self.assertRaises(wb.InputError): rec.verify(self.output)
        p.write_bytes(original.replace(b'"schema": 1,', b'"schema": 1, "schema": 1,'))
        with self.assertRaises(wb.InputError): rec.verify(self.output)

    def test_manifest_types_and_counts_are_validated(self):
        rec.backup(self.source, self.output); p = self.output / 'manifest.json'; original = p.read_bytes()
        for field, value in [('bytes', True), ('sha256', 'x' * 64), ('tables', {'work_orders': 1})]:
            bad = json.loads(original); bad['database'][field] = value; p.write_text(json.dumps(bad))
            with self.subTest(field=field), self.assertRaises(wb.InputError): rec.verify(self.output)

    def test_recomputed_hash_does_not_bypass_schema_or_integrity(self):
        rec.backup(self.source, self.output); db = self.output / rec.DB_NAME
        with closing(sqlite3.connect(db)) as con: con.execute('CREATE TABLE unexpected(value)'); con.commit()
        p = self.output / 'manifest.json'; manifest = json.loads(p.read_text()); raw = db.read_bytes()
        manifest['database'].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()); p.write_text(json.dumps(manifest))
        with self.assertRaises(wb.InputError): rec.verify(self.output)

    def test_foreign_and_changed_schema_are_refused_before_output(self):
        with closing(wb.connect(self.db)) as con: con.execute('PRAGMA application_id=2')
        with self.assertRaises(wb.InputError): rec.backup(self.source, self.output)
        self.assertFalse(self.output.exists())
        with closing(wb.connect(self.db)) as con: con.execute('PRAGMA application_id='+str(wb.APP_ID)); con.execute('DROP INDEX completion_order')
        with self.assertRaises(wb.InputError): rec.backup(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_foreign_key_corruption_is_not_silently_accepted(self):
        with closing(sqlite3.connect(self.db)) as con: con.execute("INSERT INTO process_steps VALUES ('MISSING',1,'fictional')"); con.commit()
        with self.assertRaises(wb.InputError): rec.backup(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_sidecars_and_wal_mode_are_preserved_and_refused(self):
        sidecar = self.db.with_name(self.db.name + '-journal'); sidecar.write_bytes(b'fictional sidecar')
        with self.assertRaises(wb.InputError): rec.backup(self.source, self.output)
        self.assertEqual(b'fictional sidecar', sidecar.read_bytes()); sidecar.unlink()
        with closing(sqlite3.connect(self.db)) as con: con.execute('PRAGMA journal_mode=WAL')
        with self.assertRaises(wb.InputError): rec.backup(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_active_sqlite_transaction_refuses_backup(self):
        with closing(wb.connect(self.db)) as con:
            con.execute('BEGIN IMMEDIATE')
            with self.assertRaises(sqlite3.OperationalError): rec.backup(self.source, self.output)
            con.execute('ROLLBACK')
        self.assertFalse(self.output.exists())

    def test_recomputed_manifest_cannot_hide_wal_marked_backup(self):
        rec.backup(self.source, self.output); db = self.output / rec.DB_NAME
        with closing(sqlite3.connect(db)) as con: con.execute('PRAGMA journal_mode=WAL')
        self.assertEqual(b'\x02\x02', db.read_bytes()[18:20])
        p = self.output / 'manifest.json'; value = json.loads(p.read_text())
        value['database'].update(bytes=db.stat().st_size, sha256=hashlib.sha256(db.read_bytes()).hexdigest())
        p.write_text(json.dumps(value))
        with self.assertRaises(wb.InputError): rec.restore(self.output, self.restored)
        self.assertFalse(self.restored.exists())

    def test_backup_output_failure_preserves_source_and_retains_new_partial_output(self):
        original = self.db.read_bytes(); write = rec.fresh_write
        def fail_manifest(path, content):
            if path.name == 'manifest.json': raise OSError('injected storage failure')
            return write(path, content)
        with patch.object(rec, 'fresh_write', side_effect=fail_manifest), self.assertRaises(OSError): rec.backup(self.source, self.output)
        self.assertEqual(original, self.db.read_bytes()); self.assertTrue((self.output / rec.DB_NAME).is_file())
        with self.assertRaises(wb.InputError): rec.verify(self.output)
        with ownership.data_lock(self.source): pass

    def test_database_size_bound_is_enforced_before_output(self):
        with patch.object(rec, 'MAX_DB', 10), self.assertRaises(wb.InputError): rec.backup(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_hardlinked_database_is_refused_without_changing_links(self):
        link = self.root / 'alias.sqlite3'; os.link(self.db, link)
        original = self.db.read_bytes()
        with self.assertRaises(wb.InputError): rec.backup(self.source, self.output)
        self.assertEqual(original, link.read_bytes())

    def test_symlinked_input_or_output_parent_is_refused(self):
        link = self.root / 'linked'
        try: link.symlink_to(self.source, target_is_directory=True)
        except OSError: self.skipTest('Account cannot create symlinks')
        with self.assertRaises(wb.InputError): rec.backup(link, self.output)
        with self.assertRaises(wb.InputError): rec.backup(self.source, link / 'backup')

if __name__ == '__main__': unittest.main()
