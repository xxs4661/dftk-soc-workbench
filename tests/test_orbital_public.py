"""Public-table and rectangular-FR replay with entirely synthetic arrays."""
import copy
import importlib.util
import math
from pathlib import Path
import sys
import unittest

import numpy as np

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
SPEC=importlib.util.spec_from_file_location('public_orbitals',SCRIPTS/'check_orbital_energy.py')
P=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(P)


def kinetic_tables():
    reports={}
    for label in ('A','B','Q'):
        points=[];norms=[]
        for ik in range(3):
            rows=[]
            for band in range(24):
                f=1. if band<8 else ([.7,.8,.5][band-8] if band<11 else 0.)
                T=.15*(band+1)+.021*ik;grad=T+1e-13;w=1/3
                rows.append(dict(band_one_based=band+1,occupation=f,eigenvalue_ha=band*.1-.5,norm=1.,
                    kinetic_unweighted_ha=T,gradient_unweighted_ha=grad,kinetic_weighted_ha=w*f*T,
                    gradient_weighted_ha=w*f*grad,signed_path_difference_ha=T-grad))
            points.append(dict(k_index_zero_based=ik,NG=20,weight_spatial=w,states=rows,
                kinetic_ha=math.fsum(r['kinetic_weighted_ha'] for r in rows),
                gradient_kinetic_ha=math.fsum(r['gradient_weighted_ha'] for r in rows)))
            norms.append(dict(k_index_zero_based=ik,NG=20,norms=[1.]*24,maximum_norm_error=0.,gram_frobenius=0.,status='PASS'))
        direct=math.fsum(p['kinetic_ha'] for p in points);gradient=math.fsum(p['gradient_kinetic_ha'] for p in points)
        k=dict(direct_ha=direct,gradient_ha=gradient,signed_difference_ha=direct-gradient,status='PASS',
               evidence_kind='DIRECT_REEVALUATION_OF_KINETIC_FROM_ORIGINAL_QE_WFC' if label=='Q' else 'DIRECT_REEVALUATION_OF_KINETIC_FROM_ORIGINAL_DFTK_X')
        if label!='Q':k.update(same_source_status='PASS',historical_ha=direct-3e-10,historical_signed_difference_ha=direct-(direct-3e-10))
        reports[label]=dict(label=label,status='PASS',all_required_gates_passed=True,state_count=24,k_count=3,
            normalization_and_gram=norms,per_k=points,kinetic=k,electrons=dict(from_occupations=10.,from_actual_norms=10.))
    return reports


def complex_nonlocal_fixture(reports,phase=None,unitary=None):
    rng=np.random.default_rng(72601)
    def z(shape):return (rng.normal(size=shape)+1j*rng.normal(size=shape))*.07
    d=z((16,16));d=d+d.conj().T;d+=np.diag(np.linspace(-.4,.7,16))
    arrays={'D':d};state={'kpoints':[]};nl={'states':{label:{'kpoints':[]} for label in ('A','B','Q')}}
    independent={label:[] for label in ('A','B','Q')}
    for ik in range(1,4):
        m=np.array([[j-10,j%3,0] for j in range(20)],np.int64);p=z((40,16));x=z((40,24))
        if phase is not None:x*=np.exp(1j*phase)
        if unitary is not None:x[:,:2]=x[:,:2]@unitary
        c=x.reshape(20,2,24).transpose(1,0,2).copy()
        state['kpoints'].append({'millers':m.copy(),'coefficients':c})
        arrays[f'k{ik}_P']=p;arrays[f'k{ik}_millers']=m
        for label in ('A','B','Q'):
            yu=p[0::2].conj().T@x[0::2] if label=='Q' else z((16,24))
            yd=p[1::2].conj().T@x[1::2] if label=='Q' else z((16,24))
            arrays[f'{label}_k{ik}_up']=yu;arrays[f'{label}_k{ik}_down']=yd
            rows=[]
            # This synthetic reference may build a small 40x40 matrix, while
            # the production replay must use the rectangular P representation.
            full=p@d@p.conj().T
            for band in range(24):
                up=yu[:,band];down=yd[:,band];y=up+down
                projected=float(np.vdot(y,d@y).real);cross=np.vdot(up,d@down)
                uu=float(np.vdot(up,d@up).real);dd=float(np.vdot(down,d@down).real)
                action=float(np.vdot(x[:,band],full@x[:,band]).real) if label=='Q' else projected
                f=reports[label]['per_k'][ik-1]['states'][band]['occupation'];w=1/3
                rows.append(dict(band=band+1,occupation=f,weight_spatial=w,action_ha=action,projected_ha=projected,
                    up_up_ha=uu,down_down_ha=dd,up_down_real_ha=float(cross.real),up_down_imag_ha=float(cross.imag),
                    spin_cross_ha=2*float(cross.real),spin_sum_ha=uu+dd+2*float(cross.real),
                    weighted_action_ha=w*f*action,weighted_projected_ha=w*f*projected,
                    weighted_spin_sum_ha=w*f*(uu+dd+2*float(cross.real))))
                independent[label].append(w*f*action)
            nl['states'][label]['kpoints'].append({'rows':rows})
    for label in ('A','B','Q'):
        nl['states'][label].update(energy_action_ha=math.fsum(independent[label]),
            energy_projected_ha=math.fsum(r['weighted_projected_ha'] for k in nl['states'][label]['kpoints'] for r in k['rows']),
            energy_spin_sum_ha=math.fsum(r['weighted_spin_sum_ha'] for k in nl['states'][label]['kpoints'] for r in k['rows']))
    return arrays,state,nl,independent


class OrbitalPublicTests(unittest.TestCase):
    def setUp(self):self.reports=kinetic_tables()

    def test_all_72_weighted_kinetic_rows_replay_without_AB_X_claim(self):
        replay=P.kinetic_scalar_replay(self.reports)
        for label,row in replay.items():
            self.assertEqual(row['states_replayed'],72);self.assertEqual(row['status'],'PASS_SCALAR_TABLE_REPLAY')
            self.assertIn('does not reconstruct original A/B X',row['evidence_tier'])
            expected=math.fsum(k['weight_spatial']*r['occupation']*r['kinetic_unweighted_ha'] for k in self.reports[label]['per_k'] for r in k['states'])
            self.assertEqual(row['kinetic_ha'],expected)

    def test_wrong_weighted_directT_not_hidden_by_correct_total(self):
        self.reports['A']['per_k'][0]['states'][0]['kinetic_weighted_ha']+=1e-6
        with self.assertRaises(ValueError):P.kinetic_scalar_replay(self.reports)

    def test_wrong_weighted_gradientT_rejected(self):
        self.reports['B']['per_k'][1]['states'][1]['gradient_weighted_ha']*=2
        with self.assertRaises(ValueError):P.kinetic_scalar_replay(self.reports)

    def test_kinetic_partial_total_and_global_total_rejected(self):
        for location in ('k','global'):
            self.setUp()
            if location=='k':self.reports['A']['per_k'][1]['kinetic_ha']+=.01
            else:self.reports['A']['kinetic']['direct_ha']+=.01
            with self.subTest(location=location):
                with self.assertRaises(ValueError):P.kinetic_scalar_replay(self.reports)

    def test_missing_zero_occupied_tail_row_rejected(self):
        self.reports['Q']['per_k'][0]['states'].pop()
        with self.assertRaisesRegex(ValueError,'Incomplete'):P.kinetic_scalar_replay(self.reports)

    def test_reordered_band_ids_rejected(self):
        self.reports['A']['per_k'][0]['states'][0]['band_one_based']=2
        with self.assertRaisesRegex(ValueError,'band order'):P.kinetic_scalar_replay(self.reports)

    def test_norm_and_gram_must_have_passed(self):
        self.reports['A']['normalization_and_gram'][0]['gram_frobenius']=.001
        with self.assertRaisesRegex(ValueError,'norm/Gram'):P.kinetic_scalar_replay(self.reports)

    def test_row_norm_must_equal_published_original_norm(self):
        self.reports['B']['per_k'][0]['states'][0]['norm']=1.0000000001
        with self.assertRaises(ValueError):P.kinetic_scalar_replay(self.reports)

    def test_spin_factor_and_duplicate_spatial_weight_rejected(self):
        for kind in ('spin','weight'):
            self.setUp()
            if kind=='spin':self.reports['Q']['per_k'][0]['states'][0]['occupation']=2.
            else:self.reports['Q']['per_k'][0]['weight_spatial']*=2
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):P.kinetic_scalar_replay(self.reports)

    def test_historical_T_difference_retained_and_checked(self):
        P.kinetic_scalar_replay(self.reports)
        self.reports['A']['kinetic']['historical_ha']-=1e-5
        with self.assertRaises(ValueError):P.kinetic_scalar_replay(self.reports)

    def test_native_printed_T_false_label_rejected(self):
        self.reports['Q']['kinetic']['evidence_kind']='NATIVE_QE_PRINTED_T'
        with self.assertRaisesRegex(ValueError,'mislabelled'):P.kinetic_scalar_replay(self.reports)

    def test_nonfinite_table_cannot_pass(self):
        self.reports['A']['per_k'][0]['states'][0]['eigenvalue_ha']=float('nan')
        with self.assertRaisesRegex(ValueError,'Nonfinite'):P.kinetic_scalar_replay(self.reports)

    def test_negative_squared_T_rejected(self):
        self.reports['A']['per_k'][0]['states'][0]['kinetic_unweighted_ha']=-.01
        with self.assertRaisesRegex(ValueError,'Negative'):P.kinetic_scalar_replay(self.reports)

    def test_full_complex_nondiagonal_NL_matches_independent_small_matrix(self):
        arrays,state,nl,expected=complex_nonlocal_fixture(self.reports)
        totals=P.nonlocal_replay(arrays,state,self.reports,nl)
        for label in ('A','B','Q'):self.assertAlmostEqual(totals[label],math.fsum(expected[label]),places=13)
        self.assertGreater(np.max(abs(arrays['D']-np.diag(np.diag(arrays['D'])))),.05)
        self.assertTrue(any(abs(r['up_down_imag_ha'])>1e-5 for k in nl['states']['Q']['kpoints'] for r in k['rows']))

    def test_NL_common_phase_and_equal_occupation_unitary_invariant(self):
        a,s,nl,_=complex_nonlocal_fixture(self.reports);baseline=P.nonlocal_replay(a,s,self.reports,nl)['Q']
        u=np.array([[1,1j],[1j,1]])/math.sqrt(2)
        for kwargs in ({'phase':.731},{'unitary':u}):
            a,s,nl,_=complex_nonlocal_fixture(self.reports,**kwargs)
            self.assertAlmostEqual(P.nonlocal_replay(a,s,self.reports,nl)['Q'],baseline,places=13)

    def test_NL_missing_spin_cross_is_rejected(self):
        a,s,nl,_=complex_nonlocal_fixture(self.reports);row=nl['states']['Q']['kpoints'][0]['rows'][0]
        row['spin_sum_ha']=row['up_up_ha']+row['down_down_ha']
        with self.assertRaises(ValueError):P.nonlocal_replay(a,s,self.reports,nl)

    def test_NL_one_sided_P_row_change_rejected(self):
        a,s,nl,_=complex_nonlocal_fixture(self.reports);a['k1_P'][[0,1]]=a['k1_P'][[1,0]]
        with self.assertRaisesRegex(ValueError,'projection'):P.nonlocal_replay(a,s,self.reports,nl)

    def test_NL_stale_Q_projection_rejected(self):
        a,s,nl,_=complex_nonlocal_fixture(self.reports);a['Q_k1_down'][0,0]+=.01j
        with self.assertRaisesRegex(ValueError,'projection'):P.nonlocal_replay(a,s,self.reports,nl)

    def test_NL_missing_unoccupied_tail_is_rejected(self):
        a,s,nl,_=complex_nonlocal_fixture(self.reports);nl['states']['A']['kpoints'][0]['rows'].pop()
        with self.assertRaisesRegex(ValueError,'all24'):P.nonlocal_replay(a,s,self.reports,nl)

    def test_NL_wrong_weighted_columns_not_hidden_by_correct_global_sum(self):
        for field in ('action','projected','spin_sum'):
            a,s,nl,_=complex_nonlocal_fixture(self.reports)
            nl['states']['B']['kpoints'][0]['rows'][0]['weighted_'+field+'_ha']+=.01
            with self.subTest(field=field):
                with self.assertRaises(ValueError):P.nonlocal_replay(a,s,self.reports,nl)

    def test_NL_global_projection_or_spin_total_mismatch_rejected(self):
        for field in ('projected','spin_sum'):
            a,s,nl,_=complex_nonlocal_fixture(self.reports);nl['states']['Q']['energy_'+field+'_ha']+=.01
            with self.subTest(field=field):
                with self.assertRaises(ValueError):P.nonlocal_replay(a,s,self.reports,nl)


if __name__=='__main__':unittest.main()
