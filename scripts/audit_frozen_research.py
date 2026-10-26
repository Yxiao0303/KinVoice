"""Verify historical hashes against pinned commits, never rebase old experiments.
Optional mock execution uses an isolated archive of the original source revision.
"""
import argparse,hashlib,io,json,subprocess,sys,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ARCHIVES={
 'batch-evaluation-v2':'58f6580e771f85cfb8e9b8e1c333d7b14c8ae482',
 'batch-evaluation-v1':'5ced9b1f4c8120ea4c5bd42eeb96096eb20f2256',
 'exploratory-v1':'0291b769db79ef3468fec850853107fbed756cc1',
 'listen-first-v1':'ac5ef26ed7c9e996898204d2e44c1cb4e6432fae',
 'three-arm-v1':'d3bcd355bf17583608354f6471f76bb2bd645463',
}

def git_bytes(revision,path):
    return subprocess.check_output(['git','show',f'{revision}:{path}'],cwd=ROOT)

def audit(name):
    revision=ARCHIVES[name];freeze=f'research/{name}/freeze.json'
    # Freeze files themselves must not have been rewritten to match new code.
    if (ROOT/freeze).read_bytes()!=git_bytes(revision,freeze):raise ValueError('Historical freeze modified')
    spec=json.loads((ROOT/freeze).read_text());expected=spec.get('hashes',spec)
    for path,digest in expected.items():
        if hashlib.sha256(git_bytes(revision,path)).hexdigest()!=digest:
            raise ValueError('Historical source hash mismatch')
    if name in ('three-arm-v1','batch-evaluation-v1','batch-evaluation-v2'):
        original_paths=set(subprocess.check_output(['git','ls-tree','-r','--name-only',revision,
            '--',f'research/{name}'],cwd=ROOT,text=True).splitlines())
        current_paths={str(p.relative_to(ROOT)) for p in (ROOT/f'research/{name}').rglob('*') if p.is_file()}
        if current_paths!=original_paths:raise ValueError('Real experiment artifact set modified')
        for path in original_paths:
            if (ROOT/path).read_bytes()!=git_bytes(revision,path):
                raise ValueError('Real experiment artifact modified')
    return revision

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--mock-output',type=Path)
    args=parser.parse_args()
    for name in ARCHIVES:audit(name)
    if args.mock_output:
        original=ARCHIVES['exploratory-v1']
        data=subprocess.check_output(['git','archive','--format=tar',original],cwd=ROOT)
        with tempfile.TemporaryDirectory(prefix='kinvoice-original-protocol-') as tmp:
            with tarfile.open(fileobj=io.BytesIO(data)) as archive:archive.extractall(tmp,filter='data')
            subprocess.run([sys.executable,str(Path(tmp)/'scripts/research_protocol.py'),
                            '--output',str(args.mock_output.resolve())],cwd=tmp,check=True)
    print(json.dumps({'historical_archives_verified':list(ARCHIVES),'paid_calls':0}))

if __name__=='__main__':main()
