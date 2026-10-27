import json
from playwright.sync_api import expect
from common import BrowserCase, ROOT, sha


class DemoTest(BrowserCase):
    case_name = "readonly-demo"

    def test_readonly_viewer_and_export_provenance(self):
        with self.recording():
            self.phase("Frozen export hashes and receipt provenance")
            data = ROOT / "demo" / "data"
            provenance = json.loads((data / "provenance.json").read_text(encoding="utf-8"))
            for name, expected in provenance["files"].items():
                self.assertEqual(sha(data / name), expected)
            self.assertEqual(sha(ROOT / "examples/import-valid.csv"), provenance["csv_sha256"])

            self.phase("Baseline, delayed filter and source inspector")
            page = self.page
            page.goto(self.serve_demo())
            expect(page.locator("#total")).to_have_text("9")
            page.get_by_label("Show", exact=True).select_option("delayed")
            expect(page.locator("#row-count")).to_contain_text("4 of 9")
            page.get_by_role("button", name="WO-1002", exact=True).click()
            expect(page.get_by_role("dialog")).to_be_visible()
            expect(page.locator("#order-events tr")).to_have_count(2)
            expect(page.locator("#order-state")).to_contain_text("replay")
            page.get_by_role("button", name="Close order details ×", exact=True).click()

            self.phase("After-import report, recorded SQL and comparison")
            page.get_by_label("Report sample", exact=True).select_option("after-import")
            expect(page.locator("#total")).to_have_text("12")
            expect(page.locator("#delayed")).to_have_text("6")
            expect(page.locator("#row-count")).to_contain_text("6 of 12")
            expect(page.locator("#naive-count")).to_have_text("29")
            page.get_by_role("tab", name="Correct aggregation", exact=True).press("ArrowRight")
            expect(page.get_by_role("tab", name="Naïve join · wrong", exact=True)).to_have_attribute("aria-selected", "true")
            expect(page.locator("#sql")).to_contain_text("INTENTIONALLY INCORRECT")
            expect(page.locator("#comparison-policy")).to_contain_text("same UTC date range")
            expect(page.locator("#added-orders li")).to_have_count(3)
            expect(page.locator("#comparison-rows tr").last).to_contain_text("9")

            self.phase("Selected export download, phone layout and read-only controls")
            selected = self.download_json(page.get_by_role("link", name="Download selected report ↓", exact=True), "selected-export.json")
            self.assertEqual(selected, json.loads((data / "after-import.json").read_text(encoding="utf-8")))
            self.assertEqual(page.locator('input[type="file"]').count(), 0)
            self.assertEqual(page.get_by_role("button", name="Save snapshot", exact=True).count(), 0)
            page.set_viewport_size({"width": 390, "height": 844})
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth === document.documentElement.clientWidth"))
            page.set_viewport_size({"width": 320, "height": 844})
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth === document.documentElement.clientWidth"))
            self.evidence.update(export_hashes_verified=True, selected_download_verified=True,
                                 delayed_baseline=4, delayed_after_import=6, responsive_widths=[390, 320])
