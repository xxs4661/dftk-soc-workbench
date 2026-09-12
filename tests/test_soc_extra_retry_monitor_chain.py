"""Full RUN.monitored synthetic chain with real short Python processes.

Only the process-table RSS values and host-pressure response are injected.
The actual existing executor, sampler, run-level observer, canonical policy,
atomic stop file, native exit receipt and owned cleanup are exercised. The
optional Julia bridge loads definitions and calls a safety boundary only;
no numerical context, material input, solve or production authorization is used.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT/relative)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


RUN = load('benchmarks/soc-extra-v1/run.py', 'retry_actual_monitor_chain')
R = load('benchmarks/soc-extra-v1/resources.py', 'retry_actual_monitor_resources')
TOOL = RUN.module(ROOT, 'benchmarks/soc-core-memory-v1/run.py', 'retry_actual_monitor_tool')
GIB = 1024**3
GROWTH = 2021087414


def policy(ten=False):
    return dict(schema_version=1, policy_id='k6-scf-attempt2-10gib-v1' if ten else 'extra-default-8gib-v2',
                limit_bytes=(10 if ten else 8)*GIB, warning_bytes=(8 if ten else 7)*GIB,
                remaining_growth_bytes=GROWTH, run_id='SYNTHETIC-MONITOR-CHAIN',
                action='X-K6-SCF', case_sha256='a'*64, execution_commit='b'*40)


WORKER = '''import hashlib,json,os,pathlib,sys,time
d=pathlib.Path.cwd(); mode=sys.argv[1];p=json.loads((d/'resource-policy.json').read_text())
h=hashlib.sha256((d/'resource-policy.json').read_bytes()).hexdigest()
identity={k:p[k] for k in ('policy_id','run_id','action','case_sha256','execution_commit')}
identity.update(schema_version=1,resource_policy_sha256=h)
def atomic(name,value):
 q=d/(name+'.tmp');q.write_text(json.dumps(value));q.replace(d/name)
start=time.time();changed=False;declined=False;native_emergency=False
while time.time()-start<.85:
 now=time.time(); high=500*1024**2
 if mode=='wrong_run':identity['run_id']='FOREIGN'
 if mode=='missing_policy_id':identity.pop('policy_id',None)
 if mode=='stale':now=start-100
 if mode=='decline' and time.time()-start>.30:high=400*1024**2
 if mode=='native_limit':high=p['limit_bytes']
 report=dict(identity,highwater_bytes=high,units='bytes',event='SYNTHETIC_BOUNDARY',reported_unix_time=now)
 atomic('resource-highwater.json',report)
 if mode=='tamper_policy' and not changed and time.time()-start>.15:
  p['remaining_growth_bytes']=1;atomic('resource-policy.json',p);changed=True
 if mode=='native_limit' and not native_emergency:
  decision=dict(status='RESOURCE_LIMIT',reason='SYNTHETIC native hard limit',current_group_rss_bytes=None,
   peak_group_rss_bytes=None,worker_highwater_bytes=high,screen_peak_bytes=high,
   remaining_growth_bytes=p['remaining_growth_bytes'],limit_bytes=p['limit_bytes'],warning_bytes=p['warning_bytes'])
  atomic('safe-boundary-stop.json',dict(identity,first_requested_unix_time=time.time(),resource_decision=decision));native_emergency=True
  time.sleep(.15);sys.exit(17)
 stop=d/'safe-boundary-stop.json'
 if stop.exists() and mode not in ('ignore_stop','native_limit'):
  value=json.loads(stop.read_text());assert value['run_id']==p['run_id'];assert value['resource_policy_sha256']==h
  sys.exit(17)
 time.sleep(.01)
sys.exit(0)
'''

JULIA_BOUNDARY = '''using JSON3, SHA, Serialization, Test
const PHASE6C_ROOT=ARGS[1]
filehash(path)=bytes2hex(sha256(read(path)))
si_json(path)=JSON3.read(read(path,String),Dict{String,Any})
include(joinpath(PHASE6C_ROOT,"benchmarks/soc-extra-v1/driver.jl"))
directory=pwd();outdir=joinpath(directory,"synthetic-worker");mkpath(outdir)
policy=si_json(joinpath(directory,"resource-policy.json"))
auth=Dict("selected_resource_policy"=>policy,
 "selected_resource_policy_sha256"=>filehash(joinpath(directory,"resource-policy.json")),
 "execution_commit"=>policy["execution_commit"],"case_sha256"=>policy["case_sha256"])
state=si_extra_boundary_state(outdir,auth)
@test state isa ExtraBoundaryState
@test state.policy["limit_bytes"]==8*1024^3
deadline=time()+20
while time()<deadline
 try
  si_extra_safe_boundary(outdir,"SYNTHETIC_BOUNDARY_ONLY",state)
 catch err
  reason=sprint(showerror,err)
  result=Dict("scope"=>"SYNTHETIC Julia boundary definitions only; no context/solve",
   "context_constructed"=>false,"numerical_execution_status"=>"NOT_RUN",
   "run_id"=>policy["run_id"],"resource_policy_sha256"=>state.policy_sha256,
   "first_stop_sha256"=>state.first_stop_sha256,"reason"=>reason)
  write("synthetic-boundary.json",JSON3.write(result))
  if occursin("RESOURCE_LIMIT",reason) && !isnothing(state.first_stop_sha256)
   exit(17)
  end
  rethrow()
 end
 sleep(.02)
end
error("Synthetic boundary did not receive its expected stop")
'''


class ActualMonitorChain(unittest.TestCase):
    def invoke(self, *, rss=100*1024**2, ten=False, mode='normal'):
        rules=policy(ten)
        with tempfile.TemporaryDirectory() as td:
            directory=Path(td); raw=json.dumps(rules,sort_keys=True,separators=(',',':')).encode()
            (directory/'resource-policy.json').write_bytes(raw)
            command=[sys.executable,'-B','-c',WORKER,mode]
            namespace=TOOL.monitored_execute.__globals__; actual=namespace['ps_rows']
            def sample_rows():
                rows=actual();p=directory/'process-start.json'
                if p.is_file():
                    try:leader=json.loads(p.read_text())['pid']
                    except json.JSONDecodeError:return rows
                    owned=namespace['owned_rows'](rows,leader)
                    for row in owned:row['rss_kib']=0
                    if owned:owned[0]['rss_kib']=rss//1024
                return rows
            with patch.object(RUN,'module',return_value=TOOL), \
                 patch.dict(namespace,ps_rows=sample_rows), \
                 patch.object(R,'host_pressure',return_value=dict(status='KNOWN',severe=False)):
                code,state=RUN.monitored(command,directory,os.environ.copy(),R,GROWTH,policy=rules)
            self.assertEqual(json.loads((directory/'process-exit.json').read_text())['exit_code'],code)
            self.assertEqual(json.loads((directory/'resource.json').read_text()),state)
            self.assertEqual(state['native_exit_code'],code)
            self.assertEqual(state['owned_process_cleanup_status'],'PASS')
            self.assertGreater(state['nonempty_samples'],0)
            self.assertEqual(state['resource_policy_sha256'],hashlib.sha256(raw).hexdigest())
            stopped=(directory/'safe-boundary-stop.json').read_bytes() if (directory/'safe-boundary-stop.json').exists() else None
            if state.get('first_stop_sha256'):
                self.assertEqual(hashlib.sha256(stopped).hexdigest(),state['first_stop_sha256'])
                self.assertEqual(json.loads(stopped),state['first_stop_request'])
            return code,state

    def test_normal_default_is_still_eight_gib(self):
        code,state=self.invoke()
        self.assertEqual(code,0);self.assertEqual(state['status'],'PASS')
        self.assertEqual(state['limit_bytes'],8*GIB)
        self.assertEqual(state['authenticated_worker_highwater_bytes'],500*1024**2)
        RUN.resource_contract(state,code,policy=policy())

    def test_native_boundary_exit_and_stop_are_preserved(self):
        unrelated=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(10)'],start_new_session=True)
        try:
            code,state=self.invoke(rss=7447937024)
            self.assertEqual(code,17)
            self.assertEqual(state['resource_policy_status'],'STOP_AT_SAFE_BOUNDARY')
            self.assertEqual(state['status'],'RESOURCE_BLOCKED')
            self.assertEqual(state['screen_peak_bytes'],7447937024)
            self.assertTrue(state['extra_policy']['safe_boundary_stop_requested'])
            self.assertIsNone(unrelated.poll())
            with self.assertRaises(ValueError):RUN.resource_contract(state,code,policy=policy())
        finally:unrelated.terminate();unrelated.wait()

    def test_native_zero_after_stop_cannot_be_accepted(self):
        code,state=self.invoke(rss=7447937024,mode='ignore_stop')
        self.assertEqual(code,0)
        self.assertEqual(state['resource_policy_status'],'STOP_AT_SAFE_BOUNDARY')
        self.assertEqual(state['status'],'RESOURCE_BLOCKED')
        with self.assertRaises(ValueError):RUN.resource_contract(state,code,policy=policy())

    def test_authenticated_ten_gib_mechanism_accepts_only_fitting_screen(self):
        code,state=self.invoke(rss=8*GIB+20*1024**2,ten=True)
        self.assertEqual(code,0);self.assertEqual(state['status'],'PASS')
        self.assertEqual(state['limit_bytes'],10*GIB)
        self.assertEqual(state['screen_peak_bytes'],8*GIB+20*1024**2)
        RUN.resource_contract(state,code,policy=policy(True))
        with self.assertRaises(ValueError):RUN.resource_contract(state,code,policy=policy())

    def test_policy_tamper_identity_time_and_highwater_decline_are_rejected(self):
        for mode,reason in [('tamper_policy','Resource policy changed'),('wrong_run','another policy'),
                            ('missing_policy_id','another policy'),('stale','not from this current run'),
                            ('decline','highwater decreased')]:
            with self.subTest(mode=mode):
                code,state=self.invoke(mode=mode)
                self.assertNotEqual(code,0)
                self.assertEqual(state['status'],'RESOURCE_BLOCKED')
                self.assertEqual(state['resource_policy_status'],'MONITORING_UNAVAILABLE')
                self.assertIn(reason,state['reason'])

    def test_valid_native_hard_limit_is_not_a_protocol_failure(self):
        code,state=self.invoke(mode='native_limit')
        self.assertNotEqual(code,0)
        self.assertEqual(state['status'],'RESOURCE_BLOCKED')
        self.assertEqual(state['resource_policy_status'],'RESOURCE_LIMIT')
        self.assertIn('SYNTHETIC native hard limit',state['reason'])

    def test_real_julia_boundary_reads_actual_python_stop_protocol(self):
        julia=shutil.which('julia'); depot=os.environ.get('JULIA_DEPOT_PATH')
        if not julia or not depot:
            self.skipTest('NOT_RUN: existing Julia and explicitly selected frozen JULIA_DEPOT_PATH required')
        self.assertTrue(all(Path(p).is_dir() for p in depot.split(os.pathsep)))
        with tempfile.TemporaryDirectory(prefix='synthetic-julia-monitor-') as td:
            directory=Path(td).resolve();rules=policy()
            rules.update(run_id=directory.name,remaining_growth_bytes=GIB)
            raw=json.dumps(rules,sort_keys=True,separators=(',',':')).encode()
            (directory/'resource-policy.json').write_bytes(raw)
            env=dict(os.environ,JULIA_LOAD_PATH='@:@stdlib',JULIA_PKG_OFFLINE='true',JULIA_NUM_THREADS='1',
                     OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',SOC_EXTRA_RUN_ID=directory.name,
                     SOC_EXTRA_RESOURCE_POLICY_FILE=str(directory/'resource-policy.json'))
            command=[julia,'--startup-file=no','--color=no','--project='+str(ROOT/'environment/workbench'),
                     '-e',JULIA_BOUNDARY,str(ROOT)]
            namespace=TOOL.monitored_execute.__globals__;actual=namespace['ps_rows']
            def sample_rows():
                rows=actual();start=directory/'process-start.json'
                if start.is_file() and (directory/'resource-highwater.json').is_file():
                    leader=json.loads(start.read_text())['pid'];owned=namespace['owned_rows'](rows,leader)
                    for row in owned:row['rss_kib']=0
                    if owned:owned[0]['rss_kib']=7*GIB//1024
                return rows
            with patch.object(RUN,'module',return_value=TOOL),patch.dict(namespace,ps_rows=sample_rows), \
                 patch.object(R,'host_pressure',return_value=dict(status='KNOWN',severe=False)):
                code,state=RUN.monitored(command,directory,env,R,GIB,policy=rules)
            evidence=os.environ.get('SOC_EXTRA_MONITOR_TEST_EVIDENCE')
            if evidence:
                destination=Path(evidence);destination.mkdir(parents=True,exist_ok=False)
                for name in ('qe.stdout','qe.stderr','process-start.json','process-exit.json','resource.json',
                             'resource-policy.json','resource-policy.jsonl','resource-highwater.json',
                             'safe-boundary-stop.json','synthetic-boundary.json'):
                    if (directory/name).is_file():shutil.copyfile(directory/name,destination/name)
                (destination/'test-scope.json').write_text(json.dumps(dict(
                    scope='SYNTHETIC actual Python to Julia boundary protocol; no context or material solve',
                    native_exit_code=code,driver_sha256=hashlib.sha256((ROOT/'benchmarks/soc-extra-v1/driver.jl').read_bytes()).hexdigest(),
                    sampler_sha256=hashlib.sha256((ROOT/'scripts/si_qe_reference_evidence.py').read_bytes()).hexdigest(),
                    observer_sha256=hashlib.sha256((ROOT/'benchmarks/soc-extra-v1/run.py').read_bytes()).hexdigest()),indent=2)+'\n')
            self.assertEqual(code,17,(directory/'qe.stderr').read_text())
            self.assertEqual(state['resource_policy_status'],'STOP_AT_SAFE_BOUNDARY')
            self.assertEqual(state['status'],'RESOURCE_BLOCKED')
            self.assertEqual(state['owned_process_cleanup_status'],'PASS')
            self.assertGreater(state['authenticated_worker_highwater_bytes'],0)
            self.assertEqual(state['native_exit_code'],17)
            self.assertEqual(state['screen_peak_bytes'],7*GIB)
            bridge=json.loads((directory/'synthetic-boundary.json').read_text())
            self.assertEqual(bridge['first_stop_sha256'],state['first_stop_sha256'])
            self.assertEqual(bridge['resource_policy_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertFalse(bridge['context_constructed'])
            self.assertEqual(bridge['numerical_execution_status'],'NOT_RUN')


if __name__=='__main__':unittest.main(verbosity=2)
