"""Five registered static validation slots; reuse the existing process supervisor.

This adapter authenticates inputs and source trees. It performs no Julia setup,
SCF, density map, eigenvalue or occupation calculation itself. A successful
worker is a static validation experiment, never a converged physical endpoint.
"""
import argparse
import contextlib
import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
EXPERIMENT = 'soc-validation-local-v1'
TASKS = ('DIAG-S', 'DIAG-F', 'BENCH-S', 'BENCH-F', 'BENCH-C')
SUCCESS = 'STATIC_VALIDATION_COMPLETED_NOT_SCF'
SETUP = 'STATIC_CONTEXT_SETUP_NOT_SCF'
BRANCH = 'codex/phase9a-validation-local-probe'
GIB = 1024**3
CURRENT = None


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


ROUTE = module(ROOT/'benchmarks/soc-timing-v1/route.py', 'local_probe_source_helpers')
SHARED = module(ROOT/'benchmarks/soc-timing-v1/run.py', 'local_probe_lock_helpers')
CONTROL = module(ROOT/'benchmarks/soc-timing-v1/control.py', 'local_probe_registered_control')
# Registration is private to this module. The historic control module and all
# old task/source/slot contracts retain their original bytes and semantics.
CONTROL.TASKS = {task: 600 for task in TASKS}
CONTROL.BOUNDARY_TASKS = {}
require, sha = ROUTE.require, ROUTE.sha


def load_json(path):
    return json.loads(Path(path).read_text())


def registration(root):
    c = load_json(root/'benchmarks/soc-validation-local-v1/contract.json')
    fixed = dict(schema_version=1, experiment=EXPERIMENT, slots=list(TASKS),
                 process_limit_seconds=600, cumulative_seconds=1800,
                 minimum_remaining_start_seconds=300, limit_bytes=8*GIB,
                 warning_bytes=7*GIB, remaining_growth_bytes=2*GIB,
                 escalation_seconds=[120,10,5], warmups=2, samples=5, maps=0,
                 static_status=SUCCESS, setup_status=SETUP)
    for key, value in fixed.items():
        require(type(c.get(key)) is type(value) and c[key] == value,
                'Static registration differs: '+key)
    return c


def specification(root, task, execution):
    require(task in TASKS, 'Unregistered static task')
    c = registration(root)
    role = task[-1]
    if role in ('S', 'F'):
        source = c['R' if role == 'S' else 'B']
        strategy = c['source_policy'][role]
        require(strategy == ('strict' if role == 'S' else 'single_validation_v1'),
                'Historical validation policy changed')
    else:
        selection = root/'benchmarks/soc-validation-local-v1/selection.json'
        require(selection.is_file(), 'BENCH-C blocked: no committed candidate selection')
        chosen = load_json(selection)
        require(chosen.get('status') == 'CANDIDATE_SELECTED' and
                chosen.get('experiment') == EXPERIMENT, 'No selected candidate')
        strategy = chosen.get('policy')
        require(type(strategy) is str and strategy not in ('strict', 'single_validation_v1')
                and strategy.isidentifier(), 'Candidate must use a distinct explicit strategy')
        ROUTE.exact_file(root, execution, str(selection.relative_to(root)))
        source = execution
    return dict(role=role, strategy=strategy, validation_policy=strategy, source_commit=source,
                mode='diagnostic' if task.startswith('DIAG-') else 'benchmark')


def adapter_sources(root, execution):
    names = ROUTE.git(root, 'ls-tree', '-r', '--name-only', execution).decode().splitlines()
    selected = {p for p in names if p.startswith('benchmarks/soc-validation-local-v1/')}
    selected |= {'benchmarks/soc-timing-v1/control.py', 'benchmarks/soc-timing-v1/control.jl',
                 'benchmarks/soc-timing-v1/route.py', 'benchmarks/soc-timing-v1/run.py',
                 'benchmarks/soc-timing-v1/admission.py', 'prototypes/diagnostics.jl',
                 'scripts/si_qe_reference_evidence.py', 'scripts/run_qe_soc.py',
                 'scripts/run_scalar_baseline.py', 'scripts/compare_scalar_baseline.py',
                 'scripts/parse_qe_baseline.py', 'benchmarks/soc-extra-v1/resources.py',
                 'results/soc-core-memory/memory-budget.json'}
    return {p: ROUTE.exact_file(root, execution, p) for p in sorted(selected)}


def prepare_route(root, numerical_root, task, outdir, execution, *, check=False):
    root, numerical_root = Path(root).resolve(), Path(numerical_root).resolve()
    spec = specification(root, task, execution)
    if task.startswith('BENCH-'):
        benchmark_gate(root,execution)
    ROUTE.tree_identity(root, execution)
    ROUTE.tree_identity(numerical_root, spec['source_commit'])
    require((root == numerical_root) == (spec['role'] == 'C'),
            'S/F require independent exact source trees; C requires the execution tree')
    fixture_path = root/'benchmarks/soc-validation-local-v1/fixture.json'
    fixture = load_json(fixture_path)
    case = fixture['case']['path']
    sources = ROUTE.source_files(numerical_root, spec['source_commit'], case)
    require(sources[case] == fixture['case']['sha256'], 'Physical case bytes changed')
    c = registration(root)
    if spec['role'] in ('S', 'F'):
        identity = fixture['implementations'][spec['role']]
        require(identity['commit'] == spec['source_commit'] and identity['policy'] == spec['strategy'],
                'Frozen implementation identity differs')
        for name, digest in identity['files'].items():
            require(sources.get(name) == digest, 'Frozen validation implementation changed: '+name)
            if spec['role'] == 'F':
                require(hashlib.sha256(ROUTE.git(root, 'show', c['E_old']+':'+name)).hexdigest() == digest,
                        'F no longer matches the original failed execution')
    pseudo = fixture['pseudopotential']
    require(sources[pseudo['source']] == pseudo['source_sha256'], 'Pseudopotential source changed')
    upf = numerical_root/pseudo['local_path']
    require(upf.stat().st_size == pseudo['bytes'] and sha(upf) == pseudo['sha256'], 'UPF bytes differ')
    density = (root/fixture['density']['relative_path']).resolve()
    require(density.is_relative_to(root/'.work') and density.stat().st_size == fixture['density']['bytes']
            and sha(density) == fixture['density']['sha256'], 'Fixed density bytes differ')
    out = Path(outdir).resolve()
    area = root/'.work/soc-validation-local'/('entries' if check else 'runs')
    require(out.name == 'worker' and out.parent.parent == area, 'Wrong static run directory')
    return dict(schema_version=1, experiment=EXPERIMENT, task_id=task, **spec,
                run_id=out.parent.name, worker_id='worker', outdir=str(out),
                adapter_root=str(root), source_root=str(numerical_root), numerical_root=str(numerical_root),
                execution_commit=execution, source_sha256=sources,
                adapter_sha256=adapter_sources(root, execution), case_path=case,
                case_sha256=sources[case], fixture_path=str(fixture_path), fixture_sha256=sha(fixture_path),
                density_path=str(density), density_sha256=fixture['density']['sha256'],
                check_only=check, timing_enabled=not check, budget_seconds=600,
                limit_bytes=8*GIB, warning_bytes=7*GIB, remaining_growth_bytes=2*GIB)


def slot_directory(root):
    common = Path(ROUTE.git(root, 'rev-parse', '--git-common-dir').decode().strip())
    return (common if common.is_absolute() else root/common).resolve()/'soc-validation-local-consumed'


def verify_route(path, task, outdir):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'Missing/linked route')
    routed = load_json(path)
    require(type(routed) is dict and type(routed.get('schema_version')) is int and
            routed['schema_version'] == 1 and type(routed.get('check_only')) is bool,
            'Static route schema/check mode invalid')
    require(path == path.resolve() and path.parent == Path(outdir).resolve().parent,
            'Route belongs to another run')
    root = Path(routed['adapter_root'])
    expected = prepare_route(root, routed['source_root'], task, outdir,
                             routed['execution_commit'], check=routed['check_only'])
    require(routed == expected, 'Route/current sources differ')
    result = dict(routed, route_sha256=sha(path))
    if not routed['check_only']:
        slot = load_json(slot_directory(root)/(task+'.json'))
        for key in ('run_id', 'task_id', 'execution_commit', 'source_commit'):
            require(slot.get(key) == routed[key], 'Static slot identity differs: '+key)
        require(slot.get('route_sha256') == result['route_sha256'], 'Static slot route changed')
        control = CONTROL.load_control(path.parent)
        for key in ('run_id', 'task_id', 'execution_commit', 'source_commit', 'case_sha256'):
            require(control[key] == routed[key], 'Static control identity differs: '+key)
        result.update(control_config=control, control_sha256=control['control_sha256'])
    else:
        require(not (path.parent/'control.toml').exists(), 'Check-only entry has a formal control')
    return result


def check_identity(value, route):
    for key in ('run_id','task_id','execution_commit','source_commit','case_sha256',
                'fixture_sha256','density_sha256','role','strategy','mode'):
        require(value.get(key) == route[key], 'Static worker identity differs: '+key)
    require(value.get('experiment') == EXPERIMENT, 'Wrong static experiment')
    require(type(value.get('environment')) is dict and value['environment'].get('status') == 'PASS',
            'Loaded environment identity failed')
    methods = value.get('actual_method_sources')
    require(type(methods) is dict and {'runtime_boundary','validate_context'} <= methods.keys(),
            'Actual validation method sources are missing')
    for item in methods.values():
        require(type(item) is dict and item.get('source_sha256') is not None and
                item['source_sha256'] == route['source_sha256'].get(item.get('relative_path')),
                'Loaded method source differs')


def entry_contract(raw, native, route):
    require(type(native) is int and native == 0, 'Entry worker returned nonzero')
    value = json.loads(raw)
    require(type(value) is dict and type(value.get('schema_version')) is int and
            value['schema_version'] == 1, 'Entry receipt missing/schema invalid')
    check_identity(value, route)
    require(value.get('execution_status') == 'CHECK_ONLY_PASS' and type(value.get('exit_code')) is int
            and value['exit_code'] == 0 and value.get('check_only') is True, 'Entry is not check-only success')
    require(all(value.get(k) is False for k in ('context_constructed','owned_runtime_constructed','formal_slot_reserved'))
            and value.get('numerical_execution_status') == 'NOT_RUN', 'Entry constructed state or consumed a slot')
    return value


def operation_evidence(value, route, directory):
    worker = Path(directory)/'worker'
    require(value.get('outer_integrity_status') == 'PASS', 'Static integrity comparison missing')
    def artifact(name, key):
        path = worker/name
        require(path.is_file() and not path.is_symlink() and sha(path) == value.get(key),
                'Static operation artifact missing/changed: '+name)
        return load_json(path)
    artifact('fixture-observed.json','fixture_observed_sha256')
    if route['mode'] == 'diagnostic':
        trace = artifact('trace.json','trace_sha256')
        observer = artifact('observer.json','observer_sha256')
        require(type(trace) is list and [r.get('operation') for r in trace] == ['boundary','storage'],
                'Diagnostic operations missing/duplicated')
        require(all(r.get('returned') is True and type(r.get('trace')) is dict and
                    r['trace'].get('operation') == r['operation'] and r['trace'].get('role') == route['role'] and
                    type(r['trace'].get('events')) is list and bool(r['trace']['events']) for r in trace),
                'Diagnostic validation/trace incomplete')
        require(type(observer) is dict and observer.get('role') == route['role'] and
                observer.get('scope') == 'INSTRUMENTED_DIAGNOSTIC_NOT_MAIN_TIMING', 'Observer identity/scope differs')
    else:
        require(not (worker/'trace.json').exists(), 'Benchmark contains enabled diagnostic trace')
        samples = artifact('samples.json','samples_sha256')
        selection = load_json(Path(route['adapter_root'])/'benchmarks/soc-validation-local-v1/selection.json')
        names = ['boundary','storage']+[s['name'] for s in selection['sequences']]
        require(len(names) == len(set(names)) and len(names) <= 5, 'Invalid operation names')
        expected = [(name,i) for name in names for i in range(1,8)]
        require(type(samples) is list and [(r.get('operation'),r.get('sample_index')) for r in samples] == expected,
                'Sample operations/count/order differs')
        for row in samples:
            i = row['sample_index']
            require(type(i) is int and row.get('kind') == ('warmup' if i <= 2 else 'measurement'),
                    'Sample phase differs')
            for key in ('seconds','allocation_bytes','gc_seconds'):
                x = row.get(key)
                require(type(x) in (int,float) and math.isfinite(x) and x >= 0,
                        'Invalid sample measurement: '+key)
            require(type(row['allocation_bytes']) is int, 'Allocation byte count must be integer')


def worker_contract(value, code, c, directory):
    require(type(value) is dict and type(value.get('schema_version')) is int and
            value['schema_version'] == 1, 'Static worker receipt/schema invalid')
    for key in ('run_id','execution_commit','source_commit','task_id','case_sha256','control_sha256'):
        require(value.get(key) == c[key], 'Worker/control identity differs: '+key)
    require(type(code) is int and type(value.get('exit_code')) is int and value['exit_code'] == code,
            'Static worker/native exit differs')
    require('completed_maps' not in value and not (Path(directory)/'worker/final.bin').exists(),
            'Static validation cannot counterfeit maps or publish a physical endpoint')
    request = CONTROL.read_request(directory, c)
    status = value.get('execution_status')
    if code == 0:
        require(status == SUCCESS and request is None, 'Zero exit is only unstopped static validation completion')
        require(value.get('runtime_closed') is True and value.get('workspace_released') is True,
                'Static owned cleanup unconfirmed')
        if not c['synthetic']:
            route = load_json(Path(directory)/'route.json')
            check_identity(value, route)
            require(value.get('static_context_setup_status') == SETUP and
                    value.get('validation_operations_status') == 'PASS', 'Static setup/validation incomplete')
            parallel = value.get('parallelism')
            require(parallel == {'julia':1,'blas':1,'fft':1,'mpi':1} and
                    all(type(v) is int for v in parallel.values()), 'Parallelism differs')
            after = value.get('runtime_after_close')
            require(type(after) is dict and after.get('closed') is True and
                    after.get('workspace_released') is True and after.get('owned_source_entries') == 0,
                    'Owned source release not recorded')
            if route['role'] != 'S':
                validation = after.get('validation')
                require(type(validation) is dict and validation.get('policy') == route['strategy'] and
                        validation.get('active') is False and validation.get('closed') is True and
                        validation.get('live_array_entries') == validation.get('live_source_entries') == 0,
                        'Opt-in validation policy/cache release unconfirmed')
            if route['mode'] == 'benchmark':
                sampling = value.get('sample_contract')
                require(type(sampling) is dict and all(type(sampling.get(k)) is type(v) and sampling[k] == v
                        for k,v in dict(warmups=2,samples=5,trace_enabled=False).items()),
                        'Benchmark sampling/trace contract differs')
            operation_evidence(value,route,directory)
    elif status in CONTROL.CODES:
        require(code == CONTROL.CODES[status] and request is not None and request['reason'] == status,
                'Static stop/native reason mismatch')
        control = value.get('control')
        require(type(control) is dict and control.get('first_request_sha256') == request['request_sha256'] and
                control.get('acknowledged_boundary'), 'Static worker did not acknowledge same request')
        closed = value.get('runtime_closed') is True and value.get('workspace_released') is True
        unconstructed = value.get('runtime_state') == 'NOT_CONSTRUCTED' and all(value.get(k) is False for k in
                ('owned_runtime_constructed','runtime_closed','workspace_released')) and type(value.get('context_constructed')) is bool
        require(closed or unconstructed, 'Static cooperative cleanup unconfirmed')
    else:
        require(status == 'FAIL' and code > 0 and type(value.get('reason')) is str and value['reason'],
                'Undeclared static failure')
    return value


CONTROL.worker_contract = worker_contract


def budget_remaining(root):
    """Sum completed active worker intervals; editing idle time is not consumed."""
    total = 0.0
    slots = slot_directory(root)
    if slots.exists():
        for marker in sorted(slots.glob('*.json')):
            slot = load_json(marker)
            require(marker.stem in TASKS and slot['task_id'] == marker.stem, 'Unknown static slot marker')
            directory = Path(slot['directory'])
            require(directory == directory.resolve() and directory.name == slot['run_id'], 'Slot run path changed')
            record = load_json(directory/'active-work.json')
            require(record.get('run_id') == slot['run_id'] and record.get('task_id') == slot['task_id'] and
                    record.get('cleanup_status') == 'PASS', 'Prior static process cleanup/work time unconfirmed')
            elapsed = record.get('charged_seconds')
            require(type(elapsed) in (int,float) and math.isfinite(elapsed) and elapsed >= 0,
                    'Invalid active process duration')
            hashes = record.get('receipt_sha256')
            require(type(hashes) is dict and {'process-start.json','process-exit.json','resource.json','result.json'} <= hashes.keys(),
                    'Actual prior process receipts missing')
            for name, digest in hashes.items():
                require(sha(directory/name) == digest, 'Prior process budget receipt changed: '+name)
            resource = load_json(directory/'resource.json')
            require(type(resource.get('elapsed_seconds')) in (int,float) and
                    math.isfinite(resource['elapsed_seconds']) and 0 <= resource['elapsed_seconds'] <= elapsed and
                    resource.get('owned_process_cleanup_status') == 'PASS', 'Budget undercounts process or cleanup')
            total += elapsed
    return 1800-total


def observer_preflight(resources, root):
    """Fail closed before reservation or Popen if process/RSS visibility is denied."""
    try:
        rows = resources.process_table()
        own = [r for r in rows if r.get('pid') == os.getpid()]
        require(len(own) == 1 and type(own[0].get('rss_kib')) is int and own[0]['rss_kib'] > 0,
                'Observer cannot authenticate its own positive RSS')
        require(not [p for p in rows if 'julia' in Path(p['command'].split()[0]).name and
                     any(label in p['command'] for label in ('soc-timing-v1','soc-boundary-v1',EXPERIMENT))],
                'Another diagnostic/static worker exists')
        host = resources.host_preflight(root)
        require(host.get('status') == 'ELIGIBLE', 'Host preflight blocked: '+str(host.get('reason')))
        return dict(status='ELIGIBLE',host=host,process_observer='existing resources.process_table',
                    scope='Read-only availability proof; full group monitoring remains mandatory')
    except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError) as error:
        return dict(status='BLOCKED_RESOURCE_OBSERVATION',reason=type(error).__name__+': '+str(error),
                    native_exit_code=None,slot_consumed=False)


def benchmark_gate(root, execution):
    """No benchmark can precede the observed mechanism and one protected choice."""
    specification(root,'BENCH-C',execution)  # Includes the committed selection.
    selection = load_json(root/'benchmarks/soc-validation-local-v1/selection.json')
    sequences = selection.get('sequences')
    require(type(sequences) is list and len(sequences) <= 3, 'Invalid representative sequence selection')
    for sequence in sequences:
        require(type(sequence) is dict and type(sequence.get('name')) is str and sequence['name'] and
                type(sequence.get('rationale')) is str and sequence['rationale'] and
                type(sequence.get('indices')) is list and bool(sequence['indices']) and
                all(type(i) is int and i > 0 for i in sequence['indices']), 'Sequence choice lacks exact indices/rationale')
    diagnostic_hashes = []
    for task in ('DIAG-S','DIAG-F'):
        slot = load_json(slot_directory(root)/(task+'.json'))
        directory = Path(slot['directory'])
        control = CONTROL.load_control(directory)
        worker = load_json(directory/'worker/result.json')
        outer = load_json(directory/'result.json')
        native = load_json(directory/'process-exit.json')
        resource = load_json(directory/'resource.json')
        worker_contract(worker,native['exit_code'],control,directory)
        digest = sha(directory/'worker/result.json')
        require(outer.get('execution_status') == SUCCESS and outer.get('exit_code') == outer.get('native_exit_code') ==
                native.get('exit_code') == 0 and outer.get('worker_result_sha256') == digest and
                resource.get('status') == resource.get('owned_process_cleanup_status') == 'PASS',
                'Diagnostic prerequisite failed or changed: '+task)
        diagnostic_hashes.append(digest)
    require(selection.get('mechanism_evidence') == diagnostic_hashes, 'Selection is not bound to both actual diagnostics')
    path = root/'.work/soc-validation-local/protection.json'
    require(sha(path) == selection.get('protection_receipt_sha256'), 'Candidate protection receipt differs')
    receipt = load_json(path)
    require(type(receipt.get('schema_version')) is int and receipt['schema_version'] == 1 and
            receipt.get('experiment') == EXPERIMENT and receipt.get('status') == 'PASS', 'Candidate protection incomplete')
    tested = receipt.get('tested_source_sha256')
    # Selection names the completed receipt, so exclude that self-referential
    # document from tested code. All numerical and executable adapter bytes are bound.
    required = ROUTE.source_files(root,execution,'benchmarks/si-soc-sensitivity-v1/K4/case.json')
    required.update({p:d for p,d in adapter_sources(root,execution).items() if p.endswith(('.py','.jl'))})
    require(type(tested) is dict and all(tested.get(p) == d for p,d in required.items()),
            'Candidate protection did not test these numerical/adapter bytes')
    prepared = receipt.get('preparation_commit')
    require(type(prepared) is str and len(prepared) == 40, 'Missing exact protected preparation commit')
    ROUTE.git(root,'merge-base','--is-ancestor',prepared,execution)
    require(all(hashlib.sha256(ROUTE.git(root,'show',prepared+':'+p)).hexdigest() == d for p,d in required.items()),
            'Protected preparation does not contain the tested source bytes')
    checks = receipt.get('checks')
    require(type(checks) is list and bool(checks), 'No actual protection checks')
    needed = {'protection','digest-equivalence','default-strict','control','source-entry','syntax'}
    categories = set()
    for check in checks:
        require(type(check) is dict and type(check.get('exit_code')) is int and check['exit_code'] == 0 and
                type(check.get('command')) is list and bool(check['command']) and
                all(type(x) is str and x for x in check['command']), 'Protection check failed/missing command')
        log = Path(check['log_path']);log = log if log.is_absolute() else root/log
        require(log.resolve().is_relative_to(root/'.work') and sha(log) == check['log_sha256'], 'Protection log changed')
        require(type(check.get('categories')) is list and bool(check['categories']) and
                set(check['categories']) <= needed, 'Protection check category invalid')
        categories.update(check['categories'])
    require(categories == needed, 'Required candidate protection categories incomplete')
    return dict(selection_sha256=sha(root/'benchmarks/soc-validation-local-v1/selection.json'),
                protection_sha256=sha(path),diagnostic_worker_sha256=diagnostic_hashes)


@contextlib.contextmanager
def locks(root, run_id):
    with SHARED.locks(root, run_id, boundary=True) as lease:
        path = root/'.work/soc-validation-local/active.json'
        CONTROL.publish_first(path, (json.dumps(dict(run_id=run_id,owner_pid=os.getpid()))+'\n').encode())
        lease['paths'].append(path)
        yield lease


def release(lease, run_id):
    for path in reversed(lease['paths']):
        require(load_json(path)['run_id'] == run_id, 'Lock ownership changed')
        path.unlink()


def run(task, julia, source_root, *, check=False):
    global CURRENT
    root = ROOT.resolve()
    execution = ROUTE.git(root, 'rev-parse', 'HEAD').decode().strip()
    require(ROUTE.git(root, 'branch', '--show-current').decode().strip() == BRANCH, 'Wrong static branch')
    area = root/'.work/soc-validation-local'
    run_id = task+('-ENTRY-' if check else '-')+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+uuid.uuid4().hex[:8]
    directory = area/('entries' if check else 'runs')/run_id
    directory.mkdir(parents=True, exist_ok=False)
    CURRENT = directory
    state = dict(schema_version=1,experiment=EXPERIMENT,run_id=run_id,task_id=task,
                 execution_commit=execution,execution_status='NOT_STARTED',native_exit_code=None,exit_code=9)
    CONTROL.atomic_json(directory/'launcher.json', state)
    routed = prepare_route(root, source_root, task, directory/'worker', execution, check=check)
    CONTROL.publish_first(directory/'route.json', (json.dumps(routed,indent=2,allow_nan=False)+'\n').encode())
    command = [str(Path(julia).absolute()),'--startup-file=no','--color=no','--threads=1',
               '--project='+str(Path(routed['source_root'])/'environment/workbench'),
               str(HERE/'driver.jl'),task,str(directory/'worker'),str(directory/'route.json')]
    depot = os.environ.get('JULIA_DEPOT_PATH','')
    require(depot and all(Path(p).is_dir() for p in depot.split(os.pathsep)), 'Select existing frozen depots explicitly')
    env = dict(os.environ,JULIA_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',
               MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',JULIA_PKG_OFFLINE='true',
               JULIA_LOAD_PATH='@:@stdlib',SOC_CORE_PYTHON=sys.executable,SOC_TIMING_PYTHON=sys.executable,
               SOC_LOCAL_PYTHON=sys.executable)
    if check:
        p = subprocess.run(command+['--check-entry'],env=env,capture_output=True,timeout=120)
        (directory/'entry.stdout').write_bytes(p.stdout); (directory/'entry.stderr').write_bytes(p.stderr)
        state.update(native_exit_code=p.returncode)
        try:
            entry_contract(p.stdout,p.returncode,routed)
            state.update(execution_status='CHECK_ONLY_PASS',exit_code=0,entry_contract_status='PASS')
        except (ValueError,TypeError,KeyError) as error:
            state.update(execution_status='ENTRY_PROTOCOL_FAILURE',exit_code=9,reason=str(error))
        CONTROL.atomic_json(directory/'launcher.json',state)
        print(json.dumps(dict(directory=str(directory),**state)))
        return state['exit_code']
    with locks(root, run_id) as lease:
        resources = module(root/'benchmarks/soc-extra-v1/resources.py','local_static_resources')
        observation = observer_preflight(resources,root)
        CONTROL.atomic_json(directory/'observer-preflight.json',observation)
        if observation['status'] != 'ELIGIBLE':
            state.update(execution_status='BLOCKED_RESOURCE_OBSERVATION',reason=observation['reason'],
                         exit_code=17,slot_consumed=False)
            CONTROL.atomic_json(directory/'launcher.json',state)
            release(lease,run_id)
            print(json.dumps(dict(directory=str(directory),**state)))
            return 17
        if task.startswith('BENCH-'):
            CONTROL.atomic_json(directory/'benchmark-gate.json',benchmark_gate(root,execution))
        left = budget_remaining(root)
        require(left >= 300, 'Less than five minutes of the active-process budget remain')
        position = TASKS.index(task)
        slots = slot_directory(root); slots.mkdir(exist_ok=True)
        require(all((slots/(t+'.json')).exists() for t in TASKS[:position]), 'Declared serial slot order differs')
        slot = dict(run_id=run_id,task_id=task,execution_commit=execution,source_commit=routed['source_commit'],
                    directory=str(directory),route_sha256=sha(directory/'route.json'),
                    consumption='Permanent once reserved before launch; no retry or reopening')
        CONTROL.publish_first(slots/(task+'.json'), (json.dumps(slot,indent=2)+'\n').encode())
        CONTROL.create_control(directory,execution_commit=execution,source_commit=routed['source_commit'],
                               task_id=task,case_sha256=routed['case_sha256'],budget_seconds=600,
                               batch_deadline_unix_ns=time.time_ns()+int(left*1e9))
        state.update(execution_status='LAUNCH_REQUESTED',slot_consumed=True,command=command)
        CONTROL.atomic_json(directory/'launcher.json',state)
        lease['launched'] = True
        began_utc, began_ns = time.time(), time.monotonic_ns()
        code, result = CONTROL.launch_worker(command,directory,env,resources=resources)
        elapsed = max(0,time.time()-began_utc,(time.monotonic_ns()-began_ns)/1e9,
                      result.get('resource',{}).get('elapsed_seconds',0))
        cleanup = result.get('resource',{}).get('owned_process_cleanup_status')
        hashes = {name:sha(directory/name) for name in ('process-start.json','process-exit.json','resource.json','result.json')
                  if (directory/name).is_file()}
        CONTROL.atomic_json(directory/'active-work.json',dict(schema_version=1,run_id=run_id,task_id=task,
                            charged_seconds=elapsed,cleanup_status=cleanup,receipt_sha256=hashes,
                            scope='Conservative actual supervised-process interval; edit idle time excluded'))
        state.update(execution_status=result.get('execution_status','UNKNOWN'),native_exit_code=result.get('native_exit_code'),
                     exit_code=code,charged_seconds=elapsed,cumulative_remaining_seconds=left-elapsed)
        CONTROL.atomic_json(directory/'launcher.json',state)
        if cleanup == 'PASS':
            lease['cleanup_confirmed'] = True
            release(lease,run_id)
        print(json.dumps(dict(directory=str(directory),**state)))
        return code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action',required=True)
    p = commands.add_parser('verify');p.add_argument('route');p.add_argument('task',choices=TASKS);p.add_argument('outdir')
    p = commands.add_parser('run');p.add_argument('task',choices=TASKS);p.add_argument('--julia',required=True)
    p.add_argument('--source-root',required=True);p.add_argument('--check-entry',action='store_true')
    p = commands.add_parser('stop');p.add_argument('--run-dir',required=True);p.add_argument('--run-id',required=True)
    p.add_argument('--execution-commit',required=True);p.add_argument('--detail',default='User requested cancellation')
    args = parser.parse_args(argv)
    try:
        if args.action == 'verify':
            print(json.dumps(verify_route(args.route,args.task,args.outdir),allow_nan=False));return 0
        if args.action == 'stop':
            print(json.dumps(CONTROL.request_stop(args.run_dir,run_id=args.run_id,
                  execution_commit=args.execution_commit,detail=args.detail)));return 0
        return run(args.task,args.julia,args.source_root,check=args.check_entry)
    except Exception as error:
        if CURRENT is not None:
            try:
                state = load_json(CURRENT/'launcher.json')
                state.update(execution_status='LAUNCHER_FAILURE',exit_code=9,reason=type(error).__name__+': '+str(error))
                CONTROL.atomic_json(CURRENT/'launcher.json',state)
            except Exception as persistence:
                print('PERSISTENCE FAILURE: '+str(persistence),file=sys.stderr)
        print(type(error).__name__+': '+str(error),file=sys.stderr);return 9


if __name__ == '__main__':
    sys.exit(main())
