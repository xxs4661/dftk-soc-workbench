"""Phase 8C pure contract fixtures: synthetic receipts are not QE evidence.

The one public-history test replays frozen published scalar data; no test starts
QE, Julia, SCF, occupation solving, or reads a UPF/private checkpoint.
"""
import copy
import gzip
import hashlib
import math
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import si_qe_reference as ref


def synthetic_receipts(profile='K6'):
    case = ref.load_case(ROOT, profile)
    common = {'schema_version': 1, 'case': case['case'], 'qe_reference_profile': profile,
        'case_sha256': ref.case_sha256(profile), 'code': 'QE', 'execution_status': 'PASS',
        'process_exit_code': 0, 'input_comparability_status': 'PASS', 'physical_operator': 'full_soc',
        'pseudo_sha256': case['pseudo']['sha256'], 'n_electrons': 8, 'n_bands': 24,
        'occupation_capacity': 1, 'temperature_ha': .001, 'cutoffs': copy.deepcopy(case['cutoffs']),
        'density_source_sha256': 'a'*64, 'fermi_energy_ha': 0.,
        'warning_evidence': {'eigenvalues_not_converged': False,
                             'ieee_flags': ['SYNTHETIC_WARNING_PRESERVED']}}
    scf = copy.deepcopy(common)
    scf.update(kind='scf', run_id='synthetic-'+profile+'-SCF',
        requested_kpoint_count=len(case['kpoints']), occupations_use='SCF_DENSITY',
        scf={'converged': True, 'iterations': 1, 'error_ha': 0.},
        energy={'internal_ha': -1., 'free_ha': -1., 'minus_TS_ha': 0., 'entropy_dimensionless': 0.},
        kpoints=[dict(copy.deepcopy(p), eigenvalues_ha=[-1.]*8+[1.]*16, occupations=[1.]*8+[0.]*16)
                 for p in case['kpoints']], scf_acceptance_status='PASS')
    scf['electron_sum'] = sum(p['weight_spatial']*8 for p in scf['kpoints'])
    gamma = copy.deepcopy(common)
    gamma.update(kind='spectrum', run_id='synthetic-'+profile+'-GAMMA',
        requested_kpoint_count=1, source_scf_run_id=scf['run_id'],
        occupations_use='DIAGNOSTIC_ONLY_NOT_DENSITY_FEEDBACK', energy=None, scf=None,
        electron_sum=None, precision={'diago_thr_init_ry': 1e-13, 'ethr_history_ry': [1e-13],
                                      'explicit_wavefunction_residuals': 'NOT_AVAILABLE'},
        kpoints=[{'coordinate_fractional': [0.,0.,0.], 'weight_spatial': 1.,
                  'eigenvalues_ha': [-1.]*2+[-.06]*2+[-.0582]*4+[.1+.05*(i//2) for i in range(16)]}])
    return case, scf, gamma


def synthetic_points(values=(.047, .0474, .04745, .0475)):
    return {k: {'delta_so_ev': v, 'trend_usable': True}
            for k,v in zip(('B0','K4','K6','K8'), values)}


class CaseContractTests(unittest.TestCase):
    def test_two_registered_full_grids(self):
        self.assertEqual(len(ref.prepared_paths()), 13)
        self.assertEqual(len(ref.prepared_paths('K6')), 10)
        cases = {p: ref.load_case(ROOT,p) for p in ref.PROFILE_IDS}
        points = {}
        for profile, n in [('K6',6), ('K8',8)]:
            case = cases[profile]
            self.assertEqual(len(case['kpoints']), n**3)
            self.assertEqual(case['profile_type'], 'QE_REFERENCE')
            self.assertEqual(case['dftk_execution_status'], 'NOT_RUN')
            self.assertNotIn('sensitivity_profile', case)
            self.assertEqual(case['probe_kpoints'], [[0.,0.,0.]])
            self.assertEqual(case['probe_weights'], [1.])
            points[profile] = {tuple(p['coordinate_fractional']) for p in case['kpoints']}
            self.assertEqual(len(points[profile]), n**3)
            self.assertTrue(all(p['weight_spatial']==1/n**3 for p in case['kpoints']))
            self.assertAlmostEqual(sum(p['weight_spatial'] for p in case['kpoints']),1.)
            self.assertEqual(ref.validate_case(case),case)
        k4 = ref.read(ROOT/'benchmarks/si-soc-sensitivity-v1/K4/case.json')
        kp4 = {tuple(p['coordinate_fractional']) for p in k4['kpoints']}
        self.assertFalse(kp4 <= points['K6'])
        self.assertTrue(kp4 <= points['K8'])

    def test_exact_case_contract_rejects_unapproved_fields_and_types(self):
        case = ref.load_case(ROOT,'K6')
        mutations = [lambda c: c.update(qe_reference_profile='K10'),
            lambda c: c.update(sensitivity_profile='K4'),
            lambda c: c.update(profile_type='PAIRED'), lambda c: c.update(extra_override=True),
            lambda c: c['electrons'].update(temperature_ha=.0005),
            lambda c: c['electrons'].update(n_electrons=8.),
            lambda c: c['cutoffs'].update(qe_ecutrho_ry=480),
            lambda c: c['pseudo'].update(sha256='b'*64),
            lambda c: c['kpoints'].pop(),
            lambda c: c['kpoints'][0].update(weight_spatial=.125),
            lambda c: c['kpoints'][0].update(coordinate_fractional=[.001,0.,0.]),
            lambda c: c.update(case_sha256='b'*64),
            lambda c: c.update(verified_pseudo_sha256='b'*64)]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                candidate = copy.deepcopy(case)
                mutate(candidate)
                with self.assertRaises((ValueError,KeyError)): ref.validate_case(candidate)
        runtime = dict(case, case_sha256=ref.case_sha256('K6'),
                       verified_pseudo_sha256=case['pseudo']['sha256'])
        self.assertEqual(ref.validate_case(runtime),runtime)

    def test_prepared_bytes_and_path_confinement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = ref.prepared_paths('K6') + ['benchmarks/si-soc-sensitivity-v1/K4/case.json',
                                               'benchmarks/si-soc-splitting-v1/source.json']
            for path in paths:
                out = root/path; out.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/path,out)
            self.assertEqual(ref.load_case(root,'K6'), ref.load_case(ROOT,'K6'))
            target = root/ref.CASE_DIR/'K6/qe-scf.in'
            target.write_bytes(target.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'byte mismatch'): ref.load_case(root,'K6')
            with self.assertRaisesRegex(ValueError,'Unconfined'):
                ref._bytes(root,'../outside','0'*64)
            link = root/'alias'; link.symlink_to(ROOT/ref.CASE_DIR/'K6/case.json')
            with self.assertRaisesRegex(ValueError,'Symlink or escaped'):
                ref._bytes(root,'alias',ref.case_sha256('K6'))

    def test_unknown_profile_is_not_legacy_sensitivity(self):
        from si_soc_sensitivity import load_case
        with self.assertRaises(ValueError): load_case(ROOT,'K6')
        for profile in ('K4','K10',None):
            with self.subTest(profile=profile):
                with self.assertRaises((ValueError,TypeError)): ref.load_case(ROOT,profile)


class ScfContractTests(unittest.TestCase):
    def setUp(self): self.case,self.scf,self.gamma = synthetic_receipts()

    def reject(self, mutate, message=None):
        candidate = copy.deepcopy(self.scf); mutate(candidate)
        with self.assertRaisesRegex((ValueError,KeyError,TypeError), message or '.'):
            ref.validate_q_scf(candidate,self.case)

    def test_complete_k6_and_k8_synthetic_scf(self):
        for profile in ref.PROFILE_IDS:
            case,scf,_ = synthetic_receipts(profile)
            before = copy.deepcopy(scf)
            result = ref.validate_q_scf(scf,case)
            self.assertEqual(scf,before)
            self.assertEqual(result['status'],'PASS')
            self.assertEqual(result['n_kpoints'],int(profile[1:])**3)
            self.assertEqual(result['n_bands'],24)
            self.assertAlmostEqual(result['electron_sum'],8.)
            self.assertEqual(result['FD_max_abs'],0.)
            self.assertEqual(result['top_two_occupation_max'],0.)
            self.assertEqual(result['entropy_dimensionless'],0.)

    def test_wrong_point_count_duplicate_and_coordinates(self):
        for mutate in [lambda r:r['kpoints'].pop(),
                       lambda r:r['kpoints'].__setitem__(1,copy.deepcopy(r['kpoints'][0])),
                       lambda r:r['kpoints'][0].update(coordinate_fractional=[.01,0.,0.]),
                       lambda r:r.update(requested_kpoint_count=512)]:
            self.reject(mutate)

    def test_points_can_be_permuted_or_shifted_by_reciprocal_integers(self):
        candidate = copy.deepcopy(self.scf)
        candidate['kpoints'].reverse()
        for p in candidate['kpoints']:
            p['coordinate_fractional'] = [x+1 for x in p['coordinate_fractional']]
        self.assertAlmostEqual(ref.validate_q_scf(candidate,self.case)['electron_sum'],8.)

    def test_weight_roundoff_is_not_a_new_count_or_electron_rule(self):
        candidate = copy.deepcopy(self.scf)
        candidate['kpoints'][0]['weight_spatial'] += 1e-12
        candidate['kpoints'][1]['weight_spatial'] -= 1e-12
        self.assertAlmostEqual(ref.validate_q_scf(candidate,self.case)['electron_sum'],8.)
        self.reject(lambda r:r['kpoints'][0].update(weight_spatial=.125),'weight')
        self.reject(lambda r:[p.update(weight_spatial=p['weight_spatial']+1e-11) for p in r['kpoints']], 'sum')

    def test_24_capacity_one_finite_states_are_required(self):
        mutations = [lambda r:r['kpoints'][0]['eigenvalues_ha'].pop(),
            lambda r:r['kpoints'][0]['occupations'].pop(),
            lambda r:r['kpoints'][0]['occupations'].__setitem__(0,2.),
            lambda r:r['kpoints'][0]['eigenvalues_ha'].__setitem__(0,float('nan')),
            lambda r:r['kpoints'][0]['occupations'].__setitem__(0,float('inf')),
            lambda r:r.update(occupation_capacity=2), lambda r:r.update(n_bands=48),
            lambda r:r.update(n_electrons=16)]
        for mutate in mutations: self.reject(mutate)

    def test_scf_fd_electron_and_tail_failures(self):
        self.reject(lambda r:r['kpoints'][0]['occupations'].__setitem__(0,.9),'electron')
        def wrong_fd(r):
            r['kpoints'][0]['occupations'][0] = .9
            r['kpoints'][0]['occupations'][8] = .1
        self.reject(wrong_fd,'FD')
        self.reject(lambda r:r.update(fermi_energy_ha=-1.),'FD')
        # This synthetic FD-consistent spectrum has exactly Ne=8 and a genuine
        # top-two tail. It is not a physical SCF or a new occupation solve.
        r = copy.deepcopy(self.scf)
        f = [0.999999999998]*7 + [1.-16e-9+14e-12] + [1e-9]*16
        values = [.001*math.log((1-x)/x) for x in f]
        for p in r['kpoints']:
            p['occupations'],p['eigenvalues_ha'] = list(f),list(values)
        with self.assertRaisesRegex(ValueError,'top-two'): ref.validate_q_scf(r,self.case)

    def test_thermodynamic_fields_and_original_electron_sum(self):
        for mutate in [lambda r:r.update(energy=None),
                       lambda r:r['energy'].update(entropy_dimensionless=-1.),
                       lambda r:r['energy'].update(free_ha=-2.),
                       lambda r:r['energy'].update(entropy_dimensionless=1.),
                       lambda r:r.update(electron_sum=7.)]: self.reject(mutate)
        candidate = copy.deepcopy(self.scf)
        candidate['energy']['internal_ha'] = -2.
        candidate['energy']['free_ha'] = -2.
        old = copy.deepcopy(candidate['energy'])
        ref.validate_q_scf(candidate,self.case)
        self.assertEqual(candidate['energy'],old)
        self.reject(lambda r:r.update(energy_correction_ha=0.),'Fitting/correction')

    def test_nonzero_entropy_comes_from_all_original_occupations(self):
        r = copy.deepcopy(self.scf)
        # Six filled and fourteen empty states, plus four prescribed partial
        # occupations summing to two electrons. No occupation solve is run.
        f = [1.]*6 + [.75]*2 + [.25]*2 + [0.]*14
        levels = [-1.]*6 + [-.001*math.log(3)]*2 + [.001*math.log(3)]*2 + [1.]*14
        entropy = -sum(x*math.log(x)+(1-x)*math.log1p(-x) for x in f if 0<x<1)
        for p in r['kpoints']: p.update(eigenvalues_ha=list(levels),occupations=list(f))
        r['energy'].update(entropy_dimensionless=entropy,minus_TS_ha=-.001*entropy,
                           free_ha=-1.-.001*entropy)
        diag = ref.validate_q_scf(r,self.case)
        self.assertAlmostEqual(diag['entropy_dimensionless'],entropy)
        r['energy']['entropy_dimensionless'] += 1e-7
        with self.assertRaises(ValueError): ref.validate_q_scf(r,self.case)

    def test_current_receipt_identity_and_actual_convergence(self):
        mutations = [lambda r:r.update(process_exit_code=False),
            lambda r:r.update(schema_version=999), lambda r:r.update(run_id=''),
            lambda r:r.update(density_source_sha256=None),
            lambda r:r.update(qe_reference_profile='K8'),
            lambda r:r.update(sensitivity_profile='K4'),
            lambda r:r.update(case_sha256='b'*64),
            lambda r:r.update(kind='spectrum'), lambda r:r.update(execution_status='FAIL'),
            lambda r:r['scf'].update(iterations=201), lambda r:r['scf'].update(error_ha=6e-13),
            lambda r:r['scf'].update(converged=False), lambda r:r.update(warning_evidence=None),
            lambda r:r['warning_evidence'].update(eigenvalues_not_converged=0)]
        for mutate in mutations: self.reject(mutate)
        candidate = copy.deepcopy(self.scf)
        candidate['warning_evidence']['eigenvalues_not_converged'] = True
        self.assertEqual(ref.validate_q_scf(candidate,self.case)['status'],'PASS')


class GammaContractTests(unittest.TestCase):
    def setUp(self): self.case,self.scf,self.gamma = synthetic_receipts()

    def test_same_parent_diagnostic_and_unmodified_original_levels(self):
        before = copy.deepcopy(self.gamma)
        result = ref.validate_q_gamma(self.gamma,self.scf,self.case)
        self.assertTrue(result['trend_usable'])
        self.assertEqual(result['values_ha'],before['kpoints'][0]['eigenvalues_ha'])
        self.assertEqual(result['occupation']['status'],'PASS')
        self.assertEqual(result['precision_status'],'PASS')
        self.assertEqual(result['precision']['explicit_wavefunction_residuals'],'NOT_AVAILABLE')
        self.assertEqual(result['source']['source_scf_run_id'],self.scf['run_id'])
        self.assertEqual(result['warning_evidence'],before['warning_evidence'])
        self.assertEqual(self.gamma,before)

    def test_parent_identity_mu_tau_and_failed_parent(self):
        mutations = [lambda r:r.update(source_scf_run_id='wrong'),
                     lambda r:r.update(density_source_sha256='b'*64),
                     lambda r:r.update(fermi_energy_ha=.001),
                     lambda r:r.update(temperature_ha=.0005),
                     lambda r:r.update(run_id=self.scf['run_id'])]
        for mutate in mutations:
            candidate = copy.deepcopy(self.gamma); mutate(candidate)
            with self.assertRaises(ValueError): ref.validate_q_gamma(candidate,self.scf,self.case)
        for key,value in [('scf_acceptance_status','FAIL'),('execution_status','FAIL'),('qe_reference_profile','K8')]:
            parent = copy.deepcopy(self.scf); parent[key] = value
            with self.assertRaises(ValueError): ref.validate_q_gamma(self.gamma,parent,self.case)

    def test_only_one_gamma_and_no_bands_thermodynamics(self):
        mutations = [lambda r:r['kpoints'].append(copy.deepcopy(r['kpoints'][0])),
                     lambda r:r['kpoints'][0].update(weight_spatial=.125),
                     lambda r:r['kpoints'][0].update(coordinate_fractional=[.25,0.,0.]),
                     lambda r:r.update(energy=self.scf['energy']),
                     lambda r:r.update(electron_sum=8.),
                     lambda r:r.update(scf=self.scf['scf']),
                     lambda r:r.update(occupations_use='SCF_DENSITY'),
                     lambda r:r['precision'].update(ethr_history_ry=[]),
                     lambda r:r['precision'].update(diago_thr_init_ry=1e-12)]
        for mutate in mutations:
            candidate = copy.deepcopy(self.gamma); mutate(candidate)
            with self.assertRaises((ValueError,KeyError)):
                ref.validate_q_gamma(candidate,self.scf,self.case)

    def test_failed_structure_retains_finite_original_window(self):
        mutations = [lambda v:v.__setitem__(1,-.0601),
                     lambda v:v.__setitem__(2,-.06001),
                     lambda v:v.__setitem__(slice(4,8),[-.0599]*4),
                     lambda v:v.__setitem__(9,v[8]+2e-7)]
        for mutate in mutations:
            candidate = copy.deepcopy(self.gamma)
            values = candidate['kpoints'][0]['eigenvalues_ha']; mutate(values)
            result = ref.validate_q_gamma(candidate,self.scf,self.case)
            self.assertFalse(result['trend_usable'])
            self.assertTrue(result['unusable_reasons'])
            self.assertEqual(result['values_ha'],values)
            self.assertTrue(math.isfinite(result['delta_so_ev']))
            points = synthetic_points(); points['K6'] = result
            trend = ref.build_trend(points)
            self.assertEqual(trend['steps']['s46']['status'],'INCONCLUSIVE')
            self.assertEqual(trend['steps']['s68']['status'],'INCONCLUSIVE')
            self.assertIsNotNone(trend['last_three_QE_range_ev'])

    def test_target_solver_warning_is_inconclusive_not_erased(self):
        self.gamma['warning_evidence']['eigenvalues_not_converged'] = True
        result = ref.validate_q_gamma(self.gamma,self.scf,self.case)
        self.assertEqual(result['precision_status'],'INCONCLUSIVE')
        self.assertEqual(result['precision']['status'],'INCONCLUSIVE')
        self.assertFalse(result['trend_usable'])
        self.assertTrue(result['warning_evidence']['eigenvalues_not_converged'])
        self.assertTrue(math.isfinite(result['delta_so_ev']))

    def test_fd_review_does_not_hide_usable_fixed_window(self):
        self.gamma['kpoints'][0]['eigenvalues_ha'] = [-1.]*2+[-.003]*2+[-.001]*4+[.1+.05*(i//2) for i in range(16)]
        result = ref.validate_q_gamma(self.gamma,self.scf,self.case)
        self.assertEqual(result['occupation']['status'],'REVIEW_REQUIRED')
        self.assertLess(result['occupation']['minimum_3_to_8'],.99999999)
        self.assertTrue(result['trend_usable'])
        self.assertEqual(result['precision_status'],'PASS')
        self.assertIn('not constrained',result['occupation']['scope'])


class TrendContractTests(unittest.TestCase):
    def test_inclusive_boundaries_do_not_expand_with_replay_tolerance(self):
        for sign in (-1,1):
            self.assertEqual(ref.step_status(sign*ref.WINDOW_EV),'WITHIN_SCREENING_WINDOW')
            self.assertEqual(ref.step_status(sign*math.nextafter(ref.WINDOW_EV,0.)), 'WITHIN_SCREENING_WINDOW')
            self.assertEqual(ref.step_status(sign*math.nextafter(ref.WINDOW_EV,math.inf)), 'CHANGE_EXCEEDS_SCREENING_WINDOW')
        self.assertEqual(ref.step_status(None),'INCONCLUSIVE')
        self.assertEqual(ref.step_status(.001,False),'INCONCLUSIVE')
        for value in (math.nan,math.inf,-math.inf):
            with self.assertRaises(ValueError): ref.step_status(value)
        with self.assertRaises(ValueError): ref.step_status(0.,1)

    def test_signed_steps_and_three_point_range_are_distinct(self):
        points = synthetic_points((.047,.0474,.04748,.04756))
        before = copy.deepcopy(points)
        result = ref.build_trend(points)
        self.assertAlmostEqual(result['steps']['s24']['signed_ev'],.0004)
        self.assertAlmostEqual(result['steps']['s46']['signed_ev'],.00008)
        self.assertAlmostEqual(result['steps']['s68']['signed_ev'],.00008)
        self.assertEqual(result['last_two_QE_steps_status'],'WITHIN_SCREENING_WINDOW')
        self.assertAlmostEqual(result['last_three_QE_range_ev'],.00016)
        self.assertTrue(result['range_exceeds_window'])
        self.assertEqual(result['physical_convergence'],'NOT_ESTABLISHED')
        self.assertEqual(result['same_grid_cross_code_agreement'],'NOT_ASSESSED')
        self.assertEqual(result['DFTK_K6_status'],'NOT_RUN')
        self.assertEqual(result['DFTK_K8_status'],'NOT_RUN')
        self.assertEqual(points,before)

    def test_nonmonotonic_large_then_small_step(self):
        result = ref.compare_trend(synthetic_points((.047,.0474,.0472,.04725)))
        self.assertLess(result['steps']['s46']['signed_ev'],0)
        self.assertEqual(result['last_step_status'],'WITHIN_SCREENING_WINDOW')
        self.assertEqual(result['last_two_QE_steps_status'],'CHANGE_EXCEEDS_SCREENING_WINDOW')
        self.assertAlmostEqual(result['last_three_QE_range_ev'],.0002)

    def test_failed_missing_k6_cannot_be_replaced_or_skipped(self):
        points = synthetic_points(); points['K6'] = None
        result = ref.compare_trend(points)
        self.assertEqual(result['last_two_QE_steps_status'],'INCONCLUSIVE')
        self.assertIsNone(result['steps']['s46']['signed_ev'])
        self.assertIsNone(result['steps']['s68']['signed_ev'])
        self.assertIsNone(result['last_three_QE_range_ev'])
        self.assertIsNone(result['range_exceeds_window'])
        self.assertEqual(result['range_interpretation_status'],'INCONCLUSIVE')
        self.assertIsNotNone(result['steps']['s24']['signed_ev'])

    def test_finite_unusable_k8_retains_algebra_and_blocks_interpretation(self):
        points = synthetic_points(); points['K8']['trend_usable'] = False
        result = ref.compare_trend(points)
        self.assertIsNotNone(result['steps']['s68']['signed_ev'])
        self.assertIsNotNone(result['last_three_QE_range_ev'])
        self.assertEqual(result['last_step_status'],'INCONCLUSIVE')
        self.assertEqual(result['range_interpretation_status'],'INCONCLUSIVE')
        self.assertEqual(result['steps']['s46']['status'],'WITHIN_SCREENING_WINDOW')

    def test_missing_nonfinite_or_wrong_typed_point_is_hard_failure(self):
        for mutate in [lambda p:p.pop('B0'), lambda p:p.update(DK6={'delta_so_ev':.05,'trend_usable':True}),
                       lambda p:p['K6'].update(delta_so_ev=math.nan),
                       lambda p:p['K6'].update(delta_so_ev=math.inf),
                       lambda p:p['K6'].update(delta_so_ev=True),
                       lambda p:p['K6'].update(trend_usable='PASS')]:
            points = synthetic_points(); mutate(points)
            with self.assertRaises(ValueError): ref.compare_trend(points)


class PublicHistoryTests(unittest.TestCase):
    def assert_native_close(self, actual, expected, where='root', differences=None):
        """Prepared replay tolerance, with exact keys/types/non-float values."""
        self.assertIs(type(actual),type(expected),where)
        if isinstance(actual,dict):
            self.assertEqual(actual.keys(),expected.keys(),where)
            for key in actual:
                self.assert_native_close(actual[key],expected[key],where+'/'+key,differences)
        elif isinstance(actual,list):
            self.assertEqual(len(actual),len(expected),where)
            for i,(a,b) in enumerate(zip(actual,expected)):
                self.assert_native_close(a,b,where+'/'+str(i),differences)
        elif isinstance(actual,float):
            self.assertTrue(math.isfinite(actual) and math.isfinite(expected),where)
            difference = abs(actual-expected)
            self.assertLessEqual(difference,1e-11*max(1.,abs(actual),abs(expected)),where)
            if difference and differences is not None: differences.append((where,difference))
        else: self.assertEqual(actual,expected,where)

    def test_old_b0_k4_native_parse_preserves_every_canonical_field(self):
        from si_soc_comparison import parse_si_qe
        from si_soc_sensitivity import load_case as sensitivity_case
        ref.historical_points(ROOT)  # Authenticate canonical historical sources.
        kdata = ref.read(ROOT/'results/si-soc-sensitivity/K4/data.json')
        km = ref.read(ROOT/'results/si-soc-sensitivity/K4/export-manifest.json')
        runtime = {'run_id','density_source_sha256','source_scf_run_id','density_binding_scope',
                   'scf_acceptance_status','source_evidence_ref'}
        for profile in ('B0','K4'):
            case = (ref.read(ROOT/'benchmarks/si-soc-splitting-v1/case.json')
                    if profile=='B0' else sensitivity_case(ROOT,'K4'))
            case['verified_pseudo_sha256'] = case['pseudo']['sha256']
            if profile=='K4': case['case_sha256'] = km['case_sha256']
            for kind in ('scf','spectrum'):
                with self.subTest(profile=profile,kind=kind):
                    action = 'Q-SCF' if kind=='scf' else ('Q-SPECTRUM' if profile=='B0' else 'Q-GAMMA')
                    if profile=='B0':
                        directory = ROOT/'results/si-soc-splitting'/action
                        manifest = ref.read(directory/'evidence.json')['native_files']
                        old = ref.read(ROOT/('results/si-soc-splitting/Q-SCF/qe-result.json'
                                             if kind=='scf' else 'results/si-soc-splitting/Q-spectrum.json'))
                        native = {name: (directory/name).read_bytes() for name in manifest}
                        parent = ref.read(ROOT/'results/si-soc-splitting/Q-SCF/qe-result.json')
                    else:
                        directory = ROOT/'results/si-soc-sensitivity/K4'/action
                        manifest,old,parent = km['native_files'][action],kdata[action],kdata['Q-SCF']
                        native = {}
                        for name,identity in manifest.items():
                            raw = (directory/(name+'.gz')).read_bytes()
                            self.assertEqual(hashlib.sha256(raw).hexdigest(),identity['compressed_sha256'])
                            native[name] = gzip.decompress(raw)
                    for name,raw in native.items():
                        self.assertEqual(hashlib.sha256(raw).hexdigest(),manifest[name]['public_sha256'])
                        self.assertEqual(len(raw),manifest[name]['public_bytes'])
                    for key in ('xml','stdout','stderr'):
                        self.assertEqual(old['raw_sha256'][key],manifest['qe.'+key]['raw_sha256'])
                    with tempfile.TemporaryDirectory() as directory:
                        xml = Path(directory)/'qe.xml'; xml.write_bytes(native['qe.xml'])
                        actual = parse_si_qe(xml,native['qe.stdout'].decode(),native['qe.stderr'].decode(),
                                             case=case,kind=kind,process_exit_code=0)
                    self.assertEqual(actual['raw_sha256'],{k:manifest['qe.'+k]['public_sha256']
                                                          for k in ('xml','stdout','stderr')})
                    # The old runner explicitly attaches the own-SCF mu after
                    # native bands parsing. Preserve that metadata operation.
                    if kind=='spectrum': actual['fermi_energy_ha'] = parent['fermi_energy_ha']
                    expected = {k:v for k,v in old.items() if k not in runtime}
                    actual.pop('raw_sha256'); expected.pop('raw_sha256')
                    differences = []
                    self.assert_native_close(actual,expected,profile+'/'+kind,differences)
                    if differences:
                        print('Historical native derived-float differences:',differences)

    def test_frozen_b0_k4_public_replay_and_occupational_review(self):
        points = ref.historical_points(ROOT)
        self.assertEqual(set(points),{'B0','K4'})
        self.assertAlmostEqual(points['B0']['delta_so_ev'],.04745761244197689,places=13)
        self.assertAlmostEqual(points['K4']['delta_so_ev'],.047789119355442874,places=13)
        self.assertAlmostEqual(points['K4']['delta_so_ev']-points['B0']['delta_so_ev'],.00033150691346598565,places=13)
        for point in points.values():
            self.assertTrue(point['trend_usable'])
            self.assertEqual(point['source']['status'],'HISTORICAL_REUSED')
            self.assertEqual(point['occupation']['status'],'REVIEW_REQUIRED')
            self.assertEqual(len(point['values_ha']),24)
            self.assertEqual(point['precision']['explicit_wavefunction_residuals'],'NOT_AVAILABLE')

    def test_historical_bytes_cannot_be_replaced_by_a_recomputed_summary(self):
        sources = ref.read(ROOT/ref.CASE_DIR/'sources.json')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in list(ref.PREPARED_HASHES) + list(sources['historical_files']):
                target = root/path; target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/path,target)
            self.assertEqual(ref.historical_points(root),ref.historical_points(ROOT))
            path = root/'results/si-soc-sensitivity/K4/data.json'
            raw = path.read_bytes(); path.write_bytes(raw+b'\n')
            self.assertNotEqual(hashlib.sha256(path.read_bytes()).hexdigest(),hashlib.sha256(raw).hexdigest())
            with self.assertRaisesRegex(ValueError,'byte mismatch'): ref.historical_points(root)


if __name__ == '__main__':
    unittest.main()
