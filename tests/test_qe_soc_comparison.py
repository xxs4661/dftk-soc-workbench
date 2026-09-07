#!/usr/bin/env python3
"""Synthetic comparison protocol tests; no QE/Julia calculation or physical validation."""
import copy
import csv
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import compare_qe_soc as c


def synthetic_qe(a):
    """Artificial canonical QE record, deliberately derived from a recorded DFTK endpoint.

    This is an arithmetic/adapter fixture, never evidence of QE agreement.
    """
    endpoint, evidence = a['endpoint'], a['evidence']
    d = endpoint['diagnostics']
    record = {'schema_version':1,'code':'QE','calculation':'scf','execution_status':'PASS',
            'input_comparability_status':'PASS','energy_semantics_status':'PASS',
            'energy':{'internal_ha':d['internal_energy_ha']+.2,
                      'free_ha':d['free_energy_ha']+.2,'entropy_ha':d['entropy_energy_ha'],
                      'native_etot_ha':d['free_energy_ha']+.2,'native_demet_ha':d['entropy_energy_ha'],
                      'native_components_ha':{'ehart':d['energy_terms_ha']['Hartree']+.03,
                                              'etxc':d['energy_terms_ha']['Xc']-.04,
                                              'ewald':d['energy_terms_ha']['Ewald']},
                      'sources':'SYNTHETIC canonical fixture, no real QE execution'},
            'electrons':10.,'n_bands':24,'occupation_capacity':1,'tau_ha':.001,
            'smearing':'Fermi-Dirac','pseudo_sha256':evidence['input']['sha256'],
            'xc':{'functional':'PBESOL','indices':[1,4,10,8,0,0,0]},
            'kpoints':[{'coordinate_fractional':p['coordinate_fractional'],
                        'coordinate_raw':p['coordinate_fractional'],'weight_spatial':p['weight_spatial'],
                        'weight_raw':p['weight_spatial'],'eigenvalues_ha':[v+.03 for v in values],
                        'occupations':f,'occupations_raw':f,'npw':p['ng']}
                       for p,values,f in zip(evidence['basis']['kpoints'],endpoint['eigenvalues_ha'],endpoint['occupations'])],
            'scf':{'converged':True,'iterations':17,'error_ha':1e-12},
            'fft_grid':[36,36,36],'fft_smooth_grid':[36,36,36],
            'fermi_energy_ha':.067,'precision':{'actual_target_residuals':'NOT_AVAILABLE'},
            'warnings':[],'entropy_diagnostic':{'status':'SYNTHETIC'}}
    return copy.deepcopy(record)


class ComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case_original = c.read_json(ROOT/'benchmarks/mg-soc-qe-v1/case.json')
        cls.a_original, cls.b_original = c.load_historical(ROOT,cls.case_original)

    def setUp(self):
        self.case = copy.deepcopy(self.case_original)
        self.a, self.b = copy.deepcopy(self.a_original),copy.deepcopy(self.b_original)
        self.qe = synthetic_qe(self.a)

    def compare(self):
        return c.compare(self.case,self.qe,self.a,self.b)

    def reject(self, message=None):
        with self.assertRaises((ValueError,KeyError,TypeError)) as error:
            self.compare()
        if message: self.assertIn(message,str(error.exception))

    def test_success_retains_raw_all_24_and_both_references(self):
        r = self.compare()
        self.assertEqual(r['comparison_execution_status'],'PASS')
        self.assertEqual(r['numerical_agreement_status'],'REVIEW_REQUIRED')
        self.assertEqual(r['physical_convergence_status'],'NOT_ESTABLISHED')
        for label in ('A','B'):
            spectrum = r['comparisons'][label+'_minus_QE']['spectrum']
            self.assertEqual(len(spectrum['rows']),72)
            self.assertEqual(spectrum['summary']['16']['all']['raw']['count'],48)
            self.assertEqual(spectrum['summary']['24']['all']['raw']['count'],72)
            self.assertEqual(spectrum['summary']['16']['occupied']['raw']['count'],30)
            self.assertEqual(spectrum['summary']['16']['empty']['raw']['count'],18)
            self.assertEqual(spectrum['summary']['24']['empty']['raw']['count'],42)
        self.assertEqual(r['comparisons']['A_minus_QE']['role'],'primary')
        self.assertEqual(r['references']['A']['source']['status'],'HISTORICAL_REUSED')
        self.assertEqual(r['array_revalidation']['cross_code_density_l2'],'NOT_RUN')

    def test_signed_absolute_energy_and_ha_ev_units(self):
        e = self.compare()['comparisons']['A_minus_QE']['energy']['internal']
        self.assertAlmostEqual(e['signed_ha'],-.2)
        self.assertAlmostEqual(e['absolute_ha'],.2)
        self.assertAlmostEqual(e['signed_ev'],-.2*c.HARTREE_EV)
        self.assertEqual(c.energy_to_ha(1,'Ha'),1)
        self.assertEqual(c.energy_to_ha(2,'Ry'),1)
        self.assertEqual(c.energy_to_ha(c.HARTREE_EV,'eV/cell'),1)
        for value,unit in [(1,'unknown'),(math.nan,'Ha'),(True,'Ry')]:
            with self.assertRaises(ValueError): c.energy_to_ha(value,unit)

    def test_only_three_unambiguously_corresponding_energy_terms_compared(self):
        comparison = self.compare()['comparisons']['A_minus_QE']['same_definition_energy_terms']
        self.assertEqual(set(comparison['terms']),{'Hartree','Xc','Ewald'})
        self.assertAlmostEqual(comparison['terms']['Hartree']['signed_ha'],-.03)
        self.assertAlmostEqual(comparison['terms']['Xc']['signed_ha'],.04)
        self.assertEqual(comparison['terms']['Ewald']['absolute_ha'],0.)
        self.assertAlmostEqual(comparison['terms']['Xc']['absolute_ev'],.04*c.HARTREE_EV)
        self.assertEqual(comparison['status'],'REPORTED_WITH_DISTINCT_FINAL_DENSITIES')
        self.assertIn('AtomicNonlocalFR',comparison['not_mapped'])

    def test_missing_native_component_is_not_silently_invented_or_skipped(self):
        del self.qe['energy']['native_components_ha']['etxc']
        self.reject('etxc')

    def test_global_offset_removed_once(self):
        s = self.compare()['comparisons']['A_minus_QE']['spectrum']
        self.assertAlmostEqual(s['summary']['24']['all']['raw']['max_abs_ha'],.03)
        self.assertLess(s['summary']['24']['all']['single_global_reference']['max_abs_ha'],1e-14)
        self.assertAlmostEqual(s['references']['QE']['homo_ha']-s['references']['DFTK']['homo_ha'],.03)

    def test_per_k_offsets_are_not_hidden_by_per_k_alignment(self):
        self.qe['kpoints'][0]['eigenvalues_ha'] = [e+.01 for e in self.qe['kpoints'][0]['eigenvalues_ha']]
        s = self.compare()['comparisons']['A_minus_QE']['spectrum']
        self.assertGreater(s['summary']['24']['all']['single_global_reference']['max_abs_ha'],.005)
        # Every row uses exactly the same two global references.
        rh,qh = s['references']['DFTK']['homo_ha'],s['references']['QE']['homo_ha']
        for row in s['rows']:
            self.assertEqual(row['global_reference_difference_ha'],
                (row['reference_eigenvalue_ha']-rh)-(row['qe_eigenvalue_ha']-qh))

    def test_reordered_integer_equivalent_kpoints_match_without_energy_sort(self):
        baseline = self.compare()['comparisons']
        self.qe['kpoints'].reverse()
        self.qe['kpoints'][0]['coordinate_fractional'] = [x+n for x,n in
            zip(self.qe['kpoints'][0]['coordinate_fractional'],[2,-1,3])]
        self.assertEqual(self.compare()['comparisons'],baseline)

    def test_duplicate_integer_equivalent_k_rejected(self):
        self.qe['kpoints'][1]['coordinate_fractional'] = [1,0,0]
        self.reject()

    def test_missing_k_rejected(self):
        self.qe['kpoints'].pop()
        self.reject()

    def test_wrong_sign_point_not_matched_by_similar_spectrum(self):
        self.qe['kpoints'][1]['coordinate_fractional'] = [.125,.0625,.1875]
        self.reject()

    def test_predeclared_coordinate_tolerance_enforced(self):
        self.qe['kpoints'][0]['coordinate_fractional'][0] = 2e-9
        self.reject('1e-10')

    def test_wrong_spatial_weight_rejected(self):
        self.qe['kpoints'][0]['weight_spatial'] = .5
        self.reject()

    def test_capacity_two_rejected(self):
        self.qe['occupation_capacity'] = 2
        self.reject('capacity-one')

    def test_doubled_occupations_rejected(self):
        self.qe['kpoints'][0]['occupations'] = [2*f for f in self.qe['kpoints'][0]['occupations']]
        self.reject('capacity')

    def test_electron_8_or_2_rejected(self):
        for electrons in (8,2):
            self.qe['electrons'] = electrons
            self.reject('ten electrons')

    def test_count_not_fixed_by_renormalizing_f(self):
        self.qe['kpoints'][0]['occupations'][0] = .8
        self.reject('electron count')

    def test_wrong_tau_rejected(self):
        self.qe['tau_ha'] = .002
        self.reject('tau')

    def test_wrong_xc_rejected(self):
        self.qe['xc']['indices'][-1] = 4
        self.reject('XC')

    def test_original_provisional_PZ_metadata_is_rejected(self):
        self.qe['xc']['indices'][1] = 1
        self.reject('XC')

    def test_wrong_pseudo_hash_rejected(self):
        self.qe['pseudo_sha256'] = '0'*64
        self.reject('hash')

    def test_wrong_band_count_or_missing_eigenvalue_rejected(self):
        self.qe['n_bands'] = 16
        self.reject()
        self.qe['n_bands'] = 24
        self.qe['kpoints'][0]['eigenvalues_ha'].pop()
        self.reject('bands')

    def test_nan_rejected(self):
        self.qe['kpoints'][0]['eigenvalues_ha'][0] = math.nan
        self.reject('Nonfinite')

    def test_nonconverged_exit_success_rejected(self):
        self.qe['scf']['converged'] = False
        self.reject('not converged')

    def test_failed_input_or_energy_semantics_rejected(self):
        for field in ('input_comparability_status','energy_semantics_status','execution_status'):
            self.qe[field] = 'FAIL'
            self.reject('prerequisite')
            self.qe[field] = 'PASS'

    def test_nscf_cannot_replace_scf_energy(self):
        for calculation in ('nscf','bands'):
            self.qe['calculation'] = calculation
            self.qe['energy_semantics_status'] = 'NOT_APPLICABLE_SPECTRUM_ONLY'
            self.qe['energy'] = None
            self.reject('cannot consume')

    def test_refinement_spectra_separate_and_original_energy_unchanged(self):
        original = copy.deepcopy(self.qe)
        bands = copy.deepcopy(self.qe)
        bands.update(calculation='bands',energy=None,energy_semantics_status='NOT_APPLICABLE_SPECTRUM_ONLY')
        bands['occupations_source'] = 'SYNTHETIC recalculated occupations'
        bands['chemical_potential_source'] = 'INHERITED_FROM_SCF_NOT_RESOLVED'
        bands['kpoints'][0]['eigenvalues_ha'][23] += 1e-6
        r = c.compare_refinement(self.case,self.qe,bands,self.a,self.b)
        self.assertEqual(self.qe,original)
        self.assertNotIn('energy',r)
        self.assertNotIn('energy',r['comparisons']['A_minus_QE'])
        self.assertEqual(len(r['comparisons']['A_minus_QE']['spectrum']['rows']),72)
        self.assertAlmostEqual(r['refined_minus_scf_spectrum']['summary']['24']['all']['raw']['max_abs_ha'],1e-6)
        bands['fermi_energy_ha'] += .01
        with self.assertRaisesRegex(ValueError,'Inherited SCF chemical potential'):
            c.compare_refinement(self.case,self.qe,bands,self.a,self.b)

    def test_refinement_carrying_energy_or_changed_input_is_rejected(self):
        bands = copy.deepcopy(self.qe)
        bands.update(calculation='bands',energy_semantics_status='NOT_APPLICABLE_SPECTRUM_ONLY')
        with self.assertRaisesRegex(ValueError,'must not provide'):
            c.compare_refinement(self.case,self.qe,bands,self.a,self.b)
        bands['energy'] = None; bands['tau_ha'] = .002
        with self.assertRaisesRegex(ValueError,'tau'):
            c.compare_refinement(self.case,self.qe,bands,self.a,self.b)

    def test_E_F_entropy_sign_and_double_counting(self):
        correct = c.energy_record(-10.,-10.02,-.02,source='synthetic',native_free=-10.02,native_entropy=-.02)
        self.assertEqual(correct['internal_ha'],-10.)
        for internal,free,entropy in [(-10.,-10.02,.02),(-10.02,-10.02,-.02),(-10.,-10.04,-.02),(-10.01,-10.02,-.02)]:
            with self.assertRaises(ValueError): c.energy_record(internal,free,entropy,source='synthetic wrong semantics')

    def test_native_energy_fields_cannot_be_reinterpreted(self):
        self.qe['energy']['native_etot_ha'] += .1
        self.reject('Native QE total energy')

    def test_missing_native_entropy_is_not_silently_zero(self):
        self.qe['energy']['native_demet_ha'] = None
        self.reject('Native QE entropy')

    def test_native_entropy_not_added_twice(self):
        e = self.qe['energy']; e['entropy_ha'] = -.02; e['native_demet_ha'] = -.02
        e['free_ha'] = e['internal_ha']-.04; e['native_etot_ha'] = e['free_ha']
        self.reject('E + (-TS)')

    def test_zero_tiny_entropy_and_mu_plateau_are_not_relative_error_gates(self):
        self.qe['energy']['entropy_ha'] = self.qe['energy']['native_demet_ha'] = 0.
        self.qe['fermi_energy_ha'] = .12
        r = self.compare()
        self.assertEqual(r['comparison_execution_status'],'PASS')
        self.assertNotEqual(r['comparisons']['A_minus_QE']['chemical_potential']['signed_difference_ha'],0)
        self.assertEqual(r['QE']['energy']['entropy_ha'],0.)
        self.assertLess(abs(r['references']['A']['energy']['entropy_ha']),1e-30)

    def test_partial_occupations_preserve_raw_but_global_reference_unsupported(self):
        for point in self.qe['kpoints']:
            point['occupations'][9],point['occupations'][10] = .75,.25
        s = self.compare()['comparisons']['A_minus_QE']['spectrum']
        self.assertEqual(s['global_reference_status'],'UNSUPPORTED')
        self.assertEqual(len(s['rows']),72)
        self.assertIsNone(s['rows'][0]['global_reference_difference_ha'])
        self.assertEqual(s['summary']['16']['all']['raw']['status'],'REPORTED')
        self.assertEqual(s['references']['DFTK']['status'],'SUPPORTED')

    def test_global_overlap_is_unsupported_not_pointwise_gap(self):
        # Every point remains internally gapped; the full sampled set overlaps.
        self.qe['kpoints'][0]['eigenvalues_ha'] = [e+2 for e in self.qe['kpoints'][0]['eigenvalues_ha']]
        self.assertEqual(self.compare()['comparisons']['A_minus_QE']['spectrum']['global_reference_status'],'UNSUPPORTED')

    def test_large_differences_reported_without_physical_threshold(self):
        for key in ('internal_ha','free_ha','native_etot_ha'): self.qe['energy'][key] += 100
        r = self.compare()
        self.assertEqual(r['comparison_execution_status'],'PASS')
        self.assertEqual(r['numerical_agreement_status'],'REVIEW_REQUIRED')
        self.assertGreater(r['comparisons']['A_minus_QE']['energy']['internal']['absolute_ha'],100)

    def test_A_primary_cannot_be_selected_after_results(self):
        self.a,self.b = self.b,self.a
        self.reject('swapped')

    def test_predeclared_rules_cannot_be_loosened(self):
        self.case['comparison']['saturation_tolerance'] = .1
        self.reject('rule changed')

    def test_historical_mismatching_identity_and_capacity_rejected(self):
        self.a['evidence']['input']['element'] = 'Si'
        self.reject('Historical Mg')
        self.a = copy.deepcopy(self.a_original)
        self.a['endpoint']['diagnostics']['occupations']['capacity_per_state'] = 2
        self.reject('occupation convention')

    def test_historical_bytes_not_just_recorded_hash_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            paths = [self.case['historical']['evidence']['path']]
            paths += [p['path'] for p in self.case['historical']['references'].values()]
            paths += [self.a['evidence'][key]['path'] for key in ('environment','settings')]
            for path in paths:
                (target/path).parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/path,target/path)
            c.load_historical(target,self.case)
            (target/self.case['historical']['references']['A']['path']).write_text('{}\n')
            with self.assertRaisesRegex(ValueError,'endpoint hash'): c.load_historical(target,self.case)

    def test_Mg_zero_diagnostic_is_never_applied(self):
        r = self.compare()
        z = r['mg_local_zero_diagnostic']
        self.assertAlmostEqual(z['correction_per_electron_ha'],.09187494522099392/10)
        self.assertFalse(z['energy_or_spectrum_adjustment_applied'])
        self.assertAlmostEqual(r['comparisons']['A_minus_QE']['energy']['internal']['signed_ha'],-.2)

    def test_symmetry_is_only_an_additional_diagnostic(self):
        r = self.compare()
        self.assertEqual(r['spectral_symmetry']['QE']['status'],'DIAGNOSTIC_ONLY')
        self.assertLess(r['spectral_symmetry']['QE']['plus_minus_spectrum_max_ha'],1e-10)
        self.assertEqual(r['numerical_agreement_status'],'REVIEW_REQUIRED')

    def test_fft_difference_recorded_not_hidden_or_physical_failure(self):
        r = self.compare()
        self.assertEqual(r['numerical_settings_match']['status'],'INPUT_PASS_WITH_NUMERICAL_DIFFERENCES')
        self.assertEqual(r['numerical_settings_match']['DFTK_fft_grid'],[40,40,40])
        self.assertEqual(r['numerical_settings_match']['QE_fft_grid'],[36,36,36])

    def test_csv_contains_both_references_all_raw_and_referenced_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'values.csv'; c.write_eigenvalues_csv(path,self.compare())
            with path.open() as f: rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),144)
            self.assertEqual({r['reference'] for r in rows},{'A','B'})
            self.assertTrue(all(r['reference_eigenvalue_ha'] and r['qe_eigenvalue_ha'] for r in rows))
            self.assertEqual({r['band_index'] for r in rows},{str(i) for i in range(1,25)})

    def test_cli_failure_replaces_previous_comparison_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'result.json'; output.write_text('{"comparison_execution_status":"PASS"}')
            q=Path(tmp)/'qe.json'; bad=copy.deepcopy(self.qe); bad['scf']['converged']=False
            q.write_text(json.dumps(bad))
            p=subprocess.run([sys.executable,str(ROOT/'scripts/compare_qe_soc.py'),
                '--root',str(ROOT),'--qe',str(q),'--output',str(output)],capture_output=True,text=True)
            self.assertNotEqual(p.returncode,0,p.stdout+p.stderr)
            self.assertEqual(json.loads(output.read_text())['comparison_execution_status'],'FAIL')


if __name__ == '__main__':
    unittest.main()
