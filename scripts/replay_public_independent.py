#!/usr/bin/env python3
"""Single public Phase 7G independent replay; no production numerical imports.

Run the new synthetic tests first. The formal invocation belongs on the pinned
Linux runner, with a read-only baseline checkout and a fresh output directory.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import traceback
import xml.etree.ElementTree as ET

import numpy as np

import independent_orbital_io as public_io
import independent_orbital_math as numerical


class GateFailure(ValueError):
    pass


class Checks:
    """Measured results remain in the receipt even when a stage fails."""
    def __init__(self, thresholds, records):
        self.thresholds = thresholds
        self.records = records

    def exact(self, name, actual, expected):
        okay = actual == expected
        self.records.append({'name': name, 'status': 'PASS' if okay else 'FAIL',
                             'contract': 'EXACT', 'actual': actual, 'expected': expected})
        return okay

    def bound(self, name, error, threshold, **details):
        limit = self.thresholds[threshold] if isinstance(threshold, str) else threshold
        error = float(error)
        okay = math.isfinite(error) and abs(error) <= limit
        self.records.append({'name': name, 'status': 'PASS' if okay else 'FAIL',
                             'error': error if math.isfinite(error) else str(error),
                             'absolute_limit': limit, 'threshold_key': threshold,
                             **details})
        return okay

    def compare(self, name, actual, expected, threshold, **details):
        a, b = np.asarray(actual), np.asarray(expected)
        if a.shape != b.shape:
            return self.exact(name + '.shape', list(a.shape), list(b.shape))
        difference = np.abs(a - b)
        worst = int(np.argmax(difference)) if difference.size else 0
        return self.bound(name, float(difference.flat[worst]) if difference.size else 0., threshold,
                          items=int(difference.size), worst_flat_index=worst, **details)

    def checkpoint(self, stage):
        failed = [x['name'] for x in self.records if x['status'] == 'FAIL']
        if failed:
            raise GateFailure(stage + ': ' + ', '.join(failed))


def initial_report(plan):
    return {
        'schema_version': 1, 'phase': '7G', 'path': 'I', 'status': 'NOT_RUN',
        'input_commit': plan['input_commit'], 'started_utc': datetime.now(timezone.utc).isoformat(),
        'public_input_identity_status': 'NOT_RUN', 'independent_implementation_status': 'NOT_RUN',
        'Q_full_public_numeric_replay_status': 'NOT_RUN', 'A_B_replay_scope': 'SCALAR_AND_PROJECTED_ONLY',
        'native_QE_nonlocal_status': 'NOT_MEASURED', 'original_Q_H_input_residual_status': 'NOT_AVAILABLE',
        'physical_convergence_status': 'NOT_ESTABLISHED', 'ieee_origin_status': 'NOT_LOCALIZED',
        'numerical_interpretation_status': 'REVIEW_REQUIRED',
        'not_run': ['SCF', 'eigensolve', 'occupation solve', 'QE/pp', 'Julia science', 'XC',
                    'P/D regeneration', 'physical convergence scan', 'full upstream physical suite'],
        'independence': plan['I'], 'checks': [], 'thresholds': plan['thresholds'],
        'units': 'Ha/cell, electron, bohr; density electron/bohr^3',
        'historical_dense_difference_status': 'NOT_AVAILABLE: historical derived node arrays are not public',
        'input_bytes_after_status': 'NOT_RUN', 'array_bytes_after_status': 'NOT_RUN',
    }


def checked_json(root, plan, relative):
    if relative not in plan['input_sha256']:
        raise public_io.InputIdentityError('unknown historical source: ' + relative)
    return json.loads(public_io.source_path(root, relative).read_text())


def common_density_support(root, plan, saved_millers):
    """Read integer support only; A/B density values are not replayed here."""
    relative = 'results/mg-soc-density-hartree/dftk-nout.csv.gz'
    if relative not in plan['input_sha256']:
        raise public_io.InputIdentityError('unbound DFTK support source')
    support = set()
    with gzip.open(public_io.source_path(root, relative), 'rt', encoding='ascii') as stream:
        rows = csv.reader(stream)
        public_io.require(next(rows) == ['m1', 'm2', 'm3', 'A_out_real', 'A_out_imag',
                                        'B_out_real', 'B_out_imag'], 'DFTK support CSV header')
        count = 0
        for row in rows:
            public_io.require(len(row) == 7, 'DFTK support CSV row')
            support.add(tuple(int(x) for x in row[:3]))
            count += 1
            public_io.require(count <= math.prod(plan['physical']['fft_size']), 'DFTK support count limit')
    public_io.require(count == len(support) == math.prod(plan['physical']['fft_size']),
                      'DFTK full unique support')
    return np.array(sorted(support.intersection(map(tuple, saved_millers.tolist()))), dtype='<i8')


def validate_q(q, inputs, plan, gates):
    s, physical = q['summary'], plan['physical']
    historical = inputs['historical']['state_checks']['Q']
    gates.exact('Q.k_count', len(s['kpoints']), len(physical['kpoints']))
    gates.exact('Q.total_states', s['total_states'], len(physical['kpoints']) * physical['n_states'])
    gates.compare('Q.lattice', inputs['state']['lattice_columns'],
                  np.array(physical['lattice_vectors_bohr']).T, 'geometry_abs')
    gates.bound('Q.volume', s['volume_bohr3'] - physical['volume_bohr3'], 'geometry_abs')
    gates.bound('Q.reciprocal_duality', s['reciprocal_duality_frobenius'], 'geometry_abs')
    gates.bound('Q.weight_sum', s['weight_sum'] - 1, 'geometry_abs')
    gates.bound('Q.norms', s['norm_max_error'], 'norm_abs')
    gates.bound('Q.Gram', s['gram_max_frobenius'], 'gram_frobenius')
    gates.bound('Q.three_electron_counts', s['electrons_max_error'], 'electron_abs')
    gates.exact('Q.XML_electron_target', inputs['identity']['xml']['electrons'], physical['expected_electrons'])
    gates.exact('Q.saved_modes', s['saved_density_modes_checked'],
                historical['same_source_orbital_density']['common_coefficient_count'])
    gates.exact('Q.all_product_support_covered', s['product_support_missing_saved_count'], 0)
    gates.exact('Q.enumerated_product_count', s['product_support_count'],
                historical['product_support']['possible_product_count'])
    gates.bound('Q.saved_coefficient_max', s['density_coefficient_max_error'], 'density_coefficient_max_abs')
    if s['density_nonzero_reference_l2']:
        gates.bound('Q.saved_coefficient_relative_l2', s['density_nonzero_relative_l2'], 'density_nonzero_relative_l2')
    else:
        gates.bound('Q.saved_zero_reference_absolute_rule', s['density_coefficient_max_error'],
                    'density_coefficient_max_abs')
    gates.exact('Q.probe_count', s['probe_count'], len(plan['direct_fourier_miller_points']))
    gates.exact('Q.all_17_probes_saved', s['probe_saved_modes_checked'], 17)
    gates.bound('Q.probe_vs_FFT', s['probe_fft_max_error'], 'correlation_abs')
    gates.bound('Q.probe_vs_saved', s['probe_saved_max_error'], 'correlation_abs')
    gates.bound('Q.T_paths', s['kinetic_path_difference_ha'], 'kinetic_abs_ha')
    gates.bound('Q.T_historical', s['kinetic_direct_ha'] - historical['kinetic']['direct_ha'], 'kinetic_abs_ha')
    for name, field in [('rho', q['rho']), ('rho_saved', q['rho_saved'])]:
        imag = float(np.max(np.abs(field.imag)))
        denominator = float(np.linalg.norm(field.real))
        imag_l2 = float(np.linalg.norm(field.imag))
        gates.bound('Q.' + name + '.imaginary_max', imag, 'imaginary_density_abs')
        gates.bound('Q.' + name + '.imaginary_relative_l2', imag_l2 / denominator if denominator else imag_l2,
                    'imaginary_density_relative' if denominator else 'imaginary_density_abs')
    for i, row in enumerate(s['kpoints']):
        old = historical['per_k'][i]
        gates.exact(f'Q.k{i}.bands', row['bands'], physical['n_states'])
        gates.exact(f'Q.k{i}.weight', row['weight'], physical['kweights'][i])
        gates.compare(f'Q.k{i}.fractional_identity', row['k_fractional'], physical['kpoints'][i], 'geometry_abs')
        gates.bound(f'Q.k{i}.cutoff', row['cutoff_excess_ha'], 'cutoff_slack_ha')
        gates.compare(f'Q.k{i}.all_24_T_vs_history', row['kinetic_unweighted_ha'],
                      [x['kinetic_unweighted_ha'] for x in old['states']], 'kinetic_abs_ha')
        gates.compare(f'Q.k{i}.all_24_T_gradient_paths', row['gradient_kinetic_unweighted_ha'],
                      row['kinetic_unweighted_ha'], 'kinetic_abs_ha')
        gates.compare(f'Q.k{i}.all_24_T_gradient_history', row['gradient_kinetic_unweighted_ha'],
                      [x['gradient_unweighted_ha'] for x in old['states']], 'kinetic_abs_ha')


def validate_nonlocal(result, old, gates, label, threshold):
    gates.bound(label + '.NL_imaginary', result['max_imaginary_expectation_ha'], threshold)
    gates.bound(label + '.NL_spin_sum', result['spin_decomposition_difference_ha'], threshold)
    if label == 'Q':
        gates.exact('Q.NL_all_16_projectors', result['projectors'], 16)
        gates.bound('Q.D_Hermitian', result['D_hermiticity_frobenius'], threshold)
        for key in ('path_difference_ha', 'max_state_path_error_ha', 'max_state_spin_decomposition_error_ha'):
            gates.bound('Q.NL_' + key, result[key], threshold)
        gates.bound('Q.NL_action_historical', result['action_ha'] - old['energy_action_ha'], threshold)
    gates.bound(label + '.NL_projected_historical', result['projected_ha'] - old['energy_projected_ha'], threshold)
    for i, k in enumerate(result['kpoints']):
        rows = old['kpoints'][i]['rows']
        gates.exact(f'{label}.NL_k{i}_state_count', k['bands'], len(rows))
        for new_key, old_key in [('projected', 'projected_ha'), ('up', 'up_up_ha'),
                                 ('down', 'down_down_ha'), ('cross', 'spin_cross_ha')]:
            gates.compare(f'{label}.NL_k{i}_all_states_{new_key}', k[new_key + '_unweighted_ha'],
                          [x[old_key] for x in rows], threshold)
        if 'action_unweighted_ha' in k:
            gates.compare(f'{label}.NL_k{i}_all_states_action', k['action_unweighted_ha'],
                          [x['action_ha'] for x in rows], threshold)
        split = np.array(k['up_unweighted_ha']) + k['down_unweighted_ha'] + k['cross_unweighted_ha']
        gates.compare(f'{label}.NL_k{i}_all_states_spin_sum', split, k['projected_unweighted_ha'], threshold)


def validate_projection_amplitudes(amplitudes, published_arrays, gates, input_commit):
    """Additional unchanged frozen R tolerance; no phase alignment or fitting."""
    records = []
    for i, point in enumerate(amplitudes, 1):
        row = {'k_index': i - 1}
        for spin in ('up', 'down'):
            original = published_arrays[f'Q_k{i}_{spin}']
            new = point[spin]
            gates.compare(f'Q.k{i}.{spin}.all_projected_amplitudes', new, original, 1e-11,
                          contract='ADDITIONAL_UNCHANGED_FROZEN_R_AMPLITUDE_BOUND',
                          threshold_source='scripts/check_orbital_energy.py', threshold_source_commit=input_commit)
            row[spin] = {'shape': list(new.shape), 'values_checked': int(new.size),
                         'current_derived_sha256': public_io.digest(new.astype('<c16', copy=False).tobytes(order='C'))}
        records.append(row)
    return records


def original_history(root, plan, inputs, gates):
    ledger = checked_json(root, plan, 'results/mg-soc-energy-reference/ledger.json')
    receipt = checked_json(root, plan, 'results/mg-soc-qe-local-potential/saved-field-receipt.json')
    xml = ET.parse(public_io.source_path(root, 'results/mg-soc-qe-diagnostics/G40/qe.xml')).getroot()
    for node in xml.iter():
        node.tag = node.tag.split('}')[-1]
    fields = {x['id']: x for x in ledger['field_dictionary']}
    values, widths, native_tokens = {}, {}, {}
    for key in ('etot', 'demet', 'ehart', 'etxc', 'ewald'):
        record = fields['G40.' + key]
        token = xml.findtext('output/total_energy/' + key).strip()
        gates.exact('O.' + key + '.native_token', token, record['raw_token'])
        gates.exact('O.' + key + '.units', record['original_unit'], 'Ha')
        value, width = public_io.decimal_token(token)
        values[key], widths[key], native_tokens[key] = float(value), float(width), token
        gates.exact('O.' + key + '.original_float', float(value), record['value_ha'])
        gates.exact('O.' + key + '.token_halfwidth', float(width), record['quantization_half_width_ha'])
    internal = values['etot'] - values['demet']
    oq = internal - values['ehart'] - values['etxc'] - values['ewald']
    half = float(sum((public_io.decimal_token(t)[1] for t in native_tokens.values()), Decimal(0)))
    native = ledger['native_values']
    gates.exact('historical_Q_F', values['etot'], native['G40']['F'])
    gates.exact('historical_Q_E', internal, native['G40']['E'])
    gates.bound('historical_O_reduction_grouping', oq - native['G40']['O'], 'local_ledger_abs_ha')
    gates.bound('historical_O_print_halfwidth', half - inputs['historical']['comparison']['printing']['O_halfwidth_ha'],
                'J_print_absolute_floor_ha')
    gates.bound('historical_O_Phase7F', native['G40']['O'] - inputs['historical']['comparison']['Q']['O_historical_ha'],
                'local_ledger_abs_ha')
    gates.exact('historical_E_F_Phase7F', {label: {key: value[key] for key in ('E', 'F')}
                                         for label, value in native.items()},
                inputs['historical']['comparison']['historical_E_F_ha'])
    return {'ledger': ledger, 'receipt': receipt, 'O_Q': native['G40']['O'],
            'O_Q_token_reconstruction': oq, 'O_Q_halfwidth': half,
            'O_Q_tokens': native_tokens, 'O_Q_token_halfwidths': widths,
            'O_Q_reduction_grouping_drift': oq - native['G40']['O'],
            'L_saved_historical': receipt['original_pointwise_integrals_ha']['L_Qpp_Q'],
            'historical_E_F_ha': {label: {key: value[key] for key in ('E', 'F')}
                                   for label, value in native.items()}}


def audit_ab(root, inputs, plan, history, gates):
    output = {}
    threshold = 'AB_scalar_projected_abs_ha'
    for label in ('A', 'B'):
        endpoint = checked_json(root, plan, f'results/mg-soc-scf/{label}/endpoint.json')
        kpoints = []
        gates.exact(label + '.original_capacity', endpoint['diagnostics']['occupations']['capacity_per_state'], 1)
        for i, source in enumerate(inputs['ab'][label]['kpoints']):
            gates.exact(f'{label}.k{i}.f_endpoint_identity', source['occupations'].tolist(), endpoint['occupations'][i])
            gates.exact(f'{label}.k{i}.w_endpoint_identity', source['weight'],
                        endpoint['diagnostics']['occupations']['spatial_weights'][i])
            gates.exact(f'{label}.k{i}.e_endpoint_identity', [x['eigenvalue_ha'] for x in source['states']],
                        endpoint['eigenvalues_ha'][i])
            gates.exact(f'{label}.k{i}.bands', len(source['states']), plan['physical']['n_states'])
            for b, (state, row) in enumerate(zip(source['states'], source['rows'], strict=True), 1):
                gates.exact(f'{label}.k{i}.state{b}.band_identity', [state['band_one_based'], row['band']], [b, b])
            kinetic = np.array([x['kinetic_unweighted_ha'] for x in source['states']])
            projected = np.array([x['projected_ha'] for x in source['rows']])
            factor = source['weight'] * source['occupations']
            gates.compare(f'{label}.k{i}.weighted_T_table', factor * kinetic,
                          [x['kinetic_weighted_ha'] for x in source['states']], threshold)
            gates.compare(f'{label}.k{i}.weighted_NL_table', factor * projected,
                          [x['weighted_projected_ha'] for x in source['rows']], threshold)
            kpoints.append({**source, 'kinetic': kinetic, 'nonlocal': projected})
        result = numerical.audit_projected_endpoint(kpoints, inputs['operator']['D'])
        output[label] = result
        validate_nonlocal(result, inputs['historical']['nonlocal_checks']['states'][label], gates, label, threshold)
        native = history['ledger']['native_values'][label]['terms']
        gates.bound(label + '.T_scalar_historical', result['kinetic_scalar_ha'] - native['Kinetic'], threshold)
        gates.bound(label + '.NL_scalar_historical', result['nonlocal_scalar_ha'] - native['AtomicNonlocalFR'], threshold)
        gates.bound(label + '.NL_projected_scalar', result['projected_ha'] - result['nonlocal_scalar_ha'], threshold)
        gates.exact(label + '.all_scalar_states', result['scalar_states_checked'], {'kinetic': 72, 'nonlocal': 72})
    return output


def audit_local(q, nonlocal_result, ab, inputs, history, gates):
    potential = inputs['potential']
    old = inputs['historical']['comparison']
    volume = q['summary']['volume_bohr3']
    # The caller has passed both absolute and relative complex-density gates.
    rho, saved = q['rho'].real, q['rho_saved'].real
    saved_integral = numerical.shared_potential_integral([saved], [1.], potential['values_ha'],
                                                        potential['halfwidth_ha'], volume / saved.size)
    saved_drift = saved_integral['value_ha'] - history['L_saved_historical']
    result = {}
    threshold = 'local_ledger_abs_ha'
    qkinetic, qnl = q['summary']['kinetic_direct_ha'], nonlocal_result['projected_ha']
    for label in ('A', 'B'):
        native = history['ledger']['native_values'][label]['terms']
        khist = native['Kinetic'] + native['AtomicNonlocalFR']
        knew = ab[label]['kinetic_scalar_ha'] + ab[label]['projected_ha']
        rold = history['receipt']['original_comparisons'][label + '_minus_G40']['R_after_local_ha']
        grouping = rold - (khist - history['O_Q'] + history['L_saved_historical'])
        data = {'O_Q': history['O_Q'], 'O_Q_halfwidth': history['O_Q_halfwidth'],
                'S_response': knew - (qkinetic + qnl), 'drift_S': knew - khist,
                'historical_O_grouping_drift': grouping, 'saved_local_replay_drift': saved_drift,
                'R_old': rold}
        current = numerical.local_ledger(rho, saved, potential['values_ha'], potential['halfwidth_ha'],
                                          volume, qkinetic, qnl, data)
        current['history_inputs'] = data
        current['K_historical_ha'], current['K_replayed_ha'] = khist, knew
        result[label] = current
        gates.bound(label + '.local_imaginary', max(abs(current[x]['imaginary_ha']) for x in ('L_wfc', 'L_saved', 'delta_L')), threshold)
        for newkey, oldkey in [('L_wfc', 'L_wfc_ha'), ('L_saved', 'L_saved_replayed_ha'), ('delta_L', 'delta_L_state_ha')]:
            gates.bound(label + '.' + newkey + '_historical', current[newkey]['value_ha'] - old['local_state'][oldkey], threshold)
        for newkey, oldkey in [('J_Q_ha', 'J_Q_ha'), ('NL_shaped_remainder_ha', 'NL_Q_ledger_ha')]:
            gates.bound(label + '.' + newkey + '_historical', current[newkey] - old['Q'][oldkey], threshold)
        for newkey, oldkey in [('S_response', 'S_response_ha'), ('drift_S', 'drift_S_ha'),
                               ('historical_O_grouping_drift', 'historical_O_combination_drift_ha'),
                               ('saved_local_replay_drift', 'saved_local_replay_drift_ha')]:
            gates.bound(label + '.' + newkey + '_historical', data[newkey] - old['comparisons'][label][oldkey], threshold)
        for key in ('R_old_difference_ha', 'local_subtraction_difference_ha', 'J_plus_NL_shaped_minus_NL_ha'):
            gates.bound(label + '.' + key, current[key], threshold)
        gates.bound(label + '.recomposed_R_historical', current['R_old_reconstructed_ha'] - old['comparisons'][label]['recomposed_R_ha'], threshold)
        expected = old['printing']['halfwidths_ha']['J_Q']
        width_limit = max(gates.thresholds['J_print_absolute_floor_ha'],
                          abs(expected) * gates.thresholds['J_print_relative'])
        gates.bound(label + '.J_print_halfwidth', current['J_Q_halfwidth_ha'] - expected, width_limit,
                    relative_limit=gates.thresholds['J_print_relative'], absolute_floor=gates.thresholds['J_print_absolute_floor_ha'])
        # Symbolically n_wfc + (n_saved - n_wfc) = n_saved before float reductions.
        current['J_plus_delta_L_print_halfwidth_ha'] = saved_integral['halfwidth_ha'] + history['O_Q_halfwidth']
        current['recomposed_R_print_halfwidth_ha'] = current['J_plus_delta_L_print_halfwidth_ha']
        current['delta_L_print_comparison'] = 'Current value recorded; no old 1e-23-scale interval equality gate'
        gates.bound(label + '.recomposed_print_halfwidth', current['recomposed_R_print_halfwidth_ha'] -
                    old['printing']['halfwidths_ha']['recomposed_R'], width_limit)
    return result


def run_replay(source_root, plan, output, report):
    gates = Checks(plan['thresholds'], report['checks'])
    inputs = None
    try:
        inputs = public_io.read_inputs(source_root, plan)
        report['identity'] = inputs['identity']
        gates.exact('public_input_file_bytes', {k: x['bytes'] for k, x in inputs['identity']['files'].items()}, plan['input_bytes'])
        gates.checkpoint('exact public input identity stage')
        report['public_input_identity_status'] = 'PASS'
        saved = inputs['saved_density']
        common = common_density_support(source_root, plan, saved['millers'])
        q = numerical.audit_q_state(inputs['state'], plan['physical']['fft_size'], saved['millers'], saved['coefficients'],
                                    np.array(plan['direct_fourier_miller_points']), plan['physical']['ecut_ha'],
                                    plan['physical']['expected_electrons'], original_common_millers=common)
        report['Q'] = q['summary']
        validate_q(q, inputs, plan, gates)
        gates.checkpoint('Q density/kinetic stage')
        nonlocal_result = numerical.audit_nonlocal(inputs['state'], inputs['operator'], return_amplitudes=True)
        amplitudes = nonlocal_result.pop('_amplitudes')
        report['Q_nonlocal'] = nonlocal_result
        report['Q_projection_amplitudes'] = validate_projection_amplitudes(
            amplitudes, inputs['package_arrays']['operator'], gates, plan['input_commit'])
        validate_nonlocal(nonlocal_result, inputs['historical']['nonlocal_checks']['states']['Q'], gates, 'Q', 'nonlocal_abs_ha')
        old_q = inputs['historical']['comparison']['Q']
        gates.bound('Q.T_Phase7F_comparison', q['summary']['kinetic_direct_ha'] - old_q['T_direct_ha'], 'kinetic_abs_ha')
        gates.bound('Q.NL_Phase7F_comparison', nonlocal_result['projected_ha'] - old_q['N_D_ha'], 'nonlocal_abs_ha')
        gates.bound('Q.K_Phase7F_comparison', q['summary']['kinetic_direct_ha'] + nonlocal_result['projected_ha'] -
                    old_q['K_Q_in_D_ha'], 'local_ledger_abs_ha')
        gates.checkpoint('Q nonlocal stage')
        history = original_history(source_root, plan, inputs, gates)
        report['historical_source_arithmetic'] = {k: v for k, v in history.items() if k not in ('ledger', 'receipt')}
        ab = audit_ab(source_root, inputs, plan, history, gates)
        report['A_B'] = ab
        gates.checkpoint('A/B projected/scalar stage')
        p = inputs['potential']
        native_p2 = hashlib.sha256()
        with gzip.open(public_io.source_path(source_root, 'results/mg-soc-qe-local-potential/P2/local-ionic.pp.gz'), 'rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                native_p2.update(chunk)
        gates.exact('native_P2.original_uncompressed_bytes', native_p2.hexdigest(),
                    inputs['historical']['comparison']['P2_source']['source_sha256'])
        fingerprints = {key: public_io.digest(array.astype('<f8', copy=False).tobytes(order='F'))
                        for key, array in [('V_Qpp', p['values_ha']), ('uV', p['halfwidth_ha'])]}
        for key, actual in fingerprints.items():
            gates.exact('native_P2.' + key + '.derived_from_exact_tokens', actual,
                        inputs['historical']['comparison']['local_state']['field_fingerprints'][key])
        report['P2'] = {key: p[key] for key in ('token_sha256', 'grid', 'plot_num', 'padding', 'source_units',
                                             'units', 'unit_divisions_by_two', 'ordering', 'header_lattice_used_for_volume')}
        report['P2']['field_fingerprints'] = fingerprints
        report['P2']['native_uncompressed_sha256'] = native_p2.hexdigest()
        gates.checkpoint('exact native P2 token-to-float identity stage')
        report['local_ledger'] = audit_local(q, nonlocal_result, ab, inputs, history, gates)
        gates.checkpoint('local and signed ledger stage')
        # Transient diagnostic arrays are disclosed this-run results, not historical arrays.
        np.save(output / 'rho.npy', q['rho'].real, allow_pickle=False)
        np.save(output / 'rho_saved.npy', q['rho_saved'].real, allow_pickle=False)
        report['transient_arrays'] = {name: {'file_sha256': public_io.digest((output / name).read_bytes()),
                                            'scope': 'CURRENT_I_DERIVED_ARRAY_NOT_HISTORICAL'}
                                      for name in ('rho.npy', 'rho_saved.npy')}
    finally:
        if inputs is not None:
            report['input_bytes_after_status'] = 'FAIL'
            after = public_io.verify_sources(source_root, plan['input_sha256'])
            gates.exact('source_files_before_after', after, inputs['identity']['files'])
            report['input_bytes_after_status'] = 'PASS'
            report['array_bytes_after_status'] = 'FAIL'
            for key in ('Q', 'operator'):
                public_io.verify_array_immutability(inputs['package_arrays'][key], inputs['identity']['packages'][key])
            report['array_bytes_after_status'] = 'PASS'
    gates.checkpoint('complete input preservation stage')
    report['status'] = report['independent_implementation_status'] = 'PASS'
    report['Q_full_public_numeric_replay_status'] = 'PASS'
    # The complete permutation is recomputed but need not be duplicated in a small receipt.
    for item in report['Q_nonlocal']['kpoints']:
        order = item.pop('q_indices_in_p_order')
        item['q_to_p_bijection_count'] = len(order)
        item['q_to_p_indices_sha256'] = public_io.digest(np.array(order, dtype='<i8').tobytes())
    return report


def prepare_output(path):
    path = Path(path).resolve()
    if path.exists() and any(path.iterdir()):
        raise ValueError('output directory must be new or empty; refusing stale outputs')
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_report(output, report):
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    temporary = output / 'independent.json.tmp'
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    temporary.replace(output / 'independent.json')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    output = prepare_output(args.output)
    plan = json.loads(args.plan.read_text())
    report = initial_report(plan)
    report['plan_sha256'] = public_io.digest(args.plan.read_bytes())
    report['code_sha256'] = {Path(path).name: public_io.digest(Path(path).read_bytes())
                             for path in (__file__, public_io.__file__, numerical.__file__)}
    report['command'] = ['python', 'scripts/replay_public_independent.py', '--source-root',
                          '<read-only-public-baseline>', '--plan', 'benchmarks/mg-soc-public-replay-v1/plan.json',
                          '--output', '<new-independent-output>']
    try:
        actual = subprocess.check_output(['git', '-C', str(args.source_root), 'rev-parse', 'HEAD'], text=True).strip()
        public_io.require(actual == plan['input_commit'], 'source Git commit mismatch')
        run_replay(args.source_root, plan, output, report)
        code = 0
    except Exception as exc:
        code = 1
        report['status'] = report['independent_implementation_status'] = 'FAIL'
        if 'Q' in report:
            report['Q_full_public_numeric_replay_status'] = 'FAIL'
        report['failure'] = {'type': type(exc).__name__, 'message': str(exc),
                             'traceback': traceback.format_exc()}
        print(f'Independent replay FAIL: {type(exc).__name__}: {exc}', file=sys.stderr)
    report['exit_code'] = code
    write_report(output, report)
    print(json.dumps({'status': report['status'], 'exit_code': code, 'checks': len(report['checks'])}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
