import hashlib
import os
from pathlib import Path

from playwright.sync_api import expect
from common import AFTER, BASELINE, BrowserCase, ROOT, runtime_hashes, sha


class WorkflowTest(BrowserCase):
    case_name = "csv-workflow"

    def test_csv_snapshot_and_download_workflow(self):
        with self.recording():
            page = self.page
            self.phase("Fresh database and saved baseline")
            page.goto(self.serve_app())
            expect(page.locator("#total")).to_have_text("9")
            expect(page.locator("#delayed")).to_have_text("4")
            if os.environ.get("WORKFLOOR_BROWSER_PROBE") == "1":
                self.phase("Intentional diagnostic probe")
                self.fail("Intentional failure to verify screenshot and action-trace collection")
            page.get_by_role("button", name="Save snapshot", exact=True).click()
            expect(page.locator("#history-count")).to_have_text("1")
            page.get_by_role("button", name="Open snapshot ↗", exact=True).click()
            expect(page.locator("#view-state")).to_have_text("SAVED SNAPSHOT")
            export = page.get_by_role("button", name="Download current report as JSON", exact=True)
            baseline = self.download_json(export, "baseline.json")
            self.assertEqual(baseline["metrics"], BASELINE)
            self.assertTrue(baseline["validation"]["correct_matches_reference"])
            self.assertEqual(baseline["validation"]["naive_orders"], 26)
            page.get_by_role("button", name="Return to current query ↗", exact=True).click()
            expect(page.locator("#view-state")).to_have_text("CURRENT QUERY")

            def choose(path):
                page.locator("#csv-file").set_input_files(path)
                expect(page.locator("#csv-message")).to_contain_text("File ready.")
                page.get_by_role("checkbox", name="This file contains invented demonstration data.", exact=True).check()
                page.get_by_role("button", name="Preview CSV", exact=True).click()

            self.phase("Invalid CSV is blocked with no source change")
            choose(ROOT / "examples/import-errors.csv")
            expect(page.locator("#csv-summary")).to_have_text("3 records · 0 valid · 3 with issues")
            expect(page.locator("#csv-issues")).to_contain_text("already exists in the database")
            expect(page.get_by_role("button", name="Import all validated rows", exact=True)).to_be_disabled()
            page.get_by_role("button", name="Run report", exact=True).click()
            expect(page.locator("#message")).to_contain_text("Report ready. 9 orders")

            self.phase("UTF-8 BOM/CRLF preview and changed-file invalidation")
            original = ROOT / "examples/import-valid.csv"
            bom_file = self.temp / "bom-valid.csv"
            bom_file.write_bytes(original.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8-sig"))
            choose(bom_file)
            expect(page.locator("#csv-summary")).to_have_text("3 records · 3 valid · 0 with issues")
            expect(page.locator("#csv-fingerprint")).to_contain_text(sha(bom_file)[:16])
            page.locator("#csv-file").set_input_files(original)
            expect(page.locator("#csv-message")).to_contain_text("File ready.")
            expect(page.get_by_role("checkbox", name="This file contains invented demonstration data.", exact=True)).not_to_be_checked()
            expect(page.get_by_role("button", name="Import all validated rows", exact=True)).to_be_disabled()
            page.get_by_role("checkbox", name="This file contains invented demonstration data.", exact=True).check()
            page.get_by_role("button", name="Preview CSV", exact=True).click()
            expect(page.locator("#csv-summary")).to_have_text("3 records · 3 valid · 0 with issues")

            self.phase("Valid import and downloaded receipt bytes")
            page.get_by_role("button", name="Import all validated rows", exact=True).click()
            expect(page.locator("#csv-message")).to_contain_text("Imported 3 new orders and 2 completion events")
            expect(page.locator("#total")).to_have_text("12")
            expect(page.locator("#delayed")).to_have_text("6")
            expect(page.locator("#correct-badge")).to_have_text("PASS")
            receipt = self.download_json(page.get_by_role("button", name="Download last import receipt", exact=True), "receipt.json")
            self.assertEqual(receipt["csv_sha256"], sha(original))
            self.assertEqual(receipt["dataset_sha256_before"], baseline["dataset_sha256"])
            self.assertEqual(receipt["orders_added"], 3)
            self.assertEqual(receipt["completion_events_added"], 2)
            self.assertEqual(receipt["order_ids"], ["DEMO-2001", "DEMO-2002", "DEMO-2003"])
            self.assertEqual(receipt["default_report_metrics"], AFTER)
            self.assertTrue(receipt["default_report_matches_reference"])

            self.phase("Post-import saved export and unchanged earlier export after reload")
            page.get_by_role("button", name="Save snapshot", exact=True).click()
            expect(page.locator("#history-count")).to_have_text("2")
            page.locator("#history .history-row").first.get_by_role("button", name="Open snapshot ↗", exact=True).click()
            expect(page.locator("#view-state")).to_have_text("SAVED SNAPSHOT")
            after = self.download_json(export, "after-import.json")
            self.assertEqual(after["metrics"], AFTER)
            self.assertEqual(after["validation"]["naive_orders"], 29)
            self.assertEqual(after["dataset_sha256"], receipt["dataset_sha256_after"])
            page.reload()
            expect(page.locator("#total")).to_have_text("12")
            page.locator("#history .history-row").filter(has_text=baseline["run_id"][:8]).get_by_role("button", name="Open snapshot ↗", exact=True).click()
            expect(page.locator("#view-state")).to_have_text("SAVED SNAPSHOT")
            expect(page.locator("#total")).to_have_text("9")
            expect(page.locator("#delayed")).to_have_text("4")
            reopened = self.download_json(export, "reopened-baseline.json")
            self.assertEqual(reopened, baseline)
            self.assertEqual((self.run_dir / "baseline.json").read_bytes(), (self.run_dir / "reopened-baseline.json").read_bytes())
            page.get_by_role("button", name="Return to current query ↗", exact=True).click()
            expect(page.locator("#total")).to_have_text("12")
            self.evidence.update(
                receipt_bytes_verified=True, earlier_export_byte_identical=True,
                baseline_metrics=BASELINE, after_import_metrics=AFTER,
                runtime_files=runtime_hashes(), csv_sha256=sha(original),
                exports={name: sha(self.run_dir / name) for name in ("baseline.json", "after-import.json", "receipt.json")},
            )
