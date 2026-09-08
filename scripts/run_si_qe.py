#!/usr/bin/env python3
"""Run predeclared Si QE slots, retaining current failure evidence.

The existing launcher identity and process-group helper are reused. The identity
action queries Julia/JLL metadata only; it never starts a QE numerical product.
The default Phase 8A contract remains fixed; explicit Phase 8B profiles add only
their prepared SCF/Gamma pair. No retry, installation or arbitrary override.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET

from run_qe_soc import digest, write_json, execute
from run_scalar_baseline import qe_identity
from si_soc_comparison import parse_si_qe, _contract
from parse_qe_soc_diagnostics import native_warnings

ROOT = Path(__file__).resolve().parents[1]
BASE = '9342a5ea21a76acd0d74d228d4a2081394f702d0'
PREPARATION = 'e5b940c7fb0234d4cb97572ee3f8225e9e8b6087'
CASE_DIR = 'benchmarks/si-soc-splitting-v1'
PREP_FILES = tuple(CASE_DIR+'/'+x for x in ('README.md', 'case.json', 'plan.json',
                                         'source.json', 'qe-scf.in', 'qe-spectrum.in'))
ENV_FILES = ('config/sources.lock', 'environment/workbench/Project.toml',
             'environment/workbench/Manifest.toml', 'environment/workbench/checksums.toml')
SOURCES = ('scripts/run_si_qe.py', 'scripts/si_soc_comparison.py', 'scripts/run_qe_soc.py',
           'scripts/run_scalar_baseline.py', 'scripts/parse_qe_soc.py',
           'scripts/parse_qe_baseline.py', 'scripts/parse_qe_soc_diagnostics.py',
           'scripts/probe_qe_postprocess_build.jl')
HISTORICAL = ('benchmarks/mg-soc-qe-diagnostics-v1/plan.json',
              'results/mg-soc-qe-diagnostics/evidence.json')
THREADS = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
           'VECLIB_MAXIMUM_THREADS', 'JULIA_NUM_THREADS', 'BLIS_NUM_THREADS')
FORBIDDEN_ENV = ('JULIA_PROJECT', 'JULIA_LOAD_PATH', 'JULIA_DEPOT_PATH',
                 'DYLD_LIBRARY_PATH', 'DYLD_FALLBACK_LIBRARY_PATH', 'LD_LIBRARY_PATH', 'LD_PRELOAD')
SAVE = Path('scratch/si8a.save')


def profile_layout(profile=None):
    if profile is None:
        return CASE_DIR, SAVE, '.work/phase8a'
    from si_soc_sensitivity import CASE_DIR as sensitivity_dir, PROFILE_IDS
    require(profile in PROFILE_IDS, 'Unregistered Si sensitivity profile')
    return sensitivity_dir+'/'+profile, Path('scratch/si8b_'+profile.lower()+'.save'), '.work/phase8b/'+profile


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.PIPE)


def committed_hash(root, revision, path):
    return hashlib.sha256(git(root, 'show', revision+':'+path)).hexdigest()


def confined_run(root, path, profile=None):
    area = root/profile_layout(profile)[2]
    path = Path(path).absolute()
    require(area.resolve() == area and path.resolve() == path, 'Run path aliases are not permitted')
    require(path != area and area in path.parents, 'Run and parent paths must be inside the current phase/profile area')
    return path


def clean_execution(root, expected_head):
    require(git(root, 'rev-parse', 'HEAD').decode().strip() == expected_head, 'Execution HEAD changed')
    require(git(root, 'status', '--porcelain', '--untracked-files=all').decode() == '',
            'Formal numerical action requires a clean committed worktree')


def file_map(directory):
    """Hash complete ordinary files; never follow an unbound symlink/save alias."""
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink(), 'Missing ordinary save directory')
    entries = sorted(directory.rglob('*'))
    require(not any(p.is_symlink() for p in entries), 'Symlinks are not allowed in bound save tree')
    require(all(p.is_file() or p.is_dir() for p in entries), 'Nonregular entry in save tree')
    return {p.relative_to(directory).as_posix(): {'sha256': digest(p), 'bytes': p.stat().st_size}
            for p in entries if p.is_file()}


def required_save(directory, nk):
    mapping = file_map(directory)
    needed = {'charge-density.dat', 'data-file-schema.xml', 'Si_r.upf'}
    needed.update('wfc'+str(i)+'.dat' for i in range(1, nk+1))
    require(needed <= mapping.keys(), 'Required final charge/XML/UPF/all wavefunctions are missing')
    return mapping


def frozen_inputs(root, *, require_execution_commit, profile=None):
    root = Path(root).resolve()
    case_dir, save, _ = profile_layout(profile)
    preparation, prep_files, source_files = PREPARATION, PREP_FILES, SOURCES
    if profile is not None:
        from si_soc_sensitivity import PREPARATION as preparation, prepared_paths, load_case
        prep_files = (*prepared_paths(), CASE_DIR+'/source.json')
        source_files = (*SOURCES, 'scripts/si_soc_sensitivity.py', 'scripts/run_si_dftk.py')
    head = git(root, 'rev-parse', 'HEAD').decode().strip()
    require(subprocess.run(['git', 'merge-base', '--is-ancestor', preparation, head], cwd=root,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0,
            'Preparation commit is not an ancestor of execution HEAD')
    prep = {p: committed_hash(root, preparation, p) for p in prep_files}
    frozen = {p: committed_hash(root, BASE, p) for p in (*ENV_FILES, *HISTORICAL)}
    for path, expected in {**prep, **frozen}.items():
        require(digest(root/path) == expected, 'Prepared/frozen file mismatch: '+path)
    case = load_case(root, profile) if profile is not None else json.loads((root/CASE_DIR/'case.json').read_text())
    _contract(case)
    source = json.loads((root/CASE_DIR/'source.json').read_text())
    relative = Path(source['local_path'])
    require(not relative.is_absolute() and '..' not in relative.parts, 'Source path must be portable and confined')
    pseudo = root/relative
    require(pseudo.is_file() and not pseudo.is_symlink(), 'Original authenticated Si UPF is missing')
    raw = pseudo.read_bytes()
    blob = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    require(len(raw) == source['bytes'] == 291215 and blob == source['git_blob_sha1']
            == '0bba6c59d28251b59bf831079a340f7147308611', 'Whole-file Si source identity mismatch')
    require(hashlib.sha256(raw).hexdigest() == source['sha256'] == case['pseudo']['sha256'], 'Runtime UPF SHA-256 mismatch')
    header = ET.fromstring(raw).find('PP_HEADER').attrib
    expected = {'element': 'Si', 'pseudo_type': 'NC', 'relativistic': 'full', 'has_so': 'T',
                'functional': 'PBE', 'core_correction': 'T'}
    require(all(header.get(k, '').strip() == v for k, v in expected.items()), 'Authenticated source header mismatch')
    require(float(header['z_valence']) == 4 and int(header['number_of_proj']) == 10
            and int(header['l_max']) == 2 and int(header['mesh_size']) == 1528, 'Source dimensions/valence mismatch')
    lock = tomllib.loads((root/'config/sources.lock').read_text())
    upstream = {}
    for label, spec in lock['source'].items():
        checkout = root/spec['checkout']
        actual = git(checkout, 'rev-parse', 'HEAD').decode().strip()
        status = git(checkout, 'status', '--porcelain', '--untracked-files=all').decode()
        require(actual == spec['commit'] and status == '', 'Frozen upstream commit/worktree mismatch: '+label)
        upstream[label] = {'commit': actual, 'status': status, 'checkout': spec['checkout']}
    sources = {p: digest(root/p) for p in source_files}
    if require_execution_commit:
        clean_execution(root, head)
        for p, value in sources.items():
            require(committed_hash(root, head, p) == value, 'Execution source must be committed: '+p)
    result = {'case': case, 'source': source, 'pseudo_path': str(pseudo),
            'preparation_commit': preparation, 'execution_commit': head,
            'prepared_sha256': prep, 'frozen_sha256': frozen, 'source_sha256': sources, 'upstream': upstream}
    if profile is not None:
        result.update(sensitivity_profile=profile, case_sha256=prep[case_dir+'/case.json'],
                      case_directory=case_dir, save_path=save.as_posix())
    return result


def identity(root, directory, prepared, env):
    """Fresh read-only JLL product query, then compare actual resolved code files."""
    launcher = Path.home()/'.local/bin/pw.x'
    expected = json.loads((root/HISTORICAL[0]).read_text())['qe_identity']
    baseline = json.loads((root/HISTORICAL[1]).read_text())['qe_dependency_baseline']
    observed = qe_identity(str(launcher), directory, env)
    for key in ('binary_sha256', 'launcher_sha256', 'runner_sha256', 'jll_version', 'jll_uuid'):
        require(observed.get(key) == expected[key], 'QE actual launch identity mismatch: '+key)
    content = launcher.read_text()
    match = re.fullmatch(r'#!/bin/sh\s+exec (\S+) --startup-file=no (\S+/qe-runner\.jl) "\$\(basename "\$0"\)" "\$@"\s*', content)
    require(match is not None, 'Expected existing launcher chain is not recognized')
    command = [match.group(1), '--startup-file=no', str(root/'scripts/probe_qe_postprocess_build.jl')]
    with (directory/'qe-dependencies.stdout').open('w') as out, (directory/'qe-dependencies.stderr').open('w') as err:
        probe = subprocess.run(command, env=env, cwd=directory, stdout=out, stderr=err, stdin=subprocess.DEVNULL)
    require(probe.returncode == 0, 'Read-only JLL library probe failed')
    metadata = tomllib.loads((directory/'qe-dependencies.stdout').read_text())
    require(metadata['numerical_executions'] == 0, 'Identity receipt is not read-only')
    require(metadata['julia_version'] == baseline['julia_version'], 'QE launcher Julia version mismatch')
    require(metadata['jll_version'] == observed['jll_version'] and metadata['jll_uuid'] == observed['jll_uuid'], 'Product query JLL mismatch')
    require(Path(metadata['products']['pw']['path']).resolve() == Path(observed['binary_path']).resolve(), 'Product query resolved a different pw.x')
    require(metadata['products']['pw']['sha256'] == observed['binary_sha256'], 'Product query binary mismatch')
    project = Path(metadata['active_project']).resolve()
    require(project == Path(observed['active_project']).resolve(), 'JLL active projects differ')
    manifest = project.with_name('Manifest.toml')
    require(digest(project) == baseline['project_sha256'] and digest(manifest) == baseline['manifest_sha256'],
            'QE global Project/Manifest differs from frozen build')
    dependencies = {str(project): digest(project), str(manifest): digest(manifest),
                    str(launcher): observed['launcher_sha256'], observed['runner_path']: observed['runner_sha256'],
                    observed['binary_path']: observed['binary_sha256']}
    selected_libraries = []
    for expected_library in baseline['libraries']:
        matches = {str(Path(p).resolve()): sha for p, sha in metadata['loaded_libraries'].items()
                   if Path(p).name == expected_library['filename']}
        require(len(matches) == 1, 'Missing/ambiguous actual JLL dependency: '+expected_library['filename'])
        path, sha = next(iter(matches.items()))
        require(sha == expected_library['sha256'] == digest(path), 'Frozen JLL dependency changed: '+expected_library['filename'])
        dependencies[path] = sha
        selected_libraries.append({'filename': expected_library['filename'], 'sha256': sha})
    return {'status': 'PASS', 'qe_identity': observed, 'dependency_sha256': dependencies,
            'selected_libraries': selected_libraries, 'julia_version': metadata['julia_version'],
            'global_project_sha256': digest(project), 'global_manifest_sha256': digest(manifest),
            'numerical_executions': 0, 'probe_command': command,
            'scope': 'Same existing launcher/JLL/binary and all Phase7B library hashes; no new installation or QE identity run'}


def _recheck(root, prepared, observed):
    for path, expected in {**prepared['prepared_sha256'], **prepared['frozen_sha256'], **prepared['source_sha256']}.items():
        require(digest(root/path) == expected, 'Source/input changed during run: '+path)
    require(digest(prepared['pseudo_path']) == prepared['source']['sha256'], 'Original UPF changed during run')
    for path, expected in observed['dependency_sha256'].items():
        require(digest(path) == expected, 'QE dependency changed during run')
    for label, spec in prepared['upstream'].items():
        checkout = root/spec['checkout']
        require(git(checkout, 'rev-parse', 'HEAD').decode().strip() == spec['commit']
                and git(checkout, 'status', '--porcelain', '--untracked-files=all').decode() == '',
                'Frozen upstream changed during run: '+label)


def bind_parent(parent, prepared):
    parent = Path(parent).resolve()
    result = json.loads((parent/'result.json').read_text())
    require(result.get('action') == 'Q-SCF' and result.get('execution_status') == 'PASS'
            and result.get('input_comparability_status') == 'PASS' and result.get('exit_code') == 0
            and type(result.get('process_exit_code')) is int and result['process_exit_code'] == 0,
            'Parent is not a successfully parsed new Si Q-SCF')
    require(result.get('run_id') == parent.name and result.get('preparation_commit') == prepared['preparation_commit'],
            'Parent run/preparation identity mismatch')
    require(result.get('execution_commit') == prepared['execution_commit']
            and result.get('executed_source_sha256') == prepared['source_sha256'],
            'Parent execution commit/source hashes differ from current execution')
    require(result['prepared_sha256'] == prepared['prepared_sha256'], 'Parent physical case/input differs')
    record = json.loads((parent/'qe-result.json').read_text())
    require(digest(parent/'qe-result.json') == result['parsed_sha256'] and record['kind'] == 'scf'
            and record['case'] == prepared['case']['case'] and record['scf']['converged'], 'Parent parsed SCF source mismatch')
    require(record['run_id'] == result['run_id'], 'Parent parsed run mismatch')
    sensitivity = 'sensitivity_profile' in prepared
    if sensitivity:
        case = prepared['case']
        for value in (result, record):
            require(value.get('case') == case['case'] and value.get('sensitivity_profile') == prepared['sensitivity_profile']
                    and value.get('case_sha256') == prepared['case_sha256'], 'Parent case/profile/hash mismatch')
        require(record['temperature_ha'] == case['electrons']['temperature_ha']
                and record['cutoffs'] == case['cutoffs'] and record['requested_kpoint_count'] == len(case['kpoints']),
                'Parent cutoff/k/temperature mismatch')
        require(record.get('density_source_sha256') == result.get('density_source_sha256')
                and record.get('n_electrons') == 8 and record.get('n_bands') == 24
                and record.get('occupation_capacity') == 1, 'Parent density/electron/state binding mismatch')
    save = Path(prepared.get('save_path', SAVE))
    mapping = required_save(parent/save, len(prepared['case']['kpoints']) if sensitivity else 8)
    require(mapping == result['save_files'], 'Original parent save files differ from completion receipt')
    require(mapping['Si_r.upf']['sha256'] == prepared['source']['sha256'], 'Saved parent UPF mismatch')
    require(mapping['data-file-schema.xml']['sha256'] == record['raw_sha256']['xml'], 'Parent XML differs from its parsed final SCF')
    if sensitivity:
        require(record['density_source_sha256'] == mapping['charge-density.dat']['sha256'], 'Parent recorded density differs from saved charge')
    binding = {'directory': str(parent), 'run_id': result['run_id'], 'save_files': mapping,
            'parent_result_sha256': digest(parent/'result.json'), 'parent_parsed_sha256': digest(parent/'qe-result.json'),
            'charge_sha256': mapping['charge-density.dat']['sha256'], 'fermi_energy_ha': record['fermi_energy_ha']}
    if sensitivity:
        binding.update(save_path=save.as_posix(), sensitivity_profile=prepared['sensitivity_profile'],
                       case_sha256=prepared['case_sha256'])
    return binding


def copy_parent(parent, destination):
    save = Path(parent.get('save_path', SAVE))
    source = Path(parent['directory'])/save
    require(file_map(source) == parent['save_files'], 'Parent changed before copying')
    destination = Path(destination)/save
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, copy_function=shutil.copyfile)
    require(file_map(destination) == parent['save_files'], 'Copied save bytes differ')
    for path in parent['save_files']:
        require(not os.path.samefile(source/path, destination/path)
                and (destination/path).stat().st_nlink == 1, 'Copy aliases original save')


def parent_unchanged(parent):
    directory = Path(parent['directory'])
    require(file_map(directory/parent.get('save_path', SAVE)) == parent['save_files'], 'Original Q-SCF save changed')
    require(digest(directory/'result.json') == parent['parent_result_sha256']
            and digest(directory/'qe-result.json') == parent['parent_parsed_sha256'], 'Original Q-SCF receipts changed')


def claim_slot(root, action, run_id, preparation):
    registry = root/profile_layout(preparation.get('sensitivity_profile'))[2]/'slots'
    registry.mkdir(parents=True, exist_ok=True)
    with (registry/(action+'.json')).open('x') as handle:
        json.dump({'action': action, 'run_id': run_id, 'execution_commit': preparation['execution_commit'],
                   'claimed_utc': now(), 'attempt_limit': 1}, handle, indent=2)
        handle.write('\n')


def run(action, directory, *, parent=None, root=ROOT, profile=None, preflight_manifest=None):
    root, directory = Path(root).resolve(), Path(directory).absolute()
    case_id = 'si-soc-splitting-v1' if profile is None else 'si-soc-sensitivity-v1/'+str(profile)
    state = {'schema_version': 1, 'case': case_id, 'action': action,
             'run_id': directory.name, 'execution_status': 'INCOMPLETE', 'exit_code': 9,
             'process_exit_code': None, 'worker_started': False, 'created_utc': now(),
             'input_comparability_status': 'NOT_RUN', 'scientific_review': 'REVIEW_REQUIRED'}
    owned, source, prepared, observed = False, None, None, None
    try:
        case_dir, save, _ = profile_layout(profile)
        spectrum_action = 'Q-SPECTRUM' if profile is None else 'Q-GAMMA'
        require(action in ('identity', 'Q-SCF', spectrum_action), 'Unsupported Si QE slot')
        require((parent is not None) == (action == spectrum_action), 'Spectrum needs its own Q-SCF parent; other actions reject parents')
        require(profile is not None or preflight_manifest is None, 'B0 rejects sensitivity preflight override')
        directory = confined_run(root, directory, profile)
        if parent is not None:
            parent = confined_run(root, parent, profile)
            require(parent != directory, 'Parent and new output directory cannot be identical')
        directory.mkdir(parents=True, exist_ok=False)
        owned = True
        write_json(directory/'result.json', state)
        require(not any(k in os.environ for k in FORBIDDEN_ENV), 'Inherited Julia/library override is not allowed for frozen QE')
        env = dict(os.environ, **{k: '1' for k in THREADS})
        prepared = frozen_inputs(root, require_execution_commit=action != 'identity', profile=profile)
        observed = identity(root, directory, prepared, env)
        write_json(directory/'identity.json', observed)
        state.update(preparation_commit=prepared['preparation_commit'], execution_commit=prepared['execution_commit'],
                     prepared_sha256=prepared['prepared_sha256'], frozen_sha256=prepared['frozen_sha256'],
                     executed_source_sha256=prepared['source_sha256'], pseudo_sha256=prepared['source']['sha256'],
                     parallelism={'thread_environment': {k: env[k] for k in THREADS}, 'mpi_processes_requested': 1})
        if profile is not None:
            state.update(sensitivity_profile=profile, case_sha256=prepared['case_sha256'])
        if action == 'identity':
            _recheck(root, prepared, observed)
            state.update(execution_status='PASS', input_comparability_status='NOT_APPLICABLE_IDENTITY',
                         identity_status='PASS', numerical_executions=0, exit_code=0)
            write_json(directory/'result.json', state)
            return state
        if profile is not None:
            require(preflight_manifest is not None, 'All three sensitivity preflights are required before any formal slot')
            from run_si_dftk import verify_sensitivity_preflights
            verify_sensitivity_preflights(root, Path(preflight_manifest), prepared['execution_commit'])
            state['preflight_manifest_sha256'] = digest(preflight_manifest)
        if parent is not None:
            source = bind_parent(parent, prepared)
            copy_parent(source, directory)
            write_json(directory/'parent-binding.json', source)
        filename = 'qe-scf.in' if action == 'Q-SCF' else ('qe-spectrum.in' if profile is None else 'qe-gamma.in')
        shutil.copyfile(root/case_dir/filename, directory/'qe.in')
        (directory/'pseudo').mkdir()
        shutil.copyfile(prepared['pseudo_path'], directory/'pseudo/Si_r.upf')
        require(digest(directory/'pseudo/Si_r.upf') == prepared['source']['sha256'], 'Copied actual UPF mismatch')
        require(digest(directory/'qe.in') == prepared['prepared_sha256'][case_dir+'/'+filename], 'Copied QE input mismatch')
        command = [observed['qe_identity']['selected_path'], '-in', 'qe.in']
        write_json(directory/'preflight.json', {'action': action, 'run_id': state['run_id'],
            'preparation': prepared, 'identity': observed, 'command': command,
            'parent': source, 'environment': {k: env[k] for k in THREADS},
            'fresh_scf_scratch': not (directory/'scratch').exists() if action == 'Q-SCF' else None})
        claim_slot(root, action, state['run_id'], prepared)
        state['worker_started'] = True
        write_json(directory/'result.json', state)
        code = execute(command, directory, env)
        state['process_exit_code'] = code
        write_json(directory/'result.json', state)
        require(type(code) is int and code == 0, 'Actual QE worker failed with code '+str(code))
        require(digest(directory/'pseudo/Si_r.upf') == prepared['source']['sha256'], 'Worker pseudo copy changed')
        case = dict(prepared['case'], verified_pseudo_sha256=prepared['source']['sha256'])
        nk = (len(case['kpoints']) if action == 'Q-SCF' else 1) if profile is not None else (8 if action == 'Q-SCF' else 3)
        saved = required_save(directory/save, nk)
        require(saved['Si_r.upf']['sha256'] == prepared['source']['sha256'], 'QE saved a different UPF')
        shutil.copyfile(directory/save/'data-file-schema.xml', directory/'qe.xml')
        if profile is not None:
            case['case_sha256'] = prepared['case_sha256']
        stdout = (directory/'qe.stdout').read_text()
        mpi = re.findall(r'Parallel version \(MPI\), running on\s+(\d+) processors', stdout)
        nodes = re.findall(r'MPI processes distributed on\s+(\d+) nodes', stdout)
        require(mpi == ['1'] and nodes == ['1'], 'Native MPI process/node count is not one')
        state['parallelism'].update(native_mpi_processes=1, native_nodes=1)
        parsed = parse_si_qe(directory/'qe.xml', stdout, (directory/'qe.stderr').read_text(),
                             kind='scf' if action == 'Q-SCF' else 'spectrum', case=case, process_exit_code=code)
        parsed['run_id'] = state['run_id']
        if source is not None:
            parent_unchanged(source)
            parsed.update(source_scf_run_id=source['run_id'], density_source_sha256=source['charge_sha256'],
                          fermi_energy_ha=source['fermi_energy_ha'],
                          density_binding_scope='Original Q-SCF saved charge copied exactly before bands; atomic+random new-k orbitals')
            # Bands is not authorized to create new feedback density. Its saved
            # charge may be rewritten in-place only if bytes remain identical.
            require(saved['charge-density.dat']['sha256'] == source['charge_sha256'], 'Bands changed its saved charge density')
        else:
            parsed['density_source_sha256'] = saved['charge-density.dat']['sha256']
        _recheck(root, prepared, observed)
        if profile is not None:
            clean_execution(root, prepared['execution_commit'])
            require(digest(preflight_manifest) == state['preflight_manifest_sha256'], 'Preflight manifest changed during run')
        # Construct/serialize all success payloads before the canonical result.
        json.dumps(parsed, allow_nan=False)
        state.update(execution_status='PASS', input_comparability_status='PASS', exit_code=0,
                     completed_utc=now(), save_files=saved, warnings=parsed['warning_evidence'],
                     eigensolver_status=parsed['eigensolver_status'], source_preservation_status='PASS' if source else 'NOT_APPLICABLE',
                     density_source_sha256=parsed['density_source_sha256'])
        write_json(directory/'qe-result.json', parsed)
        state['parsed_sha256'] = digest(directory/'qe-result.json')
        write_json(directory/'save-manifest.json', saved)
        write_json(directory/'result.json', state)  # Success discriminator is last.
    except (Exception, KeyboardInterrupt) as error:
        code = state.get('process_exit_code')
        if owned and (directory/'process-exit.json').is_file():
            try: code = json.loads((directory/'process-exit.json').read_text())['exit_code']
            except (ValueError, KeyError, OSError): pass
        failure = {'schema_version': 1, 'case': case_id, 'action': action, 'run_id': directory.name,
                   'execution_status': 'FAIL' if state['worker_started'] else 'BLOCKED',
                   'input_comparability_status': 'NOT_ESTABLISHED', 'scientific_review': 'REVIEW_REQUIRED',
                   'exit_code': code if type(code) is int and 0 < code < 256 else 9,
                   'process_exit_code': code, 'worker_started': state['worker_started'],
                   'reason': str(error), 'error_type': type(error).__name__, 'failed_utc': now()}
        if profile is not None:
            failure['sensitivity_profile'] = profile
        if owned:
            failure['worker_process_start_recorded'] = (directory/'process-start.json').is_file()
            if (directory/'qe.stdout').is_file() and (directory/'qe.stderr').is_file():
                try:
                    failure['warnings'] = native_warnings((directory/'qe.stdout').read_text(),
                        (directory/'qe.stderr').read_text(), code)
                except Exception as warning_error:
                    failure['warning_extraction_status'] = type(warning_error).__name__
        if source is not None:
            try:
                parent_unchanged(source)
                failure['source_preservation_status'] = 'PASS'
            except Exception as source_error:
                failure['source_preservation_status'] = 'FAIL'
                failure['source_preservation_error'] = str(source_error)
        state = failure
        if owned:
            if (directory/'qe-result.json').is_file():
                try:
                    write_json(directory/'qe-result.json', dict(failure,
                        normalized_result_status='INVALIDATED_BY_FINALIZATION_FAILURE'))
                except Exception:
                    print('Persistence failure: parsed candidate could not be invalidated; canonical current result and nonzero exit are mandatory.', file=sys.stderr)
            try: write_json(directory/'result.json', state)
            except Exception: print('Persistence failure: current Si QE run is not PASS.', file=sys.stderr)
        else:
            print('No output directory was claimed; existing result files were preserved.', file=sys.stderr)
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('identity', 'Q-SCF', 'Q-SPECTRUM', 'Q-GAMMA'))
    parser.add_argument('directory', type=Path, help='New unique run directory; existing paths refused')
    parser.add_argument('--parent', type=Path)
    parser.add_argument('--profile', choices=('E40', 'T05', 'K4'))
    parser.add_argument('--preflight-manifest', type=Path)
    args = parser.parse_args(argv)
    state = run(args.action, args.directory, parent=args.parent, profile=args.profile,
                preflight_manifest=args.preflight_manifest)
    print(json.dumps(state, allow_nan=False))
    return state['exit_code']


if __name__ == '__main__':
    sys.exit(main())
