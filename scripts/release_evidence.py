"""Reuse complete same-source platform evidence; never rebuild untested release bytes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

from build_release import NAMES, VERSION

ROOT = Path(__file__).resolve().parents[1]
OWNER = 'TheOutlandsDev/workfloor'
GROUPS = {'workfloor-release-' + platform + '-' + python for platform in ('Windows', 'Linux') for python in ('3.12', '3.13')}
JOBS = {'compare', *['verify (' + platform + ', ' + python + ')' for platform in ('windows-latest', 'ubuntu-latest') for python in ('3.12', '3.13')]}

def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', 'repos/' + OWNER + '/' + path], cwd=ROOT))

def qualified(run, jobs, source, require_complete=True):
    return (run.get('head_sha') == source and run.get('event') == 'push'
            and run.get('path') == '.github/workflows/recovery-release.yml'
            and (not require_complete or run.get('conclusion') == 'success')
            and JOBS <= {j['name'] for j in jobs if j.get('conclusion') == 'success'})

def reuse():
    selected = ''
    if os.environ.get('GITHUB_REPOSITORY') == OWNER and os.environ.get('GITHUB_REF') == 'refs/heads/main':
        source = os.environ['GITHUB_SHA']
        try:
            for run in api('actions/workflows/recovery-release.yml/runs?per_page=30')['workflow_runs']:
                if run['head_sha'] != source or run['conclusion'] != 'success': continue
                jobs = api('actions/runs/' + str(int(run['id'])) + '/jobs?per_page=100')['jobs']
                if qualified(run, jobs, source): selected = str(int(run['id'])); break
        except subprocess.CalledProcessError:
            # Unavailable evidence causes fresh verification, never a publication pass.
            selected = ''
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output: output.write('run_id=' + selected + '\n')
    print('Complete same-source verification selected.' if selected else 'Fresh platform verification required.')

def sha(data): return hashlib.sha256(data).hexdigest()

def publish(artifacts, run_id):
    if os.environ.get('GITHUB_REPOSITORY') != OWNER or os.environ.get('GITHUB_REF') != 'refs/heads/main': raise ValueError('MAIN_PUBLICATION_REQUIRED')
    source = os.environ['GITHUB_SHA']
    if not re.fullmatch('[0-9a-f]{40}', source): raise ValueError('FULL_SOURCE_REVISION_REQUIRED')
    run = api('actions/runs/' + str(run_id)); jobs = api('actions/runs/' + str(run_id) + '/jobs?per_page=100')['jobs']
    if not qualified(run, jobs, source, require_complete=str(run_id) != os.environ['GITHUB_RUN_ID']): raise ValueError('ALL_FOUR_PLATFORM_RESULTS_AND_COMPARISON_REQUIRED')
    if {p.name for p in artifacts.iterdir()} != GROUPS: raise ValueError('ALL_FOUR_PLATFORM_PACKAGES_REQUIRED')
    filename = 'workfloor-' + VERSION + '.zip'; expected = {filename, 'SHA256SUMS.txt', 'release-receipt.json'}
    contents = None
    for group in sorted(GROUPS):
        folder = artifacts / group
        if {p.name for p in folder.iterdir()} != expected: raise ValueError('EXACT_ASSETS_REQUIRED')
        current = {name: (folder / name).read_bytes() for name in expected}
        if contents is None: contents = current
        if contents != current: raise ValueError('PLATFORM_PACKAGE_BYTES_DIFFER')
    receipt = json.loads(contents['release-receipt.json'])
    if receipt['schema'] != 1 or receipt['source_revision'] != source or receipt['version'] != VERSION or receipt['filename'] != filename or receipt['files'] != len(NAMES) + 1 or receipt['sha256'] != sha(contents[filename]) or receipt['bytes'] != len(contents[filename]): raise ValueError('RELEASE_RECEIPT_MISMATCH')
    sums = ''.join(sha(contents[name]) + '  ' + name + '\n' for name in sorted(expected - {'SHA256SUMS.txt'})).encode()
    if contents['SHA256SUMS.txt'] != sums: raise ValueError('CHECKSUM_LIST_MISMATCH')
    selected = artifacts / sorted(GROUPS)[0]
    with zipfile.ZipFile(selected / filename) as archive:
        prefix = 'workfloor-' + VERSION + '/'; names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != {prefix + n for n in NAMES} | {prefix + 'SOURCE-MANIFEST.json'}: raise ValueError('SOURCE_MEMBER_SET_MISMATCH')
        if any((info.external_attr >> 16) & 0o170000 != 0o100000 for info in archive.infolist()): raise ValueError('ORDINARY_SOURCE_MEMBERS_REQUIRED')
        manifest = json.loads(archive.read(prefix + 'SOURCE-MANIFEST.json'))
        if manifest['schema'] != 1 or manifest['source_revision'] != source or manifest['version'] != VERSION or len(manifest['files']) != len(NAMES): raise ValueError('SOURCE_MANIFEST_MISMATCH')
        rows = {row['path']: row for row in manifest['files']}
        if set(rows) != set(NAMES): raise ValueError('SOURCE_MANIFEST_PATHS_MISMATCH')
        for name in NAMES:
            data = archive.read(prefix + name)
            if data != subprocess.check_output(['git', 'show', source + ':' + name], cwd=ROOT): raise ValueError('COMMITTED_SOURCE_BYTES_DIFFER')
            if rows[name]['bytes'] != len(data) or rows[name]['sha256'] != sha(data): raise ValueError('SOURCE_MANIFEST_DIGEST_MISMATCH')
    tag = 'v' + VERSION
    existing = subprocess.run(['gh', 'release', 'view', tag, '--repo', OWNER, '--json', 'url'], capture_output=True)
    if existing.returncode == 0: print('Existing named release retained unchanged.'); return
    subprocess.run(['gh', 'release', 'create', tag, *[str(selected / name) for name in sorted(expected)], '--repo', OWNER,
                    '--target', source, '--title', 'Workfloor ' + VERSION + ' - durable import history', '--notes-file', str(ROOT / 'docs/RELEASE.md')], check=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('reuse'); release = sub.add_parser('publish'); release.add_argument('--artifacts', type=Path, required=True); release.add_argument('--run-id', type=int, required=True)
    args = parser.parse_args()
    if args.command == 'reuse': reuse()
    else: publish(args.artifacts, args.run_id)
