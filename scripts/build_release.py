"""Package one reviewed committed source inventory. No database or runtime files."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.3.0'
NAMES = (
    '.gitattributes',
    '.github/workflows/recovery-release.yml',
    '.github/workflows/verify.yml',
    '.gitignore',
    'LICENSE',
    'README.md',
    'app.py',
    'csv_imports.py',
    'demo/data/after-import.json',
    'demo/data/baseline.json',
    'demo/data/provenance.json',
    'demo/data/receipt.json',
    'demo/index.html',
    'demo/mark.svg',
    'demo/viewer.css',
    'demo/viewer.js',
    'docs/BROWSER-CHECKS.md',
    'docs/BROWSER-DEMO.md',
    'docs/DECISIONS.md',
    'docs/IMPORTS.md',
    'docs/RECOVERY.md',
    'docs/RELEASE-REVIEW.md',
    'docs/RELEASE-v0.1.0.md',
    'docs/RELEASE-v0.2.0.md',
    'docs/RELEASE.md',
    'docs/VALIDATION-v0.1.0.md',
    'docs/VALIDATION-v0.2.0.md',
    'docs/VALIDATION.md',
    'docs/WALKTHROUGH.md',
    'docs/media/video-receipt.json',
    'docs/media/workfloor-walkthrough.mp4',
    'docs/media/workfloor-walkthrough.vtt',
    'docs/screenshots/conflicting-event.jpg',
    'docs/screenshots/import-errors.jpg',
    'docs/screenshots/import-valid-preview.jpg',
    'docs/screenshots/naive-query.jpg',
    'docs/screenshots/overview.jpg',
    'docs/screenshots/phone-320.jpg',
    'docs/screenshots/phone-390.jpg',
    'docs/screenshots/phone-import.jpg',
    'docs/screenshots/preserved-snapshot.jpg',
    'docs/screenshots/report-after-import.jpg',
    'docs/verification-v0.2.0.json',
    'docs/verification.json',
    'e2e/common.py',
    'e2e/test_demo.py',
    'e2e/test_workflow.py',
    'examples/default-report.json',
    'examples/import-errors.csv',
    'examples/import-valid.csv',
    'examples/recovery-case.json',
    'fixtures/synthetic.json',
    'ownership.py',
    'recovery.py',
    'requirements-browser-windows.txt',
    'scripts/accept_release.py',
    'scripts/build_release.py',
    'scripts/publish_release.py',
    'scripts/refresh_demo_exports.py',
    'scripts/run_browser_checks.py',
    'scripts/verify_entry_points.py',
    'scripts/verify_recovery.py',
    'sql/naive_join.sql',
    'sql/report.sql',
    'sql/schema.sql',
    'start-workfloor.cmd',
    'static/app.js',
    'static/imports.js',
    'static/index.html',
    'static/mark.svg',
    'static/style.css',
    'tests/test_csv_imports.py',
    'tests/test_recovery.py',
    'tests/test_workbench.py',
    'workbench.py',
)

def sha(data): return hashlib.sha256(data).hexdigest()
def git(*args): return subprocess.check_output(['git', *args], cwd=ROOT)

def build(output):
    if not output.is_absolute() or output.exists(): raise ValueError('Choose a new absolute output directory.')
    output = output.resolve()
    if output == ROOT or ROOT in output.parents or not output.parent.is_dir(): raise ValueError('Choose an external output with an existing parent.')
    if git('diff', '--name-only', 'HEAD', '--', *NAMES).strip(): raise ValueError('Commit the reviewed source before packaging.')
    revision = git('rev-parse', 'HEAD').decode().strip()
    tree = {}
    for item in filter(None, git('ls-tree', '-rz', 'HEAD').split(b'\0')):
        meta, name = item.split(b'\t', 1); mode, kind, oid = meta.split()
        tree[name.decode('utf-8')] = (mode, kind, oid)
    files = {}
    for name in NAMES:
        mode, kind, oid = tree[name]
        if kind != b'blob' or mode not in (b'100644', b'100755'): raise ValueError('Ordinary source entries only.')
        data = git('cat-file', 'blob', oid.decode())
        if hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != oid.decode(): raise ValueError('Git object mismatch.')
        if name.endswith('.py'): ast.parse(data, filename=name)
        if not name.endswith(('.jpg', '.mp4')):
            text = data.decode('utf-8')
            if '\0' in text: raise ValueError('Unexpected source payload.')
        if len(data) > 16 * 1024 * 1024: raise ValueError('Source member too large.')
        files[name] = data
    if b'VERSION = \"0.3.0\"' not in files['workbench.py']: raise ValueError('Application version differs.')
    if len(files) != len(set(NAMES)): raise ValueError('Duplicate release member.')
    manifest = dict(schema=1, version=VERSION, source_revision=revision,
                    files=[dict(path=n, bytes=len(d), sha256=sha(d)) for n, d in sorted(files.items())])
    files['SOURCE-MANIFEST.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    output.mkdir(); filename = 'workfloor-' + VERSION + '.zip'; target = output / filename
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo('workfloor-' + VERSION + '/' + name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3; info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    receipt = dict(schema=1, version=VERSION, source_revision=revision, filename=filename,
                   bytes=target.stat().st_size, sha256=sha(target.read_bytes()), files=len(files))
    (output / 'release-receipt.json').write_bytes((json.dumps(receipt, indent=2) + '\n').encode())
    (output / 'SHA256SUMS.txt').write_bytes(''.join(sha(p.read_bytes()) + '  ' + p.name + '\n' for p in sorted(output.iterdir())).encode())
    print(json.dumps(receipt)); return receipt

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
