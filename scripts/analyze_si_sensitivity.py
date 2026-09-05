#!/usr/bin/env python3
"""Analyze only B0/C1/C2/C3: independent G=0 prediction and finite sensitivities.

No SCF execution, fitted constant, or total-energy correction is performed here.
The independent C input comes from inspect_si_reference.py, never from a spectrum.
"""
import argparse
import copy
import csv
import json
import math
from pathlib import Path

from compare_scalar_baseline import (HARTREE_EV, compare, finite_tree, same_point,
                                     statistics, validate_result, volume)
from parse_qe_baseline import parse_qe
from run_scalar_baseline import check_reference_environment, sha256

BASE_COMMIT = 'f05e6d70750f10d5ea87ebb9f7c6a5ec993c7063'
B0_RUN_ID = '20260905T040945688395Z-1cc8a50c'
MATRIX = {'B0': (30, 8), 'C1': (40, 8), 'C2': (50, 8), 'C3': (50, 64)}
ROOT = Path(__file__).resolve().parents[1]


def load_json(path):
    result = json.loads(path.read_text())
    finite_tree(result)
    return result


def grouped_statistics(rows, key):
    return {name: statistics([row[key] for row in group])
            for name, group in [('all', rows),
                                ('occupied', [r for r in rows if r['occupation'] > 0]),
                                ('empty', [r for r in rows if r['occupation'] == 0])]}


def reference_diagnostic(comparison, constant):
    """epsilon_D-epsilon_Q is predicted to be -C; residual is raw delta + C."""
    if type(constant) not in (int, float) or not math.isfinite(constant):
        raise ValueError('Independent C must be a finite number')
    result = copy.deepcopy(comparison)
    for row in result['eigenvalues']:
        row['independent_C_residual_ha'] = row['delta_ha'] + constant
    result['independent_reference'] = {
        'C_ha': constant, 'predicted_delta_DFTK_minus_QE_ha': -constant,
        'evidence_level': 'SOURCE_CONVENTION_AND_RAW_UPF_PREDICTION',
        'qe_internal_G0_value_directly_extracted': False,
        'residual_formula': 'epsilon_DFTK - epsilon_QE + C_independent',
        'total_energy_changed': False,
        'summary': grouped_statistics(result['eigenvalues'], 'independent_C_residual_ha'),
        'signed_residual_range_ha': [min(r['independent_C_residual_ha'] for r in result['eigenvalues']),
                                     max(r['independent_C_residual_ha'] for r in result['eigenvalues'])]}
    return result


def common_points(requested, actual):
    """Extract a prescribed subset by coordinates, without output-order matching."""
    # Reject duplicates anywhere, including in the part not selected for comparison.
    for i, point in enumerate(actual):
        if any(same_point(point['coordinate_fractional'], p['coordinate_fractional'])
               for p in actual[:i]):
            raise ValueError('Duplicate k point in full result')
    selected, used = [], set()
    for point in requested:
        matches = [i for i, p in enumerate(actual)
                   if same_point(point['coordinate_fractional'], p['coordinate_fractional'])]
        if len(matches) != 1 or matches[0] in used:
            raise ValueError('Missing or duplicate requested common k point')
        used.add(matches[0])
        selected.append(actual[matches[0]])
    return selected


def setting_change(before_case, before, after_case, after, engine):
    """One Gamma highest-occupied reference per solution, for all shared k points.

    We use this same prescription for both cutoff and k-grid changes. Cross-code
    comparisons separately retain the Phase 4B sampled-global-HOMO prescription.
    """
    bp = validate_result(before_case, before, engine)
    ap = validate_result(after_case, after, engine)
    selected = common_points(before_case['kpoints'], ap)
    no = before_case['electrons']['n_occupied']
    gamma = [{'coordinate_fractional': [0, 0, 0]}]
    refs = [common_points(gamma, points)[0]['eigenvalues_ha'][no - 1] for points in (bp, ap)]
    rows = []
    for point, b, a in zip(before_case['kpoints'], bp, selected):
        for ib, (eb, ea) in enumerate(zip(b['eigenvalues_ha'], a['eigenvalues_ha'])):
            rows.append({'k_fractional': point['coordinate_fractional'], 'band': ib + 1,
                         'occupation': b['occupations'][ib], 'before_ha': eb, 'after_ha': ea,
                         'raw_delta_ha': ea - eb,
                         'before_gamma_reference_ha': eb - refs[0],
                         'after_gamma_reference_ha': ea - refs[1],
                         'gamma_reference_delta_ha': (ea - refs[1]) - (eb - refs[0])})
    delta = after['energy_ha'] - before['energy_ha']
    nat = len(before_case['geometry']['species'])
    return {'engine': engine, 'delta_convention': 'after minus before',
            'common_kpoint_count': len(bp), 'reference_location_fractional': [0, 0, 0],
            'reference_definition': 'Gamma highest occupied level; ONE reference per full solution',
            'reference_before_ha': refs[0], 'reference_after_ha': refs[1],
            'reference_delta_ha': refs[1] - refs[0],
            'total_energy': {'before_ha_cell': before['energy_ha'], 'after_ha_cell': after['energy_ha'],
                             'delta_ha_cell': delta, 'delta_ev_cell': delta * HARTREE_EV,
                             'delta_mev_atom': delta * HARTREE_EV * 1000 / nat},
            'raw_summary': grouped_statistics(rows, 'raw_delta_ha'),
            'gamma_reference_summary': grouped_statistics(rows, 'gamma_reference_delta_ha'),
            'eigenvalues': rows}


def check_matrix_case(case, baseline, label):
    cutoff, count = MATRIX[label]
    if (case['cutoffs'] != {'dftk_ecut_ha': cutoff, 'qe_ecutwfc_ry': 2 * cutoff,
                           'qe_ecutrho_ry': 8 * cutoff} or len(case['kpoints']) != count):
        raise ValueError('Result does not belong to requested matrix setting ' + label)
    for key in ('geometry', 'xc', 'pseudo', 'electrons', 'scf', 'dftk', 'qe', 'runtime'):
        if case[key] != baseline[key]:
            raise ValueError('Unexpected physical configuration change: ' + label + '.' + key)
    common_points(baseline['kpoints'], case['kpoints'])


def check_independent_reference(reference, baseline_path):
    if (type(reference.get('schema_version')) is not int or reference['schema_version'] != 1
            or reference.get('reference_inspection_status') != 'PASS'
            or any(reference.get(key) is not False for key in
                   ('spectral_data_used', 'dftk_correction_called', 'scf_total_energy_modified'))
            or reference.get('case_sha256') != sha256(baseline_path)):
        raise ValueError('Independent reference contract or historical case hash mismatch')


def check_historical_hashes(directory, manifest):
    prefix = '<workbench>/.work/scalar-baseline/' + B0_RUN_ID + '/'
    for item in manifest['files']:
        if not item['raw_path'].startswith(prefix):
            raise ValueError('Unexpected historical manifest path')
        path = directory / item['raw_path'][len(prefix):]
        if sha256(path) != item['raw_sha256']:
            raise ValueError('Accepted historical raw hash mismatch: ' + item['file'])


def read_run(directory, label):
    record = load_json(directory / 'result.json')
    if (record['execution_status'] != 'PASS' or record['input_comparability_status'] != 'PASS'
            or record['exit_code'] != 0 or record['run_id'] != directory.name):
        raise ValueError('Requested current run is not successful: ' + label)
    case = load_json(directory / 'case.json')
    for filename, field in [('case.json', 'case_sha256'), ('dftk-input.json', 'dftk_input_sha256'),
                            ('qe.in', 'qe_input_sha256')]:
        if sha256(directory / filename) != record['inputs'][field]:
            raise ValueError('Run input hash mismatch: ' + label + '/' + filename)
    if sha256(directory / 'pseudo' / case['pseudo']['filename']) != case['pseudo']['sha256']:
        raise ValueError('Run UPF hash mismatch')
    dftk = load_json(directory / 'dftk-result.json')
    if (dftk['input_sha256'] != record['inputs']['dftk_input_sha256'] or
            dftk['case_sha256'] != record['inputs']['case_sha256']):
        raise ValueError('DFTK loaded a different input/configuration')
    for stream in ('qe.stdout', 'dftk.stdout'):
        commands = [entry for entry in record['commands'] if entry['stdout'] == stream]
        if len(commands) != 1 or commands[0]['exit_code'] != 0:
            raise ValueError('Actual engine command did not exit normally: ' + stream)
    qe = parse_qe(directory / 'qe/scratch/si.save/data-file-schema.xml',
                  (directory / 'qe/qe.stdout').read_text(), 0,
                  expected_n_kpoints=len(case['kpoints']))
    qe['pseudo_sha256'] = case['pseudo']['sha256']
    if qe != load_json(directory / 'qe-result.json'):
        raise ValueError('Reparsed QE result differs from saved result: ' + label)
    paired = compare(case, dftk, qe)
    if paired != load_json(directory / 'comparison.json'):
        raise ValueError('Recomputed paired comparison differs from saved result: ' + label)
    return case, dftk, qe, record, paired


def analyze(reference, directories):
    finite_tree(reference)
    check_historical_hashes(directories['B0'], load_json(
        ROOT / 'results/phase4b' / B0_RUN_ID / 'evidence-manifest.json'))
    check_independent_reference(reference, directories['B0'] / 'case.json')
    data = {label: read_run(directories[label], label) for label in MATRIX}
    baseline = data['B0'][0]
    if data['B0'][3]['run_id'] != B0_RUN_ID:
        raise ValueError('B0 must be the accepted Phase 4B historical run')
    if len({row[3]['run_id'] for row in data.values()}) != 4:
        raise ValueError('The three new settings require distinct fresh run IDs')
    if (reference['input_sha256'] != baseline['pseudo']['sha256'] or
            reference['n_atoms'] != 2 or abs(reference['volume_bohr3'] - volume(baseline['geometry']['lattice_vectors_bohr'])) > 1e-10):
        raise ValueError('Independent reference was computed for different physical inputs')
    constant = reference['C_ha']
    if abs(constant - reference['alpha_ha_bohr3'] * 2 / reference['volume_bohr3']) > 1e-14:
        raise ValueError('Independent C/alpha/count/volume relation is inconsistent')
    pairs, metadata = {}, {}
    for label, (case, d, q, record, paired) in data.items():
        check_matrix_case(case, baseline, label)
        check_reference_environment(record['environment'], record['qe_identity'], data['B0'][3])
        if record['qe_identity']['startup_version'] != data['B0'][3]['qe_identity']['startup_version']:
            raise ValueError('Actual QE version changed in sequence')
        pairs[label] = reference_diagnostic(paired, constant)
        correction = d['energy_components_ha']['PspCorrection']
        metadata[label] = {
            'run_id': record['run_id'], 'reuse_status': 'HISTORICAL_REUSED' if label == 'B0' else 'NEW_EXECUTION',
            'source_commit': BASE_COMMIT if label == 'B0' else None,
            'inputs': record['inputs'], 'n_kpoints': len(case['kpoints']), 'ecut_ha': case['cutoffs']['dftk_ecut_ha'],
            'PspCorrection_ha': correction, 'C_DFTK_ha': correction / d['n_electrons'],
            'C_independent_minus_DFTK_ha': constant - correction / d['n_electrons'],
            'fft_grid': {'DFTK': d['fft_grid'], 'QE': q['fft_grid'], 'QE_smooth': q['fft_smooth_grid']},
            'npw': {code: [p['npw'] for p in common_points(case['kpoints'], result['kpoints'])]
                    for code, result in [('DFTK', d), ('QE', q)]},
            'scf_iterations': {'DFTK': d['scf']['iterations'], 'QE': q['scf']['iterations']},
            'density_residual_DFTK': d['scf']['density_residual_history'][-1],
            'scf_error_QE_ha': q['scf']['error_ha'],
            'diagonalization_QE_threshold_ry': q['scf']['diagonalization_threshold_last_ry'],
            'DFTK_solver_residual_max_ha': max(max(row[:8]) for row in d['diagonalization']['residuals_ha']),
            'DFTK_explicit_residual_max_ha': d['diagonalization'].get('explicit_recomputed_residual_max_ha'),
            'raw_result_hashes': {name: sha256(directories[label] / name)
                                  for name in ('result.json', 'dftk-result.json', 'qe-result.json', 'comparison.json')}}
    changes = {}
    for old, new in [('B0', 'C1'), ('C1', 'C2'), ('C2', 'C3')]:
        changes[old + '_to_' + new] = {
            code: setting_change(data[old][0], data[old][index], data[new][0], data[new][index], code)
            for code, index in [('DFTK', 1), ('QE', 2)]}
    return {'schema_version': 1, 'execution_status': 'PASS', 'input_comparability_status': 'PASS',
            'numerical_agreement_status': 'REVIEW_REQUIRED',
            'reference_evidence_level': 'SOURCE_CONVENTION_AND_INDEPENDENT_RAW_UPF_INTEGRATION',
            'qe_internal_G0_direct_extraction_status': 'NOT_AVAILABLE',
            'cutoff_check_status': 'MEASURED_30_40_50_HA_AT_8_POINTS',
            'k_sensitivity_status': 'MEASURED_8_TO_64_POINTS_AT_50_HA',
            'full_kpoint_convergence_status': 'NOT_ESTABLISHED',
            'spinor_development_decision': 'REVIEW_REQUIRED',
            'independent_reference': reference, 'runs': metadata, 'paired_comparisons': pairs,
            'within_code_changes': changes}


def save_analysis(directory, result):
    directory.mkdir(parents=True, exist_ok=False)
    finite_tree(result)
    summary = copy.deepcopy(result)
    tables = list(summary['paired_comparisons'].items())
    tables += [(label + '_' + code, change) for label, changes in summary['within_code_changes'].items()
               for code, change in changes.items()]
    for name, block in tables:
        rows = block.pop('eigenvalues')
        block['eigenvalues_file'] = name + '.csv'
        with (directory / (name + '.csv')).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    # Full raw and referenced rows are in the named CSVs; avoid a second bulky copy.
    (directory / 'sensitivity.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    for label in MATRIX:
        parser.add_argument('--' + label.lower(), type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(load_json(args.reference), {label: getattr(args, label.lower()) for label in MATRIX})
    save_analysis(args.output, result)
    print('Analysis saved; numerical agreement and spinor decision remain REVIEW_REQUIRED')


if __name__ == '__main__':
    main()
