from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import app
import migrate
import recovery
import workbench as wb

def legacy_database(path):
    path.parent.mkdir()
    fixture = json.loads((wb.ROOT / 'fixtures/synthetic.json').read_text(encoding='utf-8'))
    with closing(sqlite3.connect(path, autocommit=True)) as con:
        con.executescript((wb.ROOT / 'sql/schema-v1.sql').read_text(encoding='utf-8'))
        con.executemany('INSERT INTO work_orders VALUES (?, ?, ?, ?, ?)', fixture['orders'])
        con.executemany('INSERT INTO process_steps VALUES (?, ?, ?)', fixture['steps'])
        con.executemany('INSERT INTO completion_events VALUES (?, ?, ?, ?)', fixture['events'])

class Migration(unittest.TestCase):
    def setUp(self):
        root = wb.ROOT / '.test-tmp'; root.mkdir(exist_ok=True)
        t = tempfile.TemporaryDirectory(prefix='migration-', dir=root); self.addCleanup(t.cleanup)
        self.root = Path(t.name).absolute(); self.data = self.root / 'v1-data'; self.db = self.data / recovery.DB_NAME
        legacy_database(self.db); self.backup = self.root / 'before-upgrade'
        value = wb.save_report(self.db, wb.DEFAULT_START, wb.DEFAULT_END, wb.report(self.db)['dataset_sha256'])
        value['version'] = '0.3.1'
        with closing(wb.connect(self.db)) as con: con.execute('UPDATE report_runs SET payload_json=?', (wb.json_text(value),))

    def digest(self):
        with closing(wb.connect(self.db)) as con: return migrate.table_digest(con, recovery.TABLES_V1)

    def version(self):
        with closing(wb.connect(self.db)) as con: return con.execute('PRAGMA user_version').fetchone()[0]

    def test_upgrade_verifies_backup_and_preserves_all_legacy_values(self):
        before = self.digest(); payload = self.db.read_bytes()
        result = migrate.upgrade(self.data, self.backup)
        self.assertEqual('migrated', result['status']); self.assertEqual(2, self.version())
        self.assertEqual(before, self.digest()); self.assertFalse(result['prior_imports_reconstructed'])
        self.assertEqual(set(recovery.TABLES_V1), set(recovery.verify(self.backup)['database']['tables']))
        with closing(wb.connect(self.db)) as con: self.assertEqual(0, con.execute('SELECT COUNT(*) FROM import_runs').fetchone()[0])
        restored = self.root / 'v1-restored'; recovery.restore(self.backup, restored)
        with closing(wb.connect(restored / recovery.DB_NAME)) as con:
            self.assertEqual(1, con.execute('PRAGMA user_version').fetchone()[0]); self.assertEqual(before, migrate.table_digest(con, recovery.TABLES_V1))
        self.assertTrue(wb.ensure_database(self.db) is False)

    def test_startup_does_not_silently_upgrade_v1(self):
        original = self.db.read_bytes()
        with self.assertRaisesRegex(wb.InputError, 'explicit backed-up upgrade'): wb.ensure_database(self.db)
        self.assertEqual(original, self.db.read_bytes()); self.assertEqual(1, self.version())

    def test_backup_write_failure_prevents_any_schema_change(self):
        original = self.db.read_bytes()
        with patch.object(recovery, 'fresh_write', side_effect=OSError('injected')), self.assertRaises(OSError): migrate.upgrade(self.data, self.backup)
        self.assertEqual(original, self.db.read_bytes()); self.assertEqual(1, self.version())

    def test_failed_verification_prevents_schema_change(self):
        original = self.db.read_bytes()
        with patch.object(recovery, 'verify', side_effect=wb.InputError('injected')), self.assertRaises(wb.InputError): migrate.upgrade(self.data, self.backup)
        self.assertEqual(original, self.db.read_bytes()); self.assertEqual(1, self.version())

    def test_ddl_failure_rolls_back_schema_version_and_original_rows(self):
        original = self.db.read_bytes(); before = self.digest(); original_apply = migrate.apply_schema
        def fail(con): original_apply(con); raise OSError('injected after DDL')
        with patch.object(migrate, 'apply_schema', side_effect=fail), self.assertRaises(OSError): migrate.upgrade(self.data, self.backup)
        self.assertEqual(1, self.version()); self.assertEqual(before, self.digest()); self.assertEqual(original, self.db.read_bytes())
        recovery.verify(self.backup)

    def test_existing_backup_and_live_server_are_refused(self):
        self.backup.mkdir(); (self.backup / 'keep').write_text('fictional')
        with self.assertRaises(wb.InputError): migrate.upgrade(self.data, self.backup)
        self.assertEqual('fictional', (self.backup / 'keep').read_text()); self.assertEqual(1, self.version())
        with app.make_server(self.db):
            with self.assertRaises(wb.InputError): migrate.upgrade(self.data, self.root / 'blocked')
        self.assertFalse((self.root / 'blocked').exists())

    def test_repeated_upgrade_does_not_create_another_backup(self):
        migrate.upgrade(self.data, self.backup); original = self.db.read_bytes()
        with self.assertRaisesRegex(wb.InputError, 'Only schema v1'): migrate.upgrade(self.data, self.root / 'unused')
        self.assertFalse((self.root / 'unused').exists()); self.assertEqual(original, self.db.read_bytes())

    def test_backup_remains_v1_and_current_backup_can_restore_v2(self):
        migrate.upgrade(self.data, self.backup)
        second = self.root / 'v2-backup'; recovery.backup(self.data, second)
        self.assertEqual(5, len(recovery.verify(second)['database']['tables']))
        target = self.root / 'v2-restored'; recovery.restore(second, target); self.assertFalse(wb.ensure_database(target / recovery.DB_NAME))

    def test_changed_source_after_backup_is_not_migrated_or_reverted(self):
        backup = recovery._backup_owned
        def change(source, target):
            result = backup(source, target)
            with closing(wb.connect(self.db)) as con: con.execute("UPDATE work_orders SET quantity=quantity+1 WHERE order_id='WO-1001'")
            return result
        with patch.object(recovery, '_backup_owned', side_effect=change), self.assertRaisesRegex(wb.InputError, 'Data changed after the backup'):
            migrate.upgrade(self.data, self.backup)
        self.assertEqual(1, self.version())
        with closing(wb.connect(self.db)) as current, closing(wb.connect(self.backup / recovery.DB_NAME)) as saved:
            now = current.execute("SELECT quantity FROM work_orders WHERE order_id='WO-1001'").fetchone()[0]
            before = saved.execute("SELECT quantity FROM work_orders WHERE order_id='WO-1001'").fetchone()[0]
            self.assertEqual(before + 1, now)

if __name__ == '__main__': unittest.main()
