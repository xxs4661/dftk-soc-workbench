"""Synthetic Phase 8B protocol/arithmetic tests, never physical calculations.

The B0 source is the real frozen public receipt, read only; every new endpoint
and current-run identity below is explicitly synthetic and not solver evidence.
"""
import copy
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import si_soc_sensitivity as s
from si_soc_comparison import _contract, _fd_diagnostic


def fixture(profile='E40', responses=(0., 0.)):
    case = s.load_case(ROOT, profile)
    tau = case['electrons']['temperature_ha']
    digest = s.case_sha256(profile)
    binding = {p: {'scf_run_id': f'synthetic-{profile}-{p}-SCF',
                  'gamma_run_id': f'synthetic-{profile}-{p}-GAMMA',
                  'density_sha256': ('d' if p == 'D' else 'e') * 64,
                  'case_sha256': digest} for p in ('D', 'Q')}
    values = {'case': case, 'binding': binding}
    historical = s.load_historical_gamma()
    for label, response in zip(('D', 'Q'), responses):
        common = {'schema_version': 1, 'case': case['case'], 'sensitivity_profile': profile,
            'case_sha256': digest, 'code': 'DFTK' if label == 'D' else 'QE',
            'execution_status': 'PASS', 'process_exit_code': 0, 'input_comparability_status': 'PASS',
            'physical_operator': 'full_soc', 'pseudo_sha256': case['pseudo']['sha256'],
            'n_electrons': 8, 'n_bands': 24, 'occupation_capacity': 1,
            'temperature_ha': tau, 'density_source_sha256': binding[label]['density_sha256'],
            'fermi_energy_ha': 0., 'warning_evidence': {'eigenvalues_not_converged': False,
                'ieee_warning_status': 'REPORTED', 'ieee_localization_status': 'NOT_LOCALIZED'}}
        # Synthetic symmetric endpoint has exactly eight electrons at mu=0.
        ev = [-1.] * 6 + [-.01] * 2 + [.01] * 2 + [1.] * 14
        occupations = _fd_diagnostic(ev, 0., tau=tau)
        entropy = s._entropy(occupations)
        internal = -8. if label == 'D' else -8.00001
        energy = {'internal_ha': internal, 'free_ha': internal - tau * entropy,
                  'minus_TS_ha': -tau * entropy, 'entropy_dimensionless': entropy}
        parent = {**common, 'kind': 'scf', 'run_id': binding[label]['scf_run_id'],
            'scf_acceptance_status': 'PASS', 'energy': energy,
            'kpoints': [{**copy.deepcopy(p), 'eigenvalues_ha': ev[:], 'occupations': occupations[:]}
                        for p in case['kpoints']]}
        original = s.analyze_gamma(historical[label]['kpoints'][0]['eigenvalues_ha'])
        gamma = [x-original['quartet_mean_ha']-.012 for x in original['values_ha']]
        for i in range(4, 8):
            gamma[i] += response / s.HARTREE_EV
        receipt = {**common, 'kind': 'spectrum', 'run_id': binding[label]['gamma_run_id'],
            'source_scf_run_id': parent['run_id'],
            'kpoints': [{'coordinate_fractional': [0., 0., 0.], 'weight_spatial': 1.,
                'eigenvalues_ha': gamma, 'residuals_ha': [1e-12] * 24, 'gram_frobenius': 1e-12}],
            'precision': {'diago_thr_init_ry': 1e-13, 'ethr_history_ry': [1e-13]}}
        values[label.lower() + '_scf'] = parent
        values[label.lower() + '_gamma'] = receipt
    return values


class CaseContractTests(unittest.TestCase):
    def test_registered_profiles_and_bytes(self):
        for profile, nk, ecut, tau in (('E40', 8, 40, .001), ('T05', 8, 30, .0005), ('K4', 64, 30, .001)):
            with self.subTest(profile=profile):
                c = s.load_case(ROOT, profile)
                self.assertIs(s.validate_case(c), c)
                self.assertEqual((len(c['kpoints']), c['cutoffs']['dftk_ecut_ha'], c['electrons']['temperature_ha']), (nk, ecut, tau))
                self.assertEqual(c['probe_kpoints'], [[0., 0., 0.]])
                self.assertEqual(c['probe_weights'], [1.])
                self.assertEqual(len(s.prepared_paths(profile)), 6)
        self.assertEqual(len(s.prepared_paths()), 12)
        self.assertFalse(any('README' in p for p in s.prepared_paths()))
        eight = s.load_case(ROOT, 'E40')['kpoints']
        sixtyfour = s.load_case(ROOT, 'K4')['kpoints']
        self.assertTrue({tuple(p['coordinate_fractional']) for p in eight}.issubset(
            {tuple(p['coordinate_fractional']) for p in sixtyfour}))

    def test_unregistered_and_second_factor_rejected(self):
        with self.assertRaises(ValueError):
            s.load_case(ROOT, 'E50')
        mutations = [lambda c: c['electrons'].__setitem__('temperature_ha', .0005),
            lambda c: c['xc'].__setitem__('qe', 'PBEsol'),
            lambda c: c['pseudo'].__setitem__('nlcc', False),
            lambda c: c['cutoffs'].__setitem__('qe_ecutwfc_ry', 40),
            lambda c: c['settings']['solver'].__setitem__('initial_target_states', 32),
            lambda c: c['electrons'].__setitem__('occupation_capacity', 2),
            lambda c: c['geometry'].__setitem__('n_atoms', 1),
            lambda c: c['fft_size'].__setitem__(0, 64),
            lambda c: c.__setitem__('symmetries', 0),
            lambda c: c.__setitem__('arbitrary_override', True)]
        for mutation in mutations:
            c = s.load_case(ROOT, 'E40'); mutation(c)
            with self.subTest(case=c), self.assertRaises(ValueError):
                s.validate_case(c)

    def test_64_count_unique_weights_and_order_remain_strict(self):
        for mutation in (lambda p: p.pop(), lambda p: p.__setitem__(1, copy.deepcopy(p[0])),
                         lambda p: p[0].__setitem__('weight_spatial', .125), lambda p: p.reverse()):
            c = s.load_case(ROOT, 'K4'); mutation(c['kpoints'])
            with self.assertRaises(ValueError):
                s.validate_case(c)

    def test_runtime_evidence_not_override(self):
        f = fixture(); c = f['case']
        c.update(case_sha256=s.case_sha256('E40'), verified_pseudo_sha256=c['pseudo']['sha256'], binding=f['binding'])
        s.validate_case(c)
        for key, value in (('case_sha256', '0'*64), ('verified_pseudo_sha256', '0'*64), ('binding', {})):
            broken = copy.deepcopy(c); broken[key] = value
            with self.assertRaises(ValueError):
                s.validate_case(broken)

    def test_prepared_bytes_are_not_float_tolerance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = s.prepared_paths('E40') + [s.B0_CASE, 'benchmarks/si-soc-splitting-v1/source.json']
            for name in paths:
                dest = root / name; dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, dest)
            self.assertEqual(s.load_case(root, 'E40')['sensitivity_profile'], 'E40')
            path = root / s.CASE_DIR / 'E40/qe-gamma.in'
            path.write_bytes(path.read_bytes() + b'\n')
            with self.assertRaises(ValueError):
                s.load_case(root, 'E40')

    def test_original_default_still_rejects_t05(self):
        old = s.read(ROOT / s.B0_CASE)
        _contract(old)
        old['electrons']['temperature_ha'] = .0005
        with self.assertRaises(ValueError):
            _contract(old)


class ArithmeticTests(unittest.TestCase):
    def test_valid_each_profile_separate_review(self):
        for profile in s.PROFILE_IDS:
            r = s.compare_profile(**fixture(profile))
            self.assertEqual(r['comparison_execution_status'], 'PASS')
            self.assertEqual(r['fixed_window_splitting_agreement_status'], 'PASS')
            self.assertEqual(r['parameter_response_agreement_status'], 'PASS')
            self.assertEqual(r['limited_parameter_stability_status'], dict(D='WITHIN_SCREENING_WINDOW', Q='WITHIN_SCREENING_WINDOW'))
            self.assertEqual(r['numerical_review_status'], 'REVIEW_REQUIRED')
            self.assertEqual(r['physical_manifold_interpretation'], 'REVIEW_REQUIRED')
            self.assertEqual(r['physical_convergence'], 'NOT_ESTABLISHED')
            self.assertEqual(r['variant_null_control_status'], 'NOT_RUN')
            self.assertEqual(r['off_gamma_TR'], 'NOT_ASSESSED')
            self.assertEqual(r['B0']['status'], 'HISTORICAL_REUSED')
            self.assertEqual(len(r['D_gamma']['values_ha']), 24)
            self.assertLess(abs(r['response_gap_closure_ev']), 1e-15)

    def test_common_03mev_change_is_not_stability(self):
        r = s.compare_profile(**fixture(responses=(.0003, .0003)))
        self.assertEqual(r['parameter_response_agreement_status'], 'PASS')
        self.assertEqual(r['fixed_window_splitting_agreement_status'], 'PASS')
        self.assertEqual(r['limited_parameter_stability_status'], dict(D='CHANGE_EXCEEDS_SCREENING_WINDOW', Q='CHANGE_EXCEEDS_SCREENING_WINDOW'))
        for p in ('D', 'Q'):
            self.assertAlmostEqual(r['response_ev'][p], .0003, places=13)

    def test_response_disagreement_still_retains_algebra(self):
        r = s.compare_profile(**fixture(responses=(.0003, 0.)))
        self.assertEqual(r['parameter_response_agreement_status'], 'MISMATCH')
        self.assertEqual(r['fixed_window_splitting_agreement_status'], 'MISMATCH')
        self.assertEqual(r['limited_parameter_stability_status']['Q'], 'WITHIN_SCREENING_WINDOW')
        self.assertAlmostEqual(r['response_gap_ev'], .0003, places=13)

    def test_actual_temperature_and_stable_logistic(self):
        warm, cold = (s.compare_profile(**fixture(p)) for p in ('E40', 'T05'))
        self.assertEqual(warm['gamma_occupation_diagnostic_status'], dict(D='REVIEW_REQUIRED', Q='REVIEW_REQUIRED'))
        self.assertEqual(cold['gamma_occupation_diagnostic_status'], dict(D='PASS', Q='PASS'))
        f = cold['D_gamma']['occupation']
        self.assertEqual(f['temperature_ha'], .0005)
        self.assertAlmostEqual(f['mu_minus_upper_max_over_tau'], 24., places=9)
        self.assertEqual(_fd_diagnostic([-1000., 1000.], 0., tau=.0005), [1., 0.])
        self.assertNotEqual(_fd_diagnostic([.001], 0.), _fd_diagnostic([.001], 0., tau=.0005))

    def test_structure_failure_is_window_only(self):
        f = fixture()
        f['d_gamma']['kpoints'][0]['eigenvalues_ha'][4] -= .00001
        r = s.compare_profile(**f)
        self.assertEqual(r['D_gamma']['fixed_window_interpretation'], 'WINDOW_ONLY_NOT_IDENTIFIED')
        self.assertEqual(r['fixed_window_splitting_agreement_status'], 'INCONCLUSIVE')
        self.assertIn('delta_so_ev', r['D_gamma'])
        self.assertEqual(len(r['spectra']['D_raw_ha']), 24)

    def test_residual_gram_and_native_warning_not_assumed_pass(self):
        for target, mutate in (('d_gamma', lambda r: r['kpoints'][0]['residuals_ha'].__setitem__(0, 1e-8)),
            ('d_gamma', lambda r: r['kpoints'][0].__setitem__('gram_frobenius', 1e-8)),
            ('q_gamma', lambda r: r['warning_evidence'].__setitem__('eigenvalues_not_converged', True))):
            f = fixture(); mutate(f[target])
            r = s.compare_profile(**f)
            self.assertEqual(r['fixed_window_splitting_agreement_status'], 'INCONCLUSIVE')
            self.assertEqual(r['numerical_review_status'], 'REVIEW_REQUIRED')

    def test_one_program_precision_failure_does_not_hide_other_response(self):
        f = fixture(responses=(.0003, 0.))
        f['q_gamma']['warning_evidence']['eigenvalues_not_converged'] = True
        r = s.compare_profile(**f)
        self.assertEqual(r['parameter_response_agreement_status'], 'INCONCLUSIVE')
        self.assertEqual(r['limited_parameter_stability_status']['Q'], 'INCONCLUSIVE')
        self.assertEqual(r['limited_parameter_stability_status']['D'], 'CHANGE_EXCEEDS_SCREENING_WINDOW')

    def test_parent_profile_identity_and_failure_negatives(self):
        mutations = [lambda f: f['d_gamma'].__setitem__('source_scf_run_id', 'B0-parent'),
            lambda f: f['q_gamma'].__setitem__('sensitivity_profile', 'K4'),
            lambda f: f['d_scf'].__setitem__('density_source_sha256', '0'*64),
            lambda f: f['q_scf'].__setitem__('case_sha256', s.case_sha256('K4')),
            lambda f: f['d_scf'].__setitem__('scf_acceptance_status', 'FAIL'),
            lambda f: f['q_gamma'].__setitem__('execution_status', 'FAIL'),
            lambda f: f['d_gamma'].__setitem__('process_exit_code', 17),
            lambda f: f['d_gamma'].__setitem__('process_exit_code', False),
            lambda f: f.__setitem__('q_gamma', None),
            lambda f: f['d_gamma'].__setitem__('fermi_energy_ha', .001),
            lambda f: f['d_gamma'].__setitem__('temperature_ha', .0005),
            lambda f: f['d_gamma']['kpoints'][0].__setitem__('weight_spatial', 1/3),
            lambda f: f['d_gamma']['kpoints'][0]['eigenvalues_ha'].pop(),
            lambda f: f['d_gamma']['kpoints'][0]['eigenvalues_ha'].__setitem__(1, math.nan),
            lambda f: f['d_gamma'].__setitem__('energy_correction_ha', 0)]
        for i, mutate in enumerate(mutations):
            f = fixture(); mutate(f)
            with self.subTest(negative=i), self.assertRaises(ValueError):
                s.compare_profile(**f)

    def test_scf_energy_entropy_and_counts(self):
        mutations = [lambda r: r['energy'].__setitem__('minus_TS_ha', 2*r['energy']['minus_TS_ha']),
            lambda r: r['energy'].__setitem__('free_ha', 0.),
            lambda r: r.__setitem__('energy', None),
            lambda r: r['kpoints'].pop(),
            lambda r: r['kpoints'][0]['occupations'].pop(),
            lambda r: r['kpoints'][0]['occupations'].__setitem__(0, 0.),
            lambda r: r['kpoints'][0]['occupations'].__setitem__(23, .1),
            lambda r: r['kpoints'][0].__setitem__('weight_spatial', .25)]
        for mutate in mutations:
            f = fixture('T05'); mutate(f['d_scf'])
            with self.assertRaises(ValueError):
                s.compare_profile(**f)
        f = fixture(); r = s.compare_profile(**f)
        self.assertEqual(r['SCF']['D']['energy'], f['d_scf']['energy'])
        self.assertEqual(r['SCF']['Q']['energy'], f['q_scf']['energy'])

    def test_parent_mu_change_without_endpoint_change_rejected(self):
        f = fixture()
        f['d_scf']['fermi_energy_ha'] += .1
        f['d_gamma']['fermi_energy_ha'] += .1
        with self.assertRaisesRegex(ValueError, 'occupations are inconsistent'):
            s.compare_profile(**f)

    def test_consistent_synthetic_energy_and_mu_shift_remains_covariant(self):
        f = fixture(); before = s.compare_profile(**f)
        for name in ('d_scf', 'd_gamma'):
            f[name]['fermi_energy_ha'] += .1
            for point in f[name]['kpoints']:
                point['eigenvalues_ha'] = [v+.1 for v in point['eigenvalues_ha']]
        after = s.compare_profile(**f)
        self.assertAlmostEqual(before['D_gamma']['delta_so_ev'], after['D_gamma']['delta_so_ev'], places=13)
        self.assertEqual(after['fixed_window_splitting_agreement_status'], 'PASS')

    def test_native_energy_response_uses_authenticated_B0_and_actual_tau(self):
        for profile in ('E40', 'T05'):
            f = fixture(profile)
            f['d_scf']['energy']['native_metadata'] = {'scope': 'synthetic retained metadata'}
            r = s.compare_profile(**f)
            for label in ('D', 'Q'):
                for field in s.ENERGY_FIELDS:
                    self.assertEqual(r['native_SCF_energy_response_from_B0'][label][field],
                        f[label.lower() + '_scf']['energy'][field] - r['B0']['native_SCF_energy'][label][field])
                e = r['SCF'][label]['energy']
                self.assertEqual(e['minus_TS_ha'], -f['case']['electrons']['temperature_ha'] * e['entropy_dimensionless'])
            self.assertIn('native_metadata', r['SCF']['D']['energy'])
            self.assertEqual(set(r['native_SCF_energy_D_minus_Q']), set(s.ENERGY_FIELDS))
            self.assertNotEqual(r['native_SCF_energy_response_from_B0']['D']['internal_ha'],
                                r['native_SCF_energy_response_from_B0']['D']['free_ha'])

    def test_wrong_original_B0_energy_source_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = s._plan(ROOT)
            names = list(plan['B0']['source_files_sha256']) + list(s.B0_ENERGY_SOURCES)
            names += [s.CASE_DIR + '/' + name for name in s.PLAN_HASHES]
            for name in names:
                dest = root / name; dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, dest)
            self.assertEqual(s.load_historical_energy(root), s.load_historical_energy(ROOT))
            path = root / 'results/si-soc-splitting/D-SCF.json'
            d = s.read(path)
            d['final']['diagnostics']['internal_energy_ha'] += 1e-12
            path.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError, 'Prepared byte mismatch'):
                s.load_historical_energy(root)

    def test_historical_substitute_rejected(self):
        f = fixture(); b = s.load_historical_gamma()['D']
        b['kpoints'][0]['eigenvalues_ha'][4] += 1e-12
        with self.assertRaises(ValueError):
            s.compare_profile(**f, b0_d_gamma=b)

    def test_conflicting_runtime_binding_is_rejected(self):
        f = fixture()
        f['case']['binding'] = copy.deepcopy(f['binding'])
        f['case']['binding']['D']['gamma_run_id'] = 'different-synthetic-gamma'
        with self.assertRaises(ValueError):
            s.compare_profile(**f)

    def test_fresh_cli_failure_does_not_reuse_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory); f = fixture(); args = []
            for name in ('d_gamma', 'q_gamma', 'd_scf', 'q_scf', 'binding'):
                p = path / (name + '.json'); p.write_text(json.dumps(f[name]))
                args.extend(['--' + name.replace('_', '-'), str(p)])
            command = [sys.executable, str(ROOT / 'scripts/si_soc_sensitivity.py'), '--profile', 'E40', *args]
            success = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(success.returncode, 0, success.stdout + success.stderr)
            self.assertEqual(json.loads(success.stdout)['comparison_execution_status'], 'PASS')
            (path / 'q_gamma.json').unlink()
            failure = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(failure.returncode, 2)
            self.assertEqual(json.loads(failure.stdout)['comparison_execution_status'], 'FAIL')
            self.assertIn('reason', json.loads(failure.stdout))


if __name__ == '__main__':
    unittest.main(verbosity=2)
