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

def verify_preparation(root=ROOT,profile=None):
    import hashlib
    preparation=PREPARATION
    paths=['benchmarks/si-soc-splitting-v1/'+name for name in PREP_FILES]
    if profile is not None:
        from si_soc_sensitivity import PREPARATION as preparation, load_case, prepared_paths
        load_case(root,profile)
        paths=list(prepared_paths())+['benchmarks/si-soc-splitting-v1/source.json']
    for path in paths:
        frozen=subprocess.check_output(['git','show',preparation+':'+path],cwd=root)
        require(hashlib.sha256(frozen).hexdigest()==digest(root/path),'Predeclared input changed: '+path)
    source=json.loads((root/'benchmarks/si-soc-splitting-v1/source.json').read_text())
    data=(root/source['local_path']).read_bytes()
    require(len(data)==source['bytes'] and hashlib.sha256(data).hexdigest()==source['sha256'],'Runtime UPF identity mismatch')
    require(hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==source['git_blob_sha1'],'Runtime UPF Git blob mismatch')
    return source

def validate_worker(record,code,action,run_id,*,profile=None,root=ROOT):
    require(isinstance(record,dict),'Worker record is not an object')
    require(type(record.get('exit_code')) is int and record['exit_code']==code,'Worker/process exit mismatch')
    case_id='si-soc-splitting-v1' if profile is None else 'si-soc-sensitivity-v1/'+profile
    require(type(record.get('schema_version')) is int and record.get('schema_version')==1 and record.get('case')==case_id,'Worker schema/case mismatch')
    require(record.get('run_id')==run_id and record.get('action')==action,'Stale/wrong worker identity')
    status=record.get('execution_status')
    require((code==0 and status=='PASS') or (code!=0 and status=='FAIL'),'Worker status contradicts exit')
    if code:
        require(isinstance(record.get('reason'),str) and record['reason'],'Worker failure needs reason')
        return
    require(isinstance(record.get('environment'),dict) and record['environment'].get('status')=='PASS','Missing successful environment')
    require(isinstance(record.get('input'),dict) and record['input'].get('element')=='Si' and record['input'].get('nlcc_present') is True,'Missing Si/NLCC source')
    require(isinstance(record.get('grid'),dict) and record['grid'].get('status')=='PASS','Grid/memory preflight not passed')
    if profile is not None:
        from si_soc_sensitivity import load_case, CASE_DIR
        case=load_case(root,profile)
        require(record.get('sensitivity_profile')==profile and record.get('case_sha256')==digest(root/CASE_DIR/profile/'case.json'),'Wrong worker sensitivity case identity')
        require(record.get('temperature_ha')==case['electrons']['temperature_ha'],'Actual worker temperature mismatch')
        require(record['input'].get('sha256')==case['pseudo']['sha256'],'Worker source differs from the prepared Si bytes')
        if action=='prepare':
            require(all(isinstance(record.get(k),dict) and record[k].get('status')=='PASS' for k in ('gamma_grid','preflight')),'Both SCF and Gamma preflight must pass')
    if action=='static':
        require(all(record.get(k,{}).get('status')=='PASS' for k in ('nlcc','spin_trace','time_reversal')),'Static prerequisite failed')
    elif action=='D-SCF':
        require(isinstance(record.get('final'),dict) and record['final'].get('map_count',0)>1,'SCF final closure missing')
        require(isinstance(record.get('checkpoint_sha256'),str) and len(record['checkpoint_sha256'])==64,'SCF checkpoint not bound')
    elif action in ('D-SPECTRUM','D-NULL-GAMMA','D-GAMMA'):
        s=record.get('spectrum');require(isinstance(s,dict),'Spectrum missing')
        require(s.get('execution_status')=='PASS' and s.get('process_exit_code')==0,'Spectrum not successful')
        require(s.get('physical_operator')==('spin_trace_null' if action=='D-NULL-GAMMA' else 'full_soc'),'Wrong spectrum operator')
        require(len(s.get('kpoints',[]))==(3 if action=='D-SPECTRUM' else 1),'Wrong probe count')
        require(all(len(k.get('eigenvalues_ha',[]))==24 and len(k.get('residuals_ha',[]))==24 for k in s['kpoints']),'Incomplete target spectrum')
        key='spin_trace' if action=='D-NULL-GAMMA' else 'time_reversal'
        require(record.get(key,{}).get('status')=='PASS','Fixed-density operator gate failed')
        if profile is not None:
            require(s.get('sensitivity_profile')==profile and s.get('case_sha256')==record['case_sha256'] and s.get('temperature_ha')==record['temperature_ha'],'Spectrum case/temperature binding mismatch')
            require(s.get('case')==record['case'] and s.get('run_id')==run_id,'Spectrum run/case differs from its worker')
            for key in ('source_scf_run_id','density_source_sha256'):
                require(isinstance(record.get(key),str) and bool(record[key]) and s.get(key)==record[key],'Spectrum parent binding mismatch: '+key)
            require(s.get('pseudo_sha256')==case['pseudo']['sha256'],'Spectrum source mismatch')
            require(s['kpoints'][0].get('coordinate_fractional')==[0.,0.,0.],'Expected the single Gamma point')
            require(s['kpoints'][0].get('weight_spatial')==1,'Gamma diagnostic weight must be one')

def checked_parent(parent,*,profile=None,root=ROOT,execution_commit=None):
    p=Path(parent).resolve();r=json.loads((p/'receipt.json').read_text())
    require(r.get('action')=='D-SCF' and r.get('execution_status')=='PASS' and r.get('exit_code')==0,'Successful current D-SCF parent required')
    require(r.get('worker_directory')==r['run_id']+'-dftk','Invalid parent worker directory')
    if profile is not None:
        from si_soc_sensitivity import CASE_DIR
        require(r.get('sensitivity_profile')==profile and r.get('case_sha256')==digest(root/CASE_DIR/profile/'case.json'),'Wrong sensitivity parent case')
        require(r.get('execution_commit')==execution_commit,'Wrong sensitivity parent execution')
        area=(root/'.work/phase8b'/profile).resolve()
        require(area in p.parents and p.name==r['run_id'],'Parent is outside its sensitivity case/run')
    w=p/r['worker_directory']
    require(digest(w/'result.json')==r['worker_result_sha256'],'Parent receipt/worker hash mismatch')
    if profile is not None:
        record=json.loads((w/'result.json').read_text())
        validate_worker(record,0,'D-SCF',r['worker_directory'],profile=profile,root=root)
        require(record.get('execution_commit')==execution_commit,'Parent worker execution mismatch')
        require(r.get('pseudo_sha256')==record['input']['sha256'],'Parent recorder/source mismatch')
    return w

def verify_sensitivity_preflights(root,path,execution_commit):
    """Require all three same-execution, source-bound preflights before any SCF.

    This only reads the existing recorder/worker receipts and their hashes;
    it never launches a worker or substitutes a historical preparation result.
    """
    from si_soc_sensitivity import PROFILE_IDS, CASE_DIR, PREPARATION as prep
    require(path is not None,'The complete three-case preflight manifest is required')
    root=Path(root).resolve();path=Path(path).resolve();area=root/'.work/phase8b'
    require(area in path.parents,'Preflight manifest must belong to this phase')
    doc=json.loads(path.read_text())
    require(doc.get('schema_version')==1 and doc.get('execution_commit')==execution_commit and doc.get('preparation_commit')==prep,'Wrong preflight manifest identity')
    require(isinstance(doc.get('profiles'),dict) and set(doc['profiles'])==set(PROFILE_IDS),'Exactly all three preflights required')
    for profile,entry in doc['profiles'].items():
        relative=Path(entry['receipt'])
        require(not relative.is_absolute() and '..' not in relative.parts,'Unconfined preflight receipt')
        receipt=root/relative
        require(not receipt.is_symlink() and (area/profile).resolve() in receipt.resolve().parents,'Preflight receipt outside case')
        require(digest(receipt)==entry['sha256'],'Preflight receipt bytes changed')
        r=json.loads(receipt.read_text())
        require(r.get('action')=='prepare' and r.get('execution_status')=='PASS' and type(r.get('exit_code')) is int and r['exit_code']==0,'Preflight did not pass')
        require(r.get('execution_commit')==execution_commit and r.get('sensitivity_profile')==profile,'Preflight executed different code/case')
        require(r.get('worker_directory')==r['run_id']+'-dftk','Invalid preflight worker directory')
        worker=receipt.parent/r['worker_directory']/'result.json'
        require(digest(worker)==r['worker_result_sha256'],'Preflight worker bytes changed')
        record=json.loads(worker.read_text());validate_worker(record,0,'prepare',r['worker_directory'],profile=profile,root=root)
        require(record.get('execution_commit')==execution_commit,'Worker preflight execution changed')
        require(r.get('pseudo_sha256')==record['input']['sha256'],'Preflight recorder/source mismatch')
        require(r.get('case_sha256')==digest(root/CASE_DIR/profile/'case.json'),'Preflight config changed')
    return digest(path)


def launch(action,directory,*,parent=None,execution_commit=None,static_receipt=None,root=ROOT,profile=None,preflight_manifest=None):
    require(profile is None or profile in ('E40','T05','K4'),'Unregistered sensitivity profile')
    root=Path(root).resolve()
    directory=Path(directory).resolve();base=(root/('.work/phase8a' if profile is None else '.work/phase8b/'+profile)).resolve()
    require(directory!=base and base in directory.parents,'Run directory must be ignored Phase8A child')
    require(not directory.exists(),'Existing run is never reused')
    directory.mkdir(parents=True)
    rec=dict(schema_version=1,case='si-soc-splitting-v1' if profile is None else 'si-soc-sensitivity-v1/'+profile,run_id=directory.name,action=action,
             started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),execution_status='RUNNING',exit_code=1,worker_directory=directory.name+'-dftk')
    write_json(directory/'receipt.json',rec)
    child=None
    try:
        require(action in (ACTIONS if profile is None else ('prepare','D-SCF','D-GAMMA')),'Unknown Si action/profile combination')
        require((parent is not None)==(action in ('D-SPECTRUM','D-NULL-GAMMA','D-GAMMA')),'Wrong action/parent arguments')
        source=verify_preparation(root) if profile is None else verify_preparation(root,profile)
        rec['pseudo_sha256']=source['sha256']
        if profile is not None:
            from si_soc_sensitivity import CASE_DIR, PREPARATION as prep, load_case
            case=load_case(root,profile)
            rec.update(sensitivity_profile=profile,case_sha256=digest(root/CASE_DIR/profile/'case.json'),temperature_ha=case['electrons']['temperature_ha'],preparation_commit=prep)
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip();rec['execution_commit']=head
        if action not in ('prepare',) or profile is not None:
            require(execution_commit==head,'Explicit execution commit must match HEAD')
            require(not subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True),'Execution tree must be clean')
        if profile is not None:
            require(static_receipt is None,'Sensitivity uses three preflights, not the historical static/null receipt')
            if action.startswith('D-'):
                rec['preflight_manifest_sha256']=verify_sensitivity_preflights(root,preflight_manifest,head)
        if action.startswith('D-') and profile is None:
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
        if parent is not None: cmd.append(str(checked_parent(parent) if profile is None else checked_parent(parent,profile=profile,root=root,execution_commit=head)))
        if profile is not None: cmd.extend(['--profile',profile])
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
        worker=json.loads(path.read_text());validate_worker(worker,code,action,rec['worker_directory'],profile=profile,root=root)
        rec['worker_result_sha256']=digest(path)
        verify_preparation(root) if profile is None else verify_preparation(root,profile)
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
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=ACTIONS+('D-GAMMA',));p.add_argument('directory');p.add_argument('--parent');p.add_argument('--execution-commit');p.add_argument('--static-receipt');p.add_argument('--profile',choices=('E40','T05','K4'));p.add_argument('--preflight-manifest');a=p.parse_args()
    return launch(a.action,a.directory,parent=a.parent,execution_commit=a.execution_commit,static_receipt=a.static_receipt,profile=a.profile,preflight_manifest=a.preflight_manifest)
if __name__=='__main__':sys.exit(main())
