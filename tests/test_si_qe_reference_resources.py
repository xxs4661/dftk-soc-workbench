"""Synthetic/request-grid and pure geometry tests; no physical worker/context."""
import copy
from fractions import Fraction
import sys
import itertools
import json
import math
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import si_qe_reference_evidence as p

def request(n):
    return [{'coordinate_fractional':[float(format(x/n,'.17g')) for x in coords],
             'weight_spatial':float(format(1/n**3,'.17g'))} for coords in p.point_numerators(n)]

class Geometry(unittest.TestCase):
    def test_registered_axes_and_17digit_grids(self):
        self.assertEqual(p.axis(6),[0,1,2,-3,-2,-1])
        self.assertEqual(p.axis(8),[0,1,2,3,-4,-3,-2,-1])
        for n in (6,8):
            result=p.validate_explicit_grid(n,request(n))
            self.assertEqual(result,{'nk':n**3,'unique_mod_integer':True,'gamma_present':True,'inversion_complete':True})
        with self.assertRaises(ValueError):p.axis(10)

    def test_wrong_point_count_duplicate_and_units_refused(self):
        rows=request(6)
        with self.assertRaisesRegex(ValueError,'count'):p.validate_explicit_grid(6,rows[:-1])
        wrong=copy.deepcopy(rows);wrong[-1]=copy.deepcopy(wrong[0])
        with self.assertRaises(ValueError):p.validate_explicit_grid(6,wrong)
        wrong=copy.deepcopy(rows);wrong[1]['coordinate_fractional']=p.cartesian(wrong[1]['coordinate_fractional'])
        with self.assertRaisesRegex(ValueError,'units'):p.validate_explicit_grid(6,wrong)
        wrong=copy.deepcopy(rows);wrong[1]['coordinate_fractional']=[0,0,float('nan')]
        with self.assertRaisesRegex(ValueError,'Nonfinite'):p.validate_explicit_grid(6,wrong)

    def test_weights_never_renormalized(self):
        wrong=request(8);wrong[0]['weight_spatial']=1/216
        original=copy.deepcopy(wrong)
        with self.assertRaisesRegex(ValueError,'weight'):p.validate_explicit_grid(8,wrong)
        self.assertEqual(wrong,original)
        wrong=request(6)
        for row in wrong:row['weight_spatial']+=1e-13
        with self.assertRaisesRegex(ValueError,'sum'):p.validate_explicit_grid(6,wrong)

    def test_non_nested_relations_use_exact_rationals(self):
        sets={n:p.exact_keys(n) for n in (2,4,6,8)}
        self.assertTrue(sets[2]<=sets[6]);self.assertFalse(sets[4]<=sets[6])
        self.assertTrue(sets[4]<=sets[8]);self.assertFalse(sets[6]<=sets[8])
        self.assertEqual(len(sets[4]&sets[6]),8);self.assertEqual(len(sets[6]&sets[8]),8)
        self.assertTrue(all(isinstance(x,Fraction) for point in sets[6] for x in point))

    def test_reciprocal_conversion_and_integer_metric(self):
        lattice=((0,p.A/2,p.A/2),(p.A/2,0,p.A/2),(p.A/2,p.A/2,0))
        b=[p.cartesian(e) for e in ((1,0,0),(0,1,0),(0,0,1))]
        for i,j in itertools.product(range(3),repeat=2):
            self.assertAlmostEqual(sum(x*y for x,y in zip(lattice[i],b[j])),2*math.pi*(i==j),places=14)
        for triple in ((0,0,0),(1,0,0),(1,1,1),(-5,2,7)):
            q=p.cartesian(triple)
            self.assertAlmostEqual(sum(x*x for x in q),p.TWOPIA**2*p.metric(*triple),places=12)
        self.assertEqual(p.metric(1,1,1),3);self.assertEqual(p.metric(1,0,0),3)

    def test_product_extrema_equal_bruteforce_synthetic(self):
        points=[(-2,3,4),(5,-1,2),(1,0,-3)]
        lo,hi,extrema=p.difference_extrema(points)
        brute=[max(abs(a[d]-b[d]) for a in points for b in points) for d in range(3)]
        self.assertEqual(extrema,[7,4,7]);self.assertEqual(extrema,brute)
        self.assertEqual(lo,[-2,-1,-3]);self.assertEqual(hi,[5,3,4])
        with self.assertRaises(ValueError):p.difference_extrema([])

    def test_gamma_and_requested_density_sphere(self):
        gamma=p.wave_sphere(6,(0,0,0));rho=p.density_sphere()
        self.assertEqual(gamma['ng'],2085)
        self.assertEqual(rho['ng'],16865)
        self.assertEqual(rho['g_min'],[-17]*3);self.assertEqual(rho['g_max'],[17]*3)
        self.assertGreater(gamma['closest_candidate_cutoff_distance_ha'],1e-3)
        self.assertGreater(rho['closest_candidate_cutoff_distance_ha'],1e-3)
        self.assertLess(rho['analytic_abs_component_bound'],24)
        self.assertEqual(rho['cutoff_ha'],rho['cutoff_ry']/2)

    def test_all_declared_geometry_matches_preparation_snapshot(self):
        source=Path(__file__).resolve().parents[1]/'benchmarks/si-soc-k-reference-v1/resource-geometry.json'
        prepared=json.loads(source.read_text());actual=p.resource_geometry()
        self.assertEqual(actual['density_sphere'],prepared['density_sphere'])
        self.assertEqual(actual['grid_inclusion'],prepared['grid_inclusion'])
        for name in ('K4','K6','K8'):
            row=actual['profiles'][name];expected=prepared['profiles'][name]
            for key in ('ng_min','ng_max','sum_ng','max_GminusGprime_components','dftk_budget','qe_budget','single_save_budget'):
                self.assertEqual(row[key],expected[key],name+'/'+key)
            self.assertEqual([r['ng'] for r in row['rows']],expected['ng_in_declared_order'])
            self.assertEqual([r['canonical_integer_G_sha256'] for r in row['rows']],expected['G_list_sha256_in_declared_order'])
        self.assertEqual(actual['DFTK_K6_status'],'NOT_RUN')
        self.assertEqual(actual['DFTK_K8_status'],'NOT_RUN')
        self.assertEqual(actual['same_grid_cross_code_agreement'],'NOT_ASSESSED')


class Budgets(unittest.TestCase):
    def test_frozen_dftk_budget_without_context(self):
        self.assertEqual(p.dftk_budget(2148,64)['total_bytes'],5889778688)
        self.assertEqual(p.dftk_budget(2138,216)['total_bytes'],12614633984)
        result=p.dftk_budget(2138,216)
        self.assertEqual(result['budget_status'],'BUDGET_EXCEEDS_EXISTING_LIMIT')
        self.assertEqual(result['execution_status'],'NOT_RUN');self.assertIsNone(result['measured_peak_bytes'])

    def test_qe_cache_scales_all_k_and_remains_estimate(self):
        for ng,nk,total in ((2138,216,3673014272),(2148,512,4695025664)):
            result=p.qe_budget(ng,nk)
            self.assertEqual(result['total_bytes'],total)
            self.assertEqual(result['terms_bytes']['all_k_wavefunctions_and_copy_allowance'],2*16*2*ng*24*(nk+1))
            self.assertLess(total,8*p.GIB)
            self.assertIsNone(result['measured_peak_bytes'])
            self.assertIn('not native QE',result['scope'])
        for function in (p.qe_budget,p.dftk_budget):
            with self.assertRaises(ValueError):function(-1,216)
            with self.assertRaises(ValueError):function(2138,0)

    def test_disk_covers_gamma_copy_archive_restore_and_extra_reserve(self):
        synthetic={'K6':{'single_save_budget':{'total_bytes':423944788}},
                   'K8':{'single_save_budget':{'total_bytes':913508012}}}
        result=p.disk_budget(synthetic,0);needed=result['required_available_bytes']
        self.assertEqual(needed,20919067648)
        terms=result['terms_bytes']
        self.assertEqual(terms['local_scf_and_ordinary_gamma_save_copies'],2*(423944788+913508012))
        self.assertEqual(terms['outside_repository_increment_copy'],terms['local_scf_and_ordinary_gamma_save_copies']+terms['local_logs_native_text_tables_and_staging'])
        self.assertEqual(terms['additional_free_reserve'],10*p.GIB)
        self.assertEqual(p.disk_budget(synthetic,needed-1)['status'],'RESOURCE_BLOCKED')
        self.assertEqual(p.disk_budget(synthetic,needed)['status'],'ESTIMATED_WITHIN_AVAILABLE_SPACE')
        with self.assertRaises(ValueError):p.disk_budget(synthetic,-1)

if __name__=='__main__':unittest.main(verbosity=2)
