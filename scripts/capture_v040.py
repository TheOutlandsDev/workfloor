"""Capture the published v0.4.1 UI with fictional data on a Windows CI runner.

No runtime file is edited. The first isolated server substitutes a fixed import
ID/time for repeatable synthetic fixtures; later servers use the stored receipt.
Only the explicit JPEG inventory and a sanitized numeric receipt are public.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import multiprocessing as mp
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

SOURCE = '6a7a02ade5b01e1a6fc76f6e87a40ac7d2c24af6'
ZIP_SHA = '3afa8d27afa818b3f8cd91cc2449f0ee7f964aedc2e24843650d8a55987da944'
FILES = ('01-baseline.jpg', '02-valid-preview.jpg', '03-import-history.jpg',
         '04-receipt.jpg', '05-after-restart.jpg', '06-after-restore.jpg')


def digest(data): return hashlib.sha256(data).hexdigest()


def serve(release, data, pipe, fixed):
    sys.path.insert(0, release)
    import app
    import workbench as wb
    from ownership import data_lock
    if fixed:
        from datetime import datetime, timezone
        from types import SimpleNamespace
        from uuid import UUID
        import csv_imports
        class FixtureClock(datetime):
            @classmethod
            def now(cls, tz=None): return datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
        csv_imports.datetime = FixtureClock
        csv_imports.uuid = SimpleNamespace(uuid4=lambda: UUID(hex='04000400040004000400040004000400'))
    with data_lock(Path(data), create=True):
        db = Path(data) / 'workfloor.sqlite3'; wb.ensure_database(db)
        with app.make_server(db, own_lock=False) as server:
            import threading
            worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05})
            worker.start(); pipe.send('http://' + server.authority)
            try: pipe.recv()
            finally: server.shutdown(); worker.join(timeout=10)


@contextmanager
def running(release, data, fixed=False):
    parent, child = mp.Pipe()
    process = mp.Process(target=serve, args=(str(release), str(data), child, fixed))
    process.start(); child.close()
    try:
        if not parent.poll(30): raise RuntimeError('Synthetic server did not start')
        yield parent.recv()
    finally:
        if process.is_alive():
            try: parent.send('stop')
            except (BrokenPipeError, EOFError): pass
        process.join(timeout=20)
        if process.is_alive(): process.terminate(); process.join(); raise RuntimeError('Server required forced cleanup')
        parent.close()
        if process.exitcode: raise RuntimeError('Synthetic server failed')


def acquire(workspace):
    target = workspace / 'release.zip'
    request = urllib.request.Request('https://github.com/TheOutlandsDev/workfloor/releases/download/v0.4.1/workfloor-0.4.1.zip', headers={'User-Agent': 'Workfloor-reproducible-capture'})
    with urllib.request.urlopen(request, timeout=60) as response: data = response.read()
    if digest(data) != ZIP_SHA: raise ValueError('Published release bytes differ')
    target.write_bytes(data)
    with zipfile.ZipFile(target) as archive:
        prefix = 'workfloor-0.4.1/'
        names = archive.namelist()
        if len(names) != len(set(names)) or any(not n.startswith(prefix) or '..' in n.split('/') or '\\' in n for n in names): raise ValueError('Unsafe release members')
        manifest = json.loads(archive.read(prefix + 'SOURCE-MANIFEST.json'))
        if manifest['source_revision'] != SOURCE or manifest['version'] != '0.4.1': raise ValueError('Wrong release source')
        if set(names) != {prefix + r['path'] for r in manifest['files']} | {prefix + 'SOURCE-MANIFEST.json'}: raise ValueError('Unexpected release member')
        for row in manifest['files']:
            member = archive.read(prefix + row['path'])
            if len(member) != row['bytes'] or digest(member) != row['sha256']: raise ValueError('Release member differs')
        archive.extractall(workspace / 'extracted')
    return workspace / 'extracted/workfloor-0.4.1'


def capture(output):
    from playwright.sync_api import sync_playwright, expect
    if not output.is_absolute() or output.exists(): raise ValueError('Choose a new absolute public-output directory')
    output.mkdir()
    checks = []
    with tempfile.TemporaryDirectory(prefix='workfloor-capture-') as scratch:
        private = Path(scratch); release = acquire(private); data = private / 'invented data'
        checks.append('published_release_zip_and_all_members_verified')
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce', accept_downloads=True)
            page = context.new_page(); page.set_default_timeout(15000)
            errors = []; page.on('pageerror', lambda e: errors.append(type(e).__name__))
            def shot(selector, name):
                page.locator(selector).screenshot(path=str(output / name), type='jpeg', quality=94, animations='disabled')
            def download(button, name):
                with page.expect_download() as pending: button.click()
                item = pending.value
                if item.failure(): raise RuntimeError('Receipt download failed')
                target = private / name; item.save_as(target); return target.read_bytes()
            with running(release, data, fixed=True) as url:
                page.goto(url); expect(page.locator('#total')).to_have_text('9')
                expect(page.locator('#delayed')).to_have_text('4')
                expect(page.locator('#import-history-list')).to_contain_text('No recorded imports yet')
                shot('#report', FILES[0]); checks.append('fresh_report_has_nine_orders_four_delayed')
                page.locator('#csv-valid').click(); page.locator('#csv-preview').click()
                expect(page.locator('#csv-summary')).to_have_text('3 records · 3 valid · 0 with issues')
                expect(page.locator('#csv-apply')).to_be_enabled()
                expect(page.locator('#total')).to_have_text('9')
                shot('#import', FILES[1]); checks.append('three_order_preview_leaves_report_unchanged')
                page.locator('#csv-apply').click(); expect(page.locator('#total')).to_have_text('12')
                expect(page.locator('#delayed')).to_have_text('6')
                expect(page.locator('#import-history-list .history-row')).to_have_count(1)
                shot('#imports-history', FILES[2])
                original = download(page.locator('#csv-download'), 'original.json')
                receipt = json.loads(original)
                if receipt['orders_added'] != 3 or receipt['completion_events_added'] != 2 or receipt['import_id'] != '04000400040004000400040004000400' or receipt['imported_at'] != '2026-10-08T12:00:00Z': raise ValueError('Synthetic receipt differs')
                if receipt['csv_sha256'] != digest((release/'examples/import-valid.csv').read_bytes()): raise ValueError('CSV hash differs')
                page.locator('#import-history-list').get_by_role('button', name='View receipt ↗', exact=True).click()
                expect(page.locator('#import-receipt-details')).to_contain_text(receipt['import_id'])
                colors = page.locator('#import-receipt-details').evaluate("node => {const s=getComputedStyle(node);return [s.color,s.backgroundColor]}")
                import re
                def luminance(color):
                    rgb = [int(v)/255 for v in re.findall(r'\d+',color)[:3]]
                    channels = [v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]
                    return sum(v*w for v,w in zip(channels,[.2126,.7152,.0722]))
                levels=sorted(map(luminance,colors))
                if (levels[1]+.05)/(levels[0]+.05)<4.5: raise ValueError('Receipt text contrast is insufficient')
                checks.append('rendered_receipt_text_contrast_checked')
                shot('#import-receipt-dialog', FILES[3]); page.locator('#close-import-receipt').click()
                checks.append('stored_receipt_records_three_orders_two_events_and_input_hash')
            with running(release, data) as url:
                page.goto(url); expect(page.locator('#total')).to_have_text('12')
                expect(page.locator('#import-history-list .history-row')).to_have_count(1)
                again = download(page.locator('#import-history-list').get_by_role('button', name='Download receipt JSON', exact=True), 'restart.json')
                if again != original: raise ValueError('Restart receipt differs')
                shot('#imports-history', FILES[4]); checks.append('receipt_bytes_identical_after_real_process_restart')
            backup, restored = private / 'verified backup', private / 'restored data'
            for args in (['backup','--data-dir',str(data),'--output',str(backup)], ['verify','--backup',str(backup)], ['restore','--backup',str(backup),'--data-dir',str(restored)]):
                result = subprocess.run([sys.executable,'-B',str(release/'recovery.py'),*args],capture_output=True,timeout=30)
                if result.returncode: raise RuntimeError('Recovery CLI failed; raw output withheld')
            with running(release, restored) as url:
                page.goto(url); expect(page.locator('#total')).to_have_text('12')
                expect(page.locator('#import-history-list .history-row')).to_have_count(1)
                final = download(page.locator('#import-history-list').get_by_role('button', name='Download receipt JSON', exact=True), 'restore.json')
                if final != original: raise ValueError('Restored receipt differs')
                shot('#imports-history', FILES[5]); checks.append('receipt_bytes_identical_after_verified_database_restore')
            if errors: raise RuntimeError('Browser JavaScript failed')
            checks.append('no_browser_javascript_errors')
            chromium = browser.version; context.close(); browser.close()
    if {p.name for p in output.iterdir()} != set(FILES): raise ValueError('Unexpected public output')
    record = dict(schema=1, status='PASS', application_version='0.4.1', source_revision=SOURCE,
                  release_zip_sha256=ZIP_SHA, chromium=chromium, synthetic_only=True,
                  viewport=dict(width=1440,height=1000), capture_method='Real UI element screenshots from three isolated app processes on Windows CI; no DOM/CSS changes',
                  fixture_note='Only the first server substitutes a fictional fixed receipt ID and UTC time for repeatability. All API tokens remain random and private. Runtime files are unchanged.',
                  version_label_note='The released v0.4.1 corrects stale labels and explicitly styles receipt text; no capture-only CSS changes.',
                  checks=checks, images=[dict(filename=n,bytes=(output/n).stat().st_size,sha256=digest((output/n).read_bytes())) for n in FILES])
    (output/'capture.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('PASS: six current-release captures and eight workflow checks; private databases/downloads removed.')


if __name__ == '__main__':
    mp.freeze_support()
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path,required=True)
    try: capture(parser.parse_args().output)
    except Exception as error:
        print('Capture failed: '+type(error).__name__+'; no raw database, token or path is printed.',file=sys.stderr)
        raise SystemExit(1)
