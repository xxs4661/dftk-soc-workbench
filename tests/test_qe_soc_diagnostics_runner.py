"""Synthetic recorder/input tests; temporary payloads are not physical QE data."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_qe_soc_diagnostics as runner

ROOT = Path(__file__).resolve().parents[1]


class InputContracts(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((ROOT / runner.CASE_DIR / 'plan.json').read_text())

    def test_predeclared_six_inputs(self):
        runner.validate_plan(ROOT, self.plan)

    def test_physics_cannot_be_changed_in_case(self):
        for field, key, value in [('cutoffs','qe_ecutwfc_ry',31),
                                  ('electrons','temperature_ha',.002),
                                  ('pseudo','sha256','0'*64)]:
            with self.subTest(field=field):
                p = copy.deepcopy(self.plan); p[field][key] = value
                with self.assertRaises(ValueError): runner.validate_plan(ROOT, p)
        p = copy.deepcopy(self.plan); p['kpoints'][0]['coordinate_fractional'][0] = .01
        with self.assertRaises(ValueError): runner.validate_plan(ROOT, p)

    def test_nonwhitelisted_input_rejected_even_with_new_hash(self):
        mutations = [("ecutwfc = 30.0", "ecutwfc = 31.0"),
                     ("degauss = 0.002", "degauss = 0.003"),
                     ("Mg.upf", "other.upf"),
                     ("0 0 0 0.333", "0.01 0 0 0.333"),
                     ("nr1s=40, nr2s=40, nr3s=40,", "nr1s=36, nr2s=36, nr3s=36,")]
        for before, after in mutations:
            with self.subTest(before=before), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for path in ['benchmarks/mg-soc-qe-v1/case.json','benchmarks/mg-soc-qe-v1/qe.in',
                             *[c['input_path'] for c in self.plan['slots'].values()]]:
                    dest = root/path; dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes((ROOT/path).read_bytes())
                p = copy.deepcopy(self.plan); path = root/p['slots']['G40']['input_path']
                self.assertIn(before, path.read_text())
                path.write_text(path.read_text().replace(before, after))
                p['slots']['G40']['input_sha256'] = runner.digest(path)
                with self.assertRaisesRegex(ValueError, 'Non-whitelisted'): runner.validate_plan(root,p)

    def test_pairs_differ_only_by_algorithm(self):
        for grid in (36,40):
            d = (ROOT/self.plan['slots']['D'+str(grid)]['input_path']).read_text()
            c = (ROOT/self.plan['slots']['C'+str(grid)]['input_path']).read_text()
            self.assertEqual(d.replace("diagonalization = 'david', diago_david_ndim = 2",
                                       "diagonalization = 'cg', diago_cg_maxiter = 200"), c)

    def test_case_is_real_seven_b_and_actual_solver_parameters(self):
        c = runner.slot_case(self.plan,'C40')
        self.assertEqual(c['case'],'mg-soc-qe-diagnostics-v1')
        self.assertEqual(c['phase'],'7B')
        self.assertEqual(c['qe']['diagonalization'],'cg')
        self.assertEqual(c['qe']['diago_thr_init_ry'],1e-13)
        self.assertEqual(c['qe']['diago_cg_maxiter'],200)


class SnapshotContracts(unittest.TestCase):
    def source(self, root):
        source = root/'source'; save = source/runner.SAVE; save.mkdir(parents=True)
        for name in ('charge-density.dat','data-file-schema.xml','Mg.upf','wfc1.dat','wfc2.dat','wfc3.dat'):
            (save/name).write_text('synthetic protocol payload: '+name)
        return source

    def test_real_independent_copy_and_source_change_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=self.source(root); expected=runner.snapshot(source)
            worker=root/'worker'; worker.mkdir()
            runner.copy_source(source,worker,expected)
            (worker/runner.SAVE/'wfc1.dat').write_text('synthetic changed worker')
            runner.validate_snapshot(source,expected)
            (source/runner.SAVE/'wfc1.dat').write_text('synthetic changed source')
            with self.assertRaises(ValueError):runner.validate_snapshot(source,expected)

    def test_public_xml_alone_cannot_supply_a_saved_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp); save=source/runner.SAVE; save.mkdir(parents=True)
            (save/'data-file-schema.xml').write_text('<synthetic/>')
            with self.assertRaisesRegex(ValueError,'Missing original'):runner.require_save(source)

    def test_symlink_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=self.source(root)
            (source/'link').symlink_to(source/runner.SAVE/'wfc1.dat')
            with self.assertRaisesRegex(ValueError,'symlink'):runner.snapshot(source)

    def test_failed_new_run_does_not_return_old_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); previous=root/'.work/phase7b/old';previous.mkdir(parents=True)
            (previous/'result.json').write_text('{"execution_status":"PASS"}')
            result=runner.run_slot('I36',root)
            self.assertEqual(result['execution_status'],'FAIL')
            self.assertNotEqual(result['exit_code'],0)
            self.assertNotEqual(result['run_id'],'old')
            self.assertEqual(json.loads((root/'.work/phase7b'/result['run_id']/'result.json').read_text()),result)

    def test_identity_mismatch_rejected(self):
        original={k:'synthetic' for k in ('binary_sha256','launcher_sha256','runner_sha256','jll_uuid','jll_version')}
        for key in original:
            changed=dict(original);changed[key]='different'
            with self.assertRaises(ValueError):runner.checked_identity(changed,original)


if __name__ == '__main__':
    unittest.main()
