"""Publish only matching Windows/Ubuntu builds and Windows runtime acceptance."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import zipfile

from build import ROOT, TAG, FILENAME, PREFIX, encoded, git, payload, sha

OWNER='TheOutlandsDev/workfloor'


def publish(artifacts):
    assert os.environ.get('GITHUB_REF')=='refs/heads/main' and os.environ.get('GITHUB_REPOSITORY')==OWNER
    head=git('rev-parse','HEAD').decode().strip()
    assert {p.name for p in artifacts.iterdir()}=={'portable-Windows','portable-Linux'}
    windows=artifacts/'portable-Windows';linux=artifacts/'portable-Linux'
    common={FILENAME,'release-receipt.json','SHA256SUMS.txt'}
    assert {p.name for p in windows.iterdir()}==common|{'acceptance.json'}
    assert {p.name for p in linux.iterdir()}==common
    for name in common: assert (windows/name).read_bytes()==(linux/name).read_bytes()
    receipt=json.loads((windows/'release-receipt.json').read_text())
    assert receipt['packaging_source']==head and receipt['tag']==TAG
    assert receipt['sha256']==sha((windows/FILENAME).read_bytes())
    accepted=json.loads((windows/'acceptance.json').read_text())
    assert accepted['status']=='PASS' and accepted['browser'] is True
    assert accepted['package_sha256']==receipt['sha256'] and accepted['packaging_source']==head
    assert accepted['core']['tests']>=79 and accepted['core']['failures']==accepted['core']['errors']==0
    assert len(accepted['checks'])>=13
    files=payload()
    files['PACKAGE-MANIFEST.json']=encoded(dict(schema=1,package_version='0.4.1-windows.1',
        app_source=receipt['app_source'],packaging_source=head,runtime=receipt['runtime_version'],
        files=[dict(path=n,bytes=len(b),sha256=sha(b)) for n,b in sorted(files.items())]))
    with zipfile.ZipFile(windows/FILENAME) as archive:
        assert len(archive.namelist())==len(files) and set(archive.namelist())=={PREFIX+n for n in files}
        for name,body in files.items():assert archive.read(PREFIX+name)==body
    # Acceptance is created after building; include it in the final public checksum list.
    names=[FILENAME,'acceptance.json','release-receipt.json']
    (windows/'SHA256SUMS.txt').write_text(''.join(sha((windows/n).read_bytes())+'  '+n+'\n' for n in names),encoding='utf-8',newline='\n')
    existing=subprocess.run(['gh','api','repos/'+OWNER+'/releases/tags/'+TAG],capture_output=True)
    if existing.returncode==0:
        release=json.loads(existing.stdout)
        assert not release['draft'] and release['target_commitish']==head
        assert {a['name'] for a in release['assets']}==common|{'acceptance.json'}
        for asset in release['assets']:
            assert asset['size']==(windows/asset['name']).stat().st_size
            assert asset['digest']=='sha256:'+sha((windows/asset['name']).read_bytes())
        print('Existing exact portable release verified and retained.');return
    subprocess.run(['gh','release','create',TAG,*[str(windows/n) for n in sorted(common|{'acceptance.json'})],
                    '--repo',OWNER,'--target',head,'--title','Workfloor 0.4.1 - portable Windows x64',
                    '--notes-file',str(ROOT/'docs/PORTABLE-WINDOWS.md')],check=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--artifacts',type=Path,required=True);publish(p.parse_args().artifacts)
