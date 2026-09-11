"""Synthetic Phase 8B XML/recorder regressions; no QE/Julia or physical arrays."""
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'tests')]
import run_si_qe as runner
from si_soc_comparison import parse_si_qe, _contract, _expected_points, _fd_diagnostic, SCF_POINTS, PROBES
from test_si_soc_comparison import fixture, stdout_for, put, case as original_case


def case(profile):
    path = ROOT/'benchmarks/si-soc-sensitivity-v1'/profile/'case.json'
    value = json.loads(path.read_text())
    value.update(verified_pseudo_sha256=value['pseudo']['sha256'],
                 case_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    return value


def native(profile, kind='scf'):
    """Invented values in the existing XML fixture, with requested profile geometry."""
    cfg, xml = case(profile), fixture(kind)
    put(xml.find('input/control_variables'), 'prefix', cfg['qe']['prefix'])
    tau = cfg['electrons']['temperature_ha']
    for path in ('input/bands/smearing', 'output/band_structure/smearing'):
        xml.find(path).set('degauss', str(tau))
    for prefix in ('input/basis/', 'output/basis_set/'):
        for key in ('ecutwfc', 'ecutrho'):
            xml.find(prefix+key).text = str(cfg['cutoffs']['qe_'+key+'_ry']/2)
    band = xml.find('output/band_structure')
    template = copy.deepcopy(band.find('ks_energies'))
    for point in band.findall('ks_energies'): band.remove(point)
    requested = [p['coordinate_fractional'] for p in cfg['kpoints']] if kind == 'scf' else cfg['probe_kpoints']
    band.find('nks').text = str(len(requested))
    reciprocal = [[-1, 1, 1], [1, -1, 1], [1, 1, -1]]
    for p in requested:
        node = copy.deepcopy(template)
        node.find('k_point').text = ' '.join(str(sum(p[i]*reciprocal[i][j] for i in range(3))) for j in range(3))
        node.find('k_point').set('weight', str(1/len(requested)))
        band.append(node)
    return cfg, xml


class SensitivityParserTests(unittest.TestCase):
    def parse(self, profile, kind='scf', *, cfg=None, xml=None, stdout=None, stderr='', code=0):
        initial, generated = native(profile, kind)
        cfg, xml = initial if cfg is None else cfg, generated if xml is None else xml
        stdout = stdout_for(xml, kind) if stdout is None else stdout
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'synthetic.xml'
            path.write_text(ET.tostring(xml, encoding='unicode'))
            return parse_si_qe(path, stdout, stderr, kind=kind, case=cfg, process_exit_code=code)

    def test_original_default_contract_and_points_are_unchanged(self):
        cfg = original_case()
        self.assertEqual(_contract(cfg), cfg['pseudo'])
        self.assertEqual(_expected_points(cfg, 'scf'), SCF_POINTS)
        self.assertEqual(_expected_points(cfg, 'spectrum'), PROBES)
        cfg['electrons']['temperature_ha'] = .0005
        with self.assertRaises(ValueError): _contract(cfg)

    def test_three_exact_profiles_and_native_parameters(self):
        for profile, nk, tau, cutoff in (('E40', 8, .001, 40), ('T05', 8, .0005, 30), ('K4', 64, .001, 30)):
            with self.subTest(profile=profile):
                value = self.parse(profile)
                self.assertEqual((len(value['kpoints']), value['temperature_ha']), (nk, tau))
                self.assertEqual((value['n_electrons'], value['n_bands'], value['occupation_capacity']), (8, 24, 1))
                self.assertEqual(value['cutoffs']['dftk_ecut_ha'], cutoff)
                self.assertEqual(value['electron_sum'], 8)
                self.assertEqual(value['case_sha256'], case(profile)['case_sha256'])
                self.assertEqual(value['sensitivity_profile'], profile)

    def test_second_factor_xc_nlcc_profile_and_source_changes_rejected(self):
        for defect in ('tau', 'cutoff', 'xc', 'nlcc', 'profile', 'case_hash', 'source'):
            cfg = case('E40')
            if defect == 'tau': cfg['electrons']['temperature_ha'] = .0005
            if defect == 'cutoff': cfg['cutoffs']['qe_ecutrho_ry'] = 160
            if defect == 'xc': cfg['xc']['qe'] = 'PBESOL'
            if defect == 'nlcc': cfg['pseudo']['nlcc'] = False
            if defect == 'profile': cfg['sensitivity_profile'] = 'E50'
            if defect == 'case_hash': cfg['case_sha256'] = '0'*64
            if defect == 'source': cfg['verified_pseudo_sha256'] = '0'*64
            with self.subTest(defect=defect), self.assertRaises(ValueError): self.parse('E40', cfg=cfg)

    def test_native_cutoff_temperature_prefix_and_fft_must_match_request(self):
        for path, value, attribute in (
            ('input/basis/ecutwfc', '80', None), ('output/basis_set/ecutrho', '320', None),
            ('input/bands/smearing', '.001', 'degauss'),
            ('input/control_variables/prefix', 'si8a', None),
            ('output/basis_set/fft_smooth', '40', 'nr1')):
            cfg, xml = native('T05' if attribute == 'degauss' else 'E40')
            if attribute: xml.find(path).set(attribute, value)
            else: xml.find(path).text = value
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.parse(cfg['sensitivity_profile'], cfg=cfg, xml=xml)

    def test_64_points_periodic_mapping_and_reordering(self):
        cfg, xml = native('K4'); band = xml.find('output/band_structure')
        points = band.findall('ks_energies')
        # Same first point modulo one reciprocal vector; no energy-based matching.
        points[0].find('k_point').text = '-1 1 1'
        for point in points: band.remove(point)
        for point in reversed(points): band.append(point)
        result = self.parse('K4', cfg=cfg, xml=xml)
        self.assertEqual(result['requested_to_xml_indices'], list(reversed(range(64))))
        self.assertEqual(result['requested_kpoint_count'], 64)
        self.assertEqual(sum(p['weight_spatial'] for p in result['kpoints']), 1)

    def test_64_missing_duplicate_weight_count_and_truncated_states_rejected(self):
        for defect in ('missing', 'duplicate', 'weight', 'count', 'states', 'electrons', 'nan'):
            cfg, xml = native('K4'); band = xml.find('output/band_structure'); points = band.findall('ks_energies')
            if defect == 'missing': band.remove(points[-1])
            if defect == 'duplicate': points[-1].find('k_point').text = points[0].find('k_point').text
            if defect == 'weight': points[0].find('k_point').set('weight', '.125')
            if defect == 'count': band.find('nks').text = '8'
            if defect == 'states': points[0].find('eigenvalues').text = ' '.join(['0']*23)
            if defect == 'electrons': band.find('nelec').text = '64'
            if defect == 'nan': points[0].find('eigenvalues').text = 'nan '+' '.join(['0']*23)
            with self.subTest(defect=defect), self.assertRaises(ValueError): self.parse('K4', cfg=cfg, xml=xml)

    def test_gamma_only_no_feedback_energy_or_electron_constraint(self):
        cfg, xml = native('T05', 'spectrum')
        xml.find('output/band_structure/ks_energies/occupations').text = ' '.join(['.1']*24)
        xml.find('output/total_energy/etot').text = '-999'
        result = self.parse('T05', 'spectrum', cfg=cfg, xml=xml)
        self.assertEqual(len(result['kpoints']), 1)
        self.assertEqual(result['kpoints'][0]['weight_spatial'], 1.)
        self.assertAlmostEqual(sum(result['kpoints'][0]['occupations']), 2.4)
        self.assertIsNone(result['energy']); self.assertIsNone(result['scf']); self.assertIsNone(result['electron_sum'])
        self.assertEqual(result['occupations_use'], 'DIAGNOSTIC_ONLY_NOT_DENSITY_FEEDBACK')

    def test_scf_entropy_uses_actual_tau_and_native_ha_ry_fields(self):
        entropies = []
        for profile in ('E40', 'T05'):
            cfg, xml = native(profile)
            xml.find('output/total_energy/demet').text = '-.00001'
            stdout = stdout_for(xml).replace('(-TS) = 0.00000000 Ry', '(-TS) = -0.00002000 Ry')
            stdout = stdout.replace('E=F+TS = -18.00000000 Ry', 'E=F+TS = -17.99998000 Ry')
            energy = self.parse(profile, cfg=cfg, xml=xml, stdout=stdout)['energy']
            self.assertEqual(energy['free_ha'], -9.)
            self.assertEqual(energy['minus_TS_ha'], -.00001)
            self.assertAlmostEqual(energy['internal_ha'], -8.99999)
            entropies.append(energy['entropy_dimensionless'])
        self.assertEqual(entropies[1], 2*entropies[0])

    def test_fd_diagnostic_actual_tau_and_no_mu_solution(self):
        self.assertEqual(_fd_diagnostic([.001], 0.), _fd_diagnostic([.001], 0., .001))
        self.assertAlmostEqual(_fd_diagnostic([.001], 0., .0005)[0], 1/(1+math.exp(2)))
        self.assertNotEqual(_fd_diagnostic([.001], 0., .001), _fd_diagnostic([.001], 0., .0005))
        self.assertEqual(_fd_diagnostic([1000., -1000.], 0., .0005), [0., 1.])
        for bad in (0., -.001, float('nan')):
            with self.assertRaises(ValueError): _fd_diagnostic([0.], 0., bad)

    def test_actual_cg_and_warning_not_hidden_by_zero_exit(self):
        cfg, xml = native('E40', 'spectrum'); stdout = stdout_for(xml, 'spectrum')
        with self.assertRaises(ValueError): self.parse('E40', 'spectrum', code=7)
        with self.assertRaises(ValueError):
            self.parse('E40', 'spectrum', stdout=stdout.replace('ethr = 1.00E-13', 'ethr = 1.00E-10'))
        value = self.parse('E40', 'spectrum', stdout=stdout+'c_bands: 1 eigenvalues not converged\n',
                           stderr='Note: The following floating-point exceptions are signalling: IEEE_INVALID_FLAG\n')
        self.assertTrue(value['warning_evidence']['eigenvalues_not_converged'])
        self.assertEqual(value['eigensolver_status'], 'EIGENSOLVER_REVIEW_REQUIRED')


class SensitivityRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.profile = 'K4'
        self.area = self.root/'.work/phase8b'/self.profile
        self.cfg = case(self.profile)
        self.save = runner.profile_layout(self.profile)[1]
        self.source = self.root/'synthetic-source'; self.source.write_bytes(b'Synthetic recorder bytes, not a UPF.')
        self.manifest = self.root/'synthetic-preflights.json'; self.manifest.write_text('{}')
        case_dir = runner.profile_layout(self.profile)[0]; (self.root/case_dir).mkdir(parents=True)
        self.prepared = dict(case=self.cfg, sensitivity_profile=self.profile, case_sha256=self.cfg['case_sha256'],
            preparation_commit='4a58286183e4625ad7ae69b44eb80097e8ad6c7d', execution_commit='a'*40,
            source={'sha256': runner.digest(self.source)}, pseudo_path=str(self.source),
            prepared_sha256={}, frozen_sha256={}, source_sha256={}, upstream={}, save_path=self.save.as_posix())
        for name in ('qe-scf.in', 'qe-gamma.in'):
            path = self.root/case_dir/name; path.write_text('Synthetic input protocol\n')
            self.prepared['prepared_sha256'][case_dir+'/'+name] = runner.digest(path)
        for name, target in (('frozen_inputs', lambda *a, **k: self.prepared),
                             ('identity', lambda *a: {'qe_identity': {'selected_path': 'synthetic-worker'}}),
                             ('_recheck', lambda *a: None), ('clean_execution', lambda *a: None),
                             ('execute', self.worker), ('parse_si_qe', self.parsed)):
            patcher = patch.object(runner, name, side_effect=target); setattr(self, 'mock_'+name, patcher.start())
            self.addCleanup(patcher.stop)
        patcher = patch('run_si_dftk.verify_sensitivity_preflights', return_value=None)
        self.preflight = patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch.dict(runner.os.environ, {k:v for k,v in runner.os.environ.items() if k not in runner.FORBIDDEN_ENV}, clear=True)
        patcher.start(); self.addCleanup(patcher.stop)

    def worker(self, command, directory, env):
        save = directory/self.save; save.mkdir(parents=True, exist_ok=True)
        for name, raw in [('charge-density.dat', b'synthetic charge'), ('data-file-schema.xml', b'<synthetic/>'),
                          ('Si_r.upf', self.source.read_bytes())]: (save/name).write_bytes(raw)
        for i in range(1, 65): (save/f'wfc{i}.dat').write_text('synthetic '+str(i))
        (directory/'qe.stdout').write_text('Synthetic worker, not QE.\nParallel version (MPI), running on 1 processors\nMPI processes distributed on 1 nodes\n')
        (directory/'qe.stderr').write_text('')
        return 0

    def parsed(self, xml, stdout, stderr, *, kind, case, process_exit_code):
        return dict(schema_version=1, case=self.cfg['case'], sensitivity_profile=self.profile,
                    case_sha256=self.cfg['case_sha256'], temperature_ha=self.cfg['electrons']['temperature_ha'],
                    cutoffs=self.cfg['cutoffs'], requested_kpoint_count=64 if kind == 'scf' else 1,
                    n_electrons=8, n_bands=24, occupation_capacity=1, kind=kind,
                    raw_sha256={'xml': runner.digest(xml)}, scf={'converged': True} if kind == 'scf' else None,
                    fermi_energy_ha=.25 if kind == 'scf' else -123., warning_evidence={},
                    eigensolver_status='REPORTED_THRESHOLD_AVAILABLE')

    def run_action(self, action, name, parent=None, **kwargs):
        return runner.run(action, self.area/name, root=self.root, profile=self.profile,
                          parent=parent, preflight_manifest=kwargs.get('manifest', self.manifest))

    def test_64_parent_gamma_copy_mu_and_profile_slots(self):
        parent = self.area/'parent'
        first = self.run_action('Q-SCF', 'parent')
        self.assertEqual(first['exit_code'], 0); self.assertEqual(len(first['save_files']), 67)
        before = runner.file_map(parent)
        child = self.run_action('Q-GAMMA', 'gamma', parent=parent)
        self.assertEqual(child['exit_code'], 0); self.assertEqual(runner.file_map(parent), before)
        result = json.loads((self.area/'gamma/qe-result.json').read_text())
        self.assertEqual(result['fermi_energy_ha'], .25)
        self.assertEqual(result['source_scf_run_id'], 'parent')
        self.assertEqual(result['case_sha256'], self.cfg['case_sha256'])
        self.assertTrue((self.area/'slots/Q-GAMMA.json').is_file())
        self.assertFalse((self.root/'.work/phase8a/slots').exists())
        self.assertFalse(runner.os.path.samefile(parent/self.save/'charge-density.dat', self.area/'gamma'/self.save/'charge-density.dat'))

    def test_missing_or_failed_three_case_preflight_cannot_claim_slot(self):
        missing = self.run_action('Q-SCF', 'missing', manifest=None)
        self.preflight.side_effect = ValueError('Synthetic incomplete three-case preflight')
        failed = self.run_action('Q-SCF', 'failed')
        self.assertNotEqual(missing['exit_code'], 0); self.assertNotEqual(failed['exit_code'], 0)
        self.mock_execute.assert_not_called(); self.assertFalse((self.area/'slots').exists())

    def test_cross_profile_path_and_changed_parent_case_tau_density_rejected(self):
        parent = self.area/'parent'; self.run_action('Q-SCF', 'parent')
        with self.assertRaises(ValueError): runner.confined_run(self.root, parent, 'T05')
        outer = json.loads((parent/'result.json').read_text())
        parsed = json.loads((parent/'qe-result.json').read_text())
        for key, bad in (('case', 'si-soc-splitting-v1'), ('sensitivity_profile', 'T05'),
                         ('case_sha256', '0'*64), ('temperature_ha', .0005),
                         ('requested_kpoint_count', 8), ('density_source_sha256', '0'*64)):
            changed = dict(parsed, **{key: bad}); runner.write_json(parent/'qe-result.json', changed)
            runner.write_json(parent/'result.json', dict(outer, parsed_sha256=runner.digest(parent/'qe-result.json')))
            with self.subTest(key=key), self.assertRaises(ValueError): runner.bind_parent(parent, self.prepared)

    def test_failed_worker_keeps_exit_and_consumes_only_its_formal_slot(self):
        self.mock_execute.side_effect = lambda *args: 7
        failed = self.run_action('Q-SCF', 'failed'); retry = self.run_action('Q-SCF', 'retry')
        self.assertEqual(failed['process_exit_code'], 7); self.assertEqual(failed['exit_code'], 7)
        self.assertNotEqual(retry['exit_code'], 0); self.assertEqual(self.mock_execute.call_count, 1)
        self.assertNotEqual(json.loads((self.area/'failed/result.json').read_text())['execution_status'], 'PASS')


if __name__ == '__main__': unittest.main()
