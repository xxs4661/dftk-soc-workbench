#!/usr/bin/env python3
"""Offline public Fourier/Hartree replay: standard library, no private arrays.

--all additionally invokes the byte-frozen Phase 7B/7A/publication checks with
their existing interpreter split. No Julia, QE or network is started.
"""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

from compare_density_hartree import analyze_density_hartree, read_coefficients_gzip, TOLERANCES
from run_density_hartree_audit import digest, load, require, PLAN

ROOT = Path(__file__).resolve().parents[1]
RESULTS = 'results/mg-soc-density-hartree'


def historical_values(root):
    endpoints = {label: load(root / ('results/mg-soc-scf/' + label + '/endpoint.json')) for label in ('A', 'B')}
    qe = load(root / 'results/mg-soc-qe-diagnostics/canonical.json')['G40']['energy']
    hartree = {k+'_out': v['diagnostics']['energy_terms_ha']['Hartree'] for k,v in endpoints.items()}
    # These are previously public native values, not fitted from new coefficients.
    totals = {k+'_out': v['diagnostics']['internal_energy_ha'] for k,v in endpoints.items()}
    hartree['QE'] = qe['native_components_ha']['ehart']
    totals['QE'] = qe['internal_ha']
    return hartree, totals


def analyze_public(root, datasets):
    plan = load(root / PLAN)
    h, total = historical_values(root)
    states = {'A_out':'BOUND_N_OUT_ENERGY_STATE', 'B_out':'BOUND_N_OUT_ENERGY_STATE',
              'QE':'BOUND_SAVED_OUTPUT_RHO_TAGGED_SOURCE_CONVENTION'}
    result = analyze_density_hartree(datasets, plan['lattice_vectors_bohr'],
            {key:plan['fft_size'] for key in datasets}, historical_hartree_ha=h,
            expected_electrons=plan['expected_electrons'], state_bindings=states,
            historical_total_energies_ha=total)
    for key in ('A_out_minus_A_in','B_out_minus_B_in'):
        result['comparisons'].pop(key, None)
    result['in_only_scope'] = 'Not published; complete in/out closure and n_in EH remain local-array runner measurements'
    return result


def equivalent(actual, expected, path='comparison'):
    """Stable sums can differ in last bits across Python/libm; never refit inputs."""
    if isinstance(actual, dict):
        require(isinstance(expected, dict) and actual.keys() == expected.keys(), 'Object fields differ: ' + path)
        for key in actual:
            equivalent(actual[key], expected[key], path + '/' + key)
    elif isinstance(actual, list):
        require(isinstance(expected, list) and len(actual) == len(expected), 'Array length differs: ' + path)
        for i,(left,right) in enumerate(zip(actual,expected)):
            equivalent(left,right,path+'/'+str(i))
    elif type(actual) is float:
        require(type(expected) in (float,int) and math.isfinite(actual) and math.isfinite(expected), 'Nonfinite value: '+path)
        # Source numbers/coefficients are hash-bound exactly. This is only a
        # replayed reduction tolerance, bounded by the predeclared energy gate.
        tolerance = 1e-10 if path.endswith('_ha') else 1e-12 + 1e-12*abs(expected)
        require(abs(actual-expected) <= tolerance, 'Numerical replay differs: '+path)
    else:
        require(type(actual) is type(expected) and actual == expected, 'Value differs: '+path)


def check(root=ROOT):
    root = Path(root)
    plan = load(root / PLAN)
    evidence = load(root / RESULTS / 'evidence.json')
    require(evidence['schema_version'] == 1 and evidence['case'] == plan['case'], 'Wrong audit case/schema')
    require(evidence['base_commit'] == plan['base_commit'] and evidence['plan_sha256'] == digest(root / PLAN), 'Plan/base changed')
    for path, sha in {**plan['source_evidence_sha256'], **plan['frozen_environment_sha256'],
                      **evidence['public_sha256'], **evidence['verifier_sha256']}.items():
        require(digest(root / path) == sha, 'Bound public file changed: '+path)
    for label in ('A','B','G40'):
        source=evidence['sources'][label]
        require(source['run_id'] == plan['sources'][label]['run_id'], 'Wrong historical source ID')
        require(source['raw_source_binding_status'] == 'PASS' and source['source_preservation_status'] == 'PASS',
                'Source extraction binding/preservation did not pass')
        expected=plan['sources'][label]['checkpoint']['sha256'] if label!='G40' else \
                 plan['sources']['G40']['files']['scratch/mg_soc_qe_v1.save/charge-density.dat']['sha256']
        require(source['raw_sha256'] == expected, 'Wrong raw density source hash')
    require(evidence['new_scf_status'] == evidence['new_eigensolve_status'] == 'NOT_RUN', 'Unexpected scientific execution')
    dftk = read_coefficients_gzip(root / RESULTS / 'dftk-nout.csv.gz')
    qe = read_coefficients_gzip(root / RESULTS / 'qe-rho.csv.gz')
    require(set(dftk) == {'A_out','B_out'} and set(qe) == {'QE'}, 'Missing/wrong canonical density labels')
    require(all(len(c)==64000 for c in dftk.values()) and len(qe['QE'])==22119, 'Native supports are incomplete')
    result = analyze_public(root, {**dftk, **qe})
    equivalent(result, load(root / RESULTS / 'comparison.json'))
    require(result['engineering_status'] == 'PASS', 'Public arithmetic engineering gate failed')
    # Exact unit/threshold mapping is audited; no late tolerance choice.
    require(TOLERANCES['electron_abs'] == plan['thresholds']['electron_count_abs'] and
            TOLERANCES['self_hartree_abs_ha'] == plan['thresholds']['self_hartree_abs_ha'] and
            TOLERANCES['energy_identity_abs_ha'] == plan['thresholds']['decomposition_abs_ha'], 'Tolerance drift')
    require(evidence['numerical_agreement_status']=='REVIEW_REQUIRED' and
            evidence['physical_convergence_status']=='NOT_ESTABLISHED' and
            evidence['residual_attribution_status']=='NOT_ESTABLISHED' and
            evidence['ieee_warning_origin_status']=='NOT_LOCALIZED', 'Unresolved scientific status changed')
    for doc in ('README.md','docs/status.md','results/README.md','benchmarks/README.md','scripts/README.md'):
        require('mg-soc-density-hartree' in (root / doc).read_text(), 'Current navigation missing: '+doc)
    return {'status':'PASS', 'case':plan['case'], 'public_coefficient_replay_status':'PASS',
            'scope':'All native coefficients, common complex density/Poisson differences and Hartree arithmetic; source extraction is separately runner-bound',
            'numerical_agreement_status':'REVIEW_REQUIRED', 'new_scf_status':'NOT_RUN','new_eigensolve_status':'NOT_RUN'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--all',action='store_true')
    parser.add_argument('--legacy-python',default='/usr/bin/python3')
    args=parser.parse_args()
    try:
        if args.all:
            completed=subprocess.run([sys.executable,str(args.root/'scripts/check_qe_soc_diagnostics.py'),
                '--root',str(args.root),'--all','--legacy-python',args.legacy_python],capture_output=True,text=True)
            require(completed.returncode==0,'Historical replay failed: '+completed.stdout+completed.stderr)
        print(json.dumps(check(args.root),indent=2,allow_nan=False))
        return 0
    except Exception as error:
        print(json.dumps({'status':'FAIL','reason':str(error)}))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
