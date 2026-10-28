"""Fresh-ZIP Windows qualification; raw logs and generated data stay private."""
import argparse
from contextlib import contextmanager
import hashlib
import http.client
import json
import os
from pathlib import Path
import queue
import re
import signal
import sqlite3
import subprocess
import threading
import time
import zipfile

from build import FILENAME, PREFIX, sha


def run(packages, workspace, browser=False):
    if os.name != 'nt': raise RuntimeError('Windows acceptance is required.')
    if not workspace.is_absolute() or workspace.exists() or not workspace.parent.is_dir():
        raise ValueError('Choose a new absolute private workspace.')
    receipt = json.loads((packages/'release-receipt.json').read_text())
    body = (packages/FILENAME).read_bytes()
    assert sha(body) == receipt['sha256'] and len(body) == receipt['bytes']
    workspace.mkdir()
    with zipfile.ZipFile(packages/FILENAME) as archive:
        names=archive.namelist(); manifest=json.loads(archive.read(PREFIX+'PACKAGE-MANIFEST.json'))
        assert len(names)==len(set(names))==receipt['files']
        assert set(names)=={PREFIX+r['path'] for r in manifest['files']}|{PREFIX+'PACKAGE-MANIFEST.json'}
        for row in manifest['files']:
            assert '\\' not in row['path'] and ':' not in row['path'] and not Path(row['path']).is_absolute() and '..' not in Path(row['path']).parts
            content=archive.read(PREFIX+row['path']); assert sha(content)==row['sha256'] and len(content)==row['bytes']
        archive.extractall(workspace/'fresh extracted folder')
    root=workspace/'fresh extracted folder'/PREFIX.rstrip('/')
    private=workspace/'private state'; private.mkdir()
    local=private/'local app data'; local.mkdir()
    temporary=private/'temporary'; temporary.mkdir()
    env={**os.environ,'PATH':str(Path(os.environ['SystemRoot'])/'System32'),
         'LOCALAPPDATA':str(local),'TEMP':str(temporary),'TMP':str(temporary),
         'PYTHONHOME':str(private/'invalid python home'),'PYTHONPATH':str(private/'invalid python path')}
    default=local/'Outlands/Workfloor/data'
    checks=[]
    def command(args):
        text=subprocess.list2cmdline([str(root/'Workfloor.cmd'),*map(str,args)])
        return '"'+str(Path(os.environ['COMSPEC']))+'" /d /s /c "'+text+'"'
    def cli(args, expected=0):
        p=subprocess.run(command(args),env=env,cwd=workspace,capture_output=True,timeout=40)
        if p.returncode != expected:
            (private/'last-cli.log').write_bytes(p.stdout+p.stderr)
            raise AssertionError('Bundled CLI failed; private diagnostic retained.')
        return p.stdout
    health=json.loads(cli(['--check'])); assert health['bundled_runtime'] and health['isolated']
    assert health['runtime']=='3.14.10' and health['application']=='0.4.1' and not default.exists()
    checks.append('launcher_check_uses_bundled_isolated_runtime_without_creating_data')
    code="import json,sys,unittest;sys.path.insert(0,sys.argv[1]);s=unittest.defaultTestLoader.discover(sys.argv[1]+'/tests');r=unittest.TextTestRunner(verbosity=2).run(s);print(json.dumps(dict(tests=r.testsRun,skipped=len(r.skipped),failures=len(r.failures),errors=len(r.errors))));sys.exit(not r.wasSuccessful())"
    p=subprocess.run([str(root/'runtime/python.exe'),'-I','-B','-X','utf8','-c',code,str(root/'application')],env=env,capture_output=True,timeout=180)
    (private/'core-tests.log').write_bytes(p.stdout+p.stderr)
    assert p.returncode==0, 'Bundled core tests failed; private log retained.'
    core=json.loads(p.stdout); assert core['tests']>=79 and core['failures']==core['errors']==0
    checks.append('original_core_suite_passes_under_bundled_runtime')

    @contextmanager
    def server(data=None):
        args=['--no-browser']+(['--data-dir',str(data)] if data else [])
        proc=subprocess.Popen(command(args),cwd=workspace,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                              text=True,encoding='utf-8',creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        output=queue.Queue()
        def reader():
            for line in proc.stdout: output.put(line)
        worker=threading.Thread(target=reader,daemon=True);worker.start()
        try:
            deadline=time.monotonic()+25;url=None
            while time.monotonic()<deadline:
                try: line=output.get(timeout=.2)
                except queue.Empty:
                    if proc.poll() is not None: raise AssertionError('Bundled server exited before startup.')
                    continue
                m=re.fullmatch(r'Open (http://127\.0\.0\.1:[0-9]+/)\s*',line)
                if m: url=m[1];break
            assert url, 'Bundled server did not print its loopback address.'
            yield url
        finally:
            if proc.poll() is None:
                proc.send_signal(signal.CTRL_BREAK_EVENT)
                try: proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    proc.kill();proc.wait();raise AssertionError('Bundled server did not stop gracefully.')
            worker.join(timeout=2)
            proc.stdout.close()
            assert proc.returncode==0, 'Bundled server shutdown failed.'
    def request(url,path,payload=None):
        from urllib.parse import urlsplit
        parsed=urlsplit(url);con=http.client.HTTPConnection(parsed.hostname,parsed.port,timeout=10)
        try:
            headers={'Content-Type':'application/json'}
            if payload is not None:
                meta=json.loads(request(url,'/api/meta')[1]);headers['X-Workbench-Token']=meta['token'];headers['Origin']=url.rstrip('/')
            con.request('POST' if payload is not None else 'GET',path,json.dumps(payload) if payload is not None else None,headers)
            response=con.getresponse();raw=response.read();return response.status,raw
        finally:con.close()
    def report(url):
        status,raw=request(url,'/api/report?start=2026-10-01&end=2026-10-08');assert status==200;return json.loads(raw)
    with server() as url:
        baseline=report(url);assert baseline['metrics']['orders']==9 and baseline['metrics']['delayed']==4
        assert baseline['validation']['naive_orders']==26 and baseline['validation']['correct_matches_reference']
        status,raw=request(url,'/api/reports',dict(start='2026-10-01',end='2026-10-08',dataset_sha256=baseline['dataset_sha256']))
        assert status==201;saved=json.loads(raw)['run_id'];saved_bytes=request(url,'/api/reports/'+saved)[1]
        cli(['--no-browser'],expected=1)
        cli(['--backup-to',str(private/'refused live backup')],expected=1);assert not (private/'refused live backup').exists()
        text=(root/'application/examples/import-valid.csv').read_text(encoding='utf-8')
        status,raw=request(url,'/api/imports/preview',dict(csv_text=text,synthetic=True));assert status==200;preview=json.loads(raw)
        status,raw=request(url,'/api/imports/apply',dict(csv_text=text,synthetic=True,dataset_sha256=preview['dataset_sha256'],preview_token=preview['preview_token']))
        assert status==201;import_id=json.loads(raw)['import_id']
        receipt_path='/api/imports/'+import_id+'/receipt.json';receipt_bytes=request(url,receipt_path)[1]
        after=report(url);assert after['metrics']['orders']==12 and after['metrics']['delayed']==6
        assert request(url,'/api/reports/'+saved)[1]==saved_bytes
    checks+=['default_private_data_outside_package','baseline_and_deliberate_join_error_match','transactional_csv_import_and_saved_snapshot_preserved','running_backup_refused','real_launcher_process_stops_gracefully']
    with server() as url:
        assert report(url)==after and request(url,receipt_path)[1]==receipt_bytes
    checks.append('real_new_process_reopens_default_data_and_exact_receipt')
    backup=private/'verified backup';restored=private/'fresh restored data'
    cli(['--backup-to',backup]);cli(['--verify-backup',backup]);cli(['--restore-from',backup,'--data-dir',restored])
    cli(['--restore-from',backup,'--data-dir',restored],expected=1)
    with server(restored) as url:
        assert report(url)==after and request(url,receipt_path)[1]==receipt_bytes and request(url,'/api/reports/'+saved)[1]==saved_bytes
    checks+=['bundled_backup_verify_restore_and_existing_target_refusal','restored_receipt_and_original_snapshot_bytes_match']
    # Exercise original v1 fixture creation using bundled code, then the portable upgrade controls.
    legacy=private/'legacy data';legacy_backup=private/'legacy backup'
    code="import sys;sys.path.insert(0,sys.argv[1]);from pathlib import Path;from verify_import_history import legacy_fixture;legacy_fixture(Path(sys.argv[2])/'workfloor.sqlite3')"
    subprocess.run([str(root/'runtime/python.exe'),'-I','-B','-c',code,str(root/'application/scripts'),str(legacy)],env=env,check=True,capture_output=True,timeout=30)
    before=sha((legacy/'workfloor.sqlite3').read_bytes())
    cli(['--data-dir',legacy,'--backup-to',private/'legacy snapshot'])
    # Existing old database must be refused without a silent reset or upgrade.
    cli(['--data-dir',legacy,'--no-browser'],expected=1);assert sha((legacy/'workfloor.sqlite3').read_bytes())==before
    def legacy_rows(path):
        con=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)
        try:return {t:con.execute('SELECT * FROM '+t+' ORDER BY rowid').fetchall() for t in ('work_orders','process_steps','completion_events','report_runs')}
        finally:con.close()
    original_rows=legacy_rows(legacy/'workfloor.sqlite3')
    cli(['--data-dir',legacy,'--upgrade-backup',legacy_backup])
    assert legacy_rows(legacy_backup/'workfloor.sqlite3')==original_rows==legacy_rows(legacy/'workfloor.sqlite3')
    assert (legacy_backup/'workfloor.sqlite3').read_bytes()==(private/'legacy snapshot/workfloor.sqlite3').read_bytes()
    with server(legacy) as url:assert report(url)['metrics']['orders']==9
    checks.append('legacy_schema_refused_then_explicitly_upgraded_with_original_backup')
    if browser:
        from playwright.sync_api import sync_playwright, expect
        ui=private/'browser data'
        with sync_playwright() as pw:
            chromium=pw.chromium.launch();page=chromium.new_page(accept_downloads=True)
            try:
                with server(ui) as url:
                    page.goto(url);expect(page.locator('#total')).to_have_text('9')
                    page.get_by_role('button',name='Save snapshot',exact=True).click();expect(page.locator('#history-count')).to_have_text('1')
                    page.locator('#csv-errors').click();page.locator('#csv-preview').click();expect(page.locator('#csv-apply')).to_be_disabled()
                    page.locator('#csv-valid').click();page.locator('#csv-preview').click();page.locator('#csv-apply').click()
                    expect(page.locator('#total')).to_have_text('12');expect(page.locator('#delayed')).to_have_text('6')
                    with page.expect_download() as dl:page.locator('#csv-download').click()
                    original=Path(dl.value.path()).read_bytes()
                with server(ui) as url:
                    page.goto(url);expect(page.locator('#total')).to_have_text('12')
                    with page.expect_download() as dl:page.locator('#import-history-list').get_by_role('button',name='Download receipt JSON',exact=True).click()
                    assert Path(dl.value.path()).read_bytes()==original
                ui_backup=private/'browser backup';ui_restored=private/'browser restored'
                cli(['--data-dir',ui,'--backup-to',ui_backup]);cli(['--restore-from',ui_backup,'--data-dir',ui_restored])
                with server(ui_restored) as url:
                    page.goto(url);expect(page.locator('#total')).to_have_text('12')
                    with page.expect_download() as dl:page.locator('#import-history-list').get_by_role('button',name='Download receipt JSON',exact=True).click()
                    assert Path(dl.value.path()).read_bytes()==original
                    page.get_by_role('button',name='Open snapshot ↗',exact=True).click();expect(page.locator('#total')).to_have_text('9')
                checks.append('chromium_ui_import_restart_restore_and_historical_snapshot_against_bundled_process')
            finally:chromium.close()
    for row in manifest['files']: assert sha((root/row['path']).read_bytes())==row['sha256']
    checks.append('all_distribution_files_unchanged_after_acceptance')
    result=dict(schema=1,status='PASS',package_sha256=receipt['sha256'],packaging_source=receipt['packaging_source'],
                bundled_runtime=health['runtime'],core=core,browser=browser,checks=checks,
                scope='Windows hosted/local process isolation with restricted PATH; not proof of a Python-free PC or manual Explorer/browser acceptance')
    (packages/'acceptance.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--packages',type=Path,required=True);p.add_argument('--workspace',type=Path,required=True);p.add_argument('--browser',action='store_true');a=p.parse_args();run(a.packages,a.workspace,a.browser)
