"""Application-local Windows entry point; no installed Python is used."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import sys
import webbrowser

ROOT = Path(__file__).resolve().parent


def check_package():
    manifest = json.loads((ROOT / 'PACKAGE-MANIFEST.json').read_text(encoding='utf-8'))
    for row in manifest['files']:
        path = ROOT / row['path']
        if not path.is_file() or path.is_symlink() or path.stat().st_size != row['bytes']:
            raise ValueError('Package is incomplete. Extract a fresh download into a new folder.')
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Package files changed. Preserve your data and extract a fresh download.')
    if Path(sys.executable).resolve() != (ROOT / 'runtime/python.exe').resolve():
        raise ValueError('Start with Workfloor.cmd so the bundled runtime is used.')
    return manifest


def main():
    parser = argparse.ArgumentParser(description='Workfloor portable Windows application')
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--check', action='store_true', help='Check package/runtime without creating data')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--backup-to', type=Path)
    action.add_argument('--verify-backup', type=Path)
    action.add_argument('--restore-from', type=Path)
    action.add_argument('--upgrade-backup', type=Path)
    args = parser.parse_args()
    try:
        manifest = check_package()
        sys.path.insert(0, str(ROOT / 'application'))
        import app
        import workbench as wb
        import recovery
        import migrate
        from ownership import data_lock, plain_path
        if args.check:
            print(json.dumps(dict(status='PASS', runtime=sys.version.split()[0],
                                  application=wb.VERSION, package=manifest['package_version'],
                                  isolated=sys.flags.isolated == 1, bundled_runtime=True)))
            return
        if args.data_dir is None:
            if not os.environ.get('LOCALAPPDATA'):
                raise ValueError('Windows local application-data folder is unavailable; choose --data-dir.')
            data = Path(os.environ['LOCALAPPDATA']) / 'Outlands/Workfloor/data'
        else:
            data = args.data_dir
        data = plain_path(data)
        if data == ROOT or ROOT in data.parents:
            raise ValueError('Choose a data directory outside the extracted application folder.')
        if args.backup_to:
            recovery.backup(data, args.backup_to); print('Backup created and verified. Keep it private.'); return
        if args.verify_backup:
            recovery.verify(args.verify_backup); print('Backup verified.'); return
        if args.restore_from:
            recovery.restore(args.restore_from, data); print('Restored into the new data directory.'); return
        if args.upgrade_backup:
            migrate.upgrade(data, args.upgrade_backup); print('Upgrade completed with a verified original backup.'); return
        with data_lock(data, create=True):
            database = data / 'workfloor.sqlite3'
            created = wb.ensure_database(database)
            with app.make_server(database, 0, own_lock=False) as server:
                url = 'http://' + server.authority + '/'
                print('Workfloor ' + wb.VERSION + ' | INVENTED DATA ONLY', flush=True)
                print(('Created' if created else 'Reopened') + ' private data: ' + str(data), flush=True)
                print('Open ' + url, flush=True)
                print('Keep this window open. Press Ctrl+C here to stop before backup or restore.', flush=True)
                if not args.no_browser:
                    try:
                        if not webbrowser.open(url): print('Open the address above in your browser.', flush=True)
                    except OSError: print('Open the address above in your browser.', flush=True)
                def interrupt(*_):
                    raise KeyboardInterrupt
                if hasattr(signal, 'SIGBREAK'): signal.signal(signal.SIGBREAK, interrupt)
                try: server.serve_forever(poll_interval=.2)
                except KeyboardInterrupt: pass
        print('Workfloor stopped. Your data remains in the private data directory.', flush=True)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        parser.exit(1, 'Could not start Workfloor: ' + str(exc) + '\n')


if __name__ == '__main__': main()
