"""Synthetic registration/receipt tests; no material context or diagnostic slot."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location('boundary_test_'+name,ROOT/'benchmarks/soc-timing-v1'/f'{name}.py')
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj
R=load('route');C=load('control');RUN=load('run');CMP=load('compare')

def registration(root):
    dest=root/'benchmarks/soc-boundary-v1/contract.json';dest.parent.mkdir(parents=True)
    dest.write_bytes((ROOT/'benchmarks/soc-boundary-v1/contract.json').read_bytes())

def routed(root,task):
    spec=R.task_spec(task,root);execution='e'*40
    return dict(schema_version=1,task_id=task,profile=spec['profile'],budget_seconds=spec['budget_seconds'],
        timing_enabled=True,seed=81001,diagnostic_maps=2,limit_bytes=8*R.GIB,warning_bytes=7*R.GIB,
        remaining_growth_bytes=2*R.GIB,case_path=R.CASES[spec['profile']],case_sha256='c'*64,
        deadline_epoch=1900000000.,execution_commit=execution,
        source_commit=R.BOUNDARY_REFERENCE if spec['role']=='REF' else execution,
        adapter_root=str(root),numerical_root=str(root.parent/'independent-r') if spec['role']=='REF' else str(root),
        run_id='synthetic',worker_id='worker',outdir=str(root/'.work/soc-boundary/runs/synthetic/worker'),
        source_sha256={R.CASES[spec['profile']]:'c'*64},adapter_sha256={'driver':'d'*64},
        **{k:spec[k] for k in ['experiment','role','validation_policy','registration_sha256']})

def worker(c):
    value={k:c[k] for k in ['run_id','execution_commit','source_commit','task_id','case_sha256','control_sha256',
                           'experiment','timing_enabled','validation_policy','protection_gate_sha256']}
    validation=dict(policy='single_validation_v1',counter_status='MEASURED_OPT_IN',active=False,
                    live_array_entries=0,live_source_entries=0,closed=False,counters={'validation_calls':2})
    value.update(schema_version=1,exit_code=0,execution_status='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED',
        completed_maps=2,runtime_closed=True,workspace_released=True,environment={'status':'PASS'},
        parallelism={'julia':1,'blas':1,'fft':1,'mpi':1},map_checks_passed=True,runtime_dispatch_status='PASS',
        runtime_before_close=dict(backend='soc-core',counters={k:1 for k in ['fr_mul_calls','component_mul_calls','full_mul_calls']},validation=validation),
        runtime_after_close=dict(closed=True,workspace_released=True,owned_source_entries=0,validation=dict(validation,closed=True)))
    if c['validation_policy']=='strict':
        value['runtime_before_close'].pop('validation');value['runtime_after_close'].pop('validation')
    return value

class Registration(unittest.TestCase):
    def test_ref_and_opt_both_timed_but_distinct_sources(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();registration(root)
            for task in R.BOUNDARY_TASKS:
                item=R.validate_route(routed(root,task));self.assertTrue(item['timing_enabled'])
                self.assertEqual(item['source_commit'],R.BOUNDARY_REFERENCE if task.endswith('REF') else 'e'*40)
            self.assertEqual(R.task_spec('T-B0-REF')['reference_commit'],R.E0)
            self.assertFalse(R.task_spec('T-B0-REF')['timing_enabled'])
    def test_no_role_timing_namespace_or_policy_masquerade(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();registration(root)
            base=routed(root,'V-B0-REF')
            for key,bad in [('timing_enabled',False),('source_commit',R.E0),('numerical_root',str(root)),
                    ('validation_policy','single_validation_v1'),('budget_seconds',900.),('diagnostic_maps',3),
                    ('outdir',str(root/'.work/soc-timing/runs/synthetic/worker')),('task_id','V-K6-OPT')]:
                with self.subTest(key=key),self.assertRaises(ValueError):R.validate_route(dict(base,**{key:bad}))
            p=root/'benchmarks/soc-boundary-v1/contract.json';contract=json.loads(p.read_text())
            contract['tasks']['V-B0-REF']['budget_seconds']=900.;p.write_text(json.dumps(contract))
            with self.assertRaises(ValueError):R.task_spec('V-B0-REF',root)
    def test_batch_clock_bounded_at_5400_not_old_3600(self):
        b=dict(started_epoch=1000,started_monotonic_ns=1000000000,total_seconds=5400)
        self.assertEqual(RUN.remaining(b,now_epoch=6101,now_ns=11000000000),299)
        self.assertEqual(RUN.remaining(b,now_epoch=900,now_ns=5102000000000),299)
        with self.assertRaises(ValueError):RUN.remaining(dict(b,total_seconds=6000))
    def test_new_lock_also_conflicts_with_old_active_lock(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();old=root/'.work/soc-timing/active.json';old.parent.mkdir(parents=True)
            old.write_text('{"run_id":"other"}')
            with self.assertRaises(FileExistsError):
                with RUN.locks(root,'new',boundary=True):pass
            self.assertEqual(json.loads(old.read_text())['run_id'],'other')
            self.assertFalse((root/'.work/soc-boundary/active.json').exists())
    def test_inventory_covers_python_monitor_and_fixtures(self):
        names=['benchmarks/soc-timing-v1/driver.jl','benchmarks/soc-timing-v1/route.py',
               'benchmarks/soc-boundary-v1/contract.json','tests/soc_boundary/fixtures.jl']
        with patch.object(R,'git',return_value=('\n'.join(names)).encode()),patch.object(R,'exact_file',return_value='a'*64):
            found=R.adapter_files(ROOT,'e'*40,boundary=True)
        for name in ['scripts/run_qe_soc.py','scripts/si_qe_reference_evidence.py','benchmarks/soc-extra-v1/resources.py']:
            self.assertIn(name,found)
        with patch.object(RUN.route,'source_files',return_value={}),patch.object(RUN.route,'adapter_files',return_value={}),\
             patch.object(RUN.route,'git',return_value=('\n'.join(names)).encode()),patch.object(RUN.route,'exact_file',return_value='a'*64):
            self.assertIn('tests/soc_boundary/fixtures.jl',RUN.protection_sources(ROOT,'e'*40))

class Receipt(unittest.TestCase):
    def configure(self,d,task='V-B0-OPT'):
        return C.create_control(d,execution_commit='e'*40,
            source_commit=R.BOUNDARY_REFERENCE if task.endswith('REF') else 'e'*40,task_id=task,
            case_sha256='c'*64,budget_seconds=900 if '-B0-' in task else 1800,
            batch_deadline_unix_ns=time.time_ns()+5400*10**9,protection_gate_sha256='f'*64)
    def test_actual_candidate_policy_and_empty_closed_scope_required(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();c=self.configure(root);w=worker(c)
            self.assertEqual(C.worker_contract(w,0,c,root)['exit_code'],0)
            for key,bad in [('policy','strict'),('active',True),('live_array_entries',1),('live_source_entries',1),('closed',False)]:
                broken=copy.deepcopy(w);broken['runtime_after_close']['validation'][key]=bad
                with self.subTest(key=key),self.assertRaises(ValueError):C.worker_contract(broken,0,c,root)
            broken=copy.deepcopy(w);broken['runtime_before_close'].pop('validation')
            with self.assertRaises(ValueError):C.worker_contract(broken,0,c,root)
    def test_reference_does_not_invent_new_counters(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();c=self.configure(root,'V-K4-REF');w=worker(c)
            C.worker_contract(w,0,c,root)
            self.assertNotIn('validation',w['runtime_before_close'])
    def test_real_boundary_cannot_claim_synthetic_or_old_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();c=self.configure(root)
            for key,bad in [('source_commit',R.E0),('validation_policy','strict'),('synthetic',True),('protection_gate_sha256','')]:
                value=dict(c);value.pop('control_sha256');value[key]=bad
                (root/'control.toml').write_bytes(C.toml_bytes(value))
                with self.subTest(key=key),self.assertRaises(ValueError):C.load_control(root)
    def test_protection_requires_each_category_real_log_and_same_prepared_sources(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();area=root/'.work/soc-boundary';area.mkdir(parents=True)
            log=area/'checks.log';log.write_text('SYNTHETIC checks exit0\n')
            categories=['protection-equivalence','hash-equivalence','cancellation-timeout','source-entry',
                        'full-syntax','legacy-control','public-arithmetic','legacy-timer']
            value=dict(schema_version=1,experiment='soc-boundary-v1',status='PASS',preparation_commit='a'*40,
                tested_source_sha256={'source':'b'*64},checks=[dict(command='synthetic',exit_code=0,categories=categories,
                    log_path=str(log),log_sha256=R.sha(log))])
            p=area/'protection.json';p.write_text(json.dumps(value))
            with patch.object(RUN,'protection_sources',return_value={'source':'b'*64}),\
                 patch.object(RUN.route,'git',return_value=b'commit\n'),patch.object(RUN.route,'exact_file',return_value='b'*64):
                self.assertEqual(RUN.verify_protection(root,'e'*40)['checks'],1)
                missing=copy.deepcopy(value);missing['checks'][0]['categories']=categories[:-1];p.write_text(json.dumps(missing))
                with self.assertRaises(ValueError):RUN.verify_protection(root,'e'*40)
                p.write_text(json.dumps(value));log.write_text('changed')
                with self.assertRaises(ValueError):RUN.verify_protection(root,'e'*40)
            log.write_text('SYNTHETIC checks exit0\n')
            with patch.object(RUN,'protection_sources',return_value={'source':'b'*64}),\
                 patch.object(RUN.route,'git',return_value=b'commit\n'),patch.object(RUN.route,'exact_file',return_value='c'*64):
                with self.assertRaises(ValueError):RUN.verify_protection(root,'e'*40)
    def test_predecessor_cannot_hide_resource_or_process_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();registration(root);area=root/'.work/soc-boundary'
            task='V-B0-OPT';run=area/'runs'/'synthetic';(run/'worker').mkdir(parents=True)
            c=self.configure(run);w=worker(c);raw=json.dumps(w).encode();(run/'worker/result.json').write_bytes(raw)
            outer=dict(w,native_exit_code=0,worker_result_sha256=hashlib.sha256(raw).hexdigest(),
                       resource={'status':'PASS','owned_process_cleanup_status':'PASS'})
            (run/'result.json').write_text(json.dumps(outer));(run/'process-exit.json').write_text('{"exit_code":0}')
            (run/'resource.json').write_text(json.dumps(outer['resource']))
            (area/(task+'-accepted.json')).write_text(json.dumps(dict(run_id='synthetic',directory=str(run),execution_commit='e'*40)))
            RUN.checked_prior(root,area,task,'e'*40)
            (run/'process-exit.json').write_text('{"exit_code":-2}')
            with self.assertRaises(ValueError):RUN.checked_prior(root,area,task,'e'*40)
            (run/'process-exit.json').write_text('{"exit_code":0}');(run/'resource.json').write_text('{"status":"FAIL","owned_process_cleanup_status":"PASS"}')
            with self.assertRaises(ValueError):RUN.checked_prior(root,area,task,'e'*40)

class NumericalArithmetic(unittest.TestCase):
    def record(self,n=4):
        axis=[0,-.5] if n==2 else [0,.25,-.5,-.25]
        return dict(map_index=1,kpoints=[[x,y,z] for x in axis for y in axis for z in axis],
            eigenvalues_ha=[[v/10 for v in range(24)] for _ in range(n**3)],internal_energy_ha=-8.,
            free_energy_ha=-8.01,energy_terms_ha={str(i):float(i) for i in range(7)})
    def test_64_same_map_and_original_norm_denominator(self):
        x=self.record();out=CMP.compare_values(x,x,[3.,4.],[3.,4.],expected_kpoints=64,boundary=True)
        self.assertEqual(out['status'],'PASS');self.assertEqual(out['density_denominator'],5.)
        self.assertEqual(out['density_reference_norm'],5.);self.assertEqual(out['density_difference_norm'],0.)
        self.assertEqual(out['energy_terms_delta_ha'],{str(i):0. for i in range(7)})
    def test_64_count_duplicate_energy_and_level_errors(self):
        x=self.record()
        with self.assertRaises(ValueError):CMP.compare_values(x,x,[1.],[1.],boundary=True)
        y=copy.deepcopy(x);y['kpoints'][1]=y['kpoints'][0]
        with self.assertRaises(ValueError):CMP.compare_values(y,y,[1.],[1.],expected_kpoints=64,boundary=True)
        for name in ('internal_energy_ha','free_energy_ha'):
            y=copy.deepcopy(x);y[name]+=1e-7
            self.assertEqual(CMP.compare_values(x,y,[1.],[1.],expected_kpoints=64,boundary=True)['status'],'FAIL')
        y=copy.deepcopy(x);y['eigenvalues_ha'][10][20]+=1e-6
        self.assertEqual(CMP.compare_values(x,y,[1.],[1.],expected_kpoints=64,boundary=True)['status'],'FAIL')
    def test_new_pair_matches_coordinates_not_row_order(self):
        x=self.record()
        for i,row in enumerate(x['eigenvalues_ha']):row[0]+=i
        y=copy.deepcopy(x);y['kpoints'].reverse();y['eigenvalues_ha'].reverse()
        out=CMP.compare_values(x,y,[1.],[1.],expected_kpoints=64,boundary=True)
        self.assertEqual(out['raw_level_max_abs_ha'],0.);self.assertEqual(out['status'],'PASS')

if __name__=='__main__':unittest.main(verbosity=2)
