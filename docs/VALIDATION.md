# Workfloor 0.3 validation

Local Windows, Python 3.12.7: **59 tests discovered, 58 passed, one skipped**.
The skip is native symlink creation, which this account cannot perform. The
hard-link case passed with native filesystem access. The initial sandbox denied
creating that test hard link; the native rerun passed without weakening the test.
The 39 prior reporting/import/HTTP cases remain, plus 20 recovery cases.

Recovery cases exercise snapshot values and exact saved payload text, original
source preservation, baseline restore after an import, owner/server exclusion,
process-termination lock release, existing/nested destinations, relative/missing
parent paths, altered/truncated/extra/missing members, duplicate/unsafe manifests,
schema mismatch despite a recomputed checksum, foreign keys, WAL/sidecar refusal,
WAL-marked snapshots even with a recomputed manifest, active SQLite transactions, an injected output failure, size bounds and linked files.

`scripts/verify_recovery.py` additionally uses real loopback HTTP and subprocess
CLI calls. Its eight checks cover the full original -> import -> baseline restore
and imported restore case. It verifies all four tables, exact response bytes for
both saved reports, matching restored CLI reports and an unchanged original.
[The reviewed numeric receipt](../examples/recovery-case.json) contains only
invented-result counts and fixed check identifiers, without paths, timestamps,
tokens, report IDs or database files.

## Fresh downloaded package

[Recovery/release CI](https://github.com/TheOutlandsDev/workfloor/actions/workflows/recovery-release.yml)
builds only an explicit committed source allowlist, checks every ZIP member, then
runs all tests, CLI/launcher checks and the complete recovery case from a new
extracted directory containing spaces. Windows and Ubuntu use Python 3.12/3.13;
all four package/checksum outputs must match before main can publish a new release.
See the actual completed Actions result for the selected source revision.

On Windows the existing batch launcher and Python CLI must produce identical
fresh-database reports. Linux checks the Python CLI; it does not run the Windows
batch file. No third-party packages are needed for these checks. Synthetic private
test/backup outputs remain outside the release allowlist.

## Separate browser evidence

The existing [Windows browser workflow](https://github.com/TheOutlandsDev/workfloor/actions/workflows/verify.yml)
continues to check the CSV/report app and read-only sample viewer with separate
locked development dependencies. Those browser checks do not cover the new
maintenance CLI. No fresh local interactive visual acceptance was performed
because Browser access was disabled. Earlier screenshots, walkthrough and static
sample JSON retain v0.2 provenance; they were not relabeled as v0.3 captures.
See [historical v0.2 validation](VALIDATION-v0.2.0.md).

## Practical limits

These tests show functional behavior on existing Windows hosts and the specified
CI runners; they are not a clean-OS installation or power-loss certification.
The guard coordinates v0.3 entry points, not idle older apps or unrelated database
tools. Manually stop those too. A transaction probe is not universal process
detection. File checks detect observed changes and links but do not establish
hostile concurrent-writer isolation. Network/cloud-synced drives, macOS, public
backend hosting, multi-user use, cryptographic authenticity, encryption, employer
systems and live manufacturing integration remain outside this release.

Restore preserves a verified SQLite snapshot in a new directory. It does not
automatically switch the app, undo an import in place, restore separately saved
CSV/receipt files, migrate a schema or repair corruption. Follow
[RECOVERY.md](RECOVERY.md), keeping originals and failed new output for inspection.
