"""Synthetic publication-boundary tests; no Julia, UPF, SCF or QE execution."""
import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('publication', ROOT / 'scripts/check_publication.py')
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)


class PublicationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.paths = ['README.md', 'CONTRIBUTING.md', 'AGENTS.md', 'docs/status.md',
                      'docs/ai-assistance.md', 'docs/evidence-policy.md', 'results/shared/environment.json']
        self.paths += ['results/' + c + '/' + f for c in publication.CASES
                       for f in ('README.md', 'evidence.json')]
        for path in self.paths:
            self.write(path, '{}\n' if path.endswith('.json') else 'Synthetic fixture\n')

    def write(self, path, text):
        dest = self.root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)

    def test_frozen_reference_resolves_to_exact_retained_result(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import run_scalar_baseline as runner
        old = 'results/phase4b/20260905T040945688395Z-1cc8a50c/result.json'
        resolved = runner.resolve_reference_result(old)
        self.assertEqual(resolved, ROOT / 'results/scalar-si-baseline/B0/result.json')
        self.assertEqual(publication.digest(resolved),
                         '6458593dfd9bc01d2d83c032fb305b9f69aeb32dbbcfa697a7b08081fe7a5113')

    def test_reference_adapter_preserves_unrelated_paths(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import run_scalar_baseline as runner
        self.assertEqual(runner.resolve_reference_result('synthetic/unrelated.json'),
                         ROOT / 'synthetic/unrelated.json')

    def test_complete_synthetic_collection(self):
        self.assertEqual(publication.check_paths(self.root, self.paths), len(self.paths))

    def test_missing_case_is_not_skipped(self):
        removed = 'results/mg-soc-scf/evidence.json'
        (self.root / removed).unlink()
        with self.assertRaisesRegex(ValueError, 'Missing public prerequisite'):
            publication.check_paths(self.root, [p for p in self.paths if p != removed])

    def test_broken_link_rejected(self):
        self.write('README.md', '[evidence](missing.json)\n')
        with self.assertRaisesRegex(ValueError, 'Broken relative link'):
            publication.check_paths(self.root, self.paths)

    def test_local_handoff_rejected(self):
        path = 'HANDOFF_TO_GPT56PRO.md'
        self.write(path, 'Synthetic process note\n')
        with self.assertRaisesRegex(ValueError, 'Local/process artifact'):
            publication.check_paths(self.root, self.paths + [path])

    def test_private_path_does_not_echo_private_content(self):
        value = '/' + 'Users' + '/synthetic-private-owner/private-file'
        self.write('README.md', value)
        with self.assertRaises(ValueError) as error:
            publication.check_paths(self.root, self.paths)
        self.assertNotIn('synthetic-private-owner', str(error.exception))

    def test_frozen_hash_mismatch_rejected(self):
        self.write('frozen.txt', 'synthetic changed bytes')
        self.write('results/shared/frozen-science.json', json.dumps({
            'base_commit': publication.BASE, 'sha256': {'frozen.txt': '0' * 64}}))
        with self.assertRaisesRegex(ValueError, 'Frozen scientific file changed'):
            publication.check_frozen(self.root)

    def test_prepared_cannot_become_executed(self):
        self.write('benchmarks/mg-soc-fermi/parameters.json', json.dumps({
            'qe_soc_input_status': 'PREPARED_NOT_EXECUTED', 'qe_soc_benchmark_status': 'PASS'}))
        with self.assertRaises(AssertionError):
            publication.check_status(self.root)


if __name__ == '__main__':
    unittest.main()
