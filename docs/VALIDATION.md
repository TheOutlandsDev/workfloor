# Validation record — 26 October 2026

## Environment and automated result

- Windows 11, Python **3.12.7**, SQLite **3.45.3**.
- `python -m unittest discover -s tests -v`: **21 tests passed**, no skips; final run 3.409 seconds.
- `node --check static/app.js`: passed. Node is a development check only, not an application requirement.
- The CLI report executed against a newly created database and returned the expected fixture result.

The tests use real SQLite files and loopback HTTP servers. They cover manually authored expected results, due-time and completion boundaries, exact replays vs conflicting timestamps, unknown/missing data, empty ranges, invalid dates and injection-like input, unchanged source reads, snapshot reopening, stale-save refusal, insert-failure rollback, existing foreign-database preservation, source timestamp rejection, relational constraints, local HTTP reads/writes, Host/Origin/token checks and the static asset allowlist.

An initial run could not use the desktop sandbox's redirected OS temp directory. Disposable fixtures were moved to the checkout-local `.test-tmp` directory. A test setup connection was also explicitly closed to release its Windows file handle before cleanup. Neither failure was counted as a passing application test. The final complete run passed.

## Automatic verification

The [first GitHub Actions run](https://github.com/TheOutlandsDev/workfloor/actions/runs/40407181415) completed successfully on 26 October 2026 at source commit `f645e9a0200020ff356f3f891be931aa933ef7d8`. Its Windows Server 2025 runner used Python 3.12.10 and SQLite 3.49.1. All **21 existing tests passed**, with no skips, in 3.362 seconds. The fresh-database entry-point check also passed for both the Python CLI and Windows batch launcher; their complete reports were identical. The README badge was added after this successful run.

The [workflow](../.github/workflows/verify.yml) runs on push, pull request and manual dispatch. It has read-only repository permissions and pins the checkout/setup actions to full commit IDs. The [entry-point script](../scripts/verify_entry_points.py) creates two separate disposable databases in checkout-local directories with spaces, runs from outside the project working directory, and checks the expected totals, reference agreement and intentional join inflation. It runs the launcher with `--demo-report`; it does not automate a browser or qualify other operating systems. No application dependencies are installed.

The [80-second walkthrough](WALKTHROUGH.md) documents another actual browser session with invented data. It shows the delayed filter, replay evidence, 26-versus-9 validation, both SQL tabs, a snapshot save, and the preserved snapshot after interrupting and restarting the app. It is an edited sequence of real application captures with captions, rather than continuous screen recording. The interruption's exit code was 1; it is not graceful-shutdown or power-loss evidence.

## Observed result

For `[2026-10-01T00:00:00Z, 2026-10-08T00:00:00Z)`:

| Measure | Observed |
| --- | ---: |
| Work orders | 9 |
| Units represented by those orders | 365 |
| Delayed | 4 |
| Completed late / open at cutoff | 1 / 3 |
| Needs review | 2 |
| Completed on time | 3 |
| Naïve joined rows / units | 26 / 1,195 |
| Inflated row count detected | +17 |

## Browser workflow

The actual Python application was opened in the in-app browser on Windows. Its default report and validation messages matched the backend result. Observed checks included:

- Delayed filter displayed exactly four orders.
- Conflicting-event inspector showed both `EV-11` timestamps and the review explanation.
- Empty November range displayed a clear empty state and did not label the naïve query correct.
- Reversed date range displayed a validation error and disabled saving the changed range.
- Both SQL tabs displayed the corresponding source query and bound values.
- A snapshot was saved through the UI, reopened, exported as JSON, and checked for the expected metrics and validation result.
- The owned server process was interrupted and restarted with the same database. It reported reopening the database; the browser still listed and reopened the same saved snapshot. The tool interruption returned exit code 1, so this is persistence-after-interruption evidence, not proof of graceful shutdown or power-loss recovery.
- Desktop layout and 390-pixel phone layout were inspected. The hidden table heading initially caused page overflow at phone width; its containing block was fixed. The order table retained its own horizontal scroll, and a focused-panel arrow key moved it by 40 pixels.

The final 320-pixel layout check also passed: page scroll width equaled its 305-pixel client width. At 390 pixels, both were 375 pixels; at the 1280-pixel desktop breakpoint, both were 1265 pixels. Tables and SQL retain their own scroll regions. Screenshots in `screenshots/` are actual UI captures using invented data. The extracted-release check is recorded in `verification.json`.

The Copy SQL success message was observed, but the browser tool's separate clipboard view did not reflect the page's clipboard write. Copied clipboard bytes are not independently verified by this check.

## Limits of the check

Browser emulation is not physical-phone testing. The test set is bounded synthetic evidence rather than production qualification. Linux/macOS execution, public hosting, multi-user access, accessibility conformance, independent security review, large data, power-loss recovery and long-running operation were not tested. No workplace source or system was used.
