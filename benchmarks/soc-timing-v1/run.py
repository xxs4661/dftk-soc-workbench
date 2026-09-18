"""Consume one bounded timing slot. No automatic retry or next-slot dispatch."""
import argparse
import contextlib
import datetime
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
CURRENT = None
sys.path.insert(0, str(Path(__file__).resolve().parent))
import route
import admission
import control


def write(path, value, exclusive=False):
    data = json.dumps(value, indent=2, allow_nan=False)+'\n'
    with Path(path).open('x' if exclusive else 'w') as stream:
        stream.write(data)


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec); spec.loader.exec_module(obj)
    return obj


def remaining(batch, now_epoch=None, now_ns=None):
    """Conservative across sleep or calendar adjustments: take the older clock."""
    utc_elapsed = (time.time() if now_epoch is None else now_epoch)-batch['started_epoch']
    mono_elapsed = ((time.monotonic_ns() if now_ns is None else now_ns)-batch['started_monotonic_ns'])/1e9
    total=batch.get('total_seconds',3600)
    require(type(total) is int and total in (3600,5400),'Unregistered batch budget')
    return total-max(0, utc_elapsed, mono_elapsed)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def entry_contract(raw, native, routed):
    require(native == 0, 'Entry worker returned nonzero')
    value = json.loads(raw)
    require(type(value) is dict, 'Entry receipt is not an object')
    for key in ('run_id', 'task_id', 'execution_commit', 'source_commit', 'case_sha256'):
        require(value.get(key) == routed[key], 'Entry identity differs: '+key)
    require(value.get('execution_status') == 'CHECK_ONLY_PASS' and type(value.get('exit_code')) is int and
            value['exit_code'] == 0 and value.get('check_only') is True, 'Entry receipt is not successful check-only')
    require(value.get('context_constructed') is False and value.get('owned_runtime_constructed') is False and
            value.get('formal_slot_reserved') is False and value.get('numerical_execution_status') == 'NOT_RUN',
            'Entry constructed numerical state or reserved a slot')
    require(type(value.get('environment')) is dict and value['environment'].get('status') == 'PASS',
            'Entry environment failed')
    methods=value.get('actual_method_sources')
    expected={'soc_scf','solve_soc_targets','controller'}
    if routed['task_id'] in route.BOUNDARY_TASKS:
        expected|={'runtime_boundary','validate_context'}
        require(value.get('timing_enabled') is True and value.get('validation_policy')==routed['validation_policy'],
                'Boundary entry timing/policy differs')
    require(type(methods) is dict and set(methods) == expected,
            'Loaded method identities missing')
    for item in methods.values():
        require(type(item) is dict and item.get('source_sha256') == routed['source_sha256'].get(item.get('relative_path'))
                and item.get('source_sha256') is not None, 'Entry loaded method source differs')
    return value


@contextlib.contextmanager
def locks(root, run_id, *, boundary=False):
    paths = [root/p for p in ('.work/soc-timing/active.json', '.work/phase9a-extra/active.json',
             '.work/phase9a/endpoints/active.json', '.work/phase9a/static/active.json')]
    if boundary:paths.insert(0,root/'.work/soc-boundary/active.json')
    owned=[]; lease=dict(paths=owned, launched=False, cleanup_confirmed=False)
    try:
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            write(path, dict(run_id=run_id, owner_pid=os.getpid()), exclusive=True); owned.append(path)
        yield lease
    except BaseException:
        # Pre-launch failure has no child. Post-launch callers leave locks on
        # unconfirmed cleanup and must not enter this automatic-release path.
        if not lease['launched'] or lease['cleanup_confirmed']:
            for path in reversed(owned):
                if path.exists() and json.loads(path.read_text()).get('run_id') == run_id:
                    path.unlink()
        raise



def protection_sources(root,execution):
    sources=route.source_files(root,execution,route.CASES['B0'])
    sources.update(route.adapter_files(root,execution,boundary=True))
    for name in route.git(root,'ls-tree','-r','--name-only',execution).decode().splitlines():
        if name.startswith(('tests/test_soc_boundary','tests/test_soc_timing','tests/soc_boundary/')):
            sources[name]=route.exact_file(root,execution,name)
    return sources


def verify_protection(root,execution):
    path=root/'.work/soc-boundary/protection.json'
    require(path.is_file() and not path.is_symlink(),'Missing actual protection-test receipt')
    value=json.loads(path.read_text())
    require(type(value.get('schema_version')) is int and value['schema_version']==1 and
            value.get('experiment')=='soc-boundary-v1' and value.get('status')=='PASS','Protection gate is not PASS')
    tested=value.get('tested_source_sha256')
    required=protection_sources(root,execution)
    require(type(tested) is dict and all(tested.get(k)==v for k,v in required.items()),
            'Protection tests did not cover these exact numerical/adapter/test bytes')
    prepared=value.get('preparation_commit',value.get('execution_commit'))
    require(type(prepared) is str and len(prepared)==40 and
            route.git(root,'cat-file','-t',prepared).decode().strip()=='commit','Missing exact protection-test preparation commit')
    route.git(root,'merge-base','--is-ancestor',prepared,execution)
    require(all(route.exact_file(root,prepared,k)==v for k,v in required.items()),
            'Protection preparation does not contain the exact executed/tested bytes')
    checks=value.get('checks')
    require(type(checks) is list and bool(checks),'No actual protection checks recorded')
    categories=set()
    needed={'protection-equivalence','hash-equivalence','cancellation-timeout','source-entry',
            'full-syntax','legacy-control','public-arithmetic','legacy-timer'}
    for check in checks:
        require(type(check) is dict and type(check.get('exit_code')) is int and check['exit_code']==0 and
                bool(check.get('command')),'Protection check did not succeed')
        log=Path(check['log_path']);log=log if log.is_absolute() else root/log
        require(log.is_file() and not log.is_symlink() and log.resolve().is_relative_to(root/'.work') and
                route.sha(log)==check['log_sha256'],'Protection check log missing/changed')
        tags=check.get('categories')
        require(type(tags)is list and bool(tags) and all(type(t)is str and t in needed for t in tags),
                'Protection check has no recognized coverage categories')
        categories.update(tags)
    require(categories==needed,'Required protection check categories are incomplete')
    return dict(path=str(path),sha256=route.sha(path),preparation_commit=prepared,checks=len(checks))


def checked_prior(root,area,task,execution):
    receipt=json.loads((area/(task+'-accepted.json')).read_text())
    directory=Path(receipt['directory'])
    require(directory==directory.resolve() and directory.parent==area/'runs' and directory.name==receipt['run_id'],
            'Predecessor belongs to another run area')
    outer=json.loads((directory/'result.json').read_text())
    raw=(directory/'worker/result.json').read_bytes();worker=json.loads(raw)
    spec=route.task_spec(task,root);source=spec['reference_commit'] if spec['role']=='REF' else execution
    require(route.sha(directory/'worker/result.json')==outer.get('worker_result_sha256'),'Predecessor worker bytes changed')
    for record in (outer,worker):
        require(all(record.get(k)==v for k,v in dict(run_id=receipt['run_id'],task_id=task,
                    execution_commit=execution,source_commit=source,exit_code=0,
                    execution_status='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED').items()),'Predecessor identity/status differs')
    c=control.load_control(directory);control.worker_contract(worker,0,c,directory)
    native=json.loads((directory/'process-exit.json').read_text())
    resource=json.loads((directory/'resource.json').read_text())
    require(outer.get('native_exit_code')==native.get('exit_code')==0 and
            all(r.get('status')=='PASS' and r.get('owned_process_cleanup_status')=='PASS'
                for r in (outer.get('resource',{}),resource)),
            'Predecessor process/cleanup not qualified')
    return receipt


def run(task, julia, reference, *, check=False):
    global CURRENT
    root = ROOT.resolve(); spec=route.task_spec(task,root)
    boundary=task in route.BOUNDARY_TASKS
    area=root/spec['area']; area.mkdir(exist_ok=True)
    execution=route.git(root,'rev-parse','HEAD').decode().strip()
    require(route.git(root,'branch','--show-current').decode().strip() == spec['branch'], 'Wrong diagnostic branch')
    route.tree_identity(root,execution)
    profile,budget,timed=spec['profile'],spec['budget_seconds'],spec['timing_enabled']
    numerical=root if spec['role']=='OPT' else Path(reference).resolve()
    source=json.loads((numerical/'benchmarks/si-soc-splitting-v1/source.json').read_text())
    pseudo=numerical/source['local_path']
    require(pseudo.stat().st_size==source['bytes'] and route.sha(pseudo)==source['sha256']==
            'cc91a6be43c3c89daf6c34410096e8d870f25152dbfb513bcf01afa5ab53eabf', 'Frozen Si input bytes differ')
    run_id=task+('-ENTRY-' if check else '-')+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+uuid.uuid4().hex[:8]
    directory=area/('entries' if check else 'runs')/run_id
    directory.mkdir(parents=True,exist_ok=False)
    CURRENT=directory
    state=dict(schema_version=1,task_id=task,run_id=run_id,execution_commit=execution,
               execution_status='NOT_STARTED',native_exit_code=None,exit_code=9)
    write(directory/'launcher.json',state)
    protection=verify_protection(root,execution) if boundary and not check else None
    if protection:state['protection']=protection
    res=module(root/'benchmarks/soc-extra-v1/resources.py','timing_resources')
    estimate=admission.admission(root,profile);write(directory/'admission.json',estimate)
    require(estimate['status']=='ELIGIBLE_WITH_MONITORING','Resource estimate blocked')
    host=res.host_preflight(root);write(directory/'host.json',host)
    require(host['status']=='ELIGIBLE','Current host preflight blocked')
    # Include this new diagnostic name in the existing process detector.
    suspicious=[p for p in res.process_table() if 'julia' in Path(p['command'].split()[0]).name and
                ('soc-timing-v1' in p['command'] or 'soc-boundary-v1' in p['command'])]
    require(not suspicious,'Another timing worker exists')
    depot=os.environ.get('JULIA_DEPOT_PATH','')
    require(depot and all(Path(p).is_dir() for p in depot.split(os.pathsep)), 'Select existing frozen depots explicitly')
    env=dict(os.environ,JULIA_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',
             MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',JULIA_PKG_OFFLINE='true',
             JULIA_LOAD_PATH='@:@stdlib',SOC_CORE_PYTHON=sys.executable,SOC_TIMING_PYTHON=sys.executable)
    batch_path=area/'batch.json'
    if check:
        left=budget;batch=None
    elif batch_path.exists():
        batch=json.loads(batch_path.read_text())
        require(batch['execution_commit']==execution and batch.get('total_seconds')==spec['batch_seconds'],
                'The fixed batch execution version/budget changed')
        left=remaining(batch);require(left>=300,'Less than five minutes remain; no next slot')
    else:
        require(task==spec['tasks'][0],'REF must start the fixed batch')
        batch=None;left=spec['batch_seconds']
    if boundary and not check:
        position=spec['tasks'].index(task)
        previous=[checked_prior(root,area,t,execution) for t in spec['tasks'][:position]]
        if position>=2:
            paired=json.loads((area/'b0-equivalence.json').read_text())
            require(paired.get('status')=='PASS' and paired.get('execution_commit')==execution and
                    paired.get('run_ids')==[r['run_id'] for r in previous[:2]],'New B0 pair gate missing/stale')
            comparator=module(root/'benchmarks/soc-timing-v1/compare.py','boundary_start_pair')
            require(comparator.pair(root,boundary_profile='B0',write_result=False)==paired,
                    'B0 gate does not reproduce the bound current maps and density exports')
    if not boundary and not check and task!='T-B0-REF':
        prior='T-B0-REF' if task=='T-B0-TIMED' else 'T-B0-TIMED'
        receipt=json.loads((area/(prior+'-accepted.json')).read_text())
        require(receipt['execution_commit']==execution and receipt['status']=='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED', 'Previous slot not complete')
        if task=='T-K4-TIMED':
            pair=json.loads((area/'b0-equivalence.json').read_text())
            require(pair['status']=='PASS' and pair['execution_commit']==execution,'B0 pair not equivalent')
    deadline=time.time()+min(budget,left)
    routed=route.prepare_route(root,numerical,task,directory/'worker',execution,deadline)
    write(directory/'route.json',routed,exclusive=True)
    command=[str(Path(julia).absolute()),'--startup-file=no','--color=no','--threads=1',
             '--project='+str(numerical/'environment/workbench'),str(root/'benchmarks/soc-timing-v1/driver.jl'),
             task,str(directory/'worker'),str(directory/'route.json')]
    if check:
        command.append('--check-entry')
        proc=subprocess.run(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
        (directory/'entry.stdout').write_bytes(proc.stdout);(directory/'entry.stderr').write_bytes(proc.stderr)
        state.update(execution_status='ENTRY_ONLY',native_exit_code=proc.returncode,exit_code=proc.returncode)
        try:
            entry_contract(proc.stdout, proc.returncode, routed)
            state['entry_contract_status']='PASS'
        except (ValueError, TypeError, KeyError) as error:
            state.update(execution_status='ENTRY_PROTOCOL_FAILURE',entry_contract_status='FAIL',exit_code=9,
                         reason=type(error).__name__+': '+str(error))
        write(directory/'launcher.json',state)
        print(json.dumps(dict(directory=str(directory),**state)))
        return state['exit_code']
    with locks(root,run_id,boundary=boundary) as lease:
        common=Path(route.git(root,'rev-parse','--git-common-dir').decode().strip())
        if not common.is_absolute():common=root/common
        slots=common/spec['slots'];slots.mkdir(exist_ok=True)
        write(slots/(task+'.json'),dict(run_id=run_id,execution_commit=execution,task_id=task,
              consumption='Committed before launch; never reopened after failure'),exclusive=True)
        if batch is None:
            batch=dict(execution_commit=execution,started_epoch=time.time(),started_monotonic_ns=time.monotonic_ns(),
                       total_seconds=spec['batch_seconds'],origin='Immediately before first worker launch, conservatively includes parent setup')
            write(batch_path,batch,exclusive=True)
        control.create_control(directory,execution_commit=execution,source_commit=routed['source_commit'],
            task_id=task,case_sha256=routed['case_sha256'],budget_seconds=budget,
            batch_deadline_unix_ns=int((time.time()+remaining(batch))*1e9),
            protection_gate_sha256=None if protection is None else protection['sha256'])
        state.update(execution_status='LAUNCH_REQUESTED',command=command,slot_consumed=True)
        write(directory/'launcher.json',state)
        # launch_worker returns a persisted failure too; do not retry on any code.
        lease['launched']=True
        code,record=control.launch_worker(command,directory,env,resources=res)
        state.update(execution_status=record.get('execution_status',record.get('status','UNKNOWN')),
                     native_exit_code=record.get('native_exit_code'),exit_code=code,batch_remaining_seconds=remaining(batch))
        write(directory/'launcher.json',state)
        cleanup=record.get('resource',{}).get('owned_process_cleanup_status')
        if cleanup=='PASS':
            lease['cleanup_confirmed']=True
            for path in reversed(lease['paths']):
                require(json.loads(path.read_text())['run_id']==run_id,'Lock identity changed')
                path.unlink()
        else:
            state['locks_retained']='OWNED_CLEANUP_UNCONFIRMED';write(directory/'launcher.json',state)
        if code==0 and cleanup=='PASS':
            require(state['execution_status']=='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED','Zero exit not diagnostic success')
            write(area/(task+'-accepted.json'),dict(status=state['execution_status'],execution_commit=execution,
                  run_id=run_id,directory=str(directory)),exclusive=True)
        print(json.dumps(dict(directory=str(directory),**state)))
        return code


def main(argv=None, *, tasks=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task',choices=route.TASKS if tasks is None else tasks)
    parser.add_argument('--julia',required=True);parser.add_argument('--reference',required=True)
    parser.add_argument('--check-entry',action='store_true')
    args=parser.parse_args(argv)
    try:
        return run(args.task,args.julia,args.reference,check=args.check_entry)
    except Exception as error:
        if CURRENT is not None:
            path=CURRENT/'launcher.json'
            try:
                state=json.loads(path.read_text()) if path.exists() else {}
                state.update(execution_status='LAUNCHER_FAILURE',exit_code=9,reason=type(error).__name__+': '+str(error))
                write(path,state)
            except Exception as persistence:
                print('LAUNCHER PERSISTENCE FAILURE: '+str(persistence),file=sys.stderr)
        print(type(error).__name__+': '+str(error),file=sys.stderr);return 9


if __name__=='__main__':sys.exit(main())
