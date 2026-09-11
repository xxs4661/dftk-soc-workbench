#!/usr/bin/env python3
"""Phase 8B registered cases and public-only, fixed-Gamma response arithmetic.

No solver, density reconstruction, UPF reader or fitted energy reference. The
original Si fixed-window statistics and FD function remain the shared formulas.
Case/input bytes are those committed before any Phase 8B numerical execution.
"""
import argparse
import copy
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys

from si_soc_comparison import (HARTREE_EV, PROBES, analyze_gamma, check,
                               hash_string, number, _fd_diagnostic, _levels)
from parse_qe_soc import match_points

ROOT = Path(__file__).resolve().parents[1]
BASE = 'bc68aaf655d96dfd4335f6fa1a8e5ee76477c2a3'
PREPARATION = '4a58286183e4625ad7ae69b44eb80097e8ad6c7d'
CASE_DIR = 'benchmarks/si-soc-sensitivity-v1'
PROFILE_IDS = ('E40', 'T05', 'K4')
B0_CASE = 'benchmarks/si-soc-splitting-v1/case.json'
PLAN_HASHES = {
    'plan.json': 'ab37e46717e5e87e54ee443e5a0507155e1b2e146c1a5a2bb93e73231b39db2e',
    'allowed-differences.json': 'e733c76f41e074ca68e249506f44165e7c788b5e130573b5f8918967a3a67525',
    'replay-contract.json': '2ad8ff3a703440d843921e1e642594d0ed5ec01eadd41a6236d1ccafe53086b4',
}
RUNTIME_FIELDS = {'binding', 'verified_pseudo_sha256', 'case_sha256'}
REPLAY_ATOL = 1e-11
ENERGY_FIELDS = ('internal_ha', 'free_ha', 'minus_TS_ha', 'entropy_dimensionless')
# Read from BASE Git blobs before execution; these supplement, not alter, the
# prepared plan's already authenticated historical energy.json table.
B0_ENERGY_SOURCES = {
    'results/si-soc-splitting/D-SCF.json': '0860661c4383d80a6767981476cf8c3fa0f996d69e8e1174df39d0bed83e9ab2',
    'results/si-soc-splitting/Q-SCF/qe-result.json': '6e48758483e522514719bf13efcf47be2ccfda317e00d2626563b9e0d645fc47',
}


def read(path):
    def invalid(token):
        raise ValueError('Nonfinite JSON token: ' + token)
    return json.loads(Path(path).read_text(), parse_constant=invalid)


def _bytes(root, relative, digest):
    path = Path(root) / relative
    check(not path.is_symlink() and path.resolve().is_relative_to(Path(root).resolve()),
          'Unconfined public input: ' + relative)
    data = path.read_bytes()
    check(hashlib.sha256(data).hexdigest() == digest, 'Prepared byte mismatch: ' + relative)
    return data


def _plan(root):
    for name, digest in PLAN_HASHES.items():
        _bytes(root, CASE_DIR + '/' + name, digest)
    return read(Path(root) / CASE_DIR / 'plan.json')


def prepared_paths(profile=None):
    """Repository-relative immutable inputs; README navigation is not frozen."""
    check(profile is None or profile in PROFILE_IDS, 'Unregistered sensitivity profile')
    selected = PROFILE_IDS if profile is None else (profile,)
    return [CASE_DIR + '/' + name for name in PLAN_HASHES] + [
        f'{CASE_DIR}/{p}/{name}' for p in selected
        for name in ('case.json', 'qe-scf.in', 'qe-gamma.in')]


def case_sha256(profile, root=ROOT):
    check(profile in PROFILE_IDS, 'Unregistered sensitivity profile')
    return _plan(root)['prepared_input_sha256'][f'{CASE_DIR}/{profile}/case.json']


def _canonical(value):
    # Unlike Python equality this distinguishes bool/number and int/float.
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _registered_case(root, profile):
    check(profile in PROFILE_IDS, 'Unregistered sensitivity profile')
    plan = _plan(root)
    for path in prepared_paths(profile)[3:]:
        _bytes(root, path, plan['prepared_input_sha256'][path])
    _bytes(root, B0_CASE, plan['B0']['source_files_sha256'][B0_CASE])
    ref = plan['source_reference']
    _bytes(root, ref['path'], ref['sha256'])
    base = read(Path(root) / B0_CASE)
    expected = copy.deepcopy(base)
    expected['case'] = 'si-soc-sensitivity-v1/' + profile
    expected['sensitivity_profile'] = profile
    expected['source_reference'] = ref['path']
    expected['qe']['prefix'] = 'si8b_' + profile.lower()
    expected['probe_kpoints'], expected['probe_weights'] = [[0., 0., 0.]], [1.]
    axis = (0., .25, -.5, -.25) if profile == 'K4' else (0., -.5)
    expected['kpoints'] = [{'coordinate_fractional': list(p), 'weight_spatial': 1 / len(axis)**3}
                           for p in itertools.product(axis, repeat=3)]
    if profile == 'E40':
        expected['cutoffs'] = {'dftk_ecut_ha': 40, 'qe_ecutwfc_ry': 80, 'qe_ecutrho_ry': 320}
    if profile == 'T05':
        expected['electrons']['temperature_ha'] = .0005
        expected['settings']['ensemble']['tau_ha'] = .0005
    actual = read(Path(root) / CASE_DIR / profile / 'case.json')
    check(_canonical(actual) == _canonical(expected), 'Prepared case exceeds the registered B0 differences')
    return actual, plan


def _validate_binding(binding, profile, digest):
    check(isinstance(binding, dict) and set(binding) == {'D', 'Q'}, 'Expected explicit D/Q bindings')
    for label in ('D', 'Q'):
        item = binding[label]
        check(isinstance(item, dict) and set(item) == {
            'scf_run_id', 'gamma_run_id', 'density_sha256', 'case_sha256'}, 'Invalid current-run binding fields')
        check(all(isinstance(item[k], str) and item[k] for k in ('scf_run_id', 'gamma_run_id')),
              'Missing run identity')
        check(hash_string(item['density_sha256']) and item['case_sha256'] == digest,
              'Wrong density/case hash binding: ' + profile)
    ids = [binding[p][k] for p in ('D', 'Q') for k in ('scf_run_id', 'gamma_run_id')]
    check(len(set(ids)) == 4, 'Four formal slots require four distinct run identities')


def _validate_case(case, root):
    check(isinstance(case, dict), 'Case must be an object')
    profile = case.get('sensitivity_profile')
    expected, plan = _registered_case(root, profile)
    declared = {k: v for k, v in case.items() if k not in RUNTIME_FIELDS}
    check(_canonical(declared) == _canonical(expected), 'Unapproved case override or field/type change')
    digest = plan['prepared_input_sha256'][f'{CASE_DIR}/{profile}/case.json']
    if 'case_sha256' in case:
        check(case['case_sha256'] == digest, 'Runtime case hash mismatch')
    if 'verified_pseudo_sha256' in case:
        check(case['verified_pseudo_sha256'] == expected['pseudo']['sha256'], 'Runtime source hash mismatch')
    if 'binding' in case:
        _validate_binding(case['binding'], profile, digest)
    # Quantity, weights and modulo-integer uniqueness remain explicit checks.
    points = [p['coordinate_fractional'] for p in case['kpoints']]
    check(len(points) == (64 if profile == 'K4' else 8), 'Wrong expected SCF k-point count')
    match_points(points, points, 1e-10)
    match_points(points, [[-x for x in p] for p in points], 1e-10)
    check(all(p['weight_spatial'] == 1 / len(points) for p in case['kpoints']), 'Wrong spatial weights')
    return case


def validate_case(case):
    """Validate the unchanged prepared shape plus named runtime evidence only."""
    return _validate_case(case, ROOT)


def load_case(root, profile):
    case, _ = _registered_case(root, profile)
    return _validate_case(case, root)


def load_historical_gamma(root=ROOT):
    """Authenticate complete original three-probe bytes, then retain each receipt."""
    plan = _plan(root)
    sources = plan['B0']['source_files_sha256']
    for path, digest in sources.items():
        _bytes(root, path, digest)
    return {p: read(Path(root) / f'results/si-soc-splitting/{p}-spectrum.json') for p in ('D', 'Q')}


def load_historical_energy(root=ROOT):
    """Original accepted SCF fields, checked against the frozen public table."""
    historical = load_historical_gamma(root)
    for path, digest in B0_ENERGY_SOURCES.items():
        _bytes(root, path, digest)
    d = read(Path(root) / 'results/si-soc-splitting/D-SCF.json')
    q = read(Path(root) / 'results/si-soc-splitting/Q-SCF/qe-result.json')
    check(d['final_acceptance_status'] == d['execution_status'] == q['execution_status'] == 'PASS',
          'Historical native SCF was not accepted')
    check(d['exit_code'] == q['process_exit_code'] == 0 and q['kind'] == 'scf', 'Wrong historical energy endpoint')
    for label, receipt in (('D', d), ('Q', q)):
        check(receipt['run_id'] == historical[label]['source_scf_run_id'], 'Historical Gamma/energy parent mismatch')
    diagnostics = d['final']['diagnostics']
    check(diagnostics['occupations']['tau_ha'] == q['temperature_ha'] == .001, 'Wrong historical B0 temperature')
    result = {'D': dict(zip(ENERGY_FIELDS, [diagnostics[k] for k in (
        'internal_energy_ha', 'free_energy_ha', 'entropy_energy_ha', 'entropy_dimensionless')])),
        'Q': {k: q['energy'][k] for k in ENERGY_FIELDS}}
    table = read(Path(root) / 'results/si-soc-splitting/energy.json')
    for label in ('D', 'Q'):
        check(table[label + '_scf_run_id'] == historical[label]['source_scf_run_id'], 'Historical energy table parent mismatch')
        check(_canonical(result[label]) == _canonical(table[label]), 'Historical native energy/table disagreement')
        e = result[label]
        _close(e['free_ha'], e['internal_ha'] + e['minus_TS_ha'], 'Historical E/F/-TS does not close', 1e-12)
        _close(e['minus_TS_ha'], -.001 * e['entropy_dimensionless'], 'Historical entropy temperature mismatch')
    return result


def _historical_gamma(receipt, label, authenticated):
    check(_canonical(receipt) == _canonical(authenticated), 'Historical B0 receipt differs from authenticated public data')
    check(receipt['execution_status'] == 'PASS' and type(receipt['process_exit_code']) is int
          and receipt['process_exit_code'] == 0 and receipt['kind'] == 'spectrum'
          and receipt['physical_operator'] == 'full_soc', 'Invalid historical spectrum status/operator')
    points = receipt['kpoints']
    order = match_points(PROBES, [p['coordinate_fractional'] for p in points], 1e-10)
    return analyze_gamma(points[order[0]]['eigenvalues_ha'])


def _identity(receipt, case, label, kind, binding):
    check(isinstance(receipt, dict), 'Missing current receipt')
    profile = case['sensitivity_profile']
    expected = {'schema_version': 1, 'case': case['case'], 'sensitivity_profile': profile,
        'case_sha256': binding['case_sha256'], 'code': 'DFTK' if label == 'D' else 'QE',
        'kind': kind, 'execution_status': 'PASS', 'process_exit_code': 0,
        'input_comparability_status': 'PASS', 'physical_operator': 'full_soc',
        'pseudo_sha256': case['pseudo']['sha256'], 'n_electrons': 8, 'n_bands': 24,
        'occupation_capacity': 1, 'temperature_ha': case['electrons']['temperature_ha'],
        'density_source_sha256': binding['density_sha256'],
        'run_id': binding['scf_run_id' if kind == 'scf' else 'gamma_run_id']}
    for key, value in expected.items():
        check(key in receipt and _canonical(receipt[key]) == _canonical(value), 'Receipt identity/status mismatch: ' + key)
    for key in ('fitted_shift', 'per_k_shift', 'per_band_shift', 'experimental_target_ev', 'energy_correction_ha'):
        check(key not in receipt, 'Fitting or correction is not permitted: ' + key)
    check(isinstance(receipt.get('warning_evidence'), dict), 'Missing preserved warning evidence')
    return receipt


def _close(a, b, reason, tolerance=REPLAY_ATOL):
    a, b = number(a), number(b)
    check(abs(a-b) <= tolerance * max(1., abs(a), abs(b)), reason)


def _entropy(occupations):
    return -sum(f * math.log(f) + (1-f) * math.log1p(-f) for f in occupations if 0 < f < 1)


def _scf(receipt, case, label, binding):
    _identity(receipt, case, label, 'scf', binding)
    check(receipt.get('scf_acceptance_status') == 'PASS', 'Parent SCF did not pass its actual acceptance gates')
    mu, tau = number(receipt['fermi_energy_ha']), case['electrons']['temperature_ha']
    points = receipt['kpoints']
    check(isinstance(points, list), 'Missing SCF endpoints')
    requested = case['kpoints']
    order = match_points([p['coordinate_fractional'] for p in requested],
                         [p['coordinate_fractional'] for p in points], 1e-10)
    ne, entropy, fd_max, tail = 0., 0., 0., 0.
    for wanted, index in zip(requested, order):
        p = points[index]
        w = number(p['weight_spatial'])
        check(w == wanted['weight_spatial'], 'Wrong SCF endpoint weight')
        v = _levels(p['eigenvalues_ha'])
        f = p['occupations']
        check(isinstance(f, list) and len(f) == 24, 'Expected 24 capacity-one SCF occupations')
        f = [number(x) for x in f]
        check(all(0 <= x <= 1 for x in f), 'Occupation outside capacity one')
        ne += w * sum(f)
        entropy += w * _entropy(f)
        fd_max = max(fd_max, max(abs(a-b) for a, b in zip(f, _fd_diagnostic(v, mu, tau=tau))))
        tail = max(tail, *f[-2:])
    check(abs(ne-8) <= 1e-8, 'SCF endpoint electron count failure')
    check(tail <= 1e-10, 'SCF target-space occupation boundary failure')
    check(fd_max <= REPLAY_ATOL, 'Original SCF occupations are inconsistent with original eigenvalues/mu/temperature')
    energy = receipt['energy']
    check(isinstance(energy, dict), 'SCF native energy is missing; bands energy cannot replace it')
    for field in ENERGY_FIELDS:
        number(energy[field])
    check(energy['entropy_dimensionless'] >= 0, 'Negative entropy')
    _close(energy['free_ha'], energy['internal_ha'] + energy['minus_TS_ha'],
           'Native E/F/-TS arithmetic does not close', 1e-12)
    _close(energy['minus_TS_ha'], -tau * energy['entropy_dimensionless'], 'Entropy uses wrong temperature')
    _close(energy['entropy_dimensionless'], entropy, 'Native entropy differs from original occupations')
    return {'energy': copy.deepcopy(energy), 'mu_ha': mu, 'temperature_ha': tau,
            'electron_sum': ne, 'endpoint_fd_max_abs': fd_max, 'top_two_occupation_max': tail,
            'endpoint_entropy_dimensionless': entropy, 'run_id': receipt['run_id'],
            'density_source_sha256': receipt['density_source_sha256'],
            'warning_evidence': copy.deepcopy(receipt['warning_evidence']),
            'scope': 'Uncorrected native SCF E/F; endpoints retained in source summary; no Gamma occupation constraint'}


def _gamma(receipt, parent, case, label, binding):
    _identity(receipt, case, label, 'spectrum', binding)
    check(receipt.get('source_scf_run_id') == parent['run_id'], 'Wrong profile SCF parent')
    check(number(receipt['fermi_energy_ha']) == parent['mu_ha'], 'Gamma must retain the original SCF global mu')
    points = receipt['kpoints']
    check(isinstance(points, list), 'Missing Gamma points')
    order = match_points([[0., 0., 0.]], [p['coordinate_fractional'] for p in points], 1e-10)
    point = points[order[0]]
    check(number(point['weight_spatial']) == 1., 'Diagnostic Gamma spatial weight must be one')
    result = analyze_gamma(point['eigenvalues_ha'])
    values, tau = result['values_ha'], parent['temperature_ha']
    structure = all(result[k] == 'PASS' for k in ('manifold_assignment_status', 'multiplet_structure_status'))
    result['gamma_structure_status'] = 'PASS' if structure else 'MISMATCH'
    result['fixed_window_interpretation'] = 'ISOLATED_FIXED_WINDOW' if structure else 'WINDOW_ONLY_NOT_IDENTIFIED'
    pairing = max(abs(values[i]-values[i+1]) for i in range(0, 24, 2))
    result['kramers_max_ha'] = pairing
    result['gamma_pairing_status'] = 'PASS' if pairing <= 1e-7 else 'MISMATCH'
    f = _fd_diagnostic(values, parent['mu_ha'], tau=tau)
    occupied = min(f[2:8]) >= .99999999
    result['occupation'] = {'values': f, 'fixed_states_3_to_8': f[2:8],
        'maximum_hole_3_to_8': max(1-x for x in f[2:8]),
        'mu_minus_upper_max_over_tau': (parent['mu_ha']-max(values[4:8])) / tau,
        'mu_ha': parent['mu_ha'], 'temperature_ha': tau, 'criterion': .99999999,
        'status': 'PASS' if occupied else 'REVIEW_REQUIRED',
        'scope': 'FD at existing parent SCF mu; diagnostic Gamma sum is not constrained to 8'}
    if label == 'D':
        r = point['residuals_ha']
        check(isinstance(r, list) and len(r) == 24 and all(number(x) >= 0 for x in r),
              'Missing all 24 explicit D Gamma residuals')
        gram = number(point['gram_frobenius'])
        check(gram >= 0, 'Invalid Gram norm')
        result['precision'] = {'max_residual_ha': max(r), 'gram_frobenius': gram,
            'status': 'PASS' if max(r) <= 1e-9 and gram <= 1e-9 else 'MISMATCH', 'evidence_level': 'RUNNER_REPORTED'}
    else:
        precision, warning = receipt['precision'], receipt['warning_evidence']
        check(precision.get('diago_thr_init_ry') == 1e-13 and precision.get('ethr_history_ry')
              and all(number(x) == 1e-13 for x in precision['ethr_history_ry']), 'Missing native CG 1e-13 Ry evidence')
        check(type(warning.get('eigenvalues_not_converged')) is bool, 'Missing native target convergence warning status')
        result['precision'] = {'status': 'REVIEW_REQUIRED' if warning['eigenvalues_not_converged'] else 'PASS',
            'evidence_level': 'REPORTED_THRESHOLD_AVAILABLE; explicit residuals NOT_AVAILABLE',
            'native_precision': copy.deepcopy(precision)}
    result['warning_evidence'] = copy.deepcopy(receipt['warning_evidence'])
    return result


def compare_profile(*, case, d_gamma, q_gamma, d_scf, q_scf, binding,
                    b0_d_gamma=None, b0_q_gamma=None, root=ROOT):
    """Strict current-parent binding, historical byte identity, then pure sums.

    Invalid/failed/missing input raises ValueError; the CLI emits a fresh failure
    and exits 2. Valid data retain algebra even when scientific gates disagree.
    """
    _validate_case(case, root)
    profile = case['sensitivity_profile']
    plan = _plan(root)
    _validate_binding(binding, profile, case_sha256(profile, root))
    if 'binding' in case:
        check(_canonical(case['binding']) == _canonical(binding), 'Conflicting runtime and comparison bindings')
    historical = load_historical_gamma(root)
    b0_energy = load_historical_energy(root)
    bg = {p: _historical_gamma(value if value is not None else historical[p], p, historical[p])
          for p, value in (('D', b0_d_gamma), ('Q', b0_q_gamma))}
    parents = {p: _scf(value, case, p, binding[p]) for p, value in (('D', d_scf), ('Q', q_scf))}
    gamma = {p: _gamma(value, parents[p], case, p, binding[p]) for p, value in (('D', d_gamma), ('Q', q_gamma))}
    delta = {p: gamma[p]['delta_so_ev'] for p in ('D', 'Q')}
    response = {p: delta[p] - bg[p]['delta_so_ev'] for p in ('D', 'Q')}
    gap, b0gap = delta['D'] - delta['Q'], bg['D']['delta_so_ev'] - bg['Q']['delta_so_ev']
    response_gap = response['D'] - response['Q']
    closure = response_gap - (gap-b0gap)
    _close(response_gap, gap-b0gap, 'Response-gap arithmetic closure failed')
    usable_by_program = {p: (all(gamma[p][k] == 'PASS'
        for k in ('gamma_structure_status', 'gamma_pairing_status', 'resolvable_soc_status'))
        and gamma[p]['precision']['status'] == 'PASS' and all(bg[p][k] == 'PASS'
        for k in ('manifold_assignment_status', 'multiplet_structure_status', 'resolvable_soc_status')))
        for p in ('D', 'Q')}
    usable = all(usable_by_program.values())
    stability = {p: ('INCONCLUSIVE' if not usable_by_program[p] else 'WITHIN_SCREENING_WINDOW'
                    if abs(response[p]) <= 1e-4 else 'CHANGE_EXCEEDS_SCREENING_WINDOW') for p in ('D', 'Q')}
    vd, vq = gamma['D']['values_ha'], gamma['Q']['values_ha']
    rd, rq = gamma['D']['quartet_mean_ha'], gamma['Q']['quartet_mean_ha']
    energy_gap = {k: parents['D']['energy'][k] - parents['Q']['energy'][k] for k in ENERGY_FIELDS}
    energy_response = {p: {k: parents[p]['energy'][k] - b0_energy[p][k] for k in ENERGY_FIELDS}
                       for p in ('D', 'Q')}
    result = {'schema_version': 1, 'case': case['case'], 'sensitivity_profile': profile,
        'case_sha256': case_sha256(profile, root), 'comparison_execution_status': 'PASS',
        'slot_execution_status': {p + '-' + action: 'PASS' for p in ('D', 'Q') for action in ('SCF', 'GAMMA')},
        'input_comparability_status': 'PASS', 'bindings': copy.deepcopy(binding),
        'B0': {**copy.deepcopy(plan['B0']), 'delta_so_ev': {p: bg[p]['delta_so_ev'] for p in ('D', 'Q')},
               'native_SCF_energy': b0_energy, 'additional_energy_source_sha256': B0_ENERGY_SOURCES},
        'D_gamma': gamma['D'], 'Q_gamma': gamma['Q'], 'SCF': parents,
        'delta_so_D_minus_Q_ev': gap, 'B0_delta_so_D_minus_Q_ev': b0gap,
        'response_ev': response, 'response_gap_ev': response_gap,
        'response_gap_from_code_gaps_ev': gap-b0gap, 'response_gap_closure_ev': closure,
        'gamma_structure_status': {p: gamma[p]['gamma_structure_status'] for p in ('D', 'Q')},
        'gamma_pairing_status': {p: gamma[p]['gamma_pairing_status'] for p in ('D', 'Q')},
        'gamma_occupation_diagnostic_status': {p: gamma[p]['occupation']['status'] for p in ('D', 'Q')},
        'fixed_window_splitting_agreement_status': ('INCONCLUSIVE' if not usable else 'PASS' if abs(gap) <= 1e-4 else 'MISMATCH'),
        'parameter_response_agreement_status': ('INCONCLUSIVE' if not usable else 'PASS' if abs(response_gap) <= 1e-4 else 'MISMATCH'),
        'limited_parameter_stability_status': stability,
        'spectra': {'D_raw_ha': vd, 'Q_raw_ha': vq, 'raw_D_minus_Q_ha': [a-b for a, b in zip(vd, vq)],
            'D_global_reference_ha': rd, 'Q_global_reference_ha': rq,
            'global_referenced_D_minus_Q_ha': [(a-rd)-(b-rq) for a, b in zip(vd, vq)]},
        'native_SCF_energy_D_minus_Q': energy_gap,
        'native_SCF_energy_response_from_B0': energy_response,
        'energy_response_scope': 'Each program native SCF x minus B0; E, F and -TS remain separate, especially for T05; no correction or zero-temperature extrapolation',
        'parameter_scope': plan['scope'][profile],
        'stability_scope': plan['scope']['stability'], 'numerical_review_status': 'REVIEW_REQUIRED',
        'physical_manifold_interpretation': 'REVIEW_REQUIRED', 'physical_convergence': 'NOT_ESTABLISHED',
        'variant_null_control_status': 'NOT_RUN', 'off_gamma_TR': 'NOT_ASSESSED',
        'continuous_band_tracking': 'NOT_ASSESSED', 'native_QE_NL_independent': 'NOT_MEASURED'}
    _canonical(result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Replay one registered Phase 8B public-data comparison; no solver.')
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--profile', choices=PROFILE_IDS, required=True)
    for name in ('d-gamma', 'q-gamma', 'd-scf', 'q-scf', 'binding'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        values = {name: read(getattr(args, name)) for name in ('d_gamma', 'q_gamma', 'd_scf', 'q_scf', 'binding')}
        result = compare_profile(case=load_case(args.root, args.profile), root=args.root, **values)
        print(json.dumps(result, indent=2, allow_nan=False))
        # Exit0 certifies arithmetic replay, not physical convergence or review.
        return 0
    except (ValueError, OSError, KeyError, TypeError, OverflowError) as error:
        print(json.dumps({'schema_version': 1, 'sensitivity_profile': args.profile,
            'comparison_execution_status': 'FAIL', 'reason': str(error)}, allow_nan=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
