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
    return 3600-max(0, utc_elapsed, mono_elapsed)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


@contextlib.contextmanager
def locks(root, run_id):
    paths = [root/p for p in ('.work/soc-timing/active.json', '.work/phase9a-extra/active.json',
             '.work/phase9a/endpoints/active.json', '.work/phase9a/static/active.json')]
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


def run(task, julia, reference, *, check=False):
    global CURRENT
    root = ROOT.resolve(); area=root/'.work/soc-timing'; area.mkdir(exist_ok=True)
    execution=route.git(root,'rev-parse','HEAD').decode().strip()
    require(route.git(root,'branch','--show-current').decode().strip() == 'codex/phase9a-timing-cancellation', 'Wrong diagnostic branch')
    route.tree_identity(root,execution)
    profile,budget,timed=route.TASKS[task]
    numerical=root if timed else Path(reference).resolve()
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
    res=module(root/'benchmarks/soc-extra-v1/resources.py','timing_resources')
    estimate=admission.admission(root,profile);write(directory/'admission.json',estimate)
    require(estimate['status']=='ELIGIBLE_WITH_MONITORING','Resource estimate blocked')
    host=res.host_preflight(root);write(directory/'host.json',host)
    require(host['status']=='ELIGIBLE','Current host preflight blocked')
    # Include this new diagnostic name in the existing process detector.
    suspicious=[p for p in res.process_table() if 'julia' in Path(p['command'].split()[0]).name and
                ('soc-timing-v1/driver.jl' in p['command'] or 'soc-timing-v1' in p['command'])]
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
        require(batch['execution_commit']==execution,'The fixed batch execution version changed')
        left=remaining(batch);require(left>=300,'Less than five minutes remain; no next slot')
    else:
        require(task=='T-B0-REF','REF must start the fixed batch')
        batch=None;left=3600
    if not check and task!='T-B0-REF':
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
        write(directory/'launcher.json',state)
        print(json.dumps(dict(directory=str(directory),**state)))
        return proc.returncode
    with locks(root,run_id) as lease:
        common=Path(route.git(root,'rev-parse','--git-common-dir').decode().strip())
        if not common.is_absolute():common=root/common
        slots=common/'soc-timing-consumed';slots.mkdir(exist_ok=True)
        write(slots/(task+'.json'),dict(run_id=run_id,execution_commit=execution,task_id=task,
              consumption='Committed before launch; never reopened after failure'),exclusive=True)
        if batch is None:
            batch=dict(execution_commit=execution,started_epoch=time.time(),started_monotonic_ns=time.monotonic_ns(),
                       total_seconds=3600,origin='Immediately before first worker launch, conservatively includes parent setup')
            write(batch_path,batch,exclusive=True)
        control.create_control(directory,execution_commit=execution,source_commit=routed['source_commit'],
            task_id=task,case_sha256=routed['case_sha256'],budget_seconds=budget,
            batch_deadline_unix_ns=int((time.time()+remaining(batch))*1e9))
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


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task',choices=route.TASKS)
    parser.add_argument('--julia',required=True);parser.add_argument('--reference',required=True)
    parser.add_argument('--check-entry',action='store_true')
    args=parser.parse_args()
    try:
        sys.exit(run(args.task,args.julia,args.reference,check=args.check_entry))
    except Exception as error:
        if CURRENT is not None:
            path=CURRENT/'launcher.json'
            try:
                state=json.loads(path.read_text()) if path.exists() else {}
                state.update(execution_status='LAUNCHER_FAILURE',exit_code=9,reason=type(error).__name__+': '+str(error))
                write(path,state)
            except Exception as persistence:
                print('LAUNCHER PERSISTENCE FAILURE: '+str(persistence),file=sys.stderr)
        print(type(error).__name__+': '+str(error),file=sys.stderr);sys.exit(9)
