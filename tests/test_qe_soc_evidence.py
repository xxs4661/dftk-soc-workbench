"""Offline publication regressions using public native evidence; no solver runs."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import check_qe_soc_evidence as checker


class PublicEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Only the small public sources are copied; no .work, UPF or archive.
        for name in ['scripts', 'benchmarks', 'results', 'environment', 'config', 'prototypes']:
            shutil.copytree(ROOT / name, self.root / name,
                            ignore=shutil.ignore_patterns('__pycache__', 'runs'))
        self.evidence_path = self.root / 'results/mg-soc-qe-comparison/evidence.json'
        self.evidence = json.loads(self.evidence_path.read_text())

    def save(self):
        self.evidence_path.write_text(json.dumps(self.evidence))

    def test_public_sources_recompute_without_private_runs(self):
        self.assertFalse((self.root / '.work').exists())
        self.assertEqual(checker.check(self.root)['status'], 'PASS')

    def test_nonzero_process_cannot_use_successful_native_files(self):
        self.evidence['process']['exit_code'] = 7
        self.save()
        with self.assertRaisesRegex(ValueError, 'current QE process'):
            checker.check(self.root)

    def test_relabeling_historical_reference_rejected(self):
        self.evidence['historical_reference_status'] = 'NEW_RUN'
        self.save()
        with self.assertRaisesRegex(ValueError, 'Historical run mislabeled'):
            checker.check(self.root)

    def test_tampered_comparison_rejected_even_with_fresh_hash(self):
        relative = 'results/mg-soc-qe-comparison/comparison.json'
        path = self.root / relative
        data = json.loads(path.read_text())
        data['comparisons']['A_minus_QE']['energy']['internal']['signed_ha'] += 1
        path.write_text(json.dumps(data))
        self.evidence['public_sha256'][relative] = checker.digest(path)
        self.save()
        with self.assertRaisesRegex(ValueError, 'Comparison summary differs'):
            checker.check(self.root)

    def test_refinement_cannot_replace_scf_energy(self):
        self.evidence['refinement']['energy_source'] = 'bands total energy'
        self.save()
        with self.assertRaisesRegex(ValueError, 'cannot replace SCF energy'):
            checker.check(self.root)

    def test_new_case_cannot_rewrite_predeclared_physics(self):
        relative = 'benchmarks/mg-soc-qe-v1/case.json'
        path = self.root / relative
        data = json.loads(path.read_text())
        data['electrons']['temperature_ha'] = .002
        path.write_text(json.dumps(data))
        self.evidence['case_config']['sha256'] = checker.digest(path)
        self.evidence['public_sha256'][relative] = checker.digest(path)
        self.save()
        with self.assertRaisesRegex(ValueError, 'beyond the disclosed XC index'):
            checker.check(self.root)

    def test_old_input_cannot_stand_in_for_new_predeclaration(self):
        self.evidence['predeclaration']['qe_input_sha256'] = self.evidence['predeclaration']['case_sha256']
        self.save()
        with self.assertRaisesRegex(ValueError, 'Predeclared QE input changed'):
            checker.check(self.root)

    def test_refinement_source_not_interchangeable(self):
        self.evidence['refinement']['source_scf_run_id'] = 'wrong-run'
        self.save()
        with self.assertRaisesRegex(ValueError, 'Refinement source/exit differs'):
            checker.check(self.root)


if __name__ == '__main__':
    unittest.main()
