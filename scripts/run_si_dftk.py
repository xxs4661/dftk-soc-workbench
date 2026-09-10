#!/usr/bin/env python3
"""Durable single-attempt launcher for the prescribed Si Julia tasks only."""
import argparse
import importlib.util
import re
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


CORE_ACTIONS=('OPT-B0-SCF','OPT-B0-GAMMA')
CORE_BASE='c764311a5422b5c3cab5a7b78a02d420910c4e56'
CORE_PREPARATION='e4f16a51a0304f5e70f5ae038563d6760409c2c4'
CORE_REFERENCE_EXECUTION='bbe9aa7755f052900e6e9c4618252a410e1cc8f0'

def core_tools(root):
    """Reuse the frozen static receipt/resource protocol, never its science CLI."""
    path=Path(root)/'benchmarks/soc-core-memory-v1/run.py'
    spec=importlib.util.spec_from_file_location('soc_core_measurement_runner',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def resume_tools(root):
    """Load the explicit continuation contract; the default gate is unchanged."""
    path=Path(root)/'benchmarks/soc-core-memory-v1/resume/control.py'
    spec=importlib.util.spec_from_file_location('soc_core_resume_control',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def resume_fields(auth,action):
    require(action in CORE_ACTIONS,'Unregistered continuation action')
    fields={key:auth[key] for key in ('resume_id','resume_preparation_commit','resume_from_commit',
                                    'static_execution_commit','endpoint_execution_commit')}
    fields.update(resume_authorization_sha256=auth['authorization_sha256'],attempt=2 if action=='OPT-B0-SCF' else 1)
    return fields

def validate_entry_worker(record,code,action,run_id,*,root,execution_commit,auth):
    """A definitions/source check is never a successful physical worker."""
    require(isinstance(record,dict) and type(record.get('schema_version')) is int and record['schema_version']==1,'Invalid entry-check schema')
    require(type(record.get('exit_code')) is int and record['exit_code']==code==0,'Entry-check process failed')
    require(record.get('phase')=='9A' and record.get('backend')=='soc-core' and record.get('case')=='si-soc-splitting-v1','Wrong entry-check case/backend')
    require(record.get('action')==action and record.get('run_id')==run_id and record.get('execution_commit')==execution_commit,'Wrong entry-check run/action/execution')
    require(record.get('base_commit')==CORE_BASE and record.get('preparation_commit')==CORE_PREPARATION,'Wrong entry-check original identity')
    require(record.get('core_gate_sha256')==auth['core_gate_sha256'],'Entry-check static gate differs')
    require(record.get('case_sha256')==digest(Path(root)/'benchmarks/si-soc-splitting-v1/case.json'),'Entry-check B0 case differs')
    require(record.get('execution_status')=='CHECK_ONLY_PASS' and record.get('check_status')=='PASS' and record.get('check_only') is True,'Entry-check status contradiction')
    require(record.get('numerical_execution_status')=='NOT_RUN' and record.get('formal_slot_reserved') is False and record.get('context_constructed') is False,'Entry-check performed or claimed numerical work')
    require(all(type(record.get(k)) is int and record[k]==0 for k in ('context_registrations','source_registrations')),'Entry-check created a physical context/source bundle')
    require(isinstance(record.get('environment'),dict) and record['environment'].get('status')=='PASS','Entry-check environment failed')
    require(record.get('source_status')==record.get('settings_status')=='PASS' and isinstance(record.get('executed_source_sha256'),dict) and bool(record['executed_source_sha256']),'Entry-check source/settings missing')
    resume_tools(root).verify_worker_resume(record,auth,action)

def core_file(root,relative,expected=None):
    root=Path(root).resolve();part=Path(relative)
    require(not part.is_absolute() and '..' not in part.parts,'Unconfined core evidence path')
    path=root/part
    require(not path.is_symlink() and path.is_file() and path.resolve()==path and (root/'.work/phase9a') in path.resolve().parents,'Core evidence outside this phase')
    if expected is not None:require(digest(path)==expected,'Core evidence bytes changed: '+str(part))
    return path

def verify_core_gate(root,path,execution_commit):
    require(isinstance(execution_commit,str) and re.fullmatch('[0-9a-f]{40}',execution_commit),'Exact candidate commit required')
    root=Path(root).resolve();require(path is not None,'The completed core static gate is required')
    candidate=Path(path)
    if candidate.is_absolute():
        require(root in candidate.resolve().parents,'Gate outside workbench');candidate=candidate.relative_to(root)
    gate_path=core_file(root,candidate);tool=core_tools(root);gate=tool.read(gate_path)
    require(type(gate.get('schema_version')) is int and gate['schema_version']==1 and gate.get('phase')=='9A','Wrong core gate schema/phase')
    require(gate.get('execution_commit')==execution_commit and gate.get('overall_status')=='PASS' and type(gate.get('exit_code')) is int and gate['exit_code']==0,'Core gate is not current successful evidence')
    for key in ('identity_status','equivalence_status','allocation_status','resource_status','live_storage_reduction_status'):
        require(gate.get(key)=='PASS','Core gate did not pass: '+key)
    require(gate.get('time_status') in ('PASS','PERFORMANCE_REVIEW_REQUIRED'),'Missing declared time assessment')
    suites=gate.get('suite_receipts');require(isinstance(suites,dict) and set(suites)==set(tool.SUITES),'All four exact static suites required')
    for name,entry in suites.items():
        require(isinstance(entry,dict),'Invalid suite reference')
        receipt=core_file(root,entry['path'],entry['sha256']);record=tool.read(receipt)
        require(record.get('suite')==name,'Wrong static suite reference')
        expected=CORE_REFERENCE_EXECUTION if name.startswith('REF-') else execution_commit
        require(record.get('execution_commit')==expected,'Wrong static implementation commit')
        tool.prior_contract(record,receipt.parent)
    for label in ('comparison','performance'):
        entry=gate.get(label);require(isinstance(entry,dict),'Missing '+label+' evidence')
        bound=core_file(root,entry['path'],entry['sha256']);record=tool.read(bound)
        require(type(record.get('schema_version')) is int and record['schema_version']==1 and record.get('phase')=='9A' and
                record.get('execution_commit')==execution_commit and record.get('overall_status')=='PASS' and
                type(record.get('exit_code')) is int and record['exit_code']==0,'Unsuccessful/current '+label+' evidence required')
    tool.preparation(root)
    return digest(gate_path)

def validate_core_worker(record,code,action,run_id,*,root,execution_commit,gate_sha256,resume_auth=None):
    require(isinstance(record,dict) and record.get('backend')=='soc-core' and record.get('phase')=='9A','Wrong worker backend/phase')
    require(record.get('execution_commit')==execution_commit and record.get('core_gate_sha256')==gate_sha256,'Worker candidate/gate mismatch')
    require(record.get('base_commit')==CORE_BASE and record.get('preparation_commit')==CORE_PREPARATION,'Worker core base/preparation mismatch')
    require(record.get('action')==action and action in CORE_ACTIONS,'Wrong core action')
    # Reuse all pre-existing physical receipt gates on a temporary protocol view.
    view=dict(record,action='D-SCF' if action=='OPT-B0-SCF' else 'D-GAMMA')
    validate_worker(view,code,view['action'],run_id,root=root)
    if code:return
    if resume_auth is not None:resume_tools(root).verify_worker_resume(record,resume_auth,action)
    require(record.get('runtime_closed') is True,'Owned runtime did not close')
    runtime=record.get('runtime');require(isinstance(runtime,dict) and runtime.get('backend')=='soc-core','Missing actual owned runtime dispatch')
    require(record.get('runtime_dispatch_status')=='PASS','Owned backend was not actually exercised')
    counts=runtime.get('counters');require(isinstance(counts,dict) and all(type(counts.get(k)) is int and counts[k]>0 for k in ('fr_mul_calls','component_mul_calls','full_mul_calls')),'Missing actual core operator counts')
    require(runtime.get('max_rhs')==30 and runtime.get('closed') is False,'Invalid live workspace receipt')
    closed=record.get('runtime_after_close');require(isinstance(closed,dict) and closed.get('closed') is True and closed.get('owned_source_entries')==0 and closed.get('workspace_released') is True,'Owned storage did not release')
    require(record.get('case_sha256')==digest(Path(root)/'benchmarks/si-soc-splitting-v1/case.json'),'Worker B0 source case mismatch')
    if action=='OPT-B0-GAMMA':
        spectrum=record['spectrum']
        require(spectrum.get('backend')=='soc-core' and spectrum.get('temperature_ha')==.001,'Wrong Gamma backend/temperature')
        require(spectrum['kpoints'][0].get('coordinate_fractional')==[0.,0.,0.] and spectrum['kpoints'][0].get('weight_spatial')==1,'Only one Gamma probe is allowed')
        for key in ('source_scf_run_id','density_source_sha256'):
            require(isinstance(record.get(key),str) and bool(record[key]) and spectrum.get(key)==record[key],'Gamma parent binding missing: '+key)
        require(spectrum.get('occupations_use')=='DIAGNOSTIC_ONLY_NOT_DENSITY_FEEDBACK','Gamma occupations must remain diagnostic')

def checked_core_parent(parent,*,root,execution_commit,gate_sha256,resume_auth=None):
    root=Path(root).resolve();p=Path(parent).resolve();area=root/'.work/phase9a/endpoints'
    require(area in p.parents and p.is_dir() and not Path(parent).is_symlink(),'BLOCKED_PARENT: parent outside current endpoint area')
    r=json.loads((p/'receipt.json').read_text())
    require(r.get('run_id')==p.name and r.get('action')=='OPT-B0-SCF' and r.get('backend')=='soc-core' and
            r.get('execution_status')=='PASS' and type(r.get('exit_code')) is int and r['exit_code']==0,'BLOCKED_PARENT: successful owned SCF required')
    require(r.get('execution_commit')==execution_commit and r.get('core_gate_sha256')==gate_sha256,'BLOCKED_PARENT: parent candidate/gate differs')
    if resume_auth is not None:
        resume_tools(root).verify_worker_resume(r,resume_auth,'OPT-B0-SCF')
        resume_tools(root).process_proof(root,p/'receipt.json',r)
    require(r.get('worker_directory')==r['run_id']+'-dftk','BLOCKED_PARENT: worker directory mismatch')
    worker=p/r['worker_directory'];result=worker/'result.json'
    require(not worker.is_symlink() and digest(result)==r.get('worker_result_sha256'),'BLOCKED_PARENT: parent worker bytes changed')
    value=json.loads(result.read_text());validate_core_worker(value,0,'OPT-B0-SCF',worker.name,root=root,execution_commit=execution_commit,gate_sha256=gate_sha256,resume_auth=resume_auth)
    require(digest(worker/'final.bin')==value.get('checkpoint_sha256'),'BLOCKED_PARENT: original final checkpoint changed')
    tool=core_tools(root);tool.resource_contract(r.get('resource'),r.get('worker_exit_code'))
    require(tool.read(p/'resource.json')==r['resource'],'BLOCKED_PARENT: resource receipt changed')
    return worker


def launch(action,directory,*,parent=None,execution_commit=None,static_receipt=None,root=ROOT,profile=None,preflight_manifest=None,backend=None,core_gate=None,resume_authorization=None,check_entry=False):
    require(backend is None or backend=='soc-core','Unknown explicit backend')
    owned=backend=='soc-core'
    require(not owned or profile is None,'Core backend cannot impersonate a sensitivity profile')
    require(owned or core_gate is None,'Core gate requires explicit core backend')
    require(resume_authorization is None or owned,'Continuation requires explicit core backend')
    require(type(check_entry) is bool and (not check_entry or resume_authorization is not None),'Entry check requires explicit continuation authorization')
    require(profile is None or profile in ('E40','T05','K4'),'Unregistered sensitivity profile')
    root=Path(root).resolve()
    directory=Path(directory).resolve();base=(root/('.work/phase9a/endpoints' if owned else '.work/phase8a' if profile is None else '.work/phase8b/'+profile)).resolve()
    require(directory!=base and base in directory.parents,'Run directory must be ignored Phase8A child')
    require(not directory.exists(),'Existing run is never reused')
    directory.mkdir(parents=True)
    rec=dict(schema_version=1,case='si-soc-splitting-v1' if profile is None else 'si-soc-sensitivity-v1/'+profile,run_id=directory.name,action=action,
             started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),execution_status='RUNNING',exit_code=1,worker_directory=directory.name+'-dftk')
    if owned:rec.update(phase='9A',backend=backend,base_commit=CORE_BASE,preparation_commit=CORE_PREPARATION,worker_started=False)
    if check_entry:rec.update(check_only=True,check_status='RUNNING',numerical_execution_status='NOT_RUN',formal_slot_reserved=False,check_process_started=False,worker_directory=directory.name+'-entry-check')
    write_json(directory/'receipt.json',rec)
    child=None;active_lock=None;owns_lock=False;resume_auth=None
    try:
        require(action in (CORE_ACTIONS if owned else ACTIONS if profile is None else ('prepare','D-SCF','D-GAMMA')),'Unknown Si action/profile combination')
        require((parent is not None)==(action in ('D-SPECTRUM','D-NULL-GAMMA','D-GAMMA','OPT-B0-GAMMA')),'BLOCKED_PARENT: missing own SCF parent' if owned and action=='OPT-B0-GAMMA' else 'Wrong action/parent arguments')
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
        if owned:
            require(static_receipt is None and preflight_manifest is None,'Core endpoints require only their own static gate')
            if resume_authorization is None:
                rec['core_gate_sha256']=verify_core_gate(root,core_gate,head)
            else:
                resume_auth=resume_tools(root).verify_authorization(root,resume_authorization,head,core_gate)
                rec['core_gate_sha256']=resume_auth['core_gate_sha256'];rec.update(resume_fields(resume_auth,action))
                if not check_entry:resume_tools(root).validate_entry_receipt(root,resume_auth)
            rec['case_sha256']=digest(root/'benchmarks/si-soc-splitting-v1/case.json')
            try:core_parent=checked_core_parent(parent,root=root,execution_commit=head,gate_sha256=rec['core_gate_sha256'],resume_auth=resume_auth) if parent is not None else None
            except (OSError,ValueError,KeyError,TypeError) as exc:raise ValueError('BLOCKED_PARENT: '+str(exc)) from exc
            core_gate_path=Path(core_gate) if Path(core_gate).is_absolute() else root/core_gate
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
        if owned:
            depot=os.environ.get('JULIA_DEPOT_PATH')
            require(bool(depot) and all(p and Path(p).is_dir() for p in depot.split(os.pathsep)),'Select the existing frozen package cache explicitly')
            tool=core_tools(root);tool.ps_rows()
            require(not (root/'.work/phase9a/static/active.json').exists(),'A static measurement session is still active')
            active_lock=base/'active.json'
            if check_entry:
                require(not active_lock.exists(),'An endpoint session is still active')
            else:
                with active_lock.open('x') as stream:json.dump(dict(run_id=directory.name,owner_pid=os.getpid()),stream)
                owns_lock=True
        if action!='prepare' and not check_entry:
            slots=resume_tools(root).reservation_directory(root,resume_auth) if resume_auth is not None else base/'slots'
            slots.mkdir(parents=True,exist_ok=True)
            with (slots/(action+'.json')).open('x') as f:
                reservation=dict(run_id=directory.name,execution_commit=head)
                if resume_auth is not None:reservation.update(resume_fields(resume_auth,action))
                json.dump(reservation,f)
        env=os.environ.copy()
        if owned:env['SOC_CORE_PYTHON']=sys.executable
        env.update(JULIA_LOAD_PATH='@:@stdlib',JULIA_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',JULIA_PKG_OFFLINE='true')
        require(bool(env.get('JULIA_DEPOT_PATH')),'Select the existing frozen package cache explicitly')
        cmd=['julia','--startup-file=no','--color=no','--project='+str(root/'environment/workbench'),str(root/'scripts/run_si_soc.jl'),action,str(directory/rec['worker_directory'])]
        if parent is not None: cmd.append(str(core_parent if owned else checked_parent(parent) if profile is None else checked_parent(parent,profile=profile,root=root,execution_commit=head)))
        if profile is not None: cmd.extend(['--profile',profile])
        if owned:cmd.extend(['--backend','soc-core','--core-gate',str(core_gate_path.resolve())])
        if resume_auth is not None:cmd.extend(['--resume-authorization',str((root/resume_auth['authorization_path']).resolve())])
        if check_entry:cmd.append('--check-entry')
        rec['command']=cmd;write_json(directory/'receipt.json',rec)
        if owned:
            rec['check_process_started' if check_entry else 'worker_started']=True
            rec['log_labels']='qe.stdout/qe.stderr are inherited executor names containing Julia output; no QE command'
            write_json(directory/'receipt.json',rec)
            code,resource=tool.monitored_execute(tool.execute,cmd,directory,env)
            rec.update(worker_exit_code=code,resource=resource)
            require(code==0,'Julia worker returned nonzero: '+str(code))
            tool.resource_contract(resource,code)
        else:
            with (directory/'worker.stdout').open('w') as out,(directory/'worker.stderr').open('w') as err:
                child=subprocess.Popen(cmd,cwd=root,env=env,stdout=out,stderr=err,start_new_session=True)
                rec['pid']=child.pid;write_json(directory/'receipt.json',rec)
                try: code=child.wait()
                except BaseException:
                    os.killpg(child.pid,signal.SIGTERM);child.wait();raise
        rec['worker_exit_code']=code
        path=directory/rec['worker_directory']/'result.json'
        require(path.is_file(),'Worker produced no current result; see raw logs')
        worker=json.loads(path.read_text())
        if check_entry:validate_entry_worker(worker,code,action,rec['worker_directory'],root=root,execution_commit=head,auth=resume_auth)
        elif owned:validate_core_worker(worker,code,action,rec['worker_directory'],root=root,execution_commit=head,gate_sha256=rec['core_gate_sha256'],resume_auth=resume_auth)
        else:validate_worker(worker,code,action,rec['worker_directory'],profile=profile,root=root)
        rec['worker_result_sha256']=digest(path)
        verify_preparation(root) if profile is None else verify_preparation(root,profile)
        require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==head,'HEAD changed during task')
        if owned:
            if resume_auth is None:
                require(verify_core_gate(root,core_gate,head)==rec['core_gate_sha256'],'Core gate changed during endpoint')
            else:
                require(resume_tools(root).verify_authorization(root,resume_authorization,head,core_gate)==resume_auth,'Continuation authorization changed during endpoint')
            require(not subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True),'Execution source changed')
        rec['execution_status']=worker['execution_status'];rec['exit_code']=code
        if check_entry:
            rec.update(check_status='PASS',original_receipt_path=(directory/'receipt.json').relative_to(root).as_posix(),check_worker_result_path=path.relative_to(root).as_posix())
        if code: rec['reason']=worker['reason']
    except BaseException as exc:
        rec['execution_status']='FAIL';rec['exit_code']=9 if owned else 1;rec['reason']=type(exc).__name__+': '+str(exc)
        if check_entry:rec['check_status']='FAIL'
        if owned:
            rec['failure_status']='BLOCKED_PARENT' if 'BLOCKED_PARENT' in str(exc) else 'FAIL'
            for filename,key in (('resource.json','resource'),('process-exit.json','native_process')):
                try:rec[key]=json.loads((directory/filename).read_text())
                except (OSError,ValueError):pass
            if type(rec.get('native_process',{}).get('exit_code')) is int:rec['worker_exit_code']=rec['native_process']['exit_code']
        if child is not None and child.poll() is not None: rec['worker_exit_code']=child.returncode
    if owned and owns_lock:
        try:
            cleanup=rec.get('resource',{}).get('owned_process_cleanup_status')
            if cleanup=='PASS' or not (directory/'process-start.json').exists():
                require(json.loads(active_lock.read_text()).get('run_id')==directory.name,'Endpoint active lock changed')
                active_lock.unlink()
        except (OSError,ValueError) as exc:
            rec.update(execution_status='FAIL',exit_code=9,cleanup_error=str(exc))
    rec['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    try: write_json(directory/'receipt.json',rec)
    except BaseException as exc:
        print('PERSISTENCE FAILURE: '+str(exc),file=sys.stderr);print(json.dumps(rec),file=sys.stderr);return 9
    print(json.dumps({'run_id':rec['run_id'],'action':action,'execution_status':rec['execution_status'],'exit_code':rec['exit_code'],'worker_exit_code':rec.get('worker_exit_code'),'reason':rec.get('reason')}))
    return rec['exit_code'] if 0<=rec['exit_code']<=255 else 1

def main():
    if sys.argv[1:2]==['--verify-resume']:
        if len(sys.argv)!=6:return 9
        try:
            value=resume_tools(Path(sys.argv[2])).verify_authorization(Path(sys.argv[2]),sys.argv[3],sys.argv[4],sys.argv[5])
            print(json.dumps(value));return 0
        except (OSError,ValueError,KeyError,TypeError) as exc:
            print('Continuation authorization rejected: '+str(exc),file=sys.stderr);return 9
    if sys.argv[1:2]==['--verify-core-gate']:
        if len(sys.argv)!=5:return 9
        try:
            value=verify_core_gate(Path(sys.argv[2]),sys.argv[3],sys.argv[4])
            print(json.dumps({'sha256':value}));return 0
        except (OSError,ValueError,KeyError,TypeError) as exc:
            print('Core gate rejected: '+str(exc),file=sys.stderr);return 9
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=ACTIONS+('D-GAMMA',)+CORE_ACTIONS);p.add_argument('directory');p.add_argument('--parent');p.add_argument('--execution-commit');p.add_argument('--static-receipt');p.add_argument('--profile',choices=('E40','T05','K4'));p.add_argument('--preflight-manifest');p.add_argument('--backend',choices=('soc-core',));p.add_argument('--core-gate');p.add_argument('--resume-authorization');p.add_argument('--check-entry',action='store_true');a=p.parse_args()
    return launch(a.action,a.directory,parent=a.parent,execution_commit=a.execution_commit,static_receipt=a.static_receipt,profile=a.profile,preflight_manifest=a.preflight_manifest,backend=a.backend,core_gate=a.core_gate,resume_authorization=a.resume_authorization,check_entry=a.check_entry)
if __name__=='__main__':sys.exit(main())
