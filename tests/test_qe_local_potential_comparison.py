"""Analytic periodic fields only, never real Mg/QE/DFTK evaluations."""
import copy
import itertools
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import compare_qe_local_potential as M

EPS=1e-11


def fixture():
    size=(4,5,6);lattice=[[3.,0,0],[0,4.,0],[0,0,5.]];volume=60.
    modes=list(itertools.product(*(range(-n//2+(n%2),n//2+(n%2)) for n in size)))
    # First axis varies fastest. Non-axis directions and arbitrary complex
    # phases are deliberately different for density and the two potentials.
    direction=(1,1,-1);other=(0,1,1)
    def coefficients(mean,first,second=0j):
        out={m:0j for m in modes};out[(0,0,0)]=complex(mean)
        for m,z in [(direction,first),(other,second)]:
            out[m]=z;out[tuple(-i for i in m)]=z.conjugate()
        return out
    densities={'A':coefficients((10-4e-9)/volume,.011+.004j,.003-.002j),
               'B':coefficients((10+2e-9)/volume,.012+.005j,.002-.001j),
               'Q':coefficients((10+8e-9)/volume,.01+.003j,.001-.004j)}
    potentials={'D':coefficients(.01,.2+.03j,-.04+.07j),
                'Qpp':coefficients(.4,.17+.01j,-.05+.09j)}
    def field(c):
        values=[]
        for k in range(size[2]):
            for j in range(size[1]):
                for i in range(size[0]):
                    p=(i/size[0],j/size[1],k/size[2]);v=c[(0,0,0)].real
                    for m in (direction,other):
                        theta=2*math.pi*sum(a*b for a,b in zip(m,p));z=c[m]
                        v+=2*(z.real*math.cos(theta)-z.imag*math.sin(theta))
                    values.append(v)
        return values
    arrays={k:field(v) for k,v in densities.items()};v={k:field(c) for k,c in potentials.items()}
    widths=[1e-10*(1+i%3) for i in range(math.prod(size))]
    rho_widths=[1e-11]*len(widths);p0=[n+((-1)**i)*2e-12 for i,n in enumerate(arrays['Q'])]
    point=M.pointwise_checks(arrays['A'],arrays['B'],arrays['Q'],v['D'],v['Qpp'],p0,widths,rho_widths,volume_bohr3=volume)
    integrals=point['integrals_ha'];pc=.2
    qnative={'O':-5.2,'H':.8,'XC':-.4,'Ew':-1.6};qnative['E']=sum(qnative.values())
    native={'G40':qnative};comparisons={};evals={}
    for label,drift in [('A',2e-12),('B',-3e-12)]:
        terms={'Kinetic':2.,'AtomicNonlocalFR':-.1,'AtomicLocal':integrals['L_D_'+label]-drift,
               'PspCorrection':pc,'Hartree':.7,'Xc':-.3,'Ewald':-1.5}
        en=math.fsum(terms.values());od=math.fsum(terms[k] for k in ('Kinetic','AtomicNonlocalFR','AtomicLocal','PspCorrection'))
        native[label]={'E':en,'terms':terms}
        delta={'E':en-qnative['E'],'H':terms['Hartree']-qnative['H'],'XC':terms['Xc']-qnative['XC'],
               'Ew':terms['Ewald']-qnative['Ew'],'O':od-qnative['O']}
        comparisons[label+'_minus_G40']={'delta_ha':delta}
        evals[label+'_original_n_out']={'local_integral_ha':integrals['L_D_'+label]}
    evals['Q_rep']={'local_integral_ha':integrals['L_D_Q'],'local_mean_ha':.01}
    history={'ledger':{'historical_energy_ledger_status':'PASS','native_values':native,'comparisons':comparisons,
                'field_dictionary':[{'id':'G40.'+k,'quantization_half_width_ha':1e-15} for k in ('etot','demet','ehart','etxc','ewald')]},
             'common':{'execution_status':'PASS','constants':{'psp_correction_ha':pc,'model_ne':10,'volume_bohr3':volume,
                'alpha_from_common_native':pc*volume/10,'natoms':1,'n_electrons_from_atoms_actual':10},'evaluations':evals},
             'radial':{'qe_tagged_prediction':{'status':'PREDICTED_QE_7_5_TAGGED_CONVENTION','C_ha':.4}}}
    densities['Q']={m:z for m,z in densities['Q'].items() if z!=0}
    return dict(densities=densities,potentials=potentials,arrays=arrays,v=v,widths=widths,rho_widths=rho_widths,p0=p0,
        point=point,history=history,size=size,lattice=lattice,volume=volume)


def compare(f):
    return M.compare_local_potential(f['densities'],f['potentials'],lattice_vectors_bohr=f['lattice'],
        fft_size=f['size'],historical=f['history'],pointwise=f['point'])


class LocalComparisonTests(unittest.TestCase):
    def test_analytic_nonzero_phase_integral_and_complete_modes(self):
        f=fixture();out=compare(f)
        n=f['densities']['Q'];v=f['potentials']['Qpp']
        exact=f['volume']*(n[(0,0,0)].real*.4+2*sum((n[m].conjugate()*v[m]).real for m in [(1,1,-1),(0,1,1)]))
        self.assertAlmostEqual(out['integrals_fourier_ha']['L_Qpp_Q'],exact,delta=EPS)
        self.assertAlmostEqual(out['integrals_direct_ha']['L_Qpp_Q'],exact,delta=EPS)
        self.assertGreater(abs(exact),1)
        self.assertEqual(out['nonzero_G_shape']['native_coefficient_count'],120)
        self.assertEqual(out['local_energy_decomposition_status'],'PASS_ALGEBRA')
        self.assertFalse(out['native_E_F_modified'])

    def test_signed_local_partition_and_historical_drift(self):
        f=fixture();out=compare(f)
        for label,expected_drift in [('A',2e-12),('B',-3e-12)]:
            r=out['comparisons'][label+'_minus_G40']
            total=r['rho_response_ha']+r['shape_at_Q_ha']+r['g0_at_Q_ha']
            self.assertAlmostEqual(r['Delta_Lbar_current_ha'],total,delta=EPS)
            self.assertAlmostEqual(r['Delta_Lbar_historical_ha'],total-r['same_source_local_plus_Pc_drift_ha'],delta=EPS)
            self.assertAlmostEqual(r['same_source_local_plus_Pc_drift_ha'],expected_drift,delta=EPS)
            self.assertAlmostEqual(r['historical_delta_ha']['E'],sum(r['historical_delta_ha'][k] for k in ('H','XC','Ew'))+r['Delta_Lbar_historical_ha']+r['R_after_local_ha'],delta=EPS)
            self.assertLess(r['historical_delta_ha']['H'],0)

    def test_actual_electron_count_and_mean_cannot_use_simplified_g0(self):
        f=fixture();out=compare(f);r=out['comparisons']['A_minus_G40'];nq=f['point']['electrons']['Q']
        exact=.2+nq*(.01-.4)
        self.assertAlmostEqual(r['g0_at_Q_ha'],exact,delta=EPS)
        self.assertAlmostEqual(r['g0_at_Q_ha']-r['g0_simplified_auxiliary_ha'],r['g0_exact_minus_simplified_ha'],delta=EPS)
        self.assertGreater(abs(r['g0_at_Q_ha']-r['g0_simplified_auxiliary_ha']),.09)
        # Even when D mean is exactly zero, the saved delta-N term remains.
        self.assertGreater(abs((10-nq)*.4),1e-10)

    def test_uncertainty_propagation_and_correlations(self):
        f=fixture();q=f['arrays']['Q'];uv=f['widths'];un=f['rho_widths'];p0=f['p0'];vq=f['v']['Qpp']
        dvol=f['volume']/len(q);got=f['point']['quantization']
        self.assertAlmostEqual(got['u_meanV_ha'],sum(uv)/len(q),delta=1e-20)
        self.assertAlmostEqual(got['u_L_Q_ha'],dvol*sum(abs(n)*u for n,u in zip(q,uv)),delta=1e-20)
        expected=dvol*sum(abs(n)*u+abs(v)*r+r*u for n,v,u,r in zip(p0,vq,uv,un))
        self.assertAlmostEqual(got['u_L_using_printed_rho_ha'],expected,delta=1e-20)
        self.assertEqual(got['u_shape_plus_g0_ha'],got['u_L_Q_ha'])
        self.assertGreater(got['u_shape_at_Q_ha']+got['u_g0_at_Q_ha'],got['u_shape_plus_g0_ha'])
        self.assertLessEqual(got['u_L_Q_from_registered_P0_lower_ha'],got['u_L_Q_ha'])
        self.assertGreaterEqual(got['u_L_Q_from_registered_P0_upper_ha'],got['u_L_Q_ha'])

    def test_P0_failure_blocks_same_density_attribution_but_keeps_mean(self):
        f=fixture();f['p0'][7]+=.001
        f['point']=M.pointwise_checks(f['arrays']['A'],f['arrays']['B'],f['arrays']['Q'],f['v']['D'],f['v']['Qpp'],f['p0'],f['widths'],f['rho_widths'],volume_bohr3=f['volume'])
        out=compare(f)
        self.assertEqual(out['P0_density_registration_status'],'FAIL')
        self.assertEqual(out['comparisons'],{})
        self.assertEqual(out['local_same_density_integration_status'],'BLOCKED_P0_REGISTRATION')
        self.assertAlmostEqual(out['means_ha']['Qpp'],.4,delta=EPS)

    def test_P0_within_token_and_roundoff_allowance(self):
        f=fixture();self.assertEqual(f['point']['P0_density_registration_status'],'PASS')
        self.assertEqual(f['point']['P0']['failing_points'],0)
        self.assertLess(f['point']['P0']['maximum_point_error'],2.01e-12)

    def test_false_registration_PASS_is_rejected(self):
        for key,value in [('failing_points',1),('maximum_excess_over_allowance',.01),('electron_difference',1.)]:
            f=fixture();f['point']['P0'][key]=value
            with self.assertRaisesRegex(ValueError,'registration status'):compare(f)

    def test_false_correlated_uncertainty_or_precision_status_is_rejected(self):
        for key in ('u_g0_at_Q_ha','u_shape_plus_g0_ha'):
            f=fixture();f['point']['quantization'][key]*=2
            with self.assertRaisesRegex(ValueError,'propagation'):compare(f)
        f=fixture();f['point']['output_precision_status']='PRECISION_LIMITED'
        with self.assertRaisesRegex(ValueError,'precision status'):compare(f)

    def test_grid_transposition_origin_or_conjugation_are_not_fitted(self):
        f=fixture();original=f['p0']
        wrongs=[original[1:]+original[:1],list(reversed(original)),
                [original[i+4*(j+5*k)] for i in range(4) for j in range(5) for k in range(6)]]
        for p0 in wrongs:
            got=M.pointwise_checks(f['arrays']['A'],f['arrays']['B'],f['arrays']['Q'],f['v']['D'],f['v']['Qpp'],p0,f['widths'],f['rho_widths'],volume_bohr3=f['volume'])
            self.assertEqual(got['P0_density_registration_status'],'FAIL')

    def test_missing_nodes_padding_repeat_and_nonfinite_rejected(self):
        f=fixture();base=[f['arrays']['A'],f['arrays']['B'],f['arrays']['Q'],f['v']['D'],f['v']['Qpp'],f['p0'],f['widths'],f['rho_widths']]
        for replacement in [f['p0'][:-1],f['p0']+[f['p0'][0]],[math.nan]+f['p0'][1:]]:
            args=copy.deepcopy(base);args[5]=replacement
            with self.assertRaises(ValueError):M.pointwise_checks(*args,volume_bohr3=f['volume'])

    def test_missing_native_mode_even_zero_valued_rejected(self):
        f=fixture();f['potentials']['Qpp'].pop((-2,-2,-3))
        with self.assertRaisesRegex(ValueError,'Complete native'):compare(f)

    def test_duplicate_nyquist_and_external_G_and_G_plus_k_rejected(self):
        for badkey in [(2,0,0),(3,0,0),(.125,0,0)]:
            f=fixture();f['potentials']['D'][badkey]=0j
            with self.assertRaises(ValueError):compare(f)

    def test_nyquist_has_one_modular_representative_not_double_weight(self):
        size=(2,2,2);c={m:0j for m in itertools.product((-1,0),repeat=3)}
        c[(0,0,0)]=2;c[(-1,0,0)]=3
        a=M._native(c,size,complete=True)
        self.assertAlmostEqual(M.fourier_integral(a,a,5),65,delta=EPS)
        c[(-1,0,0)]=3+1j
        with self.assertRaisesRegex(ValueError,'conjugacy'):M._native(c,size,complete=True)

    def test_original_D_mean_removed_is_detected(self):
        f=fixture();f['potentials']['D'][(0,0,0)]=0j
        with self.assertRaisesRegex(ValueError,'mean'):compare(f)

    def test_wrong_Ry_Ha_or_spin_factor_is_detected(self):
        f=fixture();f['point']['units']['potential']='Ry'
        with self.assertRaisesRegex(ValueError,'units'):compare(f)
        f=fixture();f['potentials']['D']={m:2*z for m,z in f['potentials']['D'].items()}
        with self.assertRaises(ValueError):compare(f)
        f=fixture();f['densities']['Q']={m:2*z for m,z in f['densities']['Q'].items()}
        with self.assertRaisesRegex(ValueError,'electrons'):compare(f)

    def test_Pc_double_half_or_fit_without_native_identity_rejected(self):
        for factor in (2,.5,1.37):
            f=fixture();f['history']['common']['constants']['psp_correction_ha']*=factor
            with self.assertRaisesRegex(ValueError,'Pc'):compare(f)
        f=fixture();f['history']['ledger']['native_values']['A']['terms']['PspCorrection']*=2
        with self.assertRaisesRegex(ValueError,'Pc'):compare(f)

    def test_no_local_children_double_count_in_total(self):
        out=compare(fixture());r=out['comparisons']['A_minus_G40']
        correct=sum(r['historical_delta_ha'][k] for k in ('H','XC','Ew'))+r['Delta_Lbar_historical_ha']+r['R_after_local_ha']
        wrong=correct+r['rho_response_ha']+r['shape_at_Q_ha']+r['g0_at_Q_ha']
        self.assertAlmostEqual(correct,r['historical_delta_ha']['E'],delta=EPS)
        self.assertGreater(abs(wrong-r['historical_delta_ha']['E']),1)

    def test_remaining_TNL_label_is_derived_and_historical_E_untouched(self):
        f=fixture();before=copy.deepcopy(f['history']);out=compare(f)
        self.assertEqual(out['Q_TNL_record_kind'],'DERIVED_LEDGER_REMAINDER_USING_PP_RECONSTRUCTED_LOCAL_INTEGRAL')
        self.assertEqual(out['independent_QE_T_NL_status'],'NOT_AVAILABLE')
        self.assertEqual(out['qe_internal_tab_vloc_status'],'NOT_EXTRACTED')
        self.assertEqual(f['history'],before)

    def test_prediction_disagreement_is_scientific_status_not_adjustment(self):
        f=fixture();f['history']['radial']['qe_tagged_prediction']['C_ha']=.5
        out=compare(f)
        self.assertEqual(out['G0_prediction_comparison_status'],'NOT_SUPPORTED_BY_PP_RECONSTRUCTED_MEAN')
        self.assertAlmostEqual(out['means_ha']['Qpp'],.4,delta=EPS)
        self.assertEqual(out['local_energy_decomposition_status'],'PASS_ALGEBRA')

    def test_precision_limited_is_retained_without_extra_calculation(self):
        f=fixture();f['widths']=[1e-5]*120
        f['point']=M.pointwise_checks(f['arrays']['A'],f['arrays']['B'],f['arrays']['Q'],f['v']['D'],f['v']['Qpp'],f['p0'],f['widths'],f['rho_widths'],volume_bohr3=f['volume'])
        out=compare(f)
        self.assertEqual(out['output_precision_status'],'PRECISION_LIMITED')
        self.assertEqual(out['numerical_review_status'],'REVIEW_REQUIRED')


if __name__=='__main__':unittest.main()
