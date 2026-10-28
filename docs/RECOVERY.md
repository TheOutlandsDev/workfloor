# Stop, back up, verify and restore

Workfloor 0.3 adds an **offline database backup**, separate from report snapshots.
The database contains all work orders, process steps, completion events and saved
report payloads. A report JSON export or a saved report snapshot is not a database
backup. CSV files and browser-downloaded import receipts are separate files;
they are not stored in SQLite and are not included by this command.

Use Python 3.12 or 3.13, trusted **local** storage, and the same reviewed app
version. Stop every Workfloor instance with Ctrl+C and wait for it to exit.
Choose **absolute** paths with existing parents. Keep backups outside the app
and source data directory, in private storage. The examples below are placeholders:

```text
python recovery.py backup --data-dir ABSOLUTE_EXISTING_DATA_DIR --output ABSOLUTE_NEW_BACKUP_DIR
python recovery.py verify --backup ABSOLUTE_BACKUP_DIR
python recovery.py restore --backup ABSOLUTE_BACKUP_DIR --data-dir ABSOLUTE_NEW_RESTORED_DATA_DIR
python app.py --data-dir ABSOLUTE_RESTORED_DATA_DIR --port 0
```

Replace the uppercase placeholders before running. On Linux the executable may
be named `python3`. On Windows use PowerShell and quote paths containing spaces.
The backup and restore directories must **not exist** yet. Outputs are created
exclusively; no command merges, overwrites, deletes or repairs existing data.
Exit 0 means the selected operation completed; exit 2 means it was refused or
could not complete. Preserve a partial **new** output after failure and select a
new path for a retry. Never treat partial output as a verified backup.

## What gets checked

Backup holds the same process-ownership guard as the v0.3 server, probes SQLite
transaction availability, verifies the exact supported schema, runs
`PRAGMA integrity_check` and `PRAGMA foreign_key_check`, and creates a consistent
snapshot through SQLite's backup API in a read transaction. It checks the copy
again, records its byte length, SHA-256 and all four table counts in
`manifest.json`, and verifies that complete two-file backup before success.
The stored SQLite read/write header is checked explicitly; an immutable connection
can otherwise report DELETE mode for a WAL-marked file.
The snapshot file need not be byte-identical to the source SQLite container;
SQLite can change container bookkeeping. Table values and saved payloads persist.

Verify accepts exactly `workfloor.sqlite3` and `manifest.json`. Changed, missing,
extra, linked or hard-linked files, unsafe paths, duplicate manifest keys, a
foreign/changed schema, bad hashes, invalid SQLite pages and broken foreign keys
are refused. Restore verifies before creating output, rechecks the selected
snapshot while copying, then checks the new file's bytes and integrity.

The size limit is **64 MiB** per database and **16 KiB** per manifest. The SQLite
backup loop has a 15-second progress budget; this is not a hard deadline for every
filesystem or integrity operation. Only stopped **DELETE-journal** databases are
supported. WAL/SHM/journal sidecars cause refusal, even if empty. Keep them intact;
reopen with the originating app and stop normally. No checkpoint, mode conversion,
schema migration or automatic repair is performed by maintenance commands.

Workfloor's persistent `.workfloor.lock` is a one-byte coordination file. The
OS releases ownership after normal exit or process termination. **Never delete
the guard to bypass another process.** The guard protects v0.3 entry points, not
older releases or unrelated SQLite clients. Stop those manually as well. An idle
older app cannot be reliably detected by a SQLite transaction probe.

## Recovery walkthrough

The reproducible synthetic case uses a fresh workspace:

```text
python scripts/verify_recovery.py --workspace ABSOLUTE_NEW_PRIVATE_WORKSPACE
```

It runs actual loopback HTTP and maintenance CLI calls. It first saves the
9-order / 4-delayed report and backs up the baseline. Then it imports the three
invented CSV orders, obtains 12 orders / 6 delayed, saves a second snapshot and
backs up the imported state. It restores both backups into different new
directories, checks all four tables and the exact HTTP bytes of both saved
reports, and proves the original imported database remains unchanged. A corrupted
backup, a running server and an existing destination are deliberately refused.

The workspace contains private databases, backup copies and `recovery-case.json`.
Only that fixed synthetic-result receipt is suitable for deliberate public review;
do not publish the workspace. See [the recorded case](../examples/recovery-case.json).

## Limits and rationale

Checksums detect disagreement with a manifest; they do not authenticate an author.
Anyone able to replace both backup and manifest can replace the content. This
does not encrypt backups, copy external files, undo an import in place or provide
remote disaster recovery. Windows inherits directory ACLs; POSIX requests private
creation modes. Backups may include private work if you put it in the application.

Use stable trusted local paths. Observed links and file changes are refused, but
this is not a hostile-filesystem race sandbox. Network/cloud-synced drives,
adversarial concurrent writers, calibrated durability and power-loss behavior
remain unqualified. SQLite's [copying cautions](https://www.sqlite.org/howtocorrupt.html)
explain why a live raw file copy is inappropriate. Its
[integrity-check documentation](https://www.sqlite.org/pragma.html#pragma_integrity_check)
also distinguishes structural integrity from foreign-key validation.
