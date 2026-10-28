# Durable import history and the v0.4 upgrade

Workfloor 0.4 records each **committed** CSV import in SQLite, in the same
transaction as its new orders/events. It saves the complete receipt: import ID,
UTC commit time, file SHA-256, affected order IDs, counts, before/after dataset
fingerprints and report metrics. Raw CSV contents and filenames are not saved.

Open **Import history** in the local app to view a receipt or download its exact
stored UTF-8 JSON bytes. Restarting the app does not remove it. A verified v2
database backup/restore preserves all five tables, including import history.
The last 50 entries are shown; older entries remain in SQLite and can still be
retrieved by their known receipt URL. Existing saved report snapshots stay separate.

Only successful imports create ledger rows. Validation refusals, failed writes,
updates, deletes and external activity are not an audit trail. A local database
editor can change records. Neither the file hash nor the ledger authenticates an
author, proves human review or makes data tamper-proof.

## Fresh download

Extract the 0.4 ZIP into a new folder, verify its checksum and use Python 3.12
or 3.13. No package installation is needed. `python app.py --port 0` creates a
new **schema v2** demonstration database. Existing v1 databases are refused at
startup; the app does **not** migrate them silently.

To try the workflow: save the 9-order report, import the valid invented CSV,
then open Import history. Expect one committed receipt for 3 new orders and
2 events, while the current report becomes 12 orders / 6 delayed. View/download
the receipt, stop/restart with the same `--data-dir`, then download it again.
The bytes must agree. A failed receipt insertion rolls back the whole import.

## Explicit upgrade of an existing v1 database

1. Preserve the original app/source version. Stop all Workfloor/database clients,
   including older versions that do not use the ownership guard.
2. Choose an **absolute** existing data directory and an **absolute new** private
   backup directory outside it, with an existing parent. Keep backups outside
   the extracted app. Replace the uppercase placeholders below:

   ```text
   python migrate.py --data-dir ABSOLUTE_EXISTING_DATA_DIR --backup-dir ABSOLUTE_NEW_BACKUP_DIR
   ```

3. The command takes ownership, checks the exact v1 schema and database integrity,
   creates and verifies a full v1 backup, and only then begins an exclusive SQLite
   transaction. It compares all original table values against the backup, adds
   the empty history table and index, checks integrity and preservation again,
   and commits schema version 2.
4. Start v0.4 with the same data directory:

   ```text
   python app.py --data-dir ABSOLUTE_EXISTING_DATA_DIR --port 0
   ```

5. Check the current report and saved snapshots. **Earlier imports are not
   reconstructed.** Their orders remain, but receipts that were not persisted
   by older versions cannot be recovered from the source rows.

Quotes are needed around paths containing spaces. On Linux the supported
executable may be named `python3`. Exit 0 reports a completed upgrade; 2 means
refusal/failure. The ownership guard must stay in place; never delete it to bypass
another process. A repeated upgrade of v2 is refused without another backup.

## Failure, restore and rollback

- Missing/foreign/changed schema, sidecars, WAL mode, existing backup destinations,
  linked storage and active ownership cause refusal. No automatic repair occurs.
- A backup or verification failure prevents migration. An injected DDL failure
  rolls back schema/table changes; the verified backup remains available.
- A source change after backup is refused, preserving that newer source rather
  than reverting it. Stop the other client and retry with a new backup path.
- Preserve partial **new** output after failure. If interruption occurs around
  commit, inspect the schema and verify the backup before retrying. Power-loss
  and hostile concurrent filesystem writers remain unqualified.

The pre-upgrade backup is still schema v1. Restore it into a **new** data directory
with [the recovery CLI](RECOVERY.md). Use the original v0.3.1 app for that restored
v1 copy, or explicitly upgrade the new copy before opening it with v0.4. Never
overwrite the original directory to undo an upgrade. Workfloor v0.4 recovery can
verify/restore both v1 and v2 backups; v0.3.1 does not understand a v2 database.

Backups are private and bounded to 64 MiB. A rollback backup does not contain
later v2 imports. It preserves the exact earlier database state, not separately
downloaded CSV/receipt files or changes made after its checkpoint.

## API and reproducible evidence

- `GET /api/imports`: the latest 50 committed entries, with counts and fingerprints.
- `GET /api/imports/IMPORT_ID/receipt.json`: exact stored bytes plus a download
  filename. Invalid IDs return 400; an unknown valid ID returns 404.
- `POST /api/imports/apply`: existing preview-bound import, now with its durable
  receipt in the same transaction. A storage failure returns no partial import.

All endpoints remain loopback-only with the existing Host/Origin/token policy.
Receipts and source records can reveal private work; keep real records out of
public issues or screenshots.

```text
python scripts/verify_import_history.py --workspace ABSOLUTE_NEW_PRIVATE_WORKSPACE
```

The script constructs an original synthetic v1 fixture, verifies the backed-up
upgrade, imports three invented orders, checks exact receipt bytes after server
restart, in a new Python process and after database restore, and injects a failed
receipt write to prove rollback. See [the numeric case](../examples/import-history-case.json)
and [validation](VALIDATION.md). This CLI/HTTP case does not itself prove browser
interaction; the separate Windows browser CI checks the history dialog and downloads.
