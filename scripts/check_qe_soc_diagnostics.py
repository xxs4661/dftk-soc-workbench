#!/usr/bin/env python3
"""Public-only replay of Phase 7B; no .save, UPF, Julia, QE or private archive.

The old publication checker is byte-frozen by Phase 7A evidence. --all invokes
it unchanged under the requested Python 3.9, then checks this new case here.
"""
import argparse
import datetime
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from run_qe_soc_diagnostics import ORDER, BASE, CASE_DIR, digest, require, validate_plan, slot_case, object_hash
from parse_qe_soc_diagnostics import parse_qe_soc_diagnostics
from check_qe_soc_evidence import check as check_old

ROOT = Path(__file__).resolve().parents[1]
RESULTS = 'results/mg-soc-qe-diagnostics'


def check_receipt(plan, slot, receipt):
    require(receipt['slot'] == slot and receipt['run_id'].split('-')[-2] == slot, 'Run identity/slot mismatch')
    require(receipt['input_path'] == plan['slots'][slot]['input_path'] and
            receipt['input_sha256'] == plan['slots'][slot]['input_sha256'], 'Run input differs from slot')
    require(receipt['plan_sha256'] == receipt['preflight']['plan_sha256'], 'Preflight plan changed')
    if receipt.get('execution_status','PASS') != 'PASS':
        require(receipt['execution_status'] in ('FAIL','BLOCKED') and bool(receipt.get('reason'))
                and receipt.get('recorder_exit_code',9) != 0, 'Failed receipt has no explicit nonpassing reason')
        return
    require(receipt.get('recorder_exit_code') == 0, 'Successful receipt has nonzero/missing recorder exit')
    for value in (plan['saved_utc'],receipt['preflight']['saved_utc'],receipt.get('started_utc'),receipt.get('finished_utc')):
        require(isinstance(value,str) and datetime.datetime.fromisoformat(value).tzinfo is not None,
                'Successful receipt lacks a complete UTC-aware timing record')
    if slot in ('I36','G40'):
        require(receipt['source_binding'].get('fresh_scratch') is True, 'Fresh initialization/SCF source is not established')
    if receipt.get('started_utc') is not None:
        require(plan['saved_utc'] < receipt['preflight']['saved_utc'] < receipt['started_utc'], 'Input was not predeclared')
        require(receipt['finished_utc'] >= receipt['started_utc'], 'Completion precedes start')
        require(receipt['process_interrupted'] is False, 'Interrupted process cannot enter a successful comparison')
    for key, expected in plan['qe_identity'].items():
        require(receipt['qe_identity'][key] == expected, 'Run QE identity mismatch: ' + key)
    require(receipt['pseudo_before_sha256'] == receipt['pseudo_after_sha256'] == plan['pseudo']['sha256'], 'UPF identity changed')
    require(receipt['source_preservation_status'] == 'PASS', 'Protected historical source changed')
    require(receipt['thread_environment'] == {k:'1' for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS',
            'MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','JULIA_NUM_THREADS')}, 'Conservative launch limits changed')


def check_native_execution(stdout):
    require(re.findall(r'Parallel version \(MPI\), running on\s+(\d+) processors',stdout) == ['1'],
            'Native MPI process count differs from the one-process plan')
    require(re.findall(r'MPI processes distributed on\s+(\d+) nodes',stdout) == ['1'],
            'Native MPI node count differs from plan')
    require('a serial algorithm will be used' in stdout, 'Native serial subspace setting not established')


def check_source_binding(slot, receipt, snapshots):
    if slot[0] not in 'DC' or receipt['execution_status'] != 'PASS':
        return
    name = 'Q36' if slot.endswith('36') else 'G40'
    source = snapshots[name]
    binding = receipt['source_binding']
    files = source['save_sha256']
    require(binding['source_run_id'] == source['run_id'] and binding['source_slot'] == name,
            'Fixed-density source identity differs')
    require(binding['source_snapshot_sha256'] == object_hash(files), 'Starting snapshot differs from original source receipt')
    require(binding['charge_before_sha256'] == binding['charge_after_sha256'] == files['charge-density.dat'],
            'Charge hash changed or differs from original source')
    require(binding['initial_wfc_sha256'] == {p:sha for p,sha in files.items() if p.startswith('wfc')},
            'Initial orbitals differ from original source snapshot')


def check(root=ROOT):
    from compare_qe_soc_diagnostics import analyze, payload_sha256, summary, write_differences_csv
    root = Path(root)
    directory = root / RESULTS
    evidence = json.loads((directory/'evidence.json').read_text())
    require(evidence['schema_version'] == 1 and evidence['case'] == 'mg-soc-qe-diagnostics-v1', 'Unsupported case schema')
    require(evidence['base_commit'] == BASE, 'Wrong base')
    plan = json.loads((root/CASE_DIR/'plan.json').read_text())
    validate_plan(root,plan)
    plan_hash = digest(root/CASE_DIR/'plan.json')
    require(plan_hash == evidence['plan_sha256'], 'Plan hash changed')
    require(set(evidence['run_slots']) == set(ORDER), 'Missing/extra slot receipt')
    for path, sha in evidence['public_sha256'].items():
        require(digest(root/path) == sha, 'Public evidence changed: '+path)
    for path, sha in evidence['verifier_sha256'].items():
        require(digest(root/path) == sha, 'Diagnostic verifier changed: '+path)
    old = check_old(root)
    canonical = json.loads((directory/'canonical.json').read_text())
    require(set(canonical) == set(ORDER), 'Missing/extra canonical slot')
    previous_end = None
    for slot in ORDER:
        receipt = evidence['run_slots'][slot]
        check_receipt(plan,slot,receipt)
        if receipt.get('started_utc') is not None:
            require(previous_end is None or previous_end <= receipt['started_utc'], 'Slot execution order overlaps or differs')
            previous_end = receipt['finished_utc']
        check_source_binding(slot,receipt,evidence['source_snapshots'])
        require(receipt['plan_sha256'] == plan_hash, 'Execution plan differs')
        record = canonical[slot]
        require(record['run_id'] == receipt['run_id'], 'Canonical run ID differs')
        require(record['execution_status'] == receipt['execution_status'], 'Canonical execution status differs')
        # Failed native artifacts must remain listed and hash checked too. They
        # are never replaced by a convenient previous run or called valid data.
        files = receipt['native_files']
        if receipt.get('started_utc') is not None:
            require({'stdout','stderr'} <= files.keys(), 'Started run lost a native stream')
        for kind, item in files.items():
            require(digest(root/item['public_path']) == item['public_sha256'], 'Missing/bad native '+slot+'/'+kind)
            require(item['public_path'] in evidence['public_sha256'], 'Native source omitted from public whitelist')
        if record['execution_status'] not in ('PASS',):
            require(record.get('reason') and record.get('exit_code',9) != 0, 'Failed slot lacks a nonpassing reason')
            continue
        require(set(files) == {'xml','stdout','stderr'}, 'Successful slot missing native streams')
        check_native_execution((root/files['stdout']['public_path']).read_text())
        case = slot_case(plan,slot)
        case['verified_pseudo_sha256'] = receipt['pseudo_after_sha256']
        parsed = parse_qe_soc_diagnostics(*(root/files[k]['public_path'] for k in ('xml','stdout','stderr')),
                                         case,slot,process_exit_code=receipt['process_exit_code'])
        parsed.update(run_id=receipt['run_id'],source_binding=receipt['source_binding'])
        if slot != 'I36':
            parsed['parsed_payload_sha256'] = payload_sha256(parsed)
        require(parsed == record, 'Canonical record differs from all native bytes: '+slot)
    result = analyze(root,plan,canonical)
    require(summary(result) == json.loads((directory/'comparison.json').read_text()), 'Diagnostic arithmetic differs')
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp)/'differences.csv'
        write_differences_csv(target,result)
        require(target.read_bytes() == (directory/'differences.csv').read_bytes(), 'Full signed difference table differs')
    for doc in ('README.md','docs/status.md','results/README.md','benchmarks/README.md','scripts/README.md'):
        require('mg-soc-qe-diagnostics' in (root/doc).read_text(), 'New case missing from current navigation: '+doc)
    require(evidence['numerical_agreement_status'] == 'REVIEW_REQUIRED' and
            evidence['physical_convergence_status'] == 'NOT_ESTABLISHED' and
            evidence['warning_origin_status'] == 'NOT_LOCALIZED', 'Unresolved status was silently closed')
    return {'status':'PASS','scope':'Public native reparse and signed arithmetic, not physical rerun or private-array validation',
            'case':plan['case'],'historical_7a_replay':old['status'],
            'slot_execution_status':{s:canonical[s]['execution_status'] for s in ORDER},
            'numerical_agreement_status':'REVIEW_REQUIRED','physical_convergence_status':'NOT_ESTABLISHED',
            'warning_origin_status':'NOT_LOCALIZED'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--all',action='store_true',help='Run unchanged historical publication check first')
    parser.add_argument('--legacy-python',default=shutil.which('python3.9') or '/usr/bin/python3')
    args = parser.parse_args()
    try:
        if args.all:
            completed = subprocess.run([args.legacy_python,str(args.root/'scripts/check_publication.py'),
                '--root',str(args.root),'--modern-python',sys.executable],capture_output=True,text=True)
            require(completed.returncode == 0,'Historical publication check failed: '+completed.stdout+completed.stderr)
        print(json.dumps(check(args.root),indent=2,allow_nan=False))
        return 0
    except Exception as error:
        print(json.dumps({'status':'FAIL','error_type':type(error).__name__,'reason':str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
