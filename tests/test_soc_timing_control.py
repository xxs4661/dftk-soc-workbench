"""Bounded real subprocess protocol tests; synthetic data and no material context.

All attempts are retained under .work/soc-timing/cancel-tests. The signal/timeout
batch has a five-minute aggregate deadline; individual workers self-limit too.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
import tomllib
import unittest
import uuid

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('timing_control',ROOT/'benchmarks/soc-timing-v1/control.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
E='a'*40;SOURCE='b'*40;CASE='c'*64

PYWORKER=r'''
import json,time,sys,os,signal,subprocess,tomllib,hashlib
from pathlib import Path
root=Path.cwd();cfg=tomllib.loads((root/'control.toml').read_text());mode=sys.argv[1]
worker=root/'worker';worker.mkdir()
r={k:cfg[k] for k in ['run_id','execution_commit','source_commit','task_id','case_sha256']}
r.update(schema_version=1,control_sha256=hashlib.sha256((root/'control.toml').read_bytes()).hexdigest(),
 runtime_closed=True,workspace_released=True,completed_maps=0,scope='SYNTHETIC protocol only; no physical runtime')
if mode=='ignore':signal.signal(signal.SIGTERM,signal.SIG_IGN)
if mode=='orphan':
 child=subprocess.Popen([sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(6)'],start_new_session=True)
 (root/'child.pid').write_text(str(child.pid))
(root/'ready').write_text('ready')
start=time.monotonic();code=0
if mode=='missing':time.sleep(.35);sys.exit(3)
if mode=='contradict':
 time.sleep(.35);r.update(execution_status='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED',completed_maps=2,exit_code=0)
 (worker/'result.json').write_text(json.dumps(r));sys.exit(7)
while time.monotonic()-start<6:
 if mode=='normal' and time.monotonic()-start>.35:
  r.update(execution_status='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED',completed_maps=2);break
 stop=root/'stop-request.toml'
 if stop.exists() and mode!='ignore':
  request=tomllib.loads(stop.read_text());reason=request['reason'];code={'USER_CANCELLED':130,'TIME_BUDGET_EXCEEDED':124}.get(reason,17)
  r.update(execution_status=reason,reason=request['detail'],control={'first_request_sha256':hashlib.sha256(stop.read_bytes()).hexdigest(),'acknowledged_boundary':'synthetic-loop'})
  if mode=='swallow':r.update(execution_status='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED',completed_maps=2);code=0
  if mode=='writefail':
   (worker/'synthetic-checkpoint.tmp').mkdir()
   try:(worker/'synthetic-checkpoint.tmp').write_text('not an array')
   except OSError as error:r.update(execution_status='FAIL',reason=type(error).__name__+': '+str(error),errors=[str(error)]);code=1
  break
 time.sleep(.02)
else:r.update(execution_status='FAIL',reason='Synthetic self deadline');code=1
r['exit_code']=code;(worker/'result.json').write_text(json.dumps(r));sys.exit(code)
'''

JLWORKER=r'''
using TOML, SHA
root=pwd();repo=ARGS[1];mode=ARGS[2]
mode=="catch_sigint" && Base.exit_on_sigint(false)
include(joinpath(repo,"prototypes","diagnostics.jl"))
include(joinpath(repo,"benchmarks","soc-timing-v1","control.jl"))
D=WorkbenchDiagnostics;C=SocTimingControl
cfg=TOML.parsefile(joinpath(root,"control.toml"))
state=C.load_control(root;expected_run_id=cfg["run_id"],expected_execution_commit=cfg["execution_commit"],
 expected_source_commit=cfg["source_commit"],expected_task_id=cfg["task_id"],expected_case_sha256=cfg["case_sha256"])
mkpath(joinpath(root,"worker"))
r=Dict{String,Any}(k=>cfg[k] for k in ("run_id","execution_commit","source_commit","task_id","case_sha256"))
r["schema_version"]=1;r["completed_maps"]=0;r["scope"]="SYNTHETIC standard-library script; no DFTK context"
json(x::Nothing)="null"
json(x::Bool)=x ? "true" : "false"
json(x::Number)=string(x)
json(x::AbstractString)=repr(x)
json(x::AbstractVector)="["*join(json.(x),",")*"]"
json(x::AbstractDict)="{"*join([repr(string(k))*":"*json(v) for (k,v) in x],",")*"}"
function run_synthetic()
 code=1
 try
 C.boundary!(state,"synthetic-initialized")
 write(joinpath(root,"ready"),string(VERSION))
 deadline=time()+8
 while time()<deadline
  C.boundary!(state,"synthetic-loop",1,1)
  sleep(.02)
 end
 error("Synthetic deadline")
catch err
 if err isa D.ControlledStop
  r["execution_status"]=err.reason;r["reason"]=sprint(showerror,err)
  code=err.reason=="USER_CANCELLED" ? 130 : err.reason=="TIME_BUDGET_EXCEEDED" ? 124 : 17
 else
  r["execution_status"]="FAIL";r["reason"]=sprint(showerror,err);code=1
  showerror(stderr,err,catch_backtrace());println(stderr)
 end
finally
 r["runtime_closed"]=true;r["workspace_released"]=true
 try C.boundary!(state,"synthetic-closed",0,0;propagate=false) catch err
  r["execution_status"]="FAIL";r["reason"]=sprint(showerror,err);code=1
 end
 r["control"]=C.summary(state);r["control_sha256"]=state.control_sha256;r["exit_code"]=code
 write(joinpath(root,"worker","result.json"),json(r)*"\n")
end
 return code
end
exit(run_synthetic())
'''

class ControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.start=time.monotonic();cls.base=ROOT/'.work/soc-timing/cancel-tests'/('synthetic-'+uuid.uuid4().hex)
        cls.base.mkdir(parents=True);cls.records=[]
    @classmethod
    def tearDownClass(cls):
        C.atomic_json(cls.base/'cancel-tests.json',dict(scope='SYNTHETIC real launcher/worker/recorder, not physical success',elapsed_seconds=time.monotonic()-cls.start,records=cls.records))
    def make(self,name,budget=5):
        self.assertLess(time.monotonic()-self.start,300,'Synthetic signal/time budget exhausted')
        d=self.base/(name+'-'+uuid.uuid4().hex[:8]);d.mkdir()
        C.create_control(d,execution_commit=E,source_commit=SOURCE,task_id='SYNTHETIC-'+name,
            case_sha256=CASE,budget_seconds=budget,batch_deadline_unix_ns=time.time_ns()+int(10e9),
            synthetic=True,grace_seconds=2 if budget==9 else .35,term_seconds=.2,kill_seconds=.3)
        return d
    def invoke(self,mode,*,action=None,julia=False,budget=5):
        d=self.make(mode,budget);script=d/('synthetic.jl' if julia else 'synthetic.py')
        script.write_text(JLWORKER if julia else PYWORKER)
        if julia:
            exe=shutil.which('julia')
            if not exe:self.skipTest('NOT_RUN: Julia unavailable')
            cmd=[exe,'--startup-file=no','--project=@stdlib',str(script),str(ROOT),mode]
        else:cmd=[sys.executable,str(script),mode]
        observer_errors=[]
        def observe():
            deadline=time.monotonic()+10
            while not (d/'ready').exists() and time.monotonic()<deadline:
                if (d/'process-exit.json').exists():return
                time.sleep(.02)
            try:
                if not (d/'ready').exists():raise RuntimeError('Synthetic ready deadline')
                if action=='cancel':
                    if mode=='orphan':
                        child=int((d/'child.pid').read_text());end=time.monotonic()+2
                        while time.monotonic()<end:
                            log=d/'resource-samples.jsonl'
                            if log.exists() and any(any(p['pid']==child for p in row['processes']) for row in (json.loads(line) for line in log.read_text().splitlines())):break
                            time.sleep(.02)
                        else:raise RuntimeError('Child never observed; do not claim descendant cleanup test')
                    out=subprocess.run([sys.executable,str(ROOT/'benchmarks/soc-timing-v1/control.py'),'stop',
                        '--run-dir',str(d),'--run-id',d.name,'--execution-commit',E],capture_output=True,text=True,timeout=2)
                    (d/'request-cli.stdout').write_text(out.stdout);(d/'request-cli.stderr').write_text(out.stderr)
                    if out.returncode:raise RuntimeError('Stop CLI returned '+str(out.returncode))
                elif action=='sigint':
                    marker=json.loads((d/'process-start.json').read_text())
                    if marker['command']!=cmd or os.getpgid(marker['pid'])!=marker['pid']:raise RuntimeError('Synthetic signal identity differs')
                    args=subprocess.check_output(['ps','-p',str(marker['pid']),'-o','args='],text=True)
                    if str(script) not in args:raise RuntimeError('Synthetic PID command changed')
                    os.kill(marker['pid'],signal.SIGINT)
                    (d/'signal.json').write_text(json.dumps(dict(signal='SIGINT',pid=marker['pid'],authenticated_command=cmd)))
            except BaseException as error:observer_errors.append(repr(error))
        thread=threading.Thread(target=observe,daemon=True) if action else None
        if thread:thread.start()
        code,state=C.launch_worker(cmd,d)
        if thread:thread.join(11)
        self.records.append(dict(run_id=d.name,mode=mode,julia=julia,action=action,
            recorder_exit_code=code,native_exit_code=state.get('native_exit_code'),worker_exit_code=state.get('worker_exit_code'),
            execution_status=state.get('execution_status'),runtime_closed=state.get('worker',{}).get('runtime_closed'),
            process_cleanup=state.get('resource',{}).get('owned_process_cleanup_status'),
            forced_termination=state.get('forced_termination'),signals=state.get('resource',{}).get('signals'),
            original_stdout=str((d/'qe.stdout').relative_to(ROOT)),original_stderr=str((d/'qe.stderr').relative_to(ROOT)),observer_errors=observer_errors))
        self.assertFalse(observer_errors,(d,state,observer_errors));self.assertLess(time.monotonic()-self.start,300)
        return code,state,d
    def test_normal_diagnostic(self):
        code,s,d=self.invoke('normal');self.assertEqual(code,0,s);self.assertEqual(s['execution_status'],'DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED')
        self.assertFalse((d/'worker/final.bin').exists());self.assertEqual(s['resource']['owned_process_cleanup_status'],'PASS')
    def test_user_cancel_real_cli(self):
        code,s,d=self.invoke('wait',action='cancel');self.assertEqual((code,s['native_exit_code']),(130,130),s)
        self.assertEqual(s['execution_status'],'USER_CANCELLED');self.assertFalse(s['forced_termination'])
    def test_independent_timeout(self):
        code,s,d=self.invoke('wait',budget=.4);self.assertEqual((code,s['native_exit_code']),(124,124),s)
        self.assertEqual(s['execution_status'],'TIME_BUDGET_EXCEEDED')
    def test_missing_and_contradictory_worker_receipts(self):
        for mode,native in [('missing',3),('contradict',7)]:
            with self.subTest(mode=mode):
                code,s,d=self.invoke(mode);self.assertEqual(code,9,s);self.assertEqual(s['native_exit_code'],native)
    def test_cancellation_write_error_preserves_both(self):
        code,s,d=self.invoke('writefail',action='cancel');self.assertEqual((code,s['native_exit_code']),(1,1),s)
        self.assertEqual(s['execution_status'],'FAIL');self.assertEqual(s['stop_request']['reason'],'USER_CANCELLED')
        self.assertIn('IsADirectoryError',s['worker']['reason'])
    def test_swallowed_stop_cannot_become_success(self):
        code,s,d=self.invoke('swallow',action='cancel');self.assertEqual((code,s['native_exit_code']),(9,0),s)
        self.assertIn('latched stop',s['reason'])
    def test_request_identity_latch_stale_and_aliases(self):
        d=self.make('requests');c=C.load_control(d)
        with self.assertRaises(ValueError):C.request_stop(d,run_id='other',execution_commit=E)
        with self.assertRaises(ValueError):C.request_stop(d,run_id=d.name,execution_commit='f'*40)
        r=C.request_stop(d,run_id=d.name,execution_commit=E);before=(d/'stop-request.toml').read_bytes()
        again=C.request_stop(d,run_id=d.name,execution_commit=E,detail='second reason');self.assertEqual(r,again);self.assertEqual(before,(d/'stop-request.toml').read_bytes())
        alias=d.parent/(d.name+'-alias');alias.symlink_to(d,target_is_directory=True)
        with self.assertRaises(ValueError):C.request_stop(alias,run_id=d.name,execution_commit=E)
        stale=dict(r);stale.pop('request_sha256');stale['requested_unix_ns']=c['created_unix_ns']-1
        (d/'stop-request.toml').write_bytes(C.toml_bytes(stale))
        with self.assertRaises(ValueError):C.read_request(d,c)
    def test_precontext_cancel_is_not_fabricated_runtime_close(self):
        d=self.make('precontext');c=C.load_control(d);r=C.request_stop(d,run_id=d.name,execution_commit=E)
        value={k:c[k] for k in ['run_id','execution_commit','source_commit','task_id','case_sha256','control_sha256']}
        value.update(schema_version=1,exit_code=130,execution_status='USER_CANCELLED',runtime_state='NOT_CONSTRUCTED',
            context_constructed=False,owned_runtime_constructed=False,runtime_closed=False,workspace_released=False,
            control={'first_request_sha256':r['request_sha256'],'acknowledged_boundary':'before-load'})
        C.worker_contract(value,130,c,d)
        for key in ['context_constructed','owned_runtime_constructed']:
            with self.subTest(key=key),self.assertRaises(ValueError):C.worker_contract(dict(value,**{key:True}),130,c,d)
    def test_loaded_policy_types_limits_and_minimum_deadline_are_rejected(self):
        for key,value in [('limit_bytes',10*C.GIB),('remaining_growth_bytes',0),('budget_seconds',True),
                          ('created_monotonic_ns','not a clock'),('nonce','wrong'),('effective_deadline_unix_ns',1)]:
            with self.subTest(key=key):
                d=self.make('badpolicy');c=C.load_control(d);c.pop('control_sha256');c[key]=value
                (d/'control.toml').write_bytes(C.toml_bytes(c))
                with self.assertRaises(ValueError):C.load_control(d)
    def test_uncooperative_escalation_and_unrelated_survives(self):
        unrelated=subprocess.Popen([sys.executable,'-c','import time;time.sleep(3)'])
        try:
            code,s,d=self.invoke('ignore',action='cancel');self.assertEqual(code,9,s);self.assertEqual(s['native_exit_code'],-9,s)
            self.assertTrue(s['forced_termination']);self.assertEqual([x['signal'] for x in s['resource']['signals']],['SIGTERM','SIGKILL'])
            self.assertIsNone(unrelated.poll(),'unrelated process changed');self.assertEqual(s['resource']['owned_process_cleanup_status'],'PASS')
        finally:unrelated.wait(timeout=4)
    def test_parent_exit_still_cleans_observed_child(self):
        code,s,d=self.invoke('orphan',action='cancel');self.assertEqual(s['resource']['owned_process_cleanup_status'],'PASS',s)
        self.assertTrue(s['forced_termination']);self.assertNotEqual(code,0)
    def test_actual_julia_script_cooperative_boundary(self):
        code,s,d=self.invoke('cooperate',action='cancel',julia=True,budget=9)
        self.assertEqual((code,s['native_exit_code']),(130,130),s)
        self.assertEqual((d/'ready').read_text(),'1.12.7');self.assertEqual(s['worker']['control']['acknowledged_boundary'],'synthetic-loop')
    def test_actual_julia_script_default_sigint_preserved(self):
        code,s,d=self.invoke('raw_sigint',action='sigint',julia=True,budget=9)
        self.assertEqual((code,s['native_exit_code']),(9,-2),s);self.assertIsNone(s['worker_exit_code'])
        self.assertIn(s['execution_status'],('NATIVE_SIGNAL_EXIT','FORCED_TERMINATION'))
        if s['execution_status']=='FORCED_TERMINATION':self.assertTrue(s['resource']['signals'])
    def test_actual_julia_script_explicit_catch_sigint(self):
        code,s,d=self.invoke('catch_sigint',action='sigint',julia=True,budget=9)
        self.assertEqual((code,s['native_exit_code']),(1,1),s)
        self.assertTrue(s['worker']['runtime_closed']);self.assertIn('InterruptException',s['worker']['reason'])

if __name__=='__main__':unittest.main(verbosity=2)
