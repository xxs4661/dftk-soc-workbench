"""Synthetic protocol/arithmetic regressions; no SCF, eigensolve or physical evidence.

Only test_authenticated_history opens existing published QE native output and
checks its parser closure. Fabricated workers below test the public contract.
"""
import contextlib
import copy
import gzip
import hashlib
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'benchmarks/soc-extra-v1/plan.json').is_file())
FILE=ROOT/'benchmarks/soc-extra-v1/replay.py'
if not FILE.exists(): FILE=ROOT/'.work/phase9a-extra/replay.py.draft'
SPEC=importlib.util.spec_from_loader('extra_replay_tested',importlib.machinery.SourceFileLoader('extra_replay_tested',str(FILE)))
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)


def empty():
    return dict(schema_version=1,experiment='soc-extra-v1',execution_commit=M.BASE,
        original_9A_status='COMPLETED_UNCHANGED',core_changed=False,b0_regression_required=False,
        slots={k:dict(status='NOT_RUN',run_id=None,native_exit_code=None,
                     recorder_exit_code=None,reason='Synthetic unrun slot',worker=None) for k in M.SLOTS})


def measurement(scale=1):
    def sample(i): return dict(index=i,status='PASS',time_seconds=scale*i,allocated_bytes=100*i,
        gc_seconds=.01*i,compile_seconds=0.,recompile_seconds=0.)
    return dict(status='PASS',warmup_count=1,requested_samples=5,completed_samples=5,
        warmup=sample(0),samples=[sample(i) for i in range(1,6)],workload=dict(first_k_only=True,physical_states=24))


def performance(candidate=False):
    records=[]
    for mode in (('baseline','candidate') if candidate else ('baseline',)):
        for case in ('B0','K4'):
            records.append(dict(case=case,mode=mode,execution_commit=M.BASE,base_commit=M.BASE,
                raw_worker_sha256='a'*64,input=dict(case=case,source='b'*64),
                environment=dict(status='PASS',julia_version='1.12.7',manifest_sha256='c'*64),
                parallelism=dict(julia=1,blas=1,fft=1,mpi=1),
                canonical_inputs=dict(sha256='d'*64),canonical_operators=dict(sha256='e'*64),
                measurements={op:measurement(.8 if mode=='candidate' else 1.) for op in M.OPS}))
    equivalence=dict(status='NOT_ATTEMPTED',cases={})
    if candidate:
        equivalence=dict(status='PASS',cases={label:dict(rows=[dict(label='synthetic energy',kind='scalar',
            reference=1.,candidate=1.,difference=0.,limit=1e-10,status='PASS'),
            dict(label='synthetic array',kind='array',shape=[2],reference_norm=3.,candidate_norm=3.,
                 absolute_L2=1e-13,relative=1e-13/3,limit=1e-12,status='PASS')]) for label in ('B0','K4')})
    return dict(schema_version=1,records=records,selection=dict(adopted_core='candidate' if candidate else 'baseline',
        reason='Synthetic contract fixture'),equivalence=equivalence)


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.history=M.load_history(ROOT)

    def evaluate(self,data):
        with patch.object(M,'load_history',return_value=self.history): return M.evaluate(data,ROOT)

    def pair(self):
        data=empty();case=M.read(ROOT/'benchmarks/soc-extra-v1/K6.json');nk=len(case['kpoints'])
        def worker(action):
            return dict(schema_version=1,exit_code=0,phase='9A-extra',backend='soc-core',action=action,
                run_id='synthetic-'+action,execution_status='PASS',execution_commit=M.BASE,
                environment=dict(status='PASS'),parallelism=dict(julia=1,blas=1,fft=1,mpi=1),
                runtime_dispatch_status='PASS',runtime_closed=True,
                runtime=dict(backend='soc-core',max_rhs=30,counters=dict(fr_mul_calls=1,component_mul_calls=1,full_mul_calls=1)),
                runtime_after_close=dict(closed=True,owned_source_entries=0,workspace_released=True),
                input=dict(sha256=M.UPF,nlcc_present=True))
        s=worker('X-K6-SCF');s['case_sha256']=M.digest((ROOT/'benchmarks/soc-extra-v1/K6.json').read_bytes())
        s['checkpoint_sha256']='a'*64
        s['grid']=dict(rows=[dict(coordinate_fractional=p['coordinate_fractional']) for p in case['kpoints']],
            basis=dict(n_electrons=8,fft_grid=[48]*3,ecut_ha=30,kpoints=copy.deepcopy(case['kpoints'])))
        s['final']=dict(closure_status='PASS',map_count=3,mu_ha=0.,n_out_sha256='b'*64,
            eigenvalues_ha=[[-1.]*8+[1.]*16 for _ in range(nk)],occupations=[[1.]*8+[0.]*16 for _ in range(nk)],
            unmixed_residual_l2=1e-10,diagnostics=dict(internal_energy_ha=-8.,free_energy_ha=-8.,entropy_energy_ha=0.,
                energy_terms_ha=dict(Kinetic=1.,AtomicLocal=-3.,AtomicNonlocalFR=.4,Hartree=.5,Xc=-2.,Ewald=-5.,PspCorrection=.1)))
        g=worker('X-K6-GAMMA');g.update(source_scf_run_id=s['run_id'],parent_checkpoint_sha256=s['checkpoint_sha256'],density_source_sha256=s['final']['n_out_sha256'])
        # Published values copied in-memory solely to form a synthetic shift-invariance fixture.
        values=[x-.1 for x in self.history['Q_K6_GAMMA']['kpoints'][0]['eigenvalues_ha']]
        g['time_reversal']=dict(status='PASS')
        g['spectrum']=dict(execution_status='PASS',process_exit_code=0,physical_operator='full_soc',occupations_use='DIAGNOSTIC_ONLY_NOT_DENSITY_FEEDBACK',
            temperature_ha=.001,fermi_energy_ha=0.,kpoints=[dict(coordinate_fractional=[0.,0.,0.],weight_spatial=1.,
                eigenvalues_ha=values,occupations=M.fd(values,0.),residuals_ha=[1e-11]*24,gram_frobenius=1e-13)])
        for w in (s,g):
            data['slots'][w['action']]=dict(status='PASS',run_id=w['run_id'],native_exit_code=0,recorder_exit_code=0,worker=w,
                resource=dict(status='PASS',native_exit_code=0,owned_process_cleanup_status='PASS',
                              peak_aggregate_rss_bytes=2*1024**3,nonempty_samples=3))
        return data

    def test_authenticated_history_reparses_native_files(self):
        h=self.history
        self.assertEqual(h['native_slots_reparsed'],2)
        self.assertEqual(len(h['Q_K6_SCF']['kpoints']),216)
        self.assertEqual(len(h['Q_K6_GAMMA']['kpoints'][0]['eigenvalues_ha']),24)
        self.assertEqual(h['Q_K6_SCF']['warning_evidence']['ieee_localization_status'],'NOT_LOCALIZED')
        self.assertEqual(len(h['Q_K6_SCF']['warning_evidence']['c_bands_lines']),157)

    def test_missing_k6_stays_unassessed_and_preserves_history(self):
        out=self.evaluate(empty())
        self.assertIsNone(out['K6']['D']);self.assertIsNone(out['K6']['comparison'])
        self.assertEqual(out['K6']['comparison_status'],'NOT_ASSESSED')
        self.assertEqual(out['original_9A_status'],'COMPLETED_UNCHANGED')
        self.assertEqual(out['K6']['Q']['occupation']['status'],'REVIEW_REQUIRED')

    def test_synthetic_constant_shift_does_not_change_splitting(self):
        data=self.pair();out=self.evaluate(data);c=out['K6']['comparison']
        self.assertLess(abs(c['delta_D_minus_Q_ev']),1e-13)
        self.assertLess(c['global_referenced_summary_ha']['max_abs'],1e-14)
        self.assertAlmostEqual(c['raw_summary_ha']['max_abs'],.1)
        self.assertEqual(c['historical_K4_current_K6_scope'],'HISTORICAL_K4_LEGACY_TO_CURRENT_SOC_CORE_MIXED_VERSION_RESPONSE')
        self.assertAlmostEqual(c['D_K4_to_K6_ev']-c['Q_K4_to_K6_ev'],c['response_difference_ev'])
        self.assertEqual(out['K6']['D']['manifold_assignment_status'],'MANIFOLD_ASSIGNMENT_REVIEW_REQUIRED')
        self.assertFalse(out['K6']['D_energy']['native_total_energy_corrected'])
        self.assertEqual(out['K6']['D_energy']['internal_ha'],-8.)

    def test_fixed_state_window_and_screen_are_not_fit(self):
        data=self.pair();p=data['slots']['X-K6-GAMMA']['worker']['spectrum']['kpoints'][0]
        for i in range(4,8): p['eigenvalues_ha'][i]+=.001
        p['occupations']=M.fd(p['eigenvalues_ha'],0.)
        out=self.evaluate(data)
        self.assertEqual(out['K6']['comparison_status'],'REVIEW_REQUIRED')
        self.assertGreater(out['K6']['comparison']['delta_D_minus_Q_mev'],.1)

    def test_worker_failure_keeps_nonzero_and_no_comparison(self):
        data=empty();data['slots']['X-K6-SCF'].update(status='FAIL',native_exit_code=9,recorder_exit_code=9,reason='Synthetic failure')
        data['slots']['X-K6-GAMMA']['status']='BLOCKED_PARENT'
        out=self.evaluate(data);self.assertIsNone(out['K6']['D'])
        self.assertEqual(data['slots']['X-K6-SCF']['native_exit_code'],9)

    def test_protocol_contradictions_rejected(self):
        mutations=[lambda d:d['slots']['X-K6-SCF'].update(native_exit_code=1),
            lambda d:d['slots']['X-K6-SCF']['worker'].update(exit_code=9),
            lambda d:d['slots']['X-K6-SCF']['resource'].update(nonempty_samples=0),
            lambda d:d['slots']['X-K6-SCF']['worker']['environment'].update(status='FAIL'),
            lambda d:d['slots']['X-K6-SCF']['worker']['runtime']['counters'].update(fr_mul_calls=0),
            lambda d:d['slots']['X-K6-SCF']['worker']['runtime_after_close'].update(workspace_released=False),
            lambda d:d['slots']['X-K6-GAMMA']['worker'].update(density_source_sha256='f'*64),
            lambda d:d['slots']['X-K6-SCF'].update(status='PILOT_COMPLETED_NOT_SCF_CONVERGED'),
            lambda d:d.update(schema_version=True),
            lambda d:d['slots']['X-K6-SCF']['worker']['input'].update(sha256='d'*64)]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                data=self.pair();mutation(data)
                with self.assertRaises((ValueError,KeyError,TypeError)):self.evaluate(data)

    def test_unrun_exit_zero_or_stale_worker_rejected(self):
        for key,value in [('native_exit_code',0),('recorder_exit_code',0),('worker',{'execution_status':'PASS'})]:
            data=empty();data['slots']['X-K6-SCF'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.evaluate(data)

    def test_band_count_electron_weight_energy_parent_mu_failures(self):
        changes=[lambda s,g:s['final']['occupations'][0].pop(),
            lambda s,g:s['grid']['basis']['kpoints'][0].update(weight_spatial=.1),
            lambda s,g:s['final']['diagnostics'].update(free_energy_ha=-7.),
            lambda s,g:s['final']['diagnostics']['energy_terms_ha'].update(PspCorrection=.2),
            lambda s,g:s['final']['diagnostics'].update(entropy_energy_ha=float('nan')),
            lambda s,g:g['spectrum'].update(fermi_energy_ha=.1),
            lambda s,g:g['spectrum']['kpoints'][0]['residuals_ha'].__setitem__(0,1e-6),
            lambda s,g:s['final'].update(closure_status='FAIL')]
        for change in changes:
            data=self.pair();change(data['slots']['X-K6-SCF']['worker'],data['slots']['X-K6-GAMMA']['worker'])
            with self.subTest(change=change),self.assertRaises((ValueError,KeyError,TypeError)):self.evaluate(data)

    def test_gamma_occupation_threshold_unchanged(self):
        p=copy.deepcopy(self.history['Q_K6_GAMMA']['kpoints'][0]);mu=self.history['Q_K6_SCF']['fermi_energy_ha']
        out=M.gamma_metrics(p,mu,self.history['arithmetic'])
        self.assertEqual(out['occupation']['threshold'],.99999999)
        self.assertEqual(out['occupation']['status'],'REVIEW_REQUIRED')
        p['occupations']=[1.]*24
        with self.assertRaises(ValueError):M.gamma_metrics(p,mu,self.history['arithmetic'])

    def test_b0_public_arithmetic_and_private_density_scope(self):
        old=self.history['B0']['OPT-B0-SCF'];oldg=self.history['B0']['OPT-B0-GAMMA']['spectrum']['kpoints'][0]
        gamma=M.gamma_metrics(oldg,old['final']['mu_ha'],self.history['arithmetic'])
        diag=old['final']['diagnostics'];energy=dict(internal_ha=diag['internal_energy_ha'],free_ha=diag['free_energy_ha'])
        density=dict(reference_source_sha256=old['checkpoint_sha256'],reference_n_out_sha256=old['final']['n_out_sha256'],
            candidate_n_out_sha256=old['final']['n_out_sha256'],reference_norm=10.,candidate_norm=10.,absolute_L2=0.,
            relative=0.,limit=1e-8,status='PASS',evidence_level='RUNNER_REPORTED_PRIVATE_ARRAY_COMPARISON')
        reported=dict(execution_commit=old['execution_commit'],status='PASS',metrics=dict(n_out=density))
        out=M.b0_comparison(old,gamma,energy,self.history,reported)
        self.assertEqual(out['status'],'PASS');self.assertEqual(out['arithmetic']['Gamma']['max_abs_ha'],0.)
        self.assertEqual(M.b0_comparison(old,gamma,energy,self.history,None)['status'],'NOT_ASSESSED')
        reported['metrics']['n_out']['relative']=1.
        with self.assertRaises(ValueError):M.b0_comparison(old,gamma,energy,self.history,reported)

    def test_required_b0_cannot_be_replaced_by_k6_or_history(self):
        data=self.pair();data['b0_regression_required']=True
        with self.assertRaisesRegex(ValueError,'mandatory new B0'):self.evaluate(data)

    def test_all_five_performance_samples_recomputed(self):
        p=performance();p['records'][0]['measurements']['FR_1']['samples'][-1]['time_seconds']=1000.
        out=M.performance_statistics(p)
        self.assertEqual(out['records']['baseline/B0']['FR_1']['statistics']['time_seconds'],dict(median=3.,min=1.,max=1000.))
        self.assertEqual(out['adopted_core'],'baseline');self.assertEqual(out['equivalence']['status'],'NOT_ATTEMPTED')

    def test_candidate_ratios_and_norm_equivalence(self):
        out=M.performance_statistics(performance(True))
        self.assertAlmostEqual(out['ratios']['B0']['pipeline_with_validation']['time_ratio'],.8)
        self.assertEqual(out['equivalence']['status'],'PASS')
        self.assertEqual(out['performance_screen'],'ELIGIBLE_FOR_REVIEW')

    def test_performance_bad_sample_input_and_unjustified_candidate_rejected(self):
        changes=[lambda p:p['records'][0]['measurements']['FR_1']['samples'].pop(),
            lambda p:p['records'][0]['measurements']['FR_1']['samples'][0].update(index=2),
            lambda p:p['records'][2]['input'].update(source='f'*64),
            lambda p:p['records'][2]['environment'].update(manifest_sha256='f'*64),
            lambda p:p['equivalence']['cases']['B0']['rows'][1].update(relative=1.),
            lambda p:p['equivalence']['cases']['K4']['rows'][0].update(candidate=2.,difference=1.),
            lambda p:p['records'][2]['measurements']['pipeline_with_validation']['samples'][-1].update(allocated_bytes=-1.)]
        for change in changes:
            p=performance(True);change(p)
            with self.subTest(change=change),self.assertRaises(ValueError):M.performance_statistics(p)

    def test_artifact_bytes_hash_compression_and_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);raw=b'{"synthetic":true}\n';encoded=gzip.compress(raw,mtime=0);(root/'data.gz').write_bytes(encoded)
            spec=dict(path='data.gz',sha256=M.digest(encoded),bytes=len(encoded),public_sha256=M.digest(raw),public_bytes=len(raw),raw_sha256='f'*64)
            self.assertEqual(M.artifact(root,spec),raw)
            for field,value in [('sha256','a'*64),('public_sha256','a'*64),('bytes',0),('path','../data.gz')]:
                bad=dict(spec);bad[field]=value
                with self.subTest(field=field),self.assertRaises(ValueError):M.artifact(root,bad)

    def test_native_logs_and_map_trace_cannot_be_omitted_or_stale(self):
        data=self.pair();slots=data['slots']
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);artifacts=[]
            def add(action,kind,payload):
                name=action+'-'+kind+'.gz';raw=gzip.compress(payload,mtime=0);(root/name).write_bytes(raw)
                spec=dict(action=action,kind=kind,path=name,sha256=M.digest(raw),bytes=len(raw),raw_sha256=M.digest(payload),
                    public_sha256=M.digest(payload),public_bytes=len(payload));artifacts.append(spec);return spec
            for action in ('X-K6-SCF','X-K6-GAMMA'):
                for kind in ('native_stdout','native_stderr'):add(action,kind,b'Synthetic protocol log\n')
            diag=slots['X-K6-SCF']['worker']['final']['diagnostics']
            trace=[dict(map_index=i,map_role='closure' if i==3 else 'scf',status='PASS' if i==3 else 'CONTINUE',diagnostics=diag) for i in range(1,4)]
            add('X-K6-SCF','compact_trace',''.join(json.dumps(r)+'\n' for r in trace).encode())
            self.assertEqual(M.audit_artifacts(root,artifacts,slots)['complete_accepted_map_traces'],1)
            with self.assertRaises(ValueError):M.audit_artifacts(root,artifacts[:-1],slots)
            with self.assertRaises(ValueError):M.audit_artifacts(root,artifacts[1:],slots)
            slots['X-K6-SCF']['worker']['final']['map_count']=4
            with self.assertRaises(ValueError):M.audit_artifacts(root,artifacts,slots)

    def test_cli_default_strict_and_malformed_statuses(self):
        for strict,comparison,code in [(False,'NOT_ASSESSED',0),(True,'NOT_ASSESSED',1),(True,'REVIEW_REQUIRED',1),(True,'PASS',0)]:
            result=dict(K6=dict(comparison_status=comparison),replay_status='PASS')
            with patch.object(M,'replay',return_value=result),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(M.main(['--root',str(ROOT)]+(['--require-k6'] if strict else [])),code)
        with patch.object(M,'replay',side_effect=ValueError('synthetic malformed')),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(M.main(['--root',str(ROOT)]),2)
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(SystemExit) as result:M.main(['--help'])
        self.assertEqual(result.exception.code,0)


if __name__=='__main__': unittest.main()
