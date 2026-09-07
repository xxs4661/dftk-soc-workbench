#!/usr/bin/env python3
"""Explicit scalar evidence export and public-only replay; never launch SCF/QE.

Export reads the accepted Git snapshot. Check needs only current public files
and Python's standard library. Python 3.9 is required for bit-exact historical
RMS reductions; newer built-in sum implementations can change the final bit.
No radial UPF arrays are exported or reconstructed here.
"""
import argparse
import ast
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

from compare_scalar_baseline import compare, finite_tree, volume
from parse_qe_baseline import parse_qe
from analyze_si_sensitivity import (check_independent_reference, check_matrix_case,
                                   common_points, reference_diagnostic, setting_change)
from run_scalar_baseline import check_reference_environment, resolve_reference_result

BASE = '8658992afa936f6cdb1a8055699ae9aa47b32297'
RUNS = {'B0': '20260905T040945688395Z-1cc8a50c',
        'C1': '20260905T074125905466Z-f5d2bbc2',
        'C2': '20260905T074548814292Z-602630a9',
        'C3': '20260905T074856190211Z-bba6ecaf'}
ANALYSIS = 'results/phase4c/20260905T075146761615Z-19093b4b'
BASELINE = 'results/scalar-si-baseline'
SENSITIVITY = 'results/scalar-si-sensitivity'
ENVIRONMENT = 'results/shared/environment.json'
NATIVE = ('qe-data-file-schema.xml', 'qe.stdout', 'dftk.stdout',
          'dftk-result.json', 'qe.in', 'dftk-input.json')
B0_GOLDENS = ('case.json', 'qe-result.json', 'comparison.json', 'result.json',
              'qe.stderr', 'dftk.stderr')
ALGORITHMS = ('scripts/parse_qe_baseline.py', 'scripts/compare_scalar_baseline.py',
              'scripts/inspect_si_reference.py', 'scripts/run_dftk_baseline.jl')
QE_IDENTITY = ('binary_sha256', 'launcher_sha256', 'runner_sha256', 'jll_version',
               'jll_uuid', 'startup_version', 'source_commit')


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    return digest_bytes(path.read_bytes())


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def object_hash(value):
    return digest_bytes(canonical(value))


def read_json(path):
    value = json.loads(path.read_text())
    finite_tree(value)
    return value


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def old_directory(label):
    return 'results/' + ('phase4b' if label == 'B0' else 'phase4c') + '/' + RUNS[label]


def directory(label):
    return (BASELINE if label == 'B0' else SENSITIVITY) + '/' + label


def case_path(label):
    return 'benchmarks/si-sr-lda/' + ('case.json' if label == 'B0' else 'phase4c/' + label + '.json')


def source_bytes(root, path):
    return subprocess.run(['git', 'show', BASE + ':' + path], cwd=root,
                          check=True, capture_output=True).stdout


def source_record(root, path, payload):
    blob = subprocess.run(['git', 'rev-parse', BASE + ':' + path], cwd=root,
                          check=True, capture_output=True, text=True).stdout.strip()
    return {'original_path': path, 'accepted_snapshot_commit': BASE,
            'git_blob': blob, 'sha256': digest_bytes(payload), 'bytes': len(payload)}


def rows_from_csv(payload):
    rows = []
    for row in csv.DictReader(io.StringIO(payload.decode())):
        rows.append({key: ([float(v) for v in ast.literal_eval(value)]
                           if key == 'k_fractional' else
                           int(value) if key == 'band' else float(value))
                     for key, value in row.items()})
    return rows


def csv_bytes(rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def rows_hash(rows):
    # CSV's numeric types are reconstructed explicitly; no rounding or tolerance.
    normalized = [{key: ([float(x) for x in value] if key == 'k_fractional' else
                         int(value) if key == 'band' else float(value))
                   for key, value in row.items()} for row in rows]
    return object_hash(normalized)


def blocks(summary):
    result = list(summary['paired_comparisons'].items())
    result += [(name + '_' + code, block)
               for name, change in summary['within_code_changes'].items()
               for code, block in change.items()]
    return result


def export(root):
    """One explicit accepted-snapshot whitelist; existing historical files untouched."""
    root = Path(root)
    environment = read_json(root / ENVIRONMENT)
    extractor = {'path': 'scripts/curate_scalar_evidence.py',
                 'sha256': digest(root / 'scripts/curate_scalar_evidence.py'),
                 'scope': 'Curation/export identity, not a retroactive execution-code claim'}
    evidence = {}
    for label in RUNS:
        old, new = old_directory(label), directory(label)
        source_names = list(NATIVE) + ['case.json', 'qe-result.json', 'result.json',
                                     'evidence-manifest.json', 'qe.stderr', 'dftk.stderr']
        if label == 'B0':
            source_names += ['comparison.json']
        payloads = {name: source_bytes(root, old + '/' + name) for name in source_names}
        record = json.loads(payloads['result.json'])
        assert record['environment'] == environment, 'Environment must match before deduplication'
        assert payloads['case.json'] == (root / case_path(label)).read_bytes()
        canonical_files = {}
        for name in NATIVE + (B0_GOLDENS if label == 'B0' else ()):
            target = root / new / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payloads[name])
            canonical_files[new + '/' + name] = digest(target)
        canonical_files[case_path(label)] = digest(root / case_path(label))
        if label != 'B0':
            for name in ('qe.stderr', 'dftk.stderr'):
                target = BASELINE + '/B0/' + name
                assert payloads[name] == (root / target).read_bytes()
                canonical_files[target] = digest(root / target)
        # Execution fields are copied, not recomputed. Process-only commands and
        # duplicate identities remain in the archived source record and Git blob.
        fields = ('schema_version', 'run_id', 'execution_status', 'input_comparability_status',
                  'numerical_agreement_status', 'convergence_study_status', 'reasons',
                  'exit_code', 'inputs', 'pseudo', 'thread_settings', 'reference_identity_check')
        retained = {key: record[key] for key in fields if key in record}
        retained['process_exit_codes'] = {entry['stdout']: entry['exit_code']
                                          for entry in record['commands']}
        evidence[label] = {
            'run_id': RUNS[label], 'case_path': case_path(label),
            'historical_record': retained,
            'environment_reference': {'path': ENVIRONMENT, 'sha256': digest(root / ENVIRONMENT),
                                      'equality': 'Entire historical environment object equal'},
            'qe_identity': {key: record['qe_identity'].get(key) for key in QE_IDENTITY},
            'canonical_files': canonical_files,
            'original_sources': [source_record(root, old + '/' + name, payload)
                                 for name, payload in payloads.items()],
            'qe_reparse_canonical_sha256': object_hash(json.loads(payloads['qe-result.json'])),
            'warning_streams': {name: {'path': BASELINE + '/B0/' + name,
                                       'sha256': digest_bytes(payloads[name]),
                                       'occurred_in_this_run': True}
                               for name in ('qe.stderr', 'dftk.stderr')},
            'execution_code_provenance_limit':
                'Original run did not record executed script hashes; accepted snapshot and loaded package/executable identities are retained separately.'}
        if label == 'B0':
            evidence[label]['historical_raw_manifest'] = json.loads(payloads['evidence-manifest.json'])
    build_path = 'results/phase4b/preflight/qe-build-identity.json'
    build_payload = source_bytes(root, build_path)
    baseline = {'schema_version': 1, 'scope': 'Historical scalar Si baseline; SCF NOT_RUN during curation',
                'extractor': extractor, 'case': evidence['B0'],
                'qe_build_identity': json.loads(build_payload),
                'qe_build_identity_source': source_record(root, build_path, build_payload),
                'unchanged_numerical_files': {p: digest_bytes(source_bytes(root, p)) for p in ALGORITHMS}}
    write_json(root / BASELINE / 'evidence.json', baseline)
    reference_path = 'results/phase4c/preflight/reference.json'
    reference = source_bytes(root, reference_path)
    target = root / SENSITIVITY / 'reference.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(reference)
    original_summary = source_bytes(root, ANALYSIS + '/sensitivity.json')
    summary = json.loads(original_summary)
    assert summary.pop('independent_reference') == json.loads(reference)
    tables = {}
    for name, block in blocks(summary):
        original_path = ANALYSIS + '/' + block['eigenvalues_file']
        raw = source_bytes(root, original_path)
        rows = rows_from_csv(raw)
        tables[name] = {'rows': len(rows), 'columns': list(rows[0]),
                        'canonical_rows_sha256': rows_hash(rows),
                        'original_source': source_record(root, original_path, raw)}
    sensitivity = {'schema_version': 1, 'scope': 'Historical finite cutoff/k sensitivity; no new calculations',
                   'extractor': extractor, 'cases': {k: evidence[k] for k in ('C1', 'C2', 'C3')},
                   'historical_summary': summary, 'tables': tables,
                   'summary_source': source_record(root, ANALYSIS + '/sensitivity.json', original_summary),
                   'reference': {'path': SENSITIVITY + '/reference.json', 'sha256': digest(target),
                                 'original_source': source_record(root, reference_path, reference),
                                 'public_reintegration_status': 'NOT_AVAILABLE_WITHOUT_UPF'},
                   'baseline_reference': BASELINE + '/evidence.json'}
    write_json(root / SENSITIVITY / 'evidence.json', sensitivity)
    data = replay(root, baseline, sensitivity)
    (root / BASELINE / 'README.md').write_text(baseline_readme(data))
    (root / SENSITIVITY / 'README.md').write_text(sensitivity_readme(data))
    return check(root)


def replay(root, baseline, sensitivity):
    """Numerical replay uses published native output, never Git/.work/UPF."""
    reference = read_json(root / sensitivity['reference']['path'])
    check_independent_reference(reference, root / case_path('B0'))
    assert reference['C_ha'] == reference['n_atoms'] * reference['alpha_ha_bohr3'] / reference['volume_bohr3']
    assert reference['volume_bohr3'] == volume(read_json(root / case_path('B0'))['geometry']['lattice_vectors_bohr'])
    original = sensitivity['historical_summary']
    assert original['execution_status'] == original['input_comparability_status'] == 'PASS'
    assert original['numerical_agreement_status'] == 'REVIEW_REQUIRED'
    assert original['full_kpoint_convergence_status'] == 'NOT_ESTABLISHED'
    assert original['qe_internal_G0_direct_extraction_status'] == 'NOT_AVAILABLE'
    data, tables, pairs = {}, {}, {}
    reference_record = read_json(root / directory('B0') / 'result.json')
    assert reference_record['environment'] == read_json(root / ENVIRONMENT), 'Immutable B0 fixture/shared environment mismatch'
    for label in RUNS:
        case = read_json(root / case_path(label))
        e = baseline['case'] if label == 'B0' else sensitivity['cases'][label]
        record = e['historical_record']
        assert record['run_id'] == RUNS[label] and record['exit_code'] == 0
        assert record['execution_status'] == record['input_comparability_status'] == 'PASS'
        assert record['numerical_agreement_status'] == 'REVIEW_REQUIRED'
        assert record['process_exit_codes']['qe.stdout'] == record['process_exit_codes']['dftk.stdout'] == 0
        envref = e['environment_reference']
        assert digest(root / envref['path']) == envref['sha256']
        check_reference_environment(read_json(root / envref['path']), e['qe_identity'], reference_record)
        assert e['qe_identity']['startup_version'] == reference_record['qe_identity']['startup_version']
        d = read_json(root / directory(label) / 'dftk-result.json')
        q = parse_qe(root / directory(label) / 'qe-data-file-schema.xml',
                     (root / directory(label) / 'qe.stdout').read_text(), 0,
                     expected_n_kpoints=len(case['kpoints']))
        q['pseudo_sha256'] = case['pseudo']['sha256']
        assert object_hash(q) == e['qe_reparse_canonical_sha256'], label + ' exact QE reparse'
        check_matrix_case(case, read_json(root / case_path('B0')), label)
        for filename, field in [('dftk-input.json', 'dftk_input_sha256'), ('qe.in', 'qe_input_sha256')]:
            assert digest(root / directory(label) / filename) == record['inputs'][field]
        assert digest(root / case_path(label)) == record['inputs']['case_sha256']
        assert d['input_sha256'] == record['inputs']['dftk_input_sha256']
        assert d['case_sha256'] == record['inputs']['case_sha256']
        if label != 'B0':
            assert resolve_reference_result(case['phase4c']['reference_result']).relative_to(Path(__file__).resolve().parents[1]).as_posix() == directory('B0') + '/result.json'
            assert record['reference_identity_check']['reference_result_sha256'] == digest(root / directory('B0') / 'result.json')
        pair = compare(case, d, q)
        if label == 'B0':
            assert q == read_json(root / directory(label) / 'qe-result.json')
            assert pair == read_json(root / directory(label) / 'comparison.json')
        paired = reference_diagnostic(pair, reference['C_ha'])
        tables[label] = paired.pop('eigenvalues')
        paired['eigenvalues_file'] = label + '.csv'
        assert paired == original['paired_comparisons'][label], label + ' full summary'
        pairs[label] = paired
        data[label] = case, d, q
        metadata = original['runs'][label]
        assert metadata['inputs'] == record['inputs'] and metadata['run_id'] == RUNS[label]
        assert metadata['PspCorrection_ha'] == d['energy_components_ha']['PspCorrection']
        assert metadata['C_DFTK_ha'] == metadata['PspCorrection_ha'] / d['n_electrons']
        assert metadata['C_independent_minus_DFTK_ha'] == reference['C_ha'] - metadata['C_DFTK_ha']
        assert metadata['ecut_ha'] == case['cutoffs']['dftk_ecut_ha']
        assert metadata['n_kpoints'] == len(case['kpoints'])
        assert metadata['fft_grid'] == {'DFTK': d['fft_grid'], 'QE': q['fft_grid'], 'QE_smooth': q['fft_smooth_grid']}
        assert metadata['npw'] == {code: [p['npw'] for p in common_points(case['kpoints'], result['kpoints'])]
                                   for code, result in [('DFTK', d), ('QE', q)]}
        assert metadata['scf_iterations'] == {'DFTK': d['scf']['iterations'], 'QE': q['scf']['iterations']}
        assert metadata['density_residual_DFTK'] == d['scf']['density_residual_history'][-1]
        assert metadata['scf_error_QE_ha'] == q['scf']['error_ha']
        assert metadata['diagonalization_QE_threshold_ry'] == q['scf']['diagonalization_threshold_last_ry']
        assert metadata['DFTK_solver_residual_max_ha'] == max(max(row[:8]) for row in d['diagonalization']['residuals_ha'])
        assert metadata['DFTK_explicit_residual_max_ha'] == d['diagonalization'].get('explicit_recomputed_residual_max_ha')
    changes = {}
    for before, after in [('B0', 'C1'), ('C1', 'C2'), ('C2', 'C3')]:
        name = before + '_to_' + after
        changes[name] = {}
        for code, index in [('DFTK', 1), ('QE', 2)]:
            block = setting_change(data[before][0], data[before][index],
                                   data[after][0], data[after][index], code)
            tables[name + '_' + code] = block.pop('eigenvalues')
            block['eigenvalues_file'] = name + '_' + code + '.csv'
            assert block == original['within_code_changes'][name][code], name + '/' + code
            changes[name][code] = block
    for name, rows in tables.items():
        expected = sensitivity['tables'][name]
        assert len(rows) == expected['rows'] and list(rows[0]) == expected['columns']
        assert rows_hash(rows) == expected['canonical_rows_sha256'], name + ' exact rows'
        assert digest_bytes(csv_bytes(rows)) == expected['original_source']['sha256'], name + ' original CSV bytes'
    assert len(tables) == 10 and sum(map(len, tables.values())) == 1088
    return {'data': data, 'pairs': pairs, 'changes': changes, 'reference': reference, 'tables': tables}


def baseline_readme(data):
    b = data['pairs']['B0']
    energies = b['total_energy']
    levels = b['eigenvalue_summary']['all']
    return f'''# Si scalar baseline: B0

Historical execution and input comparability: PASS. Numerical agreement:
REVIEW_REQUIRED. This scalar evidence curation reruns no SCF or QE.

| Native quantity | DFTK | QE |
| --- | ---: | ---: |
| Total energy (Ha/cell) | {energies['DFTK']['ha_cell']:.15g} | {energies['QE']['ha_cell']:.15g} |

Raw maximum spectral difference: {levels['raw']['max_abs_ev']:.15g} eV.
With one sampled global HOMO reference per program, maximum difference:
{levels['global_reference']['max_abs_ev']:.15g} eV. No per-k shift or total-energy
correction is applied. The raw offset is retained and is not wholly attributed
to a gauge by this comparison.

[B0 native/normalized evidence](B0/result.json), [QE XML](B0/qe-data-file-schema.xml),
[QE stdout](B0/qe.stdout), [QE warnings](B0/qe.stderr), [DFTK stdout](B0/dftk.stdout),
[DFTK result](B0/dftk-result.json), [raw and referenced levels](B0/comparison.json)
and [provenance](evidence.json) support offline review. The original B0 result,
parsed QE result, comparison and case bytes remain golden regression fixtures.
The [shared environment](../shared/environment.json) is authoritative. The embedded
B0 environment is preserved only as part of the immutable golden fixture; its
entire object must equal the shared identity during every public check.
One copy of each repeated warning stream is referenced by its actual occurrences.

Use Python 3.9 for exact historical floating-point reductions:

```sh
PYTHONDONTWRITEBYTECODE=1 python3.9 scripts/curate_scalar_evidence.py --check
```

The [frozen input](../../benchmarks/si-sr-lda/case.json) retains eight scalar bands,
eight electrons, LDA/PW92 and NLCC. [Physical reproduction instructions](../../benchmarks/si-sr-lda/README.md)
require the hash-checked Si UPF and frozen runtime. No UPF or cache is published.
See [finite sensitivities](../scalar-si-sensitivity/README.md) before interpreting
this smoke baseline as convergence.

DFTK's historical solver-history zeros do not establish zero physical residuals;
independent B0 orbital-residual recomputation is NOT_RUN. QE per-band residual
norms are not available. QE stderr reports IEEE floating-point exception flags;
these remain visible despite normal exit and final convergence. The binary's
source commit is NOT_CONFIRMED. Package and binary identities are preserved in
[evidence.json](evidence.json) and the immutable B0 record.

The [historical Phase 4B report](https://github.com/xxs4661/dftk-soc-workbench/blob/{BASE}/results/phase4b-review.md)
retains the two failed attempts: a parser tag mismatch after converged QE and a
DFTK metadata accessor failure before SCF. Neither is recast as new calculation
success or physical nonconvergence.
'''


def sensitivity_readme(data):
    ref = data['reference']
    rows = []
    for name, changes in data['changes'].items():
        rows.append('| ' + name.replace('_to_', ' → ') + ' | ' + ' | '.join(
            f"{changes[code]['total_energy']['delta_mev_atom']:.15g}" for code in ('DFTK', 'QE')) + ' |')
    k = data['changes']['C2_to_C3']
    return f'''# Si finite cutoff and k-point sensitivity

Historical B0/C1/C2/C3 execution and input comparability: PASS. Numerical
agreement: REVIEW_REQUIRED. Full k-point convergence: NOT_ESTABLISHED.
The frozen sequence is 30/40/50 Ha at eight explicit points, then 50 Ha at
64 points. Geometry, pseudopotential, XC, occupations and tolerances are fixed.

| Change | DFTK ΔE (meV/atom) | QE ΔE (meV/atom) |
| --- | ---: | ---: |
{chr(10).join(rows)}

The 8→64-point change is large. On the original eight common points, maximum
Gamma-HOMO-referenced spectral changes are
{k['DFTK']['gamma_reference_summary']['all']['max_abs_ev']:.15g} eV (DFTK) and
{k['QE']['gamma_reference_summary']['all']['max_abs_ev']:.15g} eV (QE).
These observations cannot establish a converged gap or dense-grid baseline.

The independent input-based prediction is C = {ref['C_ha']:.17g} Ha, from
alpha = {ref['alpha_ha_bohr3']:.17g} Ha·bohr³ and C = 2 alpha / volume.
The published [reference](reference.json) retains grid, units, trapezoid and
coarsening diagnostics, and its nonzero finite tail. The quadratic/trapezoid
C difference is {ref['quadrature']['quadratic_minus_trapezoid_C_ha']:.17g} Ha;
it is a method sensitivity, not a rigorous bound. Integration stops at the
last actual radial grid point. The unintegrated tail is not fitted away.
The predicted spectrum difference is −C; the tables preserve raw differences,
one global HOMO reference per program and the independent delta+C diagnostic.
No spectral fit supplies C and no total-energy correction is added.

Public-only reintegration is NOT_AVAILABLE_WITHOUT_UPF. The reference factors,
all pair comparisons and all ten tables (1088 rows) are independently recomputed
from public native XML/JSON, without fetching a pseudopotential or running QE:

```sh
PYTHONDONTWRITEBYTECODE=1 python3.9 scripts/curate_scalar_evidence.py --check
PYTHONDONTWRITEBYTECODE=1 python3.9 scripts/curate_scalar_evidence.py --tables .work/new-scalar-tables
```

[Evidence](evidence.json) contains exact historical summaries and row fingerprints;
rows regenerate from native results, not from hashes. Native records:
[C1 XML](C1/qe-data-file-schema.xml), [C1 QE stdout](C1/qe.stdout), [C1 DFTK](C1/dftk-result.json);
[C2 XML](C2/qe-data-file-schema.xml), [C2 QE stdout](C2/qe.stdout), [C2 DFTK](C2/dftk-result.json);
[C3 XML](C3/qe-data-file-schema.xml), [C3 QE stdout](C3/qe.stdout), [C3 DFTK](C3/dftk-result.json).
[Repeated QE warnings](../scalar-si-baseline/B0/qe.stderr) occurred in all four runs.
C3 stdout also retains the “eigenvalues threshold was too large” diagnostic
before tighter final diagonalization. DFTK residual histories and explicit final
residuals are retained separately; B0 has no independent residual recomputation.

See the [frozen cases and reference conventions](../../benchmarks/si-sr-lda/phase4c/README.md)
and [historical Phase 4C report](https://github.com/xxs4661/dftk-soc-workbench/blob/{BASE}/results/phase4c-review.md).
C is a corresponding-source convention prediction, not a numeric extraction of
the installed QE binary's internal G=0 coefficient. The binary source commit
remains unconfirmed. This curation performs no SCF and establishes no SOC result.
'''


def check(root):
    root = Path(root)
    if sys.version_info[:2] != (3, 9):
        raise ValueError('Exact historical scalar replay requires Python 3.9; no tolerance is substituted')
    baseline = read_json(root / BASELINE / 'evidence.json')
    sensitivity = read_json(root / SENSITIVITY / 'evidence.json')
    for record in (baseline, sensitivity):
        assert digest(root / record['extractor']['path']) == record['extractor']['sha256']
    for evidence in [baseline['case']] + list(sensitivity['cases'].values()):
        for path, sha in evidence['canonical_files'].items():
            assert digest(root / path) == sha, path
    for path, sha in baseline['unchanged_numerical_files'].items():
        assert digest(root / path) == sha, path
    assert digest(root / sensitivity['reference']['path']) == sensitivity['reference']['sha256']
    data = replay(root, baseline, sensitivity)
    assert (root / BASELINE / 'README.md').read_text() == baseline_readme(data), 'Baseline README/data mismatch'
    assert (root / SENSITIVITY / 'README.md').read_text() == sensitivity_readme(data), 'Sensitivity README/data mismatch'
    # Immutable B0 public bytes remain tied to their original raw/public manifest.
    b0 = baseline['case']
    for item in b0['historical_raw_manifest']['files']:
        path = root / directory('B0') / item['file']
        if str(path.relative_to(root)) in b0['canonical_files']:
            assert digest(path) == item['published_sha256']
    return {'status': 'PASS', 'scope': 'Public-only historical replay; SCF/QE NOT_RUN',
            'runs_reparsed': list(RUNS), 'exact_tables': len(data['tables']),
            'exact_rows': sum(map(len, data['tables'].values())),
            'readme_data_checks': 'PASS', 'numerical_agreement_status': 'REVIEW_REQUIRED',
            'full_kpoint_convergence_status': 'NOT_ESTABLISHED',
            'reference_reintegration_status': 'NOT_AVAILABLE_WITHOUT_UPF',
            'historical_reduction_python': '.'.join(map(str, sys.version_info[:3]))}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--export', action='store_true', help='Export the explicit accepted-snapshot whitelist')
    group.add_argument('--check', action='store_true', help='Replay only the current public evidence')
    group.add_argument('--tables', type=Path, help='Replay and write all ten CSV tables to a NEW directory')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if sys.version_info[:2] != (3, 9):
        raise ValueError('Use Python 3.9 for exact historical scalar replay')
    result = export(root) if args.export else check(root)
    if args.tables:
        data = replay(root, read_json(root / BASELINE / 'evidence.json'),
                      read_json(root / SENSITIVITY / 'evidence.json'))
        args.tables.mkdir(parents=True, exist_ok=False)
        for name, rows in data['tables'].items():
            (args.tables / (name + '.csv')).write_bytes(csv_bytes(rows))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
