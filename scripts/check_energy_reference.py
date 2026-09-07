#!/usr/bin/env python3
"""Public energy-table replay; no Julia, QE, private arrays or network.

--all chains unchanged earlier checkers. This is not independent XC execution.
"""
import argparse
from pathlib import Path
import subprocess
import sys
from run_density_hartree_audit import digest,load,require
from audit_energy_ledger import build_energy_ledger
from compare_energy_reference import compare_saved
from check_density_hartree import equivalent

ROOT=Path(__file__).resolve().parents[1]
PLAN='benchmarks/mg-soc-energy-reference-v1/plan.json'
RESULTS='results/mg-soc-energy-reference'
NAV=('README.md','docs/status.md','results/README.md','benchmarks/README.md','scripts/README.md')


def check_frozen(root,base):
    names=subprocess.check_output(['git','-C',str(root),'ls-tree','-r','--name-only',base],text=True).splitlines()
    count=0
    for path in names:
        if path in NAV: continue
        prior=subprocess.check_output(['git','-C',str(root),'show',base+':'+path])
        require((root/path).is_file() and (root/path).read_bytes()==prior,'Frozen predecessor bytes changed: '+path)
        count+=1
    return count


def check(root=ROOT):
    root=Path(root);plan=load(root/PLAN);e=load(root/RESULTS/'evidence.json')
    require(e['case']==plan['case'] and e['base_commit']==plan['base_commit'] and e['plan_sha256']==digest(root/PLAN),'Plan binding mismatch')
    for path,sha in {**plan['source_sha256'],**e['public_sha256'],**e['verifier_sha256']}.items():
        require(digest(root/path)==sha,'Changed public source: '+path)
    ledger=build_energy_ledger(root)
    equivalent(ledger,load(root/RESULTS/'ledger.json'))
    common=load(root/RESULTS/'common-terms.json');radial=load(root/RESULTS/'local-g0.json')
    require(common['run_id']==e['run_id'] and common['plan_sha256']==e['plan_sha256'],'Evaluation run/plan mismatch')
    require(common['executed_script_sha256']==e['execution_source_sha256']['scripts/evaluate_common_energy_terms.jl'],'Wrong executed evaluator')
    # Current display/verification code can be newer; executed code hashes remain tied to their commit.
    for path,sha in e['execution_source_sha256'].items():
        import hashlib
        payload=subprocess.check_output(['git','-C',str(root),'show',e['execution_commit']+':'+path])
        require(hashlib.sha256(payload).hexdigest()==sha,'Execution commit/source mismatch')
    comparison=compare_saved(ledger,common,radial,plan)
    equivalent(comparison,load(root/RESULTS/'comparison.json'))
    require(e['execution_status']=='PASS' and e['julia_exit_code']==0 and e['runner_exit_code']==0,'Actual evaluation failed')
    for key in ('numerical_review_status','numerical_agreement_status','physical_convergence_status','residual_attribution_status','new_scf_status','new_eigensolve_status','new_qe_numerical_status'):
        require(e[key]==comparison[key],'Scope/status mismatch: '+key)
    count=check_frozen(root,plan['base_commit'])
    for doc in NAV:
        require('mg-soc-energy-reference' in (root/doc).read_text(),'Missing navigation: '+doc)
    return dict(status='PASS',frozen_predecessor_files=count,
                scope='Historical energy tokens, printed intervals, saved common-term tables and signed algebra; no independent XC or full field/radial replay')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--all',action='store_true')
    parser.add_argument('--legacy-python',default='python3.9')
    parser.add_argument('--modern-python',default=sys.executable)
    args=parser.parse_args()
    try:
        if args.all:
            subprocess.run([args.modern_python,str(args.root/'scripts/check_density_hartree.py'),'--all',
                '--root',str(args.root),'--legacy-python',args.legacy_python],check=True,cwd=args.root)
        import json
        print(json.dumps(check(args.root),indent=2))
        return 0
    except (ValueError,OSError,KeyError,TypeError,subprocess.CalledProcessError) as error:
        print('FAIL: '+str(error),file=sys.stderr);return 1


if __name__=='__main__':sys.exit(main())
