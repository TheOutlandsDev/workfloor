"""Run Workfloor on loopback using Python 3.12+; no installed packages needed."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sqlite3
import sys
from urllib.parse import parse_qs, urlsplit

import workbench as wb
import csv_imports
from ownership import data_lock

ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/imports.js": ("imports.js", "text/javascript; charset=utf-8"),
    "/mark.svg": ("mark.svg", "image/svg+xml"),
}
SAMPLES = {
    "/examples/import-valid.csv": "import-valid.csv",
    "/examples/import-errors.csv": "import-errors.csv",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "Workfloor/0.4"

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, fmt, *args):
        # Routine request bodies, headers and tokens are not logged.
        return

    def respond(self, status, value, content_type="application/json; charset=utf-8", body=True, attachment=None):
        data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if attachment: self.send_header('Content-Disposition', 'attachment; filename="' + attachment + '"')
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.end_headers()
        if body:
            self.wfile.write(data)

    def allowed_host(self):
        if self.headers.get("Host") != self.server.authority:
            self.respond(403, {"error": "Use the loopback URL printed by the server."})
            return False
        return True

    def do_HEAD(self):
        self.do_GET(body=False)

    def do_GET(self, body=True):
        if not self.allowed_host():
            return
        url = urlsplit(self.path)
        try:
            if url.path in ASSETS:
                name, mime = ASSETS[url.path]
                self.respond(200, (wb.ROOT / "static" / name).read_bytes(), mime, body)
            elif url.path in SAMPLES:
                self.respond(200, (wb.ROOT / "examples" / SAMPLES[url.path]).read_bytes(), "text/csv; charset=utf-8", body)
            elif url.path == "/api/meta":
                self.respond(200, {"name": "Workfloor", "version": wb.VERSION,
                                   "synthetic": True, "token": self.server.token,
                                   "default_start": wb.DEFAULT_START, "default_end": wb.DEFAULT_END}, body=body)
            elif url.path == "/api/report":
                query = parse_qs(url.query, keep_blank_values=True)
                if set(query) != {"start", "end"} or any(len(v) != 1 for v in query.values()):
                    raise wb.InputError("Provide exactly one start and end date.")
                self.respond(200, wb.report(self.server.db_path, query["start"][0], query["end"][0]), body=body)
            elif url.path == "/api/reports":
                self.respond(200, {"reports": wb.history(self.server.db_path)}, body=body)
            elif url.path == '/api/imports':
                self.respond(200, {'imports': csv_imports.history(self.server.db_path), 'limit': 50,
                                   'scope': 'Committed imports recorded by v0.4; earlier receipts are not reconstructed.'}, body=body)
            elif url.path.startswith('/api/imports/') and url.path.endswith('/receipt.json'):
                import_id = url.path[len('/api/imports/'):-len('/receipt.json')]
                data = csv_imports.receipt_bytes(self.server.db_path, import_id)
                if data is None: self.respond(404, {'error': 'Import receipt not found.'}, body=body)
                else: self.respond(200, data, body=body, attachment='workfloor-import-' + import_id + '.json')
            elif url.path.startswith("/api/reports/"):
                result = wb.saved_report(self.server.db_path, url.path.removeprefix("/api/reports/"))
                self.respond(200 if result else 404, result or {"error": "Snapshot not found."}, body=body)
            else:
                self.respond(404, {"error": "Not found."}, body=body)
        except wb.InputError as exc:
            self.respond(400, {"error": str(exc)}, body=body)
        except (sqlite3.Error, OSError, ValueError, KeyError, TypeError):
            self.respond(500, {"error": "Could not read the local data. Preserve the database and check the application files."}, body=body)

    def do_POST(self):
        if not self.allowed_host():
            return
        origin = self.headers.get("Origin")
        token = self.headers.get("X-Workbench-Token", "")
        if origin not in (None, "null", "http://" + self.server.authority) or not secrets.compare_digest(token, self.server.token):
            self.respond(403, {"error": "Reload this local application before saving or importing."})
            return
        if self.path not in ("/api/reports", "/api/imports/preview", "/api/imports/apply"):
            self.respond(404, {"error": "Not found."})
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            self.respond(415, {"error": "Use an application/json request."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            limit = 4096 if self.path == "/api/reports" else 2 * 1024 * 1024
            if not 0 < length <= limit:
                self.respond(413, {"error": f"Request must contain 1 to {limit} bytes."})
                return
            payload = json.loads(self.rfile.read(length))
            if self.path == "/api/reports":
                if not isinstance(payload, dict) or set(payload) != {"start", "end", "dataset_sha256"}:
                    raise wb.InputError("Save requires start, end and the loaded dataset fingerprint.")
                result = wb.save_report(self.server.db_path, payload["start"], payload["end"], payload["dataset_sha256"])
                self.respond(201, result)
            else:
                required = {"csv_text", "synthetic"}
                if self.path == "/api/imports/apply":
                    required |= {"dataset_sha256", "preview_token"}
                if not isinstance(payload, dict) or set(payload) != required or payload["synthetic"] is not True:
                    raise wb.InputError("Confirm this original demonstration uses invented data, with the required CSV fields.")
                if self.path == "/api/imports/preview":
                    result = csv_imports.preview(self.server.db_path, payload["csv_text"], self.server.preview_key)
                    self.respond(200, result)
                else:
                    result = csv_imports.apply_import(self.server.db_path, payload["csv_text"],
                        payload["dataset_sha256"], payload["preview_token"], self.server.preview_key)
                    self.respond(201, result)
        except wb.StaleDataError as exc:
            self.respond(409, {"error": str(exc)})
        except (wb.InputError, ValueError, TypeError, UnicodeError) as exc:
            self.respond(400, {"error": str(exc) if isinstance(exc, wb.InputError) else "Invalid JSON request."})
        except (sqlite3.Error, OSError):
            self.respond(503, {"error": "The write could not complete and was rolled back. Existing records and snapshots are retained; check local storage before retrying."})


class WorkfloorServer(ThreadingHTTPServer):
    def __init__(self, path, port, own_lock=True):
        self.owner = data_lock(Path(path).absolute().parent) if own_lock else None
        if self.owner: self.owner.__enter__()
        try: super().__init__(("127.0.0.1", port), Handler)
        except BaseException:
            self.release_owner(); raise

    def release_owner(self):
        if self.owner:
            owner, self.owner = self.owner, None
            owner.__exit__(None, None, None)

    def server_close(self):
        try: super().server_close()
        finally: self.release_owner()


def make_server(path, port=0, *, own_lock=True):
    server = WorkfloorServer(path, port, own_lock)
    server.daemon_threads = False
    server.block_on_close = True
    server.db_path = Path(path)
    server.authority = f"127.0.0.1:{server.server_port}"
    server.token = secrets.token_urlsafe(32)
    server.preview_key = secrets.token_bytes(32)
    return server


def main():
    parser = argparse.ArgumentParser(description="Workfloor: synthetic manufacturing and SQL reporting workbench.")
    parser.add_argument("--data-dir", type=Path, default=wb.ROOT / "data", help="Directory for the persistent SQLite database")
    parser.add_argument("--port", type=int, default=8765, help="Loopback port; use 0 to select a free port")
    parser.add_argument("--demo-report", action="store_true", help="Print the same report as JSON and exit")
    parser.add_argument("--start", default=wb.DEFAULT_START)
    parser.add_argument("--end", default=wb.DEFAULT_END)
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        parser.error("Python 3.12 or newer is required.")
    if not 0 <= args.port <= 65535:
        parser.error("Port must be between 0 and 65535.")
    try:
        with data_lock(args.data_dir, create=True):
            wb.bounds(args.start, args.end)
            db = args.data_dir.resolve() / "workfloor.sqlite3"
            created = wb.ensure_database(db)
            if args.demo_report:
                print(json.dumps(wb.report(db, args.start, args.end), indent=2))
                return
            with make_server(db, args.port, own_lock=False) as server:
                print(f"Workfloor {wb.VERSION} | SYNTHETIC DATA ONLY", flush=True)
                print(f"{'Created' if created else 'Reopened'} local database: {db}", flush=True)
                print(f"Open http://{server.authority}/", flush=True)
                print("Ctrl+C stops the server. Saved snapshots remain in SQLite.", flush=True)
                try:
                    server.serve_forever(poll_interval=0.2)
                except KeyboardInterrupt:
                    pass
                finally:
                    server.server_close()
    except (wb.InputError, sqlite3.Error, OSError) as exc:
        parser.exit(1, f"Could not start Workfloor: {exc}\n")


if __name__ == "__main__":
    main()
