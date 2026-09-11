#!/usr/bin/env python3
"""Offline replay of the first Mg QE SOC comparison from public native evidence.

No solver, UPF, Julia, private archive or network is used. Exact new arithmetic
is checked with Python 3.12; historical Phase 6C values are never regenerated.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import tempfile

from parse_qe_soc import parse_qe_soc
from compare_qe_soc import compare, compare_refinement, load_historical, write_eigenvalues_csv

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = 'results/mg-soc-qe-comparison'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def summary(comparison):
    result = copy.deepcopy(comparison)
    for value in result['comparisons'].values():
        del value['spectrum']['rows']
    return result


def check(root=ROOT):
    root = Path(root)
    directory = root / DIRECTORY
    evidence = json.loads((directory / 'evidence.json').read_text())
    require(evidence['schema_version'] == 1, 'Unsupported evidence schema')
    require(evidence['case'] == 'mg-soc-qe-v1', 'Wrong current case')
    require(evidence['default_publication_status'] == 'PASS', 'Default publication not established')
    require(evidence['base_commit'] == evidence['publication']['published_main_sha'], 'Wrong development base')
    require(evidence['qe_execution_status'] == 'PASS' and evidence['process']['exit_code'] == 0,
            'No successful current QE process')
    require(evidence['historical_reference_status'] == 'HISTORICAL_REUSED', 'Historical run mislabeled')
    require(evidence['numerical_agreement_status'] == 'REVIEW_REQUIRED', 'External agreement not adjudicated')
    require(evidence['physical_convergence_status'] == 'NOT_ESTABLISHED', 'Physical convergence not established')
    require(evidence['run_id'] == evidence['process']['run_id'], 'Current process run identity differs')
    for path, expected in evidence['public_sha256'].items():
        require(digest(root / path) == expected, 'Public source hash mismatch: ' + path)
    for path, expected in evidence['verifier_sha256'].items():
        require(digest(root / path) == expected, 'Current verifier changed: ' + path)
    case = json.loads((root / evidence['case_config']['path']).read_text())
    require(digest(root / evidence['case_config']['path']) == evidence['case_config']['sha256'], 'Case hash mismatch')
    require(case['base_commit'] == evidence['base_commit'], 'Case base differs')
    original_path = root / 'benchmarks/mg-soc-qe-v1/case.predeclared.json'
    require(digest(original_path) == evidence['predeclaration']['case_sha256'], 'Original predeclaration changed')
    original_case = json.loads(original_path.read_text())
    require(original_case['xc']['qe_indices'] == [1,1,10,8] and case['xc']['qe_indices'] == [1,4,10,8],
            'Unexpected metadata erratum')
    corrected = copy.deepcopy(original_case)
    corrected['xc']['qe_indices'] = [1,4,10,8]
    require(corrected == case, 'Changes beyond the disclosed XC index metadata erratum')
    require(evidence['metadata_erratum']['physical_input_changed'] is False, 'Physical input changed')
    require(evidence['predeclaration']['qe_input_sha256'] == case['qe_input_sha256'], 'Predeclared QE input changed')
    require(evidence['predeclaration']['fresh_scratch'] is True, 'SCF scratch was not new')
    require(evidence['predeclaration']['saved_utc'] < evidence['process']['started_utc'], 'Rules were not saved before execution')
    pseudo = evidence['input_receipt']
    require(pseudo['before_sha256'] == pseudo['after_sha256'] == case['pseudo']['sha256'], 'Input byte receipt mismatch')
    identity = evidence['qe_identity']
    require(identity['source_commit'] is None and identity['startup_version'] == '7.5', 'Unsupported or invented QE identity')
    require(identity['binary_sha256'] == evidence['process']['binary_sha256_after'], 'Executable changed during run')
    verified_case = dict(case, verified_pseudo_sha256=pseudo['after_sha256'])
    qe = parse_qe_soc(directory / 'qe-data-file-schema.xml', directory / 'qe.stdout', verified_case,
                       process_exit_code=evidence['process']['exit_code'], calculation='scf')
    require(qe == json.loads((directory / 'qe-result.json').read_text()), 'Published QE parse differs from native evidence')
    a,b = load_historical(root, case)
    result = compare(case, qe, a, b)
    require(summary(result) == json.loads((directory / 'comparison.json').read_text()), 'Comparison summary differs')
    with tempfile.TemporaryDirectory() as temporary:
        csv = Path(temporary) / 'eigenvalues.csv'
        write_eigenvalues_csv(csv, result)
        require(csv.read_bytes() == (directory / 'eigenvalues.csv').read_bytes(), 'Full eigenvalue table differs')
    refinement = evidence['refinement']
    require(refinement['source_scf_run_id'] == evidence['run_id'] and refinement['exit_code'] == 0,
            'Refinement source/exit differs')
    require(refinement['energy_source'] == 'SCF only', 'Refinement cannot replace SCF energy')
    require(refinement['source_preservation']['status'] == 'PASS', 'Source SCF was modified')
    require(refinement['predeclaration']['saved_utc'] < refinement['started_utc'], 'Refinement not predeclared')
    require(digest(root / refinement['input_path']) == refinement['input_sha256'] ==
            refinement['predeclaration']['qe_input_sha256'], 'Refinement input changed')
    refined = parse_qe_soc(directory / 'qe-refinement-data-file-schema.xml',
                           directory / 'qe-refinement.stdout', verified_case, process_exit_code=0, calculation='bands')
    require(refined == json.loads((directory / 'qe-refinement-result.json').read_text()), 'Refinement parse differs')
    refined_comparison = compare_refinement(case, qe, refined, a, b)
    require(summary(refined_comparison) == json.loads((directory / 'comparison-refinement.json').read_text()),
            'Refinement comparison differs')
    with tempfile.TemporaryDirectory() as temporary:
        csv = Path(temporary) / 'refined.csv'
        write_eigenvalues_csv(csv, refined_comparison)
        require(csv.read_bytes() == (directory / 'eigenvalues-refinement.csv').read_bytes(), 'Refined eigenvalue table differs')
    require(evidence['comparison_execution_status'] == result['comparison_execution_status'], 'Comparison status differs')
    return {'status': 'PASS', 'case': case['case'], 'run_id': evidence['run_id'],
            'scope': 'Public QE native parse and E/F/entropy/spectral arithmetic; no physical rerun',
            'historical_reference_status': 'HISTORICAL_REUSED', 'spectral_rows': {'SCF': 144, 'refinement': 144},
            'numerical_agreement_status': 'REVIEW_REQUIRED',
            'not_run': ['SCF/QE', 'DFTK density/orbital arrays', 'cross-code density L2', 'physical convergence']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = check(args.root)
    except Exception as error:
        print(json.dumps({'status': 'FAIL', 'reason': str(error), 'error_type': type(error).__name__}))
        return 1
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
