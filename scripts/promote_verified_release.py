"""Promote the exact 0.3.1 artifact already verified on all four platforms.

This one-release operation does not rebuild or relax qualification. It avoids
waiting for duplicate main jobs when their identical source passed branch CI.
The pinned source, ZIP digest, job results, every member and current source
agreement are required. Existing releases can only be verified, never replaced.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

from build_release import NAMES

OWNER = 'TheOutlandsDev/workfloor'
SOURCE = 'bc8c7036ec3c7fff2678ba2fd3a8af8780fafb47'
RUN = 40706268667
ZIP_SHA = '54bdaef7f87c521d1cf072fde467d1bcbfec234c6dc3925c73444106e14b84c0'
TAG = 'v0.3.1'
ROOT = Path(__file__).resolve().parents[1]
GROUPS = {'workfloor-release-Windows-3.12', 'workfloor-release-Windows-3.13',
          'workfloor-release-Linux-3.12', 'workfloor-release-Linux-3.13'}
ASSETS = {'workfloor-0.3.1.zip', 'SHA256SUMS.txt', 'release-receipt.json'}

def command(args): return subprocess.check_output(args, cwd=ROOT)
def api(path): return json.loads(command(['gh', 'api', 'repos/' + OWNER + '/' + path]))
def sha(data): return hashlib.sha256(data).hexdigest()

def promote(artifacts):
    assert os.environ.get('GITHUB_REPOSITORY') == OWNER and os.environ.get('GITHUB_REF') == 'refs/heads/main'
    run = api('actions/runs/' + str(RUN))
    assert run['head_sha'] == SOURCE and run['event'] == 'push' and run['conclusion'] == 'success'
    assert run['path'] == '.github/workflows/recovery-release.yml'
    jobs = api('actions/runs/' + str(RUN) + '/jobs?per_page=100')['jobs']
    required = {'compare', *['verify (' + platform + ', ' + python + ')' for platform in ('windows-latest', 'ubuntu-latest') for python in ('3.12', '3.13')]}
    assert required <= {j['name'] for j in jobs if j['conclusion'] == 'success'}
    subprocess.run(['git', 'merge-base', '--is-ancestor', SOURCE, 'HEAD'], cwd=ROOT, check=True)
    subprocess.run(['git', 'diff', '--exit-code', SOURCE, 'HEAD', '--', *NAMES], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    assert {p.name for p in artifacts.iterdir()} == GROUPS
    baseline = None
    for group in sorted(GROUPS):
        folder = artifacts / group
        assert {p.name for p in folder.iterdir()} == ASSETS
        contents = {name: (folder / name).read_bytes() for name in ASSETS}
        if baseline is None: baseline = contents
        assert contents == baseline
    receipt = json.loads(baseline['release-receipt.json'])
    assert receipt['source_revision'] == SOURCE and receipt['version'] == '0.3.1' and receipt['files'] == 76
    assert len(baseline['workfloor-0.3.1.zip']) == receipt['bytes'] and sha(baseline['workfloor-0.3.1.zip']) == receipt['sha256'] == ZIP_SHA
    expected_sums = ''.join(sha(baseline[n]) + '  ' + n + '\n' for n in sorted(ASSETS - {'SHA256SUMS.txt'})).encode()
    assert baseline['SHA256SUMS.txt'] == expected_sums
    selected = artifacts / sorted(GROUPS)[0]
    with zipfile.ZipFile(selected / 'workfloor-0.3.1.zip') as archive:
        prefix = 'workfloor-0.3.1/'
        assert len(archive.namelist()) == 76 and set(archive.namelist()) == {prefix + n for n in NAMES} | {prefix + 'SOURCE-MANIFEST.json'}
        for name in NAMES:
            assert archive.read(prefix + name) == command(['git', 'show', SOURCE + ':' + name])
    existing = subprocess.run(['gh', 'api', 'repos/' + OWNER + '/releases/tags/' + TAG], capture_output=True)
    if existing.returncode == 0:
        verify_existing(json.loads(existing.stdout), baseline); return
    created = subprocess.run(['gh', 'release', 'create', TAG, *[str(selected / n) for n in sorted(ASSETS)],
                              '--repo', OWNER, '--target', SOURCE, '--title', 'Workfloor 0.3.1 - verified database recovery',
                              '--notes-file', str(ROOT / 'docs/RELEASE.md')])
    # A duplicate main publisher may finish concurrently. Only accept identical assets.
    verify_existing(api('releases/tags/' + TAG), baseline)
    print('Published or retained the exact four-platform verified 0.3.1 release.')

def verify_existing(release, expected):
    assert not release['draft'] and release['tag_name'] == TAG
    assert {a['name'] for a in release['assets']} == ASSETS
    for asset in release['assets']:
        assert asset['size'] == len(expected[asset['name']])
        assert asset.get('digest') == 'sha256:' + sha(expected[asset['name']])

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--artifacts', type=Path, required=True)
    promote(parser.parse_args().artifacts)
