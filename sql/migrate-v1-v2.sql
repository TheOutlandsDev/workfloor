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
