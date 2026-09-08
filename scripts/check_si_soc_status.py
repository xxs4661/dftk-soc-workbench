#!/usr/bin/env python3
"""Si status semantics v2 over the byte-authenticated Phase 8A snapshot.

Default exit 0 certifies faithful replay and status derivation, not scientific
acceptance. Strict exit 1 means measured manifold prerequisites need review;
exit 2 is an input/contract/replay error. No numerical solver is called.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from check_si_soc import close, digest
from check_publication import check_paths, public_files
from si_soc_comparison import compare_spectra, number

ROOT = Path(__file__).resolve().parents[1]
BASE = '61cb1c226dcfa8dbeccc63e8f43e33b2790a07c6'
CASE = 'benchmarks/si-soc-splitting-v1'
OUT = 'results/si-soc-splitting'
SELF = 'scripts/check_si_soc_status.py'
NAV = {'README.md', 'docs/status.md', 'results/README.md', 'scripts/README.md',
       CASE + '/README.md', OUT + '/README.md'}
NEW = {SELF, 'tests/test_si_soc_status.py', OUT + '/status-correction/README.md',
       OUT + '/status-correction/assessment.json'}


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.PIPE)


def read(path):
    def invalid(value):
        raise ValueError('Nonfinite JSON token: ' + value)
    return json.loads(path.read_text(), parse_constant=invalid)


def authenticate(root, *, historical):
    """Compare every original file with its Git blob; only named current docs vary.

    No scientific-file exemptions, private paths or floating byte tolerances.
    The old snapshot must be detached, exact and clean, including ignored files.
    """
    if historical:
        if git(root, 'rev-parse', 'HEAD').decode().strip() != BASE:
            raise ValueError('Source HEAD is not the fixed historical commit')
        if git(root, 'rev-parse', '--abbrev-ref', 'HEAD').decode().strip() != 'HEAD':
            raise ValueError('Source snapshot must be detached')
        if git(root, 'status', '--porcelain', '--untracked-files=all', '--ignored'):
            raise ValueError('Source snapshot is not clean/public-only')
    entries = git(root, 'ls-tree', '-rz', BASE).split(b'\0')
    names = set()
    for entry in filter(None, entries):
        meta, raw = entry.split(b'\t'); mode, kind, blob = meta.split()
        path = raw.decode(); names.add(path)
        file = root / path
        if file.is_symlink() or not file.resolve().is_relative_to(root.resolve()):
            raise ValueError('Unconfined source path: ' + path)
        if not historical and path in NAV:
            continue
        if mode not in (b'100644', b'100755') or kind != b'blob' or file.is_symlink():
            raise ValueError('Unsupported source file type: ' + path)
        data = file.read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if actual != blob.decode():
            raise ValueError('Frozen byte mismatch: ' + path)
    paths = set(public_files(root))
    if paths - names - (set() if historical else NEW):
        raise ValueError('Unapproved new public files')
    for path in paths:
        if (root / path).is_symlink() or not (root / path).resolve().is_relative_to(root.resolve()):
            raise ValueError('Unconfined public path: ' + path)
    check_paths(root, paths)
    return len(names)


def validate_plan(plan):
    # These equalities certify compatibility with the frozen comparator's scope;
    # the actual threshold and indices below are read from this verified plan.
    g = plan['grouping']
    for key in ('lower_doublet_one_based', 'upper_quartet_one_based', 'isolation_neighbors_one_based'):
        if not isinstance(g[key], list) or any(type(i) is not int for i in g[key]):
            raise ValueError('State indices must be exact integers')
    if type(g['occupation_near_full_min']) is not float:
        raise ValueError('Occupation threshold must retain its original float type')
    if (g['lower_doublet_one_based'], g['upper_quartet_one_based'],
        g['isolation_neighbors_one_based'], g['occupation_near_full_min']) != (
            [3, 4], [5, 6, 7, 8], [2, 9], .99999999):
        raise ValueError('Unauthorized grouping/occupation contract change')
    gates = {'manifold_isolation_ev': .02, 'manifold_doublet_width_ev': 1e-5,
             'manifold_quartet_width_ev': 1e-5, 'split_min_ev': .005,
             'null_six_width_ev': 1e-5, 'full_to_null_width_min_ratio': 100,
             'split_D_minus_Q_abs_ev': 1e-4, 'kramers_and_pm_ha': 1e-7}
    if any(type(plan['gates'][k]) not in (int, float) or plan['gates'][k] != v for k, v in gates.items()):
        raise ValueError('Unsupported frozen spectral gate change')
    return g


def status(value, allowed=('PASS', 'MISMATCH')):
    if not isinstance(value, str) or value not in allowed:
        raise ValueError('Missing or invalid required measured status')
    return value


def derive_status(fresh, plan):
    """Aggregate existing measurements; never suppress finite-window statistics.

    Prerequisites include both structures and FD occupations, resolvable matched
    splitting, the dedicated null control, D residual/Gram, D/Q spectral TR and
    Q's reported solver gate. Missing evidence is an error, not benign review.
    All measured prerequisites passing still certifies neither irreps nor
    continuous band assignment nor physical convergence.
    """
    grouping = validate_plan(plan)
    indices = grouping['lower_doublet_one_based'] + grouping['upper_quartet_one_based']
    threshold = number(grouping['occupation_near_full_min'])
    minima, structures = {}, []
    for label in ('D', 'Q'):
        gamma = fresh[label + '_gamma']
        isolation = status(gamma['manifold_assignment_status'], ('PASS', 'MANIFOLD_ASSIGNMENT_REVIEW_REQUIRED'))
        width = status(gamma['multiplet_structure_status'])
        structures.append(isolation == width == 'PASS')
        values = fresh['gamma_fd_occupations_at_existing_scf_mu'][label]
        if not isinstance(values, list) or len(values) != 24:
            raise ValueError('Expected complete 24-state FD diagnostic')
        if any(not 0 <= number(f) <= 1 for f in values):
            raise ValueError('Invalid capacity-one FD value')
        minima[label] = min(values[i-1] for i in indices)
    occupied = all(f >= threshold for f in minima.values())  # Exact >=; no margin.
    split = status(fresh['splitting_comparison_status'])
    control = status(fresh['spin_trace_control_status'])  # Not null resolvable_soc.
    extra = {label + '_spectral_TR': status(fresh['time_reversal'][label]['status']) for label in ('D', 'Q')}
    extra.update({label + '_precision': status(fresh['D_precision'][label]['status']) for label in ('D_full', 'D_null')})
    qsolver = status(fresh['Q_eigensolver_status'], ('REPORTED_THRESHOLD_AVAILABLE', 'EIGENSOLVER_REVIEW_REQUIRED'))
    prerequisites = {'fixed_window_structure': all(structures), 'D_occupation': minima['D'] >= threshold,
                     'Q_occupation': minima['Q'] >= threshold, 'splitting_comparison': split == 'PASS',
                     'spin_trace_control': control == 'PASS',
                     **{k: v == 'PASS' for k, v in extra.items()},
                     'Q_reported_solver': qsolver == 'REPORTED_THRESHOLD_AVAILABLE'}
    passed = all(prerequisites.values())
    return {
        'semantics_version': 2,
        'fixed_window_structure_status': 'PASS' if all(structures) else 'MISMATCH',
        'fixed_window_splitting_comparison_status': split,
        'spin_trace_control_status': control,
        'gamma_occupation_diagnostic_status': 'PASS' if occupied else 'REVIEW_REQUIRED',
        'manifold_prerequisites_status': 'PASS' if passed else 'REVIEW_REQUIRED',
        'manifold_assignment_status': 'MEASURED_PREREQUISITES_PASS' if passed else 'MANIFOLD_ASSIGNMENT_REVIEW_REQUIRED',
        'physical_manifold_interpretation': 'REVIEW_REQUIRED',
        'unmet_measured_prerequisites': [k for k, v in prerequisites.items() if not v],
        'occupation_rule': {'plan': CASE + '/plan.json', 'indices_one_based': indices,
                            'minimum_inclusive': threshold, 'minimum_FD': minima,
                            'scope': 'FD function at each existing SCF global mu; no mu solve'},
        'key_numbers': {**{label + '_delta_so_ev': number(fresh[label + '_gamma']['delta_so_ev']) for label in ('D', 'Q')},
                        'D_minus_Q_delta_so_ev': number(fresh['delta_so_D_minus_Q_ev']),
                        'null_six_width_ev': number(fresh['D_null_gamma']['six_state_width_ev'])},
        'legacy': {'manifold_assignment_status': fresh['manifold_assignment_status'],
                   'definition': 'Historical v1 aggregate: window isolation and group widths only; excludes occupation'},
        'limits': {**{k: fresh[k] for k in ('numerical_review_status', 'physical_convergence',
                    'band_crossing_between_sampled_probes', 'native_QE_NL_independent', 'noncollinear_magnetic_XC')},
                   'space_group_irrep_assignment': fresh['D_gamma']['space_group_irrep_assignment'],
                   'warning_evidence': OUT + '/comparison.json#Q_warnings',
                   'array_measurements': 'Original RUNNER_REPORTED scope unchanged'}
    }


def evaluate(d, q, null, case, plan):
    for receipt in (d, q, null):
        for key, expected in (('schema_version', 1), ('n_electrons', 8), ('n_bands', 24), ('occupation_capacity', 1)):
            if type(receipt[key]) is not int or receipt[key] != expected:
                raise ValueError('Invalid exact receipt count/version: ' + key)
    if type(q['warning_evidence']['eigenvalues_not_converged']) is not bool:
        raise ValueError('Missing or invalid QE eigenvalue-warning evidence')
    fresh = compare_spectra(d, q, null, case)  # Includes unchanged FD function.
    return derive_status(fresh, plan), fresh


def exact_discrete(a, b):
    """The old close governs floats; new status/count/index types stay exact."""
    if isinstance(a, dict):
        for key in a:
            exact_discrete(a[key], b[key])
    elif isinstance(a, list):
        for x, y in zip(a, b):
            exact_discrete(x, y)
    elif type(a) is int and a != b:
        raise ValueError('Assessment integer/count/index mismatch')
    elif type(a) is not type(b):
        raise ValueError('Assessment discrete/numeric type mismatch')


def run(source, require_manifold=False, record=None):
    authenticate(ROOT, historical=False)
    if git(ROOT, 'show', 'HEAD:' + SELF) != (ROOT / SELF).read_bytes():
        raise ValueError('Semantic source must be committed before formal execution')
    count = authenticate(source, historical=True)
    process = subprocess.run([sys.executable, '-B', 'scripts/check_si_soc.py'], cwd=source,
                             env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, capture_output=True, text=True)
    historical = {'exit_code': process.returncode, 'stdout': process.stdout, 'stderr': process.stderr}
    if process.returncode != 0:
        return {'semantics_version': 2, 'semantic_validation_status': 'FAIL',
                'historical_replay_status': 'FAIL', 'historical_process': historical,
                'reason': 'Original checker failed; its exit and streams are preserved', 'exit_code': 2}, 2
    if json.loads(process.stdout)['offline_status'] != 'PASS':
        raise ValueError('Historical checker success protocol mismatch')
    directory = source / OUT
    evidence = read(directory / 'evidence.json')
    case = read(source / CASE / 'case.json'); case['binding'] = evidence['bindings']
    d, q, null = [read(directory / (name + '.json')) for name in ('D-spectrum', 'Q-spectrum', 'D-null')]
    ds, qs = read(directory / 'D-SCF.json'), read(directory / 'Q-SCF/qe-result.json')
    for label, spectrum, parent, mu, density in (
        ('D', d, ds, ds['final']['mu_ha'], ds['final']['n_out_sha256']),
        ('Q', q, qs, qs['fermi_energy_ha'], qs['density_source_sha256'])):
        if (number(spectrum['fermi_energy_ha']) != number(mu) or
            parent['run_id'] != case['binding'][label]['scf_run_id'] or
            density != case['binding'][label]['density_sha256']):
            raise ValueError('Spectrum mu/SCF/density provenance mismatch: ' + label)
    result, fresh = evaluate(d, q, null, case, read(source / CASE / 'plan.json'))
    close(fresh, read(directory / 'comparison.json'))  # Original full numeric/status contract.
    sources = [CASE + '/' + name + '.json' for name in ('plan', 'case', 'source', 'replay-contract')]
    sources += [OUT + '/' + name + '.json' for name in ('evidence', 'comparison', 'energy', 'D-spectrum', 'Q-spectrum', 'D-null', 'D-SCF')]
    sources += [OUT + '/Q-SCF/qe-result.json']
    result.update(historical_input_commit=BASE, historical_physical_execution_commit=evidence['execution_commit'],
                  semantic_execution_commit=git(ROOT, 'rev-parse', 'HEAD').decode().strip(),
                  semantic_code_sha256=digest(ROOT / SELF),
                  source_sha256={p: digest(source / p) for p in sources},
                  current_navigation_sha256={p: digest(ROOT / p) for p in sorted(NAV)},
                  historical_files_authenticated=count, historical_replay_status='PASS',
                  historical_process=historical, semantic_validation_status='PASS')
    rules = OUT + '/status-correction/README.md'
    result['semantic_rules_sha256'] = hashlib.sha256(git(ROOT, 'show', result['semantic_execution_commit'] + ':' + rules)).hexdigest()
    if record is not None:
        saved = read(record)['assessment']
        old_code = git(ROOT, 'show', saved['semantic_execution_commit'] + ':' + SELF)
        if hashlib.sha256(old_code).hexdigest() != result['semantic_code_sha256']:
            raise ValueError('Recorded semantic execution code mismatch')
        result['semantic_execution_commit'] = saved['semantic_execution_commit']
        result['semantic_rules_sha256'] = hashlib.sha256(git(ROOT, 'show', saved['semantic_execution_commit'] + ':' + rules)).hexdigest()
        if saved['occupation_rule']['minimum_inclusive'] != result['occupation_rule']['minimum_inclusive']:
            raise ValueError('Recorded occupation threshold changed')
        close(result, saved)
        exact_discrete(result, saved)
    code = 1 if require_manifold and result['manifold_prerequisites_status'] != 'PASS' else 0
    return dict(result, mode='require-manifold-pass' if require_manifold else 'validate-semantics', exit_code=code), code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--require-manifold-pass', action='store_true')
    parser.add_argument('--check-record', type=Path, help='Replay compact assessment against its recorded semantic code')
    args = parser.parse_args(argv)
    try:
        result, code = run(args.source_root.resolve(), args.require_manifold_pass, args.check_record)
    except Exception as error:
        result, code = {'semantics_version': 2, 'semantic_validation_status': 'FAIL',
                        'reason': str(error), 'error_type': type(error).__name__, 'exit_code': 2}, 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return code


if __name__ == '__main__':
    sys.exit(main())
