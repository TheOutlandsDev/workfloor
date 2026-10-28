PRAGMA application_id = 1297564209;
PRAGMA user_version = 2;
CREATE TABLE work_orders (
    order_id TEXT PRIMARY KEY,
    product TEXT NOT NULL,
    work_center TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0 AND quantity <= 1000000),
    due_at TEXT
);
CREATE TABLE process_steps (
    order_id TEXT NOT NULL REFERENCES work_orders(order_id),
    sequence INTEGER NOT NULL CHECK(sequence > 0),
    step_name TEXT NOT NULL,
    PRIMARY KEY(order_id, sequence)
);
-- record_no identifies an incoming row; source_event_id identifies an event.
-- Replays are retained so the reporting rules can be inspected.
CREATE TABLE completion_events (
    record_no INTEGER PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES work_orders(order_id),
    source_event_id TEXT NOT NULL,
    occurred_at TEXT
);
CREATE INDEX completion_order ON completion_events(order_id, source_event_id);
CREATE TABLE report_runs (
    run_id TEXT PRIMARY KEY,
    saved_at TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    dataset_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE import_runs (
    import_id TEXT PRIMARY KEY,
    imported_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status = 'committed'),
    csv_sha256 TEXT NOT NULL,
    dataset_sha256_before TEXT NOT NULL,
    dataset_sha256_after TEXT NOT NULL,
    orders_added INTEGER NOT NULL CHECK(orders_added BETWEEN 1 AND 500),
    completion_events_added INTEGER NOT NULL CHECK(completion_events_added BETWEEN 0 AND 500),
    receipt_json TEXT NOT NULL
);
CREATE INDEX import_chronology ON import_runs(imported_at, import_id);
PRAGMA user_version = 2;
