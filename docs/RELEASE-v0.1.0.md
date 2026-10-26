# v0.1.0 — first public release

Workfloor is an original synthetic manufacturing and SQL reporting workbench.
The runtime files were checked locally on Windows before publication. The public
repository adds publication links and this release note; it does not claim that
the app has a hosted backend or a qualified Linux runtime.

## Download and reproduce

Use the attached `workfloor-0.1.0.zip` from the
[GitHub release](https://github.com/TheOutlandsDev/workfloor/releases/tag/v0.1.0).
Its SHA-256 is recorded in `RELEASE-CHECKSUMS.txt`. The ZIP includes its own
member manifest and the original local handoff README. The repository's root
manifest describes the current published source files instead.

Windows 11 / Python 3.12.7 / SQLite 3.45.3: 21 automated tests passed with no
skips. The browser report, conflict inspector, empty/invalid ranges, saved
snapshots, JSON export and snapshot reopening after process restart were checked.
A fresh extraction into a path containing spaces ran through both Python and
the Windows launcher. Details and limits are in `docs/VALIDATION.md` and
`docs/verification.json`; these are recorded results, not a CI badge.

The expected default result is 9 orders, 365 units, 4 delayed, 2 needing review,
and 3 completed on time. The intentionally wrong join yields 26 rows and
1,195 units; validation catches the mismatch. All records are invented.

Screenshots are actual captures of this synthetic local application. No runtime
database, credentials, private operational records or employer material is
included in this release.
