from contextlib import closing
from pathlib import Path
import sqlite3

from playwright.sync_api import expect
from common import BrowserCase
import app
import recovery
import workbench as wb

class ImportHistoryWorkflow(BrowserCase):
    case_name = 'persistent-import-history'

    def start(self, database):
        instance = app.make_server(database)
        self.trace_secrets.append(instance.token.encode())
        return instance, self.serve(instance)

    def test_receipt_download_survives_server_restart_and_restore(self):
        with self.recording():
            db = self.temp / 'history data' / recovery.DB_NAME; wb.ensure_database(db)
            original, url = self.start(db); page = self.page; page.goto(url)
            expect(page.locator('#total')).to_have_text('9')
            page.locator('#csv-valid').click(); page.locator('#csv-preview').click()
            expect(page.locator('#csv-summary')).to_have_text('3 records · 3 valid · 0 with issues')
            page.locator('#csv-apply').click()
            expect(page.locator('#total')).to_have_text('12')
            expect(page.locator('#import-history-list .history-row')).to_have_count(1)
            first = self.download_json(page.locator('#csv-download'), 'stored-receipt-original.json')
            self.assertEqual('committed', first['status'])
            page.locator('#import-history-list').get_by_role('button', name='View receipt ↗', exact=True).click()
            expect(page.locator('#import-receipt-dialog')).to_be_visible()
            expect(page.locator('#import-receipt-details')).to_contain_text(first['import_id'])
            page.locator('#close-import-receipt').click()
            original.shutdown(); original.server_close()
            reopened, url = self.start(db); page.goto(url)
            expect(page.locator('#total')).to_have_text('12')
            expect(page.locator('#import-history-list .history-row')).to_have_count(1)
            again = self.download_json(page.locator('#import-history-list').get_by_role('button', name='Download receipt JSON', exact=True), 'stored-receipt-restart.json')
            self.assertEqual(first, again)
            self.assertEqual((self.run_dir / 'stored-receipt-original.json').read_bytes(), (self.run_dir / 'stored-receipt-restart.json').read_bytes())
            reopened.shutdown(); reopened.server_close()
            saved = self.temp / 'receipt backup'; restored = self.temp / 'receipt restored'
            recovery.backup(db.parent, saved); recovery.restore(saved, restored)
            instance, url = self.start(restored / recovery.DB_NAME); page.goto(url)
            expect(page.locator('#total')).to_have_text('12')
            expect(page.locator('#import-history-list .history-row')).to_have_count(1)
            final = self.download_json(page.locator('#import-history-list').get_by_role('button', name='Download receipt JSON', exact=True), 'stored-receipt-restore.json')
            self.assertEqual(first, final)
            self.assertEqual((self.run_dir / 'stored-receipt-original.json').read_bytes(), (self.run_dir / 'stored-receipt-restore.json').read_bytes())
            self.evidence.update(receipt_persists_after_restart=True, receipt_persists_after_restore=True, receipt_download_bytes_identical=True)
