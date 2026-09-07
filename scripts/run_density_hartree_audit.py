#!/usr/bin/env python3
"""Read only historical A/B densities, then original G40 charge. Never run QE.

Local output contains full in/out coefficients. Public publication is a separate
explicit whitelist. The archived manifest must be supplied, never discovered by
searching personal directories. Each invocation requires a NEW output directory.
"""
import argparse
import csv
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PLAN = 'benchmarks/mg-soc-density-hartree-v1/plan.json'
CODE = ('scripts/run_density_hartree_audit.py', 'scripts/extract_soc_density.jl',
        'scripts/parse_qe_charge_density.py', 'scripts/compare_density_hartree.py')


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def write_json(path, data):
    payload = json.dumps(data, indent=2, allow_nan=False) + '\n'
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(payload)
    temporary.replace(path)


def checked_file(path, spec):
    require(path.is_file(), 'Missing bound source: ' + str(path))
    require(path.stat().st_size == spec['bytes'] and digest(path) == spec['sha256'],
            'Source bytes differ from historical binding: ' + str(path))
    return {'path': str(path), 'bytes': spec['bytes'], 'sha256': spec['sha256']}


def validate_dftk_receipt(label, spec, raw, endpoint):
    require(raw['run_id'] == spec['run_id'] and raw['label'] == label,
            'Wrong DFTK run ID/label')
    require(raw['checkpoint_sha256'] == spec['checkpoint']['sha256'], 'Wrong checkpoint identity')
    require(raw['execution_status'] == 'PASS' and raw['exit_code'] == 0, 'Historical SCF did not pass')
    for key in ('n_in_sha256', 'n_out_sha256', 'map_count', 'unmixed_residual_l2'):
        require(raw['final'][key] == endpoint[key], 'Endpoint state differs: ' + key)
    require(endpoint['n_out_sha256'] == endpoint['diagnostics']['orbital_density_sha256'] and
            endpoint['n_in_sha256'] == endpoint['diagnostics']['consumed_input_sha256'],
            'Input/output density state swap')


def bind_dftk(root, plan, label):
    spec = plan['sources'][label]
    evidence = load(root / spec['historical_evidence_path'])
    require(evidence['runs'][label]['run_id'] == spec['run_id'] and
            evidence['runs'][label]['checkpoint_sha256'] == spec['checkpoint']['sha256'],
            'DFTK source is not the historical run')
    files = {key: checked_file(root / spec[key]['path'], spec[key])
             for key in ('checkpoint', 'receipt', 'maps')}
    require(digest(root / spec['endpoint']['path']) == spec['endpoint']['sha256'], 'Endpoint hash changed')
    validate_dftk_receipt(label, spec, load(root / spec['receipt']['path']), load(root / spec['endpoint']['path']))
    return {'status': 'PASS', 'run_id': spec['run_id'], 'files': files}


def bind_qe(root, plan, manifest_path, raw_root):
    spec = plan['sources']['G40']
    historical = load(root / spec['manifest_evidence_path'])
    require(digest(manifest_path) == spec['manifest_sha256'] == historical['raw_backup']['manifest_sha256'],
            'Wrong historical G40 archive manifest')
    entries = {x['path']: x for x in load(manifest_path)['files']}
    files = {}
    for suffix, expected in spec['files'].items():
        require(expected['path'] == spec['run_id'] + '/' + suffix and entries.get(expected['path']) == expected,
                'G40 path is not from the bound original SCF manifest')
        files[suffix] = checked_file(raw_root / expected['path'], expected)
    raw = load(Path(files['result.json']['path']))
    require(raw['run_id'] == spec['run_id'] and raw['slot'] == 'G40' and
            raw['execution_status'] == 'PASS' and raw['process_exit_code'] == 0,
            'Wrong or failed G40 SCF receipt')
    process = load(Path(files['process-exit.json']['path']))
    require(process['exit_code'] == 0 and process['interrupted'] is False, 'G40 was interrupted')
    snapshots = load(Path(files['save-snapshot.json']['path']))
    for name in ('charge-density.dat', 'data-file-schema.xml'):
        sha = files['scratch/mg_soc_qe_v1.save/' + name]['sha256']
        require(snapshots[name] == sha == historical['source_snapshots']['G40']['save_sha256'][name],
                'Saved G40 file differs from original SCF snapshot')
    return {'status': 'PASS', 'run_id': spec['run_id'], 'files': files}


def read_native_csv(path, label):
    datasets = {label + '_in': {}, label + '_out': {}}
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == ['m1', 'm2', 'm3', 'n_in_real', 'n_in_imag', 'n_out_real', 'n_out_imag'],
                'Unknown Julia coefficient layout')
        for row in reader:
            m = tuple(int(row[k]) for k in ('m1', 'm2', 'm3'))
            for state in ('in', 'out'):
                values = datasets[label + '_' + state]
                require(m not in values, 'Duplicate Julia native mode')
                z = complex(float(row['n_' + state + '_real']), float(row['n_' + state + '_imag']))
                require(math.isfinite(z.real) and math.isfinite(z.imag), 'Nonfinite Julia coefficient')
                values[m] = z
    return datasets


def read_bound_native_csv(path, label, metadata, grid):
    expected = metadata['coefficients']
    require(digest(path) == expected['sha256'] and expected['row_count'] == math.prod(grid),
            'Julia CSV differs from the executed extractor receipt')
    datasets = read_native_csv(path, label)
    require(all(len(c) == expected['row_count'] for c in datasets.values()), 'Incomplete Julia native CSV')
    return datasets


def validate_qe_xml(path, plan):
    root = ET.parse(path).getroot()
    for element in root.iter():
        element.tag = element.tag.split('}')[-1]
    out = root.find('output')
    require(out is not None, 'Missing original SCF XML output')
    require(root.findtext('input/control_variables/calculation') == 'scf' and
            root.findtext('exit_status') == '0' and
            out.findtext('convergence_info/scf_conv/convergence_achieved') == 'true',
            'XML is not a successful converged original SCF')
    for key, expected in [('noncolin', 'true'), ('spinorbit', 'true'), ('do_magnetization', 'false')]:
        require(out.findtext('magnetization/' + key) == expected, 'Wrong G40 ' + key)
    require(int(out.findtext('basis_set/ngm')) == plan['sources']['G40']['expected_ngm'], 'Wrong density ngm')
    require(out.findtext('basis_set/gamma_only') == 'false' and
            float(out.findtext('basis_set/ecutwfc')) == 15.0 and
            float(out.findtext('basis_set/ecutrho')) == plan['sources']['G40']['density_cutoff_ha'],
            'Wrong G40 full-G/cutoff convention')
    grid = out.find('basis_set/fft_grid')
    require([int(grid.attrib[k]) for k in ('nr1', 'nr2', 'nr3')] == plan['fft_size'], 'Wrong G40 FFT')
    smooth = out.find('basis_set/fft_smooth')
    require([int(smooth.attrib[k]) for k in ('nr1', 'nr2', 'nr3')] == plan['fft_size'], 'Wrong G40 smooth FFT')
    lattice = [[float(x) for x in out.findtext('atomic_structure/cell/a' + str(i)).split()] for i in (1, 2, 3)]
    require(max(abs(x-y) for a,b in zip(lattice,plan['lattice_vectors_bohr']) for x,y in zip(a,b)) <=
            plan['thresholds']['direct_lattice_abs_bohr'], 'G40 lattice mismatch')
    return {'lattice_vectors_bohr': lattice, 'hartree_ha': float(out.findtext('total_energy/ehart')),
            'density_state': 'Converged unmixed output rho; tagged QE7.5 v_of_rho then write_scf',
            'state_evidence_level': 'TAGGED_SOURCE_CALL_CHAIN_AND_BOUND_SUCCESSFUL_NATIVE_RECEIPTS',
            'exact_installed_qe_source_commit': None}


def validate_reciprocal_columns(columns, plan):
    require(isinstance(columns, (list, tuple)) and len(columns) == 3 and
            all(len(c) == 3 and all(math.isfinite(x) for x in c) for c in columns), 'Invalid reciprocal basis')
    direct = plan['lattice_vectors_bohr']
    error = max(abs(math.fsum(x*y for x,y in zip(direct[i], columns[j])) / (2*math.pi) - (i == j))
                for i in range(3) for j in range(3))
    require(error <= plan['thresholds']['reciprocal_duality_abs'], 'A^T B/(2pi) differs: units/basis not comparable')
    return error


def store_qe_coefficients(directory, parsed, datasets, writer):
    candidate = dict(zip(parsed['miller'], parsed['rho_g']))
    writer(directory / 'qe-native.csv.gz', {'QE': candidate})
    # The completion set must not include QE until its required file exists.
    datasets['QE'] = candidate
    del parsed['miller'], parsed['rho_g']


def save_completion(directory, record, summary_builder=None):
    """Build and persist auxiliary output before publishing the success authority."""
    try:
        require(isinstance(record, dict) and isinstance(record.get('sources'), dict), 'Malformed completion')
        payload = json.dumps(record, indent=2, allow_nan=False) + '\n'
        summary = (summary_builder or (lambda r: 'Array audit: ' + r['execution_status'] + '\n'))(record)
        require(isinstance(summary, str), 'Invalid summary')
        (directory / 'summary.md').write_text(summary)
        write_json(directory / 'result.json', json.loads(payload))
    except BaseException as error:
        safe = {'schema_version': 1, 'execution_status': 'FAIL', 'exit_code': 9,
                'sources': {}, 'reason': 'Output publication failed: ' + type(error).__name__}
        try:
            write_json(directory / 'result.json', safe)
        except BaseException:
            print('Persistence failed; this attempt is FAIL (exit 9)', file=sys.stderr)
        raise


def execute(root, directory, manifest_path, raw_root, julia):
    # Reusing a prior PASS directory is an error; do not overwrite its evidence.
    directory.mkdir(parents=True, exist_ok=False)
    record = {'schema_version': 1, 'run_id': directory.name, 'execution_status': 'INCOMPLETE',
              'exit_code': 9, 'sources': {}, 'new_scf_status': 'NOT_RUN', 'new_eigensolve_status': 'NOT_RUN'}
    write_json(directory / 'result.json', record)
    plan = load(root / PLAN)
    try:
        for path, sha in {**plan['source_evidence_sha256'], **plan['frozen_environment_sha256']}.items():
            require(digest(root / path) == sha, 'Frozen source/environment changed: ' + path)
        commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
        require(commit != plan['base_commit'], 'Preparation commit required before extraction')
        require(subprocess.check_output(['git', '-C', str(root), 'show', 'HEAD:' + PLAN]) == (root / PLAN).read_bytes(),
                'Plan must be committed before extraction')
        record.update(execution_commit=commit, plan_sha256=digest(root / PLAN),
                      execution_source_sha256={p: digest(root / p) for p in CODE},
                      started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        datasets = {}
        for label in ('A', 'B'):
            try:
                binding = bind_dftk(root, plan, label)
                record['sources'][label] = {'raw_source_binding_status': 'PASS', 'binding': binding}
                request = {'schema_version': 1, 'plan_path': PLAN, 'plan_sha256': digest(root / PLAN), 'label': label}
                write_json(directory / (label + '-request.json'), request)
                env = os.environ.copy()
                env['JULIA_LOAD_PATH'] = '@:@stdlib'
                command = [julia, '--startup-file=no', '--color=no', '--project=' + str(root / 'environment/workbench'),
                           str(root / 'scripts/extract_soc_density.jl'), str(directory / (label + '-request.json')),
                           str(directory / label)]
                with (directory / (label + '.stdout')).open('w') as out, (directory / (label + '.stderr')).open('w') as err:
                    completed = subprocess.run(command, cwd=root, env=env, stdout=out, stderr=err)
                record['sources'][label]['exit_code'] = completed.returncode
                require(completed.returncode == 0, 'Julia density extraction failed; retain this attempt')
                metadata = load(directory / label / 'metadata.json')
                require(metadata['execution_status'] == 'PASS' and metadata['exit_code'] == 0 and
                        metadata['source_run_id'] == plan['sources'][label]['run_id'] and
                        metadata['plan_sha256'] == digest(root / PLAN) and
                        metadata['executed_script_sha256'] == record['execution_source_sha256']['scripts/extract_soc_density.jl'],
                        'Julia result is not a successful current extraction')
                record['sources'][label]['metadata'] = metadata
                datasets.update(read_bound_native_csv(directory / label / 'native.csv', label, metadata, plan['fft_size']))
            except Exception as error:
                record['sources'].setdefault(label, {})['extraction_status'] = 'BLOCKED'
                record['sources'][label]['reason'] = str(error)
        # Only after the A/B attempts do we parse original G40 charge.
        try:
            from parse_qe_charge_density import parse_qe_charge_density
            from compare_density_hartree import write_coefficients_gzip
            binding = bind_qe(root, plan, manifest_path, raw_root)
            record['sources']['G40'] = {'raw_source_binding_status': 'PASS', 'binding': binding}
            xml = validate_qe_xml(Path(binding['files']['scratch/mg_soc_qe_v1.save/data-file-schema.xml']['path']), plan)
            parsed = parse_qe_charge_density(Path(binding['files']['scratch/mg_soc_qe_v1.save/charge-density.dat']['path']),
                                            expected_ngm=plan['sources']['G40']['expected_ngm'])
            parsed['reciprocal_duality_max_abs'] = validate_reciprocal_columns(parsed['b_columns_bohr_inv'], plan)
            b = parsed['b_columns_bohr_inv']
            q2 = [math.fsum(math.fsum(b[j][i]*m[j] for j in range(3))**2 for i in range(3)) for m in parsed['miller']]
            parsed['native_max_q2_over_2_ha'] = max(q2) / 2
            require(parsed['native_max_q2_over_2_ha'] <= plan['sources']['G40']['density_cutoff_ha'] +
                    plan['thresholds']['cutoff_abs_ha'], 'G40 actual Miller list exceeds density cutoff')
            store_qe_coefficients(directory, parsed, datasets, write_coefficients_gzip)
            record['sources']['G40'].update(metadata=parsed, xml=xml)
        except Exception as error:
            record['sources'].setdefault('G40', {})['extraction_status'] = 'BLOCKED'
            record['sources']['G40']['reason'] = str(error)
        for label, source in record['sources'].items():
            if 'binding' in source:
                for item in source['binding']['files'].values():
                    require(digest(item['path']) == item['sha256'], 'Read-only source changed after extraction')
                source['source_preservation_status'] = 'PASS'
        # Arithmetic and explicit public export are separate, replayable operations.
        complete = set(datasets) == {'A_in','A_out','B_in','B_out','QE'} and all(
            'extraction_status' not in source for source in record['sources'].values())
        record['execution_status'] = 'PASS' if complete else 'BLOCKED'
        record['exit_code'] = 0 if record['execution_status'] == 'PASS' else 7
        record['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save_completion(directory, record)
    except BaseException as error:
        record.update(execution_status='FAIL', exit_code=9, reason=type(error).__name__ + ': ' + str(error))
        save_completion(directory, record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--qe-raw-manifest', required=True, type=Path)
    parser.add_argument('--qe-raw-root', required=True, type=Path)
    parser.add_argument('--julia', default='julia')
    args = parser.parse_args()
    try:
        result = execute(ROOT, args.output.resolve(), args.qe_raw_manifest, args.qe_raw_root, args.julia)
        print(json.dumps({'run_id': result['run_id'], 'execution_status': result['execution_status'],
                          'exit_code': result['exit_code']}, allow_nan=False))
        return result['exit_code']
    except BaseException as error:
        print(json.dumps({'execution_status':'FAIL', 'exit_code':9, 'reason':str(error)}))
        return 9


if __name__ == '__main__':
    raise SystemExit(main())
