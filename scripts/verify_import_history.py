"""Synthetic legacy upgrade -> durable receipt -> restart -> verified restore."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import csv_imports
import migrate
from ownership import plain_path
import recovery
import workbench as wb
from verify_recovery import cli, report, save, server, table_rows

def legacy_fixture(db):
    db.parent.mkdir()
    data = json.loads((ROOT / 'fixtures/synthetic.json').read_text(encoding='utf-8'))
    with closing(sqlite3.connect(db, autocommit=True)) as con:
        con.executescript((ROOT / 'sql/schema-v1.sql').read_text(encoding='utf-8'))
        con.executemany('INSERT INTO work_orders VALUES (?, ?, ?, ?, ?)', data['orders'])
        con.executemany('INSERT INTO process_steps VALUES (?, ?, ?)', data['steps'])
        con.executemany('INSERT INTO completion_events VALUES (?, ?, ?, ?)', data['events'])
    saved = wb.save_report(db, wb.DEFAULT_START, wb.DEFAULT_END, wb.report(db)['dataset_sha256'])
    saved['version'] = '0.3.1'
    with closing(wb.connect(db)) as con: con.execute('UPDATE report_runs SET payload_json=?', (wb.json_text(saved),))
    return saved['run_id']

def run(workspace):
    workspace = plain_path(workspace); workspace.mkdir()
    data = workspace / 'legacy-data'; db = data / recovery.DB_NAME; old_id = legacy_fixture(db)
    with closing(wb.connect(db)) as con: original = migrate.table_digest(con, recovery.TABLES_V1)
    with server(data) as request: old_bytes = request('/api/reports/' + old_id)[2]
    checks = []
    cli([ROOT / 'app.py', '--demo-report', '--data-dir', data], expected=1)
    checks.append('legacy_startup_refuses_automatic_migration')
    before = workspace / 'verified-v1-backup'
    result = cli([ROOT / 'migrate.py', '--data-dir', data, '--backup-dir', before]); assert result['status'] == 'migrated'
    recovery.verify(before)
    with closing(wb.connect(before / recovery.DB_NAME)) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 1
        assert migrate.table_digest(con, recovery.TABLES_V1) == original
    with closing(wb.connect(db)) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 2
        assert migrate.table_digest(con, recovery.TABLES_V1) == original
    checks.append('verified_v1_backup_precedes_schema_v2')
    assert csv_imports.history(db) == []; checks.append('prior_receipts_not_fabricated')
    text = (ROOT / 'examples/import-valid.csv').read_bytes().decode('utf-8')
    with server(data) as request:
        baseline = report(request); assert baseline['metrics']['orders'] == 9
        status, preview, _ = request('/api/imports/preview', dict(csv_text=text, synthetic=True)); assert status == 200 and preview['can_import']
        status, receipt, _ = request('/api/imports/apply', dict(csv_text=text, synthetic=True, dataset_sha256=preview['dataset_sha256'], preview_token=preview['preview_token']))
        assert status == 201 and receipt['status'] == 'committed' and receipt['orders_added'] == 3
        assert receipt['csv_sha256'] == hashlib.sha256(text.encode()).hexdigest()
        status, history, _ = request('/api/imports'); assert status == 200 and len(history['imports']) == 1
        status, downloaded, receipt_bytes = request('/api/imports/' + receipt['import_id'] + '/receipt.json')
        assert status == 200 and downloaded == receipt
        assert receipt_bytes == (wb.json_text(receipt) + '\n').encode()
        assert request('/api/reports/' + old_id)[2] == old_bytes
        imported = report(request); assert imported['metrics']['orders'] == 12
    checks.append('orders_and_durable_receipt_commit_together')
    (workspace / 'private-receipt.json').write_bytes(receipt_bytes)
    with server(data) as request:
        assert request('/api/imports/' + receipt['import_id'] + '/receipt.json')[2] == receipt_bytes
        assert request('/api/reports/' + old_id)[2] == old_bytes
    checks.append('receipt_bytes_identical_after_server_restart')
    process = subprocess.run([sys.executable, '-B', '-c', 'import csv_imports,sys; sys.stdout.buffer.write(csv_imports.receipt_bytes(sys.argv[1],sys.argv[2]))', str(db), receipt['import_id']], cwd=ROOT, capture_output=True, timeout=30)
    assert process.returncode == 0 and process.stdout == receipt_bytes
    checks.append('receipt_bytes_identical_in_new_process')
    after = workspace / 'verified-v2-backup'; restored = workspace / 'restored-v2'
    cli([ROOT / 'recovery.py', 'backup', '--data-dir', data, '--output', after])
    cli([ROOT / 'recovery.py', 'restore', '--backup', after, '--data-dir', restored])
    assert table_rows(db) == table_rows(restored / recovery.DB_NAME)
    checks.append('all_five_tables_preserved_after_restore')
    with server(restored) as request:
        assert report(request) == imported
        assert request('/api/imports/' + receipt['import_id'] + '/receipt.json')[2] == receipt_bytes
        assert request('/api/reports/' + old_id)[2] == old_bytes
    checks.extend(['receipt_bytes_identical_after_database_restore', 'legacy_snapshot_bytes_preserved'])
    failed = workspace / 'injected-failure'; wb.ensure_database(failed / recovery.DB_NAME)
    with closing(wb.connect(failed / recovery.DB_NAME)) as con:
        con.execute("CREATE TRIGGER injected_failure AFTER INSERT ON import_runs BEGIN SELECT RAISE(ABORT, 'injected'); END")
    with server(failed) as request:
        status, preview, _ = request('/api/imports/preview', dict(csv_text=text, synthetic=True)); assert status == 200
        status, _, _ = request('/api/imports/apply', dict(csv_text=text, synthetic=True, dataset_sha256=preview['dataset_sha256'], preview_token=preview['preview_token']))
        assert status == 503 and report(request)['metrics']['orders'] == 9
        assert request('/api/imports')[1]['imports'] == []
    checks.append('failed_receipt_insert_rolls_back_entire_import')
    result = dict(schema=1, app='Workfloor', version=wb.VERSION, status='PASS', synthetic_only=True,
                  evidence='Real CLI and loopback HTTP; constructed original v1 fixture; no browser acceptance implied',
                  from_schema=1, to_schema=2, original_tables_preserved=4, restored_tables=5,
                  metrics_before=baseline['metrics'], metrics_after=imported['metrics'], imported_orders=3, imported_events=2,
                  receipt_count=1, csv_sha256=receipt['csv_sha256'], checks=checks)
    (workspace / 'import-history-case.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(result))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--workspace', type=Path, required=True)
    try: run(parser.parse_args().workspace)
    except Exception:
        print('Import-history acceptance failed. Private new files retained; no token, receipt or raw log printed.', file=sys.stderr)
        raise SystemExit(1)
