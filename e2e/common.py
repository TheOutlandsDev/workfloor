"""Isolated browser checks. Application runtime dependencies stay unchanged."""
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import platform
import sqlite3
import sys
import tempfile
import threading
import unittest
import uuid
import zipfile

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app
import workbench as wb

BASELINE = {"orders": 9, "units": 365, "delayed": 4, "completed_late": 1,
            "open_overdue": 3, "on_time": 3, "review": 2}
AFTER = {"orders": 12, "units": 440, "delayed": 6, "completed_late": 2,
         "open_overdue": 4, "on_time": 4, "review": 2}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def runtime_hashes():
    names = ["app.py", "workbench.py", "csv_imports.py", "ownership.py", "recovery.py", "fixtures/synthetic.json"]
    names += [p.relative_to(ROOT).as_posix() for folder in ("sql", "static")
              for p in sorted((ROOT / folder).rglob("*")) if p.is_file()]
    return {name: sha(ROOT / name) for name in sorted(names)}


class QuietFiles(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


class BrowserCase(unittest.TestCase):
    case_name = "browser"

    def setUp(self):
        root = (ROOT / ".test-tmp").resolve()
        root.mkdir(exist_ok=True)
        self.run_dir = root / "browser-artifacts" / (self.case_name + "-" + uuid.uuid4().hex[:12])
        self.run_dir.mkdir(parents=True)
        temporary = tempfile.TemporaryDirectory(prefix="browser-session-", dir=root)
        if Path(temporary.name).resolve().parent != root:
            raise RuntimeError("Browser data escaped its checkout-local directory")
        self.temp = Path(temporary.name)
        self.addCleanup(temporary.cleanup)
        self.evidence = {"case": self.case_name, "synthetic_only": True, "status": "running",
                         "python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
                         "platform": platform.platform(), "phase": "browser startup"}
        self.trace_secrets = []
        try:
            self.pw = sync_playwright().start()
            self.addCleanup(self.pw.stop)
            self.browser = self.pw.chromium.launch()
            self.addCleanup(self.browser.close)
            self.context = self.browser.new_context(accept_downloads=True, viewport={"width": 1280, "height": 900},
                                                    reduced_motion="reduce")
            self.addCleanup(self.context.close)
            # Network/DOM snapshots would include process-scoped API tokens.
            # Keep action timing and screenshot evidence without those payloads.
            self.context.tracing.start(screenshots=True, snapshots=False, sources=False, aria_snapshots=False)
            self.page = self.context.new_page()
            self.page.set_default_timeout(10_000)
            self.page.set_default_navigation_timeout(20_000)
            self.console_errors = []
            self.page.on("pageerror", lambda error: self.console_errors.append(str(error)))
            self.evidence["chromium"] = self.browser.version
        except Exception as error:
            self.write_failure(error)
            raise
        print("Browser artifacts:", self.run_dir.relative_to(ROOT), flush=True)

    def serve(self, server):
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05})
        thread.start()
        def stop():
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            if thread.is_alive():
                raise RuntimeError("The browser-test HTTP server did not stop")
        self.addCleanup(stop)
        return "http://127.0.0.1:" + str(server.server_port)

    def serve_app(self):
        database = self.temp / "fresh data" / "workfloor.sqlite3"
        wb.ensure_database(database)
        server = app.make_server(database)
        self.trace_secrets.append(server.token.encode())
        return self.serve(server)

    def serve_demo(self):
        return self.serve(ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietFiles, directory=str(ROOT / "demo"))))

    def write_failure(self, error):
        self.evidence.update(status="failed", error_type=type(error).__name__, error=str(error))
        (self.run_dir / "verification.json").write_text(json.dumps(self.evidence, indent=2) + "\n", encoding="utf-8")

    @contextmanager
    def recording(self):
        try:
            yield
            self.assertEqual(self.console_errors, [], "Browser JavaScript raised an error")
        except BaseException as error:
            diagnostics = []
            try:
                self.page.screenshot(path=str(self.run_dir / "failure.png"), full_page=True)
            except Exception as diagnostic:
                diagnostics.append("Screenshot unavailable: " + type(diagnostic).__name__)
            try:
                self.context.tracing.stop(path=str(self.run_dir / "trace.zip"))
                with zipfile.ZipFile(self.run_dir / "trace.zip") as trace:
                    contains_secret = any(secret in trace.read(name) for name in trace.namelist()
                                          for secret in self.trace_secrets)
                if contains_secret:
                    private = ROOT / ".test-tmp" / "private-browser-traces"
                    private.mkdir(exist_ok=True)
                    (self.run_dir / "trace.zip").rename(private / (self.run_dir.name + ".zip"))
                    diagnostics.append("Trace retained privately and withheld from artifacts: runtime token found")
            except Exception as diagnostic:
                diagnostics.append("Trace unavailable: " + type(diagnostic).__name__)
            self.evidence["diagnostic_errors"] = diagnostics
            self.write_failure(error)
            raise
        else:
            self.context.tracing.stop()
            self.evidence.update(status="passed", finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
            (self.run_dir / "verification.json").write_text(json.dumps(self.evidence, indent=2) + "\n", encoding="utf-8")

    def download_json(self, button, filename):
        with self.page.expect_download() as pending:
            button.click()
        download = pending.value
        self.assertIsNone(download.failure())
        destination = self.run_dir / filename
        download.save_as(destination)
        return json.loads(destination.read_text(encoding="utf-8"))

    def phase(self, text):
        self.evidence["phase"] = text
        print("  " + text, flush=True)
