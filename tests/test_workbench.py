from contextlib import closing
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

import app
import workbench as wb


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        # Keep disposable test data inside this checkout, including in restricted
        # desktop sandboxes whose redirected OS temp directory is not writable.
        test_root = (wb.ROOT / ".test-tmp").resolve()
        test_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="case-", dir=test_root)
        if Path(self.temp.name).resolve().parent != test_root:
            raise RuntimeError("Test directory escaped its intended root")
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "workfloor.sqlite3"
        wb.ensure_database(self.db)

    def test_hand_authored_default_truth(self):
        result = wb.report(self.db)
        self.assertEqual(result["metrics"], {"orders": 9, "units": 365, "delayed": 4,
            "completed_late": 1, "open_overdue": 3, "on_time": 3, "review": 2})
        truth = {"WO-1001":"on_time", "WO-1002":"completed_late", "WO-1003":"open_overdue",
            "WO-1004":"review_missing_time", "WO-1005":"on_time", "WO-1007":"on_time",
            "WO-1010":"open_overdue", "WO-1011":"review_conflict", "WO-1012":"open_overdue"}
        self.assertEqual({r["order_id"]:r["status"] for r in result["rows"]}, truth)
        self.assertTrue(result["validation"]["correct_matches_reference"])

    def test_intentional_join_error_is_detected(self):
        validation = wb.report(self.db)["validation"]
        self.assertEqual(validation["naive_orders"], 26)
        self.assertEqual(validation["naive_units"], 1195)
        self.assertEqual(validation["extra_joined_rows"], 17)
        self.assertTrue(validation["inflation_detected"])

    def test_due_boundaries_are_half_open(self):
        rows = wb.report(self.db, "2026-10-01", "2026-10-02")["rows"]
        self.assertEqual([r["order_id"] for r in rows], ["WO-1007"])
        self.assertEqual(rows[0]["status"], "on_time")

    def test_completion_at_cutoff_is_excluded(self):
        rows = {r["order_id"]:r for r in wb.report(self.db)["rows"]}
        self.assertIsNone(rows["WO-1012"]["completed_at"])
        later = {r["order_id"]:r for r in wb.report(self.db, "2026-10-01", "2026-10-09")["rows"]}
        self.assertEqual(later["WO-1012"]["status"], "completed_late")
        self.assertEqual(later["WO-1010"]["status"], "open_overdue")

    def test_later_completion_changes_only_later_snapshot(self):
        later = {r["order_id"]:r for r in wb.report(self.db, "2026-10-01", "2026-10-10")["rows"]}
        self.assertEqual(later["WO-1010"]["status"], "completed_late")
        self.assertEqual(later["WO-1005"]["status"], "on_time")

    def test_replays_and_conflicts_are_different(self):
        result = wb.report(self.db)
        rows = {r["order_id"]:r for r in result["rows"]}
        self.assertEqual(rows["WO-1002"]["replay_rows"], 1)
        self.assertEqual(len(rows["WO-1002"]["events"]), 2)
        self.assertIsNone(rows["WO-1011"]["completed_at"])
        self.assertEqual(result["quality"]["missing_due_orders"], ["WO-1009"])
        self.assertEqual(result["quality"]["replay_rows_in_cohort"], 1)

    def test_empty_range_is_not_a_proof_of_naive_correctness(self):
        result = wb.report(self.db, "2026-11-01", "2026-11-02")
        self.assertEqual(result["metrics"]["orders"], 0)
        self.assertTrue(result["validation"]["correct_matches_reference"])
        self.assertFalse(result["validation"]["inflation_detected"])

    def test_invalid_dates_and_sql_text_are_rejected(self):
        for start, end in [("20261001","2026-10-08"),("2026-02-30","2026-03-01"),
            ("2026-10-08","2026-10-01"),("2026-10-01","2026-10-01"),
            ("2026-01-01","2027-01-03"),("2026-10-01' OR 1=1 --","2026-10-08"),
            (None,"2026-10-08")]:
            with self.subTest(start=start, end=end), self.assertRaises(wb.InputError):
                wb.report(self.db, start, end)
        self.assertEqual(wb.report(self.db)["metrics"]["orders"], 9)

    def test_query_does_not_modify_source(self):
        before = wb.report(self.db)["dataset_sha256"]
        wb.report(self.db, "2026-10-01", "2026-10-10")
        self.assertEqual(before, wb.report(self.db)["dataset_sha256"])
        self.assertEqual(wb.history(self.db), [])

    def test_snapshot_survives_new_connection_and_source_changes(self):
        loaded = wb.report(self.db)
        saved = wb.save_report(self.db, loaded["start"], loaded["end"], loaded["dataset_sha256"])
        with closing(wb.connect(self.db)) as con:
            con.execute("UPDATE work_orders SET product = ? WHERE order_id = ?", ("Revised invented product", "WO-1001"))
        reopened = wb.saved_report(self.db, saved["run_id"])
        self.assertEqual(reopened, saved)
        self.assertNotEqual(wb.report(self.db)["dataset_sha256"], saved["dataset_sha256"])
        self.assertIn("Bench sensor", [r["product"] for r in reopened["rows"]])
        self.assertEqual(len(wb.history(self.db)), 1)

    def test_stale_save_refused_without_losing_existing_snapshot(self):
        loaded = wb.report(self.db)
        first = wb.save_report(self.db, loaded["start"], loaded["end"], loaded["dataset_sha256"])
        with closing(wb.connect(self.db)) as con:
            con.execute("UPDATE work_orders SET quantity = quantity + 1 WHERE order_id = ?", ("WO-1001",))
        with self.assertRaises(wb.StaleDataError):
            wb.save_report(self.db, loaded["start"], loaded["end"], loaded["dataset_sha256"])
        self.assertEqual(len(wb.history(self.db)), 1)
        self.assertEqual(wb.saved_report(self.db, first["run_id"]), first)

    def test_failed_snapshot_insert_rolls_back(self):
        loaded = wb.report(self.db)
        first = wb.save_report(self.db, loaded["start"], loaded["end"], loaded["dataset_sha256"])
        with closing(wb.connect(self.db)) as con:
            con.execute("CREATE TRIGGER fixture_failure BEFORE INSERT ON report_runs BEGIN SELECT RAISE(ABORT, 'fixture storage failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            wb.save_report(self.db, loaded["start"], loaded["end"], loaded["dataset_sha256"])
        self.assertEqual(len(wb.history(self.db)), 1)
        self.assertEqual(wb.saved_report(self.db, first["run_id"]), first)

    def test_existing_database_is_preserved(self):
        other = Path(self.temp.name) / "other.sqlite3"
        with closing(sqlite3.connect(other)) as con:
            con.execute("CREATE TABLE original (value TEXT)")
            con.execute("INSERT INTO original VALUES ('keep me')")
            con.commit()
        original = other.read_bytes()
        with self.assertRaises(wb.InputError):
            wb.ensure_database(other)
        self.assertEqual(other.read_bytes(), original)
        self.assertFalse(wb.ensure_database(self.db))

    def test_invalid_source_timestamp_is_not_silently_classified(self):
        with closing(wb.connect(self.db)) as con:
            con.execute("UPDATE completion_events SET occurred_at = ? WHERE record_no = ?", ("2026-13-01T00:00:00Z", 1))
        with self.assertRaises(wb.InputError):
            wb.report(self.db)
        self.assertEqual(wb.history(self.db), [])

    def test_order_keys_are_unique_and_steps_use_foreign_keys(self):
        with closing(wb.connect(self.db)) as con:
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("INSERT INTO work_orders SELECT * FROM work_orders WHERE order_id = 'WO-1001'")
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("INSERT INTO process_steps VALUES ('missing',1,'Verify')")


class HTTPCase(unittest.TestCase):
    def setUp(self):
        DatabaseCase.setUp(self)
        self.server = app.make_server(self.db, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, method, path, value=None, headers=None):
        con = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            payload = json.dumps(value) if value is not None else None
            con.request(method, path, payload, headers or {})
            response = con.getresponse()
            data = response.read()
            return response.status, dict(response.getheaders()), data
        finally:
            con.close()

    def test_http_report_and_no_side_effect_get(self):
        status, headers, body = self.request("GET", "/api/report?start=2026-10-01&end=2026-10-08")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["metrics"]["orders"], 9)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(wb.history(self.db), [])

    def test_http_invalid_parameters(self):
        for path in ["/api/report?start=2026-10-01", "/api/report?start=2026-10-01&start=2026-10-02&end=2026-10-08"]:
            self.assertEqual(self.request("GET", path)[0], 400)

    def test_host_foreign_origin_and_missing_token_refused(self):
        self.assertEqual(self.request("GET", "/api/meta", headers={"Host":"foreign.example"})[0], 403)
        payload={"start":wb.DEFAULT_START,"end":wb.DEFAULT_END,"dataset_sha256":wb.report(self.db)["dataset_sha256"]}
        self.assertEqual(self.request("POST", "/api/reports", payload, {"Content-Type":"application/json"})[0],403)
        headers={"Content-Type":"application/json","X-Workbench-Token":self.server.token,"Origin":"https://foreign.example"}
        self.assertEqual(self.request("POST", "/api/reports", payload, headers)[0],403)
        self.assertEqual(wb.history(self.db), [])

    def test_opaque_browser_origin_save_and_reopen(self):
        payload={"start":wb.DEFAULT_START,"end":wb.DEFAULT_END,"dataset_sha256":wb.report(self.db)["dataset_sha256"]}
        headers={"Content-Type":"application/json","X-Workbench-Token":self.server.token,"Origin":"null"}
        status, _, body=self.request("POST", "/api/reports", payload, headers)
        self.assertEqual(status,201)
        saved=json.loads(body)
        status, _, body=self.request("GET", "/api/reports/"+saved["run_id"])
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body),saved)

    def test_stale_http_save_returns_conflict(self):
        payload={"start":wb.DEFAULT_START,"end":wb.DEFAULT_END,"dataset_sha256":"0"*64}
        headers={"Content-Type":"application/json","X-Workbench-Token":self.server.token}
        self.assertEqual(self.request("POST", "/api/reports", payload, headers)[0],409)
        self.assertEqual(wb.history(self.db),[])

    def test_static_allowlist(self):
        for path in ["/../workbench.py", "/fixtures/synthetic.json", "/data/workfloor.sqlite3"]:
            self.assertEqual(self.request("GET",path)[0],404)
        self.assertEqual(self.request("GET","/app.js")[0],200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
