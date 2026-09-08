#!/usr/bin/env python3
"""Offline public Si statistics and boundary audit only; never call a solver."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from check_publication import check_paths, public_files
from si_soc_comparison import compare_spectra
ROOT=Path(__file__).resolve().parents[1]
BASE='9342a5ea21a76acd0d74d228d4a2081394f702d0'
OUT='results/si-soc-splitting'
NAV={'README.md','docs/status.md','results/README.md','scripts/README.md','benchmarks/README.md'}

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def boundary(root=ROOT):
    plan=json.loads((root/'benchmarks/si-soc-splitting-v1/plan.json').read_text())
    allowed=set(plan['shared_code_allowlist'])|NAV
    original=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE],cwd=root,text=True).splitlines()
    changed=[]
    for path in original:
        previous=subprocess.check_output(['git','show',BASE+':'+path],cwd=root)
        if not (root/path).is_file() or (root/path).read_bytes()!=previous:
            if path not in allowed:raise ValueError('Unapproved historical change: '+path)
            changed.append(path)
    check_paths(root,public_files(root))
    return dict(status='PASS',base_commit=BASE,historical_files_checked=len(original),authorized_changes=changed,
                historical_upstream_results='Unchanged; current static regressions are separate')

def close(a,b,path='root'):
    if isinstance(a,bool) or a is None or isinstance(a,str):
        if type(a) is not type(b) or a!=b:raise ValueError('Exact derived field mismatch: '+path)
    elif isinstance(a,(int,float)):
        if isinstance(b,bool) or not isinstance(b,(int,float)) or not math.isfinite(a) or not math.isfinite(b):raise ValueError('Invalid numeric field: '+path)
        if abs(a-b)>1e-11*max(1,abs(a),abs(b)):raise ValueError('Derived numeric mismatch: '+path)
    elif isinstance(a,list):
        if not isinstance(b,list) or len(a)!=len(b):raise ValueError('Array size mismatch: '+path)
        for i,(x,y) in enumerate(zip(a,b)):close(x,y,path+'.'+str(i))
    elif isinstance(a,dict):
        if not isinstance(b,dict) or a.keys()!=b.keys():raise ValueError('Object fields mismatch: '+path)
        for k in a:close(a[k],b[k],path+'.'+k)
    else:raise ValueError('Unsupported derived type: '+path)

def replay(root=ROOT):
    directory=root/OUT;e=json.loads((directory/'evidence.json').read_text())
    for path,expected in e['public_sha256'].items():
        if Path(path).is_absolute() or '..' in Path(path).parts:raise ValueError('Unconfined public evidence path')
        if digest(root/path)!=expected:raise ValueError('Public byte hash mismatch: '+path)
    if e['comparison_status']=='NOT_RUN':
        return dict(offline_status='BLOCKED',reason='Required spectra unavailable; preserve measured failures',boundary=boundary(root))
    case=json.loads((root/'benchmarks/si-soc-splitting-v1/case.json').read_text())
    case['binding']=e['bindings']
    docs={k:json.loads((directory/(k+'.json')).read_text()) for k in ('D-spectrum','Q-spectrum','D-null')}
    fresh=compare_spectra(docs['D-spectrum'],docs['Q-spectrum'],docs['D-null'],case)
    expected=json.loads((directory/'comparison.json').read_text());close(fresh,expected)
    return dict(offline_status='PASS',scope='All public spectral statistics replayed; runner-reported arrays not independently resolved',
        splitting_comparison_status=fresh['splitting_comparison_status'],numerical_review_status='REVIEW_REQUIRED',boundary=boundary(root))

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--boundary-only',action='store_true');a=p.parse_args(argv)
    try:
        r=boundary() if a.boundary_only else replay();print(json.dumps(r,indent=2));return 1 if r.get('offline_status')=='BLOCKED' else 0
    except Exception as err:print(json.dumps(dict(status='FAIL',reason=str(err))));return 2
if __name__=='__main__':sys.exit(main())
