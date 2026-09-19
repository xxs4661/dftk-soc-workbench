"""Synthetic protocol/source tests; no Julia or material context is started."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('local_probe_unit_supervisor', ROOT/'benchmarks/soc-validation-local-v1/supervisor.py')
S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)


class LocalProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name).resolve()/'SYNTHETIC-local'
        self.d.mkdir(); (self.d/'worker').mkdir()
        self.c = S.CONTROL.create_control(self.d,execution_commit='a'*40,source_commit='b'*40,
            task_id='SYNTHETIC-local',case_sha256='c'*64,budget_seconds=3,
            batch_deadline_unix_ns=time.time_ns()+int(10e9),synthetic=True,
            grace_seconds=.3,term_seconds=.2,kill_seconds=.2)
        self.value = {k:self.c[k] for k in ('run_id','task_id','execution_commit','source_commit','case_sha256','control_sha256')}
        self.value.update(schema_version=1,execution_status=S.SUCCESS,exit_code=0,
                          runtime_closed=True,workspace_released=True)

    def test_static_success_is_not_scf(self):
        self.assertEqual(S.worker_contract(self.value,0,self.c,self.d)['execution_status'],S.SUCCESS)
        for status in ('PASS','DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED'):
            bad = dict(self.value,execution_status=status)
            with self.assertRaises(ValueError): S.worker_contract(bad,0,self.c,self.d)

    def test_no_counterfeit_maps_or_final_checkpoint(self):
        with self.assertRaises(ValueError): S.worker_contract(dict(self.value,completed_maps=2),0,self.c,self.d)
        (self.d/'worker/final.bin').write_bytes(b'SYNTHETIC not a physical checkpoint')
        with self.assertRaises(ValueError): S.worker_contract(self.value,0,self.c,self.d)

    def test_schema_native_and_identity_types(self):
        for key,value in [('schema_version',True),('exit_code',False),('source_commit','e'*40)]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                S.worker_contract(dict(self.value,**{key:value}),0,self.c,self.d)
        with self.assertRaises(ValueError): S.worker_contract(self.value,1,self.c,self.d)

    def test_legitimate_failure_preserves_native_code(self):
        value = dict(self.value,execution_status='FAIL',exit_code=3,reason='Synthetic input failure')
        self.assertEqual(S.worker_contract(value,3,self.c,self.d)['exit_code'],3)

    def test_latched_user_stop_cannot_succeed(self):
        request = S.CONTROL.request_stop(self.d,run_id=self.c['run_id'],execution_commit=self.c['execution_commit'])
        with self.assertRaises(ValueError): S.worker_contract(self.value,0,self.c,self.d)
        value = dict(self.value,execution_status='USER_CANCELLED',exit_code=130,
            control=dict(first_request_sha256=request['request_sha256'],acknowledged_boundary='synthetic-before-validation'))
        self.assertEqual(S.worker_contract(value,130,self.c,self.d)['exit_code'],130)
        value.update(runtime_closed=False,workspace_released=False,context_constructed=False,
                     owned_runtime_constructed=False,runtime_state='NOT_CONSTRUCTED')
        self.assertEqual(S.worker_contract(value,130,self.c,self.d)['runtime_state'],'NOT_CONSTRUCTED')

    def test_both_roles_are_fixed_and_registration_is_private(self):
        self.assertEqual(S.specification(ROOT,'DIAG-S','f'*40)['source_commit'],S.registration(ROOT)['R'])
        self.assertEqual(S.specification(ROOT,'DIAG-F','f'*40)['source_commit'],S.registration(ROOT)['B'])
        self.assertEqual(S.specification(ROOT,'BENCH-F','f'*40)['strategy'],'single_validation_v1')
        self.assertEqual(S.CONTROL.TASKS,{task:600 for task in S.TASKS})
        self.assertIn('T-B0-REF',S.SHARED.control.TASKS)
        self.assertNotIn('DIAG-S',S.SHARED.control.TASKS)
        with self.assertRaises(ValueError): S.specification(ROOT,'BENCH-C','f'*40)

    def test_real_registration_preserves_budget_and_resource_policy(self):
        d = self.d.parent/'DIAG-S-real-control-only'; d.mkdir()
        c = S.CONTROL.create_control(d,execution_commit='a'*40,source_commit='b'*40,
            task_id='DIAG-S',case_sha256='c'*64,budget_seconds=600,
            batch_deadline_unix_ns=time.time_ns()+int(601e9))
        self.assertEqual((c['limit_bytes'],c['warning_bytes'],c['remaining_growth_bytes']),(8*S.GIB,7*S.GIB,2*S.GIB))
        self.assertEqual((c['grace_seconds'],c['term_seconds'],c['kill_seconds']),(120,10,5))
        self.assertFalse((d/'process-start.json').exists())
        with self.assertRaises(ValueError): S.CONTROL.create_control(self.d,execution_commit='a'*40,source_commit='b'*40,
            task_id='DIAG-S',case_sha256='c'*64,budget_seconds=600,
            batch_deadline_unix_ns=time.time_ns()+int(299e9))

    def test_entry_requires_real_identity_and_no_context(self):
        route = dict(run_id='entry',task_id='DIAG-S',execution_commit='a'*40,source_commit='b'*40,
                     case_sha256='c'*64,fixture_sha256='d'*64,density_sha256='e'*64,role='S',strategy='strict',mode='diagnostic',
                     source_sha256={'runtime.jl':'1'*64,'hamiltonian.jl':'2'*64})
        value = {k:v for k,v in route.items() if k != 'source_sha256'}
        value.update(schema_version=1,experiment=S.EXPERIMENT,environment={'status':'PASS'},
                     actual_method_sources={'runtime_boundary':{'relative_path':'runtime.jl','source_sha256':'1'*64},
                                            'validate_context':{'relative_path':'hamiltonian.jl','source_sha256':'2'*64}},
                     execution_status='CHECK_ONLY_PASS',exit_code=0,check_only=True,context_constructed=False,
                     owned_runtime_constructed=False,formal_slot_reserved=False,numerical_execution_status='NOT_RUN')
        self.assertEqual(S.entry_contract(json.dumps(value),0,route)['exit_code'],0)
        for key in ('context_constructed','owned_runtime_constructed','formal_slot_reserved'):
            with self.subTest(key=key),self.assertRaises(ValueError):
                S.entry_contract(json.dumps(dict(value,**{key:True})),0,route)
        with self.assertRaises(ValueError): S.entry_contract('',0,route)
        bad = copy.deepcopy(value);bad['actual_method_sources']['validate_context']['source_sha256']='f'*64
        with self.assertRaises(ValueError): S.entry_contract(json.dumps(bad),0,route)

    def test_denied_or_empty_observer_fails_closed(self):
        for error in (PermissionError('Synthetic operation not permitted: ps'), ValueError('Empty process table')):
            resource = types.SimpleNamespace(process_table=lambda: (_ for _ in ()).throw(error))
            result = S.observer_preflight(resource,ROOT)
            self.assertEqual(result['status'],'BLOCKED_RESOURCE_OBSERVATION')
            self.assertFalse(result['slot_consumed']);self.assertIsNone(result['native_exit_code'])

    def test_denied_observer_consumes_no_slot_and_never_launches(self):
        root = self.d.parent/'repo';root.mkdir()
        denied = types.SimpleNamespace(process_table=lambda: (_ for _ in ()).throw(PermissionError('Synthetic ps denial')))
        def git(root,*args):
            return (S.BRANCH if args[0] == 'branch' else 'a'*40).encode()
        def routed(root,source,task,outdir,execution,check=False):
            return dict(source_root=str(root),source_commit='b'*40,case_sha256='c'*64)
        with patch.object(S,'ROOT',root),patch.object(S.ROUTE,'git',git),patch.object(S,'prepare_route',routed),\
             patch.object(S,'module',return_value=denied),patch.dict(os.environ,{'JULIA_DEPOT_PATH':str(root)}),\
             patch.object(S.CONTROL,'launch_worker') as launch,patch.object(S,'slot_directory') as slots:
            self.assertEqual(S.run('DIAG-S','/synthetic/julia',root),17)
            launch.assert_not_called();slots.assert_not_called()
        record = json.loads(next((root/'.work/soc-validation-local/runs').glob('*/launcher.json')).read_text())
        self.assertEqual(record['execution_status'],'BLOCKED_RESOURCE_OBSERVATION')
        self.assertFalse(record['slot_consumed']);self.assertIsNone(record['native_exit_code'])
        self.assertFalse(list((root/'.work').glob('**/active.json')))

    def test_budget_counts_active_time_not_edit_idle(self):
        root = self.d.parent/'budget-repo';root.mkdir();slots=root/'slots';slots.mkdir()
        d=root/'old-run';d.mkdir()
        records={'process-start.json':{'pid':123},'process-exit.json':{'exit_code':1},
                 'resource.json':{'elapsed_seconds':400,'owned_process_cleanup_status':'PASS'},'result.json':{'exit_code':1}}
        for name,value in records.items(): (d/name).write_text(json.dumps(value))
        work=dict(run_id=d.name,task_id='DIAG-S',charged_seconds=402,cleanup_status='PASS',
                  receipt_sha256={name:S.sha(d/name) for name in records})
        (d/'active-work.json').write_text(json.dumps(work))
        (slots/'DIAG-S.json').write_text(json.dumps(dict(run_id=d.name,task_id='DIAG-S',directory=str(d))))
        with patch.object(S,'slot_directory',return_value=slots):
            self.assertEqual(S.budget_remaining(root),1398)
            work['charged_seconds']=399;(d/'active-work.json').write_text(json.dumps(work))
            with self.assertRaises(ValueError): S.budget_remaining(root)
            work['charged_seconds']=402;work['cleanup_status']='UNKNOWN'
            (d/'active-work.json').write_text(json.dumps(work))
            with self.assertRaises(ValueError): S.budget_remaining(root)

    def evidence(self, mode):
        value = dict(outer_integrity_status='PASS')
        def artifact(name,key,data):
            (self.d/'worker'/name).write_text(json.dumps(data))
            value[key] = S.sha(self.d/'worker'/name)
        artifact('fixture-observed.json','fixture_observed_sha256',{'scope':'SYNTHETIC protocol fixture'})
        route = dict(mode=mode,role='S',adapter_root=str(self.d))
        if mode == 'diagnostic':
            artifact('trace.json','trace_sha256',[dict(operation=n,returned=True,
                     trace=dict(operation=n,role='S',events=[{'scope':'SYNTHETIC'}])) for n in ('boundary','storage')])
            artifact('observer.json','observer_sha256',dict(role='S',scope='INSTRUMENTED_DIAGNOSTIC_NOT_MAIN_TIMING'))
        else:
            selection = self.d/'benchmarks/soc-validation-local-v1';selection.mkdir(parents=True)
            (selection/'selection.json').write_text(json.dumps({'sequences':[]}))
            artifact('samples.json','samples_sha256',[dict(operation=n,sample_index=i,
                     kind='warmup' if i <= 2 else 'measurement',seconds=.01,gc_seconds=0,allocation_bytes=32)
                     for n in ('boundary','storage') for i in range(1,8)])
        return value,route,artifact

    def test_diagnostic_artifacts_are_required_and_authenticated(self):
        value,route,artifact = self.evidence('diagnostic')
        S.operation_evidence(value,route,self.d)
        (self.d/'worker/trace.json').write_text('[]')
        with self.assertRaises(ValueError): S.operation_evidence(value,route,self.d)
        artifact('trace.json','trace_sha256',[])
        with self.assertRaises(ValueError): S.operation_evidence(value,route,self.d)

    def test_diagnostic_false_return_or_integrity_failure_is_not_success(self):
        value,route,artifact = self.evidence('diagnostic')
        data=json.loads((self.d/'worker/trace.json').read_text());data[0]['returned']=False
        artifact('trace.json','trace_sha256',data)
        with self.assertRaises(ValueError): S.operation_evidence(value,route,self.d)
        data[0]['returned']=True;artifact('trace.json','trace_sha256',data)
        value['outer_integrity_status']='FAIL'
        with self.assertRaises(ValueError): S.operation_evidence(value,route,self.d)

    def test_benchmark_requires_all_two_warmups_and_five_samples(self):
        value,route,artifact = self.evidence('benchmark')
        S.operation_evidence(value,route,self.d)
        original=json.loads((self.d/'worker/samples.json').read_text())
        for altered in ([],original[:-1],original+[original[0]]):
            artifact('samples.json','samples_sha256',altered)
            with self.assertRaises(ValueError): S.operation_evidence(value,route,self.d)

    def test_benchmark_invalid_values_and_phase_fail(self):
        value,route,artifact = self.evidence('benchmark')
        original=json.loads((self.d/'worker/samples.json').read_text())
        for key,bad in (('seconds',float('nan')),('gc_seconds',-1),('allocation_bytes',True),('kind','measurement'),('sample_index',True)):
            data=copy.deepcopy(original);data[0][key]=bad
            artifact('samples.json','samples_sha256',data)
            with self.subTest(key=key),self.assertRaises(ValueError): S.operation_evidence(value,route,self.d)

    def test_all_benchmarks_gate_before_source_loading(self):
        for task in ('BENCH-S','BENCH-F'):
            with patch.object(S,'benchmark_gate',side_effect=ValueError('Synthetic no observed mechanism')),\
                 patch.object(S.ROUTE,'tree_identity') as loaded:
                with self.assertRaisesRegex(ValueError,'no observed mechanism'):
                    S.prepare_route(ROOT,ROOT.parent/'synthetic-reference',task,self.d/'worker','a'*40)
                loaded.assert_not_called()


if __name__ == '__main__': unittest.main(verbosity=2)
