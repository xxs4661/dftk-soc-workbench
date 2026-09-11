"""Synthetic publication-boundary tests; no Julia, UPF, SCF or QE execution."""
import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest import mock

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


    def current_status_fixture(self, execution='PASS', comparison='PASS', reasons=None):
        self.write('benchmarks/mg-soc-fermi/parameters.json', json.dumps({
            'qe_soc_input_status': 'PREPARED_NOT_EXECUTED', 'qe_soc_benchmark_status': 'NOT_RUN'}))
        self.write('benchmarks/mg-soc-fermi/checklist.md',
                   'Status: **PREPARED_NOT_EXECUTED**. QE SOC benchmark: **NOT RUN**.')
        data = {'qe_execution_status': execution, 'comparison_execution_status': comparison,
                'numerical_agreement_status': 'REVIEW_REQUIRED',
                'physical_convergence_status': 'NOT_ESTABLISHED',
                'historical_reference_status': 'HISTORICAL_REUSED',
                'process': {'exit_code': 0}, 'reasons': reasons or []}
        self.write('results/mg-soc-qe-comparison/evidence.json', json.dumps(data))
        text = ('[Current evidence](results/mg-soc-qe-comparison/evidence.json)\n'
                + 'QE execution: **' + execution + '**; REVIEW_REQUIRED; '
                + 'NOT_ESTABLISHED; HISTORICAL_REUSED.\n')
        for path in ('README.md', 'docs/status.md'):
            self.write(path, text)
        return data

    def historical_extractor(self):
        evidence = json.loads((ROOT / 'results/upf-acceptance/evidence.json').read_text())
        return dict(evidence['extractor'])

    def test_current_executed_and_historical_prepared_coexist(self):
        self.current_status_fixture()
        result = publication.check_status(self.root)
        self.assertEqual(result['current_qe_execution_status'], 'PASS')
        self.assertIn('PREPARED_NOT_EXECUTED', result['historical_preparation'])
        self.assertNotIn('NOT_RUN', (self.root / 'README.md').read_text())

    def test_unrelated_not_run_token_does_not_establish_current_state(self):
        self.current_status_fixture()
        self.write('README.md', 'An unrelated historical test is NOT_RUN.\n')
        with self.assertRaisesRegex(ValueError, 'Current QE state'):
            publication.check_status(self.root)

    def test_missing_new_case_is_not_skipped(self):
        removed = 'results/mg-soc-qe-comparison/evidence.json'
        (self.root / removed).unlink()
        with self.assertRaisesRegex(ValueError, 'Missing public prerequisite'):
            publication.check_paths(self.root, [p for p in self.paths if p != removed])

    def test_documentation_cannot_publish_wrong_current_status(self):
        self.current_status_fixture()
        path = self.root / 'README.md'
        path.write_text(path.read_text().replace('**PASS**', '**BLOCKED**'))
        with self.assertRaisesRegex(ValueError, 'Current QE state'):
            publication.check_status(self.root)

    def test_current_review_cannot_be_promoted_to_agreement(self):
        data = self.current_status_fixture()
        data['numerical_agreement_status'] = 'PASS'
        self.write('results/mg-soc-qe-comparison/evidence.json', json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'human review'):
            publication.check_status(self.root)

    def test_blocked_current_run_retains_reasons_and_no_comparison(self):
        self.current_status_fixture('BLOCKED', 'NOT_RUN', ['Synthetic unavailable executable'])
        result = publication.check_status(self.root)
        self.assertEqual(result['current_qe_execution_status'], 'BLOCKED')
        self.assertEqual(result['comparison_execution_status'], 'NOT_RUN')

    def test_blocked_current_run_cannot_reuse_comparison_pass(self):
        self.current_status_fixture('BLOCKED', 'PASS', ['Synthetic unavailable executable'])
        with self.assertRaisesRegex(ValueError, 'completed comparison'):
            publication.check_status(self.root)

    def test_failure_without_reason_is_rejected(self):
        self.current_status_fixture('FAIL', 'NOT_RUN')
        with self.assertRaisesRegex(ValueError, 'explicit reasons'):
            publication.check_status(self.root)

    def test_pass_cannot_hide_nonzero_process_exit(self):
        data = self.current_status_fixture()
        data['process']['exit_code'] = 9
        self.write('results/mg-soc-qe-comparison/evidence.json', json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'exit code'):
            publication.check_status(self.root)

    def test_fixed_historical_extractor_survives_current_verifier_change(self):
        extractor = self.historical_extractor()
        self.assertNotEqual(publication.digest(ROOT / extractor['path']), extractor['sha256'])
        result = publication.check_historical_upf_extractor(ROOT, extractor)
        self.assertEqual(result['commit'], 'ac22a64421c4a5444a399477b9a3215dbd913487')
        self.assertEqual(result['blob'], '062aa1660a9bc1366d1bdbe181c05885aa57e575')

    def test_current_verifier_hash_cannot_replace_historical_hash(self):
        extractor = self.historical_extractor()
        extractor['sha256'] = publication.digest(ROOT / extractor['path'])
        with self.assertRaisesRegex(ValueError, 'fixed Git blob'):
            publication.check_historical_upf_extractor(ROOT, extractor)

    def test_wrong_historical_extractor_path_rejected(self):
        extractor = self.historical_extractor()
        extractor['path'] = 'scripts/another-extractor.py'
        with self.assertRaisesRegex(ValueError, 'fixed binding'):
            publication.check_historical_upf_extractor(ROOT, extractor)

    def test_corrupt_historical_blob_rejected(self):
        with mock.patch.object(publication.subprocess, 'check_output', return_value=b'synthetic changed code'):
            with self.assertRaisesRegex(ValueError, 'fixed Git blob'):
                publication.check_historical_upf_extractor(ROOT, self.historical_extractor())

    def test_evolving_export_refuses_without_writing(self):
        before = {p: (self.root / p).read_bytes() for p in self.paths}
        with self.assertRaisesRegex(ValueError, publication.UPF_EXTRACTOR_COMMIT):
            publication.export_upf(self.root)
        self.assertEqual(before, {p: (self.root / p).read_bytes() for p in self.paths})


if __name__ == '__main__':
    unittest.main()
