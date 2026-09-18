#!/usr/bin/env python3
"""Small cooperative control and recorder for the three declared timing tasks.

No physics is implemented here. Old extra slots and their resource-stop files
are not accepted. Synthetic mode exists only for bounded protocol tests.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
import tomllib
import uuid

ROOT=Path(__file__).resolve().parents[2]
GIB=1024**3
TASKS={'T-B0-REF':900,'T-B0-TIMED':900,'T-K4-TIMED':1800}
BOUNDARY_TASKS={'V-B0-REF':900,'V-B0-OPT':900,'V-K4-REF':1800,'V-K4-OPT':1800}
BOUNDARY_REFERENCE='d9e19af3557c923a1e4f7e64510092d47975cc7c'
REASONS={'USER_CANCELLED','TIME_BUDGET_EXCEEDED','RESOURCE_LIMIT','RESOURCE_HEADROOM','HOST_PRESSURE'}
CODES={'USER_CANCELLED':130,'TIME_BUDGET_EXCEEDED':124,'RESOURCE_LIMIT':17,'RESOURCE_HEADROOM':17,'HOST_PRESSURE':17}


def require(ok,reason):
    if not ok:raise ValueError(reason)


def safe_directory(path):
    p=Path(path).absolute()
    require('..' not in p.parts and p.resolve(strict=True)==p and p.is_dir(),'Run path must be an existing canonical directory, without symlink aliases')
    require(not p.is_symlink(),'Linked run directory')
    return p


def checked_bytes(path,max_bytes=65536):
    path=Path(path);safe_directory(path.parent)
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    try:
        info=os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size<=max_bytes,'Invalid nonregular/large control file')
        data=os.read(fd,max_bytes+1)
        require(len(data)==info.st_size,'Control file changed while read')
        return data
    finally:os.close(fd)


def toml_bytes(value):
    lines=[]
    for k,v in sorted(value.items()):
        require(re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',k),'Invalid scalar TOML key')
        require(type(v) in (str,int,bool,float),'Control TOML only permits scalar fields')
        if type(v)is float:require(math.isfinite(v),'Nonfinite TOML value')
        lines.append(k+' = '+json.dumps(v,ensure_ascii=False,allow_nan=False))
    return ('\n'.join(lines)+'\n').encode()


def publish_first(path,data):
    """Complete temporary bytes, exclusive final link; never replace first request."""
    path=Path(path);safe_directory(path.parent)
    tmp=path.with_name('.'+path.name+'-'+uuid.uuid4().hex+'.tmp')
    with tmp.open('xb') as f:f.write(data)
    try:os.link(tmp,path)
    finally:tmp.unlink()


def atomic_json(path,value):
    data=(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
    path=Path(path);tmp=path.with_name('.'+path.name+'-'+uuid.uuid4().hex+'.tmp')
    with tmp.open('xb') as f:f.write(data)
    try:os.replace(tmp,path)
    finally:
        if tmp.exists():tmp.unlink()


def create_control(directory,*,execution_commit,source_commit,task_id,case_sha256,
                   budget_seconds,batch_deadline_unix_ns,synthetic=False,
                   grace_seconds=None,term_seconds=None,kill_seconds=None,protection_gate_sha256=None):
    directory=safe_directory(directory);now=time.time_ns()
    require(re.fullmatch('[A-Za-z0-9_-]+',directory.name),'Invalid run id')
    for value,n in [(execution_commit,40),(source_commit,40),(case_sha256,64)]:
        require(type(value)is str and re.fullmatch('[a-f0-9]{'+str(n)+'}',value),'Invalid execution/source/case identity')
    require(type(synthetic)is bool,'Invalid synthetic flag')
    require((synthetic and task_id.startswith('SYNTHETIC-')) or (not synthetic and task_id in TASKS|BOUNDARY_TASKS),'Unregistered task')
    require(type(budget_seconds) in (int,float) and math.isfinite(budget_seconds) and budget_seconds>0,'Invalid budget')
    require(budget_seconds<=10 if synthetic else budget_seconds==(TASKS|BOUNDARY_TASKS)[task_id],'Task budget differs from declaration')
    require(type(batch_deadline_unix_ns)is int and batch_deadline_unix_ns>now,'Batch deadline already exhausted')
    if not synthetic:require(batch_deadline_unix_ns-now>=300*10**9,'Less than five minutes of total budget remain')
    grace=120 if grace_seconds is None else grace_seconds;term=10 if term_seconds is None else term_seconds;kill=5 if kill_seconds is None else kill_seconds
    require((grace,term,kill)==(120,10,5) or synthetic,'Only synthetic tests may shorten escalation windows')
    require(all(type(v) in (int,float) and math.isfinite(v) and 0<v<=bound for v,bound in [(grace,120),(term,10),(kill,5)]),'Invalid escalation window')
    value=dict(schema_version=1,run_id=directory.name,worker_id='worker',execution_commit=execution_commit,
        source_commit=source_commit,task_id=task_id,case_sha256=case_sha256,nonce=uuid.uuid4().hex,
        created_unix_ns=now,created_monotonic_ns=time.monotonic_ns(),budget_seconds=budget_seconds,
        effective_deadline_unix_ns=min(now+int(budget_seconds*10**9),batch_deadline_unix_ns),
        batch_deadline_unix_ns=batch_deadline_unix_ns,limit_bytes=8*GIB,warning_bytes=7*GIB,
        remaining_growth_bytes=2*GIB,grace_seconds=grace,term_seconds=term,kill_seconds=kill,synthetic=synthetic)
    if task_id in BOUNDARY_TASKS:
        require(type(protection_gate_sha256)is str and re.fullmatch('[a-f0-9]{64}',protection_gate_sha256),
                'Boundary diagnostics require the actual protection receipt hash')
        value.update(experiment='soc-boundary-v1',timing_enabled=True,
                     validation_policy='strict' if task_id.endswith('-REF') else 'single_validation_v1',
                     protection_gate_sha256=protection_gate_sha256)
        require(source_commit==(BOUNDARY_REFERENCE if task_id.endswith('-REF') else execution_commit),
                'Boundary numerical source differs from role')
    else:
        require(protection_gate_sha256 is None,'An old timing task cannot consume a boundary authorization')
    publish_first(directory/'control.toml',toml_bytes(value))
    return load_control(directory)


def load_control(directory):
    directory=safe_directory(directory);raw=checked_bytes(directory/'control.toml');c=tomllib.loads(raw.decode())
    require(type(c.get('schema_version'))is int and c['schema_version']==1 and c.get('run_id')==directory.name and c.get('worker_id')=='worker','Control identity invalid')
    require((c.get('limit_bytes'),c.get('warning_bytes'),c.get('remaining_growth_bytes'))==(8*GIB,7*GIB,2*GIB),'Timing tasks have only fixed8/7 GiB and2 GiB growth')
    require(c.get('synthetic') is True and c.get('task_id','').startswith('SYNTHETIC-') or c.get('synthetic') is False and c.get('task_id') in TASKS|BOUNDARY_TASKS,'Control task invalid')
    require(re.fullmatch('[A-Za-z0-9_-]+',c['run_id']),'Invalid run id')
    for key,length in [('execution_commit',40),('source_commit',40),('case_sha256',64),('nonce',32)]:
        require(type(c.get(key))is str and re.fullmatch('[a-f0-9]{'+str(length)+'}',c[key]),'Invalid control identity: '+key)
    for key in ['created_unix_ns','created_monotonic_ns','effective_deadline_unix_ns','batch_deadline_unix_ns']:
        require(type(c.get(key))is int and c[key]>0,'Invalid control clock field: '+key)
    budget=c.get('budget_seconds')
    require(type(budget) in (int,float) and math.isfinite(budget) and budget>0,'Invalid control budget')
    require(budget<=10 if c['synthetic'] else budget==(TASKS|BOUNDARY_TASKS)[c['task_id']],'Changed task budget')
    if c['task_id'] in BOUNDARY_TASKS:
        ref=c['task_id'].endswith('-REF')
        require(c.get('experiment')=='soc-boundary-v1' and c.get('timing_enabled') is True and
                c.get('validation_policy')==('strict' if ref else 'single_validation_v1') and
                c['source_commit']==(BOUNDARY_REFERENCE if ref else c['execution_commit']),
                'Boundary control role/source/policy differs')
        require(type(c.get('protection_gate_sha256'))is str and
                re.fullmatch('[a-f0-9]{64}',c['protection_gate_sha256']),'Boundary protection hash missing')
    require(c['effective_deadline_unix_ns']==min(c['created_unix_ns']+int(budget*10**9),c['batch_deadline_unix_ns']) and c['effective_deadline_unix_ns']>c['created_unix_ns'],'Effective deadline differs from declared minimum')
    values=[c.get('grace_seconds'),c.get('term_seconds'),c.get('kill_seconds')]
    require(all(type(v) in (int,float) and math.isfinite(v) and 0<v<=cap for v,cap in zip(values,[120,10,5])),'Invalid bounded escalation fields')
    require(c['synthetic'] or values==[120,10,5],'Real escalation windows changed')
    c['control_sha256']=hashlib.sha256(raw).hexdigest()
    return c


def read_request(directory,c):
    path=Path(directory)/'stop-request.toml'
    require(not path.is_symlink(),'Linked stop request refused')
    if not path.exists():return None
    raw=checked_bytes(path);r=tomllib.loads(raw.decode())
    for k in ['run_id','execution_commit','source_commit','nonce','control_sha256']:
        require(r.get(k)==c[k],'Stop request belongs to another run/version: '+k)
    require(r.get('schema_version')==1 and type(r.get('schema_version'))is int and r.get('reason') in REASONS,'Stop request reason/schema invalid')
    stamp=r.get('requested_unix_ns');now=time.time_ns()
    require(type(stamp)is int and c['created_unix_ns']<=stamp<=now+10**9,'Stale/future stop request')
    require(type(r.get('request_id'))is str and re.fullmatch('[a-f0-9]{32}',r['request_id']) and type(r.get('detail'))is str and r['detail'],'Invalid stop request detail/id')
    r['request_sha256']=hashlib.sha256(raw).hexdigest();return r


def request_stop(directory,*,run_id,execution_commit,reason='USER_CANCELLED',detail='User requested cancellation',internal=False):
    directory=safe_directory(directory);c=load_control(directory)
    require(c['run_id']==run_id and c['execution_commit']==execution_commit,'Requested run/version does not match')
    require(reason in REASONS and (reason=='USER_CANCELLED' or internal),'Only supervisor may issue non-user reasons')
    existing=read_request(directory,c)
    if existing:return existing
    if (directory/'result.json').exists():
        rec=json.loads(checked_bytes(directory/'result.json',1024*1024))
        require(rec.get('execution_status') in ('RUNNING','INCOMPLETE'),'Run is already terminal')
    r={k:c[k] for k in ['run_id','execution_commit','source_commit','nonce','control_sha256']}
    r.update(schema_version=1,reason=reason,detail=detail,requested_unix_ns=time.time_ns(),request_id=uuid.uuid4().hex)
    try:publish_first(directory/'stop-request.toml',toml_bytes(r))
    except FileExistsError:pass
    return read_request(directory,c)


def _module(relative,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/relative);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod


def worker_contract(value,code,c,directory):
    require(type(value)is dict,'Worker receipt missing or not an object')
    for k in ['run_id','execution_commit','source_commit','task_id','case_sha256','control_sha256']:
        require(value.get(k)==c[k],'Worker identity mismatch: '+k)
    require(type(value.get('schema_version'))is int and value['schema_version']==1,'Unsupported worker schema')
    require(type(code)is int and type(value.get('exit_code'))is int and value['exit_code']==code,'Worker/process exit mismatch')
    boundary=c['task_id'] in BOUNDARY_TASKS
    if boundary:
        for key in ('experiment','timing_enabled','validation_policy','protection_gate_sha256'):
            require(type(value.get(key))is type(c[key]) and value[key]==c[key],'Boundary worker contract differs: '+key)
    require(not (Path(directory)/'worker/final.bin').exists(),'Timing diagnostic must not publish final.bin')
    status=value.get('execution_status');request=read_request(directory,c)
    if code==0:
        require(status=='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED' and value.get('completed_maps')==2 and type(value.get('completed_maps'))is int,'Zero exit is only a two-map diagnostic, never SCF PASS')
        require(request is None,'A latched stop cannot publish diagnostic completion')
        require(value.get('runtime_closed') is True and value.get('workspace_released') is True,'Diagnostic runtime/owned storage cleanup unconfirmed')
        if not c['synthetic']:
            require(type(value.get('environment'))is dict and value['environment'].get('status')=='PASS','Diagnostic environment identity failed')
            parallel=value.get('parallelism')
            require(parallel=={'julia':1,'blas':1,'fft':1,'mpi':1} and all(type(v)is int for v in parallel.values()),'Diagnostic parallelism changed')
            require(value.get('map_checks_passed') is True and value.get('runtime_dispatch_status')=='PASS','Original scientific/dispatch checks missing')
            before=value.get('runtime_before_close');after=value.get('runtime_after_close')
            require(type(before)is dict and before.get('backend')=='soc-core','Owned runtime not recorded')
            counts=before.get('counters',{})
            require(all(type(counts.get(k))is int and counts[k]>0 for k in ['fr_mul_calls','component_mul_calls','full_mul_calls']),'Actual core dispatch not exercised')
            require(type(after)is dict and after.get('closed') is True and after.get('workspace_released') is True and after.get('owned_source_entries')==0,'Owned storage release not confirmed')
            if boundary and c['validation_policy']=='single_validation_v1':
                for label,summary in [('before',before),('after',after)]:
                    validation=summary.get('validation')
                    require(type(validation)is dict and validation.get('policy')=='single_validation_v1' and
                            validation.get('counter_status')=='MEASURED_OPT_IN' and validation.get('active') is False and
                            type(validation.get('live_array_entries'))is int and validation['live_array_entries']==0 and
                            type(validation.get('live_source_entries'))is int and validation['live_source_entries']==0,
                            'Candidate validation scope/release unconfirmed: '+label)
                require(after['validation'].get('closed') is True,'Candidate validation state not closed')
                counters=before['validation'].get('counters')
                require(type(counters)is dict and type(counters.get('validation_calls'))is int and
                        counters['validation_calls']>0,'Candidate validation dispatch not exercised')

    elif status in CODES:
        require(code==CODES[status] and request is not None and request['reason']==status,'Stop/native reason mismatch')
        control=value.get('control')
        require(type(control)is dict and control.get('first_request_sha256')==request['request_sha256'] and control.get('acknowledged_boundary'),'Worker did not acknowledge same request')
        closed=value.get('runtime_closed') is True and value.get('workspace_released') is True
        unconstructed=(value.get('runtime_state')=='NOT_CONSTRUCTED' and value.get('context_constructed') is False and
                       value.get('owned_runtime_constructed') is False and value.get('runtime_closed') is False and value.get('workspace_released') is False)
        require(closed or unconstructed,'Cooperative cleanup unconfirmed')
    else:
        require(status=='FAIL' and code>0 and type(value.get('reason'))is str and value['reason'],'Undeclared worker failure')
    return value


def launch_worker(command,directory,env=None,*,resources=None):
    directory=safe_directory(directory);c=load_control(directory);initial_bytes=checked_bytes(directory/'control.toml')
    require(not any((directory/n).exists() for n in ['result.json','process-start.json','resource.json']),'Run was already started; preserve prior receipt')
    publish_first(directory/'launch.toml',toml_bytes(dict(run_id=c['run_id'],execution_commit=c['execution_commit'],started_unix_ns=time.time_ns())))
    sys.path.insert(0,str(ROOT/'scripts'))
    import si_qe_reference_evidence as tool
    from run_qe_soc import execute
    resources=resources or _module('benchmarks/soc-extra-v1/resources.py','timing_resources')
    state={k:c[k] for k in ['run_id','execution_commit','source_commit','task_id','case_sha256','control_sha256']}
    if c['task_id'] in BOUNDARY_TASKS:
        state.update({k:c[k] for k in ['experiment','validation_policy','timing_enabled','protection_gate_sha256']})
    state.update(schema_version=1,execution_status='RUNNING',exit_code=9,native_exit_code=None,worker_exit_code=None,started_unix_ns=time.time_ns())
    atomic_json(directory/'result.json',state)
    env=dict(os.environ if env is None else env,SOC_TIMING_CONTROL_FILE=str(directory/'control.toml'),SOC_TIMING_STOP_FILE=str(directory/'stop-request.toml'))
    first=[None];pressure=[0,None];highwater=[None];last_request=[None]
    rules=resources.validate_policy(dict(schema_version=1,policy_id='extra-default-8gib-v2',limit_bytes=8*GIB,warning_bytes=7*GIB,remaining_growth_bytes=2*GIB))
    def current_request():
        require(checked_bytes(directory/'control.toml')==initial_bytes,'Bound control file changed during worker')
        r=read_request(directory,c)
        if first[0] is not None:require(r is not None and r['request_sha256']==first[0],'Latched request changed or removed')
        if r is not None:first[0]=r['request_sha256'];last_request[0]=r
        return r
    def control(sample):
        r=current_request()
        # Both are independent parent clocks. max catches host sleep missed by monotonic;
        # a backwards UTC adjustment never extends the monotonic budget.
        elapsed=max(time.monotonic_ns()-c['created_monotonic_ns'],time.time_ns()-c['created_unix_ns'])
        allowed=c['effective_deadline_unix_ns']-c['created_unix_ns']
        if r is None and elapsed>=allowed:
            r=request_stop(directory,run_id=c['run_id'],execution_commit=c['execution_commit'],reason='TIME_BUDGET_EXCEEDED',detail='Independent parent deadline exhausted',internal=True)
            current_request()
        if r and r['reason'] in ('USER_CANCELLED','TIME_BUDGET_EXCEEDED'):
            return dict(status='REQUEST_STOP',reason=r['reason'],request_sha256=r['request_sha256'],request_id=r['request_id'])
        return dict(status='CONTINUE')
    def resource(sample):
        now=sample['monotonic_seconds']
        if pressure[1] is None or now-pressure[0]>=2:pressure[:]=[now,resources.host_pressure()]
        hp=directory/'resource-highwater.toml'
        if hp.exists():
            h=tomllib.loads(checked_bytes(hp).decode())
            for key in ['run_id','execution_commit','control_sha256']:require(h.get(key)==c[key],'Highwater belongs to another run')
            require(h.get('units')=='bytes' and type(h.get('highwater_bytes'))is int and h['highwater_bytes']>0,'Invalid worker highwater')
            require(highwater[0] is None or h['highwater_bytes']>=highwater[0],'Worker highwater decreased')
            highwater[0]=h['highwater_bytes']
        r=current_request();latched=None
        if r and r['reason']=='RESOURCE_HEADROOM':latched=dict(status='STOP_AT_SAFE_BOUNDARY',reason=r['detail'])
        decision=resources.monitor_decision(sample['current_group_rss_bytes'],policy=rules,
            peak_group_rss_bytes=sample['peak_group_rss_bytes'],worker_highwater_bytes=highwater[0],pressure=pressure[1],stop_request=latched)
        if decision['status'] in ('STOP_AT_SAFE_BOUNDARY','RESOURCE_LIMIT'):
            reason='RESOURCE_HEADROOM' if decision['status']=='STOP_AT_SAFE_BOUNDARY' else 'HOST_PRESSURE' if pressure[1].get('severe') else 'RESOURCE_LIMIT'
            request_stop(directory,run_id=c['run_id'],execution_commit=c['execution_commit'],reason=reason,detail=decision['reason'],internal=True)
        return decision
    try:
        native,res=tool.monitored_execute(execute,command,directory,env,limit_bytes=8*GIB,observation_callback=resource,
            cooperative_callback=control,cooperative_grace_seconds=c['grace_seconds'],termination_grace_seconds=c['term_seconds'],cleanup_grace_seconds=c['kill_seconds'])
        state.update(native_exit_code=native,resource=res,forced_termination=res.get('forced_termination',False))
        path=directory/'worker/result.json'
        require(path.exists(),'Worker receipt missing')
        raw=checked_bytes(path,2*1024*1024);value=json.loads(raw)
        state['worker_exit_code']=value.get('exit_code') if type(value)is dict else None
        worker_contract(value,native,c,directory)
        require(res.get('owned_process_cleanup_status')=='PASS','Owned-process cleanup unconfirmed')
        if native==0:require(res.get('status')=='PASS','Resource/supervision failure cannot publish diagnostic success')
        state.update(execution_status=value['execution_status'],exit_code=native,worker=value,worker_result_sha256=hashlib.sha256(raw).hexdigest())
    except BaseException as error:
        for name,key in [('process-exit.json','native'),('resource.json','resource')]:
            try:state[key]=json.loads(checked_bytes(directory/name,2*1024*1024))
            except (OSError,ValueError):pass
        if type(state.get('native'))is dict:state['native_exit_code']=state['native'].get('exit_code')
        forced=state.get('resource',{}).get('forced_termination',False)
        negative=type(state.get('native_exit_code'))is int and state['native_exit_code']<0
        state.update(execution_status='FORCED_TERMINATION' if forced else 'NATIVE_SIGNAL_EXIT' if negative else 'FAIL',
                     forced_termination=forced,exit_code=9,reason=type(error).__name__+': '+str(error))
    finally:
        state['finished_unix_ns']=time.time_ns()
        try:
            state['stop_request']=read_request(directory,c)
            state['control_unchanged']=checked_bytes(directory/'control.toml')==initial_bytes
            require(state['control_unchanged'],'Control changed after worker')
        except (ValueError,OSError) as error:
            state.update(execution_status='FAIL',exit_code=9,control_error=str(error),stop_request=last_request[0])
        try:atomic_json(directory/'result.json',state)
        except BaseException as error:
            print('PERSISTENCE FAILURE: '+str(error),file=sys.stderr);print(json.dumps(dict(state,execution_status='FAIL',exit_code=9),default=str),file=sys.stderr);return 9,state
    return state['exit_code'],state


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    q=sub.add_parser('stop');q.add_argument('--run-dir',type=Path,required=True);q.add_argument('--run-id',required=True);q.add_argument('--execution-commit',required=True);q.add_argument('--detail',default='User requested cancellation')
    args=p.parse_args()
    try:
        r=request_stop(args.run_dir,run_id=args.run_id,execution_commit=args.execution_commit,detail=args.detail)
        print(json.dumps({'status':'REQUESTED','request_id':r['request_id'],'reason':r['reason']}));return 0
    except (ValueError,OSError) as e:print(str(e),file=sys.stderr);return 9

if __name__=='__main__':sys.exit(main())
