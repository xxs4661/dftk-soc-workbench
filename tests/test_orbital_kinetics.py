"""Synthetic finite Fourier states only: no original orbitals, UPF or solver."""
import copy
import importlib.util
import itertools
import math
from pathlib import Path
import unittest

import numpy as np

SPEC=importlib.util.spec_from_file_location('orbital_audit',Path(__file__).resolve().parents[1]/'scripts/audit_orbital_kinetics.py')
audit=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(audit)
TOL=audit.DEFAULT_THRESHOLDS.copy()
PROBES=[[0,0,0],[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1],
        [1,1,0],[-1,-1,0],[1,0,1],[-1,0,-1],[0,1,1],[0,-1,-1],
        [1,-1,1],[-1,1,-1],[2,0,0],[-2,0,0]]


def reciprocal_by_cross_products(a):
    volume=float(np.dot(a[:,0],np.cross(a[:,1],a[:,2])))
    b=np.column_stack([2*math.pi*np.cross(a[:,1],a[:,2])/volume,
                       2*math.pi*np.cross(a[:,2],a[:,0])/volume,
                       2*math.pi*np.cross(a[:,0],a[:,1])/volume])
    return volume,b


def fixture(label='A'):
    a=np.array([[7.,1.,0.],[0.,8.,1.3],[.6,0.,9.]])
    volume,b=reciprocal_by_cross_products(a)
    physical={'lattice_vectors_bohr':a.T.tolist(),'fft_size':[8,8,8],'n_states':2,
              'kpoints':[[.17,-.13,.19],[-.21,.08,.11]],'kweights':[.3,.7],
              'ecut_ha':6.,'expected_electrons':.79,'direct_fourier_miller_points':PROBES}
    spin=np.array([1.,1j],np.complex128)/math.sqrt(2)
    first=np.array([[1.,1.],[np.exp(.37j),-np.exp(.37j)]],np.complex128)/math.sqrt(2)
    second=np.array([[1.,0.],[0.,1/math.sqrt(2)],[0.,np.exp(-.61j)/math.sqrt(2)]],np.complex128)
    points=[]
    for i,(m,phi,f) in enumerate([
        ([[0,0,0],[1,1,0]],first,[.8,.2]),
        ([[1,0,0],[0,1,1],[-1,0,0]],second,[.1,.6])]):
        points.append({'millers':np.array(m,np.int64),'coefficients':spin[:,None,None]*phi[None,:,:],
                       'occupations':np.array(f,np.float64),'eigenvalues':np.array([-.8,.4],np.float64),
                       'weight':float(physical['kweights'][i]),'k_cart':b@physical['kpoints'][i]})
    return {'label':label,'lattice_columns':a,'reciprocal_columns':b,'kpoints':points},physical


def analytic_reference(state,physical):
    """Direct finite exponentials and trapezoidal trigonometric quadrature; no FFT.

    The grid resolves every fixture product strictly below Nyquist. Reciprocal
    columns are formed by cross products, independent of production geometry.
    """
    size=physical['fft_size'];volume,b=reciprocal_by_cross_products(state['lattice_columns'])
    coords=np.array([(i/size[0],j/size[1],k/size[2]) for k in range(size[2])
                     for j in range(size[1]) for i in range(size[0])])
    density=np.zeros(len(coords));pauli=np.zeros((3,len(coords)));kinetic_terms=[]
    for ik,p in enumerate(state['kpoints']):
        phases=np.exp(2j*math.pi*(coords@p['millers'].T))
        for n,f in enumerate(p['occupations']):
            u=np.column_stack([phases@p['coefficients'][s,:,n] for s in range(2)])/math.sqrt(volume)
            weight=float(p['weight'])*float(f);cross=u[:,0]*u[:,1].conjugate()
            density+=weight*(abs(u[:,0])**2+abs(u[:,1])**2)
            pauli+=weight*np.vstack((2*cross.real,-2*cross.imag,abs(u[:,0])**2-abs(u[:,1])**2))
            for ig,m in enumerate(p['millers']):
                q=sum((b[:,j]*(int(m[j])+physical['kpoints'][ik][j]) for j in range(3)),np.zeros(3))
                for s in range(2):kinetic_terms.append(weight*.5*float(np.dot(q,q))*abs(p['coefficients'][s,ig,n])**2)
    modes=list(itertools.product(*(range(-(n//2),n-n//2) for n in size)))
    # Direct real-space trigonometric quadrature. No production FFT/correlation.
    values=np.exp(-2j*math.pi*(np.array(modes)@coords.T))@density/len(coords)
    coefficients=dict(zip(modes,map(complex,values)))
    return {'density_real':density,'density_coefficients':coefficients,'kinetic_ha':math.fsum(kinetic_terms)},pauli


class OrbitalKineticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base,cls.physical=fixture();cls.reference,cls.pauli=analytic_reference(cls.base,cls.physical)

    def setUp(self):
        self.state=copy.deepcopy(self.base);self.p=copy.deepcopy(self.physical)
        self.reference=copy.deepcopy(type(self).reference)

    def evaluate(self,reference=None):
        return audit.evaluate_orbitals(self.state,self.p,TOL,reference or self.reference)

    def test_finite_complex_sheared_two_k_analytic_density_and_T(self):
        result=self.evaluate();report=result['report']
        self.assertEqual(report['status'],'PASS')
        self.assertLess(np.max(abs(result['density_real']-self.reference['density_real'])),1e-14)
        self.assertLess(np.max(abs(result['pauli_density']-self.pauli)),1e-14)
        self.assertAlmostEqual(report['kinetic']['direct_ha'],self.reference['kinetic_ha'],places=13)
        self.assertAlmostEqual(report['kinetic']['gradient_ha'],self.reference['kinetic_ha'],places=13)
        self.assertEqual([x['NG'] for x in report['per_k']],[2,3])
        self.assertEqual(len(report['direct_correlation_checks']),17)
        self.assertTrue(all(x['status']=='PASS' for x in report['direct_correlation_checks']))

    def test_plane_wave_closed_form_k_geometry_and_sigma_y(self):
        a=np.array([[6.,2.,0.],[0.,8.,0.],[0.,0.,10.]])
        b=np.array([[math.pi/3,0.,0.],[-math.pi/12,math.pi/4,0.],[0.,0.,math.pi/5]])
        c=np.array([math.sqrt(.3),1j*math.sqrt(.7)],np.complex128).reshape(2,1,1)
        self.p.update(lattice_vectors_bohr=a.T.tolist(),n_states=1,kpoints=[[.2,-.3,.4]],kweights=[1.],expected_electrons=1.)
        self.state={'label':'Q','lattice_columns':a,'reciprocal_columns':b,'kpoints':[{
            'millers':np.array([[1,1,0]],np.int64),'coefficients':c,'occupations':np.array([1.]),
            'eigenvalues':np.array([.7]),'weight':1.,'k_cart':b@np.array([.2,-.3,.4])}]}
        ref={'density_coefficients':{m:complex(1/480 if m==(0,0,0) else 0) for m in self.reference['density_coefficients']}}
        result=self.evaluate(ref)
        self.assertEqual(result['report']['status'],'PASS')
        self.assertAlmostEqual(result['report']['kinetic']['direct_ha'],.0860125*math.pi**2,places=13)
        self.assertLess(max(abs(result['density_real']-1/480)),1e-15)
        self.assertLess(max(abs(result['pauli_density'][1]-2*math.sqrt(.21)/480)),1e-15)
        self.assertLess(max(abs(result['pauli_density'][2]+.4/480)),1e-15)
        self.assertTrue(result['report']['same_source_orbital_density']['zero_reference_denominator'])

    def test_explicit_block_to_interleaved_preserves_complex_phase(self):
        c=np.array([[[1+2j,3-4j],[5+6j,7-8j]],[[9-10j,11+12j],[13-14j,15+16j]]],np.complex128)
        expected=np.array([[1+2j,3-4j],[9-10j,11+12j],[5+6j,7-8j],[13-14j,15+16j]],np.complex128)
        original=c.tobytes();out=audit.block_to_interleaved(c)
        self.assertEqual(out.tobytes(),expected.tobytes());self.assertEqual(c.tobytes(),original)
        self.assertFalse(np.shares_memory(c,out))

    def test_relative_spin_phase_changes_pauli_even_when_density_T_same(self):
        original=self.evaluate();self.state['kpoints'][0]['coefficients'][1]*=-1
        changed=self.evaluate()
        self.assertEqual(changed['report']['status'],'PASS')
        self.assertLess(np.max(abs(changed['density_real']-original['density_real'])),1e-14)
        self.assertGreater(np.max(abs(changed['pauli_density'][1]-original['pauli_density'][1])),1e-4)
        self.assertAlmostEqual(changed['report']['kinetic']['direct_ha'],original['report']['kinetic']['direct_ha'],places=13)

    def test_nonzero_k_support_need_not_contain_zero_or_negative_closure(self):
        self.assertNotIn([0,0,0],self.state['kpoints'][1]['millers'].tolist())
        self.assertNotIn([0,-1,-1],self.state['kpoints'][1]['millers'].tolist())
        self.assertEqual(self.evaluate()['report']['status'],'PASS')

    def test_different_k_occupations_spatial_weights_once(self):
        electrons=self.evaluate()['report']['electrons']
        self.assertAlmostEqual(electrons['from_occupations'],.3*1+.7*.7,places=14)
        np.testing.assert_allclose(electrons['per_k_real_contributions'],[.3,.49],atol=1e-14,rtol=0)
        self.assertNotAlmostEqual(electrons['from_real_density'],.3**2*1+.7**2*.7,places=6)

    def test_double_weights_are_rejected(self):
        self.state['kpoints'][0]['weight']*=2
        with self.assertRaisesRegex(audit.OrbitalAuditError,'weight'):self.evaluate()

    def test_spin_capacity_two_is_rejected(self):
        self.state['kpoints'][0]['occupations']*=2
        with self.assertRaisesRegex(audit.OrbitalAuditError,'capacity'):self.evaluate()

    def test_weight_applied_to_occupations_twice_fails_electrons(self):
        for p in self.state['kpoints']:p['occupations']*=p['weight']
        self.assertEqual(self.evaluate()['report']['electrons']['status'],'FAIL')

    def test_wrong_electron_target_does_not_renormalize(self):
        self.p['expected_electrons']=1.1
        r=self.evaluate()['report'];self.assertEqual(r['status'],'FAIL')
        self.assertAlmostEqual(r['electrons']['from_occupations'],.79,places=14)

    def test_omit_k_rejected_from_bound_geometry(self):
        self.state['kpoints'][0]['k_cart'][:]=0
        with self.assertRaisesRegex(audit.OrbitalAuditError,'k Cartesian'):self.evaluate()

    def test_extra_twopi_rejected_from_duality(self):
        self.state['reciprocal_columns']*=2*math.pi
        with self.assertRaisesRegex(audit.OrbitalAuditError,'Reciprocal'):self.evaluate()

    def test_row_column_transpose_rejected_on_sheared_cell(self):
        self.state['reciprocal_columns']=self.state['reciprocal_columns'].T.copy()
        with self.assertRaisesRegex(audit.OrbitalAuditError,'Reciprocal'):self.evaluate()

    def test_wrong_cutoff_not_silently_filtered(self):
        self.p['ecut_ha']=.01
        with self.assertRaisesRegex(audit.OrbitalAuditError,'cutoff'):self.evaluate()

    def test_joint_miller_coefficient_permutation_invariant(self):
        p=self.state['kpoints'][1];perm=[2,0,1]
        p['millers']=p['millers'][perm];p['coefficients']=p['coefficients'][:,perm,:]
        self.assertEqual(self.evaluate()['report']['status'],'PASS')

    def test_millers_only_permutation_fails_same_source_density(self):
        p=self.state['kpoints'][1];p['millers']=p['millers'][[2,0,1]]
        self.assertEqual(self.evaluate()['report']['same_source_orbital_density']['status'],'FAIL')

    def test_coefficients_only_permutation_fails_same_source_density(self):
        p=self.state['kpoints'][1];p['coefficients']=p['coefficients'][:,[2,0,1],:]
        self.assertEqual(self.evaluate()['report']['same_source_orbital_density']['status'],'FAIL')

    def test_same_dimension_cross_k_swap_is_not_accepted(self):
        # Two same-sized k blocks with different finite superpositions. Keep
        # each original k/occupation slot; swapping c alone changes its density.
        p0=self.state['kpoints'][0];p1=self.state['kpoints'][1]
        p0['millers']=p1['millers'].copy()
        p0['coefficients']=np.zeros_like(p1['coefficients'])
        p0['coefficients'][:,0,:]=np.array([[1,0],[0,1]],np.complex128)
        reference,_=analytic_reference(self.state,self.p)
        p0['coefficients'],p1['coefficients']=p1['coefficients'].copy(),p0['coefficients'].copy()
        self.assertEqual(self.evaluate(reference)['report']['status'],'FAIL')

    def test_k_record_swap_rejected(self):
        self.state['kpoints']=self.state['kpoints'][::-1]
        with self.assertRaisesRegex(audit.OrbitalAuditError,'k Cartesian'):self.evaluate()

    def test_common_orbital_phases_invariant(self):
        for p in self.state['kpoints']:p['coefficients']*=np.array([np.exp(.73j),np.exp(-.28j)])[None,None,:]
        self.assertEqual(self.evaluate()['report']['status'],'PASS')

    def test_equal_occupation_unitary_invariance(self):
        for p in self.state['kpoints']:p['occupations'][:]=.4
        self.p['expected_electrons']=.8;reference,_=analytic_reference(self.state,self.p)
        unitary=np.array([[1,1j],[1j,1]],np.complex128)/math.sqrt(2)
        for p in self.state['kpoints']:p['coefficients']=p['coefficients']@unitary
        self.assertEqual(self.evaluate(reference)['report']['status'],'PASS')

    def test_unequal_occupation_unitary_not_a_density_invariant(self):
        unitary=np.array([[1,1j],[1j,1]],np.complex128)/math.sqrt(2)
        for p in self.state['kpoints']:p['coefficients']=p['coefficients']@unitary
        self.assertEqual(self.evaluate()['report']['same_source_orbital_density']['status'],'FAIL')

    def test_norm_failure_preserved_without_QR_or_mutation(self):
        self.state['kpoints'][0]['coefficients']*=1.001
        original=[p['coefficients'].tobytes() for p in self.state['kpoints']]
        r=self.evaluate()['report']
        self.assertEqual(r['status'],'FAIL');self.assertEqual(r['normalization_and_gram'][0]['status'],'FAIL')
        self.assertFalse(r['normalization_or_QR_applied']);self.assertTrue(r['input_bytes_unchanged'])
        self.assertEqual([p['coefficients'].tobytes() for p in self.state['kpoints']],original)

    def test_gram_failure_with_each_norm_one(self):
        p=self.state['kpoints'][0];p['coefficients'][:,:,1]=p['coefficients'][:,:,0]
        r=self.evaluate()['report']['normalization_and_gram'][0]
        self.assertLess(r['maximum_norm_error'],1e-12);self.assertGreater(r['gram_frobenius'],1.)
        self.assertEqual(r['status'],'FAIL')

    def test_nan_coefficient_is_rejected(self):
        self.state['kpoints'][0]['coefficients'][0,0,0]=complex(float('nan'),0)
        with self.assertRaisesRegex(audit.OrbitalAuditError,'Nonfinite'):self.evaluate()

    def test_int64_min_miller_cannot_bypass_index_bound(self):
        self.state['kpoints'][0]['millers'][0,0]=np.iinfo(np.int64).min
        with self.assertRaisesRegex(audit.OrbitalAuditError,'Unbounded'):self.evaluate()

    def test_overflowing_finite_coefficients_cannot_publish_nonfinite_report(self):
        self.state['kpoints'][0]['coefficients']*=1e200
        with np.errstate(over='ignore',invalid='ignore'):
            with self.assertRaisesRegex(audit.OrbitalAuditError,'Nonfinite derived'):self.evaluate()

    def test_nonfinite_reference_energy_is_rejected(self):
        self.reference['kinetic_ha']=float('nan')
        with self.assertRaisesRegex(audit.OrbitalAuditError,'Nonfinite historical'):self.evaluate()

    def test_duplicate_miller_is_rejected(self):
        self.state['kpoints'][0]['millers'][1]=self.state['kpoints'][0]['millers'][0]
        with self.assertRaisesRegex(audit.OrbitalAuditError,'Duplicate'):self.evaluate()

    def test_float_miller_and_complex64_are_rejected(self):
        self.state['kpoints'][0]['millers']=self.state['kpoints'][0]['millers'].astype(float)
        with self.assertRaisesRegex(audit.OrbitalAuditError,'Miller'):self.evaluate()
        self.state=copy.deepcopy(self.base)
        self.state['kpoints'][0]['coefficients']=self.state['kpoints'][0]['coefficients'].astype('complex64')
        with self.assertRaisesRegex(audit.OrbitalAuditError,'dtype'):self.evaluate()

    def test_nyquist_product_is_explicitly_unsupported(self):
        with self.assertRaises(audit.OrbitalAuditError) as caught:
            audit.product_support([np.array([[0,0,0],[4,0,0]],np.int64)],[8,8,8])
        self.assertEqual(caught.exception.status,'UNSUPPORTED_PRODUCT_GRID')

    def test_product_support_full_and_projected_scopes_are_distinct(self):
        self.state['label']='Q';result=self.evaluate()
        self.assertEqual(result['report']['same_source_orbital_density']['scope'],'FULL_FINITE_PRODUCT_SUPPORT_WITHIN_SAVED_G')
        ref=copy.deepcopy(self.reference);del ref['density_coefficients'][(1,1,0)]
        result=self.evaluate(ref);r=result['report']['same_source_orbital_density']
        self.assertEqual(r['status'],'PASS');self.assertEqual(r['scope'],'PROJECTED_ON_SAVED_DENSITY_G')
        self.assertGreater(r['possible_products_outside_saved_count'],0)
        self.assertGreater(r['outside_saved_coefficient_max_abs'],1e-5)
        self.assertFalse(r['unknown_physical_modes_assumed_zero'])

    def test_missing_zero_reference_is_rejected(self):
        del self.reference['density_coefficients'][(0,0,0)]
        with self.assertRaisesRegex(audit.OrbitalAuditError,'Missing'):self.evaluate()

    def test_bad_reference_density_cannot_pass(self):
        self.state['label']='Q';self.reference['density_coefficients'][(1,1,0)]+=.001j
        self.assertEqual(self.evaluate()['report']['same_source_orbital_density']['status'],'FAIL')

    def test_historical_T_is_check_only_never_assigned(self):
        expected=self.reference['kinetic_ha'];self.reference['kinetic_ha']+=1e-5
        r=self.evaluate()['report'];self.assertEqual(r['kinetic']['same_source_status'],'FAIL')
        self.assertAlmostEqual(r['kinetic']['direct_ha'],expected,places=13);self.assertEqual(r['status'],'FAIL')

    def test_eband_bookkeeping_preserves_scope_and_intervals(self):
        value=sum(p['weight']*sum(p['occupations']*p['eigenvalues']) for p in self.state['kpoints'])
        self.reference.update(eband_ha=value+2e-10,eband_print_halfwidth_ha=3e-10)
        r=self.evaluate()['report'];self.assertEqual(r['eband_bookkeeping']['status'],'PASS')
        self.assertIn('not a Hamiltonian residual',r['eband_bookkeeping']['scope'])
        self.assertEqual(r['qe_original_input_hamiltonian_residual_status'],'NOT_AVAILABLE')
        self.reference['eband_ha']+=1e-6
        self.assertEqual(self.evaluate()['report']['status'],'FAIL')

    def test_zero_occupation_band_is_retained(self):
        self.state['kpoints'][0]['occupations'][1]=0.;self.p['expected_electrons']-=.06
        ref,_=analytic_reference(self.state,self.p)
        rows=self.evaluate(ref)['report']['per_k'][0]['states']
        self.assertEqual(len(rows),2);self.assertEqual(rows[1]['occupation'],0.)
        self.assertEqual(rows[1]['kinetic_weighted_ha'],0.);self.assertGreater(rows[1]['kinetic_unweighted_ha'],0.)


if __name__=='__main__':unittest.main()
