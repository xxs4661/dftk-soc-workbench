#!/usr/bin/env python3
"""One-shot extra Si slots; reuse the existing process-group executor and sampler.

The inherited qe.stdout/qe.stderr filenames hold Julia output, never QE runs.
"""
import argparse
from contextlib import contextmanager
import datetime
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import types
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))


def module(root, relative, name):
    spec = importlib.util.spec_from_file_location(name, Path(root) / relative)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


control = module(ROOT, 'benchmarks/soc-extra-v1/control.py', 'soc_extra_control')
require, read, sha = control.require, control.read, control.sha
ACTIONS = control.ACTIONS
PILOT = 'PILOT_COMPLETED_NOT_SCF_CONVERGED'


def write(path, value, *, exclusive=False):
    encoded = json.dumps(value, indent=2, allow_nan=False) + '\n'
    if exclusive:
        with Path(path).open('x') as stream:
            stream.write(encoded)
        return
    temporary = Path(path).with_name(Path(path).name + '.tmp-' + uuid.uuid4().hex)
    try:
        temporary.write_text(encoded); temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def finite_tree(value):
    if type(value) is float:
        require(math.isfinite(value), 'Nonfinite worker number')
    elif isinstance(value, dict):
        for v in value.values(): finite_tree(v)
    elif isinstance(value, list):
        for v in value: finite_tree(v)


def worker_contract(value, code, state, auth, *, check=False):
    require(isinstance(value, dict), 'Worker result must be an object')
    finite_tree(value)
    require(type(value.get('schema_version')) is int and value['schema_version'] == 1, 'Unsupported worker schema')
    require(type(code) is int and type(value.get('exit_code')) is int and value['exit_code'] == code,
            'Worker/process exit mismatch')
    expected = {'phase': '9A-extra', 'backend': 'soc-core', 'case': 'soc-extra-v1/' + auth['profile'],
                'extra_profile': auth['profile'], 'action': state['action'], 'run_id': state['worker_directory'],
                'execution_commit': auth['execution_commit'], 'contract_sha256': auth['contract_sha256']}
    for key, item in expected.items():
        require(value.get(key) == item, 'Worker identity mismatch: ' + key)
    status = value.get('execution_status')
    if code:
        require(status in ('FAIL', 'RESOURCE_LIMIT', 'RESOURCE_BLOCKED') and
                isinstance(value.get('reason'), str) and value['reason'], 'Failure status/exit/reason contradiction')
        return
    require(isinstance(value.get('environment'), dict) and value['environment'].get('status') == 'PASS',
            'Environment identity not successful')
    require(value.get('case_sha256') == auth['case_sha256'] and
            value.get('executed_source_sha256') == auth['executed_source_sha256'], 'Worker executed different sources/case')
    if check:
        require(status == 'CHECK_ONLY_PASS' and value.get('check_only') is True and
                value.get('context_constructed') is False and value.get('numerical_execution_status') == 'NOT_RUN',
                'Entry check must not build a context or claim a numerical slot')
        return
    require(status == (PILOT if state['action'] == 'X-K6-PILOT' else 'PASS'), 'Wrong numerical action/status')
    require(value.get('parallelism') == {'julia': 1, 'blas': 1, 'fft': 1, 'mpi': 1} and
            all(type(v) is int for v in value['parallelism'].values()), 'Incorrect parallelism')
    require(isinstance(value.get('input'), dict) and value['input'].get('element') == 'Si' and
            value['input'].get('nlcc_present') is True and value['input'].get('sha256') ==
            'cc91a6be43c3c89daf6c34410096e8d870f25152dbfb513bcf01afa5ab53eabf', 'Wrong Si/NLCC source')
    require(isinstance(value.get('grid'), dict) and value['grid'].get('status') == 'PASS', 'Missing geometry validation')
    require(value.get('runtime_closed') is True and value.get('runtime_dispatch_status') == 'PASS', 'Owned runtime not exercised/closed')
    runtime, closed = value.get('runtime'), value.get('runtime_after_close')
    require(isinstance(runtime, dict) and runtime.get('backend') == 'soc-core' and runtime.get('max_rhs') == 30,
            'Missing actual owned runtime')
    counts = runtime.get('counters')
    require(isinstance(counts, dict) and all(type(counts.get(k)) is int and counts[k] > 0 for k in
            ('fr_mul_calls', 'component_mul_calls', 'full_mul_calls')), 'Core dispatch counters missing')
    require(isinstance(closed, dict) and closed.get('closed') is True and closed.get('owned_source_entries') == 0 and
            closed.get('workspace_released') is True, 'Owned storage release unconfirmed')
    if state['action'] == 'X-K6-PILOT':
        pilot = value.get('pilot')
        require(isinstance(pilot, dict) and type(pilot.get('completed_maps')) is int and
                1 <= pilot['completed_maps'] <= 2, 'Pilot must complete at most two real maps')
        require(isinstance(pilot.get('lifecycle'), dict) and isinstance(pilot.get('geometry'), dict),
                'Pilot needs lifecycle/actual geometry observations')
        require(value.get('final') is None, 'Pilot cannot publish a converged final endpoint')
    elif state['action'].endswith('-SCF'):
        final = value.get('final')
        require(isinstance(final, dict) and type(final.get('map_count')) is int and final['map_count'] > 1,
                'Missing final SCF closure')
        require(final.get('closure_status') == 'PASS', 'Final additional closure map not certified')
        require(isinstance(final.get('diagnostics'), dict) and final['diagnostics'].get('target_states') == 24,
                'SCF must keep 24 physical target states')
        nk = 8 if auth['profile'] == 'B0' else 216
        for field in ('eigenvalues_ha', 'occupations'):
            require(isinstance(final.get(field), list) and len(final[field]) == nk and
                    all(isinstance(row, list) and len(row) == 24 for row in final[field]), 'SCF point/band count differs: ' + field)
        require(isinstance(value.get('checkpoint_sha256'), str) and len(value['checkpoint_sha256']) == 64 and
                isinstance(final.get('n_out_sha256'), str) and len(final['n_out_sha256']) == 64, 'Final density/checkpoint unbound')
    else:
        spectrum = value.get('spectrum')
        require(isinstance(spectrum, dict) and spectrum.get('execution_status') == 'PASS' and
                spectrum.get('physical_operator') == 'full_soc' and spectrum.get('process_exit_code') == 0,
                'Gamma full-SOC spectrum missing')
        points = spectrum.get('kpoints')
        require(isinstance(points, list) and len(points) == 1 and points[0].get('coordinate_fractional') == [0., 0., 0.] and
                points[0].get('weight_spatial') == 1, 'Only own-density Gamma is authorized')
        require(all(isinstance(points[0].get(k), list) and len(points[0][k]) == 24 for k in
                    ('eigenvalues_ha', 'residuals_ha')), 'Gamma requires all 24 target states/residuals')
        require(spectrum.get('occupations_use') == 'DIAGNOSTIC_ONLY_NOT_DENSITY_FEEDBACK' and
                spectrum.get('temperature_ha') == .001, 'Gamma occupation contract differs')
        require(isinstance(value.get('time_reversal'), dict) and value['time_reversal'].get('status') == 'PASS',
                'Gamma operator time reversal gate missing')
        for key in ('source_scf_run_id', 'density_source_sha256'):
            require(isinstance(value.get(key), str) and value[key] and spectrum.get(key) == value[key], 'Gamma parent binding missing: ' + key)


def resource_contract(value, native):
    require(isinstance(value, dict) and value.get('status') == 'PASS' and
            value.get('owned_process_cleanup_status') == 'PASS', 'Resource monitor or cleanup failed')
    require(value.get('native_exit_code') == native and type(native) is int, 'Resource/native exit differs')
    require(type(value.get('peak_aggregate_rss_bytes')) is int and 0 < value['peak_aggregate_rss_bytes'] < 8 * 1024**3 and
            type(value.get('nonempty_samples')) is int and value['nonempty_samples'] > 0, 'Missing/unsafe observed RSS')


def checked_run(root, directory, action, execution, *, auth=None):
    root = Path(root).resolve(); original = Path(directory); directory = original.resolve()
    area = root / '.work/phase9a-extra/runs'
    require(area == directory.parent and not original.is_symlink(), 'BLOCKED_PARENT: run outside extra area')
    rec = read(directory / 'result.json')
    require(rec.get('run_id') == directory.name and rec.get('action') == action and rec.get('execution_commit') == execution and
            rec.get('execution_status') == (PILOT if action == 'X-K6-PILOT' else 'PASS') and rec.get('exit_code') == 0 and
            rec.get('worker_started') is True, 'BLOCKED_PARENT: prior slot is not a successful current execution')
    own_auth = control.verify_contract(root, root / rec['contract_path'], execution, rec['profile'])
    if auth is not None:
        require(auth['contract_sha256'] == own_auth['contract_sha256'], 'BLOCKED_PARENT: parent contract differs')
    worker = directory / rec['worker_directory']
    require(worker.parent == directory and not worker.is_symlink() and sha(worker / 'result.json') == rec['worker_result_sha256'],
            'BLOCKED_PARENT: worker bytes changed')
    value = read(worker / 'result.json'); worker_contract(value, rec['native_exit_code'], rec, own_auth)
    native = read(directory / 'process-exit.json')
    require(native.get('exit_code') == rec['native_exit_code'] == 0 and native.get('interrupted') is False, 'BLOCKED_PARENT: native receipt differs')
    require(read(directory / 'resource.json') == rec['resource'], 'BLOCKED_PARENT: resource bytes changed')
    resource_contract(rec['resource'], rec['native_exit_code'])
    if action.endswith('-SCF'):
        require(sha(worker / 'final.bin') == value['checkpoint_sha256'], 'BLOCKED_PARENT: final checkpoint changed')
    return rec, value, worker


def prior(root, action, execution, *, auth=None):
    slot = read(root / '.work/phase9a-extra/slots' / (action + '.json'))
    require(slot.get('action') == action and isinstance(slot.get('run_id'), str), 'Prior slot identity differs')
    return checked_run(root, root / '.work/phase9a-extra/runs' / slot['run_id'], action, execution, auth=auth)


@contextmanager
def global_guard(root, run_id):
    """Use old lock names too; keep every old reservation and stale lock intact."""
    paths = [root / p for p in ('.work/phase9a-extra/active.json', '.work/phase9a/endpoints/active.json',
                                '.work/phase9a/static/active.json')]
    acquired = []
    try:
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            write(path, {'run_id': run_id, 'owner_pid': os.getpid(), 'experiment': 'soc-extra-v1'}, exclusive=True)
            acquired.append(path)
        yield acquired
    finally:
        # The caller removes locks only after confirmed owned-process cleanup.
        if len(acquired) < len(paths):
            for path in reversed(acquired):
                require(read(path).get('run_id') == run_id, 'Lock ownership changed')
                path.unlink()


def monitored(command, directory, env, resources, remaining_growth):
    """Reuse frozen session/RSS/reaping logic, adding an isolated sampling hook."""
    tool = module(ROOT, 'benchmarks/soc-core-memory-v1/run.py', 'soc_extra_existing_runner')
    sampler = tool.monitored_execute
    original_rows = sampler.__globals__['ps_rows']
    last_pressure = [0., None]
    policy_log = directory / 'resource-policy.jsonl'
    def observe():
        rows = original_rows()
        now = time.monotonic()
        if now - last_pressure[0] >= 2:
            last_pressure[:] = [now, resources.host_pressure()]
        pressure = last_pressure[1]
        marker = directory / 'process-start.json'
        total = 0
        if marker.is_file():
            try:
                leader = read(marker)['pid']
                total = sum(row['rss_kib'] for row in sampler.__globals__['owned_rows'](rows, leader)) * 1024
            except json.JSONDecodeError:
                return rows  # Frozen executor's short start marker can be mid-write.
        decision = resources.monitor_decision(total, remaining_growth_bytes=remaining_growth, pressure=pressure)
        if decision['status'] != 'CONTINUE':
            with policy_log.open('a') as stream:
                stream.write(json.dumps(dict(decision, observed_rss_bytes=total, monotonic_seconds=now), allow_nan=False) + '\n')
        if decision['status'] in ('RESOURCE_LIMIT', 'MONITORING_UNAVAILABLE'):
            raise ValueError('RESOURCE_LIMIT: ' + json.dumps(decision))
        if decision['status'] == 'STOP_AT_SAFE_BOUNDARY':
            write(Path(env['SOC_EXTRA_STOP_FILE']), dict(decision, observed_rss_bytes=total))
        return rows
    namespace = dict(sampler.__globals__, ps_rows=observe)
    observer = types.FunctionType(sampler.__code__, namespace, sampler.__name__, sampler.__defaults__, sampler.__closure__)
    code, resource = observer(tool.execute, command, directory, env)
    resource['extra_policy'] = {'warning_bytes': 7 * 1024**3, 'stop_bytes': 8 * 1024**3,
                              'remaining_growth_bytes': remaining_growth,
                              'host_pressure_sampling_seconds': 2,
                              'safe_boundary_stop_requested': Path(env['SOC_EXTRA_STOP_FILE']).exists()}
    write(directory / 'resource.json', resource)
    return code, resource


def prerequisites(root, action, auth, resources):
    host = resources.host_preflight(root)
    require(host.get('status') == 'ELIGIBLE', 'RESOURCE_BLOCKED: host prerequisites: ' + json.dumps(host))
    if action.startswith('X-B0'):
        require(auth['numerical_change_requires_B0'], 'Unchanged numerical path does not authorize another B0')
        return {'status': 'ELIGIBLE', 'host': host, 'remaining_growth_bytes': 1024**3}
    if auth['numerical_change_requires_B0']:
        scf, _, _ = prior(root, 'X-B0-SCF', auth['execution_commit'])
        gamma, _, _ = prior(root, 'X-B0-GAMMA', auth['execution_commit'])
        gate = read(root / '.work/phase9a-extra/b0-regression.json')
        require(gate.get('schema_version') == 1 and gate.get('execution_commit') == auth['execution_commit'] and
                gate.get('status') == 'PASS' and gate.get('scf_receipt_sha256') == sha(root / '.work/phase9a-extra/runs' / scf['run_id'] / 'result.json') and
                gate.get('gamma_receipt_sha256') == sha(root / '.work/phase9a-extra/runs' / gamma['run_id'] / 'result.json'), 'BLOCKED_PARENT: own B0 numerical regression not passed')
    if action == 'X-K6-PILOT':
        decision = resources.pilot_eligibility(root, host=host)
        require(decision.get('status') == 'PILOT_ELIGIBLE', 'RESOURCE_BLOCKED: pilot initial screen: ' + json.dumps(decision))
    else:
        rec, worker, _ = prior(root, 'X-K6-PILOT', auth['execution_commit'], auth=auth)
        pilot = dict(worker['pilot'], status=PILOT, native_exit_code=rec['native_exit_code'], recorder_exit_code=rec['exit_code'], resource=rec['resource'])
        decision = resources.formal_admission(root, pilot, host=host)
        require(decision.get('status') == 'PROVISIONAL_GO_WITH_MONITORING', 'RESOURCE_BLOCKED: full K6 admission: ' + json.dumps(decision))
    return {'status': 'ELIGIBLE', 'host': host, 'decision': decision,
            'remaining_growth_bytes': decision.get('remaining_growth_bytes', 1024**3)}


def launch(action, *, profile, contract, execution_commit, directory=None, parent=None, check_entry=False, root=ROOT, julia='julia'):
    root = Path(root).resolve(); area = root / '.work/phase9a-extra'
    run_id = action + ('-ENTRY-' if check_entry else '-') + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8]
    directory = Path(directory).resolve() if directory else area / 'runs' / run_id
    require(directory.parent == area / 'runs', 'Run directory must be a direct child of extra/runs')
    require(not directory.exists(), 'Existing run is never overwritten')
    directory.mkdir(parents=True)
    state = {'schema_version': 1, 'phase': '9A-extra', 'action': action, 'profile': profile,
             'run_id': directory.name, 'worker_directory': directory.name + '-dftk', 'execution_commit': execution_commit,
             'execution_status': 'INCOMPLETE', 'exit_code': 9, 'native_exit_code': None,
             'worker_started': False, 'check_only': check_entry, 'formal_slot_reserved': False}
    locks = []; auth = None
    try:
        write(directory / 'result.json', state)
        require(action in ACTIONS and ('-' + profile + '-') in action, 'Unregistered action/profile')
        require((parent is not None) == action.endswith('-GAMMA') or check_entry and parent is None, 'BLOCKED_PARENT: wrong parent arguments')
        auth = control.verify_contract(root, contract, execution_commit, profile)
        state.update(contract_sha256=auth['contract_sha256'], contract_path=auth['contract_path'], case_sha256=auth['case_sha256'])
        parent_worker = None
        if parent is not None:
            _, parent_value, parent_worker = checked_run(root, parent, action.replace('-GAMMA', '-SCF'), execution_commit, auth=auth)
            state['parent_result_sha256'] = sha(parent_worker / 'result.json')
            state['parent_checkpoint_sha256'] = sha(parent_worker / 'final.bin')
        depot = os.environ.get('JULIA_DEPOT_PATH')
        require(depot and all(p and Path(p).is_dir() for p in depot.split(os.pathsep)), 'Select the existing frozen Julia cache explicitly')
        executable = shutil.which(julia)
        require(executable, 'Existing Julia executable unavailable')
        resources = module(root, 'benchmarks/soc-extra-v1/resources.py', 'soc_extra_resources')
        with global_guard(root, directory.name) as acquired:
            locks = acquired
            if not check_entry:
                eligibility = prerequisites(root, action, auth, resources)
                state['admission'] = eligibility
                slot = area / 'slots' / (action + '.json'); slot.parent.mkdir(parents=True, exist_ok=True)
                write(slot, dict(run_id=directory.name, action=action, profile=profile, execution_commit=execution_commit,
                                 contract_sha256=auth['contract_sha256'], worker_directory=state['worker_directory'],
                                 numerical_authorization_status='ELIGIBLE', admission=eligibility), exclusive=True)
                state['formal_slot_reserved'] = True
            env = dict(os.environ, JULIA_LOAD_PATH='@:@stdlib', JULIA_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                       OMP_NUM_THREADS='1', JULIA_PKG_OFFLINE='true', SOC_CORE_PYTHON=sys.executable,
                       SOC_EXTRA_PYTHON=sys.executable, SOC_EXTRA_RUN_ID=directory.name,
                       SOC_EXTRA_WORKER_DIRECTORY=state['worker_directory'], SOC_EXTRA_STOP_FILE=str(directory / 'safe-boundary-stop.json'))
            if not check_entry: env['SOC_EXTRA_SLOT_RECEIPT'] = str(slot)
            command = [executable, '--startup-file=no', '--color=no', '--project=' + str(root / 'environment/workbench'),
                       str(root / 'scripts/run_si_soc.jl'), action, str(directory / state['worker_directory'])]
            if parent_worker is not None: command.append(str(parent_worker))
            command += ['--extra-profile', profile, '--extra-contract', str(Path(contract).resolve())]
            if check_entry: command.append('--check-entry')
            state['command'] = command; write(directory / 'result.json', state)
            code, resource = monitored(command, directory, env, resources, 1024**3 if check_entry else eligibility['remaining_growth_bytes'])
            state.update(native_exit_code=code, resource=resource, worker_started=not check_entry and (directory / 'process-start.json').exists())
            resource_contract(resource, code)
            result_path = directory / state['worker_directory'] / 'result.json'
            value = read(result_path); worker_contract(value, code, state, auth, check=check_entry)
            require(control.verify_contract(root, contract, execution_commit, profile) == auth, 'Execution identity changed during worker')
            if parent_worker is not None:
                require(sha(parent_worker / 'result.json') == state['parent_result_sha256'] and sha(parent_worker / 'final.bin') == state['parent_checkpoint_sha256'], 'Parent changed during Gamma')
                require(value.get('parent_result_sha256') == state['parent_result_sha256'] and value.get('parent_checkpoint_sha256') == state['parent_checkpoint_sha256'], 'Gamma worker did not bind its actual parent')
            state.update(execution_status=value['execution_status'], exit_code=code, worker_result_sha256=sha(result_path))
            if code: state['reason'] = value['reason']
    except BaseException as error:
        state.update(execution_status='RESOURCE_BLOCKED' if 'RESOURCE_' in str(error) else 'BLOCKED_PARENT' if 'BLOCKED_PARENT' in str(error) else 'FAIL',
                     exit_code=9, reason=type(error).__name__ + ': ' + str(error))
        for name, key in [('process-exit.json', 'native_process'), ('resource.json', 'resource')]:
            try: state[key] = read(directory / name)
            except (OSError, ValueError): pass
        if isinstance(state.get('native_process'), dict): state['native_exit_code'] = state['native_process'].get('exit_code')
        state['worker_started'] = not check_entry and (directory / 'process-start.json').exists()
    finally:
        cleanup = state.get('resource', {}).get('owned_process_cleanup_status')
        if cleanup == 'PASS' or not (directory / 'process-start.json').exists():
            for lock in reversed(locks):
                try:
                    require(read(lock).get('run_id') == directory.name, 'Global lock owner changed'); lock.unlink()
                except (OSError, ValueError) as error:
                    state.update(execution_status='FAIL', exit_code=9, cleanup_error=str(error))
        state['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try: write(directory / 'result.json', state)
        except BaseException as error:
            print('PERSISTENCE FAILURE; current execution is not PASS: ' + str(error), file=sys.stderr)
            print(json.dumps(dict(state, execution_status='FAIL', exit_code=9), allow_nan=False), file=sys.stderr)
            return 9
    print(json.dumps({k: state.get(k) for k in ('run_id', 'action', 'execution_status', 'exit_code', 'native_exit_code', 'reason')}, allow_nan=False))
    return state['exit_code'] if 0 <= state['exit_code'] <= 255 else 9


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=ACTIONS); parser.add_argument('directory', nargs='?')
    parser.add_argument('--extra-profile', required=True, choices=control.PROFILES)
    parser.add_argument('--extra-contract', required=True); parser.add_argument('--execution-commit', required=True)
    parser.add_argument('--parent'); parser.add_argument('--check-entry', action='store_true')
    parser.add_argument('--julia', default='julia')
    args = parser.parse_args(argv)
    try:
        return launch(args.action, profile=args.extra_profile, contract=args.extra_contract, execution_commit=args.execution_commit,
                      directory=args.directory, parent=args.parent, check_entry=args.check_entry, julia=args.julia)
    except (OSError, ValueError) as error:
        print('Extra recorder rejected before directory creation: ' + str(error), file=sys.stderr)
        return 9


if __name__ == '__main__':
    sys.exit(main())
