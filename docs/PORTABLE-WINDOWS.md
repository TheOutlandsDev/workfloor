# Workfloor 0.4.1 — portable Windows x64, package 1

Download `workfloor-0.4.1-windows-x64.zip` and `SHA256SUMS.txt` from this release.
Extract All into a new local folder, then **double-click Workfloor.cmd**. Your
browser opens the local report. Keep the console open; press Ctrl+C there to stop.
No Python installation, terminal command, pip, administrator rights or PATH change
is required for the ordinary first launch. A current browser is required.

The default private database lives under `%LOCALAPPDATA%\Outlands\Workfloor\data`,
outside the extracted app. Relaunching reopens it. A second running instance is
refused. Older source-download data is not searched for, moved, reset or upgraded
automatically. Keep data and backups private. Replacing the extracted application
does not delete its external database.

## One useful workflow

Keep the default dates, 2026-10-01 through before 2026-10-08. Expect **9 orders /
365 units / 4 delayed**; the deliberate bad join counts **26 rows / 1,195 units**.
Save a snapshot. Load the valid fictional CSV, preview, then import: expect
**12 orders / 440 units / 6 delayed**. Stop and relaunch; the import receipt and
the older snapshot remain available.

The extracted `START-HERE.txt` gives explicit backup, verify, fresh-directory
restore and legacy-upgrade commands using the bundled runtime. These advanced
maintenance steps use a terminal and require the server to be stopped. There is
no automatic overwrite, deletion or migration. Report exports are not backups.

## What is included

- The unchanged reviewed Workfloor **0.4.1** source at
  `6a7a02ade5b01e1a6fc76f6e87a40ac7d2c24af6`, with its original source manifest.
- Official CPython **3.14.10** Windows x64 embeddable runtime, pinned to upstream
  SHA-256 `90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159`.
  All binaries and license files remain exact. Only `python314._pth` adds the
  sibling application folder; automatic site imports remain disabled.
- The original launcher, offline instructions, third-party notices and exact
  package-member hashes. Runtime, source and packaging revisions are separate.

The runtime comes from [Python's official release](https://www.python.org/downloads/release/python-31410/).
Python documents this [application-local distribution](https://docs.python.org/3.14/using/windows.html#the-embeddable-package).
No installer, browser, pip, employer material, credentials or user data is bundled.
The prior cross-platform source ZIP and its release assets remain unchanged.

## Qualification and boundaries

The portable workflow builds on Windows and Ubuntu and requires identical archive
bytes. Windows acceptance runs the extracted original core suite under the bundled
Python, then launches through Workfloor.cmd from a different working directory
with spaces, PATH restricted to Windows system directories, and invalid
PYTHONHOME/PYTHONPATH values. It checks default external storage, ordinary reports,
the join error, transactional import, historical snapshot/receipt bytes after a
real process restart, stopped backup/restore, existing-target refusal and explicit
schema-1 upgrade with a verified original backup. Package files must remain exact.

A separate Chromium test connects to a real bundled-runtime process and checks
invalid/valid CSV, snapshots, restart and restored receipt downloads. Browser test
dependencies are not included in the user package. The public acceptance JSON
contains only counts and check outcomes; raw logs, tokens, runtime files and
generated databases are not uploaded. A skipped native fixture remains a skip.

These are fresh hosted Windows runner and interpreter-isolation checks. Hosted
runners have other installed software; this does **not** establish a manual test
on a PC with Python absent, Explorer double-click acceptance, default-browser
integration on every machine or a reputation/signing guarantee. Windows 11 x64 is
the intended desktop; Windows ARM64/32-bit and other operating systems are not
qualified for this portable package. Use the existing source alternative there.

OUTLANDS does not Authenticode-sign the launcher/outer archive. If device policy
or Windows reputation protection blocks it, use the source alternative or consult
the administrator; do not disable protections. No public hosting, production MES,
signed audit log or power-loss durability guarantee is claimed.
