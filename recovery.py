"""Offline verified database backup and new-directory restore. Original MIT source."""
from __future__ import annotations
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time

import workbench as wb
from ownership import data_lock, ordinary_file, plain_path, identity

DB_NAME = 'workfloor.sqlite3'
MAX_DB = 64 * 1024 * 1024
MAX_MANIFEST = 16 * 1024
TABLES = ('work_orders', 'process_steps', 'completion_events', 'report_runs')

def read_file(path, maximum):
    before = ordinary_file(path, maximum)
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
    with os.fdopen(fd, 'rb') as stream:
        if identity(os.fstat(stream.fileno())) != identity(before): raise wb.InputError('Input changed while opening.')
        data = stream.read(maximum + 1)
        if len(data) > maximum or identity(os.fstat(stream.fileno())) != identity(before): raise wb.InputError('Input changed while reading.')
    if identity(ordinary_file(path, maximum)) != identity(before): raise wb.InputError('Input path changed while reading.')
    return data

def fresh_write(path, data):
    plain_path(path)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0), 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())

def no_sidecars(db):
    if any(db.with_name(db.name + suffix).exists() or db.with_name(db.name + suffix).is_symlink() for suffix in ('-wal', '-shm', '-journal')):
        raise wb.InputError('SQLite sidecars are present. Preserve them; reopen and stop normally before backup. No checkpoint or repair is performed here.')

def schema(con):
    return [(kind, name, table, re.sub(r'\s+', ' ', sql).strip() if sql else None)
            for kind, name, table, sql in con.execute('SELECT type, name, tbl_name, sql FROM sqlite_schema ORDER BY name')]

def check_database(con):
    con.execute('PRAGMA trusted_schema = OFF')
    if con.execute('PRAGMA application_id').fetchone()[0] != wb.APP_ID or con.execute('PRAGMA user_version').fetchone()[0] != 1:
        raise wb.InputError('The database is not supported Workfloor schema v1.')
    if con.execute('PRAGMA journal_mode').fetchone()[0] != 'delete':
        raise wb.InputError('Only stopped DELETE-journal databases are supported. No journal conversion is performed.')
    with closing(sqlite3.connect(':memory:', autocommit=True)) as expected:
        expected.executescript((wb.ROOT / 'sql/schema.sql').read_text(encoding='utf-8'))
        if schema(con) != schema(expected): raise wb.InputError('The Workfloor schema differs; no migration or repair is attempted.')
    if con.execute('PRAGMA integrity_check').fetchall() != [('ok',)]: raise wb.InputError('SQLite integrity check failed.')
    if con.execute('PRAGMA foreign_key_check').fetchone() is not None: raise wb.InputError('SQLite foreign-key check failed.')
    return {table: con.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] for table in TABLES}

def inspect_database(db):
    ordinary_file(db, MAX_DB); no_sidecars(db)
    header = read_file(db, MAX_DB)[:20]
    if header[:16] != b'SQLite format 3\0' or header[18:20] != b'\x01\x01':
        raise wb.InputError('Only rollback-journal SQLite headers are supported; WAL-marked snapshots are refused.')
    # Immutable is restricted to a selected stopped/verified backup copy.
    with closing(sqlite3.connect(db.as_uri() + '?mode=ro&immutable=1', uri=True, autocommit=True)) as con:
        return check_database(con)

def new_directory(path, source):
    target = plain_path(path)
    if target == source or source in target.parents or target in source.parents:
        raise wb.InputError('Choose a new output outside the input directory.')
    if not target.parent.is_dir(): raise wb.InputError('Output parent must already exist.')
    if target.exists(): raise wb.InputError('Output already exists. Choose a new directory; existing data is never replaced.')
    return target

def backup(data_dir, output):
    source = plain_path(data_dir)
    if not source.is_dir(): raise wb.InputError('The source data directory must already exist.')
    target = new_directory(output, source); db = source / DB_NAME
    with data_lock(source):
        ordinary_file(db, MAX_DB); no_sidecars(db)
        # Probe for active transactions. The server guard is authoritative for v0.3;
        # an idle older client must still be stopped manually.
        with closing(sqlite3.connect(db.as_uri() + '?mode=rw', uri=True, timeout=.1, autocommit=True)) as probe:
            if probe.execute('PRAGMA journal_mode').fetchone()[0] != 'delete': raise wb.InputError('Stop a DELETE-journal Workfloor database before backup.')
            probe.execute('BEGIN EXCLUSIVE'); probe.execute('ROLLBACK')
        no_sidecars(db)
        with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=.1, autocommit=True)) as con:
            con.execute('BEGIN')
            try:
                counts = check_database(con)
                target.mkdir(mode=0o700)
                # Use SQLite's backup API rather than raw-copying an open source.
                # One read transaction fixes the snapshot while the guard is held.
                fresh_write(target / DB_NAME, b'')
                page_size = con.execute('PRAGMA page_size').fetchone()[0]
                deadline = time.monotonic() + 15
                def progress(_status, _remaining, total):
                    if total * page_size > MAX_DB or time.monotonic() > deadline:
                        raise wb.InputError('Snapshot exceeds the size or time budget.')
                with closing(sqlite3.connect((target / DB_NAME).as_uri() + '?mode=rw', uri=True, autocommit=True)) as destination:
                    con.backup(destination, pages=256, progress=progress, sleep=.01)
                data = read_file(target / DB_NAME, MAX_DB)
                if inspect_database(target / DB_NAME) != counts: raise wb.InputError('Copied database differs.')
                manifest = {'schema': 1, 'app': 'Workfloor', 'app_version': wb.VERSION,
                            'database': {'name': DB_NAME, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'tables': counts}}
                fresh_write(target / 'manifest.json', (json.dumps(manifest, indent=2) + '\n').encode('utf-8'))
                verify(target)
                return {'status': 'verified', **manifest}
            finally: con.execute('ROLLBACK')

def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value: raise wb.InputError('Duplicate manifest key.')
        value[key] = item
    return value

def verify(directory):
    root = plain_path(directory)
    if not root.is_dir() or {p.name for p in root.iterdir()} != {DB_NAME, 'manifest.json'}:
        raise wb.InputError('Backup must contain exactly the database and manifest.json.')
    manifest = json.loads(read_file(root / 'manifest.json', MAX_MANIFEST), object_pairs_hook=unique_object)
    if not isinstance(manifest, dict) or set(manifest) != {'schema', 'app', 'app_version', 'database'} or type(manifest['schema']) is not int or manifest['schema'] != 1 or manifest['app'] != 'Workfloor' or not isinstance(manifest['app_version'], str) or not re.fullmatch(r'\d+\.\d+\.\d+', manifest['app_version']):
        raise wb.InputError('Unsupported backup manifest.')
    item = manifest['database']
    if not isinstance(item, dict) or set(item) != {'name', 'bytes', 'sha256', 'tables'} or item['name'] != DB_NAME or type(item['bytes']) is not int or not 0 < item['bytes'] <= MAX_DB or not isinstance(item['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', item['sha256']):
        raise wb.InputError('Unsupported database manifest fields.')
    if not isinstance(item['tables'], dict) or set(item['tables']) != set(TABLES) or any(type(n) is not int or n < 0 for n in item['tables'].values()): raise wb.InputError('Invalid table counts.')
    data = read_file(root / DB_NAME, MAX_DB)
    if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']: raise wb.InputError('Backup checksum or byte length differs.')
    if inspect_database(root / DB_NAME) != item['tables']: raise wb.InputError('Backup table counts differ.')
    if {p.name for p in root.iterdir()} != {DB_NAME, 'manifest.json'}: raise wb.InputError('Backup members changed.')
    return manifest

def restore(directory, data_dir):
    source = plain_path(directory); manifest = verify(source)
    target = new_directory(data_dir, source)
    data = read_file(source / DB_NAME, MAX_DB); item = manifest['database']
    if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']: raise wb.InputError('Backup changed before restore.')
    target.mkdir(mode=0o700)
    fresh_write(target / DB_NAME, data)
    if read_file(target / DB_NAME, MAX_DB) != data or inspect_database(target / DB_NAME) != item['tables']: raise wb.InputError('Restored database verification failed.')
    return {'status': 'restored', **manifest}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    save = sub.add_parser('backup'); save.add_argument('--data-dir', type=Path, required=True); save.add_argument('--output', type=Path, required=True)
    check = sub.add_parser('verify'); check.add_argument('--backup', type=Path, required=True)
    recover = sub.add_parser('restore'); recover.add_argument('--backup', type=Path, required=True); recover.add_argument('--data-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'backup': result = backup(args.data_dir, args.output)
        elif args.command == 'verify': result = {'status': 'verified', **verify(args.backup)}
        else: result = restore(args.backup, args.data_dir)
        print(json.dumps(result)); return 0
    except wb.InputError as exc:
        print('Recovery refused: ' + str(exc) + ' Partial NEW output may remain. See docs/RECOVERY.md.', file=sys.stderr)
        return 2
    except (OSError, sqlite3.Error, ValueError, TypeError):
        print('Recovery operation refused. Stop Workfloor, check trusted absolute paths and the backup format/checksums. Existing data is preserved; partial NEW output may remain. See docs/RECOVERY.md.', file=sys.stderr)
        return 2

if __name__ == '__main__': raise SystemExit(main())
