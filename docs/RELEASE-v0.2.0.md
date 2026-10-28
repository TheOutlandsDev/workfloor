# Workfloor v0.2.0 — CSV preview and transactional imports

[Download v0.2.0](https://github.com/TheOutlandsDev/workfloor/releases/tag/v0.2.0) · [CSV workflow](IMPORTS.md) · [Validation](VALIDATION.md)

A Windows-checked local prototype using original invented manufacturing data. Python 3.12+ and its standard SQLite module are required; no package installation or account is needed.

v0.2 adds UTF-8 CSV preview, row-level validation, insert-only imports in one transaction, exact-file/source preview checks, sample files and a downloadable import receipt. Existing source rows and saved snapshot payloads are retained. Database format remains 1, so an existing v0.1 database needs no schema migration.

The fresh baseline remains 9 orders / 365 units / 4 delayed, with a deliberate 26-versus-9 join error. Applying the included three-order sample produces 12 orders / 440 units / 6 delayed. The earlier saved baseline remains unchanged.

**39 automated tests passed locally**, with no skips. Both fresh-database command-line entry points passed. The import/file-picker/report/reopen browser workflow was observed separately. CI repeats backend and entry-point checks on pushes and pull requests; its per-commit result is public.

Use the attached workfloor-0.2.0.zip and SHA256SUMS.txt. The ZIP contains this source tree and its member SHA-256 manifest, without Git metadata, databases, runtime logs, credentials or private material. Extract into a new directory, then run Python app.py or start-workfloor.cmd. Choose a separate data directory for independent experiments.

The original [v0.1.0 release](https://github.com/TheOutlandsDev/workfloor/releases/tag/v0.1.0), [release notes](RELEASE-v0.1.0.md) and original checksum remain available unchanged. The older 80-second video documents reporting and snapshots in v0.1; v0.2 CSV behavior is documented with actual captures in IMPORTS.md.

This remains an insert-only, loopback-only synthetic demonstration. There is no MES integration, undo-import UI, authentication, multi-user service or qualified Linux/macOS runtime. See the validation record for the observed result and limits.
