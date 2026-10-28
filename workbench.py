"""Original synthetic reporting example. No employer data or schema is used."""
from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import closing
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid

ROOT = Path(__file__).resolve().parent
APP_ID = 1297564209
DEFAULT_START, DEFAULT_END = "2026-10-01", "2026-10-08"
VERSION = "0.4.1"
SCHEMA_VERSION = 2
STATUS_LABELS = {
    "on_time": "Completed on time", "completed_late": "Completed late",
    "open_overdue": "Open at cutoff", "review_conflict": "Conflicting event",
    "review_missing_time": "Missing completion time",
}


class InputError(ValueError):
    pass


class StaleDataError(InputError):
    pass


def json_text(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def bounds(start, end):
    if not all(isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v)
               for v in (start, end)):
        raise InputError("Use dates in YYYY-MM-DD format.")
    try:
        a, b = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError as exc:
        raise InputError("Choose valid calendar dates.") from exc
    if not 0 < (b - a).days <= 366:
        raise InputError("The end must follow the start, within 366 days.")
    return {"start_utc": start + "T00:00:00Z", "end_utc": end + "T00:00:00Z"}


def timestamp(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise InputError("Source timestamps must be canonical UTC seconds or null.")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise InputError("A source timestamp is not a valid UTC date/time.") from exc


def connect(path):
    con = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=rw", uri=True,
                          timeout=5, autocommit=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def ensure_database(path):
    """Create only a new file. Existing foreign or incomplete databases are refused."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        with closing(connect(path)) as con:
            if con.execute("PRAGMA application_id").fetchone()[0] != APP_ID:
                raise InputError("Existing database is not Workfloor. Preserve it and choose another data directory.")
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version == 1:
                raise InputError("Schema v1 needs an explicit backed-up upgrade: see docs/IMPORT-HISTORY.md and migrate.py. No automatic migration was performed.")
            if version != SCHEMA_VERSION:
                raise InputError("Unsupported Workfloor schema. Preserve it and use the matching app version.")
        return False
    os.close(fd)
    try:
        fixture = json.loads((ROOT / "fixtures/synthetic.json").read_text(encoding="utf-8"))
        for row in fixture["orders"]:
            timestamp(row[4])
        for row in fixture["events"]:
            timestamp(row[3])
        with closing(sqlite3.connect(path, autocommit=True)) as con:
            con.execute("PRAGMA foreign_keys = ON")
            try:
                con.executescript("BEGIN IMMEDIATE;\n" + (ROOT / "sql/schema.sql").read_text(encoding="utf-8"))
                con.executemany("INSERT INTO work_orders VALUES (?, ?, ?, ?, ?)", fixture["orders"])
                con.executemany("INSERT INTO process_steps VALUES (?, ?, ?)", fixture["steps"])
                con.executemany("INSERT INTO completion_events VALUES (?, ?, ?, ?)", fixture["events"])
                con.execute("COMMIT")
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise
        return True
    except Exception:
        # Only remove the empty/new file reserved by this invocation.
        path.unlink(missing_ok=True)
        raise


def source_data(con):
    result = {
        "orders": [dict(r) for r in con.execute("SELECT * FROM work_orders ORDER BY order_id")],
        "steps": [dict(r) for r in con.execute("SELECT * FROM process_steps ORDER BY order_id, sequence")],
        "events": [dict(r) for r in con.execute("SELECT * FROM completion_events ORDER BY record_no")],
    }
    for row in result["orders"]:
        timestamp(row["due_at"])
    for row in result["events"]:
        timestamp(row["occurred_at"])
    return result


def reference_rows(data, parameters):
    """Procedural reference: no report SQL, SQL aggregates, or SQL classifications."""
    start, end = timestamp(parameters["start_utc"]), timestamp(parameters["end_utc"])
    groups = defaultdict(list)
    for event in data["events"]:
        groups[(event["order_id"], event["source_event_id"])].append(event["occurred_at"])
    steps = Counter(r["order_id"] for r in data["steps"])
    result = []
    for order in data["orders"]:
        due = timestamp(order["due_at"])
        if due is None or not start <= due < end:
            continue
        matching = [times for (oid, _), times in groups.items() if oid == order["order_id"]]
        conflict = any(len(set(times)) > 1 for times in matching)
        missing = any(set(times) == {None} for times in matching)
        usable = [times[0] for times in matching if len(set(times)) == 1
                  and times[0] is not None and timestamp(times[0]) < end]
        completed = min(usable) if usable else None
        if conflict:
            state = "review_conflict"
        elif missing:
            state = "review_missing_time"
        elif completed is None:
            state = "open_overdue"
        elif timestamp(completed) > due:
            state = "completed_late"
        else:
            state = "on_time"
        result.append({**order, "completed_at": completed, "status": state,
                       "step_count": steps[order["order_id"]],
                       "replay_rows": sum(len(times) - 1 for times in matching if len(set(times)) == 1)})
    return sorted(result, key=lambda r: (r["due_at"], r["order_id"]))


def source_fingerprint(data):
    return hashlib.sha256(json_text(data).encode()).hexdigest()


def calculate(con, start=DEFAULT_START, end=DEFAULT_END):
    parameters = bounds(start, end)
    data = source_data(con)
    fingerprint = source_fingerprint(data)
    correct_sql = (ROOT / "sql/report.sql").read_text(encoding="utf-8")
    naive_sql = (ROOT / "sql/naive_join.sql").read_text(encoding="utf-8")
    rows = [dict(r) for r in con.execute(correct_sql, parameters)]
    reference = reference_rows(data, parameters)
    counts = Counter(r["status"] for r in rows)
    naive = dict(con.execute(naive_sql, parameters).fetchone())
    expected_units = sum(r["quantity"] for r in reference)
    missing_due = [r["order_id"] for r in data["orders"] if r["due_at"] is None]
    by_order = defaultdict(list)
    for event in data["events"]:
        by_order[event["order_id"]].append(event)
    for row in rows:
        row["status_label"] = STATUS_LABELS[row["status"]]
        row["steps"] = [s for s in data["steps"] if s["order_id"] == row["order_id"]]
        row["events"] = by_order[row["order_id"]]
    # Compare the query's original columns before UI-only fields are added.
    comparable = [{k: r[k] for k in reference[0]} for r in rows] if reference else rows
    return {
        "version": VERSION, "synthetic": True, "dataset_orders": len(data["orders"]),
        "start": start, "end": end, "parameters": parameters,
        "definition": "Orders due in [start, end), using completion events strictly before end. All timestamps are UTC.",
        "dataset_sha256": fingerprint,
        "metrics": {"orders": len(rows), "units": sum(r["quantity"] for r in rows),
                    "delayed": counts["completed_late"] + counts["open_overdue"],
                    "completed_late": counts["completed_late"], "open_overdue": counts["open_overdue"],
                    "on_time": counts["on_time"],
                    "review": counts["review_conflict"] + counts["review_missing_time"]},
        "rows": rows,
        "quality": {"missing_due_orders": missing_due,
                    "missing_due_count": len(missing_due),
                    "replay_rows_in_cohort": sum(r["replay_rows"] for r in rows),
                    "conflicting_orders_in_cohort": counts["review_conflict"],
                    "missing_completion_time_in_cohort": counts["review_missing_time"]},
        "validation": {"correct_matches_reference": comparable == reference,
                       "expected_orders": len(reference), "expected_units": expected_units,
                       "naive_orders": naive["work_order_count"], "naive_units": naive["units"],
                       "inflation_detected": naive["work_order_count"] != len(reference) or naive["units"] != expected_units,
                       "extra_joined_rows": naive["work_order_count"] - len(reference)},
        "sql": {"correct": correct_sql, "naive": naive_sql},
    }


def report(path, start=DEFAULT_START, end=DEFAULT_END):
    with closing(connect(path)) as con:
        con.execute("BEGIN")
        try:
            return calculate(con, start, end)
        finally:
            con.execute("ROLLBACK")


def save_report(path, start, end, expected_fingerprint):
    if not isinstance(expected_fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_fingerprint):
        raise InputError("Load a report before saving its snapshot.")
    with closing(connect(path)) as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            payload = calculate(con, start, end)
            if payload["dataset_sha256"] != expected_fingerprint:
                raise StaleDataError("Source data changed. Reload and review the report before saving.")
            if not payload["validation"]["correct_matches_reference"]:
                raise InputError("The report disagrees with its reference. Snapshot was not saved.")
            run_id = uuid.uuid4().hex
            saved_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            payload.update({"run_id": run_id, "saved_at": saved_at})
            con.execute("INSERT INTO report_runs VALUES (?, ?, ?, ?, ?, ?)",
                        (run_id, saved_at, start, end, payload["dataset_sha256"], json_text(payload)))
            con.execute("COMMIT")
            return payload
        except Exception:
            con.execute("ROLLBACK")
            raise


def history(path):
    with closing(connect(path)) as con:
        return [dict(r) for r in con.execute(
            "SELECT run_id, saved_at, start_date, end_date, dataset_sha256 FROM report_runs ORDER BY saved_at DESC, rowid DESC LIMIT 50")]


def saved_report(path, run_id):
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise InputError("Invalid snapshot identifier.")
    with closing(connect(path)) as con:
        row = con.execute("SELECT payload_json FROM report_runs WHERE run_id = ?", (run_id,)).fetchone()
        return json.loads(row[0]) if row else None
