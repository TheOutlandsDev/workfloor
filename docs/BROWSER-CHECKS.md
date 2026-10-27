# Browser verification

Current source has two Chromium tests alongside the 39 standard-library backend tests. The application still runs without pip packages. Browser tooling is a separate development environment, qualified here on Windows x64 with CPython 3.12.

## Reproduce

From a current source checkout on Windows:

```console
python -m venv .browser-venv
.browser-venv\Scripts\python.exe -m pip install --require-hashes --only-binary=:all: -r requirements-browser-windows.txt
.browser-venv\Scripts\python.exe scripts\run_browser_checks.py --install-browser
```

The lock file pins Playwright 1.64.1 and all transitive wheels with SHA-256 hashes. It is specific to Windows x64 / CPython 3.12. The runner installs the Chromium build required by that pinned Playwright package into `.test-tmp/playwright-browsers`, and confines browser temporary files to the checkout. Later runs can omit `--install-browser`. `--pattern test_workflow.py` or `--pattern test_demo.py` selects one test. No browser profile or operational database is reused.

If this machine's redirected temporary directory blocks venv creation, set that terminal's `TEMP` and `TMP` to a writable checkout-local directory before creating the environment. Do not change system-wide settings.

## What the two tests establish

1. **Application workflow:** start a real loopback server with fresh synthetic SQLite data; save/download a 9-order, 4-delayed baseline; reject the entire invalid CSV; preview a BOM/CRLF file; replace it and require another confirmation/preview; import the original valid CSV; assert 12 orders / 440 units / 6 delayed and reference agreement; download/parse the receipt and verify its original CSV hash, before/after fingerprints, three IDs and two completion events; save/download the new result; reload the page; reopen and download the old snapshot with identical JSON and identical bytes; return to the 12-order current report.
2. **Read-only viewer:** verify frozen export hashes against provenance and the original CSV hash; filter the baseline; inspect raw replay records; select the post-import report; use the recorded SQL tabs by keyboard; check the before/after comparison; download the selected JSON; confirm there are no upload/save controls and no page overflow at 390 and 320 px.

Local qualification: Windows 11, Python 3.12.7, SQLite 3.45.3, Playwright 1.64.1, Chromium 156.0.8078.4. Both tests use the application's normal UI and real downloads. The application test checks page reload, not server-process restart. The earlier manual restart is recorded separately in [VALIDATION.md](VALIDATION.md). Phone widths are emulation; accessibility conformance, physical phones, other browsers/platforms, power-loss recovery and production use remain unqualified.

## CI evidence and failures

The Windows [workflow](../.github/workflows/verify.yml) runs backend tests, both CLI/launcher entry points and both browser tests on every push/PR. A `browser-verification-windows` artifact is kept for **14 days**. Each test writes a `verification.json` with runtime versions, phase and assertions; successful application checks also retain their synthetic report/receipt downloads. The viewer test retains its selected sample download.

On failure, the recording block adds a full-page screenshot and Playwright action trace. Traces include screenshots and action timing, with **network, DOM, source and accessibility snapshots disabled**. Before retention, each trace is scanned for the server's process-scoped token; a match moves it outside the upload path and records that it was withheld. Only `.test-tmp/browser-artifacts/` is uploaded. Databases, browser profiles, dependency caches and withheld traces are outside it. The workflow has read-only repository permissions.

An intentional local failure verified the screenshot and trace paths, empty network payloads and runtime-token check. To repeat that collector probe in a disposable local run, set the process environment variable `WORKFLOOR_BROWSER_PROBE=1` and run `--pattern test_workflow.py`; **exit code 1 is expected**. Remove the variable before a normal run. CI does not enable the probe. Startup failures record what is available; they may occur before a screenshot/trace can be captured.

These checks are developer tooling added after v0.2.0. The release ZIP/tag and application runtime code remain unchanged. See [sample export provenance](BROWSER-DEMO.md) for the no-install portfolio viewer.
