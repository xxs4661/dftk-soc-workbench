#!/usr/bin/env python3
"""Five fixed-density public-term calls and one fixed radial diagnostic; no solver.

Raw arrays stay in a NEW ignored run directory. Publication is a separate exact
whitelist. Reuse the frozen array recorder's atomic completion/failure pattern.
"""
import argparse
import datetime
import gzip
import os
from pathlib import Path
import subprocess
import sys
import uuid

from run_density_hartree_audit import digest, load, require, write_json, save_completion, bind_dftk
from audit_energy_ledger import build_energy_ledger

ROOT = Path(__file__).resolve().parents[1]
PLAN = 'benchmarks/mg-soc-energy-reference-v1/plan.json'
CODE = ('scripts/run_energy_reference_audit.py', 'scripts/evaluate_common_energy_terms.jl',
        'scripts/audit_energy_ledger.py', 'scripts/audit_local_g0.py', 'scripts/compare_energy_reference.py')


def bind_public(root, plan):
    for path, sha in plan['source_sha256'].items():
        source = root / path
        require(source.is_file(), 'BLOCKED_MISSING_SOURCE: ' + path)
        require(source.stat().st_size == plan['source_bytes'][path] and digest(source) == sha,
                'Source bytes changed: ' + path)


def prepare_transfer(root, directory, plan, label, public_path):
    source = root / public_path
    require(digest(source) == plan['source_sha256'][public_path], 'Public coefficient hash mismatch')
    data = gzip.decompress(source.read_bytes())
    target = directory / (label + '.csv')
    target.write_bytes(data)
    require(target.read_bytes() == data, 'Decompressed transfer write mismatch')
    return dict(path=str(target), sha256=digest(target), public_path=public_path,
                public_sha256=digest(source), bytes=len(data),
                binding='Exact bytes equal gzip.decompress of bound full public source')


def validate_worker_receipt(common, record, directory):
    require(isinstance(common,dict) and common.get('execution_status')=='PASS' and common.get('exit_code')==0,
            'Invalid or failed fixed-density worker receipt')
    for key in ('run_id','plan_sha256'):
        require(common.get(key)==record[key], 'Worker current identity mismatch: '+key)
    require(common.get('executed_script_sha256')==record['execution_source_sha256']['scripts/evaluate_common_energy_terms.jl'],
            'Wrong worker execution source')
    arrays=common.get('local_arrays')
    require(isinstance(arrays,dict) and arrays.get('path')=='arrays.bin', 'Missing local array binding')
    require(digest(directory/'common/arrays.bin')==arrays.get('sha256'), 'Worker array file hash mismatch')


def initial_record(run_id):
    return dict(schema_version=1, run_id=run_id, execution_status='INCOMPLETE', exit_code=9,
                sources={}, new_data_status='NEW_POSTPROCESSING_OF_HISTORICAL_STATES',
                new_scf_status='NOT_RUN', new_eigensolve_status='NOT_RUN', new_qe_numerical_status='NOT_RUN')


def fixed_summary(record):
    require(record['execution_status'] in ('PASS', 'FAIL', 'BLOCKED_MISSING_SOURCE'), 'Invalid completion status')
    return 'Fixed-density energy audit: ' + record['execution_status'] + '\nRun: ' + record['run_id'] + '\n'


def execute(root, directory, julia):
    directory.mkdir(parents=True, exist_ok=False)
    record = initial_record(directory.name)
    try:
        write_json(directory / 'result.json', record)
        plan = load(root / PLAN)
        bind_public(root, plan)
        commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
        require(commit != plan['base_commit'], 'Preparation commit required')
        for path in (PLAN, *CODE):
            require(subprocess.check_output(['git', '-C', str(root), 'show', 'HEAD:' + path]) == (root/path).read_bytes(),
                    'Commit plan/execution code before evaluation: ' + path)
        record.update(base_commit=plan['base_commit'], execution_commit=commit, plan_sha256=digest(root/PLAN),
                      execution_source_sha256={p:digest(root/p) for p in CODE},
                      started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        # Independent historical ledger remains available even if a private input is absent.
        ledger = build_energy_ledger(root)
        write_json(directory / 'ledger.json', ledger)
        record['historical_energy_ledger_status'] = 'PASS'
        prior = load(root / plan['historical_binding_plan'])
        for label in ('A', 'B'):
            record['sources'][label] = bind_dftk(root, prior, label)
        qe = prior['sources']['G40']
        source = root / '.work/phase7b' / qe['files']['scratch/mg_soc_qe_v1.save/charge-density.dat']['path']
        expected = qe['files']['scratch/mg_soc_qe_v1.save/charge-density.dat']
        require(source.is_file(), 'BLOCKED_MISSING_SOURCE: G40 original charge')
        require(source.stat().st_size == expected['bytes'] and digest(source) == expected['sha256'], 'G40 original charge changed')
        record['sources']['G40'] = dict(status='PASS', run_id=qe['run_id'], raw_sha256=digest(source), raw_bytes=source.stat().st_size,
            public_coefficients_ref='results/mg-soc-density-hartree/evidence.json#/sources/G40')
        upf = root / plan['pseudo_path']
        require(upf.is_file(), 'BLOCKED_MISSING_SOURCE: Mg UPF')
        require(digest(upf) == plan['pseudo_sha256'], 'UPF identity changed')
        transfers = {label:prepare_transfer(root,directory,plan,label,path) for label,path in (
            ('dftk','results/mg-soc-density-hartree/dftk-nout.csv.gz'),
            ('qe','results/mg-soc-density-hartree/qe-rho.csv.gz'))}
        request = dict(schema_version=1, run_id=directory.name, plan_path=PLAN,
                       plan_sha256=digest(root/PLAN), transfers=transfers)
        write_json(directory/'request.json', request)
        env = os.environ.copy()
        env.update(JULIA_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', JULIA_LOAD_PATH='@:@stdlib')
        command = [julia,'--startup-file=no','--threads=1','--project='+str(root/'environment/workbench'),
                   str(root/'scripts/evaluate_common_energy_terms.jl'), str(directory/'request.json'), str(directory/'common')]
        with (directory/'julia.stdout').open('w') as stdout, (directory/'julia.stderr').open('w') as stderr:
            code = subprocess.run(command, cwd=root, env=env, stdout=stdout, stderr=stderr).returncode
        record['julia_exit_code'] = code
        require(code == 0, 'Fixed-density worker failed: ' + str(code))
        common = load(directory/'common/metadata.json')
        validate_worker_receipt(common,record,directory)
        from audit_local_g0 import build_local_g0_audit
        radial = build_local_g0_audit(root, common)
        write_json(directory/'local-g0.json', radial)
        require(radial['dftk_bookkeeping']['status']=='PASS', 'Native local correction bookkeeping failed')
        from compare_energy_reference import compare_saved
        comparison=compare_saved(ledger,common,radial,plan)
        write_json(directory/'comparison.json',comparison)
        # Detect accidental changes to public and original inputs after all read-only calls.
        bind_public(root, plan)
        for label in ('A','B'):
            bind_dftk(root, prior, label)
        require(digest(source) == expected['sha256'] and digest(upf) == plan['pseudo_sha256'], 'Original source changed during evaluation')
        record.update(execution_status='PASS', exit_code=0, source_preservation_status='PASS',
                      finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      outputs_sha256={p:digest(directory/p) for p in ('ledger.json','common/metadata.json','common/arrays.bin','local-g0.json','comparison.json')})
        save_completion(directory,record,fixed_summary)
    except BaseException as error:
        # New safe primitive fields, never propagate malformed worker nested objects.
        failure = initial_record(directory.name)
        failure.update(execution_status='BLOCKED_MISSING_SOURCE' if 'Missing bound source' in str(error) or 'BLOCKED_MISSING_SOURCE' in str(error) else 'FAIL',
                       reason=type(error).__name__+': '+str(error),
                       historical_energy_ledger_status='SAVED_INDEPENDENT_RESULT' if (directory/'ledger.json').is_file() else 'NOT_RUN')
        try:
            save_completion(directory,failure,fixed_summary)
        except BaseException:
            print('Persistence failed; current attempt FAIL, exit 9',file=sys.stderr)
        print(failure['reason'],file=sys.stderr)
        return 9
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--directory',type=Path,help='New ignored directory; defaults to unique .work/phase7d run_id')
    parser.add_argument('--julia',default='julia')
    args=parser.parse_args()
    root=args.root.resolve()
    runid=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ-')+uuid.uuid4().hex[:8]
    directory=(args.directory or root/'.work/phase7d'/runid).resolve()
    if directory.exists():
        print('Refusing an existing run directory; prior evidence preserved',file=sys.stderr)
        return 9
    try:
        code=execute(root,directory,args.julia)
    except OSError as error:
        print('Persistence failed; no successful run: '+type(error).__name__,file=sys.stderr)
        return 9
    print(str(directory/'result.json'))
    return code


if __name__ == '__main__':
    sys.exit(main())
