"""Synthetic public-contract/number tests. No electronic-structure execution.

Historical native QE parsing is tested separately in one fixed clean snapshot;
no fabricated worker below is physical evidence.
"""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('extra_retry_replay', ROOT/'benchmarks/soc-extra-v1/replay_retry.py')
M = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(M)


class RetryReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old, cls.arithmetic = M.helpers(ROOT)
        cls.plan = json.loads((ROOT/M.PLAN).read_text())
        cls.case = json.loads((ROOT/cls.plan['case']).read_text())

    def fixture(self, accepted=False):
        plan = self.plan; E = M.START; old = self.old
        data = dict(schema_version=1, experiment=M.EXPERIMENT, execution_commit=E,
                    executed_source_sha256={'synthetic.py':'a'*64}, slots={}, checks={})
        for check, table in ((False,data['slots']),(True,data['checks'])):
            for action in M.ACTIONS:
                policy = M.policy_for(plan,action,E,check=check)
                table[action] = dict(status='NOT_RUN',run_id=policy['run_id'],policy=policy,policy_sha256=M.policy_hash(policy),
                    native_exit_code=None,recorder_exit_code=None,worker=None,reason='SYNTHETIC not run',complete_map_count=0)
        values=[-.5,-.5,-.1,-.1]+[-.0985]*4+[.2+i*.05 for i in range(8) for _ in range(2)]
        point=dict(eigenvalues_ha=values,coordinate_fractional=[0.,0.,0.],weight_spatial=1.,occupations=old.fd(values,0.),residuals_ha=[1e-11]*24,gram_frobenius=1e-13)
        metrics=old.gamma_metrics(point,0.,self.arithmetic)
        history=dict(K4=dict(D=copy.deepcopy(metrics),Q=copy.deepcopy(metrics)),K6=dict(Q=copy.deepcopy(metrics)),
            QE_native_energy=dict(internal_ha=-8.,free_ha=-8.),QE_warnings={'scope':'SYNTHETIC'},historical_sources={})
        if not accepted:return data,history
        for check,table in ((False,data['slots']),(True,data['checks'])):
            for action,row in table.items():
                p=row['policy'];w=dict(schema_version=1,phase='9A-extra',case='soc-extra-v1/K6',backend='soc-core',action=action,
                    run_id=row['run_id']+'-dftk',execution_commit=E,case_sha256=plan['case_sha256'],contract_sha256='f'*64,
                    executed_source_sha256=data['executed_source_sha256'],exit_code=0,execution_status='CHECK_ONLY_PASS' if check else 'PASS',
                    environment=dict(status='PASS'),resource_policy=p,resource_policy_sha256=M.policy_hash(p),resource_policy_status='WORKER_BOUNDARY_CHECKS_PASS',
                    parallelism=dict(julia=1,blas=1,fft=1,mpi=1),runtime_closed=True,runtime_dispatch_status='PASS',
                    runtime=dict(backend='soc-core',max_rhs=30,counters=dict(fr_mul_calls=1,component_mul_calls=1,full_mul_calls=1)),
                    runtime_after_close=dict(closed=True,workspace_released=True,owned_source_entries=0),
                    input=dict(sha256=plan['upf_sha256'],nlcc_present=True))
                if check:w.update(check_only=True,context_constructed=False,formal_slot_reserved=False,numerical_execution_status='NOT_RUN')
                resource=dict(resource_policy=p,resource_policy_sha256=M.policy_hash(p),status='PASS',resource_policy_status='PASS',native_exit_code=0,
                    owned_process_cleanup_status='PASS',peak_aggregate_rss_bytes=2*1024**3,authenticated_worker_highwater_bytes=3*1024**3,
                    screen_peak_bytes=3*1024**3,first_stop_request=None,safe_stop_requested=False,nonempty_samples=5)
                row.update(status='PASS',native_exit_code=0,recorder_exit_code=0,worker=w,resource=resource,raw_recorder_sha256='b'*64,raw_worker_sha256='c'*64)
        scf=data['slots']['X-K6-SCF'];s=scf['worker'];scf['complete_map_count']=3
        s.update(checkpoint_sha256='d'*64,grid=dict(rows=[dict(coordinate_fractional=p['coordinate_fractional']) for p in self.case['kpoints']],
            basis=dict(n_electrons=8,fft_grid=[48]*3,ecut_ha=30,kpoints=copy.deepcopy(self.case['kpoints']))),
            final=dict(closure_status='PASS',map_count=3,mu_ha=0.,n_out_sha256='e'*64,
                eigenvalues_ha=[[-1.]*8+[1.]*16 for _ in range(216)],occupations=[[1.]*8+[0.]*16 for _ in range(216)],
                unmixed_residual_l2=1e-10,diagnostics=dict(internal_energy_ha=-8.,free_energy_ha=-8.,entropy_energy_ha=0.,
                    energy_terms_ha=dict(Kinetic=1.,AtomicLocal=-3.,AtomicNonlocalFR=.4,Hartree=.5,Xc=-2.,Ewald=-5.,PspCorrection=.1))))
        for table in (data['slots'],data['checks']):
            g=table['X-K6-GAMMA']['worker'];g.update(source_scf_run_id=s['run_id'],parent_result_sha256=scf['raw_worker_sha256'],
                parent_checkpoint_sha256=s['checkpoint_sha256'],density_source_sha256=s['final']['n_out_sha256'],time_reversal=dict(status='PASS'))
        data['slots']['X-K6-GAMMA']['worker']['spectrum']=dict(execution_status='PASS',process_exit_code=0,physical_operator='full_soc',
            occupations_use='DIAGNOSTIC_ONLY_NOT_DENSITY_FEEDBACK',fermi_energy_ha=0.,temperature_ha=.001,kpoints=[point])
        return data,history

    def evaluate(self,data,history):return M.evaluate(data,self.plan,history,self.old,self.arithmetic,self.case)

    def test_unrun_and_failed_pair_remain_unassessed(self):
        data,h=self.fixture();out=self.evaluate(data,h)
        self.assertEqual(out['K6']['comparison_status'],'NOT_ASSESSED');self.assertIsNone(out['K6']['D'])
        row=data['slots']['X-K6-SCF'];row.update(status='FAIL',native_exit_code=1,recorder_exit_code=1,raw_recorder_sha256='b'*64,reason='SYNTHETIC stopped')
        data['slots']['X-K6-GAMMA']['status']='BLOCKED_PARENT'
        self.assertEqual(self.evaluate(data,h)['replay_status'],'PASS')
        self.assertEqual(row['native_exit_code'],1)

    def test_parent10_child8_success_and_fixed_shift(self):
        data,h=self.fixture(True);out=self.evaluate(data,h)
        self.assertEqual(out['K6']['comparison_status'],'PASS')
        self.assertEqual(out['K6']['comparison']['delta_D_minus_Q_mev'],0.)
        self.assertFalse(out['K6']['D_energy']['native_total_energy_corrected'])
        self.assertEqual(out['K6']['D']['manifold_assignment_status'],'MANIFOLD_ASSIGNMENT_REVIEW_REQUIRED')
        g=data['slots']['X-K6-GAMMA']['worker']['spectrum'];point=g['kpoints'][0]
        point['eigenvalues_ha']=[v-.1 for v in point['eigenvalues_ha']];point['occupations']=self.old.fd(point['eigenvalues_ha'],0.)
        shifted=self.evaluate(data,h)['K6']['comparison']
        self.assertAlmostEqual(shifted['delta_D_minus_Q_mev'],0.,places=10)
        self.assertAlmostEqual(shifted['raw_summary_ha']['max_abs'],.1)
        self.assertLess(shifted['global_referenced_summary_ha']['max_abs'],1e-14)

    def test_declared_screen_and_response_not_fit(self):
        data,h=self.fixture(True);point=data['slots']['X-K6-GAMMA']['worker']['spectrum']['kpoints'][0]
        for i in range(4,8):point['eigenvalues_ha'][i]+=.001
        point['occupations']=self.old.fd(point['eigenvalues_ha'],0.)
        out=self.evaluate(data,h);c=out['K6']['comparison']
        self.assertEqual(out['K6']['comparison_status'],'REVIEW_REQUIRED')
        self.assertGreater(c['delta_D_minus_Q_mev'],.1)
        self.assertAlmostEqual(c['response_difference_mev'],c['D_K4_to_K6_mev']-c['Q_K4_to_K6_mev'])

    def test_source_exit_policy_and_parent_corruption_rejected(self):
        changes=[lambda d:d['slots']['X-K6-SCF'].update(native_exit_code=1),
            lambda d:d['slots']['X-K6-SCF']['policy'].update(limit_bytes=8*1024**3),
            lambda d:d['slots']['X-K6-GAMMA']['policy'].update(limit_bytes=10*1024**3),
            lambda d:d['slots']['X-K6-SCF']['policy'].update(remaining_growth_bytes=2021087414),
            lambda d:d['slots']['X-K6-SCF']['worker'].update(execution_commit='f'*40),
            lambda d:d['slots']['X-K6-SCF']['worker'].update(executed_source_sha256={}),
            lambda d:d['checks']['X-K6-GAMMA']['worker'].update(parent_result_sha256='f'*64),
            lambda d:d['slots']['X-K6-GAMMA']['worker'].update(parent_checkpoint_sha256='f'*64),
            lambda d:d['checks']['X-K6-GAMMA']['worker'].update(context_constructed=True),
            lambda d:d['checks']['X-K6-SCF']['worker'].update(formal_slot_reserved=True),
            lambda d:d['slots']['X-K6-SCF']['resource'].update(screen_peak_bytes=5*1024**3),
            lambda d:d['slots']['X-K6-SCF']['resource'].update(resource_policy_status='STOP_AT_SAFE_BOUNDARY'),
            lambda d:d['slots']['X-K6-SCF']['worker']['final'].update(closure_status='FAIL'),
            lambda d:d['slots']['X-K6-SCF'].update(complete_map_count=4),
            lambda d:d['slots']['X-K6-SCF']['worker']['final']['occupations'][0].pop(),
            lambda d:d['slots']['X-K6-SCF']['worker']['final']['eigenvalues_ha'].pop(),
            lambda d:d['slots']['X-K6-SCF']['worker']['final']['diagnostics'].update(free_energy_ha=-7.)]
        for change in changes:
            with self.subTest(change=change):
                data,h=self.fixture(True);change(data)
                with self.assertRaises((ValueError,KeyError,TypeError)):self.evaluate(data,h)

    def test_latched_first_stop_not_cleaned_into_pass(self):
        data,h=self.fixture(True);row=data['slots']['X-K6-SCF'];p=row['policy'];r=row['resource']
        peak=p['limit_bytes']-p['remaining_growth_bytes'];decision=dict(status='STOP_AT_SAFE_BOUNDARY',reason='SYNTHETIC fixed-growth equality',
            current_group_rss_bytes=1024,peak_group_rss_bytes=peak,worker_highwater_bytes=1024,screen_peak_bytes=peak,
            remaining_growth_bytes=p['remaining_growth_bytes'],limit_bytes=p['limit_bytes'],warning_bytes=p['warning_bytes'])
        stop={k:p[k] for k in ('run_id','action','case_sha256','execution_commit','policy_id')}
        stop.update(resource_policy_sha256=row['policy_sha256'],resource_decision=decision)
        r.update(first_stop_request=stop,resource_policy_status='STOP_AT_SAFE_BOUNDARY')
        with self.assertRaises(ValueError):self.evaluate(data,h)
        row.update(status='FAIL',native_exit_code=1,recorder_exit_code=1,reason='SYNTHETIC safe stop')
        row['worker'].update(exit_code=1,execution_status='FAIL');r['native_exit_code']=1
        for table in (data['slots'],data['checks']):
            g=table['X-K6-GAMMA'];g.update(status='BLOCKED_PARENT',worker=None,native_exit_code=None,recorder_exit_code=None,reason='SYNTHETIC parent failed')
        self.assertEqual(self.evaluate(data,h)['K6']['comparison_status'],'NOT_ASSESSED')
        r['resource_policy_status']='PASS'
        with self.assertRaises(ValueError):self.evaluate(data,h)

    def test_default0_strict1_malformed2(self):
        data,h=self.fixture();result=self.evaluate(data,h)
        with patch.object(M,'replay',return_value=result),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(M.main([]),0);self.assertEqual(M.main(['--require-k6']),1)
        with patch.object(M,'replay',side_effect=ValueError('synthetic corruption')),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(M.main([]),2)

    def test_actual_plan_policy_matches_control(self):
        spec=importlib.util.spec_from_file_location('retry_policy_reference',ROOT/'benchmarks/soc-extra-v1/retry.py')
        retry=importlib.util.module_from_spec(spec);spec.loader.exec_module(retry)
        formal,checks=retry.policies(ROOT,M.START)
        for action in M.ACTIONS:
            self.assertEqual(M.policy_for(self.plan,action,M.START),formal[action])
            self.assertEqual(M.policy_for(self.plan,action,M.START,check=True),checks[action])



class RetryArtifactTests(unittest.TestCase):
    def setUp(self):
        self.fixture=RetryReplayTests('test_unrun_and_failed_pair_remain_unassessed')
        RetryReplayTests.setUpClass()

    def test_failure_trace_complete_count_excludes_failure_row(self):
        data,_=self.fixture.fixture();row=data['slots']['X-K6-SCF'];row['complete_map_count']=1
        trace=b'{"map_index":1,"status":"CONTINUE","diagnostics":{}}\n{"map_index":2,"status":"FAIL","diagnostics":{}}\n'
        entry=dict(action='X-K6-SCF',kind='compact_trace')
        with patch.object(self.fixture.old,'artifact',return_value=trace):
            self.assertEqual(M.audit_artifacts(ROOT,[entry],data,self.fixture.old)['status'],'PASS')
            row['complete_map_count']=2
            with self.assertRaises(ValueError):M.audit_artifacts(ROOT,[entry],data,self.fixture.old)

    def test_stop_artifact_cannot_be_hidden_by_data(self):
        data,_=self.fixture.fixture();entry=dict(action='X-K6-SCF',kind='resource_stop',raw_sha256='a'*64)
        with patch.object(self.fixture.old,'artifact',return_value=b'{"reason":"synthetic stop"}'):
            with self.assertRaises(ValueError):M.audit_artifacts(ROOT,[entry],data,self.fixture.old)

    def test_success_needs_native_and_highwater_artifacts(self):
        data,_=self.fixture.fixture(True)
        with self.assertRaises(ValueError):M.audit_artifacts(ROOT,[],data,self.fixture.old)


if __name__=='__main__':unittest.main()
