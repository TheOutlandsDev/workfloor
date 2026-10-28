# Workfloor 0.4 validation

The local native Windows / Python 3.12.7 suite discovers **79 tests**: 78 pass
and one symlink-creation case is skipped because the account lacks that privilege.
The hard-link case requires native filesystem access and passes there.

The 20 new cases cover committed history/HTTP bytes, rollback after receipt
insertion, refusal of stale/invalid imports, retained older receipts, latest-50
listing, backup/restore, explicit schema migration, backup/verification failures,
DDL rollback, source changes after backup, active ownership and strict same-commit
release evidence. The previous 59 reporting/import/recovery cases remain.

The [ten-check numeric case](../examples/import-history-case.json) uses original
invented schema-1 data, the actual migration CLI, real loopback HTTP and a separate
Python process. It proves preserved old table values and snapshot bytes, no
fabricated earlier receipts, atomic import+history, identical receipt bytes after
server restart/new process/database restore, and rollback of an entire import on
an injected receipt INSERT failure. The old v0.3.1 recovery code separately verified
the generated schema-1 pre-upgrade backup. Raw private case folders are excluded.

## Extracted packages and CI

The [four-platform workflow](https://github.com/TheOutlandsDev/workfloor/actions/workflows/recovery-release.yml)
builds an explicit committed inventory on Windows/Ubuntu with Python 3.12/3.13.
Each extracts into a fresh path with spaces, reruns the full suite, CLI/Windows
launcher checks, eight recovery checks against five current tables and ten import
history checks. All package bytes must match. A main run can reuse only complete
successful same-commit canonical push evidence; the publisher rechecks job results,
all four assets, checksums, source manifest and each raw committed source member.
Use the completed Actions result at the exact release commit for hosted evidence.

## Browser scope

The [Windows browser workflow](https://github.com/TheOutlandsDev/workfloor/actions/workflows/verify.yml)
checks three cases with locked developer-only dependencies: original report/CSV
workflow, frozen read-only viewer, and persisted receipt view/download after server
restart and restored database. These tests are distinct from local visual review.
Browser access is disabled locally; no new local interactive acceptance is claimed.
Earlier media, static exports and [v0.2 evidence](VALIDATION-v0.2.0.md) keep their
original provenance. See [browser reproduction](BROWSER-CHECKS.md).

## Boundaries

Functional tests are not clean-OS installation, hostile filesystem isolation,
cryptographic authenticity or power-loss certification. The owner guard coordinates
current entry points; unrelated tools and idle older releases must be stopped
manually. Only trusted local DELETE-journal databases up to 64 MiB are supported.
There is no employer/MES integration, general migration engine or multi-user service.
Backup/restore preserves SQLite, not separately saved CSV or downloaded files.
Migration preserves a verified old-format backup before changing the original.


Patch 0.4.1 changes receipt text/background styles and stale display labels only.
The hosted receipt workflow also checks the rendered foreground/background contrast
before accepting the dialog. This focused check is not an accessibility-conformance claim.
