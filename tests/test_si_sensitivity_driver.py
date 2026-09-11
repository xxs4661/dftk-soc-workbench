"""Synthetic Python recorder/preflight contracts; never launch Julia or read a UPF."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_si_dftk as driver
import si_soc_sensitivity as sensitivity

HEAD = 'b' * 40


class SensitivityDriverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.cases = {}
        for profile in sensitivity.PROFILE_IDS:
            source = ROOT / sensitivity.CASE_DIR / profile / 'case.json'
            self.cases[profile] = json.loads(source.read_text())
            target = self.root / sensitivity.CASE_DIR / profile / 'case.json'
            target.parent.mkdir(parents=True)
            target.write_bytes(source.read_bytes())
        # This suite isolates recorder protocol; exact prepared Git-case loading
        # is covered independently, without installing sources in this temp tree.
        mock = patch.object(sensitivity, 'load_case', side_effect=lambda root, profile: copy.deepcopy(self.cases[profile]))
        mock.start()
        self.addCleanup(mock.stop)

    def worker(self, profile='E40', action='prepare', run='synthetic-dftk'):
        case = self.cases[profile]
        value = dict(schema_version=1, case=case['case'], run_id=run, action=action,
                     sensitivity_profile=profile, execution_commit=HEAD, execution_status='PASS', exit_code=0,
                     case_sha256=driver.digest(self.root / sensitivity.CASE_DIR / profile / 'case.json'),
                     temperature_ha=case['electrons']['temperature_ha'], environment={'status': 'PASS'},
                     input={'element': 'Si', 'nlcc_present': True, 'sha256': case['pseudo']['sha256']},
                     grid={'status': 'PASS'}, gamma_grid={'status': 'PASS'}, preflight={'status': 'PASS'})
        if action == 'D-SCF':
            value.update(final={'map_count': 2}, checkpoint_sha256='c' * 64)
        if action == 'D-GAMMA':
            value.update(time_reversal={'status': 'PASS'}, source_scf_run_id='synthetic-parent', density_source_sha256='d' * 64)
            value['spectrum'] = dict(schema_version=1, case=case['case'], kind='spectrum', code='DFTK',
                run_id=run, execution_status='PASS', process_exit_code=0, physical_operator='full_soc',
                sensitivity_profile=profile, case_sha256=value['case_sha256'], temperature_ha=value['temperature_ha'],
                source_scf_run_id=value['source_scf_run_id'], density_source_sha256=value['density_source_sha256'],
                pseudo_sha256=case['pseudo']['sha256'], n_electrons=8, n_bands=24, occupation_capacity=1,
                kpoints=[dict(coordinate_fractional=[0., 0., 0.], weight_spatial=1.,
                              eigenvalues_ha=[i * .1 for i in range(24)], residuals_ha=[1e-12] * 24)])
        return value

    def save_worker(self, profile, action, run):
        directory = self.root / '.work/phase8b' / profile / run
        worker_name = run + '-dftk'
        path = directory / worker_name / 'result.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(self.worker(profile, action, worker_name)))
        receipt = dict(schema_version=1, case=self.cases[profile]['case'], run_id=run, action=action,
            execution_status='PASS', exit_code=0, execution_commit=HEAD, worker_directory=worker_name,
            worker_result_sha256=driver.digest(path), sensitivity_profile=profile,
            case_sha256=driver.digest(self.root / sensitivity.CASE_DIR / profile / 'case.json'),
            temperature_ha=self.cases[profile]['electrons']['temperature_ha'],
            pseudo_sha256=self.cases[profile]['pseudo']['sha256'])
        outer = directory / 'receipt.json'
        outer.write_text(json.dumps(receipt))
        return outer, path

    def preflights(self):
        manifest = self.root / '.work/phase8b/preflights.json'
        doc = dict(schema_version=1, execution_commit=HEAD, preparation_commit=sensitivity.PREPARATION, profiles={})
        for profile in sensitivity.PROFILE_IDS:
            outer, _ = self.save_worker(profile, 'prepare', 'prepare-' + profile)
            doc['profiles'][profile] = dict(receipt=outer.relative_to(self.root).as_posix(), sha256=driver.digest(outer))
        manifest.write_text(json.dumps(doc))
        return manifest, doc

    def validate(self, value, code=0):
        return driver.validate_worker(value, code, value['action'], value['run_id'],
                                      profile=value['sensitivity_profile'], root=self.root)

    def test_three_preflights_bound_and_no_worker_launch(self):
        manifest, _ = self.preflights()
        with patch.object(driver.subprocess, 'Popen', side_effect=AssertionError('No numerical worker allowed')):
            self.assertEqual(driver.verify_sensitivity_preflights(self.root, manifest, HEAD), driver.digest(manifest))

    def test_preflights_missing_case_or_manifest_and_wrong_execution(self):
        manifest, doc = self.preflights()
        with self.assertRaises(ValueError): driver.verify_sensitivity_preflights(self.root, None, HEAD)
        with self.assertRaises(ValueError): driver.verify_sensitivity_preflights(self.root, manifest, 'a' * 40)
        del doc['profiles']['K4']; manifest.write_text(json.dumps(doc))
        with self.assertRaises(ValueError): driver.verify_sensitivity_preflights(self.root, manifest, HEAD)

    def test_preflight_corrupt_receipt_or_worker_bytes(self):
        manifest, doc = self.preflights()
        outer = self.root / doc['profiles']['E40']['receipt']
        original = outer.read_bytes(); outer.write_bytes(original + b' ')
        with self.assertRaises(ValueError): driver.verify_sensitivity_preflights(self.root, manifest, HEAD)
        outer.write_bytes(original)
        receipt = json.loads(original); worker = outer.parent / receipt['worker_directory'] / 'result.json'
        worker.write_bytes(worker.read_bytes() + b' ')
        with self.assertRaises(ValueError): driver.verify_sensitivity_preflights(self.root, manifest, HEAD)

    def test_preflight_rebound_wrong_source_is_rejected(self):
        manifest, doc = self.preflights()
        outer = self.root / doc['profiles']['E40']['receipt']; receipt = json.loads(outer.read_text())
        receipt['pseudo_sha256'] = 'f' * 64; outer.write_text(json.dumps(receipt))
        doc['profiles']['E40']['sha256'] = driver.digest(outer); manifest.write_text(json.dumps(doc))
        with self.assertRaises(ValueError): driver.verify_sensitivity_preflights(self.root, manifest, HEAD)

    def test_preflight_missing_gamma_gate_or_failed_worker(self):
        for key in ('grid', 'gamma_grid', 'preflight'):
            for state in ('FAIL', 'NOT_RUN'):
                value = self.worker(); value[key] = {'status': state}
                with self.subTest(key=key, state=state), self.assertRaises(ValueError): self.validate(value)
        value = self.worker(); del value['gamma_grid']
        with self.assertRaises(ValueError): self.validate(value)

    def test_worker_wrong_source_hash_is_rejected(self):
        value = self.worker(); value['input']['sha256'] = 'f' * 64
        with self.assertRaises(ValueError): self.validate(value)

    def test_profile_worker_temperature_and_case_hash(self):
        for profile in sensitivity.PROFILE_IDS:
            value = self.worker(profile); self.validate(value)
            for key, replacement in [('temperature_ha', .002), ('case_sha256', 'f' * 64)]:
                bad = copy.deepcopy(value); bad[key] = replacement
                with self.subTest(profile=profile, key=key), self.assertRaises(ValueError): self.validate(bad)

    def test_gamma_only_count_temperature_weight_and_failures(self):
        good = self.worker('T05', 'D-GAMMA'); self.validate(good)
        for field, value in [('temperature_ha', .001), ('execution_status', 'FAIL'), ('process_exit_code', 1)]:
            bad = copy.deepcopy(good); bad['spectrum'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.validate(bad)
        for mode in ('missing', 'three', 'weight', 'bands'):
            bad = copy.deepcopy(good); points = bad['spectrum']['kpoints']
            if mode == 'missing': points.clear()
            if mode == 'three': points.extend(copy.deepcopy(points) * 2)
            if mode == 'weight': points[0]['weight_spatial'] = .125
            if mode == 'bands': points[0]['eigenvalues_ha'].pop()
            with self.subTest(mode=mode), self.assertRaises(ValueError): self.validate(bad)

    def test_single_non_gamma_point_is_rejected(self):
        value = self.worker('E40', 'D-GAMMA'); value['spectrum']['kpoints'][0]['coordinate_fractional'] = [.125, 0., 0.]
        with self.assertRaises(ValueError): self.validate(value)

    def test_gamma_source_run_case_binding_is_rejected(self):
        good = self.worker('E40', 'D-GAMMA')
        for key, value in [('run_id', 'old-spectrum'), ('case', 'si-soc-splitting-v1'),
                           ('source_scf_run_id', 'other-parent'), ('density_source_sha256', 'f' * 64)]:
            bad = copy.deepcopy(good); bad['spectrum'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.validate(bad)

    def test_legal_worker_failure_preserves_code_and_reason(self):
        value = self.worker(); value.update(execution_status='FAIL', exit_code=7, reason='synthetic failure')
        self.validate(value, 7)
        self.assertEqual(value['exit_code'], 7)
        with self.assertRaises(ValueError): self.validate(value, 0)

    def test_parent_case_execution_and_worker_hash(self):
        outer, worker = self.save_worker('E40', 'D-SCF', 'parent-E40')
        self.assertEqual(driver.checked_parent(outer.parent, profile='E40', root=self.root, execution_commit=HEAD), worker.parent)
        for profile, head in [('T05', HEAD), ('E40', 'a' * 40)]:
            with self.subTest(profile=profile, head=head), self.assertRaises(ValueError):
                driver.checked_parent(outer.parent, profile=profile, root=self.root, execution_commit=head)
        worker.write_bytes(worker.read_bytes() + b' ')
        with self.assertRaises(ValueError): driver.checked_parent(outer.parent, profile='E40', root=self.root, execution_commit=HEAD)

    def test_parent_rebound_failure_is_not_successful_parent(self):
        outer, worker = self.save_worker('E40', 'D-SCF', 'parent-E40')
        value = json.loads(worker.read_text()); value.update(execution_status='FAIL', exit_code=7, reason='synthetic failure')
        worker.write_text(json.dumps(value)); receipt = json.loads(outer.read_text())
        receipt['worker_result_sha256'] = driver.digest(worker); outer.write_text(json.dumps(receipt))
        with self.assertRaises(ValueError): driver.checked_parent(outer.parent, profile='E40', root=self.root, execution_commit=HEAD)


if __name__ == '__main__':
    unittest.main()
