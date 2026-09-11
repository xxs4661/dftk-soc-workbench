"""Synthetic Phase 8C native-format and recorder protocol tests; no QE or UPF.

Invented XML values and worker bytes are not physical calculations or source
validation. Real source identity and process monitoring have separate gates.
"""
from contextlib import contextmanager, redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'tests')]
import run_si_qe as runner
import si_qe_reference as reference
import si_qe_reference_evidence as evidence
from si_soc_comparison import parse_si_qe, _contract, _expected_points
from test_si_soc_comparison import stdout_for
from test_si_sensitivity_qe import native as sensitivity_native


def case(profile='K6'):
    cfg = reference.load_case(ROOT, profile)
    return dict(cfg, case_sha256=reference.case_sha256(profile),
                verified_pseudo_sha256=cfg['pseudo']['sha256'])


def native(profile='K6', kind='scf'):
    # Reuse only the old synthetic XML builder, never a production calculation.
    with patch('test_si_sensitivity_qe.case', return_value=case(profile)):
        return sensitivity_native(profile, kind)


class ReferenceParserTests(unittest.TestCase):
    def parse(self, profile='K6', kind='scf', *, cfg=None, xml=None, stdout=None, stderr='', code=0):
        generated_case, generated_xml = native(profile, kind)
        cfg = generated_case if cfg is None else cfg
        xml = generated_xml if xml is None else xml
        stdout = stdout_for(xml, kind) if stdout is None else stdout
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'synthetic.xml'
            path.write_text(ET.tostring(xml, encoding='unicode'))
            return parse_si_qe(path, stdout, stderr, kind=kind, case=cfg, process_exit_code=code)

    def test_explicit_216_and_512_contracts_preserve_8_electrons_and_24_spinors(self):
        for profile, nk in (('K6', 216), ('K8', 512)):
            with self.subTest(profile=profile):
                result = self.parse(profile)
                self.assertEqual((len(result['kpoints']), result['requested_kpoint_count']), (nk, nk))
                self.assertEqual((result['n_electrons'], result['n_bands'], result['occupation_capacity']), (8, 24, 1))
                self.assertAlmostEqual(result['electron_sum'], 8, places=12)
                self.assertAlmostEqual(sum(p['weight_spatial'] for p in result['kpoints']), 1, places=12)
                self.assertEqual(result['qe_reference_profile'], profile)
                self.assertEqual(result['profile_type'], 'QE_REFERENCE')
                self.assertEqual(result['case_sha256'], case(profile)['case_sha256'])
                self.assertNotIn('sensitivity_profile', result)
                self.assertEqual(result['dftk_execution_status'], 'NOT_RUN')
                self.assertEqual(result['temperature_ha'], .001)
                self.assertEqual(result['cutoffs'], case(profile)['cutoffs'])

    def test_gamma_one_crystal_point_is_not_eight_electron_feedback(self):
        cfg, xml = native('K6', 'spectrum')
        xml.find('output/band_structure/ks_energies/occupations').text = ' '.join(['.1']*24)
        result = self.parse(kind='spectrum', cfg=cfg, xml=xml)
        self.assertEqual(_expected_points(cfg, 'spectrum'), [[0., 0., 0.]])
        self.assertEqual(result['requested_kpoint_count'], 1)
        self.assertEqual(result['kpoints'][0]['weight_spatial'], 1)
        self.assertAlmostEqual(sum(result['kpoints'][0]['occupations']), 2.4)
        for key in ('energy', 'scf', 'electron_sum'): self.assertIsNone(result[key])
        self.assertEqual(result['occupations_use'], 'DIAGNOSTIC_ONLY_NOT_DENSITY_FEEDBACK')

    def test_k6_modulo_mapping_and_reverse_order_do_not_match_by_energy(self):
        cfg, xml = native(); band = xml.find('output/band_structure')
        points = band.findall('ks_energies')
        points[0].find('k_point').text = '-1 1 1'
        for p in points: band.remove(p)
        for p in reversed(points): band.append(p)
        result = self.parse(cfg=cfg, xml=xml)
        self.assertEqual(result['requested_to_xml_indices'], list(reversed(range(216))))

    def test_missing_duplicate_wrong_weight_count_and_state_counts_rejected(self):
        for defect in ('missing', 'duplicate', 'weight', 'count', 'states', 'electrons', 'nan'):
            cfg, xml = native(); band = xml.find('output/band_structure'); points = band.findall('ks_energies')
            if defect == 'missing': band.remove(points[-1])
            if defect == 'duplicate': points[-1].find('k_point').text = points[0].find('k_point').text
            if defect == 'weight': points[0].find('k_point').set('weight', str(1/64))
            if defect == 'count': band.find('nks').text = '64'
            if defect == 'states': points[0].find('eigenvalues').text = ' '.join(['0']*23)
            if defect == 'electrons': band.find('nelec').text = '216'
            if defect == 'nan': points[0].find('eigenvalues').text = 'nan '+' '.join(['0']*23)
            with self.subTest(defect=defect), self.assertRaises(ValueError): self.parse(cfg=cfg, xml=xml)

    def test_expected_profile_is_not_inferred_from_native_count(self):
        _, xml = native('K6')
        with self.assertRaises(ValueError): self.parse('K8', xml=xml)
        cfg = case(); cfg['sensitivity_profile'] = 'K4'
        with self.assertRaises(ValueError): _contract(cfg)
        for key, value in (('qe_reference_profile', 'K4'), ('profile_type', 'SENSITIVITY'),
                           ('case_sha256', '0'*64), ('verified_pseudo_sha256', '0'*64)):
            cfg = case(); cfg[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): _contract(cfg)

    def test_fixed_native_cutoff_tau_fft_prefix_and_solver_cannot_change(self):
        for path, value, attr in (
            ('input/basis/ecutwfc', '40', None), ('output/basis_set/ecutrho', '160', None),
            ('input/bands/smearing', '.0005', 'degauss'),
            ('input/control_variables/prefix', 'si8b_k4', None),
            ('output/basis_set/fft_smooth', '64', 'nr1'),
            ('input/electron_control/diago_thr_init', '1e-8', None)):
            cfg, xml = native()
            if attr: xml.find(path).set(attr, value)
            else: xml.find(path).text = value
            with self.subTest(path=path), self.assertRaises(ValueError): self.parse(cfg=cfg, xml=xml)

    def test_native_threshold_warning_and_ieee_stay_separate_from_zero_exit(self):
        cfg, xml = native('K8', 'spectrum'); stdout = stdout_for(xml, 'spectrum')
        with self.assertRaises(ValueError): self.parse('K8', 'spectrum', code=7)
        with self.assertRaises(ValueError):
            self.parse('K8', 'spectrum', stdout=stdout.replace('ethr = 1.00E-13', 'ethr = 1.00E-10'))
        result = self.parse('K8', 'spectrum', stdout=stdout+'c_bands: 1 eigenvalues not converged\n',
            stderr='Note: The following floating-point exceptions are signalling: IEEE_INVALID_FLAG\n')
        self.assertTrue(result['warning_evidence']['eigenvalues_not_converged'])
        self.assertEqual(result['eigensolver_status'], 'EIGENSOLVER_REVIEW_REQUIRED')
        self.assertEqual(result['precision']['explicit_wavefunction_residuals'], 'NOT_AVAILABLE')


class ReferenceRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.profile = 'K6'
        self.cfg = case(self.profile); self.area = self.root/'.work/phase8c'/self.profile
        case_dir, self.save, _ = runner.profile_layout(qe_reference_profile=self.profile)
        (self.root/case_dir).mkdir(parents=True)
        self.source = self.root/'synthetic-source'
        self.source.write_bytes(b'Synthetic recorder bytes, not a UPF.')
        self.manifest = self.root/'synthetic-preflights.json'; self.manifest.write_text('{}')
        self.prepared = dict(case=self.cfg, qe_reference_profile=self.profile, profile_type='QE_REFERENCE',
            case_sha256=self.cfg['case_sha256'], preparation_commit=reference.PREPARATION, execution_commit='a'*40,
            source={'sha256': runner.digest(self.source)}, pseudo_path=str(self.source), prepared_sha256={},
            frozen_sha256={}, source_sha256={}, upstream={}, save_path=self.save.as_posix())
        for name in ('qe-scf.in', 'qe-gamma.in'):
            path = self.root/case_dir/name; path.write_text('Synthetic input protocol\n')
            self.prepared['prepared_sha256'][case_dir+'/'+name] = runner.digest(path)
        self.events = []
        for module, name, target in (
            (runner, 'frozen_inputs', lambda *a, **k: self.prepared),
            (runner, 'identity', lambda *a: {'qe_identity': {'selected_path': 'synthetic-worker'}}),
            (runner, '_recheck', lambda *a: None), (runner, 'clean_execution', lambda *a: None),
            (runner, 'execute', self.worker), (runner, 'parse_si_qe', self.parsed),
            (evidence, 'verify_preflights', lambda *a: self.events.append('preflight')),
            (evidence, 'reference_execution_guard', self.guard),
            (evidence, 'monitored_execute', self.monitored),
            (reference, 'validate_q_scf', lambda *a, **k: {'status': 'PASS', 'synthetic': True}),
            (reference, 'validate_q_gamma', lambda *a, **k: {'precision_status': 'PASS', 'trend_usable': True})):
            patcher = patch.object(module, name, side_effect=target)
            setattr(self, 'mock_'+name, patcher.start()); self.addCleanup(patcher.stop)
        patcher = patch.dict(runner.os.environ, {k:v for k,v in runner.os.environ.items() if k not in runner.FORBIDDEN_ENV}, clear=True)
        patcher.start(); self.addCleanup(patcher.stop)

    @contextmanager
    def guard(self, root, directory, action, profile):
        self.assertEqual(profile, self.profile)
        self.assertFalse((self.area/'slots'/(action+'.json')).exists())
        self.events.append('guard_enter')
        try: yield
        finally: self.events.append('guard_exit')

    def monitored(self, executor, command, directory, env):
        self.assertIn('guard_enter', self.events)
        self.events.append('monitor')
        return executor(command, directory, env), {'status': 'PASS', 'synthetic': True, 'peak_tree_rss_bytes': 1024}

    def worker(self, command, directory, env):
        self.assertEqual(self.events[-1], 'monitor')
        self.events.append('worker')
        save = directory/self.save; save.mkdir(parents=True, exist_ok=True)
        for name, raw in [('charge-density.dat', b'synthetic charge'), ('data-file-schema.xml', b'<synthetic/>'),
                          ('Si_r.upf', self.source.read_bytes())]: (save/name).write_bytes(raw)
        for i in range(1, 217): (save/f'wfc{i}.dat').write_text('synthetic '+str(i))
        (directory/'qe.stdout').write_text('Synthetic worker, not QE.\nParallel version (MPI), running on 1 processors\nMPI processes distributed on 1 nodes\n')
        (directory/'qe.stderr').write_text('')
        return 0

    def parsed(self, xml, stdout, stderr, *, kind, case, process_exit_code):
        self.events.append('parse')
        self.assertNotEqual(self.events[-2], 'guard_exit')
        return dict(schema_version=1, case=self.cfg['case'], qe_reference_profile=self.profile,
            profile_type='QE_REFERENCE', case_sha256=self.cfg['case_sha256'], temperature_ha=.001,
            cutoffs=self.cfg['cutoffs'], requested_kpoint_count=216 if kind == 'scf' else 1,
            n_electrons=8, n_bands=24, occupation_capacity=1, kind=kind,
            raw_sha256={'xml': runner.digest(xml)}, scf={'converged': True} if kind == 'scf' else None,
            fermi_energy_ha=.25 if kind == 'scf' else -123., warning_evidence={},
            eigensolver_status='REPORTED_THRESHOLD_AVAILABLE')

    def run_action(self, action, name, *, parent=None, manifest=True):
        return runner.run(action, self.area/name, root=self.root, qe_reference_profile=self.profile,
                          parent=parent, preflight_manifest=self.manifest if manifest else None)

    def test_own_parent_gamma_copy_original_mu_and_density(self):
        parent = self.area/'parent'; first = self.run_action('Q-SCF', 'parent')
        self.assertEqual(first['exit_code'], 0); self.assertEqual(first['slot_id'], 'Q6-SCF')
        self.assertEqual(len(first['save_files']), 219)
        before = runner.file_map(parent)
        child = self.run_action('Q-GAMMA', 'gamma', parent=parent)
        self.assertEqual(child['exit_code'], 0); self.assertEqual(child['slot_id'], 'Q6-GAMMA')
        self.assertEqual(runner.file_map(parent), before)
        parsed = json.loads((self.area/'gamma/qe-result.json').read_text())
        self.assertEqual(parsed['fermi_energy_ha'], .25)
        self.assertEqual(parsed['source_scf_run_id'], 'parent')
        self.assertEqual(parsed['density_source_sha256'], before[(self.save/'charge-density.dat').as_posix()]['sha256'])
        self.assertEqual(parsed['gamma_validation']['precision_status'], 'PASS')
        self.assertNotIn('sensitivity_profile', parsed)
        self.assertFalse((self.root/'.work/phase8b').exists())
        self.assertFalse(runner.os.path.samefile(parent/self.save/'charge-density.dat', self.area/'gamma'/self.save/'charge-density.dat'))
        self.assertEqual(self.events, ['preflight', 'guard_enter', 'monitor', 'worker', 'parse', 'guard_exit']*2)

    def test_scf_validation_failure_cannot_be_gamma_parent(self):
        self.mock_validate_q_scf.side_effect = ValueError('Synthetic FD/entropy failure')
        failed = self.run_action('Q-SCF', 'failed')
        self.assertEqual((failed['process_exit_code'], failed['exit_code']), (0, 9))
        self.assertEqual(failed['execution_status'], 'FAIL')
        blocked = self.run_action('Q-GAMMA', 'gamma', parent=self.area/'failed')
        self.assertEqual(blocked['execution_status'], 'BLOCKED_PARENT')
        self.assertFalse(blocked['worker_started']); self.assertIsNone(blocked['process_exit_code'])
        self.assertFalse((self.area/'slots/Q-GAMMA.json').exists())
        self.assertEqual(self.mock_execute.call_count, 1)

    def test_missing_parent_has_current_durable_blocked_record_without_worker(self):
        for name, parent in (('absent', None), ('missing', self.area/'never-existed'),
                             ('old-k4', self.root/'.work/phase8b/K4/parent')):
            result = self.run_action('Q-GAMMA', name, parent=parent)
            self.assertEqual(result['execution_status'], 'BLOCKED_PARENT')
            self.assertEqual(json.loads((self.area/name/'result.json').read_text()), result)
        self.mock_execute.assert_not_called(); self.assertFalse((self.area/'slots').exists())

    def test_both_preflights_and_global_guard_must_pass_before_claim(self):
        missing = self.run_action('Q-SCF', 'missing', manifest=False)
        self.mock_verify_preflights.side_effect = ValueError('Synthetic incomplete K6/K8 manifest')
        failed = self.run_action('Q-SCF', 'failed')
        self.mock_verify_preflights.side_effect = lambda *a: None
        self.mock_reference_execution_guard.side_effect = ValueError('Synthetic active previous slot')
        locked = self.run_action('Q-SCF', 'locked')
        for result in (missing, failed, locked): self.assertNotEqual(result['exit_code'], 0)
        self.mock_execute.assert_not_called(); self.assertFalse((self.area/'slots').exists())

    def test_resource_failure_preserves_actual_exit_and_cannot_parse_or_pass(self):
        self.mock_monitored_execute.side_effect = lambda *a: (-15, {'status': 'RESOURCE_BLOCKED', 'reason': 'synthetic cap'})
        result = self.run_action('Q-SCF', 'cap')
        self.assertEqual((result['execution_status'], result['exit_code'], result['process_exit_code']), ('RESOURCE_BLOCKED', 9, -15))
        self.mock_parse_si_qe.assert_not_called()
        self.assertTrue((self.area/'slots/Q-SCF.json').is_file())
        self.assertEqual(json.loads((self.area/'cap/result.json').read_text()), result)

    def test_even_native_zero_cannot_override_resource_failure(self):
        self.mock_monitored_execute.side_effect = lambda *a: (0, {'status': 'RESOURCE_BLOCKED', 'reason': 'synthetic lost monitor'})
        result = self.run_action('Q-SCF', 'lost')
        self.assertEqual(result['process_exit_code'], 0); self.assertEqual(result['exit_code'], 9)
        self.assertEqual(result['execution_status'], 'RESOURCE_BLOCKED')
        self.mock_parse_si_qe.assert_not_called()

    def test_monitor_exception_recovers_its_current_resource_and_native_receipts(self):
        def interrupted(executor, command, directory, env):
            runner.write_json(directory/'process-exit.json', {'exit_code': -15, 'interrupted': True})
            runner.write_json(directory/'resource.json', {'status': 'RESOURCE_BLOCKED', 'reason': 'Synthetic monitor loss'})
            raise RuntimeError('Synthetic executor interrupted after resource publication')
        self.mock_monitored_execute.side_effect = interrupted
        result = self.run_action('Q-SCF', 'interrupted')
        self.assertEqual((result['process_exit_code'], result['exit_code']), (-15, 9))
        self.assertEqual(result['execution_status'], 'RESOURCE_BLOCKED')
        self.assertEqual(result['resource']['reason'], 'Synthetic monitor loss')
        self.mock_parse_si_qe.assert_not_called()

    def test_native_failure_keeps_its_positive_exit_and_once_claim(self):
        self.mock_execute.side_effect = lambda *a: 7
        failed = self.run_action('Q-SCF', 'failed'); retry = self.run_action('Q-SCF', 'retry')
        self.assertEqual((failed['process_exit_code'], failed['exit_code']), (7, 7))
        self.assertNotEqual(retry['exit_code'], 0)
        self.assertEqual(self.mock_execute.call_count, 1)

    def test_reference_once_claim_is_exclusive_and_separate_from_old_cases(self):
        runner.claim_slot(self.root, 'Q-SCF', 'first', self.prepared)
        with self.assertRaises(FileExistsError): runner.claim_slot(self.root, 'Q-SCF', 'second', self.prepared)
        value = json.loads((self.area/'slots/Q-SCF.json').read_text())
        self.assertEqual(value['run_id'], 'first')
        self.assertFalse((self.root/'.work/phase8b').exists())

    def test_changed_profile_hash_tau_or_charge_parent_is_rejected(self):
        parent = self.area/'parent'; self.run_action('Q-SCF', 'parent')
        outer = json.loads((parent/'result.json').read_text()); parsed = json.loads((parent/'qe-result.json').read_text())
        for key, bad in (('qe_reference_profile', 'K8'), ('case_sha256', '0'*64),
                         ('temperature_ha', .0005), ('density_source_sha256', '0'*64),
                         ('scf_acceptance_status', 'FAIL'), ('requested_kpoint_count', 64)):
            runner.write_json(parent/'qe-result.json', dict(parsed, **{key: bad}))
            runner.write_json(parent/'result.json', dict(outer, parsed_sha256=runner.digest(parent/'qe-result.json')))
            with self.subTest(key=key), self.assertRaises(ValueError): runner.bind_parent(parent, self.prepared, root=self.root)

    def test_native_gamma_warning_keeps_numbers_but_precision_inconclusive(self):
        self.run_action('Q-SCF', 'parent')
        self.mock_validate_q_gamma.side_effect = lambda *a, **k: {'precision_status': 'INCONCLUSIVE', 'trend_usable': False}
        result = self.run_action('Q-GAMMA', 'warning', parent=self.area/'parent')
        self.assertEqual(result['exit_code'], 0)
        value = json.loads((self.area/'warning/qe-result.json').read_text())
        self.assertEqual(value['gamma_validation']['precision_status'], 'INCONCLUSIVE')
        self.assertFalse(value['gamma_validation']['trend_usable'])

    def test_finalization_failure_invalidates_candidate_success(self):
        original = runner.write_json
        def write(path, value):
            if Path(path).name == 'save-manifest.json': raise OSError('Synthetic manifest write failure')
            return original(path, value)
        with patch.object(runner, 'write_json', side_effect=write): result = self.run_action('Q-SCF', 'persist')
        self.assertNotEqual(result['exit_code'], 0)
        for name in ('result.json', 'qe-result.json'):
            self.assertNotEqual(json.loads((self.area/'persist'/name).read_text())['execution_status'], 'PASS')

    def test_guard_finalization_failure_cannot_leave_canonical_success(self):
        @contextmanager
        def fails_after_body(*args):
            with self.guard(*args): yield
            raise ValueError('Synthetic lock owner changed on release')
        self.mock_reference_execution_guard.side_effect = fails_after_body
        result = self.run_action('Q-SCF', 'guard-final')
        self.assertNotEqual(result['exit_code'], 0)
        for name in ('result.json', 'qe-result.json'):
            self.assertNotEqual(json.loads((self.area/'guard-final'/name).read_text())['execution_status'], 'PASS')

    def test_existing_directory_and_dirty_execution_do_not_start_worker(self):
        directory = self.area/'old'; directory.mkdir(parents=True)
        (directory/'result.json').write_text('{"execution_status":"PASS","historical":true}')
        old = (directory/'result.json').read_bytes()
        with redirect_stderr(io.StringIO()): stale = self.run_action('Q-SCF', 'old')
        self.assertNotEqual(stale['exit_code'], 0); self.assertEqual((directory/'result.json').read_bytes(), old)
        self.mock_frozen_inputs.side_effect = ValueError('Synthetic uncommitted source mismatch')
        dirty = self.run_action('Q-SCF', 'dirty')
        self.assertNotEqual(dirty['exit_code'], 0); self.mock_execute.assert_not_called()

    def test_explicit_routes_mutually_exclusive_and_help_is_zero(self):
        with self.assertRaises(ValueError): runner.profile_layout('K4', 'K6')
        with self.assertRaises(ValueError): runner.profile_layout(qe_reference_profile='K4')
        for args in (['--help'], ['Q-SCF', 'unused', '--profile', 'K4', '--qe-reference-profile', 'K6']):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                runner.main(args)
            self.assertEqual(raised.exception.code, 0 if args == ['--help'] else 2)


if __name__ == '__main__': unittest.main()
