"""Build a deterministic, pinned application-local Windows distribution."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = '6a7a02ade5b01e1a6fc76f6e87a40ac7d2c24af6'
APP_SHA = '3afa8d27afa818b3f8cd91cc2449f0ee7f964aedc2e24843650d8a55987da944'
APP_URL = 'https://github.com/TheOutlandsDev/workfloor/releases/download/v0.4.1/workfloor-0.4.1.zip'
RUNTIME_VERSION = '3.14.10'
RUNTIME_SHA = '90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159'
RUNTIME_URL = 'https://www.python.org/ftp/python/3.14.10/python-3.14.10-embed-amd64.zip'
TAG = 'windows-v0.4.1-1'
FILENAME = 'workfloor-0.4.1-windows-x64.zip'
PREFIX = 'workfloor-0.4.1-windows-x64/'
EXTRAS = ('launch.py', 'Workfloor.cmd', 'START-HERE.txt', 'THIRD-PARTY-NOTICES.txt')


def sha(data): return hashlib.sha256(data).hexdigest()
def encoded(value): return (json.dumps(value, indent=2) + '\n').encode()
def git(*args): return subprocess.check_output(['git', *args], cwd=ROOT)


def download(url, digest, maximum, cached=None):
    if cached:
        body = cached.read_bytes()
    else:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Workfloor-portable-build'}), timeout=60) as response:
            body = response.read(maximum + 1)
    if len(body) > maximum or sha(body) != digest: raise ValueError('UPSTREAM_DIGEST_MISMATCH')
    return body


def members(body):
    result = {}
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        for info in archive.infolist():
            name = info.filename
            path = Path(name)
            if info.is_dir() or '\\' in name or path.is_absolute() or '..' in path.parts or ':' in name or name in result:
                raise ValueError('UNEXPECTED_ARCHIVE_MEMBER')
            if info.file_size > 32 * 1024 * 1024: raise ValueError('MEMBER_BOUND_EXCEEDED')
            result[name] = archive.read(info)
    return result


def payload(runtime=None, source=None):
    upstream = members(download(APP_URL, APP_SHA, 4*1024*1024, source))
    manifest = json.loads(upstream['workfloor-0.4.1/SOURCE-MANIFEST.json'])
    if manifest['source_revision'] != APP_SOURCE: raise ValueError('APP_SOURCE_MISMATCH')
    expected = {'workfloor-0.4.1/' + r['path'] for r in manifest['files']} | {'workfloor-0.4.1/SOURCE-MANIFEST.json'}
    if set(upstream) != expected: raise ValueError('APP_MEMBER_MISMATCH')
    for row in manifest['files']:
        data = upstream['workfloor-0.4.1/' + row['path']]
        if len(data) != row['bytes'] or sha(data) != row['sha256'] or data != git('show', APP_SOURCE + ':' + row['path']):
            raise ValueError('APP_BYTES_MISMATCH')
    files = {'application/' + n.removeprefix('workfloor-0.4.1/'): b for n, b in upstream.items()}
    runtime_files = members(download(RUNTIME_URL, RUNTIME_SHA, 20*1024*1024, runtime))
    if not {'python.exe', 'LICENSE.txt', 'python314._pth', '_sqlite3.pyd', 'sqlite3.dll'} <= set(runtime_files):
        raise ValueError('RUNTIME_INCOMPLETE')
    # Only the documented module-search configuration changes; binaries/notices stay exact.
    runtime_files['python314._pth'] = b'python314.zip\n.\n../application\n'
    files.update({'runtime/' + n: b for n, b in runtime_files.items()})
    for name in EXTRAS: files[name] = git('show', 'HEAD:portable/' + name)
    return files


def build(output, runtime=None, source=None):
    if not output.is_absolute() or output.exists() or not output.parent.is_dir() or ROOT == output or ROOT in output.parents:
        raise ValueError('NEW_EXTERNAL_ABSOLUTE_OUTPUT_REQUIRED')
    if git('diff', 'HEAD', '--name-only', '--', 'portable').strip(): raise ValueError('COMMIT_PACKAGING_FIRST')
    files = payload(runtime, source)
    revision = git('rev-parse', 'HEAD').decode().strip()
    files['PACKAGE-MANIFEST.json'] = encoded(dict(schema=1, package_version='0.4.1-windows.1',
        app_source=APP_SOURCE, packaging_source=revision, runtime=RUNTIME_VERSION,
        files=[dict(path=n, bytes=len(b), sha256=sha(b)) for n,b in sorted(files.items())]))
    output.mkdir()
    with zipfile.ZipFile(output / FILENAME, 'x', compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(PREFIX + name, (1980,1,1,0,0,0))
            info.create_system = 3; info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    receipt = dict(schema=1, tag=TAG, filename=FILENAME, app_version='0.4.1', app_source=APP_SOURCE,
                   source_zip_sha256=APP_SHA, packaging_source=revision, runtime_version=RUNTIME_VERSION,
                   runtime_url=RUNTIME_URL, runtime_sha256=RUNTIME_SHA, files=len(files),
                   bytes=(output/FILENAME).stat().st_size, sha256=sha((output/FILENAME).read_bytes()))
    (output/'release-receipt.json').write_bytes(encoded(receipt))
    (output/'SHA256SUMS.txt').write_text(''.join(sha((output/n).read_bytes())+'  '+n+'\n' for n in [FILENAME,'release-receipt.json']), encoding='utf-8', newline='\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--runtime',type=Path); p.add_argument('--source',type=Path)
    a=p.parse_args(); build(a.output,a.runtime,a.source)
