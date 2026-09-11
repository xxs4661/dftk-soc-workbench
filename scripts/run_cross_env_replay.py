#!/usr/bin/env python3
"""One Linux job: frozen R once, independent I once, with honest separate status."""
from __future__ import annotations
import argparse,contextlib,ctypes,datetime,hashlib,io,json,math,os,pathlib,platform,re,subprocess,sys
import numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[1]
PLAN='benchmarks/mg-soc-public-replay-v1/plan.json'
EXECUTION_FILES=[PLAN,'benchmarks/mg-soc-public-replay-v1/requirements.lock',
 '.github/workflows/phase7g-public-replay.yml','scripts/run_cross_env_replay.py',
 'scripts/replay_public_independent.py','scripts/independent_orbital_io.py',
 'scripts/independent_orbital_math.py','scripts/phase7g_observer/sitecustomize.py',
 'tests/test_independent_orbital_io.py','tests/test_independent_orbital_math.py',
 'tests/test_independent_replay.py','tests/test_phase7g_observer.py','tests/test_cross_env_replay.py']
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(pathlib.Path(p).read_text())
def write(p,d):
    p=pathlib.Path(p);pending=p.with_name(p.name+'.pending')
    pending.write_text(json.dumps(d,indent=2,allow_nan=False)+'\n');pending.replace(p)
def require(condition,message):
    if not condition:raise ValueError(message)
def git(*args,cwd=ROOT):return subprocess.check_output(['git',*args],cwd=cwd,text=True).strip()
def aggregate_exit(test_exit,R_exit,I_exit,diagnostic_exit):
    """Upload/packaging has no authority to turn a nonzero numerical result green."""
    for code in (test_exit,R_exit,I_exit,diagnostic_exit):
        if code is not None and code!=0:return int(code) if code>0 else 1
    return 1 if any(code is None for code in (test_exit,R_exit,I_exit,diagnostic_exit)) else 0

def input_snapshot(source,plan):
    require(git('rev-parse','HEAD',cwd=source)==plan['input_commit'],'Wrong detached source commit')
    require(not (source/'.work').exists() and not (source/'.agent-work').exists(),'Forbidden private directory in public checkout')
    out={}
    for relative,digest in plan['input_sha256'].items():
        p=source/relative
        require(p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(source.resolve()),'Missing or unsafe public source '+relative)
        require(sha(p)==digest and p.stat().st_size==plan['input_bytes'][relative],'Public input identity mismatch '+relative)
        out[relative]=digest
    return out

def field_differences(new,old,prefix=''):
    """Enumerate every changed leaf; no rewriting of old or new reports."""
    if isinstance(new,dict) and isinstance(old,dict):
        out=[]
        for key in sorted(set(new)|set(old)):
            path=prefix+'.'+key if prefix else key
            if key not in new or key not in old:out.append(dict(path=path,old=old.get(key),new=new.get(key),classification='UNCLASSIFIED_STRUCTURE',frozen_close_pass=False))
            else:out.extend(field_differences(new[key],old[key],path))
        return out
    if isinstance(new,list) and isinstance(old,list):
        if len(new)!=len(old):return [dict(path=prefix,old_length=len(old),new_length=len(new),classification='UNCLASSIFIED_STRUCTURE',frozen_close_pass=False)]
        return [r for i,(a,b) in enumerate(zip(new,old)) for r in field_differences(a,b,prefix+f'[{i}]')]
    if any(type(value) in (int,float) and not math.isfinite(value) for value in (new,old)):
        return [dict(path=prefix,old=str(old),new=str(new),classification='NONFINITE_NUMERIC',frozen_close_pass=False)]
    if new==old and type(new)==type(old):return []
    record=dict(path=prefix,old=old,new=new)
    if type(new) in (int,float) and type(old) in (int,float):
        delta=new-old;record.update(classification='DERIVED_NUMERIC',signed_difference=delta,absolute_difference=abs(delta),frozen_close_pass=abs(delta)<=1e-11)
    elif prefix in ('comparison.local_state.field_fingerprints.n_wfc','comparison.local_state.field_fingerprints.n_saved') and all(isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) for value in (new,old)):
        record.update(classification='PREDECLARED_DERIVED_DENSITY_HASH',frozen_close_pass=False)
    elif prefix=='state-checks.Q.backend.numpy_version':record.update(classification='ENVIRONMENT_VERSION_MISMATCH_NOT_EXEMPT',frozen_close_pass=False)
    else:record.update(classification='UNCLASSIFIED_EXACT_FIELD',frozen_close_pass=False)
    return [record]

def reference_failure_matches_hashes(exit_code,stdout_text,differences):
    """Bind classification to the frozen checker's actual exact-compare failure."""
    if exit_code!=1:return False
    try:result=json.loads(stdout_text)
    except (ValueError,TypeError):return False
    if not isinstance(result,dict) or set(result)!={'status','reason'} or result['status']!='FAIL':return False
    expected={'Replay differs: '+str((row['new'],row['old']))[:200] for row in differences
              if row['classification']=='PREDECLARED_DERIVED_DENSITY_HASH'}
    return result['reason'] in expected

def environment_receipt(plan,wheel):
    expected=plan['environment'];require(platform.system()=='Linux' and platform.machine()=='x86_64','Not the declared cross-platform Linux x86_64 environment')
    require(platform.python_version()==expected['python_version'] and np.__version__==expected['numpy_version'],'Fixed Python/NumPy version mismatch')
    require(sys.flags.no_user_site==1 and sys.dont_write_bytecode,'User site or bytecode enabled')
    for key,value in expected['thread_environment'].items():require(os.environ.get(key)==value,'Thread setting differs: '+key)
    require(wheel.name==expected['numpy_wheel']['filename'] and sha(wheel)==expected['numpy_wheel']['digests']['sha256'],'Installed wheel source identity differs')
    config=io.StringIO()
    with contextlib.redirect_stdout(config):np.show_config()
    libs=[];threads=[]
    for p in sorted((pathlib.Path(np.__file__).resolve().parent.parent/'numpy.libs').glob('*')):
        if not p.is_file():continue
        row=dict(file=p.name,sha256=sha(p),bytes=p.stat().st_size)
        if 'openblas' in p.name.lower():
            library=ctypes.CDLL(str(p));found=False
            for symbol in ('scipy_openblas_get_num_threads64_','openblas_get_num_threads64_','openblas_get_num_threads','scipy_openblas_get_num_threads'):
                try:fn=getattr(library,symbol)
                except AttributeError:continue
                fn.restype=ctypes.c_int;n=fn();row.update(thread_symbol=symbol,actual_threads=n);threads.append(n);found=True;break
            require(found,'Cannot verify actual OpenBLAS thread count')
        libs.append(row)
    require(threads and all(x==1 for x in threads),'Actual BLAS threading is not one')
    cpu='UNAVAILABLE'
    for line in pathlib.Path('/proc/cpuinfo').read_text().splitlines():
        if line.startswith('model name'):cpu=line.split(':',1)[1].strip();break
    import importlib.metadata as metadata
    dist=metadata.distribution('numpy');package_files={}
    for entry in dist.files or []:
        p=pathlib.Path(dist.locate_file(entry))
        if p.is_file():package_files[str(entry)]=sha(p)
    return dict(status='PASS',OS=platform.system(),architecture=platform.machine(),platform=platform.platform(),cpu=cpu,
       os_release=platform.freedesktop_os_release(),python_version=platform.python_version(),python_build=platform.python_build(),python_full_version=sys.version,python_compiler=platform.python_compiler(),python_executable_sha256=sha(sys.executable),numpy_version=np.__version__,numpy_configuration=config.getvalue(),numpy_libraries=libs,numpy_installed_file_count=len(package_files),numpy_installed_files_digest=hashlib.sha256(json.dumps(package_files,sort_keys=True).encode()).hexdigest(),wheel={'filename':wheel.name,'sha256':sha(wheel),'bytes':wheel.stat().st_size},threads={k:os.environ[k] for k in expected['thread_environment']},actual_openblas_threads=threads,FFT='NumPy pocketfft; shared library/backend family with R, not fully independent numerical stack',user_site_enabled=False,bytecode_enabled=False,network='No numerical network calls implemented; OS-level network sandbox NOT_ENFORCED',package_files=package_files)

def run_command(command,cwd,out,env):
    out.mkdir(parents=True,exist_ok=False)
    with (out/'stdout.txt').open('wb') as stdout,(out/'stderr.txt').open('wb') as stderr:
        cp=subprocess.run(command,cwd=cwd,env=env,stdout=stdout,stderr=stderr,check=False)
    result=dict(command=command,exit_code=cp.returncode,completed=True,stdout_sha256=sha(out/'stdout.txt'),stderr_sha256=sha(out/'stderr.txt'))
    write(out/'process.json',result);return result

def diagnostic(source,out,R,I):
    observer=out/'R-observer';files=['r-orbitals-report.json','r-comparison.json','r-n-wfc.npy','r-n-saved.npy']
    missing=[f for f in files if not (observer/f).is_file()]
    status=read(observer/'r-observer-status.json') if (observer/'r-observer-status.json').is_file() else {'status':'MISSING'}
    report=dict(observer=status,missing_captures=missing,reference_exit_code=R['exit_code'],independent_exit_code=I['exit_code'],old_real_array_nodewise_difference='NOT_AVAILABLE_FROM_PUBLIC_HASHES',differences=[])
    for file,old,prefix in [('r-orbitals-report.json',read(source/'results/mg-soc-wavefunction-energy/state-checks.json')['Q'],'state-checks.Q'),('r-comparison.json',read(source/'results/mg-soc-wavefunction-energy/comparison.json'),'comparison')]:
        if (observer/file).is_file():report['differences']+=field_differences(read(observer/file),old,prefix)
    report['current_R_vs_I_density']={}
    for key,rname,iname in [('n_wfc','r-n-wfc.npy','rho.npy'),('n_saved','r-n-saved.npy','rho_saved.npy')]:
        rp,ip=observer/rname,out/'I'/iname
        if rp.is_file() and ip.is_file():
            a=np.load(rp,allow_pickle=False).reshape(-1,order='F');b=np.load(ip,allow_pickle=False).reshape(-1,order='F')
            require(a.shape==b.shape and np.isfinite(a).all() and np.isfinite(b).all(),'R/I diagnostic density shape/finite failure')
            delta=a-b;report['current_R_vs_I_density'][key]=dict(max_abs=float(np.max(abs(delta))),relative_l2=float(np.linalg.norm(delta)/np.linalg.norm(a)),scope='Current Linux R versus independent I, NOT original Mac nodes')
    unacceptable=[x for x in report['differences'] if not x['frozen_close_pass'] and x['classification']!='PREDECLARED_DERIVED_DENSITY_HASH']
    complete=not missing and status.get('status')=='OBSERVATION_FINISHED'
    arrays_ok=all(x['max_abs']<=1e-10 and x['relative_l2']<=1e-9 for x in report['current_R_vs_I_density'].values()) and len(report['current_R_vs_I_density'])==2
    numeric_ok=I['exit_code']==0 and not unacceptable and complete and arrays_ok
    report['raw_failure_matches_observed_hash']=reference_failure_matches_hashes(R['exit_code'],(out/'R'/'stdout.txt').read_text(),report['differences'])
    if R['exit_code']==0:classification='FROZEN_REFERENCE_PASS'
    elif numeric_ok and report['raw_failure_matches_observed_hash']:classification='FROZEN_FAIL_PREDECLARED_PLATFORM_DENSITY_FINGERPRINTS_ONLY'
    else:classification='UNEXPLAINED_OR_SUBSTANTIVE_REFERENCE_FAILURE'
    report.update(classification=classification,unclassified_or_over_frozen_tolerance=unacceptable,complete_numerical_diagnosis=numeric_ok,
      frozen_status_unchanged='PASS' if R['exit_code']==0 else 'FAIL',independent_status='PASS' if I['exit_code']==0 else 'FAIL')
    write(out/'platform-diagnostic.json',report)
    return report,0 if complete and arrays_ok and not unacceptable else 1

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--wheel',required=True);args=parser.parse_args(argv)
    out=pathlib.Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    require(not (out/'replay.json').exists(),'Existing final run refused')
    record=dict(schema_version=1,phase='7G',started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),execution_status='RUNNING',R={'status':'NOT_RUN','exit_code':None},I={'status':'NOT_RUN','exit_code':None})
    final_code=1;source=None;before=None
    try:
        plan=read(ROOT/PLAN);execution=git('rev-parse','HEAD');require(execution==os.environ['GITHUB_SHA'],'Execution checkout is not event head')
        require(os.environ.get('GITHUB_REPOSITORY')==plan['repository'] and os.environ.get('GITHUB_REF')=='refs/heads/'+plan['branch'],'Wrong repository/event branch')
        record.update(repository=plan['repository'],input_commit=plan['input_commit'],tested_commit=execution,run_id=os.environ['GITHUB_RUN_ID'],run_attempt=os.environ['GITHUB_RUN_ATTEMPT'],job_key=os.environ['GITHUB_JOB'],runner_image_version=os.environ.get('ImageVersion','UNAVAILABLE'),code_sha256={p:sha(ROOT/p) for p in EXECUTION_FILES})
        for name in EXECUTION_FILES:require(subprocess.check_output(['git','show',execution+':'+name],cwd=ROOT)==(ROOT/name).read_bytes(),'Uncommitted execution code')
        env=environment_receipt(plan,pathlib.Path(args.wheel));write(out/'environment.json',env);record['environment_status']='PASS'
        source=out.parent/'phase7g-baseline';require(not source.exists(),'Existing source worktree refused')
        subprocess.run(['git','worktree','add','--detach',str(source),plan['input_commit']],cwd=ROOT,check=True)
        before=input_snapshot(source,plan);record['input_sha256']=before
        for p in source.rglob('*'):
            if p.is_file():p.chmod(p.stat().st_mode & ~0o222)
        for p in sorted(source.rglob('*'),reverse=True):
            if p.is_dir():p.chmod(p.stat().st_mode & ~0o222)
        source.chmod(source.stat().st_mode & ~0o222)
        record['input_read_only_status']='MODE_BITS_WRITE_DISABLED'
        inherited=os.environ.copy();inherited.pop('PYTHONPATH',None)
        for key in list(inherited):
            if key.startswith('PHASE7G_OBSERVER_'):inherited.pop(key)
        tests=[p for p in EXECUTION_FILES if p.startswith('tests/')];test_results=[]
        for name in tests:
            result=run_command([sys.executable,str(ROOT/name)],ROOT,out/'tests'/pathlib.Path(name).stem,inherited);test_results.append(dict(test=name,**result))
        record['tests']=test_results;test_exit=next((r['exit_code'] for r in test_results if r['exit_code']),0)
        if test_exit:record['execution_status']='FAIL_TESTS';final_code=test_exit
        else:
            r_env=dict(inherited,PYTHONPATH=str(ROOT/'scripts/phase7g_observer'),PHASE7G_OBSERVER_SOURCE_ROOT=str(source),PHASE7G_OBSERVER_OUTPUT=str(out/'R-observer'))
            R=run_command([sys.executable,'scripts/check_orbital_energy.py'],source,out/'R',r_env);record['R']=R
            I=run_command([sys.executable,str(ROOT/'scripts/replay_public_independent.py'),'--source-root',str(source),'--plan',str(ROOT/PLAN),'--output',str(out/'I')],ROOT,out/'I-process',inherited);record['I']=I
            diagnosis,dcode=diagnostic(source,out,R,I);record['platform_classification']=diagnosis['classification']
            final_code=aggregate_exit(test_exit,R['exit_code'],I['exit_code'],dcode)
            record['execution_status']='PASS' if final_code==0 else 'FAIL_WITH_SEPARATE_PATH_RESULTS'
        require(input_snapshot(source,plan)==before,'Public input changed during replay');record['public_input_identity_status']='PASS'
        require({p:sha(ROOT/p) for p in EXECUTION_FILES}==record['code_sha256'],'Execution code changed during run')
        record['input_after_sha256']=before
    except BaseException as error:
        record.update(execution_status='FAIL',reason=type(error).__name__+': '+str(error));print(record['reason'],file=sys.stderr);final_code=1
    finally:
        if source is not None and before is not None:
            try:
                require(input_snapshot(source,plan)==before,'Public input changed during replay')
                record['public_input_identity_status']='PASS';record['input_after_sha256']=before
            except Exception as error:
                record.update(public_input_identity_status='FAIL',execution_status='FAIL',input_after_error=type(error).__name__+': '+str(error));final_code=1
    record.update(exit_code=final_code,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    try:write(out/'replay.json',record)
    except Exception as error:print('FINAL RECEIPT PERSISTENCE FAILED: '+str(error),file=sys.stderr);return 9
    print(json.dumps({'execution_status':record['execution_status'],'exit_code':final_code,'R':record['R'].get('exit_code'),'I':record['I'].get('exit_code')}))
    return final_code
if __name__=='__main__':sys.exit(main())
