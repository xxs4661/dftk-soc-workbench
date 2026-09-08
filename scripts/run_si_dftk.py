#!/usr/bin/env python3
"""Durable single-attempt launcher for the prescribed Si Julia tasks only."""
import argparse
import datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from run_qe_soc import digest, write_json, require

ROOT=Path(__file__).resolve().parents[1]
PREPARATION='e5b940c7fb0234d4cb97572ee3f8225e9e8b6087'
ACTIONS=('prepare','static','D-SCF','D-SPECTRUM','D-NULL-GAMMA')
PREP_FILES=('source.json','case.json','plan.json','qe-scf.in','qe-spectrum.in')

def verify_preparation(root=ROOT):
    import hashlib
    for name in PREP_FILES:
        path='benchmarks/si-soc-splitting-v1/'+name
        frozen=subprocess.check_output(['git','show',PREPARATION+':'+path],cwd=root)
        require(hashlib.sha256(frozen).hexdigest()==digest(root/path),'Predeclared input changed: '+name)
    source=json.loads((root/'benchmarks/si-soc-splitting-v1/source.json').read_text())
    data=(root/source['local_path']).read_bytes()
    require(len(data)==source['bytes'] and hashlib.sha256(data).hexdigest()==source['sha256'],'Runtime UPF identity mismatch')
    require(hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==source['git_blob_sha1'],'Runtime UPF Git blob mismatch')
    return source

def validate_worker(record,code,action,run_id):
    require(isinstance(record,dict),'Worker record is not an object')
    require(type(record.get('exit_code')) is int and record['exit_code']==code,'Worker/process exit mismatch')
    require(type(record.get('schema_version')) is int and record.get('schema_version')==1 and record.get('case')=='si-soc-splitting-v1','Worker schema/case mismatch')
    require(record.get('run_id')==run_id and record.get('action')==action,'Stale/wrong worker identity')
    status=record.get('execution_status')
    require((code==0 and status=='PASS') or (code!=0 and status=='FAIL'),'Worker status contradicts exit')
    if code:
        require(isinstance(record.get('reason'),str) and record['reason'],'Worker failure needs reason')
        return
    require(isinstance(record.get('environment'),dict) and record['environment'].get('status')=='PASS','Missing successful environment')
    require(isinstance(record.get('input'),dict) and record['input'].get('element')=='Si' and record['input'].get('nlcc_present') is True,'Missing Si/NLCC source')
    require(isinstance(record.get('grid'),dict) and record['grid'].get('status')=='PASS','Grid/memory preflight not passed')
    if action=='static':
        require(all(record.get(k,{}).get('status')=='PASS' for k in ('nlcc','spin_trace','time_reversal')),'Static prerequisite failed')
    elif action=='D-SCF':
        require(isinstance(record.get('final'),dict) and record['final'].get('map_count',0)>1,'SCF final closure missing')
        require(isinstance(record.get('checkpoint_sha256'),str) and len(record['checkpoint_sha256'])==64,'SCF checkpoint not bound')
    elif action in ('D-SPECTRUM','D-NULL-GAMMA'):
        s=record.get('spectrum');require(isinstance(s,dict),'Spectrum missing')
        require(s.get('execution_status')=='PASS' and s.get('process_exit_code')==0,'Spectrum not successful')
        require(s.get('physical_operator')==('full_soc' if action=='D-SPECTRUM' else 'spin_trace_null'),'Wrong spectrum operator')
        require(len(s.get('kpoints',[]))==(3 if action=='D-SPECTRUM' else 1),'Wrong probe count')
        require(all(len(k.get('eigenvalues_ha',[]))==24 and len(k.get('residuals_ha',[]))==24 for k in s['kpoints']),'Incomplete target spectrum')
        key='time_reversal' if action=='D-SPECTRUM' else 'spin_trace'
        require(record.get(key,{}).get('status')=='PASS','Fixed-density operator gate failed')

def checked_parent(parent):
    p=Path(parent).resolve();r=json.loads((p/'receipt.json').read_text())
    require(r.get('action')=='D-SCF' and r.get('execution_status')=='PASS' and r.get('exit_code')==0,'Successful current D-SCF parent required')
    require(r.get('worker_directory')==r['run_id']+'-dftk','Invalid parent worker directory')
    w=p/r['worker_directory']
    require(digest(w/'result.json')==r['worker_result_sha256'],'Parent receipt/worker hash mismatch')
    return w

def launch(action,directory,*,parent=None,execution_commit=None,static_receipt=None,root=ROOT):
    directory=Path(directory).resolve();base=(root/'.work/phase8a').resolve()
    require(directory!=base and base in directory.parents,'Run directory must be ignored Phase8A child')
    require(not directory.exists(),'Existing run is never reused')
    directory.mkdir(parents=True)
    rec=dict(schema_version=1,case='si-soc-splitting-v1',run_id=directory.name,action=action,
             started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),execution_status='RUNNING',exit_code=1,worker_directory=directory.name+'-dftk')
    write_json(directory/'receipt.json',rec)
    child=None
    try:
        require(action in ACTIONS,'Unknown Si action')
        require((parent is not None)==(action in ('D-SPECTRUM','D-NULL-GAMMA')),'Wrong action/parent arguments')
        source=verify_preparation(root);rec['pseudo_sha256']=source['sha256']
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip();rec['execution_commit']=head
        if action not in ('prepare',):
            require(execution_commit==head,'Explicit execution commit must match HEAD')
            require(not subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True),'Execution tree must be clean')
        if action.startswith('D-'):
            require(static_receipt is not None,'Static prerequisites are required')
            sr=Path(static_receipt);stat=json.loads(sr.read_text())
            require(stat.get('action')=='static' and stat.get('execution_status')=='PASS' and stat.get('exit_code')==0,'Static prerequisites did not pass')
            require(stat.get('execution_commit')==head,'Static checks used another execution commit')
            require(stat.get('worker_directory')==stat['run_id']+'-dftk','Invalid static worker directory')
            require(digest(sr.parent/stat['worker_directory']/'result.json')==stat['worker_result_sha256'],'Static result identity changed')
            rec['static_receipt_sha256']=digest(sr)
        if action!='prepare':
            slots=base/'slots';slots.mkdir(exist_ok=True)
            with (slots/(action+'.json')).open('x') as f:
                json.dump(dict(run_id=directory.name,execution_commit=head),f)
        env=os.environ.copy();env.update(JULIA_LOAD_PATH='@:@stdlib',JULIA_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',JULIA_PKG_OFFLINE='true')
        require(bool(env.get('JULIA_DEPOT_PATH')),'Select the existing frozen package cache explicitly')
        cmd=['julia','--startup-file=no','--color=no','--project='+str(root/'environment/workbench'),str(root/'scripts/run_si_soc.jl'),action,str(directory/rec['worker_directory'])]
        if parent is not None: cmd.append(str(checked_parent(parent)))
        rec['command']=cmd;write_json(directory/'receipt.json',rec)
        with (directory/'worker.stdout').open('w') as out,(directory/'worker.stderr').open('w') as err:
            child=subprocess.Popen(cmd,cwd=root,env=env,stdout=out,stderr=err,start_new_session=True)
            rec['pid']=child.pid;write_json(directory/'receipt.json',rec)
            try: code=child.wait()
            except BaseException:
                os.killpg(child.pid,signal.SIGTERM);child.wait();raise
        rec['worker_exit_code']=code
        path=directory/rec['worker_directory']/'result.json'
        require(path.is_file(),'Worker produced no current result; see raw logs')
        worker=json.loads(path.read_text());validate_worker(worker,code,action,rec['worker_directory'])
        rec['worker_result_sha256']=digest(path)
        verify_preparation(root)
        require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==head,'HEAD changed during task')
        rec['execution_status']=worker['execution_status'];rec['exit_code']=code
        if code: rec['reason']=worker['reason']
    except BaseException as exc:
        rec['execution_status']='FAIL';rec['exit_code']=1;rec['reason']=type(exc).__name__+': '+str(exc)
        if child is not None and child.poll() is not None: rec['worker_exit_code']=child.returncode
    rec['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    try: write_json(directory/'receipt.json',rec)
    except BaseException as exc:
        print('PERSISTENCE FAILURE: '+str(exc),file=sys.stderr);print(json.dumps(rec),file=sys.stderr);return 9
    print(json.dumps({'run_id':rec['run_id'],'action':action,'execution_status':rec['execution_status'],'exit_code':rec['exit_code'],'worker_exit_code':rec.get('worker_exit_code'),'reason':rec.get('reason')}))
    return rec['exit_code'] if 0<=rec['exit_code']<=255 else 1

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=ACTIONS);p.add_argument('directory');p.add_argument('--parent');p.add_argument('--execution-commit');p.add_argument('--static-receipt');a=p.parse_args()
    return launch(a.action,a.directory,parent=a.parent,execution_commit=a.execution_commit,static_receipt=a.static_receipt)
if __name__=='__main__':sys.exit(main())
