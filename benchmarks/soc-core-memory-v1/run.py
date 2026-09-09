#!/usr/bin/env python3
"""Launch one registered static suite using the existing process/RSS recorder.

This is a Julia command adapter, not a new scientific solver or recorder. The
frozen executor's qe.stdout/qe.stderr names contain Julia output in these runs.
"""
import argparse
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from run_qe_soc import execute
from si_qe_reference_evidence import monitored_execute, ps_rows

BASE = 'c764311a5422b5c3cab5a7b78a02d420910c4e56'
PLAN = 'e4f16a51a0304f5e70f5ae038563d6760409c2c4'
BRANCH = 'codex/phase9a-soc-core-memory'
SUITES = ('REF-B0', 'REF-K4', 'CORE-B0', 'CORE-K4')
PREPARED = ('README.md', 'plan.json', 'sources.json', 'contract.json')
OPERATIONS = {f'{name}_{n}' for name in ('FR', 'component', 'full_H') for n in (1, 24, 30)} | {'density', 'nonlocal', 'energy', 'pipeline'}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def write(path, value):
    encoded = json.dumps(value, indent=2, allow_nan=False) + '\n'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(encoded)
    temporary.replace(path)


def read(path):
    def invalid(value):
        raise ValueError('Nonfinite JSON constant: ' + value)
    return json.loads(path.read_text(), parse_constant=invalid)


def resource_contract(resource, native):
    require(isinstance(resource, dict) and resource.get('status') == resource.get('owned_process_cleanup_status') == 'PASS', 'Resource observer or cleanup failed')
    require(type(native) is int and native == 0 and resource.get('native_exit_code') == native, 'Resource/native exit mismatch')
    require(type(resource.get('peak_aggregate_rss_bytes')) is int and 0 < resource['peak_aggregate_rss_bytes'] < 8 * 1024**3, 'Invalid sampled RSS')
    require(type(resource.get('nonempty_samples')) is int and resource['nonempty_samples'] > 0, 'Missing numerical RSS samples')


def worker_contract(worker, state, directory):
    require(isinstance(worker, dict) and type(worker.get('schema_version')) is int and worker['schema_version'] == 1, 'Unsupported worker schema')
    require(worker.get('phase') == '9A' and worker.get('backend') == ('LEGACY_REFERENCE' if state['suite'].startswith('REF-') else 'OWNED_CORE'), 'Wrong worker phase/backend')
    for key in ('suite', 'run_id', 'execution_commit'):
        require(worker.get(key) == state.get(key), 'Worker identity mismatch: ' + key)
    require(worker.get('base_commit') == BASE and worker.get('preparation_commit') == PLAN, 'Worker base/preparation mismatch')
    require(worker.get('overall_status') == worker.get('execution_status') == 'PASS' and worker.get('measurement_status') == 'COMPLETE', 'Incomplete or contradictory worker status')
    require(type(worker.get('exit_code')) is int and worker['exit_code'] == state['process_exit_code'] == 0, 'Worker/process exit mismatch')
    require(isinstance(worker.get('environment'), dict) and worker['environment'].get('status') == 'PASS', 'Worker environment mismatch')
    require(worker.get('parallelism') == {'julia': 1, 'blas': 1, 'fft': 1, 'mpi': 1}, 'Worker parallelism mismatch')
    require(all(type(v) is int for v in worker['parallelism'].values()), 'Worker parallelism needs integer counts')
    measurements = worker.get('measurements')
    require(isinstance(measurements, dict) and set(measurements) == OPERATIONS, 'Incomplete operation matrix')
    for name, item in measurements.items():
        require(isinstance(item, dict) and item.get('status') == 'PASS' and item.get('completed_samples') == item.get('requested_samples') == 5 and item.get('warmup_count') == 1, 'Incomplete sample set: ' + name)
        samples = item.get('samples')
        require(isinstance(samples, list) and len(samples) == 5 and [s.get('index') for s in samples] == [1, 2, 3, 4, 5], 'Missing/reordered sample: ' + name)
        for sample in [item.get('warmup'), *samples]:
            require(isinstance(sample, dict) and sample.get('status') == 'PASS', 'Failed warmup/sample: ' + name)
            for field in ('time_seconds', 'allocated_bytes', 'gc_seconds', 'compile_seconds', 'recompile_seconds'):
                require(type(sample.get(field)) in (int, float) and math.isfinite(sample[field]) and sample[field] >= 0, 'Invalid measurement: ' + name + '/' + field)
    unchanged = worker.get('input_unchanged')
    require(isinstance(unchanged, dict) and set(unchanged) == {'payload', 'rhs', 'checkpoint', 'original_result'} and all(v is True for v in unchanged.values()), 'Input preservation failed or missing')
    outputs = worker.get('outputs')
    require(isinstance(outputs, dict) and set(outputs) == OPERATIONS, 'Missing canonical numerical outputs')
    for record in [worker.get('canonical_inputs'), *outputs.values()]:
        require(isinstance(record, dict) and isinstance(record.get('path'), str) and Path(record['path']).name == record['path'], 'Unconfined canonical output')
        path = directory / record['path']
        require(not path.is_symlink() and path.stat().st_size == record.get('bytes') and sha(path) == record.get('sha256'), 'Canonical payload bytes differ')


def prior_contract(record, directory):
    require(record.get('run_id') == directory.name and record.get('overall_status') == 'PASS' and record.get('exit_code') == 0 and record.get('worker_started') is True, 'Prior suite not a successful bound run')
    require(sha(directory / 'worker-result.json') == record.get('worker_result_sha256'), 'Prior worker receipt bytes differ')
    native = read(directory / 'process-exit.json')
    require(native.get('interrupted') is False and native.get('exit_code') == record.get('process_exit_code'), 'Prior native exit differs')
    resource = read(directory / 'resource.json')
    require(resource == record.get('resource'), 'Prior resource receipt differs')
    resource_contract(resource, record['process_exit_code'])
    worker_contract(read(directory / 'worker-result.json'), record, directory)


def preparation(root):
    directory = root / 'benchmarks/soc-core-memory-v1'
    for name in PREPARED:
        path = directory / name
        blob = subprocess.check_output(['git', '-C', str(root), 'show', PLAN + ':' + str(path.relative_to(root))])
        require(path.read_bytes() == blob, 'Frozen preparation bytes changed: ' + name)
    sources = json.loads((directory / 'sources.json').read_text())
    for rel, identity in sources['frozen_inputs_and_history'].items():
        path = root / rel
        require(not path.is_symlink() and path.stat().st_size == identity['bytes'] and sha(path) == identity['sha256'], 'Frozen source changed: ' + rel)
    return sources


def run(suite, julia, root=ROOT):
    root = root.resolve()
    area = root / '.work/phase9a/static'
    run_id = suite + '-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8]
    directory = area / run_id
    state = dict(schema_version=1, suite=suite, run_id=run_id, overall_status='INCOMPLETE',
                 exit_code=9, process_exit_code=None, worker_started=False)
    lock = area / 'active.json'
    owns_lock = False
    try:
        directory.mkdir(parents=True, exist_ok=False)
        write(directory / 'result.json', state)
        require(suite in SUITES, 'Unregistered suite')
        require(git(root, 'branch', '--show-current') == BRANCH, 'Wrong branch')
        require(not git(root, 'status', '--porcelain', '--untracked-files=all'), 'Formal execution requires a clean checkout')
        execution = git(root, 'rev-parse', 'HEAD')
        require(subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', BASE, execution]).returncode == 0, 'Accepted base missing')
        sources = preparation(root)
        state['execution_commit'] = execution
        prior = [(read(p), p.parent) for p in area.glob('*/result.json') if p.parent != directory]
        require(not any(r.get('suite') == suite and r.get('worker_started') for r, _ in prior), 'This formal static suite already started; inspect its retained record before any further action')
        for previous in SUITES[:SUITES.index(suite)]:
            records = [(r, d) for r, d in prior if r.get('suite') == previous and r.get('worker_started')]
            require(len(records) == 1, 'Prior static suite has no unique PASS: ' + previous)
            prior_contract(*records[0])
            if previous.startswith(suite.split('-')[0]):
                require(records[0][0]['execution_commit'] == execution, 'Paired static suites require the same execution commit')
        code_root = root / '.work/phase9a/reference-tree' if suite.startswith('REF-') else root
        if suite.startswith('REF-'):
            require(git(code_root, 'rev-parse', 'HEAD') == BASE and not git(code_root, 'status', '--porcelain', '--untracked-files=all'), 'Reference checkout differs from exact clean base')
            for rel, identity in sources['reference_implementation']['files'].items():
                require(sha(code_root / rel) == identity['sha256'], 'Reference implementation bytes differ: ' + rel)
        checkpoint = root / sources['historical_endpoints'][suite.split('-')[1]]['directory'] / 'final.bin'
        free = shutil.disk_usage(area).free
        require(free >= 10 * 1024**3 + 20 * checkpoint.stat().st_size, 'Disk reserve insufficient')
        ps_rows()  # Refuse before starting when the real RSS observer is unavailable.
        with lock.open('x') as stream:
            json.dump(dict(run_id=run_id, owner_pid=os.getpid()), stream)
        owns_lock = True
        env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
                   VECLIB_MAXIMUM_THREADS='1', JULIA_NUM_THREADS='1', JULIA_PKG_OFFLINE='true')
        command = [str(Path(julia).absolute()), '--startup-file=no', '--color=no', '--threads=1',
                   '--project=' + str(root / 'environment/workbench'),
                   str(root / 'benchmarks/soc-core-memory-v1/measure.jl'),
                   '--root', str(root), '--code-root', str(code_root), '--suite', suite, '--output', str(directory)]
        write(directory / 'preflight.json', dict(schema_version=1, run_id=run_id, suite=suite,
            execution_commit=execution, code_commit=git(code_root, 'rev-parse', 'HEAD'),
            free_disk_bytes=free, disk_extra_reserve_bytes=20 * checkpoint.stat().st_size,
            command=command, thread_environment={k: env[k] for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'JULIA_NUM_THREADS')},
            tooling_sha256={str(p.relative_to(root)): sha(p) for p in (root / 'benchmarks/soc-core-memory-v1').glob('*') if p.is_file()},
            log_labels='qe.stdout and qe.stderr are inherited generic executor names; actual command is Julia, no QE execution'))
        state['worker_started'] = True
        write(directory / 'result.json', state)
        code, resource = monitored_execute(execute, command, directory, env)
        state.update(process_exit_code=code, resource=resource)
        require(code == 0, 'Julia worker returned nonzero: ' + str(code))
        resource_contract(resource, code)
        worker_contract(read(directory / 'worker-result.json'), state, directory)
        preparation(root)
        if suite.startswith('REF-'):
            require(git(code_root, 'rev-parse', 'HEAD') == BASE and not git(code_root, 'status', '--porcelain', '--untracked-files=all'), 'Reference checkout changed during suite')
            for rel, identity in sources['reference_implementation']['files'].items():
                require(sha(code_root / rel) == identity['sha256'], 'Reference implementation changed during suite: ' + rel)
        require(git(root, 'rev-parse', 'HEAD') == execution and not git(root, 'status', '--porcelain', '--untracked-files=all'), 'Execution checkout changed during suite')
        state.update(overall_status='PASS', exit_code=0, worker_result_sha256=sha(directory / 'worker-result.json'))
        prior_contract(state, directory)  # Validate persisted native/resource bytes before publishing PASS.
        write(directory / 'result.json', state)
    except (Exception, KeyboardInterrupt) as error:
        state.update(overall_status='FAIL', exit_code=9, failure_type=type(error).__name__, reason=str(error))
        try:
            native = read(directory / 'process-exit.json')
            if type(native.get('exit_code')) is int:
                state['process_exit_code'] = native['exit_code']
        except (OSError, ValueError, TypeError):
            pass
        try:
            write(directory / 'result.json', state)
        except OSError:
            print('Persistence failed; this current run is not PASS.', file=sys.stderr)
    finally:
        if owns_lock:
            try:
                resource_path = directory / 'resource.json'
                cleanup = read(resource_path).get('owned_process_cleanup_status') if resource_path.exists() else None
                if cleanup == 'PASS' or not (directory / 'process-start.json').exists():
                    require(read(lock).get('run_id') == run_id, 'Execution lock ownership changed')
                    lock.unlink()
            except (OSError, ValueError, TypeError) as error:
                state.update(overall_status='FAIL', exit_code=9, cleanup_error=str(error))
                try:
                    write(directory / 'result.json', state)
                except OSError:
                    print('Failure persistence failed; current result cannot be relied upon.', file=sys.stderr)
    print(json.dumps(dict(state, directory=str(directory.relative_to(root))), allow_nan=False))
    return state['exit_code']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('suite', choices=SUITES)
    parser.add_argument('--julia', required=True, help='Existing frozen Julia executable; no installation')
    arguments = parser.parse_args()
    sys.exit(run(arguments.suite, arguments.julia))
