"""Verify every ZIP member, then exercise the extracted application's recovery."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

from build_release import NAMES, VERSION

def accept(packages, workspace):
    if not workspace.is_absolute() or workspace.exists(): raise ValueError('Choose a new absolute scratch directory.')
    receipt = json.loads((packages / 'release-receipt.json').read_text(encoding='utf-8'))
    assert receipt['version'] == VERSION and receipt['filename'] == 'workfloor-' + VERSION + '.zip'
    data = (packages / receipt['filename']).read_bytes()
    assert len(data) == receipt['bytes'] and hashlib.sha256(data).hexdigest() == receipt['sha256']
    prefix = 'workfloor-' + VERSION + '/'
    with zipfile.ZipFile(packages / receipt['filename']) as archive:
        names = archive.namelist(); assert len(names) == len(set(names)) == receipt['files']
        assert set(names) == {prefix + n for n in NAMES} | {prefix + 'SOURCE-MANIFEST.json'}
        assert all(n.startswith(prefix) and '..' not in n.split('/') and '\\' not in n and ':' not in n for n in names)
        manifest = json.loads(archive.read(prefix + 'SOURCE-MANIFEST.json'))
        assert manifest['source_revision'] == receipt['source_revision'] and manifest['version'] == VERSION
        assert {row['path'] for row in manifest['files']} == set(NAMES)
        for row in manifest['files']:
            member = archive.read(prefix + row['path'])
            assert len(member) == row['bytes'] and hashlib.sha256(member).hexdigest() == row['sha256']
        workspace.mkdir(); archive.extractall(workspace)
    app = workspace / prefix
    for command in ([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                    [sys.executable, '-B', 'scripts/verify_entry_points.py'],
                    [sys.executable, '-B', 'scripts/verify_recovery.py', '--workspace', str(workspace / 'private recovery')],
                    [sys.executable, '-B', 'scripts/verify_import_history.py', '--workspace', str(workspace / 'private import history')]):
        subprocess.run(command, cwd=app, check=True, timeout=120)
    result = json.loads((workspace / 'private recovery/recovery-case.json').read_text(encoding='utf-8'))
    assert result['status'] == 'PASS'
    history = json.loads((workspace / 'private import history/import-history-case.json').read_text(encoding='utf-8'))
    assert history['status'] == 'PASS'
    print(json.dumps(dict(status='PASS', source_members=receipt['files'], recovery_checks=len(result['checks']), import_history_checks=len(history['checks']), source_revision=receipt['source_revision'])))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packages', type=Path, required=True); parser.add_argument('--workspace', type=Path, required=True)
    options = parser.parse_args(); accept(options.packages, options.workspace)
