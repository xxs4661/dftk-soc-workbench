"""Synthetic periodic densities only: no Mg arrays, SCF, eigensolve or QE calls.

Analytic references use n(s)=n0+a*cos(2*pi*m.s+phi)+b*sin(2*pi*t.s).
For one cosine pair, EH=pi*Omega*a^2/|q_m|^2. Direct sums below use
explicit fractional points and hand-written coefficients, not an FFT/IFFT
round trip. Algebra tolerances are abs 1e-12 and rel 1e-11 unless a stricter
fixed production engineering gate is tested. Coefficient file round trips
compare IEEE Float64 bytes, including signed zero.
"""
import cmath
import csv
import gzip
import importlib.util
import io
import itertools
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("density_hartree", Path(__file__).resolve().parents[1]/"scripts/compare_density_hartree.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
ZERO = (0, 0, 0)


def negate(m):
    return tuple(-x for x in m)


def sparse_pair(n0=0.01, amplitude=0.001, phase=0.37, mode=(1, 2, -1)):
    positive = amplitude/2*complex(math.cos(phase), math.sin(phase))
    return {ZERO: complex(n0), mode: positive, negate(mode): positive.conjugate()}


def grid_modes(size):
    axes = [list(range((n-1)//2+1))+list(range(-n//2, 0)) for n in size]
    return list(itertools.product(*axes))


def full_grid(sparse, size):
    # Synthetic fixture deliberately declares every present zero mode.
    return {m: sparse.get(m, 0j) for m in grid_modes(size)}


def direct_coefficient(density, mode, size):
    # Explicit column-major real-space iteration, independent analytic reference.
    terms = []
    for iz in range(size[2]):
        for iy in range(size[1]):
            for ix in range(size[0]):
                s = (ix/size[0], iy/size[1], iz/size[2])
                phase = -2*math.pi*sum(m*x for m, x in zip(mode, s))
                terms.append(density(s)*complex(math.cos(phase), math.sin(phase)))
    return complex(math.fsum(z.real for z in terms), math.fsum(z.imag for z in terms))/math.prod(size)


def compressed_csv(text):
    return gzip.compress(text.encode(), mtime=0)


class GeometryAndAnalyticTests(unittest.TestCase):
    def setUp(self):
        self.geometry = M.reciprocal_geometry([[10, 0, 0], [0, 10, 0], [0, 0, 10]])
        self.size = (8, 8, 8)

    def test_noncubic_nondiagonal_lattice_columns(self):
        direct = [[2, 0, 0], [1, 3, 0], [.5, .25, 4]]
        geom = M.reciprocal_geometry(direct)
        self.assertEqual(geom['volume_bohr3'], 24)
        # Solve A^T b=2*pi e by hand for this triangular cell.
        expected = [[math.pi, -math.pi/3, -5*math.pi/48], [0, 2*math.pi/3, -math.pi/24], [0, 0, math.pi/2]]
        for actual, reference in zip(geom['reciprocal_vectors_bohr_inv'], expected):
            for x, y in zip(actual, reference):
                self.assertAlmostEqual(x, y, delta=1e-14)
        q = M.q_cartesian((1, 2, -1), geom)
        self.assertAlmostEqual(q[0], math.pi, delta=1e-14)
        self.assertAlmostEqual(q[1], math.pi, delta=1e-14)
        self.assertAlmostEqual(q[2], -11*math.pi/16, delta=1e-14)
        # A matrix-row interpretation would produce a different q, detectably.
        transposed = list(map(list, zip(*direct)))
        wrong = M.q_cartesian((1, 2, -1), M.reciprocal_geometry(transposed))
        self.assertGreater(math.dist(q, wrong), .1)

    def test_left_handed_cell_volume_and_reciprocal(self):
        geom = M.reciprocal_geometry([[0, 3, 0], [2, 0, 0], [0, 0, 4]])
        self.assertEqual(geom['volume_bohr3'], 24)
        self.assertEqual(geom['signed_determinant_bohr3'], -24)
        self.assertLess(geom['reciprocal_identity_max_abs'], 1e-15)

    def test_invalid_cell_rejected(self):
        for a in [[[1,0,0],[2,0,0],[0,0,1]], [[math.nan,0,0],[0,1,0],[0,0,1]]]:
            with self.assertRaises(ValueError):M.reciprocal_geometry(a)

    def test_nonaxis_complex_phase_and_analytic_hartree(self):
        m=(1,2,-1); phi=.37; a=.001; n0=.01; c=sparse_pair(n0,a,phi,m)
        def density(s):
            return n0+a*math.cos(2*math.pi*sum(x*y for x,y in zip(m,s))+phi)
        for mode in [ZERO,m,negate(m),(2,-1,1),(-2,1,-1)]:
            actual=direct_coefficient(density,mode,self.size)
            self.assertAlmostEqual(actual,c.get(mode,0j),delta=1e-16)
        self.assertGreater(abs(c[m].imag),1e-4)
        q2=(2*math.pi/10)**2*6
        expected=math.pi*1000*a*a/q2
        self.assertAlmostEqual(M.hartree_energy(c,self.geometry),expected,delta=1e-15)
        v=M.hartree_potential(c,self.geometry)
        self.assertEqual(v[ZERO],0j)
        self.assertAlmostEqual(v[m],4*math.pi*c[m]/q2,delta=1e-17)
        report=M.dataset_report(c,self.geometry,self.size,expected_electrons=10,historical_hartree_ha=expected)
        self.assertEqual(report['engineering_status'],'PASS')

    def test_sine_sign_volume_and_grid_count_independent(self):
        m=(1,-2,1); b=.002; n0=.02; size=(8,10,12)
        def density(s):return n0+b*math.sin(2*math.pi*sum(x*y for x,y in zip(m,s)))
        self.assertAlmostEqual(direct_coefficient(density,m,size),-0.001j,delta=2e-17)
        self.assertAlmostEqual(direct_coefficient(density,negate(m),size),0.001j,delta=2e-17)
        self.assertAlmostEqual(direct_coefficient(density,ZERO,size),n0,delta=2e-17)
        # Raw, unnormalized sum or reversed Fourier sign cannot satisfy these.
        self.assertGreater(abs(direct_coefficient(density,m,size)*math.prod(size)+.001j),.1)
        self.assertGreater(abs(direct_coefficient(density,negate(m),size)+.001j),.001)

    def test_orthonormal_conversion_is_sqrt_volume_once(self):
        nbar=sparse_pair(); c={m:z*math.sqrt(1000) for m,z in nbar.items()}
        recovered=M.orthonormal_to_nbar(c,1000)
        for m in nbar:self.assertAlmostEqual(recovered[m],nbar[m],delta=2e-18)
        bad=M.dataset_report(c,self.geometry,self.size)
        self.assertEqual(bad['electron_count_status'],'FAIL')
        self.assertEqual(M.dataset_report(recovered,self.geometry,self.size)['electron_count_status'],'PASS')

    def test_extra_spin_kweight_and_density_unit_factors_fail_electrons(self):
        c=sparse_pair()
        for factor in [2,1/3,1/2,math.sqrt(1000)]:
            with self.subTest(factor=factor):
                bad=M.dataset_report({m:z*factor for m,z in c.items()},self.geometry,self.size)
                self.assertEqual(bad['electron_count_status'],'FAIL')
                self.assertEqual(bad['engineering_status'],'FAIL')

    def test_hartree_ha_ry_double_factor_fails_self_identity(self):
        c=sparse_pair(); expected=math.pi*1000*.001**2/((2*math.pi/10)**2*6)
        report=M.dataset_report(c,self.geometry,self.size,historical_hartree_ha=2*expected)
        self.assertEqual(report['self_hartree_reconstruction_status'],'FAIL')
        self.assertGreater(abs(report['self_hartree_difference_ha']),1e-5)

    def test_translation_changes_complex_density_preserves_energy(self):
        c=sparse_pair(); shift=(.17,.23,.31)
        translated={m:z*cmath.exp(-2j*math.pi*sum(i*s for i,s in zip(m,shift))) for m,z in c.items()}
        self.assertAlmostEqual(M.hartree_energy(c,self.geometry),M.hartree_energy(translated,self.geometry),delta=1e-15)
        result=M.compare_coefficients(c,translated,self.geometry,self.size,self.size)
        self.assertGreater(result['density']['projected_l2'],.01)
        self.assertGreater(result['density']['maximum']['abs_difference'],1e-4)
        self.assertAlmostEqual(result['hartree_decomposition']['native_difference_ha'],0,delta=1e-15)


class SupportAndDecompositionTests(unittest.TestCase):
    def setUp(self):
        self.g=M.reciprocal_geometry([[10,0,0],[0,10,0],[0,0,10]])
        self.size=(8,8,8);self.c=sparse_pair()

    def test_missing_zero_nonfinite_and_G_plus_k_rejected(self):
        with self.assertRaises(ValueError):M.validate_coefficients({(1,0,0):1j})
        with self.assertRaises(ValueError):M.validate_coefficients({ZERO:math.nan})
        with self.assertRaises(ValueError):M.validate_coefficients({ZERO:.01,(1.125,0,0):.01j})
        with self.assertRaises(ValueError):M.validate_coefficients({ZERO:.01,(True,0,0):.01j})

    def test_zero_imaginary_charge_gate(self):
        bad=dict(self.c);bad[ZERO]=complex(.01,1e-9)
        report=M.dataset_report(bad,self.g,self.size)
        self.assertEqual(report['zero_imaginary_status'],'FAIL')
        self.assertEqual(report['electron_count_status'],'PASS')

    def test_missing_mode_is_distinct_from_present_zero(self):
        r=dict(self.c); l=dict(r);l[(2,0,0)]=0j;l[(-2,0,0)]=0j
        d=M.compare_coefficients(l,r,self.g,self.size,self.size)
        self.assertEqual(d['left_exclusive_nonzero_count'],2)
        self.assertEqual(d['density']['projected_l2'],0)
        self.assertEqual(d['full_cross_code_realspace_density_status'],'NOT_ASSESSED')
        self.assertEqual(d['hartree_decomposition']['left_exclusive_ha'],0)

    def test_support_holes_fail_complete_grid_gate(self):
        report=M.dataset_report(self.c,self.g,self.size,require_complete_fft=True)
        self.assertEqual(report['reciprocal_support_status'],'FAIL')
        report=M.dataset_report(full_grid(self.c,self.size),self.g,self.size,require_complete_fft=True)
        self.assertEqual(report['reciprocal_support_status'],'PASS')

    def test_joint_permutation_invariant_one_sided_permutation_detected(self):
        c=dict(self.c);c[(2,1,1)]=.002+.003j;c[(-2,-1,-1)]=.002-.003j
        reversed_items=dict(reversed(list(c.items())))
        same=M.compare_coefficients(c,reversed_items,self.g,self.size,self.size)
        self.assertEqual(same['density']['projected_l2'],0)
        values=list(c.values());wrong=dict(zip(c,values[:1]+values[2:]+values[1:2]))
        diff=M.compare_coefficients(c,wrong,self.g,self.size,self.size)
        self.assertGreater(diff['density']['projected_l2'],.01)
        self.assertEqual(M.dataset_report(wrong,self.g,self.size)['discrete_conjugacy_status'],'FAIL')

    def test_nyquist_native_retained_and_modular_distinguished(self):
        size=(4,4,4);c={ZERO:.01+0j,(-2,1,0):.002+.003j,(-2,-1,0):.002-.003j,(-2,0,0):.004+0j}
        report=M.dataset_report(c,self.g,size)
        self.assertEqual(report['modular_conjugacy']['status'],'PASS')
        self.assertEqual(report['strict_conjugacy']['missing_partner_count'],3)
        self.assertGreater(report['native_hartree_ha'],0)
        d=M.compare_coefficients(c,c,self.g,size,size)
        self.assertEqual(d['common_nonzero_count'],0)
        self.assertEqual(d['nyquist_ambiguous_common_count'],3)
        self.assertEqual(d['left_exclusive_nonzero_count'],3)
        self.assertEqual(d['hartree_decomposition']['left_exclusive_ha'],report['native_hartree_ha'])
        # Adding the opposite Nyquist representative is illegal double counting.
        bad=dict(c);bad[(2,0,0)]=.004+0j
        with self.assertRaises(ValueError):M.dataset_report(bad,self.g,size)

    def test_primary_common_requires_strict_negative_closure(self):
        c={ZERO:.01+0j,(1,0,0):.002+.003j}
        d=M.compare_coefficients(c,c,self.g,self.size,self.size)
        self.assertEqual(d['reciprocal_support_status'],'FAIL')
        self.assertEqual(d['common_G_density_comparison_status'],'UNRESOLVED')
        with self.assertRaises(ValueError):list(M.iter_common_differences(c,c,self.g,self.size,self.size))

    def test_nonzero_denominator_does_not_use_mean_or_floor(self):
        r={ZERO:.01+0j,(1,0,0):1e-15+0j,(-1,0,0):1e-15+0j};l={m:(z if m==ZERO else 2*z) for m,z in r.items()}
        d=M.compare_coefficients(l,r,self.g,self.size,self.size)
        self.assertAlmostEqual(d['density']['relative_l2'],1,delta=1e-15)
        zero={m:(z if m==ZERO else 0j) for m,z in r.items()}
        d=M.compare_coefficients(l,zero,self.g,self.size,self.size)
        self.assertIsNone(d['density']['relative_l2'])
        self.assertEqual(d['density']['relative_l2_status'],'NOT_APPLICABLE_ZERO_REFERENCE_FLUCTUATION')
        self.assertGreater(d['density']['projected_l2'],0)

    def test_full_native_support_and_nonzero_cross_term_decomposition(self):
        right={ZERO:.01+0j,(1,0,0):.001+.002j,(-1,0,0):.001-.002j,(0,2,0):.002+0j,(0,-2,0):.002+0j}
        left={ZERO:.01+0j,(1,0,0):.003+.004j,(-1,0,0):.003-.004j,(0,0,3):.001j,(0,0,-3):-.001j}
        d=M.compare_coefficients(left,right,self.g,self.size,self.size);e=d['hartree_decomposition']
        commonq2=(2*math.pi/10)**2;factor=2*math.pi*1000/commonq2
        expected_cross=factor*2*(2*((.001-.002j)*(.002+.002j)).real)
        expected_quadratic=factor*2*abs(.002+.002j)**2
        self.assertAlmostEqual(e['common_linear_cross_term_ha'],expected_cross,delta=1e-15)
        self.assertAlmostEqual(e['common_nonnegative_quadratic_ha'],expected_quadratic,delta=1e-15)
        self.assertGreater(abs(e['common_difference_ha']-expected_quadratic),.1)
        self.assertAlmostEqual(e['native_difference_ha'],e['common_difference_ha']+e['left_exclusive_ha']-e['right_exclusive_ha'],delta=1e-15)
        self.assertEqual(e['support_decomposition_status'],'PASS');self.assertEqual(e['cross_decomposition_status'],'PASS')
        self.assertEqual(e['shell_sum_status'],'PASS');self.assertEqual(len(d['shells']),6)
        self.assertEqual(sum(s['common_count'] for s in d['shells']),2)
        self.assertEqual(sum(s['left_exclusive_count'] for s in d['shells']),2)
        self.assertEqual(sum(s['right_exclusive_count'] for s in d['shells']),2)

    def test_fixed_shell_boundaries_all_six_retained(self):
        # b1=sqrt(2), so q^2/2=|m|^2. Cases sit exactly on 1,5 and 30.
        length=2*math.pi/math.sqrt(2);g=M.reciprocal_geometry([[length,0,0],[0,length,0],[0,0,length]])
        modes=[(1,0,0),(1,2,0),(2,2,2),(1,2,5),(1,2,6),(9,0,0)]
        c={ZERO:10/g['volume_bohr3']+0j}
        for m in modes:c[m]=1e-6+0j;c[negate(m)]=1e-6+0j
        d=M.compare_coefficients(c,c,g,(24,24,24),(24,24,24))
        self.assertEqual(len(d['shells']),6)
        self.assertEqual(sum(r['common_count'] for r in d['shells']),12)
        self.assertTrue(all(r['common_count']>0 for r in d['shells']))
        self.assertEqual(d['shells'][-1]['upper_inclusive_ha'],None)

    def test_maximum_keeps_complex_values_position_and_potential_units(self):
        r=self.c;l={m:(z if m==ZERO else z+.0002j*(1 if m==(1,2,-1) else -1)) for m,z in r.items()}
        d=M.compare_coefficients(l,r,self.g,self.size,self.size)
        maxr=d['density']['maximum'];self.assertEqual(maxr['m'],[-1,-2,1]);self.assertAlmostEqual(abs(maxr['difference_imag']),.0002,delta=1e-18)
        self.assertAlmostEqual(d['density']['projected_l2'],math.sqrt(1000*2)*.0002,delta=1e-16)
        factor=4*math.pi/((2*math.pi/10)**2*6)
        self.assertAlmostEqual(d['hartree_potential']['projected_l2'],factor*d['density']['projected_l2'],delta=1e-16)
        rows=list(M.iter_common_differences(l,r,self.g,self.size,self.size));self.assertEqual(len(rows),2)
        for row in rows:self.assertAlmostEqual(complex(*row['delta_vh_ha']),complex(*row['delta_nbar'])*factor,delta=1e-17)

    def test_native_closure_keeps_nyquist_and_zero_modes(self):
        left=full_grid({ZERO:.01+0j,(-4,0,0):.001+0j},self.size)
        right=full_grid({ZERO:.01+0j,(-4,0,0):.0011+0j},self.size)
        d=M.compare_coefficients(left,right,self.g,self.size,self.size)
        self.assertEqual(d['density']['projected_l2'],0)
        native=d['identical_native_support_density_difference']
        self.assertAlmostEqual(native['density_l2_including_zero'],math.sqrt(1000)*.0001,delta=1e-17)
        self.assertEqual(native['mode_count_including_zero'],512)

    def test_missing_B_does_not_erase_A_QE_report(self):
        a=full_grid(self.c,self.size)
        d=M.analyze_density_hartree({'A_out':a,'QE':self.c},[[10,0,0],[0,10,0],[0,0,10]],{'A_out':self.size,'QE':self.size})
        self.assertEqual(d['comparisons']['A_out_minus_QE']['common_G_density_comparison_status'],'MEASURED')
        self.assertEqual(d['comparisons']['B_out_minus_QE']['common_G_density_comparison_status'],'BLOCKED_MISSING_SOURCE')
        self.assertEqual(d['numerical_agreement_status'],'REVIEW_REQUIRED')
        self.assertEqual(d['new_scf_status'],'NOT_RUN')
        json.dumps(d,allow_nan=False)

    def test_total_minus_hartree_remains_unattributed(self):
        a=full_grid(self.c,self.size);q={m:(z if m==ZERO else .9*z) for m,z in self.c.items()}
        d=M.analyze_density_hartree({'A_out':a,'QE':q},[[10,0,0],[0,10,0],[0,0,10]],{'A_out':self.size,'QE':self.size},historical_total_energies_ha={'A_out':-1.,'QE':-1.01})
        r=d['comparisons']['A_out_minus_QE']
        self.assertAlmostEqual(r['other_energy_terms_undecomposed_difference_ha'],.01-r['hartree_decomposition']['native_difference_ha'],delta=1e-16)
        self.assertEqual(d['residual_attribution_status'],'NOT_ESTABLISHED')


class CoefficientStorageTests(unittest.TestCase):
    def test_deterministic_gzip_fullprecision_signed_zero_no_filter(self):
        d={'A_out':{ZERO:complex(.01,-0.),(1,0,0):complex(-0.,5e-324),(-1,0,0):complex(-0.,-5e-324)},'B_out':{ZERO:.01+0j,(1,0,0):complex(1.2345678901234567,-2.345678901234567),(-1,0,0):complex(1.2345678901234567,2.345678901234567)}}
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'a.csv.gz';b=Path(tmp)/'another-name.csv.gz'
            M.write_coefficients_gzip(a,d);M.write_coefficients_gzip(b,{k:dict(reversed(list(v.items()))) for k,v in reversed(list(d.items()))})
            self.assertEqual(a.read_bytes(),b.read_bytes());self.assertEqual(a.read_bytes()[4:8],bytes(4))
            raw=gzip.decompress(a.read_bytes());self.assertNotIn(b'\r',raw)
            out=M.read_coefficients_gzip(a)
            for name in d:
                self.assertEqual(set(out[name]),set(d[name]))
                for m,z in d[name].items():self.assertEqual(struct.pack('dd',out[name][m].real,out[name][m].imag),struct.pack('dd',z.real,z.imag))

    def test_reader_rejects_duplicate_missing_zero_bad_integer_nonfinite(self):
        for text in ['m1,m2,m3,QE_real,QE_imag\n0,0,0,.01,0\n0,0,0,.01,0\n', 'm1,m2,m3,QE_real,QE_imag\n1,0,0,.01,0\n', 'm1,m2,m3,QE_real,QE_imag\n0.0,0,0,.01,0\n', 'm1,m2,m3,QE_real,QE_imag\n0,0,0,nan,0\n', 'm1,m2,m3,QE_real,QE_imag\n0,0,0,.01,0,extra\n']:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):M.read_coefficients_gzip_bytes(compressed_csv(text))

    def test_truncation_and_wrong_shared_support_rejected(self):
        payload=compressed_csv('m1,m2,m3,QE_real,QE_imag\n0,0,0,.01,0\n')
        with self.assertRaises(ValueError):M.read_coefficients_gzip_bytes(payload[:-4])
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'x.gz'
            with self.assertRaises(ValueError):M.write_coefficients_gzip(dest,{'A_out':sparse_pair(),'B_out':{ZERO:.01}})
            self.assertFalse(dest.exists())


if __name__=='__main__':unittest.main()
