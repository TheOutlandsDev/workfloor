# Reporting decisions and tradeoffs

## One grain before any dashboard

The report counts work orders, not routing rows or raw event rows. A work order may have several planned steps and several incoming completion records. Directly joining both relationships produces a Cartesian multiplication inside each order. `COUNT(DISTINCT order_id)` alone would hide that count symptom while leaving repeated quantities and ambiguous completion evidence unresolved. The corrected query reduces each relationship before joining.

## Half-open UTC dates

Inputs are validated calendar dates. A cohort is `[start 00:00:00Z, end 00:00:00Z)`, and the same upper cutoff applies to completion event time. An exact-start due time is included; an exact-end due time or completion is excluded. This avoids overlapping adjacent ranges. The tradeoff is an explicit exclusive-end control rather than an inclusive calendar label. Local time zones, daylight saving transitions and working-day calendars are outside the model.

## Keep uncertainty visible

An identical event replay can be collapsed without changing the known timestamp. Copies of one event with different timestamps cannot be resolved that way. The source rows are retained; the report leaves conflicting or undated completion timing in review, even when a more convenient usable record also exists. This conservative policy reduces false certainty but may overstate review work. A real system would need approved business definitions and ingestion/reconciliation rules.

## SQLite and frozen snapshots

SQLite makes the prototype portable without a database service or dependency installer. The source fixture, relational constraints and saved results are inspectable. A save transaction computes against a consistent source view and checks the loaded fingerprint before inserting a new snapshot. No saved report is overwritten by the interface. External source changes trigger a stale-save refusal.

This provides reproducibility for a local example, not server authorization or a tamper-proof record. Snapshot JSON includes the selected orders and their raw events, parameters and query text. The fingerprint covers all three source tables, including rows outside the selected cohort, so even an unrelated source change conservatively requires a reload.

## A separate reference and an explicit counterexample

Python groups source rows and compares parsed UTC datetimes without running the report SQL. The test suite additionally checks manually authored expected classifications, counts and boundary examples. Agreement is useful evidence for this bounded fixture; both implementations still share the documented business policy and can share a mistaken assumption. The wrong SQL remains visible and deliberately fails on the default fixture. A range that does not expose its defect is labeled accordingly.

## v0.1 milestone boundary

This original demonstration combines reporting judgment with a complete small application. Source imports, manufacturing integrations, live planning, authentication and public hosting would substantially change its operating assumptions. They are separate future work rather than hidden prototype features.

## v0.2 — all rows or no rows

CSV imports use one record per new work order and an optional completion timestamp. Required UTC due times make imported orders reportable; an empty completion creates no event. The narrow format deliberately excludes routing steps, raw event replays, conflict resolution and updates. Those need a different reconciliation policy.

Every row is checked before any row can be imported. Duplicate IDs in either the file or database block the whole batch. This trades the convenience of partial success/upserts for a predictable review and retry path. Text is never interpolated into SQL or HTML.

A valid preview is bound to the exact UTF-8 file hash and source fingerprint with a process-scoped signature. Apply revalidates under BEGIN IMMEDIATE and inserts new source rows only. A source change requires another preview; any write/reference failure rolls back the entire batch. The signature binds inputs, not human attention or record authenticity.

The existing database schema and saved JSON payloads are preserved. No migration, persistent import-history table or undo-import UI was added. Receipts can be downloaded during the browser session; saved snapshots freeze reporting evidence, not a complete database backup. These boundaries keep the next data workflow inspectable without implying a production import service.

## v0.3 - recovery into a new directory

A report snapshot explains an earlier result but cannot reconstruct the complete
source database. Recovery therefore has its own stopped-app CLI, with no web
endpoint. The v0.3 server and maintenance operations share a process-owned guard;
OS ownership disappears after a crash without deleting a marker someone else may
hold. Older releases do not participate and must be stopped manually.

SQLite's backup API reads a fixed transaction snapshot. The backup is checked for
supported schema, structural integrity, foreign keys, exact members, table counts
and SHA-256; restore copies its exact bytes into a newly created directory. This
preserves the original dataset while the operator checks a candidate restore.
Rejecting existing destinations costs an extra directory and explicit selection
on restart, but removes an accidental overwrite path. There is no automatic repair,
WAL conversion, in-place undo or migration. Read docs/RECOVERY.md for limits.


## v0.4: durable receipt and explicit upgrade

Orders, events and canonical JSON receipt use one SQLite transaction: if receipt
storage fails, the import fails too. Storing JSON preserves exact downloaded bytes
across restarts rather than rebuilding a receipt from current rows. Indexed metadata
makes the latest 50 visible; older receipts remain stored. This duplicates a small
amount of metadata in exchange for stable downloads. The 64 MiB database limit remains.

The only upgrade is schema 1 to 2. It takes the shared ownership guard, verifies a
new v1 backup, then holds an exclusive SQLite transaction while checking that the
original four tables still match the backup. It adds an empty ledger without
rewriting old payloads. Failure rolls back DDL; backup remains. Receipt times
cannot be recovered from historical imports, so they are never invented.

Local database owners can edit receipts. These records are useful operational
history, not signed audit evidence, operator identity or proof of human approval.
