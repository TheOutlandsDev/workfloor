"""CI-only new release publication after matching platform packages and checks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

OWNER = 'TheOutlandsDev/workfloor'
ROOT = Path(__file__).resolve().parents[1]

def publish(output):
    assert os.environ.get('GITHUB_REPOSITORY') == OWNER and os.environ.get('GITHUB_REF') == 'refs/heads/main'
    receipt = json.loads((output / 'release-receipt.json').read_text(encoding='utf-8'))
    assert receipt['version'] == '0.3.0' and receipt['source_revision'] == os.environ['GITHUB_SHA']
    assert {p.name for p in output.iterdir()} == {'workfloor-0.3.0.zip', 'SHA256SUMS.txt', 'release-receipt.json'}
    assert hashlib.sha256((output / receipt['filename']).read_bytes()).hexdigest() == receipt['sha256']
    existing = subprocess.run(['gh', 'release', 'view', 'v0.3.0', '--repo', OWNER, '--json', 'url'], capture_output=True)
    if existing.returncode == 0: print('Existing release retained unchanged.'); return
    subprocess.run(['gh', 'release', 'create', 'v0.3.0', *[str(p) for p in sorted(output.iterdir())], '--repo', OWNER,
                    '--target', receipt['source_revision'], '--title', 'Workfloor 0.3.0 - verified database recovery',
                    '--notes-file', str(ROOT / 'docs/RELEASE.md')], check=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    publish(parser.parse_args().output)
