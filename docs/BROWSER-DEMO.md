# Explore sample reports

[Open the no-install viewer](https://connor-oshea-outlands.thatrobotguy.chatgpt.site/demos/workfloor/) · [Viewer source](../demo/)

This static, read-only browser adaptation displays actual JSON downloads captured from the tested Workfloor v0.2.0 application. All manufacturing records were invented for the public project. It has no database, upload endpoint or SQL engine. The full local application remains the place to preview/import CSVs, execute reports and save snapshots.

Select the baseline or post-import export; filter delayed/review/on-time orders; inspect raw source evidence; compare the 9-order/4-delayed baseline with 12 orders/6 delayed after import; inspect the recorded correct and deliberately incorrect SQL; download the selected report or import receipt. The viewer explicitly labels recorded validation and checks that date bounds, definition and SQL agree before presenting the comparison.

## Provenance

The three files in [demo/data](../demo/data/) are actual browser downloads from the application test: `baseline.json`, `after-import.json`, and `receipt.json`. The [provenance record](../demo/data/provenance.json) lists their SHA-256 hashes, capture time, runtime versions, original CSV hash and runtime source-file hashes. Runtime code and fixtures matched the published v0.2.0 tag at capture. The test reopened the earlier saved report after reload and confirmed the downloaded JSON was byte-identical.

This preserves one verified capture. New CI runs create their own temporary snapshots/IDs/times and retain them as artifacts; they do not silently regenerate the published samples. To deliberately refresh them from a successful local application-test run:

```console
python scripts/refresh_demo_exports.py .test-tmp/browser-artifacts/csv-workflow-RUN_ID
```

The helper requires a successful receipt/byte-identity check, validates downloaded hashes, and refuses runtime files that differ from v0.2.0. It copies only those three downloads and a new provenance record. Review the result and rerun the viewer check before publishing. The portfolio serves byte-identical copies of the eight files under `demo/`; it does not load private local data.

For a local static preview, run `python -m http.server 8000 --bind 127.0.0.1 --directory demo`, then open `http://127.0.0.1:8000/`. JSON fetching needs HTTP; opening the HTML directly as a file is unsupported. The viewer uses plain HTML/CSS/JavaScript, without package dependencies or external services.

## Limits

The selected filter changes only the visible table; metric cards retain the selected export's full cohort totals. The SQL and reference results are recorded evidence, not calculations performed in this viewer. The comparison is illustrative, with three new synthetic orders, not a forecasting or capacity model. A saved report is not a database backup. Source hashing identifies bytes; it does not authenticate manufacturing evidence.
