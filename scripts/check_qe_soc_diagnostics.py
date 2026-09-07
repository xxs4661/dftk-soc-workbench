#!/usr/bin/env python3
"""Public-only replay of Phase 7B; no .save, UPF, Julia, QE or private archive.

The old publication checker is byte-frozen by Phase 7A evidence. --all invokes
it unchanged under the requested Python 3.9, then checks this new case here.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from run_qe_soc_diagnostics import ORDER, BASE, CASE_DIR, digest, require, validate_plan, slot_case
from parse_qe_soc_diagnostics import parse_qe_soc_diagnostics
from check_qe_soc_evidence import check as check_old

ROOT = Path(__file__).resolve().parents[1]
RESULTS = 'results/mg-soc-qe-diagnostics'


def check_receipt(plan, slot, receipt):
    require(receipt['slot'] == slot and receipt['run_id'].split('-')[-2] == slot, 'Run identity/slot mismatch')
    require(receipt['input_path'] == plan['slots'][slot]['input_path'] and
            receipt['input_sha256'] == plan['slots'][slot]['input_sha256'], 'Run input differs from slot')
    require(receipt['plan_sha256'] == receipt['preflight']['plan_sha256'], 'Preflight plan changed')
    if receipt.get('started_utc') is not None:
        require(plan['saved_utc'] < receipt['preflight']['saved_utc'] < receipt['started_utc'], 'Input was not predeclared')
        require(receipt['finished_utc'] >= receipt['started_utc'], 'Completion precedes start')
        require(receipt['process_interrupted'] is False, 'Interrupted process cannot enter a successful comparison')
    for key, expected in plan['qe_identity'].items():
        require(receipt['qe_identity'][key] == expected, 'Run QE identity mismatch: ' + key)
    require(receipt['pseudo_before_sha256'] == receipt['pseudo_after_sha256'] == plan['pseudo']['sha256'], 'UPF identity changed')
    require(receipt['source_preservation_status'] == 'PASS', 'Protected historical source changed')


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
    for slot in ORDER:
        receipt = evidence['run_slots'][slot]
        check_receipt(plan,slot,receipt)
        require(receipt['plan_sha256'] == plan_hash, 'Execution plan differs')
        record = canonical[slot]
        require(record['run_id'] == receipt['run_id'], 'Canonical run ID differs')
        require(record['execution_status'] == receipt['execution_status'], 'Canonical execution status differs')
        # Failed native artifacts must remain listed and hash checked too. They
        # are never replaced by a convenient previous run or called valid data.
        files = receipt['native_files']
        for kind, item in files.items():
            require(digest(root/item['public_path']) == item['public_sha256'], 'Missing/bad native '+slot+'/'+kind)
            require(item['public_path'] in evidence['public_sha256'], 'Native source omitted from public whitelist')
        if record['execution_status'] not in ('PASS',):
            require(record.get('reason') and record.get('exit_code',9) != 0, 'Failed slot lacks a nonpassing reason')
            continue
        require(set(files) == {'xml','stdout','stderr'}, 'Successful slot missing native streams')
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
