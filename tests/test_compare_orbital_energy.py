"""Synthetic ledger/precision tests. No real orbital or P2 array is read."""
import copy
import importlib.util
import json
import math
from pathlib import Path
import unittest

import numpy as np

SPEC=importlib.util.spec_from_file_location('orbital_energy',Path(__file__).resolve().parents[1]/'scripts/compare_orbital_energy.py')
C=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(C)
T={'ledger_abs_ha':1e-10,'electron_count_abs':1e-8,'kinetic_history_abs_ha':1e-9,
   'historical_nonlocal_abs_ha':1e-9,'nonlocal_contraction_abs_ha':1e-10}


def synthetic():
    ns=np.array([.8,1.1,1.2,.9]);nw=ns+np.array([.05,-.04,-.02,.01])
    v=np.array([-2.,.4,-.3,-1.5]);uv=np.array([.01,.002,.03,.004]);dvol=2.
    Ls=dvol*math.fsum((ns*v).tolist());Lold=Ls-3e-12
    token_widths=[1e-7,2e-8,3e-8,4e-9,5e-8];uO=math.fsum(token_widths)
    uR=dvol*math.fsum((np.abs(ns)*uv).tolist())+uO
    ledger={'historical_energy_ledger_status':'PASS','source_binding_status':'PASS',
            'native_values':{'G40':{'E':-4.,'F':-4.01,'H':2.,'XC':-1.,'Ew':-.5,'O':-4.5}},
            'field_dictionary':[{'id':'G40.'+k,'quantization_half_width_ha':w} for k,w in zip(('etot','demet','ehart','etxc','ewald'),token_widths)],
            'comparisons':{}}
    previous={'execution_status':'PASS','source_preservation_status':'PASS',
              'original_pointwise_integrals_ha':{'L_Qpp_Q':Lold},'original_comparisons':{}}
    reports={};nl={'execution_status':'PASS','states':{}}
    for label,Tval,Nval in [('A',3.,-.4),('B',3.4,-.5),('Q',3.3,-.7)]:
        actualT=Tval+(1e-10 if label=='A' else 0.);actualN=Nval+(2e-10 if label=='A' else 0.)
        reports[label]={'label':label,'status':'PASS','all_required_gates_passed':True,
            'same_source_orbital_density':{'status':'PASS'},'electrons':{'status':'PASS','from_real_density':8.},
            'kinetic':{'status':'PASS','direct_ha':actualT,'same_source_status':'PASS',
                'evidence_kind':'DIRECT_REEVALUATION_OF_KINETIC_FROM_ORIGINAL_QE_WFC' if label=='Q' else 'DIRECT_REEVALUATION_OF_KINETIC_FROM_ORIGINAL_DFTK_X'},
            'input_bytes_unchanged':True,'normalization_or_QR_applied':False,
            'normalization_and_gram':[{'status':'PASS'}],'direct_correlation_checks':[{'status':'PASS'} for _ in range(17)]}
        nl['states'][label]={'status':'PASS','quantity':C.Q_NL_KIND if label=='Q' else C.AB_NL_KIND,
            'energy_action_ha':actualN,'energy_projected_ha':actualN,'energy_spin_sum_ha':actualN}
        if label=='Q':continue
        terms={'Kinetic':Tval,'AtomicNonlocalFR':Nval,'AtomicLocal':-1.2,'PspCorrection':.1}
        ledger['native_values'][label]={'E':-3.8,'F':-3.81,'terms':terms}
        Kh=Tval+Nval;grouping=5e-12
        Rold=math.fsum([Kh,4.5,Lold])+grouping
        ledger['comparisons'][label+'_minus_G40']={'delta_ha':{'O':Rold+(terms['AtomicLocal']+terms['PspCorrection']-Lold)}}
        previous['original_comparisons'][label+'_minus_G40']={'R_after_local_ha':Rold,
            'uncertainty':{'u_R_after_local_print_ha':uR}}
    return reports,nl,nw,ns,v,uv,ledger,previous


class OrbitalEnergyTests(unittest.TestCase):
    def setUp(self):
        self.reports,self.nl,self.nw,self.ns,self.v,self.uv,self.ledger,self.previous=synthetic()

    def calculate(self):
        return C.compare_arrays(self.reports,self.nl,self.nw,self.ns,self.v,self.uv,volume_bohr3=8.,
            expected_electrons=8.,ledger=self.ledger,previous=self.previous,thresholds=T)

    def test_signed_decomposition_matches_independent_scalar_arithmetic(self):
        r=self.calculate();row=r['comparisons']['A']
        Lw=2*sum(self.nw*self.v);Ls=2*sum(self.ns*self.v)
        self.assertAlmostEqual(r['local_state']['L_wfc_ha'],Lw,places=14)
        self.assertAlmostEqual(r['local_state']['delta_L_state_ha'],Ls-Lw,places=14)
        self.assertAlmostEqual(r['Q']['J_Q_ha'],3.3-.7+Lw+4.5,places=14)
        self.assertAlmostEqual(r['Q']['NL_Q_ledger_ha'],-4.5-Lw-3.3,places=14)
        self.assertLess(abs(row['signed_closure_error_ha']),1e-14)
        self.assertEqual(row['R_old_ha'],self.previous['original_comparisons']['A_minus_G40']['R_after_local_ha'])

    def test_direct_local_state_difference_and_replay_drift_retained(self):
        r=self.calculate();row=r['comparisons']['A']
        expected=2*math.fsum(((self.ns-self.nw)*self.v).tolist())
        self.assertEqual(row['delta_L_state_ha'],expected)
        self.assertNotEqual(row['saved_local_replay_drift_ha'],0.)
        self.assertNotEqual(row['historical_O_combination_drift_ha'],0.)
        self.assertLess(abs(row['historical_O_combination_drift_ha']),T['ledger_abs_ha'])

    def test_omitting_local_state_term_is_rejected(self):
        r=self.calculate();r['comparisons']['A']['delta_L_state_ha']=0.
        with self.assertRaisesRegex(ValueError,'local state'):C.validate_result(r,T)

    def test_omitting_same_source_drift_is_rejected(self):
        r=self.calculate();self.assertGreater(abs(r['comparisons']['A']['drift_S_ha']),T['ledger_abs_ha'])
        r['comparisons']['A']['drift_S_ha']=0.
        with self.assertRaisesRegex(ValueError,'drift'):C.validate_result(r,T)

    def test_correlated_delta_bound_is_not_two_independent_error_bars(self):
        b=self.calculate()['printing']['halfwidths_ha']
        exact=2*sum(abs(self.ns-self.nw)*self.uv)
        self.assertAlmostEqual(b['delta_L_state'],exact,places=15)
        self.assertLess(b['delta_L_state'],b['L_saved']+b['L_wfc'])
        self.assertNotAlmostEqual(b['delta_L_state'],math.hypot(b['L_saved'],b['L_wfc']),places=5)

    def test_shared_P2_and_O_cancel_before_propagation(self):
        r=self.calculate();b=r['printing']['halfwidths_ha'];uO=r['printing']['O_halfwidth_ha']
        self.assertEqual(b['J_plus_NL_Q_ledger'],0.)
        self.assertEqual(b['J_plus_delta_L'],b['L_saved']+uO)
        self.assertEqual(b['recomposed_R'],b['J_plus_delta_L'])
        self.assertAlmostEqual(r['Q']['J_Q_ha']+r['Q']['NL_Q_ledger_ha'],r['Q']['N_D_ha'],places=14)

    def test_full_token_specific_bound_and_volume_no_RSS(self):
        coeff=np.array([2.,-3.,1.,0.]);u=np.array([.1,.01,.3,.04])
        self.assertAlmostEqual(C.correlated_print_bound(coeff,u,2.,O_coefficient=-2.,O_halfwidth=.07),1.2,places=15)
        self.assertAlmostEqual(C.correlated_print_bound(coeff,u,4.),2*C.correlated_print_bound(coeff,u,2.),places=15)

    def test_ledger_O_token_widths_used_once(self):
        p=self.calculate()['printing'];self.assertEqual(len(p['O_token_halfwidths_ha']),5)
        self.assertEqual(p['O_halfwidth_ha'],math.fsum([1e-7,2e-8,3e-8,4e-9,5e-8]))
        self.assertEqual(p['halfwidths_ha']['NL_Q_ledger'],p['halfwidths_ha']['L_wfc']+p['O_halfwidth_ha'])

    def test_Q_workbench_NL_cannot_be_relabelled_native(self):
        self.nl['states']['Q']['quantity']='QE_NATIVE_NONLOCAL'
        with self.assertRaisesRegex(ValueError,'quantity'):self.calculate()

    def test_public_Q_ND_or_ledger_NL_overclaim_rejected(self):
        for key in ('N_D_quantity','NL_Q_ledger_quantity'):
            r=self.calculate();r['Q'][key]='QE_NATIVE_NONLOCAL_MEASURED'
            with self.subTest(field=key):
                with self.assertRaisesRegex(ValueError,'provenance'):C.validate_result(r,T)

    def test_Q_kinetic_is_direct_not_native_print(self):
        r=self.calculate();r['Q']['T_quantity']='NATIVE_QE_PRINTED_KINETIC'
        with self.assertRaisesRegex(ValueError,'printed'):C.validate_result(r,T)

    def test_Q_density_failure_blocks_dependent_ledger(self):
        self.reports['Q']['same_source_orbital_density']['status']='FAIL'
        with self.assertRaisesRegex(ValueError,'Density/electron'):self.calculate()

    def test_empty_gate_list_does_not_pass_vacuously(self):
        self.reports['Q']['normalization_and_gram']=[]
        with self.assertRaisesRegex(ValueError,'Incomplete'):self.calculate()

    def test_nonlocal_contraction_mismatch_blocks_ledger(self):
        self.nl['states']['Q']['energy_projected_ha']+=1e-5
        with self.assertRaisesRegex(ValueError,'projection'):self.calculate()

    def test_A_nonlocal_history_failure_blocks_Q_comparison(self):
        for k in ('energy_action_ha','energy_projected_ha','energy_spin_sum_ha'):self.nl['states']['A'][k]+=1e-5
        with self.assertRaisesRegex(ValueError,'same-source NL'):self.calculate()

    def test_P2_Ry_double_scale_cannot_match_old_integral(self):
        self.v*=2
        with self.assertRaisesRegex(ValueError,'local integral replay'):self.calculate()

    def test_wrong_Q_density_electron_count_rejected(self):
        self.nw*=2
        with self.assertRaisesRegex(ValueError,'electrons'):self.calculate()

    def test_wrong_Q_report_ownership_rejected(self):
        self.reports['Q']['electrons']['from_real_density']=7.
        with self.assertRaisesRegex(ValueError,'ownership'):self.calculate()

    def test_nonfinite_field_negative_halfwidth_and_wrong_dtype_rejected(self):
        for kind in ('nan','negative','float32'):
            self.setUp()
            if kind=='nan':self.nw[0]=float('nan')
            elif kind=='negative':self.uv[0]=-.1
            else:self.nw=self.nw.astype(np.float32)
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):self.calculate()

    def test_historical_E_F_and_input_arrays_are_unchanged(self):
        before=json.dumps([self.ledger,self.previous],sort_keys=True)
        arrays=[x.tobytes() for x in (self.nw,self.ns,self.v,self.uv)]
        r=self.calculate()
        self.assertEqual(before,json.dumps([self.ledger,self.previous],sort_keys=True))
        self.assertEqual(arrays,[x.tobytes() for x in (self.nw,self.ns,self.v,self.uv)])
        self.assertFalse(r['native_E_F_modified']);self.assertFalse(r['energy_correction_applied'])
        self.assertEqual(r['historical_E_F_ha']['G40'],{'E':-4.,'F':-4.01})

    def test_new_J_is_not_forced_close_to_zero(self):
        for key in ('energy_action_ha','energy_projected_ha','energy_spin_sum_ha'):self.nl['states']['Q'][key]=15.
        r=self.calculate();self.assertGreater(abs(r['Q']['J_Q_ha']),10.)
        self.assertEqual(r['status'],'PASS_LIMITED_STATIC_AUDIT')
        self.assertEqual(r['physical_convergence_status'],'NOT_ESTABLISHED')

    def test_false_physical_validation_and_correction_rejected(self):
        for key,value in [('physical_convergence_status','PASS'),('independent_native_qe_nonlocal_status','PASS'),
                          ('energy_correction_applied',True),('new_qe_pp_execution_status','PASS')]:
            r=self.calculate();r[key]=value
            with self.subTest(field=key):
                with self.assertRaises(ValueError):C.validate_result(r,T)

    def test_derived_NL_numeric_tamper_is_rejected(self):
        r=self.calculate();r['Q']['NL_Q_ledger_ha']+=.01
        with self.assertRaisesRegex(ValueError,'NL-shaped'):C.validate_result(r,T)

    def test_wrong_old_R_and_print_interval_rejected(self):
        self.previous['original_comparisons']['A_minus_G40']['R_after_local_ha']+=1e-5
        with self.assertRaisesRegex(ValueError,'grouping'):self.calculate()
        self.setUp();self.previous['original_comparisons']['A_minus_G40']['uncertainty']['u_R_after_local_print_ha']*=2
        with self.assertRaisesRegex(ValueError,'print interval'):self.calculate()


if __name__=='__main__':unittest.main()
