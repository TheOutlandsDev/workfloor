"""Explicit v1 -> v2 upgrade, with a verified backup before any schema change."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

from ownership import data_lock, plain_path
import recovery
import workbench as wb

def table_digest(con, tables):
    value = hashlib.sha256()
    for table in tables:
        value.update(table.encode() + b'\0')
        for row in con.execute('SELECT * FROM ' + table + ' ORDER BY rowid'):
            values = [dict(blob=v.hex()) if isinstance(v, bytes) else v for v in row]
            value.update((wb.json_text(values) + '\n').encode('utf-8'))
    return value.hexdigest()

def apply_schema(con):
    # Static authored DDL, never user-provided SQL. execute keeps the outer transaction.
    for statement in (wb.ROOT / 'sql/migrate-v1-v2.sql').read_text(encoding='utf-8').split(';'):
        if statement.strip(): con.execute(statement)

def upgrade(data_dir, backup_dir):
    source = plain_path(data_dir); target = plain_path(backup_dir); db = source / recovery.DB_NAME
    with data_lock(source):
        recovery.inspect_database(db)
        with closing(sqlite3.connect(db.as_uri() + '?mode=ro&immutable=1', uri=True, autocommit=True)) as con:
            if con.execute('PRAGMA user_version').fetchone()[0] != 1:
                raise wb.InputError('Only schema v1 needs this upgrade. Existing v2 databases are not changed.')
        backup = recovery._backup_owned(source, target)
        recovery.verify(target)
        with closing(wb.connect(db)) as con:
            con.execute('BEGIN EXCLUSIVE')
            try:
                counts = recovery.check_database(con)
                if con.execute('PRAGMA user_version').fetchone()[0] != 1: raise wb.InputError('Schema changed before upgrade.')
                before = table_digest(con, recovery.TABLES_V1)
                with closing(sqlite3.connect((target / recovery.DB_NAME).as_uri() + '?mode=ro&immutable=1', uri=True, autocommit=True)) as snapshot:
                    if before != table_digest(snapshot, recovery.TABLES_V1):
                        raise wb.InputError('Data changed after the backup. Stop every older app and retry with a new backup.')
                apply_schema(con)
                after_counts = recovery.check_database(con)
                if before != table_digest(con, recovery.TABLES_V1) or any(after_counts[k] != n for k, n in counts.items()) or after_counts['import_runs'] != 0:
                    raise wb.InputError('Upgrade did not preserve the original tables. The transaction was refused.')
                con.execute('COMMIT')
            except BaseException:
                if con.in_transaction: con.execute('ROLLBACK')
                raise
    return dict(status='migrated', from_schema=1, to_schema=2, original_tables_preserved=True,
                prior_imports_reconstructed=False, verified_backup_sha256=backup['database']['sha256'])

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True); parser.add_argument('--backup-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    try: print(json.dumps(upgrade(args.data_dir, args.backup_dir))); return 0
    except (wb.InputError, OSError, sqlite3.Error, ValueError, TypeError):
        print('Upgrade could not complete. Preserve the database and any NEW backup output. Stop all app/database clients and read docs/IMPORT-HISTORY.md; no automatic restore is attempted.', file=sys.stderr)
        return 2

if __name__ == '__main__': raise SystemExit(main())
