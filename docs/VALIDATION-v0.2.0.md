# v0.2 validation — 26 October 2026

## Current automated checks

Windows 11, Python **3.12.7**, SQLite **3.45.3**.

- All **39 tests passed**, no skips, in 4.257 seconds: the original 21 reporting/HTTP tests plus 18 CSV/import tests.
- Fresh-database entry-point verification passed for both the Python CLI and Windows launcher. Both produced identical default reports from separate data paths containing spaces, outside the project working directory.
- Both browser scripts passed Node syntax checks. Node is a development check only.

The suite exercises real SQLite transactions and loopback HTTP. New checks cover read-only preview (including unchanged database bytes), mixed-validity file rejection, headers and field counts, calendar/UTC validation, duplicates, UTF-8/BOM/quoted text, byte/row limits, exact-file preview binding, changed source, simultaneous applies, failure after a later insert and failure inserting a completion event, old snapshot preservation, and HTTP token/origin/type/size boundaries.

The [workflow](../.github/workflows/verify.yml) runs the full backend suite, entry-point checks and two Chromium browser tests on every push and pull request, with manual dispatch available. It records runner/Python/SQLite versions and uses pinned actions with read-only repository permissions. See [Actions](https://github.com/TheOutlandsDev/workfloor/actions/workflows/verify.yml) for the result attached to each public commit.

## Browser automation added after v0.2.0

Two browser tests passed locally on Windows 11, Python 3.12.7, SQLite 3.45.3 and Chromium 156.0.8078.4 using Playwright 1.64.1. The application test uses the real loopback server and a fresh SQLite database. It verifies invalid-file rejection, BOM/CRLF preview, changed-file invalidation, the valid three-order import, downloaded receipt fields and original CSV SHA-256, the 12-order result, and the earlier 9-order export's byte identity after page reload. The second test checks the static sample viewer and its export provenance, controls, download and 390/320 px layouts. No runtime application code changed.

An intentional local failure also verified screenshot/action-trace collection. Network/DOM snapshots are disabled, the trace is checked for the process token, and a matching trace is withheld from the upload directory. CI retains the scoped browser artifact for 14 days. This automated reload check does not restart the server process; the historical manual interruption check below is separate. See [reproduction and diagnostic scope](BROWSER-CHECKS.md).

## Observed browser workflow

The actual local application was checked in the in-app browser on Windows:

1. Saved baseline snapshot **916d6070…** at **23:16:02 UTC**, showing 9 orders / 365 units / 4 delayed.
2. Loaded the error sample and previewed it. All three records were blocked; row-level validation messages were visible, and Apply was disabled.
3. Selected the valid synthetic CSV through the file picker. Changing files cleared the old preview and required the invented-data confirmation again.
4. Previewed three valid records. The source was unchanged until Apply.
5. Applied them at **23:28:34 UTC**, adding **3 orders / 2 completion events**. The current report refreshed to **12 orders / 440 units / 6 delayed / 2 review / 4 on time**, matching the independent reference. The wrong join returned **29 rows / 1,270 units**.
6. Saved snapshot **31d9bcbf…** at **23:30:19 UTC**. Interrupted/restarted the owned app using the same data directory; it reported reopening the existing database.
7. Reopened the earlier snapshot through the UI: **9 orders / 4 delayed**, labeled SAVED SNAPSHOT, with its original SQL and fingerprint. The current source still contained the imported orders.

The process interruption returned exit code 1. This demonstrates persistence after that interruption, not graceful-shutdown or power-loss recovery.

The error preview initially clipped detailed validation at the right edge of its table. Row-level issue cards were added above the table so errors can be read without horizontal scrolling. Both **390 px (375 px client width)** and **320 px (305 px client width)** matched their page scroll width after the fix; tables retain their own scroll regions. These are browser-emulated layouts, not physical phones.

Actual captures: [valid preview](screenshots/import-valid-preview.jpg), [rejected file](screenshots/import-errors.jpg), [current report after import](screenshots/report-after-import.jpg), [preserved baseline snapshot](screenshots/preserved-snapshot.jpg), [phone layout](screenshots/phone-import.jpg).

In that original manual session, the receipt button was enabled but downloaded receipt bytes were not independently inspected. The newer automated browser check above now downloads and parses the receipt and verifies its CSV hash, source fingerprints, added IDs and report totals.

## Reproduce and inspect

See [CSV format and workflow](IMPORTS.md), [design decisions](DECISIONS.md), and [machine-readable v0.2 record](verification-v0.2.0.json). A new database still reproduces the original **9 orders / 365 units / 4 delayed**, with **26 rows / 1,195 units** in the deliberately wrong join.

The [v0.1 validation record](VALIDATION-v0.1.0.md), [original machine-readable record](verification.json), and [80-second v0.1 reporting walkthrough](WALKTHROUGH.md) remain historical evidence. The video does not demonstrate CSV imports.

## Limits

This is a single-user local prototype using invented records. No employer source, schema or operational records were used. Imports add new orders only, with no updates, deletes, partial-success mode, persistent import-history screen or undo-import UI. Receipts can be downloaded during the browser session. A saved report is not a database backup or a tamper-proof audit log.

The cutoff remains an event-time view over current source, not a reconstruction of historical knowledge. Linux/macOS execution, public backend hosting, multi-user behavior, accessibility conformance, penetration testing, large datasets, power-loss recovery and long-running operation remain unqualified.
