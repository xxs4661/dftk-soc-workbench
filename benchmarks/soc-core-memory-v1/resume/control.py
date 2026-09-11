#!/usr/bin/env python3
"""One fixed Phase9A continuation: byte/source inheritance, never numerical work."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import datetime
import tomllib

ROOT=Path(__file__).resolve().parents[3]
RESUME_FROM='98781fd0ce6c2f4138ed010e115a13e370410d58'
STATIC='1b42a27063ca65757d2c4f34d46fe4f1cd9929ed'
PREPARATION='234fe85d4e9386d9889bd1af256a28394ba88089'
PLAN='benchmarks/soc-core-memory-v1/resume/plan.json'
PLAN_SHA='87a3083988c682c321d753dfa7a9251897dd8b87c3b897c5dcf5a2cdde156af5'
RESUME_ID='phase9a-completion-20260910'
ACTIONS={'OPT-B0-SCF':2,'OPT-B0-GAMMA':1}

# Reviewed routing bytes, in addition to the immutable numerical-region checks.
APPROVED_ROUTING_SHA256={'scripts/run_si_dftk.py': 'c477aae0cc6909b616126cd5c512f502d0c2d6296197d470fbd5d9a23e568dbb', 'scripts/run_si_soc.jl': '110fd055dc2063dae3f9910e1d0044b52b9f33c6d5a8d6d3ce6729c5cd788bc2', 'benchmarks/soc-core-memory-v1/endpoint_metrics.py': '5dcda768706fb42f47ecf6437f2f8dff48d84e82e6d8a3956c1499b66228933a', 'benchmarks/soc-core-memory-v1/endpoint_compare.jl': '253803b7f6402d96602dc1a2ce1b101bf576e5ea9f9f679138fedd8c3848ef91'}
APPROVED_NEW_EXECUTABLES={"benchmarks/soc-core-memory-v1/resume/control.py", "benchmarks/soc-core-memory-v1/resume/replay.py", "tests/soc_core_memory/resume/test_control.py", "tests/soc_core_memory/resume/test_driver.py", "tests/soc_core_memory/resume/test_driver_entry.jl", "tests/soc_core_memory/resume/test_endpoint_compare_source.py", "tests/soc_core_memory/resume/test_endpoint_compare_bridge.jl"}


def require(ok,reason):
    if not ok:raise ValueError(reason)


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def read(path):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    def invalid(v):raise ValueError('Nonfinite JSON: '+v)
    return json.loads(Path(path).read_text(),object_pairs_hook=pairs,parse_constant=invalid)


def git(root,*args):return subprocess.check_output(['git','-C',str(root),*args])
def module(root,path,name):
    spec=importlib.util.spec_from_file_location(name,Path(root)/path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def launcher(root):
    sys.path.insert(0,str(Path(root)/'scripts'))
    return module(root,'scripts/run_si_dftk.py','phase9a_resumed_launcher_contract')

def plan(root):
    p=Path(root)/PLAN
    require(digest(p)==PLAN_SHA and p.read_bytes()==git(root,'show',PREPARATION+':'+PLAN),'Frozen continuation plan changed')
    readme=Path(root)/'benchmarks/soc-core-memory-v1/resume/README.md'
    require(readme.read_bytes()==git(root,'show',PREPARATION+':benchmarks/soc-core-memory-v1/resume/README.md'),'Continuation preparation README changed')
    return read(p)

def confined(root,relative):
    root=Path(root).resolve();part=Path(relative)
    if part.is_absolute():
        require(root in part.parents,'Path outside workbench');part=part.relative_to(root)
    require('..' not in part.parts,'Unconfined evidence path');path=root/part
    require(path.is_file() and not path.is_symlink() and path.resolve()==path,'Missing or aliased evidence: '+str(part))
    return path

def bound(root,entry):
    require(isinstance(entry,dict),'Missing descriptor');p=confined(root,entry['path'])
    require(digest(p)==entry['sha256'],'Evidence changed: '+entry['path'])
    if 'bytes' in entry:require(type(entry['bytes']) is int and p.stat().st_size==entry['bytes'],'Evidence size changed')
    return p

def descriptor(root,path):
    p=Path(path);return dict(path=p.relative_to(root).as_posix(),sha256=digest(p),bytes=p.stat().st_size)

def tree(root,commit):
    out={}
    for row in git(root,'ls-tree','-r','-z',commit).split(b'\0'):
        if not row:continue
        prefix,name=row.split(b'\t');mode,kind,oid=prefix.decode().split()
        require(kind=='blob' and mode in ('100644','100755'),'Unexpected linked/submodule source')
        out[name.decode()]=oid
    return out

def chunk(text,start,end):
    require(text.count(start)==1,'Ambiguous numerical region start');i=text.index(start)
    return text[i:text.index(end,i)]

def source_proof(root,execution,*,clean=True):
    root=Path(root).resolve();p=plan(root)
    require(len(execution)==40 and all(c in '0123456789abcdef' for c in execution),'Exact execution SHA required')
    if clean:
        require(git(root,'rev-parse','HEAD').decode().strip()==execution,'Wrong actual endpoint HEAD')
        require(not git(root,'status','--porcelain','--untracked-files=all').strip(),'Clean endpoint execution tree required')
    subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',RESUME_FROM,execution],check=True,capture_output=True)
    trees={c:tree(root,c) for c in (STATIC,RESUME_FROM,execution)};before=trees[RESUME_FROM];current=trees[execution]
    for path,sha in APPROVED_ROUTING_SHA256.items():
        require(digest(root/path)==sha,'Unreviewed driver routing bytes: '+path)
    allowed=set(p['allowed_existing_code'])|set(p['allowed_navigation']);numeric={};changes=[]
    require(set(before)<=set(current),'Preexisting files deleted')
    for path,oid in current.items():
        local=confined(root,path);data=local.read_bytes()
        require(hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==oid,'Uncommitted actual source: '+path)
        if path in before and before[path]!=oid:
            require(path in allowed,'Unauthorized changed preexisting file: '+path)
            changes.append(dict(path=path,partial_blob=before[path],endpoint_blob=oid,scope=p['allowed_existing_code'].get(path,'Current navigation only')))
        if path not in before:
            require(any(path.startswith(v) for v in p['allowed_new_paths']),'Unauthorized new execution file: '+path)
            if Path(path).suffix in ('.py','.jl','.sh'):
                require(path in APPROVED_NEW_EXECUTABLES,'Unreviewed new executable/dispatch file: '+path)
        isnum=path.startswith(('src/','prototypes/')) or path.startswith('scripts/') and path.endswith('.jl') and path!='scripts/run_si_soc.jl'
        if isnum:
            require(path in trees[STATIC] and oid==trees[STATIC][path]==before[path],'Changed measured numerical implementation: '+path)
            numeric[path]=hashlib.sha256(data).hexdigest()
    require(set(k for k in trees[STATIC] if k.startswith(('src/','prototypes/')))==set(k for k in current if k.startswith(('src/','prototypes/'))),'Numerical source set changed')
    driver=(root/'scripts/run_si_soc.jl').read_text();regions=[]
    for r in p['numerical_driver_regions']:
        actual=hashlib.sha256(chunk(driver,r['start'],r['end']).encode()).hexdigest()
        require(actual==r['sha256'],'Driver numerical region changed: '+r['name']);regions.append(dict(name=r['name'],sha256=actual))
    metrics='benchmarks/soc-core-memory-v1/endpoint_metrics.py'
    original=git(root,'show',RESUME_FROM+':'+metrics).decode();now=(root/metrics).read_text()
    require(chunk(original,'def evaluate(','\ndef main(')==chunk(now,'def evaluate(','\ndef main('),'Endpoint numerical evaluation changed')
    oldgate=git(root,'show',RESUME_FROM+':scripts/run_si_dftk.py').decode();nowgate=(root/'scripts/run_si_dftk.py').read_text()
    require(chunk(oldgate,'def verify_core_gate(','\ndef validate_core_worker(')==chunk(nowgate,'def verify_core_gate(','\ndef validate_core_worker('),'Default gate identity rule changed')
    compare='benchmarks/soc-core-memory-v1/endpoint_compare.jl';oldc=git(root,'show',RESUME_FROM+':'+compare).decode();nowc=(root/compare).read_text()
    require(chunk(oldc,'        accuracy=','        result["sources"]')==chunk(nowc,'        accuracy=','        result["sources"]'),'Endpoint density norm/threshold changed')
    return dict(status='PASS',numerical_sources=numeric,numerical_driver_regions=regions,
        measured_to_partial_diff=p['accepted_static_to_partial_diff'],partial_to_endpoint_diff=changes,
        new_files=sorted(set(current)-set(before)),default_gate_rule='UNCHANGED',endpoint_numerical_functions='UNCHANGED',
        static_execution_commit=STATIC,endpoint_execution_commit=execution)


def old_failure(root,p):
    f=p['old_failure'];d=Path(root)/f['directory'];slot=confined(root,f['slot']);r=read(d/'receipt.json')
    require(read(slot)==dict(run_id=f['run_id'],execution_commit=STATIC),'Old first-attempt slot changed')
    require(r['execution_commit']==STATIC and r['run_id']==f['run_id'] and r['execution_status']=='FAIL' and type(r['exit_code']) is int and r['exit_code']==9 and type(r['worker_exit_code']) is int and r['worker_exit_code']==1,'Original failed attempt changed')
    public=read(Path(root)/'results/soc-core-memory/endpoints/endpoint-status.json');verified=[]
    for path,entry in public['raw_sources'].items():
        q=bound(root,dict(path=path,**entry));verified.append(descriptor(root,q))
    require(not (Path(root)/'.work/phase9a/endpoints/slots/OPT-B0-GAMMA.json').exists(),'Unexpected prior Gamma attempt')
    return dict(status='PASS',run_id=f['run_id'],native_exit_code=1,recorder_exit_code=9,stage=f['stage'],files=verified)


def static_proof(root,p,gate):
    root=Path(root);driver=launcher(root);g=confined(root,gate)
    require(g.relative_to(root).as_posix()==p['static_gate']['path'] and digest(g)==p['static_gate']['sha256'],'Different original static gate')
    driver.verify_core_gate(root,g,STATIC)
    replay=module(root,'scripts/replay_soc_core_memory.py','phase9a_original_static_arithmetic')
    result=replay.replay(root,root/'results/soc-core-memory/static-evidence.json')
    require(result['assessment_status']=='PASS' and result['time_status']=='PERFORMANCE_REVIEW_REQUIRED','Original static assessment changed')
    record=read(g);files=[descriptor(root,g)]
    for entry in record['suite_receipts'].values():
        q=bound(root,entry);w=read(q.parent/'worker-result.json');files.append(descriptor(root,q))
        for raw in [q.parent/'worker-result.json',q.parent/'process-exit.json',q.parent/'resource.json']:files.append(descriptor(root,raw))
        for k in ['canonical_inputs',*(['canonical_operators'] if 'canonical_operators' in w else [])]:
            e=w[k];raw=bound(root,dict(e,path=(q.parent/e['path']).relative_to(root).as_posix()));files.append(descriptor(root,raw))
        for e in w['outputs'].values():
            raw=bound(root,dict(e,path=(q.parent/e['path']).relative_to(root).as_posix()));files.append(descriptor(root,raw))
    for key in ('comparison','performance','replay_data'):files.append(descriptor(root,bound(root,record[key])))
    comparison=read(bound(root,record['comparison']))
    for pair in comparison['pairs']:
        q=bound(root,pair['reference_operators']);export=read(q);files.append(descriptor(root,q))
        e=export['operators'];files.append(descriptor(root,bound(root,dict(e,path=(q.parent/e['path']).relative_to(root).as_posix()))))
    return dict(status='STATIC_EVIDENCE_REUSED_UNCHANGED_CORE',arithmetic=result,files=files)


def environment_inputs(root):
    root=Path(root);lock=tomllib.loads((root/'config/sources.lock').read_text());out={}
    for name in ('dftk','pseudopotentialio'):
        s=lock['source'][name];q=root/s['checkout'];commit=git(q,'rev-parse','HEAD').decode().strip()
        require(commit==s['commit'] and not git(q,'status','--porcelain','--untracked-files=all').strip(),'Frozen checkout identity changed: '+name)
        out[name]=dict(commit=commit,worktree_status='clean',checkout=s['checkout'])
    driver=launcher(root);source=driver.verify_preparation(root)
    depot=os.environ.get('JULIA_DEPOT_PATH','').split(os.pathsep)
    require(all(v and Path(v).is_dir() for v in depot),'Explicit existing depot required')
    require(os.environ.get('JULIA_NUM_THREADS')=='1' and os.environ.get('OPENBLAS_NUM_THREADS')=='1' and os.environ.get('OMP_NUM_THREADS')=='1','Prescribed thread environment required')
    sources=read(root/'benchmarks/soc-core-memory-v1/sources.json');old=sources['historical_endpoints']['B0'];d=root/old['directory']
    require(digest(d/'final.bin')==old['checkpoint_sha256'] and (d/'final.bin').stat().st_size==old['checkpoint_bytes'] and digest(d/'result.json')==old['raw_result_sha256'],'Original B0 checkpoint unavailable/changed')
    require('results/si-soc-splitting/D-spectrum.json' in tree(root,RESUME_FROM),'Canonical Git spectrum path missing')
    return dict(checkouts=out,files={v:digest(root/v) for v in ('environment/workbench/Project.toml','environment/workbench/Manifest.toml','config/sources.lock','environment/workbench/checksums.toml','benchmarks/si-soc-splitting-v1/source.json','benchmarks/si-soc-splitting-v1/case.json','results/si-soc-splitting/D-spectrum.json','results/si-soc-splitting/D-SCF.json')},
        pseudo_sha256=source['sha256'],depot_paths=depot,parallelism=dict(julia=1,blas=1,fft=1,mpi=1),historical_checkpoint_sha256=old['checkpoint_sha256'])


def authorization_path(root):return Path(root)/'.work/phase9a/resume-authorizations'/PREPARATION/'authorization.json'

def make_payload(root,execution,gate):
    root=Path(root).resolve();p=plan(root);proof=source_proof(root,execution)
    return dict(schema_version=1,phase='9A',resume_id=RESUME_ID,resume_from_commit=RESUME_FROM,original_stage_base=p['original_stage_base'],
        static_execution_commit=STATIC,reference_execution_commit=p['reference_execution_commit'],reference_scientific_commit=p['reference_scientific_commit'],
        resume_preparation_commit=PREPARATION,endpoint_execution_commit=execution,core_gate_path=p['static_gate']['path'],core_gate_sha256=p['static_gate']['sha256'],
        source_proof=proof,static_proof=static_proof(root,p,gate),old_failure=old_failure(root,p),environment_inputs=environment_inputs(root),attempts=ACTIONS,
        status='STATIC_EVIDENCE_REUSED_UNCHANGED_CORE',time_status='PERFORMANCE_REVIEW_REQUIRED')

def issue(root,execution,gate):
    root=Path(root).resolve();out=authorization_path(root);require(not out.exists(),'Continuation authorization already issued; verify/reuse without reissuing')
    payload=make_payload(root,execution,gate);payload['issued_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    require(shutil.disk_usage(root).free>=10*1024**3,'Insufficient disk reserve')
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x') as f:json.dump(payload,f,indent=2,allow_nan=False);f.write('\n')
    return verify_authorization(root,out,execution,gate)

def verify_authorization(root,path,execution_commit,gate_path):
    root=Path(root).resolve();actual=confined(root,path)
    require(actual==authorization_path(root),'Only this preparation authorization identity is accepted')
    receipt=read(actual);fresh=make_payload(root,execution_commit,gate_path)
    require({k:v for k,v in receipt.items() if k!='issued_utc'}==fresh,'Continuation authorization no longer matches source/static/input/environment')
    require(isinstance(receipt.get('issued_utc'),str),'Missing issue time')
    return dict(receipt,authorization_sha256=digest(actual),authorization_path=actual.relative_to(root).as_posix())

def resume_fields(auth,action):
    require(action in ACTIONS,'Wrong continuation action')
    return dict(resume_id=auth['resume_id'],resume_from_commit=auth['resume_from_commit'],resume_preparation_commit=auth['resume_preparation_commit'],
        static_execution_commit=auth['static_execution_commit'],resume_authorization_sha256=auth['authorization_sha256'],attempt=ACTIONS[action])

def verify_worker_resume(record,auth,action):
    for k,v in resume_fields(auth,action).items():require(type(record.get(k)) is type(v) and record[k]==v,'Worker/parent continuation field differs: '+k)
    require(record.get('execution_commit')==auth['endpoint_execution_commit'] and record.get('core_gate_sha256')==auth['core_gate_sha256'],'Wrong continuation E/gate')

def reservation_directory(root,auth):
    require(auth.get('resume_id')==RESUME_ID and auth.get('resume_preparation_commit')==PREPARATION and auth.get('attempts')==ACTIONS,'Arbitrary continuation namespace refused')
    return Path(root)/'.work/phase9a/endpoints/resume-slots'/PREPARATION

def validate_entry_receipt(root,auth):
    root=Path(root).resolve();manifest=read(authorization_path(root).with_name('entry-check.json'))
    require(type(manifest.get('schema_version')) is int and manifest['schema_version']==1 and manifest.get('phase')=='9A' and manifest.get('endpoint_execution_commit')==auth['endpoint_execution_commit'] and manifest.get('resume_authorization_sha256')==auth['authorization_sha256'],'Missing current entry preflight binding')
    outerpath=bound(root,manifest['launcher_receipt']);workerpath=bound(root,manifest['worker_result']);outer=read(outerpath);worker=read(workerpath)
    require(workerpath==outerpath.parent/outer['worker_directory']/'result.json' and digest(workerpath)==outer['worker_result_sha256'],'Entry worker binding differs')
    for r in (outer,worker):
        verify_worker_resume(r,auth,'OPT-B0-SCF')
        require(r.get('check_only') is True and r.get('execution_status')=='CHECK_ONLY_PASS' and r.get('check_status')=='PASS' and r.get('numerical_execution_status')=='NOT_RUN' and r.get('formal_slot_reserved') is False and type(r.get('exit_code')) is int and r['exit_code']==0,'Entry preflight is not a complete nonphysical success')
    require(outer.get('worker_started') is False and outer.get('check_process_started') is True and type(outer.get('worker_exit_code')) is int and outer['worker_exit_code']==0,'Entry process not completed')
    launcher(root).core_tools(root).resource_contract(outer['resource'],outer['worker_exit_code'])
    driver=launcher(root)
    driver.validate_entry_worker(worker,0,'OPT-B0-SCF',outer['worker_directory'],root=root,execution_commit=auth['endpoint_execution_commit'],auth=auth)
    process_proof(root,outerpath,outer)
    require(worker.get('environment',{}).get('julia_version')=='1.12.7','Entry Julia version differs')
    for path,sha in worker['executed_source_sha256'].items():
        require(digest(confined(root,path))==sha,'Entry loaded source bytes changed: '+path)
    return dict(status='PASS',manifest_sha256=digest(authorization_path(root).with_name('entry-check.json')))



def process_proof(root,outerpath,outer):
    directory=Path(outerpath).parent
    native=read(directory/'process-exit.json');resource=read(directory/'resource.json')
    require(type(native.get('exit_code')) is int and native['exit_code']==0 and native.get('interrupted') is False,'Missing/failed/interrupted native exit')
    require(type(outer.get('worker_exit_code')) is int and outer['worker_exit_code']==native['exit_code'] and outer.get('resource')==resource,'Native process/resource binding differs')
    launcher(root).core_tools(root).resource_contract(resource,native['exit_code'])
    return [descriptor(root,directory/name) for name in ('process-start.json','process-exit.json','resource.json')]


def verify_endpoints(root,path,execution,scf,gamma):
    root=Path(root).resolve();raw=read(confined(root,path))
    auth=verify_authorization(root,path,execution,raw['core_gate_path']);validate_entry_receipt(root,auth)
    driver=launcher(root);bindings={};values={}
    for action,argument in (('OPT-B0-SCF',scf),('OPT-B0-GAMMA',gamma)):
        q=confined(root,argument);outer=read(q);verify_worker_resume(outer,auth,action)
        require(q.name=='receipt.json' and q.parent.name==outer['run_id'] and root/'.work/phase9a/endpoints' in q.parents,'Wrong endpoint directory')
        require(outer.get('action')==action and outer.get('backend')=='soc-core' and outer.get('execution_status')=='PASS' and type(outer.get('exit_code')) is int and outer['exit_code']==0 and outer.get('worker_started') is True,'Endpoint recorder failed')
        require(outer.get('worker_directory')==outer['run_id']+'-dftk','Wrong endpoint worker directory')
        workerpath=confined(root,q.parent/outer['worker_directory']/'result.json');worker=read(workerpath)
        require(digest(workerpath)==outer['worker_result_sha256'],'Endpoint worker changed')
        processfiles=process_proof(root,q,outer)
        driver.validate_core_worker(worker,0,action,outer['worker_directory'],root=root,execution_commit=execution,gate_sha256=auth['core_gate_sha256'],resume_auth=auth)
        for source,sha in worker['executed_source_sha256'].items():require(digest(confined(root,source))==sha,'Executed endpoint source changed: '+source)
        reservation=reservation_directory(root,auth)/(action+'.json');slot=read(reservation)
        verify_worker_resume(dict(slot,core_gate_sha256=auth['core_gate_sha256']),auth,action)
        require(slot.get('run_id')==outer['run_id'],'Endpoint reservation differs')
        values[action]=(outer,worker,workerpath)
        bindings[action]=dict(recorder=descriptor(root,q),worker=descriptor(root,workerpath),reservation=descriptor(root,reservation),process=processfiles)
    _,s,sp=values['OPT-B0-SCF'];_,g,gp=values['OPT-B0-GAMMA']
    parent=driver.checked_core_parent(sp.parent.parent,root=root,execution_commit=execution,gate_sha256=auth['core_gate_sha256'],resume_auth=auth)
    checkpoint=parent/'final.bin'
    require(g['source_scf_run_id']==s['run_id'] and g['parent_result_sha256']==digest(sp) and g['parent_checkpoint_sha256']==s['checkpoint_sha256']==digest(checkpoint),'Wrong Gamma parent result/checkpoint')
    require(g['density_source_sha256']==s['final']['n_out_sha256'],'Wrong Gamma final density')
    bindings['OPT-B0-SCF']['checkpoint']=descriptor(root,checkpoint)
    return dict(status='PASS',endpoint_execution_commit=execution,authorization_sha256=auth['authorization_sha256'],resume_id=RESUME_ID,resume_preparation_commit=PREPARATION,resume_from_commit=RESUME_FROM,static_execution_commit=STATIC,core_gate_sha256=auth['core_gate_sha256'],endpoint_bindings=bindings)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='mode',required=True)
    for mode in ('issue','verify'):
        p=sub.add_parser(mode);p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--execution-commit',required=True);p.add_argument('--gate',required=True)
        if mode=='verify':p.add_argument('--authorization',required=True)
    p=sub.add_parser('verify-endpoints');p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--execution-commit',required=True);p.add_argument('--authorization',required=True);p.add_argument('--scf',required=True);p.add_argument('--gamma',required=True)
    a=parser.parse_args(argv)
    try:
        if a.mode=='verify-endpoints':result=verify_endpoints(a.root,a.authorization,a.execution_commit,a.scf,a.gamma)
        else:result=issue(a.root,a.execution_commit,a.gate) if a.mode=='issue' else verify_authorization(a.root,a.authorization,a.execution_commit,a.gate)
        print(json.dumps(result,allow_nan=False));return 0
    except Exception as e:
        print(json.dumps(dict(status='FAIL',exit_code=9,reason=type(e).__name__+': '+str(e)),allow_nan=False));return 9
if __name__=='__main__':sys.exit(main())
