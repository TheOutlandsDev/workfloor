from contextlib import closing
import csv
import hashlib
import http.client
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

import app
import csv_imports as imports
import workbench as wb

KEY = b"test-only-preview-signing-key"
VALID = (wb.ROOT / "examples/import-valid.csv").read_text(encoding="utf-8")
ERRORS = (wb.ROOT / "examples/import-errors.csv").read_text(encoding="utf-8")


def csv_file(rows, header=imports.COLUMNS):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(header)
    writer.writerows(rows)
    return output.getvalue()


class ImportBase(unittest.TestCase):
    def setUp(self):
        root = (wb.ROOT / ".test-tmp").resolve()
        root.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="csv-", dir=root)
        if Path(temporary.name).resolve().parent != root:
            raise RuntimeError("Temporary directory escaped its intended root")
        self.addCleanup(temporary.cleanup)
        self.db = Path(temporary.name) / "workfloor.sqlite3"
        wb.ensure_database(self.db)

    def state(self):
        with closing(wb.connect(self.db)) as con:
            return {"source": wb.source_data(con),
                    "snapshots": [dict(row) for row in con.execute("SELECT * FROM report_runs ORDER BY run_id")]}

    def apply(self, text=VALID, checked=None, key=KEY):
        checked = checked or imports.preview(self.db, text, key)
        return imports.apply_import(self.db, text, checked["dataset_sha256"], checked["preview_token"], key)


class CSVImportCase(ImportBase):
    def test_preview_is_read_only_and_checks_every_row(self):
        before = self.db.read_bytes()
        checked = imports.preview(self.db, VALID, KEY)
        self.assertEqual((checked["total_rows"], checked["valid_rows"], checked["invalid_rows"]), (3, 3, 0))
        self.assertTrue(checked["can_import"])
        self.assertEqual(len(checked["rows"]), 3)
        self.assertEqual(checked["dataset_sha256"], wb.report(self.db)["dataset_sha256"])
        self.assertEqual(self.db.read_bytes(), before)

    def test_apply_adds_expected_orders_and_preserves_original_source(self):
        before = self.state()["source"]
        receipt = self.apply()
        current = self.state()["source"]
        original_ids = {row["order_id"] for row in before["orders"]}
        self.assertEqual([row for row in current["orders"] if row["order_id"] in original_ids], before["orders"])
        self.assertEqual(current["steps"], before["steps"])
        self.assertEqual([row for row in current["events"] if row["order_id"] in original_ids], before["events"])
        self.assertEqual((receipt["orders_added"], receipt["completion_events_added"]), (3, 2))
        report = wb.report(self.db)
        self.assertEqual(report["metrics"], {"orders": 12, "units": 440, "delayed": 6,
                         "completed_late": 2, "open_overdue": 4, "on_time": 4, "review": 2})
        self.assertEqual(report["validation"]["naive_orders"], 29)
        self.assertEqual(report["validation"]["naive_units"], 1270)
        self.assertTrue(report["validation"]["correct_matches_reference"])
        self.assertEqual(report["dataset_orders"], 15)
        self.assertEqual(receipt["dataset_sha256_after"], report["dataset_sha256"])

    def test_legacy_snapshot_and_database_format_survive_import(self):
        saved = wb.save_report(self.db, wb.DEFAULT_START, wb.DEFAULT_END, wb.report(self.db)["dataset_sha256"])
        saved["version"] = "0.1.0"
        saved.pop("dataset_orders")
        with closing(wb.connect(self.db)) as con:
            con.execute("UPDATE report_runs SET payload_json=? WHERE run_id=?", (wb.json_text(saved), saved["run_id"]))
        before = self.state()["snapshots"]
        self.apply()
        self.assertEqual(self.state()["snapshots"], before)
        self.assertEqual(wb.saved_report(self.db, saved["run_id"]), saved)
        self.assertEqual(wb.saved_report(self.db, saved["run_id"])["metrics"]["orders"], 9)
        self.assertEqual(wb.report(self.db)["metrics"]["orders"], 12)
        with closing(wb.connect(self.db)) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_duplicate_and_invalid_sample_blocks_the_entire_file(self):
        before = self.db.read_bytes()
        checked = imports.preview(self.db, ERRORS, KEY)
        self.assertFalse(checked["can_import"])
        self.assertIsNone(checked["preview_token"])
        self.assertEqual(checked["invalid_rows"], 3)
        errors = " ".join(error for row in checked["rows"] for error in row["errors"])
        for expected in ("repeated within", "already exists", "quantity", "product", "due_at"):
            self.assertIn(expected, errors)
        with self.assertRaises(wb.InputError):
            self.apply(ERRORS, checked)
        self.assertEqual(self.db.read_bytes(), before)

    def test_valid_row_cannot_slip_through_a_mixed_file(self):
        rows = list(csv.reader(io.StringIO(VALID)))
        rows[2][3] = "0"
        text = csv_file(rows[1:])
        checked = imports.preview(self.db, text, KEY)
        self.assertEqual((checked["valid_rows"], checked["invalid_rows"]), (2, 1))
        before = self.state()
        with self.assertRaises(wb.InputError):
            self.apply(text, checked)
        self.assertEqual(self.state(), before)

    def test_field_rules_and_calendar_dates_are_validated(self):
        valid = ["DEMO-9001", "Invented part", "Test bay", "1", "2026-10-03T12:00:00Z", ""]
        cases = [(0, "bad id"), (0, "X" * 65), (1, ""), (1, "X" * 121), (2, ""),
                 (3, "0"), (3, "1000001"), (3, "1.5"), (3, "-1"), (3, "\u0661"),
                 (4, ""), (4, "2026-02-30T12:00:00Z"), (4, "2026-10-03 12:00:00"),
                 (5, "2026-10-03T25:00:00Z"), (1, " newline\nvalue"), (2, "Test\x00bay"),
                 (1, " Part"), (1, "Part ")]
        for column, value in cases:
            with self.subTest(column=column, value=repr(value)):
                row = valid.copy()
                row[column] = value
                checked = imports.preview(self.db, csv_file([row]), KEY)
                self.assertFalse(checked["can_import"])
                self.assertTrue(checked["rows"][0]["errors"])

    def test_header_quoting_and_field_counts_are_checked(self):
        for text in ["", "x,y\n1,2\n", ",".join(imports.COLUMNS) + "\n",
                     ",".join(imports.COLUMNS) + '\n"unterminated',
                     ",".join(["order_id"] * 6) + "\nX,a,b,1,c,d\n"]:
            with self.subTest(text=text), self.assertRaises(wb.InputError):
                imports.preview(self.db, text, KEY)
        for cells in [["DEMO-9", "P"], ["DEMO-9", "P", "C", "1", "2026-10-03T00:00:00Z", "", "extra"]]:
            self.assertFalse(imports.preview(self.db, csv_file([cells]), KEY)["can_import"])

    def test_bom_reordered_headers_unicode_and_quoted_text_are_preserved(self):
        product = "Invented café, 'A'; <span>literal text</span>"
        header = tuple(reversed(imports.COLUMNS))
        values = dict(zip(imports.COLUMNS, ["DEMO-9010", product, "Test bay", "25", "2026-10-03T00:00:00Z", ""]))
        text = "\ufeff" + csv_file([[values[name] for name in header]], header)
        self.apply(text)
        with closing(wb.connect(self.db)) as con:
            self.assertEqual(con.execute("SELECT product FROM work_orders WHERE order_id='DEMO-9010'").fetchone()[0], product)
        self.assertEqual(wb.report(self.db)["metrics"]["orders"], 10)

    def test_byte_and_row_limits_leave_source_untouched(self):
        before = self.state()
        row = ["DEMO-9", "P", "C", "1", "2026-10-03T00:00:00Z", ""]
        oversized = csv_file([[f"DEMO-{index}", *row[1:]] for index in range(imports.MAX_ROWS + 1)])
        for text in ["x" * (imports.MAX_BYTES + 1), oversized, "\ud800"]:
            with self.subTest(size=len(text)), self.assertRaises(wb.InputError):
                imports.preview(self.db, text, KEY)
        self.assertEqual(self.state(), before)

    def test_changed_file_or_expired_preview_cannot_be_applied(self):
        checked = imports.preview(self.db, VALID, KEY)
        before = self.state()
        with self.assertRaises(wb.InputError):
            self.apply(VALID + "\n", checked)
        with self.assertRaises(wb.InputError):
            self.apply(VALID, checked, b"different-process-key")
        for token in ("forged", None, "\u00e9" * 64):
            with self.subTest(token=repr(token)), self.assertRaises(wb.InputError):
                imports.apply_import(self.db, VALID, checked["dataset_sha256"], token, KEY)
        self.assertEqual(self.state(), before)

    def test_changed_source_requires_a_new_preview(self):
        checked = imports.preview(self.db, VALID, KEY)
        with closing(wb.connect(self.db)) as con:
            con.execute("UPDATE work_orders SET quantity=41 WHERE order_id='WO-1001'")
        changed = self.state()
        with self.assertRaises(wb.StaleDataError):
            self.apply(VALID, checked)
        self.assertEqual(self.state(), changed)

    def test_second_insert_failure_rolls_back_orders_and_events(self):
        wb.save_report(self.db, wb.DEFAULT_START, wb.DEFAULT_END, wb.report(self.db)["dataset_sha256"])
        with closing(wb.connect(self.db)) as con:
            con.execute("CREATE TRIGGER fail_second_order BEFORE INSERT ON work_orders "
                        "WHEN NEW.order_id='DEMO-2002' BEGIN SELECT RAISE(ABORT,'simulated storage failure'); END")
        before = self.state()
        with self.assertRaises(sqlite3.IntegrityError):
            self.apply()
        self.assertEqual(self.state(), before)

    def test_double_apply_and_concurrent_apply_add_only_one_batch(self):
        checked = imports.preview(self.db, VALID, KEY)
        outcomes = []
        def attempt():
            try:
                self.apply(VALID, checked)
                outcomes.append("committed")
            except wb.StaleDataError:
                outcomes.append("stale")
        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=8)
            self.assertFalse(thread.is_alive())
        self.assertCountEqual(outcomes, ["committed", "stale"])
        with self.assertRaises(wb.StaleDataError):
            self.apply(VALID, checked)
        again = imports.preview(self.db, VALID, KEY)
        self.assertFalse(again["can_import"])
        self.assertEqual(wb.report(self.db)["metrics"]["orders"], 12)


class ImportHTTPCase(ImportBase):
    def setUp(self):
        super().setUp()
        self.server = app.make_server(self.db)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .05})
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.headers = {"Content-Type": "application/json", "X-Workbench-Token": self.server.token, "Origin": "null"}

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, method, path, payload=None, headers=None):
        with closing(http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)) as con:
            con.request(method, path, json.dumps(payload) if payload is not None else None,
                        self.headers if headers is None else headers)
            response = con.getresponse()
            return response.status, response.read()

    def preview(self):
        status, body = self.request("POST", "/api/imports/preview", {"csv_text": VALID, "synthetic": True})
        self.assertEqual(status, 200)
        return json.loads(body)

    def test_http_preview_apply_and_saved_snapshot_reopening(self):
        saved = wb.save_report(self.db, wb.DEFAULT_START, wb.DEFAULT_END, wb.report(self.db)["dataset_sha256"])
        checked = self.preview()
        payload = {"csv_text": VALID, "synthetic": True, "dataset_sha256": checked["dataset_sha256"],
                   "preview_token": checked["preview_token"]}
        status, body = self.request("POST", "/api/imports/apply", payload)
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(body)["orders_added"], 3)
        status, body = self.request("GET", "/api/reports/" + saved["run_id"])
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), saved)
        self.assertEqual(self.request("POST", "/api/imports/apply", payload)[0], 409)

    def test_import_requires_local_token_origin_and_synthetic_confirmation(self):
        payload = {"csv_text": VALID, "synthetic": True}
        for headers in [{"Content-Type": "application/json"},
                        {**self.headers, "Origin": "https://foreign.example"}]:
            self.assertEqual(self.request("POST", "/api/imports/preview", payload, headers)[0], 403)
        for value in [False, 1, "true", None]:
            self.assertEqual(self.request("POST", "/api/imports/preview", {**payload, "synthetic": value})[0], 400)
        self.assertEqual(self.request("POST", "/api/imports/preview", payload, {**self.headers, "Content-Type": "text/plain"})[0], 415)
        self.assertEqual(wb.report(self.db)["metrics"]["orders"], 9)

    def test_invalid_and_changed_csv_are_refused_over_http(self):
        status, body = self.request("POST", "/api/imports/preview", {"csv_text": ERRORS, "synthetic": True})
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["can_import"])
        checked = self.preview()
        payload = {"csv_text": VALID + "\n", "synthetic": True, "dataset_sha256": checked["dataset_sha256"],
                   "preview_token": checked["preview_token"]}
        self.assertEqual(self.request("POST", "/api/imports/apply", payload)[0], 400)
        self.assertEqual(wb.report(self.db)["metrics"]["orders"], 9)

    def test_import_storage_failure_is_reported_without_partial_rows(self):
        checked = self.preview()
        with closing(wb.connect(self.db)) as con:
            con.execute("CREATE TRIGGER fail_event BEFORE INSERT ON completion_events BEGIN SELECT RAISE(ABORT,'test'); END")
        before = self.state()
        payload = {"csv_text": VALID, "synthetic": True, "dataset_sha256": checked["dataset_sha256"],
                   "preview_token": checked["preview_token"]}
        self.assertEqual(self.request("POST", "/api/imports/apply", payload)[0], 503)
        self.assertEqual(self.state(), before)

    def test_only_known_samples_are_served_and_request_size_is_bounded(self):
        for path in ("/examples/import-valid.csv", "/examples/import-errors.csv"):
            status, body = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertTrue(body.startswith(b"order_id,product"))
        self.assertEqual(self.request("GET", "/examples/../workbench.py")[0], 404)
        # The server rejects an oversized Content-Length before reading a body.
        # Sending megabytes anyway races its close with Windows TCP resets.
        before = self.state()
        headers = {**self.headers, "Content-Length": str(2 * 1024 * 1024 + 1)}
        self.assertEqual(self.request("POST", "/api/imports/preview", headers=headers)[0], 413)
        self.assertEqual(self.state(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
