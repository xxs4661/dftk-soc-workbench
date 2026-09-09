"""Synthetic partial-delivery protocols; no real failure log or arrays used."""
import contextlib
import copy
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('delivery9a', ROOT / 'benchmarks/soc-core-memory-v1/replay_delivery.py')
m = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(m)
HASH = 'a' * 64
SOURCE = ('\n' * 328 + 'work_action = synthetic_fixture\nallowed = synthetic :isnothing(profile)\n').encode()


def endpoint_fixture():
    text = ('ERROR: LoadError: ParseError:\n# Error @ <workbench>/scripts/run_si_soc.jl:330:52\n'
            'work_action = synthetic_fixture\nallowed = synthetic :isnothing(profile)\n'
            'space required after `:` in `?` expression\n').encode()
    zipped = gzip.compress(text, mtime=0)
    descriptor = dict(path='results/soc-core-memory/endpoints/failure.txt.gz', sha256=hashlib.sha256(zipped).hexdigest(), bytes=len(zipped))
    native = dict(exit_code=1, interrupted=False)
    resource = dict(status='PASS', owned_process_cleanup_status='PASS', native_exit_code=1,
                    remaining_observed_processes=[], limit_bytes=8 * 1024**3, sample_interval_seconds=.1,
                    samples=31, nonempty_samples=31, peak_aggregate_rss_bytes=741703680, elapsed_seconds=3.7200854169932427)
    receipt = dict(run_id=m.RUN_ID, action='OPT-B0-SCF', backend='soc-core', execution_commit=m.EXECUTION,
                   execution_status='FAIL', failure_status='FAIL', worker_started=True,
                   exit_code=9, worker_exit_code=1, native_process=native, resource=resource, core_gate_sha256=HASH)
    scf = dict(status='FAIL', run_id=m.RUN_ID, formal_slot_claimed=True, formal_attempt=1, native_process_started=True,
               recorder_exit_code=9, native_exit_code=1, failure_stage='JULIA_PARSE_BEFORE_DRIVER_ENTRY',
               scf_status='NOT_STARTED', map_count=0, progress_records=0, worker_result_present=False,
               checkpoint_present=False, worker_environment_validation_status='NOT_REACHED',
               energy_density_occupation_and_gamma_results='NOT_AVAILABLE', receipt=receipt,
               launch_exit={'exit_code': 9}, launch_stdout_summary=dict(exit_code=9, worker_exit_code=1, execution_status='FAIL'),
               formal_slot_claim=dict(execution_commit=m.EXECUTION, run_id=m.RUN_ID),
               resource_samples=dict(columns=['elapsed_s', 'aggregate_rss_bytes', 'process_count'],
                                     rows=[[i / 10, 741703680 if i == 31 else 100 * i, 1] for i in range(1, 32)],
                                     sampled_peak_rss_bytes=741703680, observer_elapsed_seconds=3.7200854169932427),
               native_stderr=dict(path=descriptor['path'], compressed_sha256=descriptor['sha256'], compressed_bytes=len(zipped),
                                  public_text_sha256=hashlib.sha256(text).hexdigest(), public_text_bytes=len(text),
                                  public_text_lines=len(text.splitlines()), raw_text_sha256=HASH))
    gamma = dict(status='BLOCKED_PARENT', spectrum_status='NOT_RUN', formal_slot_claimed=False,
                 native_process_started=False, parent_run_id=m.RUN_ID, parent_status='FAIL',
                 run_id=None, recorder_exit_code=None, native_exit_code=None)
    record = dict(schema_version=1, phase='9A', execution_commit=m.EXECUTION,
                  base_commit=m.static.BASE, preparation_commit=m.static.PREPARATION,
                  static_gate={'sha256': HASH}, slots={'OPT-B0-SCF': scf, 'OPT-B0-GAMMA': gamma},
                  failed_driver_source=dict(path=m.DRIVER, execution_commit=m.EXECUTION,
                                            sha256=hashlib.sha256(SOURCE).hexdigest(), bytes=len(SOURCE), error_line=330, error_column=52),
                  raw_sources={'.work/phase9a/endpoints/' + m.RUN_ID + '/qe.stderr': {'sha256': HASH}})
    return record, zipped, descriptor


class EndpointFailureTests(unittest.TestCase):
    def setUp(self):
        self.record, self.zipped, self.descriptor = endpoint_fixture()
        self.patch = patch.object(m.static, 'git_bytes', return_value=SOURCE); self.patch.start(); self.addCleanup(self.patch.stop)

    def check(self):
        return m.endpoints_check(ROOT, self.record, self.zipped, self.descriptor, {'gate': {'sha256': HASH}})

    def test_original_failure_is_successfully_replayed_without_scf_pass(self):
        result = self.check()
        self.assertEqual(result['end_to_end_status'], 'FAIL')
        self.assertEqual((result['native_exit_code'], result['recorder_exit_code']), (1, 9))

    def test_any_scf_pass_claim_rejected(self):
        self.record['slots']['OPT-B0-SCF']['status'] = 'PASS'
        with self.assertRaises(ValueError): self.check()

    def test_swapped_or_boolean_exit_codes_rejected(self):
        for value in (0, 9, True):
            self.record['slots']['OPT-B0-SCF']['native_exit_code'] = value
            with self.assertRaises(ValueError): self.check()

    def test_unexecuted_gamma_needs_null_exit_and_no_claim(self):
        gamma = self.record['slots']['OPT-B0-GAMMA']
        for key, value in (('native_exit_code', 0), ('formal_slot_claimed', True), ('status', 'PASS')):
            saved = gamma[key]; gamma[key] = value
            with self.assertRaises(ValueError): self.check()
            gamma[key] = saved

    def test_fake_checkpoint_or_energy_is_rejected(self):
        scf = self.record['slots']['OPT-B0-SCF']; scf['checkpoint_present'] = True
        with self.assertRaises(ValueError): self.check()
        scf['checkpoint_present'] = False; scf['receipt']['internal_energy_ha'] = 0.
        with self.assertRaisesRegex(ValueError, 'Fabricated'): self.check()

    def test_fake_scf_progress_or_fresh_environment_rejected(self):
        scf = self.record['slots']['OPT-B0-SCF']; scf['map_count'] = 1
        with self.assertRaises(ValueError): self.check()
        scf['map_count'] = 0; scf['worker_environment_validation_status'] = 'PASS'
        with self.assertRaises(ValueError): self.check()

    def test_rss_samples_and_peak_must_agree(self):
        self.record['slots']['OPT-B0-SCF']['resource_samples']['rows'][-1][1] -= 1
        with self.assertRaisesRegex(ValueError, 'RSS arithmetic'): self.check()

    def test_missing_resource_sample_rejected(self):
        self.record['slots']['OPT-B0-SCF']['resource_samples']['rows'].pop()
        with self.assertRaises(ValueError): self.check()

    def test_count_type_and_spurious_checkpoint_hash_rejected(self):
        self.record['slots']['OPT-B0-SCF']['receipt']['resource']['samples'] = 31.0
        with self.assertRaises(ValueError): self.check()
        self.record['slots']['OPT-B0-SCF']['receipt']['resource']['samples'] = 31
        self.record['slots']['OPT-B0-SCF']['receipt']['checkpoint_sha256'] = HASH
        with self.assertRaisesRegex(ValueError, 'Fabricated'): self.check()

    def test_corrupt_or_wrong_native_error_text_rejected(self):
        self.zipped = b'not gzip'
        with self.assertRaises((ValueError, OSError)): self.check()

    def test_later_repaired_driver_cannot_replace_original_blob(self):
        self.patch.stop()
        with patch.object(m.static, 'git_bytes', return_value=SOURCE.replace(b':isnothing', b': isnothing')):
            with self.assertRaisesRegex(ValueError, 'Git bytes'): self.check()

    def test_source_commit_alias_rejected(self):
        self.record['failed_driver_source']['execution_commit'] = 'HEAD'
        with self.assertRaises(ValueError): self.check()

    def test_tests_metadata_preserves_real_failures(self):
        ledger = dict(schema_version=1, phase='9A', entries=[dict(exit_code=0, status='PASS', scope='Synthetic', assertions_or_tests=1)],
                      original_publication_checks=[dict(exit_code=1, status='FAIL', reason='Frozen boundary changed')])
        self.assertEqual(m.tests_check(ledger)['original_publication_failure_count'], 1)
        ledger['original_publication_checks'][0]['status'] = 'PASS'
        with self.assertRaises(ValueError): m.tests_check(ledger)


class PublicDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.public = self.root / 'results/soc-core-memory'; self.public.mkdir(parents=True)
        record, zipped, descriptor = endpoint_fixture(); self.zipped = zipped
        self.write('endpoints/failure.txt.gz', zipped)
        self.manifest = dict(schema_version=1, phase='9A', execution_commit=m.EXECUTION,
                             endpoint_stderr_gzip=self.desc('endpoints/failure.txt.gz'))
        statics = {key: dict(sha256=HASH) for key in ('gate', 'performance', 'replay_data')}
        geometry = dict(nk=216, ng_max=2138, sum_ng=457287, fft_size=[48] * 3, projectors_per_k=72, target_states=24, solver_columns=30)
        terms = m.budget.known_terms(geometry); code = Path(m.budget.__file__).read_bytes(); self.budget_code = code
        budget_path = 'benchmarks/soc-core-memory-v1/budget.py'; target = self.root / budget_path; target.parent.mkdir(parents=True); target.write_bytes(code)
        ledger = dict(schema_version=1, phase='9A', execution_commit=m.EXECUTION, geometry=geometry,
                      accounting_terms={k: {'bytes': v} for k, v in terms.items()}, known_terms_plus_retained_allowances_subtotal_bytes=sum(terms.values()),
                      hard_limit_bytes=8 * 1024**3, margin_bytes=2 * 1024**3,
                      original_legacy_estimate=dict(total_bytes=12614633984), status='INSUFFICIENT_EVIDENCE',
                      new_estimated_peak_bytes=None, subtotal_is_upper_bound=False, unpriced_or_unbounded=['Synthetic missing bound'],
                      DFTK_K6_SCF='NOT_RUN', DFTK_K6_context_created=False,
                      source_sha256={budget_path: hashlib.sha256(code).hexdigest()}, static_evidence_reference=statics)
        for key, value in (('static_evidence', statics), ('memory_budget', ledger), ('endpoints', record),
                           ('tests', dict(schema_version=1, phase='9A', entries=[dict(status='PASS', exit_code=0, scope='Synthetic', assertions_or_tests=1)]))):
            self.write(key + '.json', json.dumps(value).encode()); self.manifest[key] = self.desc(key + '.json')
        self.write('delivery-evidence.json', json.dumps(self.manifest).encode())
        self.addCleanup(patch.stopall)
        patch.object(m.static, 'git_bytes', side_effect=lambda root, commit, path: SOURCE if path == m.DRIVER else self.budget_code).start()
        patch.object(m.static, 'replay', return_value=dict(replay_exit_code=0, assessment_exit_code=0, assessment_status='PASS', execution_commit=m.EXECUTION, time_status='PERFORMANCE_REVIEW_REQUIRED')).start()

    def write(self, relative, data):
        path = self.public / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)

    def desc(self, relative):
        path = self.public / relative
        return dict(path=path.relative_to(self.root).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)

    def test_default_zero_means_replay_partial_not_endpoints_pass(self):
        result = m.run(self.root)
        self.assertEqual((result['exit_code'], result['delivery_status'], result['end_to_end_status']), (0, 'PARTIAL', 'FAIL'))
        self.assertEqual(result['k6_budget_status'], 'INSUFFICIENT_EVIDENCE')

    def test_strict_mode_exits_one_preserving_successful_replay(self):
        result = m.run(self.root, require_endpoints=True)
        self.assertEqual((result['exit_code'], result['replay_status'], result['end_to_end_status']), (1, 'PASS', 'FAIL'))

    def test_wrong_artifact_bytes_or_hash_rejected(self):
        self.write('tests.json', b'{}')
        with self.assertRaisesRegex(ValueError, 'bytes differ'): m.run(self.root)

    def test_path_escape_and_symlink_rejected(self):
        entry = self.desc('tests.json'); entry['path'] = '../tests.json'
        with self.assertRaises(ValueError): m.artifact(self.root, entry)
        link = self.public / 'link.json'; link.symlink_to(self.public / 'tests.json'); entry = self.desc('link.json')
        with self.assertRaises(ValueError): m.artifact(self.root, entry)

    def test_cli_modes_and_protocol_error(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.main(['--root', str(self.root)]), 0)
            self.assertEqual(m.main(['--root', str(self.root), '--require-endpoints']), 1)
            self.write('tests.json', b'{}')
            self.assertEqual(m.main(['--root', str(self.root)]), 2)


if __name__ == '__main__':
    unittest.main()
