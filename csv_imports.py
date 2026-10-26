"""Bounded, insert-only imports of original synthetic work orders.

Preview never writes. Apply revalidates the exact CSV inside one SQLite
transaction, refusing a changed source or an expired/changed preview.
"""
from __future__ import annotations

from collections import Counter
from contextlib import closing
import csv
from datetime import datetime, timezone
import hashlib
import hmac
import io
import re
import uuid

import workbench as wb

MAX_BYTES = 256 * 1024
MAX_ROWS = 500
COLUMNS = ("order_id", "product", "work_center", "quantity", "due_at", "completed_at")


def csv_digest(text):
    if not isinstance(text, str):
        raise wb.InputError("CSV content must be UTF-8 text.")
    try:
        encoded = text.encode("utf-8")
    except UnicodeError as exc:
        raise wb.InputError("CSV content must be valid UTF-8 text.") from exc
    if not encoded or len(encoded) > MAX_BYTES:
        raise wb.InputError("Choose a nonempty UTF-8 CSV file of at most 256 KiB.")
    return hashlib.sha256(encoded).hexdigest()


def parse_rows(text, existing_ids):
    digest = csv_digest(text)
    reader = csv.reader(io.StringIO(text.removeprefix("\ufeff"), newline=""), strict=True)
    rows = []
    try:
        header = next(reader, [])
        if len(header) != len(COLUMNS) or set(header) != set(COLUMNS):
            raise wb.InputError("Use exactly these six CSV headers, once each: " + ", ".join(COLUMNS) + ".")
        for cells in reader:
            if not cells:
                continue
            if len(rows) >= MAX_ROWS:
                raise wb.InputError("A CSV import is limited to 500 work orders. No rows were imported.")
            values = {name: value for name, value in zip(header, cells)}
            errors = []
            if len(cells) != len(COLUMNS):
                errors.append("Expected exactly six fields in this record.")
            for name in COLUMNS:
                value = values.get(name, "")
                values[name] = value
                if value != value.strip():
                    errors.append(f"{name}: remove leading or trailing whitespace.")
                if value and not value.isprintable():
                    errors.append(f"{name}: control characters and multiline values are not accepted.")
            if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,63}", values["order_id"]):
                errors.append("order_id: use 1-64 uppercase letters, digits, hyphens or underscores.")
            for name, maximum in (("product", 120), ("work_center", 80)):
                if not 1 <= len(values[name]) <= maximum:
                    errors.append(f"{name}: enter 1-{maximum} characters.")
            quantity = values["quantity"]
            if not re.fullmatch(r"[0-9]{1,7}", quantity) or not 1 <= int(quantity) <= 1_000_000:
                errors.append("quantity: enter a whole number from 1 to 1000000.")
            for name in ("due_at", "completed_at"):
                value = values[name]
                if name == "due_at" and not value:
                    errors.append("due_at: a UTC due timestamp is required.")
                elif value:
                    try:
                        wb.timestamp(value)
                    except wb.InputError:
                        errors.append(f"{name}: use a valid UTC timestamp, YYYY-MM-DDTHH:MM:SSZ.")
            rows.append({"line": reader.line_num, "values": values, "errors": errors})
    except csv.Error as exc:
        raise wb.InputError("CSV quoting or field size is invalid. Check the file and preview again.") from exc
    if not rows:
        raise wb.InputError("The CSV needs at least one work order after its header.")
    counts = Counter(row["values"]["order_id"] for row in rows)
    for row in rows:
        order_id = row["values"]["order_id"]
        if counts[order_id] > 1:
            row["errors"].append("order_id: repeated within this file; each order needs one record.")
        if order_id in existing_ids:
            row["errors"].append("order_id: already exists in the database; existing orders cannot be overwritten.")
    return digest, rows


def signature(key, csv_sha256, dataset_sha256):
    message = f"workfloor.csv.v1\n{csv_sha256}\n{dataset_sha256}".encode("ascii")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def build_preview(con, text, key):
    data = wb.source_data(con)
    fingerprint = wb.source_fingerprint(data)
    digest, rows = parse_rows(text, {row["order_id"] for row in data["orders"]})
    invalid = sum(bool(row["errors"]) for row in rows)
    return {
        "csv_sha256": digest, "dataset_sha256": fingerprint,
        "total_rows": len(rows), "valid_rows": len(rows) - invalid, "invalid_rows": invalid,
        "can_import": invalid == 0, "rows": rows,
        "preview_token": signature(key, digest, fingerprint) if invalid == 0 else None,
        "policy": "All rows must pass. Add new orders only; no updates, deletes or partial imports.",
        "limits": {"bytes": MAX_BYTES, "rows": MAX_ROWS},
    }


def preview(path, text, key):
    with closing(wb.connect(path)) as con:
        con.execute("BEGIN")
        try:
            return build_preview(con, text, key)
        finally:
            con.execute("ROLLBACK")


def apply_import(path, text, expected_fingerprint, preview_token, key):
    digest = csv_digest(text)
    if not isinstance(expected_fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_fingerprint):
        raise wb.InputError("Preview the CSV against the current source before importing.")
    if not isinstance(preview_token, str) or not re.fullmatch(r"[0-9a-f]{64}", preview_token) or not hmac.compare_digest(
        preview_token, signature(key, digest, expected_fingerprint)
    ):
        raise wb.InputError("This file changed or its preview expired. Preview the CSV again.")
    with closing(wb.connect(path)) as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            current = wb.source_fingerprint(wb.source_data(con))
            if current != expected_fingerprint:
                raise wb.StaleDataError("Source data changed since preview. Preview the CSV again; no rows were imported.")
            checked = build_preview(con, text, key)
            if not checked["can_import"]:
                raise wb.InputError("CSV validation failed. No rows were imported; fix the file and preview again.")
            import_id = uuid.uuid4().hex
            events = 0
            for row in checked["rows"]:
                value = row["values"]
                con.execute(
                    "INSERT INTO work_orders (order_id, product, work_center, quantity, due_at) VALUES (?, ?, ?, ?, ?)",
                    (value["order_id"], value["product"], value["work_center"], int(value["quantity"]), value["due_at"]),
                )
                if value["completed_at"]:
                    con.execute(
                        "INSERT INTO completion_events (order_id, source_event_id, occurred_at) VALUES (?, ?, ?)",
                        (value["order_id"], "CSV-" + import_id + "-" + value["order_id"], value["completed_at"]),
                    )
                    events += 1
            result = wb.calculate(con)
            if not result["validation"]["correct_matches_reference"]:
                raise wb.InputError("The post-import report disagreed with its reference. The entire import was rolled back.")
            receipt = {
                "import_id": import_id,
                "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "orders_added": checked["total_rows"], "completion_events_added": events,
                "csv_sha256": digest, "dataset_sha256_before": current,
                "dataset_sha256_after": result["dataset_sha256"],
                "order_ids": [row["values"]["order_id"] for row in checked["rows"]],
                "default_report_metrics": result["metrics"],
                "default_report_matches_reference": True,
                "policy": checked["policy"],
            }
            con.execute("COMMIT")
            return receipt
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
