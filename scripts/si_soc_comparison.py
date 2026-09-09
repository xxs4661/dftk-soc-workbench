#!/usr/bin/env python3
"""Restricted Si Phase 8A native-output adapter and public spectrum arithmetic.

No solver, occupations solver, UPF transform or fitted energy reference. XML
primitives and printed-precision checks are reused from the unchanged adapters.
All constants below are the predeclared one-case contract, not inferred outputs.
"""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

from parse_qe_baseline import require, text, finite, vector, boolean, positive_int, dot
from parse_qe_soc import (HARTREE_EV, match_points, same_point, text_consistency,
                          stdout_spectrum_check)
from parse_qe_soc_diagnostics import native_warnings

CASE = 'si-soc-splitting-v1'
LATTICE = [[0., 5.13, 5.13], [5.13, 0., 5.13], [5.13, 5.13, 0.]]
POSITIONS = [[0., 0., 0.], [.25, .25, .25]]
SCF_POINTS = [list(p) for p in itertools.product((0., -.5), repeat=3)]
PROBES = [[0., 0., 0.], [.125, .0625, -.1875], [-.125, -.0625, .1875]]
GATES = {'coordinate_abs': 1e-10, 'weight_abs': 1e-10, 'electron_abs': 1e-8,
         'geometry_abs': 1e-9, 'magnetization_abs': 1e-10,
         'stdout_conversion_abs_ha': 1e-10}


def check(condition, reason):
    if not condition:
        raise ValueError(reason)


def number(value):
    check(type(value) in (int, float) and math.isfinite(value), 'Expected finite real number')
    return float(value)


def hash_string(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def _contract(case):
    if isinstance(case, dict) and 'qe_reference_profile' in case:
        check('sensitivity_profile' not in case, 'Mixed reference/sensitivity case is not allowed')
        from si_qe_reference import validate_case
        validate_case(case)  # Explicit QE-only K6/K8 request; never a paired D/Q profile.
        return case['pseudo']
    if isinstance(case, dict) and 'sensitivity_profile' in case:
        from si_soc_sensitivity import validate_case
        validate_case(case)  # Only the three prepared profiles; no arbitrary overrides.
        return case['pseudo']
    check(isinstance(case, dict) and case.get('case') == CASE, 'Wrong Si case')
    p, e, g = case['pseudo'], case['electrons'], case['geometry']
    expected = {'element': 'Si', 'z_valence': 4, 'nlcc': True, 'filename': 'Si_r.upf'}
    check(all(p.get(k) == v for k, v in expected.items()), 'Wrong Si source/NLCC contract')
    check(hash_string(p.get('sha256')), 'Missing actual source SHA-256')
    check(all(e.get(k) == v for k, v in {'n_electrons': 8, 'n_bands': 24, 'occupation_capacity': 1,
              'temperature_ha': .001}.items()), 'Wrong 8-electron/24-spinor/capacity-one contract')
    check(g['lattice_vectors_bohr'] == LATTICE and g['positions_fractional'] == POSITIONS,
          'Wrong diamond Si geometry')
    if 'species' in g:
        check(g['species'] == ['Si', 'Si'], 'Wrong atom species count')
    if 'xc' in case:
        check(case['xc']['qe'] == 'PBE' and case['xc']['dftk_identifiers'] == ['gga_x_pbe', 'gga_c_pbe'],
              'Wrong PBE functional contract')
    if 'fft_size' in case:
        check(case['fft_size'] == [48, 48, 48], 'Wrong FFT contract')
    if 'probe_kpoints' in case:
        check(case['probe_kpoints'] == PROBES, 'Wrong prescribed probe points')
    return p


def _expected_points(case, kind):
    if 'sensitivity_profile' in case or 'qe_reference_profile' in case:
        _contract(case)
        return case['probe_kpoints'] if kind == 'spectrum' else [p['coordinate_fractional'] for p in case['kpoints']]
    if kind == 'spectrum':
        return PROBES
    points = [p['coordinate_fractional'] for p in case.get('kpoints',
              [{'coordinate_fractional': p, 'weight_spatial': .125} for p in SCF_POINTS])]
    match_points(SCF_POINTS, points, GATES['coordinate_abs'])
    if 'kpoints' in case:
        check(all(p['weight_spatial'] == .125 for p in case['kpoints']), 'Wrong requested SCF weights')
    return points


def _float_field(parent, path, expected, absolute=1e-12):
    actual = finite(text(parent, path))
    check(math.isclose(actual, expected, rel_tol=1e-12, abs_tol=absolute), 'Wrong native ' + path)
    return actual


def parse_si_qe(xml_path, stdout, stderr, *, kind, case, process_exit_code):
    """Parse text streams and one current XML; caller supplies authenticated bytes.

    The runner must attach run_id/source_scf_run_id/density_source_sha256 from
    its immutable save-file receipt before a spectrum can enter comparison.
    A bands output never supplies new SCF E/F or solves an occupation problem.
    """
    pseudo = _contract(case)
    sensitivity, reference = 'sensitivity_profile' in case, 'qe_reference_profile' in case
    registered = sensitivity or reference
    tau = case['electrons']['temperature_ha'] if registered else .001
    ecutwfc = case['cutoffs']['qe_ecutwfc_ry']/2 if registered else 30.
    ecutrho = case['cutoffs']['qe_ecutrho_ry']/2 if registered else 120.
    if registered:
        check(hash_string(case.get('case_sha256')), 'Missing authenticated prepared case hash')
    check(kind in ('scf', 'spectrum'), 'Unsupported Si QE action')
    check(type(process_exit_code) is int and process_exit_code == 0, 'QE process exit was not zero')
    check(isinstance(stdout, str) and isinstance(stderr, str), 'Native streams must be text')
    check(case.get('verified_pseudo_sha256') == pseudo['sha256'], 'Missing authenticated runtime UPF receipt')
    warning = native_warnings(stdout, stderr, process_exit_code)
    check(not warning['fatal_native_lines'], 'Native fatal error prevents usable output')
    check('JOB DONE.' in stdout and re.findall(r'Program\s+PWSCF\s+v\.([^\s]+)', stdout) == ['7.5'],
          'Missing normal QE 7.5 completion')
    calc = 'scf' if kind == 'scf' else 'bands'
    boundary = 'End of self-consistent calculation' if kind == 'scf' else 'End of band structure calculation'
    check(boundary in stdout, 'Missing final native spectrum boundary')
    final_stdout = stdout.rsplit(boundary, 1)[1]
    root = ET.parse(xml_path).getroot()
    check(root.tag == '{http://www.quantum-espresso.org/ns/qes/qes-1.0}espresso'
          and root.get('Units') == 'Hartree atomic units', 'Unsupported XML root/units')
    for node in root.iter():
        node.tag = node.tag.split('}')[-1]
    fmt, creator = require(root, 'general_info/xml_format'), require(root, 'general_info/creator')
    check((fmt.get('NAME'), fmt.get('VERSION'), creator.get('NAME'), creator.get('VERSION')) ==
          ('QEXSD', '25.05.21', 'PWSCF', '7.5'), 'Unsupported XML format/creator')
    check(text(root, 'exit_status') == '0', 'Native XML exit failure')
    require(root, 'closed')
    outputs = root.findall('output')
    check(bool(outputs), 'Missing final XML output')
    out, inp = outputs[-1], require(root, 'input')
    control = require(inp, 'control_variables')
    check(text(control, 'calculation') == calc, 'SCF/spectrum output kind mismatch')
    if registered:
        check(text(control, 'prefix') == case['qe']['prefix'], 'Wrong native profile prefix')
    check(text(control, 'restart_mode') == 'from_scratch', 'Unexpected restart mode')
    check(text(control, 'verbosity') == 'high' and text(control, 'disk_io') == 'low', 'Wrong output/save controls')
    check(not boolean(control, 'forces') and not boolean(control, 'stress'), 'Unexpected force/stress calculation')
    bands = require(out, 'band_structure')
    flags = {'lsda': False, 'noncolin': True, 'spinorbit': True}
    for parent, prefix in ((inp, 'spin/'), (bands, ''), (out, 'magnetization/')):
        check({k: boolean(parent, prefix + k) for k in flags} == flags, 'Wrong charge-only SOC spinor flags')
    check(not boolean(out, 'magnetization/do_magnetization'), 'Actual magnetic feedback enabled')
    check(abs(finite(text(out, 'magnetization/absolute'))) <= 1e-10, 'Unexpected native magnetization')
    for name in ('nosym', 'noinv', 'no_t_rev'):
        check(boolean(inp, 'symmetry_flags/' + name), 'Unexpected k reduction: ' + name)
    electron = require(inp, 'electron_control')
    check(boolean(electron, 'diago_full_acc'), 'Full empty-state accuracy missing')
    threshold = 1e-10 if kind == 'scf' else 1e-13
    _float_field(electron, 'diago_thr_init', threshold, 0.)  # QE XML writer keeps this one field in Ry.
    _float_field(electron, 'conv_thr', 5e-13, 0.)
    _float_field(electron, 'mixing_beta', .3)
    check(positive_int(text(electron, 'max_nstep')) == 200, 'Wrong SCF step ceiling')
    solver = 'davidson' if kind == 'scf' else 'cg'
    check(text(electron, 'diagonalization') == solver, 'Wrong actual solver')
    if kind == 'spectrum':
        check(positive_int(text(electron, 'diago_cg_maxiter')) == 300, 'Wrong CG iteration ceiling')
    banners = re.findall(r'^\s*(Davidson|CG style) diagonalization(?: with overlap)?\s*$', stdout, re.I | re.M)
    check(bool(banners) and all(x.lower() == ('davidson' if kind == 'scf' else 'cg style') for x in banners),
          'Native solver banner mismatch')
    check(text(inp, 'bands/occupations') == text(bands, 'occupations_kind') == 'smearing', 'FD smearing missing')
    for parent in (require(inp, 'bands'), bands):
        smear = require(parent, 'smearing')
        check((smear.text or '').strip() == 'fd' and finite(smear.get('degauss', 'nan')) == tau,
              'Wrong native FD temperature/units')
    _float_field(inp, 'bands/tot_charge', 0.)
    ne = _float_field(bands, 'nelec', 8., 1e-8)
    expected_points = _expected_points(case, kind)
    check(positive_int(text(bands, 'nbnd')) == 24 and positive_int(text(bands, 'nks')) == len(expected_points),
          'Wrong spinor band or requested k count')
    structure = require(out, 'atomic_structure')
    check(positive_int(structure.get('nat')) == 2, 'Si requires two atoms')
    alat = finite(structure.get('alat', 'nan'))
    check(alat > 0, 'Invalid lattice scale')
    lattice = [vector(require(structure, 'cell/a' + str(i)), 3) for i in (1, 2, 3)]
    reciprocal = [vector(require(out, 'basis_set/reciprocal_lattice/b' + str(i)), 3) for i in (1, 2, 3)]
    check(all(abs(x-y) <= 1e-9 for row, ref in zip(lattice, LATTICE) for x, y in zip(row, ref)), 'Wrong native Si cell')
    check(all(abs(dot(a, b)/alat - (i == j)) <= 1e-10
              for i, a in enumerate(lattice) for j, b in enumerate(reciprocal)), 'Reciprocal duality failure')
    atoms = require(structure, 'atomic_positions').findall('atom')
    check(len(atoms) == 2 and all(a.get('name') == 'Si' for a in atoms), 'Wrong native species or atom count')
    positions = [[dot(vector(a, 3), b)/alat for b in reciprocal] for a in atoms]
    match_points(POSITIONS, positions, 1e-10)
    for parent, prefix in ((inp, 'basis/'), (out, 'basis_set/')):
        _float_field(parent, prefix + 'ecutwfc', ecutwfc)
        _float_field(parent, prefix + 'ecutrho', ecutrho)
        for grid in ('fft_grid', 'fft_smooth'):
            check([positive_int(require(parent, prefix + grid).get('nr' + str(i))) for i in (1, 2, 3)] == [48]*3,
                  'Native hard/smooth FFT must be explicitly 48 cubed')
    for parent in (inp, out):
        species = require(parent, 'atomic_species').findall('species')
        check(len(species) == 1 and species[0].get('name') == 'Si'
              and text(species[0], 'pseudo_file') == pseudo['filename'], 'Wrong native UPF species/filename')
    magnetization = require(inp, 'atomic_species/species').find('starting_magnetization')
    check(magnetization is None or finite(magnetization.text or '') == 0, 'Nonzero initial magnetization')
    reads = re.findall(r'PseudoPot\.\s*#\s*\d+\s+for\s+(\w+)\s+read from file:\s*(\S+)', stdout)
    summaries = re.findall(r'Pseudo is\s+([^\n,]+),\s*Zval\s*=\s*(\S+)', stdout)
    check(len(reads) == len(summaries) == 1 and reads[0][0] == 'Si'
          and Path(reads[0][1]).name == pseudo['filename'], 'Ambiguous native UPF read')
    check(' '.join(summaries[0][0].split()) == 'Norm-conserving + core correction'
          and finite(summaries[0][1]) == 4., 'Native NC/NLCC/valence mismatch')
    declarations = re.findall(r'Exchange-correlation\s*=\s*([^\n]+)\s*\(([\d\s]+)\)', stdout)
    check(len(declarations) == 1, 'Missing unique native XC declaration')
    indices = [int(x) for x in declarations[0][1].split()]
    check(text(out, 'dft/functional').upper() == 'PBE' and indices[:4] == [1, 4, 3, 4]
          and not any(indices[4:]), 'Native XC is not complete PBE')
    points = []
    for block in bands.findall('ks_energies'):
        kp = require(block, 'k_point')
        raw = vector(kp, 3)
        values = vector(require(block, 'eigenvalues'), 24)
        check(all(a <= b+1e-12 for a, b in zip(values, values[1:])), 'Unsorted native spectrum')
        onode = block.find('occupations')
        occ = None if onode is None else vector(onode, 24)
        check(occ is not None or kind == 'spectrum', 'SCF occupations missing')
        check(occ is None or all(0 <= f <= 1 for f in occ), 'Spinor occupation capacity is one')
        points.append({'coordinate_fractional': [dot(a, raw)/alat for a in lattice],
                       'coordinate_raw': raw, 'weight_spatial': finite(kp.get('weight', 'nan')),
                       'eigenvalues_ha': values, 'eigenvalues_ev': [v*HARTREE_EV for v in values],
                       'occupations': occ, 'npw': positive_int(text(block, 'npw'))})
    order = match_points(expected_points, [p['coordinate_fractional'] for p in points], 1e-10)
    check(all(abs(p['weight_spatial']-1/len(expected_points)) <= 1e-10 for p in points), 'Wrong native k weights')
    check(abs(sum(p['weight_spatial'] for p in points)-1) <= 1e-10, 'Native k weights do not sum to one')
    spectrum_check = stdout_spectrum_check(final_stdout, points, lattice, alat, calc, GATES)
    ethr = [finite(s) for s in re.findall(r'ethr\s*=\s*([^\s,]+)', stdout)]
    check(bool(ethr) and min(ethr) > 0, 'Missing native diagonalization thresholds')
    if kind == 'spectrum':
        check(all(math.isclose(t, threshold, rel_tol=1e-12, abs_tol=0.) for t in ethr), 'Wrong actual CG threshold')
    starts = [line.strip() for line in stdout.splitlines()
              if re.search(r'(?:Starting wfcs|potential is recalculated from file)', line, re.I)]
    check(any(re.search(r'Starting wfcs.*random.*atomic', s, re.I) for s in starts), 'Atomic+random wavefunction start unconfirmed')
    check(not any('from file' in s.lower() and 'wfcs' in s.lower() for s in starts), 'Reused numbered wavefunctions are not authorized')
    trace, energy, electron_sum = [], None, None
    if kind == 'scf':
        check(not any('potential is recalculated from file' in s.lower() for s in starts), 'Fresh SCF potential was read from file')
        conv = re.findall(r'convergence\s+(has been achieved|NOT achieved)', stdout, re.I)
        check(bool(conv) and conv[-1].lower() == 'has been achieved', 'Final native SCF not converged')
        scf = require(out, 'convergence_info/scf_conv')
        check(boolean(scf, 'convergence_achieved'), 'Final XML SCF not converged')
        steps = positive_int(text(scf, 'n_scf_steps'))
        error = finite(text(scf, 'scf_error'))
        check(0 <= error <= 5e-13, 'Native SCF error exceeds requested threshold')
        electron_sum = sum(p['weight_spatial']*sum(p['occupations']) for p in points)
        check(abs(electron_sum-ne) <= 1e-8, 'Valence occupations do not integrate to eight electrons')
        node = require(out, 'total_energy')
        native = {n.tag: finite(n.text or '') for n in node}
        f, demet = native['etot'], native['demet']
        check(demet <= 1e-10, 'FD entropy energy has wrong sign')
        fields = {}
        for key, pattern, value, unit in (
            ('free', r'!\s+total energy\s*=\s*(\S+)\s+Ry', f, 'Ry'),
            ('minus_TS', r'smearing contrib\.\s*\(-TS\)\s*=\s*(\S+)\s+Ry', demet, 'Ry'),
            ('internal', r'internal energy E=F\+TS\s*=\s*(\S+)\s+Ry', f-demet, 'Ry')):
            tokens = re.findall(pattern, final_stdout)
            check(bool(tokens), 'Missing final native ' + key)
            fields[key] = text_consistency(value, tokens[-1], unit, 1e-10)
        mu = finite(text(bands, 'fermi_energy'))
        mtokens = re.findall(r'the Fermi energy is\s*(\S+)\s*ev', final_stdout, re.I)
        check(bool(mtokens), 'Missing native chemical potential')
        fields['fermi'] = text_consistency(mu, mtokens[-1], 'eV', 1e-10)
        energy = {'internal_ha': f-demet, 'free_ha': f, 'minus_TS_ha': demet,
                  'entropy_dimensionless': -demet/tau, 'native_components_ha': native,
                  'native_stdout': fields, 'convention': 'Native F=etot; E=F-demet; no constant correction'}
        iteration_matches = list(re.finditer(r'iteration\s*#\s*(\d+)', stdout, re.I))
        for i, m in enumerate(iteration_matches):
            section = stdout[m.end():iteration_matches[i+1].start() if i+1 < len(iteration_matches) else len(stdout)]
            estimate = re.findall(r'estimated scf accuracy\s*[<=>]+\s*(\S+)\s*Ry', section, re.I)
            totals = re.findall(r'(?:!\s*)?total energy\s*=\s*(\S+)\s*Ry', section, re.I)
            trace.append({'iteration': int(m.group(1)), 'estimated_scf_accuracy_ry': None if not estimate else finite(estimate[0]),
                          'printed_free_ry': None if not totals else finite(totals[0])})
        check(len(trace) == steps and [x['iteration'] for x in trace] == list(range(1, steps+1)), 'Incomplete SCF iteration trace')
        scf_record = {'converged': True, 'iterations': steps, 'error_ha': error, 'trace': trace}
    else:
        check(any('potential is recalculated from file' in s.lower() for s in starts), 'Saved-density potential read unconfirmed')
        check('Band Structure Calculation' in stdout and not re.search(r'iteration\s*#\s*\d+', stdout, re.I),
              'Fixed-density task contains SCF feedback or lacks bands marker')
        mnode = bands.find('fermi_energy')
        mu = None if mnode is None else finite(mnode.text or '')
        scf_record = None
    result = {'schema_version': 1, 'case': case['case'], 'kind': kind, 'code': 'QE', 'execution_status': 'PASS',
              'process_exit_code': 0, 'input_comparability_status': 'PASS', 'physical_operator': 'full_soc',
              'n_electrons': 8, 'n_bands': 24, 'occupation_capacity': 1, 'temperature_ha': tau,
              'pseudo_sha256': pseudo['sha256'], 'nlcc': True, 'z_valence': 4, 'n_atoms': 2,
              'xc': 'PBE', 'fft_grid': [48]*3, 'lattice_vectors_bohr': lattice, 'positions_fractional': positions,
              'kpoints': [points[i] for i in order], 'requested_to_xml_indices': order,
              'fermi_energy_ha': mu, 'energy': energy, 'scf': scf_record, 'electron_sum': electron_sum,
              'occupations_use': 'SCF_DENSITY' if kind == 'scf' else 'DIAGNOSTIC_ONLY_NOT_DENSITY_FEEDBACK',
              'precision': {'diago_thr_init_ry': threshold, 'ethr_history_ry': ethr,
                            'explicit_wavefunction_residuals': 'NOT_AVAILABLE', 'stdout_spectrum': spectrum_check},
              'warning_evidence': warning, 'read_start_evidence': starts,
              'eigensolver_status': 'EIGENSOLVER_REVIEW_REQUIRED' if warning['eigenvalues_not_converged'] else 'REPORTED_THRESHOLD_AVAILABLE',
              'raw_sha256': {'xml': hashlib.sha256(Path(xml_path).read_bytes()).hexdigest(),
                             'stdout': hashlib.sha256(stdout.encode()).hexdigest(), 'stderr': hashlib.sha256(stderr.encode()).hexdigest()}}
    if sensitivity:
        result.update(sensitivity_profile=case['sensitivity_profile'], case_sha256=case['case_sha256'],
                      cutoffs=dict(case['cutoffs']), requested_kpoint_count=len(expected_points))
    if reference:
        result.update(qe_reference_profile=case['qe_reference_profile'], profile_type='QE_REFERENCE',
                      case_sha256=case['case_sha256'], cutoffs=dict(case['cutoffs']),
                      requested_kpoint_count=len(expected_points), dftk_execution_status='NOT_RUN')
    json.dumps(result, allow_nan=False)
    return result


def _levels(values):
    check(isinstance(values, list) and len(values) == 24, 'Exactly 24 complete spinor levels required')
    values = [number(v) for v in values]
    check(all(a <= b+1e-12 for a, b in zip(values, values[1:])), 'Levels must be in native sorted order')
    return values


def analyze_gamma(values_ha):
    """Keep fixed one-based states 3:4 and 5:8; never choose a favorable window."""
    v = _levels(values_ha)
    doublet, quartet = v[2:4], v[4:8]
    means = [sum(group)/len(group) for group in (doublet, quartet)]
    lower, upper = (v[2]-v[1])*HARTREE_EV, (v[8]-v[7])*HARTREE_EV
    widths = [(max(group)-min(group))*HARTREE_EV for group in (doublet, quartet)]
    delta = (means[1]-means[0])*HARTREE_EV
    assignment = lower >= .02 and upper >= .02
    structure = all(w <= 1e-5 for w in widths)
    return {'values_ha': v, 'values_ev': [x*HARTREE_EV for x in v],
            'fixed_state_indices_one_based': {'split_off': [3, 4], 'upper': [5, 6, 7, 8]},
            'doublet_mean_ha': means[0], 'quartet_mean_ha': means[1],
            'doublet_width_ev': widths[0], 'quartet_width_ev': widths[1],
            'lower_isolation_ev': lower, 'upper_isolation_ev': upper,
            'delta_so_ev': delta, 'six_state_width_ev': (v[7]-v[2])*HARTREE_EV,
            'manifold_assignment_status': 'PASS' if assignment else 'MANIFOLD_ASSIGNMENT_REVIEW_REQUIRED',
            'multiplet_structure_status': 'PASS' if structure else 'MISMATCH',
            'resolvable_soc_status': 'PASS' if delta >= .005 else 'MISMATCH',
            'space_group_irrep_assignment': 'NOT_COMPUTED'}


def _receipt(receipt, label, case, null=False):
    check(isinstance(receipt, dict), 'Missing spectrum receipt')
    check(receipt.get('schema_version') == 1 and receipt.get('case') == CASE, 'Wrong spectrum schema/case')
    check(receipt.get('kind') == ('null' if null else 'spectrum'), 'SCF/null/full spectrum mixing')
    check(receipt.get('code') == ('QE' if label == 'Q' else 'DFTK'), 'Wrong program/source label')
    check(receipt.get('execution_status') == 'PASS' and type(receipt.get('process_exit_code')) is int
          and receipt['process_exit_code'] == 0, 'Failed worker cannot supply comparison input')
    check(isinstance(receipt.get('run_id'), str) and bool(receipt['run_id']), 'Missing unique run ID')
    expected = case['binding'][label]
    check(receipt['run_id'] == expected['null_run_id' if null else 'spectrum_run_id'], 'Stale or wrong spectrum run ID')
    check(receipt.get('source_scf_run_id') == expected['scf_run_id'], 'Wrong SCF source binding')
    check(hash_string(expected['density_sha256']) and receipt.get('density_source_sha256') == expected['density_sha256'],
          'Wrong final-density hash binding')
    check(receipt.get('physical_operator') == ('spin_trace_null' if null else 'full_soc'), 'Wrong physical operator')
    check(receipt.get('pseudo_sha256') == case['pseudo']['sha256'], 'Wrong spectrum UPF hash')
    check(receipt.get('n_electrons') == 8 and receipt.get('n_bands') == 24
          and receipt.get('occupation_capacity') == 1, 'Wrong electron/spinor count')
    for key in ('fitted_shift', 'per_k_shift', 'per_band_shift', 'experimental_target_ev', 'energy_correction_ha'):
        check(key not in receipt, 'Fitting or correction is not permitted: ' + key)
    points = receipt['kpoints']
    requested = [[0., 0., 0.]] if null else PROBES
    order = match_points(requested, [p['coordinate_fractional'] for p in points], 1e-10)
    points = [points[i] for i in order]
    for point in points:
        _levels(point['eigenvalues_ha'])
    return points


def _fd_diagnostic(levels, mu, tau=.001):
    # Evaluate the declared FD function at the existing SCF chemical potential;
    # no electron constraint is solved on the diagnostic probe point set.
    check(number(tau) > 0, 'FD diagnostic temperature must be finite and positive')
    result = []
    for value in levels:
        x = (value-mu)/tau
        e = math.exp(-abs(x))
        result.append(e/(1+e) if x >= 0 else 1/(1+e))
    return result


def compare_spectra(d, q, null, case):
    """Pure public-data arithmetic with explicit current-run/final-density binding."""
    _contract(case)
    dp, qp, np = _receipt(d, 'D', case), _receipt(q, 'Q', case), _receipt(null, 'D', case, True)
    check(len({d['run_id'], q['run_id'], null['run_id']}) == 3, 'Distinct tasks require distinct run IDs')
    dg, qg, ng = (analyze_gamma(p[0]['eigenvalues_ha']) for p in (dp, qp, np))
    metrics, gamma_occupations = {}, {}
    for label, receipt, points in (('D', d, dp), ('Q', q, qp)):
        mu = number(receipt['fermi_energy_ha'])
        gamma_occupations[label] = _fd_diagnostic(points[0]['eigenvalues_ha'], mu)
        pair = max(abs(p['eigenvalues_ha'][i]-p['eigenvalues_ha'][i+1])
                   for p in points for i in range(0, 24, 2))
        tr = max(abs(a-b) for a, b in zip(points[1]['eigenvalues_ha'], points[2]['eigenvalues_ha']))
        metrics[label] = {'kramers_max_ha': pair, 'p_minus_p_max_ha': tr,
                          'status': 'PASS' if max(pair, tr) <= 1e-7 else 'MISMATCH',
                          'scope': 'Sorted spectral checks; physical-q operator TR measured separately by runner'}
    full_prerequisites = all(g['manifold_assignment_status'] == 'PASS' and g['multiplet_structure_status'] == 'PASS'
                             for g in (dg, qg))
    occupied = all(min(f[2:8]) >= .99999999 for f in gamma_occupations.values())
    assignment_status = 'PASS' if full_prerequisites else 'MANIFOLD_ASSIGNMENT_REVIEW_REQUIRED'
    null_width = ng['six_state_width_ev']
    null_status = 'PASS' if (ng['manifold_assignment_status'] == 'PASS' and null_width <= 1e-5
                            and dg['delta_so_ev'] >= 100*null_width) else 'MISMATCH'
    diff = dg['delta_so_ev']-qg['delta_so_ev']
    split = (assignment_status == 'PASS' and all(g['resolvable_soc_status'] == 'PASS' for g in (dg, qg))
             and abs(diff) <= 1e-4)
    diagnostics = []
    for pd, pq in zip(dp, qp):
        vd, vq = pd['eigenvalues_ha'], pq['eigenvalues_ha']
        raw = [a-b for a, b in zip(vd, vq)]
        refd, refq = dg['quartet_mean_ha'], qg['quartet_mean_ha']
        delta = [(a-refd)-(b-refq) for a, b in zip(vd, vq)]
        diagnostics.append({'coordinate_fractional': pd['coordinate_fractional'],
                            'D_raw_ha': vd, 'Q_raw_ha': vq, 'raw_D_minus_Q_ha': raw,
                            'D_global_referenced_ha': [a-refd for a in vd],
                            'Q_global_referenced_ha': [b-refq for b in vq],
                            'global_referenced_D_minus_Q_ha': delta,
                            'max_abs_referenced_ev': max(map(abs, delta))*HARTREE_EV,
                            'rms_referenced_ev': math.sqrt(sum(x*x for x in delta)/24)*HARTREE_EV})
    residuals = {}
    for name, points in (('D_full', dp), ('D_null', np)):
        for p in points:
            check(isinstance(p.get('residuals_ha'), list) and len(p['residuals_ha']) == 24, 'Missing all24 DFTK explicit residuals')
            check(all(number(x) >= 0 for x in p['residuals_ha']), 'Invalid explicit residual')
            check(number(p.get('gram_frobenius')) >= 0, 'Invalid Gram measurement')
        r = max(number(x) for p in points for x in p['residuals_ha'])
        gram = max(number(p['gram_frobenius']) for p in points)
        residuals[name] = {'max_explicit_residual_ha': r, 'max_gram_frobenius': gram,
                           'status': 'PASS' if r <= 1e-9 and gram <= 1e-9 else 'MISMATCH',
                           'evidence_level': 'RUNNER_REPORTED'}
    qwarning = q.get('warning_evidence', {})
    q_precision = q.get('precision', {})
    check(q_precision.get('diago_thr_init_ry') == 1e-13 and q_precision.get('ethr_history_ry')
          and all(x == 1e-13 for x in q_precision['ethr_history_ry']), 'Missing actual fixed CG threshold evidence')
    qe_gate = 'EIGENSOLVER_REVIEW_REQUIRED' if qwarning.get('eigenvalues_not_converged') else 'REPORTED_THRESHOLD_AVAILABLE'
    result = {'schema_version': 1, 'case': CASE, 'comparison_execution_status': 'PASS',
              'manifold_assignment_status': assignment_status,
              'splitting_comparison_status': 'PASS' if split else 'MISMATCH',
              'spin_trace_control_status': null_status, 'D_gamma': dg, 'Q_gamma': qg, 'D_null_gamma': ng,
              'delta_so_D_minus_Q_ev': diff,
              'delta_so_relative_difference': diff/qg['delta_so_ev'] if qg['delta_so_ev'] else None,
              'gamma_fd_occupations_at_existing_scf_mu': gamma_occupations,
              'gamma_occupation_saturation_tolerance': 1e-8,
              'gamma_occupation_diagnostic_status': 'PASS' if occupied else 'REVIEW_REQUIRED',
              'gamma_occupation_scope': 'Conservative extra predeclared diagnostic .99999999, not a physical-failure threshold supplied by the task; spectra/statistics retained regardless',
              'reference_rule': 'Each program Gamma upper-quartet mean; one global value for all probes; no fitting',
              'spectra': diagnostics, 'time_reversal': metrics, 'D_precision': residuals,
              'Q_eigensolver_status': qe_gate, 'Q_warnings': qwarning,
              'bindings': case['binding'], 'numerical_review_status': 'REVIEW_REQUIRED',
              'physical_convergence': 'NOT_ESTABLISHED', 'null_interpretation': 'Fixed D final density spin-trace; not scalar UPF or SCF',
              'band_crossing_between_sampled_probes': 'NOT_MEASURED; no continuous-path or irrep tracking claimed',
              'native_QE_NL_independent': 'NOT_MEASURED', 'noncollinear_magnetic_XC': 'NOT_IMPLEMENTED'}
    json.dumps(result, allow_nan=False)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Recompute Phase 8A public spectra only; no solver.')
    for field in ('case', 'd', 'q', 'null'):
        parser.add_argument('--' + field, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        documents = {name: json.loads(getattr(args, name).read_text()) for name in ('case', 'd', 'q', 'null')}
        result = compare_spectra(documents['d'], documents['q'], documents['null'], documents['case'])
        print(json.dumps(result, indent=2, allow_nan=False))
        passed = (all(result[k] == 'PASS' for k in ('manifold_assignment_status', 'splitting_comparison_status', 'spin_trace_control_status'))
                  and all(v['status'] == 'PASS' for v in result['time_reversal'].values())
                  and all(v['status'] == 'PASS' for v in result['D_precision'].values())
                  and result['Q_eigensolver_status'] == 'REPORTED_THRESHOLD_AVAILABLE')
        return 0 if passed else 1
    except (ValueError, OSError, KeyError, TypeError, ET.ParseError) as error:
        print(json.dumps({'comparison_execution_status': 'FAIL', 'reason': str(error)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
