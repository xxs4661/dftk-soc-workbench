"""Synthetic public-record protocol tests; no physical density/context is loaded."""
import contextlib
import copy
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('validation_local_replay', ROOT / 'benchmarks/soc-validation-local-v1/replay.py')
REPLAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPLAY)


class BlockedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-local-replay-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.result = self.root / 'results/soc-validation-local'
        self.result.mkdir(parents=True)
        # Copy only the already public metadata fixture. No UPF, density export,
        # checkpoint, real process output or actual benchmark result is read.
        self.fixture = json.loads((ROOT / REPLAY.FIXTURE).read_text())
        self.write_json(REPLAY.FIXTURE, self.fixture)
        self.record = dict(
            schema_version=1, experiment=REPLAY.EXPERIMENT, status='BLOCKED_RESOURCE_OBSERVATION',
            branch=REPLAY.BRANCH, base_commit=REPLAY.BASE, reference_commit=REPLAY.REFERENCE,
            failed_candidate_execution_commit=REPLAY.OLD_EXECUTION,
            preparation_commit='a' * 40, execution_commit='b' * 40,
            static_processes_started=0,
            slots=[dict(slot_id=slot, status='NOT_RUN') for slot in REPLAY.SLOTS],
            candidate_status='NO_CANDIDATE_SELECTED', local_target_status='NOT_ASSESSED',
            counts_status='NOT_MEASURED', actual_types_status='NOT_OBSERVED',
            fresh_numerical_results_status='NOT_RUN', artifacts={}, checks=[],
            blocker=dict(operation='PROCESS_OBSERVATION', exit_code=127,
                         reason='SYNTHETIC permission-denied protocol fixture, not an actual process probe'),
            resource_observer_exit=127,
            limitations=['SYNTHETIC protocol fixture; no context, worker, actual type or performance observation.'])
        self.record['artifacts']['fixture'] = self.descriptor(REPLAY.FIXTURE)
        for label, header in REPLAY.HEADERS.items():
            stream = io.StringIO(); csv.writer(stream).writerow(header)
            relative = 'results/soc-validation-local/' + label + '.csv'
            (self.root / relative).write_text(stream.getvalue())
            self.record['artifacts'][label] = self.descriptor(relative)
        log = 'results/soc-validation-local/synthetic-check.txt'
        (self.root / log).write_text('SYNTHETIC check output, no command actually ran.\n')
        self.record['checks'] = [dict(name='synthetic-preparation', scope='NONPHYSICAL_PREPARATION',
            exit_code=0, status='PASS', log_path=log, log_sha256=self.descriptor(log)['sha256'])]
        self.save()

    def write_json(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, allow_nan=False) + '\n')

    def descriptor(self, relative):
        return dict(path=relative, sha256=hashlib.sha256((self.root / relative).read_bytes()).hexdigest())

    def save(self):
        self.write_json(REPLAY.RECORD, self.record)

    def reject(self):
        self.save()
        with self.assertRaises(REPLAY.EvidenceError):
            REPLAY.audit(self.root)

    def fixture_change(self, action):
        action(self.fixture)
        self.write_json(REPLAY.FIXTURE, self.fixture)
        self.record['artifacts']['fixture'] = self.descriptor(REPLAY.FIXTURE)

    def test_consistent_blocked_record_has_no_measured_data(self):
        value = REPLAY.audit(self.root)
        self.assertEqual(value['evidence_status'], 'CONSISTENT')
        self.assertEqual(value['status'], 'BLOCKED_RESOURCE_OBSERVATION')
        self.assertEqual(value['table_rows'], {'types': 0, 'work': 0, 'samples': 0})
        self.assertEqual(value['strict_acceptance'], 'NOT_MET_NOT_RUN')

    def test_cli_default_zero_and_strict_one_are_distinct(self):
        actual = REPLAY.audit
        with mock.patch.object(REPLAY, 'audit', side_effect=lambda: actual(self.root)):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(REPLAY.main([]), 0)
                self.assertEqual(REPLAY.main(['--strict']), 1)

    def test_cli_corruption_returns_recorder_error_nine(self):
        with mock.patch.object(REPLAY, 'audit', side_effect=REPLAY.EvidenceError('synthetic corruption')):
            with contextlib.redirect_stderr(io.StringIO()) as output:
                self.assertEqual(REPLAY.main([]), 9)
        self.assertIn('synthetic corruption', output.getvalue())

    def test_measured_or_successful_status_cannot_replace_blocked_contract(self):
        for field, false_value in [('status', 'PASS'), ('candidate_status', 'C_SELECTED'),
                                   ('local_target_status', 'LOCAL_BENCHMARK_TARGET_MET'),
                                   ('counts_status', 'MEASURED'), ('actual_types_status', 'OBSERVED'),
                                   ('fresh_numerical_results_status', 'PASS')]:
            with self.subTest(field=field):
                original = self.record[field]
                self.record[field] = false_value; self.reject(); self.record[field] = original

    def test_static_started_zero_is_typed_not_boolean_or_unmeasured_number(self):
        for value in (False, True, 1, -1, 0.0, '0', None):
            with self.subTest(value=value):
                self.record['static_processes_started'] = value
                self.reject()

    def test_fake_counts_or_metrics_cannot_hide_in_extra_record_fields(self):
        for name, value in [('counts', {'hash_calls': 0}), ('samples', []),
                            ('completed_maps', 2), ('wall_seconds', 0.0), ('performance_ratio', 0.8)]:
            with self.subTest(name=name):
                self.record[name] = value; self.reject(); del self.record[name]

    def test_every_slot_must_remain_exactly_not_run(self):
        for index in range(5):
            with self.subTest(index=index):
                self.record['slots'][index]['status'] = 'PASS'; self.reject()
                self.record['slots'][index]['status'] = 'NOT_RUN'
        self.record['slots'][0]['samples'] = 0
        self.reject()

    def test_duplicate_missing_extra_or_reordered_slots_are_rejected(self):
        original = copy.deepcopy(self.record['slots'])
        cases = [original[:-1], original + [original[0]], list(reversed(original)),
                 [original[0], original[0], *original[2:]]]
        for slots in cases:
            with self.subTest(slots=slots):
                self.record['slots'] = slots; self.reject()

    def test_branch_and_all_three_fixed_source_versions_are_bound(self):
        for field in ('branch', 'base_commit', 'reference_commit', 'failed_candidate_execution_commit'):
            with self.subTest(field=field):
                original = self.record[field]
                self.record[field] = 'main' if field == 'branch' else '0' * 40
                self.reject(); self.record[field] = original

    def test_preparation_versions_require_complete_sha(self):
        for field in ('preparation_commit', 'execution_commit'):
            for value in (None, 'short123', 'A' * 40, 42):
                with self.subTest(field=field, value=value):
                    original = self.record[field]; self.record[field] = value
                    self.reject(); self.record[field] = original

    def test_schema_unknown_and_boolean_versions_fail(self):
        for value in (999, True, 1.0, '1'):
            self.record['schema_version'] = value; self.reject()

    def test_table_fake_data_rejected_even_after_hash_is_updated(self):
        for label, header in REPLAY.HEADERS.items():
            relative = self.record['artifacts'][label]['path']
            path = self.root / relative; original = path.read_bytes()
            with path.open('a') as stream:
                csv.writer(stream).writerow(['S'] + ['0'] * (len(header) - 1))
            self.record['artifacts'][label] = self.descriptor(relative)
            self.reject()
            path.write_bytes(original); self.record['artifacts'][label] = self.descriptor(relative)

    def test_missing_wrong_or_empty_csv_header_rejected(self):
        relative = self.record['artifacts']['types']['path']
        for value in ('', 'status\n', ','.join(REPLAY.HEADERS['types'][::-1]) + '\n'):
            (self.root / relative).write_text(value)
            self.record['artifacts']['types'] = self.descriptor(relative)
            self.reject()

    def test_each_artifact_checksum_is_actually_verified(self):
        for name in self.record['artifacts']:
            original = self.record['artifacts'][name]['sha256']
            self.record['artifacts'][name]['sha256'] = '0' * 64
            self.reject(); self.record['artifacts'][name]['sha256'] = original

    def test_artifact_path_cannot_escape_or_read_private_work(self):
        for value in ('../secret', '/tmp/secret', '.work/secret', REPLAY.RECORD):
            self.record['artifacts']['fixture']['path'] = value; self.reject()

    def test_symlinked_public_file_rejected(self):
        relative = self.record['artifacts']['types']['path']
        path = self.root / relative; target = path.with_name('same-types.csv')
        path.rename(target); path.symlink_to(target)
        self.reject()

    def test_fixed_historical_density_cannot_be_replaced(self):
        original = copy.deepcopy(self.fixture)
        for field, value in [('sha256', '1' * 64), ('map_index', 2), ('encoding', 'native Float64'),
                             ('count', 64), ('convergence', 'PASS'), ('fallback_uniform_density', 'SELECTED')]:
            with self.subTest(field=field):
                self.fixture = copy.deepcopy(original)
                self.fixture_change(lambda x: x['density'].__setitem__(field, value)); self.reject()

    def test_fixture_does_not_claim_new_actual_types_or_candidate(self):
        self.fixture_change(lambda x: x['type_shape_alias_comparability'].__setitem__('status', 'PASS'))
        self.reject()
        self.fixture['type_shape_alias_comparability']['status'] = 'NOT_OBSERVED'
        self.fixture_change(lambda x: x['implementations'].__setitem__('C', x['implementations']['F']))
        self.reject()

    def test_malformed_nested_fixture_fields_reject_without_attribute_error(self):
        original = copy.deepcopy(self.fixture)
        for key in ('case', 'density', 'pseudopotential', 'type_shape_alias_comparability', 'implementations'):
            for value in (None, [], 'not an object'):
                with self.subTest(key=key, value=value):
                    self.fixture = copy.deepcopy(original)
                    self.fixture_change(lambda x: x.__setitem__(key, value))
                    self.reject()

    def test_original_density_count_and_volume_are_not_renormalized(self):
        for field, value in [('volume_bohr3', 1), ('dvol_bohr3', 1), ('electron_count_python_fsum', 4)]:
            old = self.fixture['density'][field]
            self.fixture_change(lambda x: x['density'].__setitem__(field, value)); self.reject()
            self.fixture['density'][field] = old

    def test_check_exit_and_status_keep_real_failure(self):
        check = self.record['checks'][0]
        check.update(exit_code=127, status='BLOCKED'); self.save()
        self.assertEqual(REPLAY.audit(self.root)['status'], 'BLOCKED_RESOURCE_OBSERVATION')
        check['status'] = 'PASS'; self.reject()
        check.update(exit_code=0, status='FAIL'); self.reject()
        check.update(exit_code=False, status='PASS'); self.reject()

    def test_public_check_log_checksum_is_verified_when_present(self):
        (self.root / self.record['checks'][0]['log_path']).write_text('changed synthetic log\n')
        self.reject()

    def test_check_scope_and_duplicate_checks_fail(self):
        self.record['checks'][0]['scope'] = 'PHYSICAL_SCF_PASS'; self.reject()
        self.record['checks'][0]['scope'] = 'NONPHYSICAL_PREPARATION'
        self.record['checks'].append(copy.deepcopy(self.record['checks'][0])); self.reject()

    def test_resource_blocker_is_not_converted_to_success_or_other_stage(self):
        for field, value in [('operation', 'SCF'), ('exit_code', 0), ('exit_code', True), ('reason', '')]:
            original = self.record['blocker'][field]
            self.record['blocker'][field] = value; self.reject(); self.record['blocker'][field] = original
        self.record['resource_observer_exit'] = 0; self.reject()

    def test_unknown_fields_and_missing_limitations_fail(self):
        self.record['limitations'] = []; self.reject()
        self.record['limitations'] = ['synthetic limitation']
        self.record['success'] = True; self.reject()

    def test_duplicate_keys_and_nonfinite_json_are_rejected(self):
        for data in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
            with self.assertRaises(REPLAY.EvidenceError):
                REPLAY.json_bytes(data)


if __name__ == '__main__':
    unittest.main()
