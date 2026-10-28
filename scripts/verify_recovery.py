"""Reproduce original data -> CSV import -> verified recovery using invented data."""
import argparse
from contextlib import closing, contextmanager
import hashlib
import http.client
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app
import ownership
import recovery
import workbench as wb

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

@contextmanager
def server(data):
    with app.make_server(data / recovery.DB_NAME) as instance:
        worker = threading.Thread(target=instance.serve_forever, kwargs={'poll_interval': .05})
        worker.start()
        def request(route, payload=None):
            connection = http.client.HTTPConnection('127.0.0.1', instance.server_port, timeout=5)
            try:
                headers = {'Content-Type': 'application/json', 'X-Workbench-Token': instance.token, 'Origin': 'http://' + instance.authority}
                connection.request('POST' if payload is not None else 'GET', route, body=json.dumps(payload) if payload is not None else None, headers=headers)
                result = connection.getresponse(); raw = result.read()
                return result.status, json.loads(raw), raw
            finally: connection.close()
        try: yield request
        finally: instance.shutdown(); worker.join(timeout=10); assert not worker.is_alive()

def cli(command, expected=0):
    result = subprocess.run([sys.executable, '-B', *map(str, command)], cwd=ROOT, capture_output=True, text=True, timeout=30)
    if result.returncode != expected: raise AssertionError('CLI did not complete with expected status; private outputs retained.')
    return json.loads(result.stdout) if expected == 0 else None

def report(request):
    status, value, _ = request('/api/report?start=' + wb.DEFAULT_START + '&end=' + wb.DEFAULT_END)
    assert status == 200 and value['validation']['correct_matches_reference']; return value

def save(request, value):
    status, saved, _ = request('/api/reports', dict(start=wb.DEFAULT_START, end=wb.DEFAULT_END, dataset_sha256=value['dataset_sha256']))
    assert status == 201
    status, _, raw = request('/api/reports/' + saved['run_id']); assert status == 200
    return saved['run_id'], raw

def table_rows(path):
    with closing(sqlite3.connect(path)) as con:
        return {t: con.execute('SELECT * FROM ' + t + ' ORDER BY rowid').fetchall() for t in recovery.TABLES}

def run(workspace):
    workspace = ownership.plain_path(workspace); workspace.mkdir()
    data = workspace / 'original-data'; wb.ensure_database(data / recovery.DB_NAME)
    before_backup = workspace / 'baseline-backup'; after_backup = workspace / 'imported-backup'
    checks = []
    with server(data) as request:
        baseline = report(request); assert baseline['metrics']['orders'] == 9
        old_id, old_bytes = save(request, baseline)
        cli([ROOT / 'recovery.py', 'backup', '--data-dir', data, '--output', workspace / 'blocked-live-backup'], expected=2)
        assert not (workspace / 'blocked-live-backup').exists(); checks.append('running_backup_refused')
    original = sha(data / recovery.DB_NAME)
    cli([ROOT / 'recovery.py', 'backup', '--data-dir', data, '--output', before_backup])
    cli([ROOT / 'recovery.py', 'verify', '--backup', before_backup]); assert sha(data / recovery.DB_NAME) == original
    checks.append('baseline_backup_verified_without_source_changes')
    with server(data) as request:
        text = (ROOT / 'examples/import-valid.csv').read_text(encoding='utf-8')
        status, preview, _ = request('/api/imports/preview', dict(csv_text=text, synthetic=True)); assert status == 200 and preview['can_import']
        status, receipt, _ = request('/api/imports/apply', dict(csv_text=text, synthetic=True, dataset_sha256=preview['dataset_sha256'], preview_token=preview['preview_token']))
        assert status == 201 and receipt['orders_added'] == 3 and receipt['completion_events_added'] == 2
        imported = report(request); assert imported['metrics']['orders'] == 12 and imported['metrics']['delayed'] == 6
        assert request('/api/reports/' + old_id)[2] == old_bytes
        new_id, new_bytes = save(request, imported)
    post_bytes = sha(data / recovery.DB_NAME); expected_rows = table_rows(data / recovery.DB_NAME)
    manifest = cli([ROOT / 'recovery.py', 'backup', '--data-dir', data, '--output', after_backup])
    cli([ROOT / 'recovery.py', 'verify', '--backup', after_backup]); assert sha(data / recovery.DB_NAME) == post_bytes
    checks.append('imported_records_and_both_snapshots_backed_up')
    damaged = workspace / 'damaged-backup'; shutil.copytree(after_backup, damaged)
    with (damaged / recovery.DB_NAME).open('r+b') as stream: stream.seek(100); stream.write(b'fictional corruption')
    cli([ROOT / 'recovery.py', 'verify', '--backup', damaged], expected=2)
    cli([ROOT / 'recovery.py', 'restore', '--backup', damaged, '--data-dir', workspace / 'refused-restore'], expected=2)
    assert not (workspace / 'refused-restore').exists(); checks.append('corrupt_backup_refused_before_restore')
    restored_before = workspace / 'baseline-restored'; restored_after = workspace / 'imported-restored'
    for backup, target in ((before_backup, restored_before), (after_backup, restored_after)):
        cli([ROOT / 'recovery.py', 'restore', '--backup', backup, '--data-dir', target])
        assert (backup / recovery.DB_NAME).read_bytes() == (target / recovery.DB_NAME).read_bytes()
    assert table_rows(restored_after / recovery.DB_NAME) == expected_rows; checks.append('all_four_tables_preserved')
    preserved = sha(restored_after / recovery.DB_NAME)
    cli([ROOT / 'recovery.py', 'restore', '--backup', after_backup, '--data-dir', restored_after], expected=2)
    assert sha(restored_after / recovery.DB_NAME) == preserved; checks.append('existing_restore_destination_preserved')
    with server(restored_after) as request:
        assert report(request) == imported
        assert request('/api/reports/' + old_id)[2] == old_bytes
        assert request('/api/reports/' + new_id)[2] == new_bytes
    checks.append('restored_http_reports_and_snapshot_bytes_match')
    before = cli([ROOT / 'app.py', '--demo-report', '--data-dir', restored_before])
    after = cli([ROOT / 'app.py', '--demo-report', '--data-dir', restored_after])
    assert before['metrics'] == baseline['metrics'] and after['metrics'] == imported['metrics']
    assert sha(data / recovery.DB_NAME) == post_bytes; checks.append('restored_cli_reports_match_and_original_is_unchanged')
    result = dict(schema=1, app='Workfloor', version=wb.VERSION, status='PASS', synthetic_only=True,
                  evidence='Real CLI and loopback HTTP; no browser interaction',
                  stages=[dict(stage='original', metrics=baseline['metrics']), dict(stage='after_import', metrics=imported['metrics']),
                          dict(stage='restored_baseline', metrics=before['metrics']), dict(stage='restored_imported', metrics=after['metrics'])],
                  imported_orders=3, imported_events=2, saved_snapshots=2,
                  restored_table_counts=manifest['database']['tables'], checks=checks)
    (workspace / 'recovery-case.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--workspace', type=Path, required=True)
    try: run(parser.parse_args().workspace)
    except Exception:
        print('Recovery acceptance failed; private new files retained. No database, token or raw log is printed.', file=sys.stderr)
        raise SystemExit(1)
