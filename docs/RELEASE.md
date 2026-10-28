# Workfloor 0.4.1 - durable import history

[Download ZIP](https://github.com/TheOutlandsDev/workfloor/releases/download/v0.4.1/workfloor-0.4.1.zip)
[Upgrade guide](IMPORT-HISTORY.md) | [Validation](VALIDATION.md)

CSV orders, completion events and their complete JSON receipt now commit in one
SQLite transaction. Open Import history to inspect or download the exact stored
receipt after restarting the app or restoring a verified backup. Receipt-storage
failure rolls back the entire batch. The latest 50 entries are listed without
deleting older ones. Raw CSV contents and filenames are not retained.

Fresh databases use schema 2. Existing schema-1 databases require an explicit
stopped-app upgrade: `python migrate.py --data-dir ABSOLUTE_EXISTING_DATA_DIR
--backup-dir ABSOLUTE_NEW_BACKUP_DIR` (one command on one line). Use new absolute
backup paths with existing parents. It creates and verifies the old-format backup
before adding history, preserves all four original tables and saved payloads,
and starts with empty history. Earlier receipts are not fabricated. Failed
upgrades preserve the backup and roll back the schema transaction.

## Run and reproduce

Compare the three release assets with their checksum list; extract into a new
folder. With Python 3.12+ and sqlite3 installed, run `python app.py --port 0`, or
use `start-workfloor.cmd --port 0` on Windows. No pip packages are needed for the
application. Use only invented records. Follow the [ten-check case](../examples/import-history-case.json)
and [reproduction command](IMPORT-HISTORY.md). The report moves from 9 orders /
365 units / 4 delayed to 12 / 440 / 6 after the three-order sample import.

An explicit source inventory excludes databases, backups, runtime dependencies,
logs, credentials and employer material. Windows/Ubuntu with Python 3.12/3.13
build and extract identical ZIPs, then run the unit, CLI, recovery and import-history
checks. Main may reuse only a completed successful canonical push run at the
identical commit, and rechecks all four artifacts and every committed member
before creating a new release. Existing named releases are never replaced.
A separate Windows workflow checks three browser scenarios.

## Limits

This remains a synthetic, single-user local prototype. History is editable by
someone with database access; hashes are not signatures, identity or proof of
human review. Only committed imports are recorded. There is no undo-import UI.
Old binaries do not understand schema 2: use their preserved schema-1 backup in
a separate directory. Recovery accepts either supported schema but does not
upgrade it automatically. Stop every older app and database tool before maintenance.

Only trusted local DELETE-journal databases up to 64 MiB are qualified. No employer
system, production integration, macOS execution, multi-user service, hostile-writer
isolation or power-loss guarantee is represented. Browser is disabled locally;
new local visual acceptance is not claimed. Historical captures remain v0.2.
The earlier v0.3.1 release and its [notes](RELEASE-v0.3.1.md) remain unchanged.


Patch 0.4.1 gives the stored-receipt JSON explicit dark text and a light background,
fixing the low-contrast inherited SQL text style found during actual capture review.
It also corrects the sidebar version and removes a stale version from the insert-only
feature label. No database schema or receipt-storage behavior changes. The 0.4.0
release and its [notes](RELEASE-v0.4.0.md) remain unchanged. Capture and walkthrough
sources are separate from the downloadable application source inventory.
