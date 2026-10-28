# Workfloor 0.3.1 - verified offline database recovery

[Download ZIP](https://github.com/TheOutlandsDev/workfloor/releases/download/v0.3.1/workfloor-0.3.1.zip)
· [Recovery guide](https://github.com/TheOutlandsDev/workfloor/blob/v0.3.1/docs/RECOVERY.md)
· [Synthetic case](https://github.com/TheOutlandsDev/workfloor/blob/v0.3.1/examples/recovery-case.json)
· [Platform checks](https://github.com/TheOutlandsDev/workfloor/actions/workflows/recovery-release.yml)

Patch 0.3.1 also checks the stored SQLite header before immutable inspection,
refusing a WAL-marked snapshot even if its manifest checksum was recomputed.
The previously published 0.3.0 release is retained unchanged.

Adds stopped-database backup, checksum/integrity verification and fresh-directory
restore. A shared OS-owned guard prevents concurrent v0.3 server/maintenance use.
SQLite's backup API takes a consistent snapshot; only new output directories are
created. Existing databases, report snapshots and earlier releases are preserved.
The schema remains v1, compatible with the earlier public data format.

The reproducible case saves the original 9-order / 4-delayed report, backs up,
imports three invented orders to obtain 12 orders / 6 delayed, saves a second
snapshot, and backs up again. It restores both states into separate new folders,
checks all four tables and exact saved-report HTTP bytes, and proves the original
imported database is unchanged. It deliberately refuses a running backup,
corruption and an existing restore destination.

## Download and run

Compare the ZIP with SHA256SUMS.txt from the same release, then extract into a
new folder. Install Python 3.12 or 3.13 separately; the runtime app requires no pip
packages, account or network service. Run `python app.py --port 0` or the Windows
`start-workfloor.cmd --port 0` launcher. Stop with Ctrl+C before maintenance.
Use the absolute-path commands in docs/RECOVERY.md to back up, verify and restore.

The ZIP includes reviewed original source, synthetic fixtures, documentation,
tests, licenses and historical public captures. No database, backup, runtime,
real metrics, credentials, logs or employer material is included. SOURCE-MANIFEST.json
records every member's bytes/hash, and release-receipt.json pins the source commit
and outer ZIP hash. Windows/Ubuntu Python 3.12/3.13 independently build, extract,
test and reproduce recovery; matching package/checksum bytes are required before
publication. Existing named releases are never replaced.

## Boundaries

This is a single-user synthetic local prototype. Backups cover SQLite, not CSV
files or browser-downloaded receipts. History snapshots remain reports, not full
database backups. Only stopped DELETE-journal databases up to 64 MiB are supported.
WAL/SHM/journal sidecars are preserved and refused; no automatic repair or mode
conversion occurs. Checksums are not signatures or encryption. Restore never
reverts the original database in place. Stop idle older releases manually: they
do not participate in the new ownership guard.

The new recovery evidence is CLI/HTTP. Local Browser access was disabled, so no
new local interactive visual acceptance is claimed. Existing Windows browser CI
checks run separately; older captures and the static browser demo retain their
v0.2 provenance. macOS, hostile concurrent file changes, network/cloud storage,
multi-user/public hosting, MES integration and power-loss recovery remain unqualified.

See [validation](https://github.com/TheOutlandsDev/workfloor/blob/v0.3.1/docs/VALIDATION.md)
and [recovery decisions](https://github.com/TheOutlandsDev/workfloor/blob/v0.3.1/docs/DECISIONS.md).
