# v0.4 public source review

The target is TheOutlandsDev/workfloor and a new immutable v0.4.0 source release.
New original code covers durable receipts, explicit backed-up schema upgrade,
synthetic tests and reproducible CLI/HTTP evidence. No employer source, schema,
records or private operational system was consulted.

scripts/build_release.py contains the literal approved file inventory. It includes
source, synthetic fixtures, documentation, tests, license and unchanged historical
public captures. It excludes runtime/dependencies, databases, backups, guard files,
logs, private workspaces and one-time v0.3.1 promotion helpers. The old root manifest
and checksums remain historical; the new ZIP gets SOURCE-MANIFEST.json and attached
release-receipt.json / SHA256SUMS.txt pinned to the exact committed source.

The new numeric case has fixed synthetic counts/check identifiers and a public
sample CSV hash. It omits raw receipt IDs/times, machine paths, secrets, logs and
database bytes. Receipt downloads from real use should remain private. Historical
notes/validation retain explicit versioned filenames; old tags/assets stay unchanged.

Review covers the staged inventory, text/privacy findings, source parsing and
relative links, unit checks, fresh ZIP extraction/acceptance and hosted Windows
browser checks. Published assets are compared against a local build from their
exact source commit. Checksums detect differences, not authenticity or authorship.
