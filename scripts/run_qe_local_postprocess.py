#!/usr/bin/env python3
"""Exactly two independently copied, source-bound pp slots; no retry backend."""
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
import uuid

from parse_qe_filplot import parse_qe_filplot
from run_qe_soc import execute

ROOT = Path(__file__).resolve().parents[1]
PLAN = 'benchmarks/mg-soc-qe-local-potential-v1/plan.json'
G40_RUN = '20260907T112107073262Z-G40-3f9731a6'
SAVE = 'scratch/mg_soc_qe_v1.save/'
REQUIRED = {SAVE+name for name in ('data-file-schema.xml', 'charge-density.dat', 'Mg.upf')}
THREADS = {'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
           'VECLIB_MAXIMUM_THREADS', 'JULIA_NUM_THREADS'}
FORBIDDEN_INHERITED = {'JULIA_PROJECT', 'JULIA_LOAD_PATH', 'JULIA_DEPOT_PATH',
                       'LD_LIBRARY_PATH', 'LD_PRELOAD', 'DYLD_LIBRARY_PATH',
                       'DYLD_FALLBACK_LIBRARY_PATH', 'DYLD_INSERT_LIBRARIES'}
EXECUTION_SOURCES = ['scripts/run_qe_local_postprocess.py', 'scripts/parse_qe_filplot.py',
                     'scripts/run_qe_soc.py', 'scripts/run_scalar_baseline.py']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def write_json(path, record):
    """Encode before touching disk, then publish one completely written object."""
    encoded = (json.dumps(record, indent=2, allow_nan=False)+'\n').encode()
    temporary = path.parent/(path.name+'.tmp-'+uuid.uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def snapshot(directory):
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink(), 'Missing/symlink protected source root')
    files = {}
    for path in sorted(directory.rglob('*')):
        require(not path.is_symlink(), 'Symlink in protected source tree')
        if path.is_file():
            files[str(path.relative_to(directory))] = digest(path)
    require(bool(files), 'Empty protected source tree')
    return files


def _git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.PIPE).decode().strip()


def _committed(root, revision, path, expected):
    data = subprocess.check_output(['git', 'show', revision+':'+path], cwd=root, stderr=subprocess.PIPE)
    require(hashlib.sha256(data).hexdigest() == expected, 'Committed bytes mismatch: '+path)


def input_text(slot):
    filename, plot = ('local-ionic.pp', 2) if slot == 'P2' else ('charge.pp', 0)
    text = "&INPUTPP\n prefix = 'mg_soc_qe_v1',\n outdir = './scratch',\n filplot = './%s',\n plot_num = %d,\n" % (filename, plot)
    return text + (' spin_component = 0,\n' if slot == 'P0' else '') + '/\n'


def _changed(expected, actual):
    return {name: {'before': expected.get(name), 'after': actual.get(name)}
            for name in sorted(set(expected)|set(actual)) if expected.get(name) != actual.get(name)}


def _dependencies(preparation):
    mapping = preparation['dependency_sha256']
    require(isinstance(mapping, dict) and bool(mapping), 'Missing dependency identities')
    for name, expected in mapping.items():
        require(Path(name).is_absolute() and digest(name) == expected, 'Dependency identity mismatch: '+name)
    launcher = preparation['launcher']
    require(launcher in mapping, 'Launcher is not among verified dependencies')


def validate_preparation(root, prep, plan, slot):
    require(prep['source_run_id'] == G40_RUN, 'Source must be original G40 SCF, not D40/C40')
    require(plan['source_run_id'] == G40_RUN, 'Committed source is not original G40')
    require(not (FORBIDDEN_INHERITED & os.environ.keys()), 'Unapproved inherited Julia/library environment override')
    require(digest(root/PLAN) == prep['plan_sha256'], 'Plan changed after preparation')
    revision = prep['preparation_commit']
    require(re.fullmatch('[0-9a-f]{40}', revision) is not None, 'Preparation commit is not an exact SHA')
    require(subprocess.run(['git', 'merge-base', '--is-ancestor', revision, 'HEAD'], cwd=root,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0,
            'Preparation commit is not an ancestor of execution commit')
    _committed(root, revision, PLAN, prep['plan_sha256'])
    require(set(plan['slots']) == {'P2', 'P0'}, 'Unexpected postprocessing slot')
    spec = plan['slots'][slot]
    require(spec['plot_num'] == (2 if slot == 'P2' else 0), 'Slot plot_num mismatch')
    require(spec['filplot'] == ('local-ionic.pp' if slot == 'P2' else 'charge.pp'), 'Slot output mismatch')
    path = Path(spec['input_path'])
    require(not path.is_absolute() and '..' not in path.parts, 'Nonportable input path')
    require(digest(root/path) == spec['input_sha256'], 'Postprocessing input hash mismatch')
    require((root/path).read_text() == input_text(slot), 'Input contains an unapproved parameter or change')
    _committed(root, revision, str(path), spec['input_sha256'])
    frozen = prep['frozen_public_sha256']
    require(isinstance(frozen, dict) and bool(frozen), 'Missing frozen public source identities')
    for name, expected in frozen.items():
        require(digest(root/name) == expected, 'Frozen source changed: '+name)
    for name in EXECUTION_SOURCES:
        _committed(root, 'HEAD', name, digest(root/name))
    require(set(prep['environment']) == THREADS and all(v == '1' for v in prep['environment'].values()),
            'Single-process/thread environment mismatch')
    require(set(prep['source_files']) == REQUIRED, 'Save copy must contain exactly XML, charge and Mg UPF')
    require(prep['source_files'] == plan['source_files'], 'Source file receipt differs from committed plan')
    require(set(prep['protected_sources']) == {'G40'}, 'Unexpected historical source set')
    source = prep['protected_sources']['G40']
    original = Path(source['path'])
    require(snapshot(original) == source['sha256'], 'Original G40 full tree differs from saved snapshot')
    full_digest = hashlib.sha256(json.dumps(source['sha256'], sort_keys=True).encode()).hexdigest()
    require(full_digest == plan['source_mapping']['full_G40_snapshot_sha256'], 'Full G40 snapshot is detached from committed plan')
    for name, expected in prep['source_files'].items():
        path = original/name
        require(source['sha256'].get(name) == expected['sha256'], 'Source file is detached from G40 snapshot')
        require(path.stat().st_size == expected['bytes'] and digest(path) == expected['sha256'],
                'Required source bytes mismatch: '+name)
    _dependencies(prep)
    identity = plan['qe_identity']
    require(identity['pp_build_identity_status'] == 'PASS' and identity['historical_pw_verification_status'] == 'PASS',
            'Unverified common QE build')
    require(digest(prep['launcher']) == identity['launcher_sha256'], 'Launcher differs from committed public identity')
    required_hashes = {identity['products'][p]['sha256'] for p in ('pp', 'pw')}
    required_hashes.update(identity[k] for k in ('runner_sha256', 'package_project_sha256',
                           'artifacts_toml_sha256', 'wrapper_sha256', 'probe_script_sha256'))
    required_hashes.update(identity['shared_dependencies'].values())
    require(required_hashes <= set(prep['dependency_sha256'].values()), 'Dependencies detached from public build identity')
    require(digest(root/plan['identity_path']) == plan['identity_sha256'], 'Public identity file changed')
    require(json.loads((root/plan['identity_path']).read_text()) == identity, 'Committed identity representations disagree')
    return original


def _copies(directory, source, prep):
    copied = {}
    inodes = set()
    for name, expected in prep['source_files'].items():
        target = directory/name
        target.parent.mkdir(parents=True, exist_ok=True)
        require(not target.exists() and not target.is_symlink(), 'Preexisting copy target')
        shutil.copyfile(source/name, target)
        require(not target.is_symlink() and target.stat().st_nlink == 1, 'Copy is linked')
        identity = (target.stat().st_dev, target.stat().st_ino)
        original = (source/name).stat()
        require(identity != (original.st_dev, original.st_ino) and identity not in inodes, 'Copy aliases source or another copy')
        require(digest(target) == expected['sha256'] and target.stat().st_size == expected['bytes'], 'Copied bytes mismatch')
        inodes.add(identity)
        copied[name] = expected['sha256']
    # The source XML's relative pseudo_dir is ./pseudo; supply that layout.
    pseudo = directory/'pseudo/Mg.upf'
    pseudo.parent.mkdir()
    shutil.copyfile(source/(SAVE+'Mg.upf'), pseudo)
    require(pseudo.stat().st_nlink == 1 and not pseudo.is_symlink(), 'Controlled pseudo copy is linked')
    copied['pseudo/Mg.upf'] = digest(pseudo)
    require(copied['pseudo/Mg.upf'] == prep['source_files'][SAVE+'Mg.upf']['sha256'], 'Controlled pseudo bytes mismatch')
    return copied


def _warnings(stdout, stderr):
    streams = {}
    for name, text in [('stdout', stdout), ('stderr', stderr)]:
        streams[name] = {'lines': [line for line in text.splitlines() if re.search(r'IEEE_|warning|error in routine', line, re.I)],
                         'ieee_flags': sorted(set(re.findall(r'IEEE_[A-Z_]+', text)))}
    return streams


def run_slot(slot, root=ROOT):
    root = Path(root).resolve()
    parent = root/'.work/phase7e'
    run_id = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+str(slot)+'-'+uuid.uuid4().hex[:8]
    directory = parent/run_id
    claimed = False
    process_code = None
    state = {'schema_version': 1, 'run_id': run_id, 'slot': str(slot), 'execution_status': 'RUNNING',
             'postprocessing_status': 'NOT_RUN', 'parse_status': 'NOT_RUN', 'exit_code': 9, 'formal_call_count': 0}
    try:
        directory.mkdir(parents=True, exist_ok=False)
        write_json(directory/'result.json', state)
        require(slot in ('P2', 'P0'), 'Only P2 and P0 are authorized')
        claim_path = parent/(slot+'.claim.json')
        require(not claim_path.exists(), 'Slot already claimed; no numerical retry is permitted')
        if slot == 'P0':
            previous = json.loads((parent/'P2.claim.json').read_text())
            previous_id = previous['run_id']
            require(re.fullmatch(r'[A-Za-z0-9-]+', previous_id) is not None, 'Invalid predecessor run ID')
            terminal = json.loads((parent/previous_id/'result.json').read_text())
            require(terminal['run_id'] == previous_id and terminal['slot'] == 'P2'
                    and terminal['execution_status'] in ('PASS', 'FAIL') and terminal['formal_call_count'] == 1,
                    'P0 requires a completed P2 attempt')
        prep_path = parent/'preparation.json'
        prep = json.loads(prep_path.read_text())
        plan = json.loads((root/PLAN).read_text())
        source = validate_preparation(root, prep, plan, slot)
        spec = plan['slots'][slot]
        copied = _copies(directory, source, prep)
        shutil.copyfile(root/spec['input_path'], directory/'pp.in')
        require(digest(directory/'pp.in') == spec['input_sha256'], 'Working input copy mismatch')
        output = directory/spec['filplot']
        require(not output.exists() and not output.is_symlink(), 'Output exists before this run')
        env = dict(os.environ, **prep['environment'])
        command = [prep['launcher'], '-in', 'pp.in']
        receipt = {'schema_version': 1, 'run_id': run_id, 'slot': slot, 'source_run_id': G40_RUN,
                   'plan_sha256': digest(root/PLAN), 'preparation_sha256': digest(prep_path),
                   'preparation_commit': prep['preparation_commit'], 'execution_commit': _git(root, 'rev-parse', 'HEAD'),
                   'execution_source_sha256': {p: digest(root/p) for p in EXECUTION_SOURCES},
                   'input_sha256': spec['input_sha256'], 'source_files': prep['source_files'],
                   'copy_sha256_before': copied, 'environment': prep['environment'], 'command': command,
                   'qe_identity': plan['qe_identity'], 'output_absent_before': True,
                   'field_provenance': 'QE_PP_RECONSTRUCTION_BOUND_TO_HISTORICAL_G40'}
        write_json(directory/'preflight.json', receipt)
        state['formal_call_count'] = 1
        write_json(directory/'result.json', state)
        with claim_path.open('x') as stream:
            json.dump({'run_id': run_id, 'slot': slot, 'plan_sha256': receipt['plan_sha256']}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        claimed = True
        execution_error = None
        try:
            process_code = execute(command, directory, env)
        except (Exception, KeyboardInterrupt) as error:
            execution_error = error
        preservation = {'source_run_id': G40_RUN, 'source_changes': {}, 'copy_changes': {}}
        try:
            preservation['source_changes'] = _changed(prep['protected_sources']['G40']['sha256'], snapshot(source))
            after = {p: digest(directory/p) if (directory/p).is_file() and not (directory/p).is_symlink() else None for p in copied}
            preservation['copy_changes'] = _changed(copied, after)
            preservation['status'] = 'PASS' if not preservation['source_changes'] and not preservation['copy_changes'] else 'FAIL'
        except Exception as error:
            preservation.update(status='FAIL', error=str(error))
        write_json(directory/'source-preservation.json', preservation)
        require(preservation['status'] == 'PASS', 'Historical source or controlled copy changed')
        _dependencies(prep)
        if execution_error is not None:
            raise execution_error
        require(type(process_code) is int and process_code == 0, 'pp process returned nonzero: '+str(process_code))
        stdout = (directory/'qe.stdout').read_text()
        stderr = (directory/'qe.stderr').read_text()
        require(re.search(r'Program\s+POST-PROC\s+v\.7\.5\b', stdout), 'Missing native pp 7.5 banner')
        require('JOB DONE.' in stdout, 'Missing native pp completion')
        require(not re.search(r'Error in routine|MPI_ABORT|SIGSEGV', stdout+'\n'+stderr, re.I), 'Native fatal-error evidence')
        require(not re.search(r'Self-consistent Calculation|End of self-consistent calculation|iteration #', stdout, re.I), 'Unexpected SCF/eigensolve stage')
        require(output.is_file() and not output.is_symlink() and output.stat().st_nlink == 1, 'Native filplot missing or linked')
        parsed = parse_qe_filplot(output, expected_plot_num=spec['plot_num'], expected=plan['filplot_expected'])
        write_json(directory/'parsed-filplot.json', parsed)
        state = dict(schema_version=1, run_id=run_id, slot=slot, execution_status='PASS',
                     postprocessing_status='PASS', parse_status='PASS', exit_code=0,
                     process_exit_code=process_code, formal_call_count=1, source_preservation_status='PASS',
                     copied_files_preservation_status='PASS', input_sha256=spec['input_sha256'],
                     filplot_sha256=digest(output), parsed_sha256=digest(directory/'parsed-filplot.json'),
                     stdout_sha256=digest(directory/'qe.stdout'), stderr_sha256=digest(directory/'qe.stderr'),
                     source_run_id=G40_RUN, warnings=_warnings(stdout, stderr),
                     qe_local_potential_status='RECONSTRUCTED_BY_SAME_BUILD_PP_FROM_BOUND_G40' if slot == 'P2' else 'NOT_APPLICABLE',
                     field_provenance='QE_PP_RECONSTRUCTION_BOUND_TO_HISTORICAL_G40',
                     qe_historical_in_memory_vloc_status='NOT_EXTRACTED', qe_internal_tab_vloc_status='NOT_EXTRACTED')
        # All required artifacts already exist. This is the final fallible
        # operation in successful publication; no PASS is written earlier.
        write_json(directory/'result.json', state)
    except (Exception, KeyboardInterrupt) as error:
        state = {'schema_version': 1, 'run_id': run_id, 'slot': str(slot), 'execution_status': 'FAIL',
                 'postprocessing_status': 'INCOMPLETE_OR_FAILED' if claimed else 'NOT_RUN',
                 'parse_status': 'FAIL_OR_NOT_RUN', 'exit_code': 9, 'process_exit_code': process_code,
                 'formal_call_count': 1 if claimed else 0, 'error_type': type(error).__name__, 'reason': str(error)}
        try:
            write_json(directory/'result.json', state)
        except Exception as persist_error:
            # If atomic replacement fails but the existing file remains writable,
            # remove any possible PASS through an independently encoded fallback.
            try:
                with (directory/'result.json').open('w') as stream:
                    json.dump(state, stream, allow_nan=False)
                    stream.flush()
                    os.fsync(stream.fileno())
            except Exception:
                print('Result persistence failed; this run is not PASS: '+str(persist_error), file=sys.stderr)
            state['persistence_status'] = 'PRIMARY_WRITE_FAILED'
    print(json.dumps(dict(state, directory=str(directory)), allow_nan=False))
    return state['exit_code']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('slot', choices=['P2', 'P0'])
    args = parser.parse_args()
    raise SystemExit(run_slot(args.slot))
