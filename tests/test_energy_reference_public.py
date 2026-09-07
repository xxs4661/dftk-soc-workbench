"""Recorder/public-table contracts; synthetic faults never execute Julia or QE."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from run_energy_reference_audit import validate_worker_receipt
from compare_energy_reference import compare_saved
from check_density_hartree import equivalent
from check_energy_reference import check_frozen


class WorkerReceipt(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        (self.root/'common').mkdir()
        # Not a Julia Serialization object: only tests the recorder's byte hash.
        self.arrays=b'synthetic opaque bytes; not physical arrays'
        (self.root/'common/arrays.bin').write_bytes(self.arrays)
        self.record={'run_id':'synthetic-current', 'plan_sha256':'1'*64,
            'execution_source_sha256':{'scripts/evaluate_common_energy_terms.jl':'2'*64}}
        self.receipt={'execution_status':'PASS','exit_code':0,
            'run_id':'synthetic-current','plan_sha256':'1'*64,'executed_script_sha256':'2'*64,
            'local_arrays':{'path':'arrays.bin','sha256':hashlib.sha256(self.arrays).hexdigest()}}

    def tearDown(self):
        self.temp.cleanup()

    def test_complete_current_receipt(self):
        validate_worker_receipt(self.receipt,self.record,self.root)

    def test_wrong_current_run_or_plan_rejected(self):
        for key in ('run_id','plan_sha256'):
            with self.subTest(field=key):
                altered=copy.deepcopy(self.receipt);altered[key]='stale'
                with self.assertRaisesRegex(ValueError,'current identity'):
                    validate_worker_receipt(altered,self.record,self.root)

    def test_wrong_executed_source_rejected(self):
        altered=copy.deepcopy(self.receipt);altered['executed_script_sha256']='3'*64
        with self.assertRaisesRegex(ValueError,'execution source'):
            validate_worker_receipt(altered,self.record,self.root)

    def test_failed_or_incomplete_worker_rejected(self):
        for change in [{'execution_status':'FAIL'},{'execution_status':'INCOMPLETE'},{'exit_code':1}]:
            with self.subTest(change=change):
                altered={**self.receipt,**change}
                with self.assertRaises(ValueError): validate_worker_receipt(altered,self.record,self.root)

    def test_null_or_wrong_type_worker_rejected(self):
        for value in (None,[],True,'PASS'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                validate_worker_receipt(value,self.record,self.root)

    def test_missing_array_receipt_rejected(self):
        for value in (None,[],{},'arrays.bin'):
            with self.subTest(value=value):
                altered={**self.receipt,'local_arrays':value}
                with self.assertRaises(ValueError): validate_worker_receipt(altered,self.record,self.root)

    def test_other_array_path_cannot_replace_current_file(self):
        altered=copy.deepcopy(self.receipt);altered['local_arrays']['path']='../previous/arrays.bin'
        with self.assertRaises(ValueError): validate_worker_receipt(altered,self.record,self.root)

    def test_changed_array_bytes_rejected(self):
        (self.root/'common/arrays.bin').write_bytes(b'changed synthetic bytes')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):
            validate_worker_receipt(self.receipt,self.record,self.root)

    def test_missing_array_file_rejected(self):
        (self.root/'common/arrays.bin').unlink()
        with self.assertRaises(FileNotFoundError): validate_worker_receipt(self.receipt,self.record,self.root)


class PublishedTableContracts(unittest.TestCase):
    """Read real saved tables; mutate only owned in-memory synthetic fault copies.

    These assertions replay scalar arithmetic and validation, not XC or a
    radial integral. The untouched public files remain the sole authority.
    """
    @classmethod
    def setUpClass(cls):
        result=ROOT/'results/mg-soc-energy-reference'
        cls.paths=[result/(name+'.json') for name in ('ledger','common-terms','local-g0','comparison')]
        cls.hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.paths}
        cls.original=[json.loads(p.read_text()) for p in cls.paths]
        cls.plan=json.loads((ROOT/'benchmarks/mg-soc-energy-reference-v1/plan.json').read_text())

    @classmethod
    def tearDownClass(cls):
        for path,expected in cls.hashes.items():
            if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise AssertionError('Public source mutated by table tests: '+str(path))

    def setUp(self):
        self.ledger,self.common,self.radial,self.expected=copy.deepcopy(self.original)

    def compare(self):
        return compare_saved(self.ledger,self.common,self.radial,self.plan)

    def reject(self):
        with self.assertRaises((ValueError,KeyError,TypeError)):
            self.compare()

    def test_published_tables_replay_saved_arithmetic_only(self):
        result=self.compare()
        equivalent(result,self.expected)
        self.assertEqual(result['same_source_common_terms_status'],'PASS')
        self.assertEqual(result['new_scf_status'],'NOT_RUN')
        self.assertEqual(result['new_eigensolve_status'],'NOT_RUN')
        self.assertEqual(result['new_qe_numerical_status'],'NOT_RUN')
        self.assertEqual(result['numerical_agreement_status'],'REVIEW_REQUIRED')
        self.assertEqual(result['qe_separate_kinetic_nonlocal_status'],'NOT_AVAILABLE')

    def test_deleted_required_check_groups_cannot_vacuously_pass(self):
        for group in ('reconstruction','original_sources','same_source','responses','evaluations'):
            with self.subTest(group=group):
                self.common=copy.deepcopy(self.original[1]);self.common[group]={};self.reject()

    def test_null_check_group_cannot_pass(self):
        for group in ('reconstruction','original_sources','same_source','responses','evaluations'):
            with self.subTest(group=group):
                self.common=copy.deepcopy(self.original[1]);self.common[group]=None;self.reject()

    def test_missing_one_source_or_evaluation_is_not_complete(self):
        for group in ('reconstruction','original_sources','same_source','responses','evaluations'):
            with self.subTest(group=group):
                self.common=copy.deepcopy(self.original[1]);self.common[group].pop(next(iter(self.common[group])));self.reject()

    def test_empty_or_duplicated_same_source_rows_rejected(self):
        rows=self.common['same_source']['A_original_n_out']['rows']
        for bad in ([],[rows[0]]*5,None):
            with self.subTest(rows=bad):
                self.common=copy.deepcopy(self.original[1]);self.common['same_source']['A_original_n_out']['rows']=bad;self.reject()

    def test_same_source_actual_rows_cannot_detach_from_evaluation(self):
        # A common local-energy shift cancels every density response. Historical
        # same-source rows must nevertheless prevent its silent introduction.
        for ev in self.common['evaluations'].values():
            ev['atomic_local_ha']+=1e-5;ev['local_integral_ha']+=1e-5
        with self.assertRaisesRegex(ValueError,'detached'):
            self.compare()

    def test_same_source_historical_rows_cannot_detach_from_ledger(self):
        row=self.common['same_source']['A_original_n_out']['rows'][0]
        row['actual']+=1e-6;row['historical']+=1e-6
        with self.assertRaisesRegex(ValueError,'detached'):
            self.compare()

    def test_empty_or_duplicate_directional_checks_rejected(self):
        original=self.common['reconstruction']['Q']['directional_checks']
        for bad in ([],[original[0]]*17):
            with self.subTest(length=len(bad)):
                self.common=copy.deepcopy(self.original[1]);self.common['reconstruction']['Q']['directional_checks']=bad;self.reject()

    def test_source_failure_and_uncompleted_evaluations_rejected(self):
        for key,value in [('source_binding_status','FAIL'),('source_unchanged_status','FAIL'),
                          ('execution_status','FAIL'),('exit_code',1),('xc_calls_completed',4),
                          ('environment_recheck_status','FAIL')]:
            with self.subTest(field=key):
                self.common=copy.deepcopy(self.original[1]);self.common[key]=value;self.reject()

    def test_source_status_cannot_hide_wrong_pseudopotential(self):
        self.common['constants']['source_sha256']='0'*64;self.reject()

    def test_new_scientific_execution_cannot_be_relabelled_not_run(self):
        for key in ('new_scf_status','new_eigensolve_status','new_qe_numerical_status'):
            with self.subTest(field=key):
                self.common=copy.deepcopy(self.original[1]);self.common[key]='PASS';self.reject()

    def test_failed_ledger_cannot_publish_success(self):
        for key in ('source_binding_status','historical_energy_ledger_status'):
            with self.subTest(field=key):
                self.ledger=copy.deepcopy(self.original[0]);self.ledger[key]='FAIL';self.reject()

    def test_clipping_or_renormalization_cannot_validate_density(self):
        for key in ('clipping_applied','normalization_applied'):
            with self.subTest(field=key):
                self.common=copy.deepcopy(self.original[1]);self.common['evaluations']['Q_rep']['density'][key]=True;self.reject()

    def test_nonfinite_or_incorrect_electron_count_rejected(self):
        for bad in (float('nan'),float('inf'),9.99):
            with self.subTest(value=bad):
                self.common=copy.deepcopy(self.original[1]);self.common['evaluations']['Q_rep']['density']['electron_count']=bad;self.reject()

    def test_full_gga_and_actual_backend_are_required(self):
        for key,value in [('full_gga_potential',False),('generic_dftfunctionals_evaluation_used',True)]:
            with self.subTest(field=key):
                self.common=copy.deepcopy(self.original[1]);self.common['evaluations']['Q_rep']['backend'][key]=value;self.reject()

    def test_native_pc_electron_atom_volume_factors_not_interchangeable(self):
        for key,value in [('natoms',2),('model_ne',20),('volume_bohr3',2000),('alpha_from_common_native',18.0)]:
            with self.subTest(field=key):
                self.common=copy.deepcopy(self.original[1]);self.common['constants'][key]=value;self.reject()

    def test_native_local_zero_not_finite_alpha(self):
        self.common['constants']['psp_local_fourier_G0']=self.common['constants']['alpha_from_common_native']/1000
        self.reject()

    def test_radial_cannot_apply_a_correction_to_historical_energy(self):
        self.radial['applied_energy_correction']=True;self.reject()

    def test_saved_radial_C_and_NePc_factors_rejected_if_changed(self):
        for route in ('primary_full_native_grid','trapezoid_full_native_grid','qe_tagged_prediction'):
            for key in ('C_ha','Pc_neutral_candidate_ha'):
                with self.subTest(route=route,field=key):
                    self.radial=copy.deepcopy(self.original[2]);self.radial[route][key]*=2;self.reject()

    def test_signed_radial_candidate_cannot_reverse_sign(self):
        candidate='Ne_times_C_D_minus_C_Q_tagged_ha'
        self.assertNotEqual(self.radial['dftk_bookkeeping'][candidate],0)
        self.radial['dftk_bookkeeping'][candidate]*=-1
        with self.assertRaisesRegex(ValueError,'Signed G0 candidate'):
            self.compare()

    def test_tagged_prediction_cannot_become_runtime_measurement(self):
        for key,value in [('status','MEASURED_QE_RUNTIME'),('actual_QE_table_status','EXTRACTED')]:
            with self.subTest(field=key):
                self.radial=copy.deepcopy(self.original[2]);self.radial['qe_tagged_prediction'][key]=value;self.reject()

    def test_historical_and_reevaluated_xc_keep_explicit_drift(self):
        result=self.compare()
        for label in ('A','B'):
            for name in ('xc','ixc'):
                split=result['comparisons'][label+'_minus_G40'][name]
                self.assertAlmostEqual(split['historical_difference_ha'],
                    split['density_response_in_D_ha']+split['evaluation_residual_at_Q_rep_ha']-split['same_source_reference_drift_ha'],delta=1e-10)
                self.assertIn('reevaluated_reference_minus_historical_Q_ha',split)

    def test_all_277_frozen_predecessor_files_remain_exact(self):
        self.assertEqual(check_frozen(ROOT,self.plan['base_commit']),277)


if __name__=='__main__':
    unittest.main()
