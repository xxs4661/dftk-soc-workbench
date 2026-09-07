#!/usr/bin/env python3
"""Synthetic 7B protocol/arithmetic fixtures; no new QE, Julia or density evidence."""
import copy
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import compare_qe_soc_diagnostics as d


def synthetic_ieee_flags():
    return {name:{'reported':name=='IEEE_INVALID_FLAG','stdout':[],'stderr':[]} for name in
        ('IEEE_INVALID_FLAG','IEEE_DIVIDE_BY_ZERO','IEEE_OVERFLOW_FLAG','IEEE_UNDERFLOW_FLAG','IEEE_INEXACT_FLAG')}


def fixture_records(plan):
    """Published values copied only to synthesize slot protocols, never measured runs."""
    source=json.loads((ROOT/'results/mg-soc-qe-comparison/qe-result.json').read_text())
    records={}
    for slot,spec in plan['slots'].items():
        if slot == 'I36':
            records[slot]={'slot':slot,'run_id':'SYNTHETIC-'+slot,'execution_status':'PASS',
                'input_contract_status':'PASS','numerical_solve_status':'NOT_RUN',
                'energy':None,'scf':None,'kpoints':None,
                'warning_diagnostics':{'ieee_flags':synthetic_ieee_flags(), 'eigenvalues_not_converged':False,
                                       'native_lines':[{'stream':'stderr','line':1,'text':'SYNTHETIC IEEE_INVALID_FLAG'}]},
                'native_solver_warning_status':'NO_UNCONVERGED_WARNING_REPORTED'}
            continue
        record=copy.deepcopy(source)
        record.update(slot=slot,run_id='SYNTHETIC-'+slot,case=plan['case'],phase='7B',
                      input_contract_status='PASS',execution_status='PASS')
        record['calculation']=spec['calculation']
        record['fft_grid']=record['fft_smooth_grid']=list(spec['fft_grid'])
        record['actual_solver']={'namelist':spec['solver'],'xml':{'david':'davidson','cg':'cg'}[spec['solver']],'stdout':[spec['solver']]}
        record['diagnostic_parameters']={'diago_thr_init_ry':spec['diago_thr_init_ry']}
        record['native_solver_warning_status']='NO_UNCONVERGED_WARNING_REPORTED'
        record['warning_diagnostics']={'ieee_flags':synthetic_ieee_flags(),'eigenvalues_not_converged':False,
            'native_lines':[{'stream':'stderr','line':1,'text':'SYNTHETIC IEEE_INVALID_FLAG'}]}
        record['source_binding']={'status':'NOT_APPLICABLE'}
        if spec['calculation'] == 'bands':
            record['energy']=record['scf']=None
            record['energy_semantics_status']='NOT_APPLICABLE_SPECTRUM_ONLY'
            src=spec['source_slot']
            record['source_binding']={'status':'PASS','source_slot':src,
                'source_run_id':'20260907T001853989732Z-c88a8fa3' if src=='Q36' else 'SYNTHETIC-G40',
                'source_snapshot_sha256':('a' if src=='Q36' else 'b')*64,
                'charge_before_sha256':'c'*64,'charge_after_sha256':'c'*64,
                'initial_wfc_sha256':{'wfc1.dat':'d'*64,'wfc2.dat':'e'*64,'wfc3.dat':'f'*64},
                'source_preservation_status':'PASS'}
            record['read_start_evidence']={'potential_from_file':True,'wavefunctions_from_file':True,
                                           'scf_iteration_lines':[],'fallback_lines':[],'band_structure_lines':[{'line':1,'text':'SYNTHETIC bands'}],'status':'PASS'}
        record['parsed_payload_sha256']=d.payload_sha256(record)
        records[slot]=record
    return records


class DiagnosticsComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan0=json.loads((ROOT/'benchmarks/mg-soc-qe-diagnostics-v1/plan.json').read_text())

    def setUp(self):
        self.plan=copy.deepcopy(self.plan0)
        self.records=fixture_records(self.plan)

    def analyze(self):return d.analyze(ROOT,self.plan,self.records)

    def reseal(self,slot):self.records[slot]['parsed_payload_sha256']=d.payload_sha256(self.records[slot])

    def test_all_slots_and_all_required_comparisons_retained(self):
        r=self.analyze()
        self.assertEqual(set(r['slots']),set(self.plan['slots']))
        for key in ('D36_minus_Q36','C36_minus_Q36','D36_minus_C36',
                    'D36_minus_old_bands','C36_minus_old_bands','D40_minus_G40',
                    'C40_minus_G40','D40_minus_C40','D40_minus_D36','C40_minus_C36'):
            self.assertEqual(len(r['spectra'][key]['rows']),72,key)
        for ref in ('A','B'):
            for slot in ('Q36','D36','C36','G40','D40','C40'):
                self.assertEqual(len(r['spectra'][ref+'_minus_'+slot]['rows']),72)
        self.assertEqual(r['numerical_agreement_status'],'REVIEW_REQUIRED')
        self.assertNotIn('overall_status',r)

    def test_same_density_pairs_never_align(self):
        for p in self.records['D36']['kpoints']:p['eigenvalues_ha']=[x+.001 for x in p['eigenvalues_ha']]
        self.reseal('D36');r=self.analyze()['spectra']['D36_minus_C36']
        self.assertEqual(r['reference_mode'],'RAW_ONLY')
        self.assertAlmostEqual(r['summary']['24']['all']['raw']['max_abs_ha'],.001)
        self.assertTrue(all('global_reference_difference_ha' not in row for row in r['rows']))

    def test_stability_threshold_and_ieee_remain_independent(self):
        r=self.analyze()
        for grid in ('36','40'):
            self.assertEqual(r['cross_solver_stability'][grid]['status'],'CROSS_SOLVER_STABILITY_OBSERVED')
        self.assertEqual(r['warning_origin_status'],'NOT_LOCALIZED')
        self.assertEqual(r['residual_certificate_status'],'NOT_AVAILABLE')

    def test_large_DC_difference_retained_without_retry_or_physical_pass(self):
        self.records['C36']['kpoints'][0]['eigenvalues_ha'][23]+=2e-7
        self.reseal('C36');r=self.analyze()
        self.assertEqual(r['cross_solver_stability']['36']['status'],'NOT_ESTABLISHED')
        self.assertGreater(r['spectra']['D36_minus_C36']['summary']['24']['all']['raw']['max_abs_ha'],1e-7)
        self.assertEqual(len(r['spectra']['D36_minus_C36']['rows']),72)

    def test_unconverged_warning_prevents_stability_not_data_retention(self):
        self.records['D36']['warning_diagnostics']['eigenvalues_not_converged']=True
        self.records['D36']['native_solver_warning_status']='UNCONVERGED_WARNING'
        r=self.analyze()
        self.assertEqual(r['cross_solver_stability']['36']['status'],'NOT_ESTABLISHED')
        self.assertEqual(len(r['spectra']['D36_minus_C36']['rows']),72)

    def test_missing_smooth_grid_or_different_actual_grid_rejected(self):
        self.records['G40']['fft_smooth_grid']=[36,36,36];self.reseal('G40')
        with self.assertRaises(ValueError):self.analyze()

    def test_solver_and_threshold_units_rejected(self):
        self.records['C36']['actual_solver']['xml']='david'
        with self.assertRaises(ValueError):self.analyze()
        self.records=fixture_records(self.plan)
        self.records['D36']['diagnostic_parameters']['diago_thr_init_ry']=.5e-13
        with self.assertRaises(ValueError):self.analyze()

    def test_different_source_density_or_initial_wfc_rejected(self):
        for field in ('source_snapshot_sha256','charge_before_sha256'):
            with self.subTest(field=field):
                self.records=fixture_records(self.plan)
                self.records['C36']['source_binding'][field]='0'*64
                with self.assertRaises(ValueError):self.analyze()
        self.records=fixture_records(self.plan)
        self.records['C36']['source_binding']['initial_wfc_sha256']['wfc1.dat']='0'*64
        with self.assertRaises(ValueError):self.analyze()

    def test_source_rewritten_or_using_other_solver_output_rejected(self):
        self.records['D36']['source_binding']['source_preservation_status']='FAIL'
        with self.assertRaises(ValueError):self.analyze()
        self.records=fixture_records(self.plan)
        self.records['C40']['source_binding']['source_run_id']='SYNTHETIC-D40'
        with self.assertRaises(ValueError):self.analyze()

    def test_missing_save_cannot_be_replaced_by_xml_receipt(self):
        self.records['D36']['source_binding']={'status':'PASS','source_slot':'Q36'}
        with self.assertRaises((ValueError,KeyError)):self.analyze()

    def test_bands_energy_is_never_in_total_energy_table(self):
        self.records['D36']['energy']={'internal_ha':0,'free_ha':0,'entropy_ha':0}
        with self.assertRaises(ValueError):self.analyze()

    def test_nonconverged_SCF_cannot_supply_energy(self):
        self.records['G40']['scf']['converged']=False
        with self.assertRaises(ValueError):self.analyze()

    def test_NaN_rejected_before_any_max_gate(self):
        self.records['C36']['kpoints'][0]['eigenvalues_ha'][0]=float('nan')
        with self.assertRaises(ValueError):self.analyze()

    def test_hybrid_record_spectrum_rejected_by_original_payload_binding(self):
        self.records['D40']['kpoints'][0]['eigenvalues_ha'][23]+=1e-6
        with self.assertRaisesRegex(ValueError,'payload'):self.analyze()

    def test_k_reordering_allowed_missing_duplicate_rejected(self):
        self.records['D36']['kpoints'].reverse();self.reseal('D36')
        self.analyze()
        self.records['D36']['kpoints'][0]['coordinate_fractional']=[0,0,0];self.reseal('D36')
        with self.assertRaises(ValueError):self.analyze()

    def test_non_saturated_occupation_keeps_raw_global_unsupported(self):
        for p in self.records['G40']['kpoints']:p['occupations'][9],p['occupations'][10]=.75,.25
        self.reseal('G40');r=self.analyze()['spectra']['A_minus_G40']
        self.assertEqual(r['global_reference_status'],'UNSUPPORTED')
        self.assertEqual(len(r['rows']),72)

    def test_summary_groups_and_maximum_location_occupations(self):
        self.records['C36']['kpoints'][1]['eigenvalues_ha'][17]+=8e-8
        self.reseal('C36');s=self.analyze()['spectra']['D36_minus_C36']['summary']
        self.assertEqual(s['16']['all']['raw']['count'],48)
        self.assertEqual(s['24']['all']['raw']['count'],72)
        self.assertEqual(s['24']['empty']['raw']['count'],42)
        loc=s['24']['all']['raw']['maximum_location']
        self.assertEqual(loc['band_index'],18)
        self.assertEqual(loc['coordinate_fractional'],[.125,.0625,-.1875])
        self.assertIn('left_occupation',loc)
        self.assertIn('right_occupation',loc)

    def test_grid_energy_bookkeeping_identity_without_correction(self):
        for field in ('internal_ha','free_ha','native_etot_ha'):self.records['G40']['energy'][field]+=.003
        self.reseal('G40');r=self.analyze()['energy']
        self.assertAlmostEqual(r['G40_minus_Q36']['energy']['internal']['signed_ha'],.003)
        for label in ('A','B'):
            self.assertLess(abs(r['grid_cross_difference_algebra'][label]['internal_residual_ha']),1e-12)
        self.assertNotIn('D36',r['records'])
        self.assertFalse(r['total_energy_correction_applied'])

    def test_FAILED_and_BLOCKED_slots_retained_with_dependency_status(self):
        self.records['G40']={'slot':'G40','execution_status':'FAIL','reason':'SYNTHETIC SCF failure'}
        for slot in ('D40','C40'):self.records[slot]={'slot':slot,'execution_status':'BLOCKED','reason':'G40 failed'}
        r=self.analyze()
        self.assertEqual(r['slots']['G40']['execution_status'],'FAIL')
        self.assertEqual(r['spectra']['D40_minus_C40']['status'],'BLOCKED')
        self.assertEqual(r['cross_solver_stability']['40']['status'],'NOT_ESTABLISHED')
        self.assertIn('Q36',r['energy']['records'])

    def test_plan_cannot_raise_stability_threshold(self):
        self.plan['cross_solver_gate_ha']=1e-3
        with self.assertRaises(ValueError):self.analyze()

    def test_missing_ieee_record_cannot_be_hidden_by_stable_spectrum(self):
        del self.records['C36']['warning_diagnostics']['ieee_flags']['IEEE_INVALID_FLAG']
        with self.assertRaises((ValueError,KeyError)):self.analyze()

    def test_wrong_stdout_solver_or_atomic_fallback_rejected(self):
        self.records['C36']['actual_solver']['stdout']=['david']
        with self.assertRaises(ValueError):self.analyze()
        self.records=fixture_records(self.plan)
        self.records['D36']['read_start_evidence']['fallback_lines']=[{'line':2,'text':'SYNTHETIC random fallback'}]
        with self.assertRaises(ValueError):self.analyze()

    def test_old_7A_public_replay_is_unchanged(self):
        from check_qe_soc_evidence import check
        result=check(ROOT)
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['historical_reference_status'],'HISTORICAL_REUSED')

    def test_public_summary_and_full_csv_have_no_duplicate_rows_or_CRLF(self):
        result=self.analyze()
        reduced=d.summary(result)
        self.assertTrue(all('rows' not in item for item in reduced['spectra'].values()))
        self.assertEqual(len(result['spectra']['D36_minus_C36']['rows']),72)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'eigenvalues.csv';d.write_differences_csv(path,result)
            self.assertNotIn(b'\r',path.read_bytes())
            with path.open() as f:rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),22*72)
            self.assertEqual(len({(r['pair'],r['k_index'],r['band_index']) for r in rows}),22*72)


if __name__=='__main__':unittest.main()
