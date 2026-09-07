#!/usr/bin/env python3
"""Restricted Phase 7B native-output adapter; no QE calculation is implemented.

The frozen SOC parser checks the physical case, units, finite spectra and energy
semantics. This adapter supplies the real new case and adds the six prescribed
solver/grid contracts. File-copy/source binding belongs to the runner receipt.
"""
import hashlib
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from parse_qe_soc import (QeSocParseError, parse_qe_soc, _case_contract,
                          require, text, positive_int)

SLOTS = ('I36', 'D36', 'C36', 'G40', 'D40', 'C40')
IEEE_FLAGS = ('IEEE_INVALID_FLAG', 'IEEE_DIVIDE_BY_ZERO', 'IEEE_OVERFLOW_FLAG',
              'IEEE_UNDERFLOW_FLAG', 'IEEE_INEXACT_FLAG')
SOURCES = {
    'input_controls': 'https://gitlab.com/QEF/q-e/-/raw/qe-7.5/PW/Doc/INPUT_PW.def',
    'input_threshold_units': 'https://github.com/QEF/q-e/blob/qe-7.5/PW/src/pw_init_qexsd_input.f90#L482-L486',
    'initialization_only': 'https://github.com/QEF/q-e/blob/qe-7.5/PW/src/run_pwscf.f90#L148-L156',
    'initialization_process_status': 'https://github.com/QEF/q-e/blob/qe-7.5/PW/src/stop_run.f90#L54-L92',
    'solver_xml_name': 'https://github.com/QEF/q-e/blob/qe-7.5/PW/src/pw_init_qexsd_input.f90#L477-L486',
    'cg_stdout_banner': 'https://github.com/QEF/q-e/blob/qe-7.5/PW/src/c_bands.f90#L1037-L1040',
    'algorithm_control_serialization': 'https://github.com/QEF/q-e/blob/qe-7.5/Modules/qexsd_input.f90#L226-L255',
}


def native_warnings(stdout, stderr, process_exit_code):
    """Retain complete stderr and warning provenance; absence is not clearance."""
    if not isinstance(stdout, str) or not isinstance(stderr, str):
        raise QeSocParseError('Warning inputs must be native text strings')
    warnings = []
    unconverged = []
    fatal = []
    for stream, value in (('stdout', stdout), ('stderr', stderr)):
        for number, line in enumerate(value.splitlines(), 1):
            entry = {'stream': stream, 'line': number, 'text': line}
            profile = (re.fullmatch(r'\s*Called by c_bands:\s*', line, re.I)
                       or re.fullmatch(r'\s*c_bands\s*:\s*[\d.]+s\s+CPU\s+[\d.]+s\s+WALL\s*\(\s*\d+\s+calls?\s*\)\s*', line, re.I))
            if not profile and re.search(r'warning|^\s*c_bands\s*:|not\s+converged|not\s+achieved|IEEE_|floating.point|error|%%%%', line, re.I):
                warnings.append(entry)
            if re.search(r'(?:eigenvalues?\s+not\s+converged|c_bands\s*:.*not\s+converged)', line, re.I):
                unconverged.append(entry)
            if re.search(r'Error in routine|^\s*%{5,}|Program received signal|Segmentation fault|SIGSEGV|MPI_ABORT|ERROR STOP', line, re.I):
                fatal.append(entry)
    flags = {flag: {'reported': flag in stdout or flag in stderr,
                    'stdout': flag in stdout, 'stderr': flag in stderr}
             for flag in IEEE_FLAGS}
    return {'process_exit_code': process_exit_code,
            'stderr_lines': stderr.splitlines(), 'warning_lines': warnings,
            'ieee_flags': flags,
            'ieee_warning_status': 'REPORTED' if any(v['reported'] for v in flags.values()) else 'NOT_REPORTED',
            'ieee_localization_status': 'NOT_LOCALIZED',
            'eigenvalues_not_converged': bool(unconverged),
            'unconverged_eigenvalue_lines': unconverged,
            'fatal_native_lines': fatal,
            'c_bands_lines': [x for x in warnings if re.match(r'\s*c_bands\s*:', x['text'], re.I)],
            'note': 'Reported flags are retained independently of exit code and spectral stability. Unreported flags are not proven absent.'}


def _contract(case, slot):
    if slot not in SLOTS or case.get('case') != 'mg-soc-qe-diagnostics-v1' or case.get('phase') != '7B':
        raise QeSocParseError('Wrong Phase 7B case or unsupported diagnostic slot')
    _case_contract(case)
    bands = slot.startswith(('D', 'C'))
    expected = {'calculation': 'bands' if bands else 'scf',
                'initialization_only': slot == 'I36',
                'solver': 'cg' if slot.startswith('C') else 'david',
                'diago_thr_init_ry': 1e-13 if bands else 1e-10,
                'fft_grid': [40]*3 if slot.endswith('40') else [36]*3,
                'source_slot': ('G40' if slot.endswith('40') else 'Q36') if bands else None}
    if bands:
        expected['diago_cg_maxiter' if slot.startswith('C') else 'diago_david_ndim'] = 200 if slot.startswith('C') else 2
    supplied = case['slots'][slot]
    if any(supplied.get(key) != value for key, value in expected.items()):
        raise QeSocParseError('Requested slot differs from the fixed six-slot contract')
    qe = case['qe']
    for key, value in (('calculation', expected['calculation']),
                       ('diagonalization', expected['solver']),
                       ('diago_thr_init_ry', expected['diago_thr_init_ry'])):
        if qe.get(key) != value:
            raise QeSocParseError('Actual requested QE parameter differs from slot: ' + key)
    for key in ('diago_cg_maxiter', 'diago_david_ndim'):
        if key in expected and qe.get(key) != expected[key]:
            raise QeSocParseError('Actual requested algorithm control differs from slot: ' + key)
    return expected


def _xml(path):
    root = ET.parse(path).getroot()
    if root.tag != '{http://www.quantum-espresso.org/ns/qes/qes-1.0}espresso' or root.get('Units') != 'Hartree atomic units':
        raise QeSocParseError('Unsupported diagnostic XML namespace or units', 'BLOCKED')
    for node in root.iter():
        node.tag = node.tag.split('}')[-1]
    creator = require(root, 'general_info/creator')
    fmt = require(root, 'general_info/xml_format')
    if (creator.get('NAME'), creator.get('VERSION'), fmt.get('NAME'), fmt.get('VERSION')) != ('PWSCF', '7.5', 'QEXSD', '25.05.21'):
        raise QeSocParseError('Unsupported diagnostic XML creator or format', 'BLOCKED')
    return root


def _read_start(stdout, calculation):
    evidence = {'potential_from_file': [], 'wavefunctions_from_file': [],
                'fallback_lines': [], 'scf_iteration_lines': [], 'band_structure_lines': []}
    for number, line in enumerate(stdout.splitlines(), 1):
        item = {'line': number, 'text': line}
        if re.search(r'The potential is recalculated from file', line, re.I):
            evidence['potential_from_file'].append(item)
        if re.search(r'Starting wfcs from file', line, re.I):
            evidence['wavefunctions_from_file'].append(item)
        if re.search(r'(?:starting.*(?:atomic|random)|(?:wfc|wavefunction|potential).*not found|(?:falling|fall)\s*back)', line, re.I):
            evidence['fallback_lines'].append(item)
        if re.search(r'iteration\s*#\s*\d+', line, re.I):
            evidence['scf_iteration_lines'].append(item)
        if re.search(r'^\s*Band Structure Calculation\s*$', line, re.I):
            evidence['band_structure_lines'].append(item)
    if calculation == 'bands':
        if (not evidence['potential_from_file'] or not evidence['wavefunctions_from_file']
                or not evidence['band_structure_lines']):
            raise QeSocParseError('Native bands output does not establish file potential, file wavefunctions and bands execution', 'BLOCKED')
        if evidence['fallback_lines'] or evidence['scf_iteration_lines']:
            raise QeSocParseError('Bands execution fell back or performed an unexpected SCF iteration')
    evidence['status'] = 'PASS' if calculation == 'bands' else 'NOT_APPLICABLE_FRESH_SCF'
    evidence['source_hash_binding_status'] = 'RUNNER_RECEIPT_REQUIRED' if calculation == 'bands' else 'NOT_APPLICABLE'
    return evidence


def _initialization(xml_path, stdout, expected, process_exit_code):
    if type(process_exit_code) is not int or process_exit_code not in (0, 255):
        raise QeSocParseError('Initialization process status is outside QE 7.5 dry-run return conventions')
    if re.findall(r'Program\s+PWSCF\s+v\.([^\s]+)', stdout) != ['7.5']:
        raise QeSocParseError('Unsupported or ambiguous initialization executable banner', 'BLOCKED')
    if re.search(r'(?<!\w)[+-]?(?:nan|inf(?:inity)?)(?!\w)', stdout, re.I):
        raise QeSocParseError('Initialization native summary contains a nonfinite numeric token')
    solve = re.search(r'iteration\s*#|Band Structure Calculation|diagonalization with overlap|CG style diagonalization|ethr\s*=|End of self-consistent|convergence has been achieved', stdout, re.I)
    if solve:
        raise QeSocParseError('Initialization-only output contains numerical-solve evidence')
    if xml_path is None:
        raise QeSocParseError('Initialization XML config-init status unavailable; no SCF success is inferred', 'BLOCKED')
    root = _xml(xml_path)
    if text(root, 'exit_status') != '255' or text(root, 'input/control_variables/nstep') != '0':
        raise QeSocParseError('Initialization must expose native config-init exit_status=255 and nstep=0')
    if text(root, 'input/control_variables/calculation') != 'scf':
        raise QeSocParseError('Initialization calculation differs from requested SCF setup')
    if root.find('output/band_structure') is not None:
        raise QeSocParseError('Initialization XML unexpectedly contains a solved spectrum')
    grids = re.findall(r'(Dense|Smooth)\s+grid[^\n]*FFT dimensions:\s*\(\s*(\d+),\s*(\d+),\s*(\d+)\s*\)', stdout, re.I)
    observed = {kind.lower(): [int(a), int(b), int(c)] for kind, a, b, c in grids}
    if any(grid != expected['fft_grid'] for grid in observed.values()):
        raise QeSocParseError('Initialization actual FFT grid differs from prescribed grid')
    basis = root.find('output/basis_set')
    xml_grids = {}
    if basis is not None:
        for kind, tag in (('dense', 'fft_grid'), ('smooth', 'fft_smooth')):
            node = require(basis, tag)
            grid = [positive_int(node.get(axis)) for axis in ('nr1', 'nr2', 'nr3')]
            if grid != expected['fft_grid'] or (kind in observed and grid != observed[kind]):
                raise QeSocParseError('Initialization native XML/stdout hard/smooth FFT grid mismatch')
            xml_grids[kind] = grid
    actual_grids = xml_grids or observed
    return {'schema_version': 1, 'code': 'QE', 'calculation': 'initialization_only',
            'execution_status': 'PASS', 'version': '7.5', 'exit_code': process_exit_code,
            'energy': None, 'scf': None, 'kpoints': None,
            'energy_semantics_status': 'NOT_APPLICABLE_INITIALIZATION_ONLY',
            'numerical_solve_status': 'NOT_RUN',
            'initialization_evidence': {'xml_exit_status': 255, 'xml_nstep': 0,
                 'no_numerical_solve_markers': True,
                 'scope': 'setup/pre_init/data_structure/summary/memory_report; not init_run/electrons or eigensolve'},
            'fft_grid': actual_grids.get('dense'), 'fft_smooth_grid': actual_grids.get('smooth'),
            'fft_control_status': 'PASS' if len(actual_grids) == 2 else 'NOT_AVAILABLE',
            'initialization_fft_evidence': {'xml': xml_grids, 'stdout': observed,
                 'note': 'Use explicit native grid fields; an omitted stdout smooth-grid line is not an inferred equality.'},
            'actual_solver': {'namelist': expected['solver'], 'xml': None, 'stdout': None,
                              'execution_status': 'NOT_RUN'},
            'read_start_evidence': {'status': 'NOT_APPLICABLE_INITIALIZATION_ONLY'}}


def parse_qe_soc_diagnostics(xml_path, stdout_path, stderr_path, case, slot, process_exit_code=0):
    """Normalize one prescribed diagnostic slot, retaining native warnings."""
    try:
        expected = _contract(case, slot)
        stdout, stderr = Path(stdout_path).read_text(), Path(stderr_path).read_text()
        warning = native_warnings(stdout, stderr, process_exit_code)
        if warning['fatal_native_lines']:
            raise QeSocParseError('Native fatal diagnostic contradicts a usable completed run')
        if expected['initialization_only']:
            result = _initialization(xml_path, stdout, expected, process_exit_code)
        else:
            result = parse_qe_soc(xml_path, stdout_path, case, process_exit_code, expected['calculation'])
            root = _xml(xml_path)
            control = require(root, 'input/electron_control')
            actual = text(control, 'diagonalization')
            names = {'david': 'davidson', 'cg': 'cg'}
            if actual != names[expected['solver']]:
                raise QeSocParseError('Native XML diagonalization differs from prescribed solver')
            banners = re.findall(r'^\s*(Davidson|CG style) diagonalization(?: with overlap)?\s*$', stdout, re.I | re.M)
            normalized = ['david' if b.lower() == 'davidson' else 'cg' for b in banners]
            if not normalized or any(b != expected['solver'] for b in normalized):
                raise QeSocParseError('Native stdout diagonalization differs from prescribed solver', 'BLOCKED')
            if expected['solver'] == 'cg' and positive_int(text(control, 'diago_cg_maxiter')) != 200:
                raise QeSocParseError('Native CG iteration ceiling is not the prescribed 200')
            if result['fft_grid'] != expected['fft_grid'] or result['fft_smooth_grid'] != expected['fft_grid']:
                raise QeSocParseError('Actual hard/smooth FFT grids differ from prescribed slot')
            for expected_count, index in zip((2777, 2770, 2770), result['requested_to_xml_kpoint_indices']):
                if result['kpoints'][index]['npw'] != expected_count:
                    raise QeSocParseError('Actual spatial plane-wave count differs at requested k coordinate')
            result['read_start_evidence'] = _read_start(stdout, expected['calculation'])
            if expected['calculation'] == 'bands':
                ethr = result['precision']['last_ethr_ry']
                if ethr is None or not math.isclose(ethr, expected['diago_thr_init_ry'], rel_tol=1e-12, abs_tol=0):
                    raise QeSocParseError('Native bands ethr does not report the prescribed threshold')
            result['actual_solver'] = {'namelist': expected['solver'], 'xml': actual,
                                       'stdout': normalized, 'execution_status': 'EXECUTED'}
            result['fft_control_status'] = 'PASS'
            result['numerical_solve_status'] = 'EXECUTED'
        result.update(phase='7B', case=case['case'], slot=slot, input_contract_status='PASS',
                      diagnostic_parameters=expected, grid_expectation=expected['fft_grid'],
                      warning_diagnostics=warning,
                      native_solver_warning_status='UNCONVERGED_WARNING' if warning['eigenvalues_not_converged'] else 'NO_UNCONVERGED_WARNING_REPORTED',
                      fixed_density_binding_status='RUNNER_RECEIPT_REQUIRED' if expected['calculation'] == 'bands' else 'NOT_APPLICABLE',
                      individual_eigenvector_residual_status='NOT_AVAILABLE',
                      diagnostic_format_sources=SOURCES)
        result['algorithm_control_evidence'] = {
            'diago_david_ndim': {'requested': expected.get('diago_david_ndim'),
                                'native_status': 'NOT_EXPOSED_IN_QEXSD',
                                'evidence': 'Exact input whitelist/hash is checked separately by the runner'},
            'diago_cg_maxiter': {'requested': expected.get('diago_cg_maxiter'),
                                'native_status': 'PASS' if expected['solver'] == 'cg' else 'NOT_APPLICABLE'}}
        result['native_files_sha256'] = {name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                                         for name, path in (('xml', xml_path), ('stdout', stdout_path), ('stderr', stderr_path)) if path is not None}
        return result
    except QeSocParseError:
        raise
    except (ET.ParseError, OSError) as error:
        raise QeSocParseError('Missing/truncated diagnostic native output: ' + type(error).__name__, 'BLOCKED') from error
    except (ValueError, KeyError, TypeError, IndexError, ArithmeticError) as error:
        raise QeSocParseError('Malformed diagnostic field: ' + str(error), 'BLOCKED') from error
