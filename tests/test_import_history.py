from contextlib import closing
import hashlib
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

import csv_imports as imports
import app
import recovery
import workbench as wb

KEY = b'fictional-import-history-key'
VALID = (wb.ROOT / 'examples/import-valid.csv').read_text(encoding='utf-8')

class ImportHistory(unittest.TestCase):
    def setUp(self):
        root = wb.ROOT / '.test-tmp'; root.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix='history-', dir=root)
        self.addCleanup(temporary.cleanup); self.root = Path(temporary.name).absolute()
        self.data = self.root / 'data'; self.db = self.data / recovery.DB_NAME; wb.ensure_database(self.db)

    def apply(self, text=VALID):
        p = imports.preview(self.db, text, KEY)
        return imports.apply_import(self.db, text, p['dataset_sha256'], p['preview_token'], KEY)

    def state(self):
        with closing(wb.connect(self.db)) as con:
            return wb.source_data(con), list(con.execute('SELECT * FROM import_runs'))

    def test_receipt_is_durable_exact_and_matches_committed_rows(self):
        receipt = self.apply(); rows = imports.history(self.db)
        self.assertEqual(1, len(rows)); self.assertEqual('committed', rows[0]['status'])
        raw = imports.receipt_bytes(self.db, receipt['import_id'])
        self.assertEqual((wb.json_text(receipt) + '\n').encode(), raw)
        self.assertEqual(hashlib.sha256(VALID.encode()).hexdigest(), receipt['csv_sha256'])
        with closing(wb.connect(self.db)) as con:
            self.assertEqual(2, con.execute('PRAGMA user_version').fetchone()[0])
            self.assertTrue(set(receipt['order_ids']) <= {r[0] for r in con.execute('SELECT order_id FROM work_orders')})
        self.assertEqual(receipt['dataset_sha256_after'], wb.report(self.db)['dataset_sha256'])
        self.assertEqual(raw, imports.receipt_bytes(self.db, receipt['import_id']))
        self.assertNotIn(b'preview_token', raw); self.assertNotIn(KEY, raw)

    def test_ledger_failure_rolls_back_orders_events_and_receipt(self):
        original = wb.report(self.db)['dataset_sha256']
        with closing(wb.connect(self.db)) as con:
            con.execute("CREATE TRIGGER injected_ledger_failure AFTER INSERT ON import_runs BEGIN SELECT RAISE(ABORT, 'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.apply()
        self.assertEqual(original, wb.report(self.db)['dataset_sha256'])
        self.assertEqual([], imports.history(self.db))

    def test_invalid_stale_and_duplicate_imports_never_add_history(self):
        with self.assertRaises(wb.InputError): self.apply((wb.ROOT / 'examples/import-errors.csv').read_text())
        self.assertEqual([], imports.history(self.db))
        p = imports.preview(self.db, VALID, KEY); self.apply()
        with self.assertRaises(wb.StaleDataError): imports.apply_import(self.db, VALID, p['dataset_sha256'], p['preview_token'], KEY)
        self.assertEqual(1, len(imports.history(self.db)))
        with self.assertRaises(wb.InputError): self.apply()
        self.assertEqual(1, len(imports.history(self.db)))

    def test_backup_restore_preserves_receipt_bytes_and_all_five_tables(self):
        receipt = self.apply(); raw = imports.receipt_bytes(self.db, receipt['import_id'])
        saved = self.root / 'backup'; restored = self.root / 'restored'
        manifest = recovery.backup(self.data, saved)
        self.assertEqual(1, manifest['database']['tables']['import_runs'])
        recovery.restore(saved, restored)
        self.assertEqual(raw, imports.receipt_bytes(restored / recovery.DB_NAME, receipt['import_id']))
        self.assertEqual(imports.history(self.db), imports.history(restored / recovery.DB_NAME))

    def test_receipt_identifier_is_not_a_file_path_or_sql_expression(self):
        for value in ('../manifest.json', "' OR 1=1 --", 'x'*32, None):
            with self.subTest(value=value), self.assertRaises(wb.InputError): imports.receipt_bytes(self.db, value)
        self.assertIsNone(imports.receipt_bytes(self.db, 'a'*32))

    def test_multiple_imports_have_distinct_preserved_receipts(self):
        first = self.apply(); first_bytes = imports.receipt_bytes(self.db, first['import_id'])
        second = self.apply(VALID.replace('DEMO-20', 'DEMO-30'))
        self.assertNotEqual(first['import_id'], second['import_id'])
        self.assertEqual([second['import_id'], first['import_id']], [r['import_id'] for r in imports.history(self.db)])
        self.assertEqual(first_bytes, imports.receipt_bytes(self.db, first['import_id']))

    def test_history_limit_does_not_delete_older_receipts(self):
        receipt = self.apply(); raw = imports.receipt_bytes(self.db, receipt['import_id'])
        with closing(wb.connect(self.db)) as con:
            for n in range(51):
                copy = dict(receipt, import_id=f'{n:032x}', imported_at='2099-01-01T00:00:00Z')
                con.execute('INSERT INTO import_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                            (copy['import_id'], copy['imported_at'], 'committed', copy['csv_sha256'], copy['dataset_sha256_before'], copy['dataset_sha256_after'], 3, 2, wb.json_text(copy)))
        self.assertEqual(50, len(imports.history(self.db)))
        self.assertEqual(raw, imports.receipt_bytes(self.db, receipt['import_id']))

    def test_http_receipt_and_history_survive_server_restart(self):
        receipt = self.apply(); expected = imports.receipt_bytes(self.db, receipt['import_id'])
        for _ in range(2):
            with app.make_server(self.db) as server:
                worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}); worker.start()
                try:
                    connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
                    connection.request('GET', '/api/imports'); response = connection.getresponse()
                    self.assertEqual(200, response.status); self.assertEqual(receipt['import_id'], json.loads(response.read())['imports'][0]['import_id'])
                    connection.request('GET', '/api/imports/' + receipt['import_id'] + '/receipt.json'); response = connection.getresponse()
                    self.assertIn(receipt['import_id'], response.getheader('Content-Disposition')); self.assertEqual(expected, response.read())
                    connection.request('GET', '/api/imports/' + 'a'*32 + '/receipt.json'); response = connection.getresponse()
                    self.assertEqual(404, response.status); response.read()
                    connection.close()
                finally: server.shutdown(); worker.join(timeout=3)

if __name__ == '__main__': unittest.main()
