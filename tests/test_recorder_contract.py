"""Recorder protocol/publication regressions using temporary synthetic workers.

The first five cases retain the independent review's assertions. These fixtures
do not load Julia or validate an environment, pseudopotential, or physical result.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'contract_recorder', Path(__file__).resolve().parents[1] / 'scripts/run_recorded.py')
recorder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recorder)


def valid_protocol():
    # Synthetic protocol fixture; not an assertion of a real environment or UPF.
    return dict(schema_version=2, mode='fr-nc', parse_status='PASS',
                metadata_validation_status='PASS',
                dftk_construction_status='EXPECTED_SOC_REJECTION',
                overall_status='PASS', exit_code=0, reasons=[],
                environment={'status': 'PASS', 'manifest_sha256': '0' * 64},
                input={'sha256': '0' * 64})


def invoke(payload, *, action='inspect', process_exit=0, render_error=False,
           summary_write_error=False, disk_error=False):
    """Exercise main, process exit, and persisted output in an isolated directory."""
    with tempfile.TemporaryDirectory(prefix='phase4a1-contract-') as td:
        root = Path(td)
        bindir = root / 'bin'
        bindir.mkdir()
        worker = bindir / 'julia'
        calls = root / 'worker-invocations'
        worker.write_text('#!' + sys.executable + '\nimport sys\nwith open(' +
                          repr(str(calls)) + ", 'a') as calls: calls.write('called\\n')\nprint(" +
                          repr(json.dumps(payload)) + ')\nsys.exit(' + str(process_exit) + ')\n')
        worker.chmod(0o755)
        stdout, stderr = io.StringIO(), io.StringIO()
        observations = dict(summary_failures=0, status_before_summary=[],
                            summary_ready_before_pass=[])
        original_write, original_replace = Path.write_text, Path.replace

        def write_text(path, data, *args, **kwargs):
            if disk_error:
                raise OSError('Synthetic disk write failure')
            if path.name.startswith('summary.md') and '- Status: `PASS`' in data:
                current = path.parent / 'result.json'
                observations['status_before_summary'].append(
                    json.loads(current.read_text())['overall_status'] if current.exists() else None)
                if summary_write_error:
                    observations['summary_failures'] += 1
                    raise OSError('Synthetic summary write failure')
            return original_write(path, data, *args, **kwargs)

        def replace(path, target):
            target = Path(target)
            if target.name == 'result.json':
                result = json.loads(path.read_text())
                if result['overall_status'] == 'PASS':
                    summary = target.parent / 'summary.md'
                    observations['summary_ready_before_pass'].append(
                        summary.is_file() and '- Status: `PASS`' in summary.read_text())
            return original_replace(path, target)

        exit_code, error = None, None
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(recorder, 'ROOT', root))
            stack.enter_context(patch.object(recorder, 'ENV_DIR', root / 'environment/workbench'))
            stack.enter_context(patch.dict(os.environ, {
                'PATH': str(bindir) + os.pathsep + os.environ.get('PATH', '')}))
            stack.enter_context(contextlib.redirect_stdout(stdout))
            stack.enter_context(contextlib.redirect_stderr(stderr))
            stack.enter_context(patch.object(Path, 'write_text', write_text))
            stack.enter_context(patch.object(Path, 'replace', replace))
            if render_error:
                original_render = recorder.render_summary

                def render(record):
                    if record['overall_status'] == 'PASS':
                        observations['summary_failures'] += 1
                        raise AttributeError('Synthetic summary rendering failure')
                    return original_render(record)

                stack.enter_context(patch.object(recorder, 'render_summary', render))
            try:
                exit_code = recorder.main([action])
            except Exception as exc:
                error = f'{type(exc).__name__}: {exc}'
        records = [json.loads(p.read_text()) for p in (root / 'results/runs').glob('*/result.json')]
        return dict(exit_code=exit_code, error=error, records=records,
                    stdout=stdout.getvalue(), stderr=stderr.getvalue(),
                    worker_invocations=len(calls.read_text().splitlines()) if calls.exists() else 0,
                    **observations)


class RecorderContractTests(unittest.TestCase):
    def invoke(self, payload):
        result = invoke(payload)
        return result['exit_code'], result['error'], result['records']

    def assert_rejected(self, payload):
        exit_code, error, records = self.invoke(payload)
        self.assertIsNone(error, f'Uncaught exception; saved records: {records}; error: {error}')
        self.assertIsInstance(exit_code, int)
        self.assertNotEqual(exit_code, 0, f'Malformed protocol returned success: {records}')
        self.assertTrue(records, 'Current run should retain a non-success record')
        self.assertTrue(all(r['overall_status'] not in ('PASS', 'INFO_ONLY') for r in records),
                        f'Current run left a success-looking record: {records}')

    def test_failed_overall_cannot_exit_zero(self):
        payload = valid_protocol()
        payload.update(overall_status='FAIL', parse_status='FAIL',
                       metadata_validation_status='NOT_RUN', dftk_construction_status='NOT_RUN')
        self.assert_rejected(payload)

    def test_overall_pass_requires_successful_parse(self):
        payload = valid_protocol()
        payload['parse_status'] = 'FAIL'
        self.assert_rejected(payload)

    def test_unknown_schema_must_not_pass(self):
        payload = valid_protocol()
        payload['schema_version'] = 999
        self.assert_rejected(payload)

    def test_strict_inspection_cannot_accept_info_only(self):
        payload = valid_protocol()
        payload.update(mode='inspect', overall_status='INFO_ONLY',
                       metadata_validation_status='NOT_RUN', dftk_construction_status='NOT_RUN')
        self.assert_rejected(payload)

    def test_null_environment_cannot_leave_pass_or_crash(self):
        payload = valid_protocol()
        payload['environment'] = None
        self.assert_rejected(payload)


class AdditionalRecorderContractTests(unittest.TestCase):
    def assert_protocol_error(self, payload, **kwargs):
        result = invoke(payload, **kwargs)
        self.assertIsNone(result['error'], result)
        self.assertEqual(result['exit_code'], 9, result)
        self.assertEqual(len(result['records']), 1, result)
        saved = result['records'][0]
        self.assertEqual(saved['overall_status'], 'ERROR', result)
        self.assertEqual(saved['exit_code'], 9, result)
        self.assertTrue(saved['reasons'], result)
        # Safe fallback records must discard malformed worker objects entirely.
        self.assertNotIn('environment', saved)
        self.assertNotIn('input', saved)
        self.assertEqual(json.loads(result['stdout'])['overall_status'], 'ERROR')
        return result

    def test_valid_strict_success_publishes_after_summary(self):
        result = invoke(valid_protocol())
        self.assertIsNone(result['error'], result)
        self.assertEqual(result['exit_code'], 0, result)
        self.assertEqual(result['records'][0]['overall_status'], 'PASS')
        self.assertEqual(result['status_before_summary'], ['BLOCKED'])
        self.assertEqual(result['summary_ready_before_pass'], [True])

    def test_null_input_is_protocol_error(self):
        payload = valid_protocol()
        payload['input'] = None
        self.assert_protocol_error(payload)

    def test_environment_and_input_reject_wrong_types(self):
        for field in ('environment', 'input'):
            for invalid in ([], 'wrong type', 1, True):
                with self.subTest(field=field, invalid=invalid):
                    payload = valid_protocol()
                    payload[field] = invalid
                    self.assert_protocol_error(payload)

    def test_missing_environment_cannot_become_successful_empty_object(self):
        payload = valid_protocol()
        del payload['environment']
        self.assert_protocol_error(payload)

    def test_required_fields_types_and_status_values(self):
        invalid_fields = (
            ('schema_version', '2'), ('schema_version', True),
            ('exit_code', False), ('exit_code', '0'),
            ('parse_status', True), ('parse_status', 'UNKNOWN'),
            ('metadata_validation_status', []), ('metadata_validation_status', 'UNKNOWN'),
            ('dftk_construction_status', None), ('dftk_construction_status', 'UNSUPPORTED'),
            ('overall_status', {}), ('overall_status', 'UNKNOWN'),
            ('reasons', 'not a list'), ('reasons', [1]), ('mode', ['fr-nc']),
        )
        for field, invalid in invalid_fields:
            with self.subTest(field=field, invalid=invalid):
                payload = valid_protocol()
                payload[field] = invalid
                self.assert_protocol_error(payload)
        for field in ('schema_version', 'exit_code', 'parse_status',
                      'metadata_validation_status', 'dftk_construction_status',
                      'overall_status', 'reasons'):
            with self.subTest(missing=field):
                payload = valid_protocol()
                del payload[field]
                self.assert_protocol_error(payload)

    def test_nested_summary_fields_have_valid_types(self):
        for object_name, field, invalid in (
                ('environment', 'status', None), ('environment', 'status', 'UNKNOWN'),
                ('environment', 'manifest_sha256', []), ('input', 'sha256', {})):
            with self.subTest(object_name=object_name, field=field):
                payload = valid_protocol()
                payload[object_name][field] = invalid
                self.assert_protocol_error(payload)

    def test_strict_success_requires_all_stages_and_matching_mode(self):
        for field, invalid in (
                ('mode', 'inspect'), ('metadata_validation_status', 'NOT_RUN'),
                ('dftk_construction_status', 'NOT_RUN'),
                ('dftk_construction_status', 'UNEXPECTED_SUCCESS'),
                ('action', '--unit-tests')):
            with self.subTest(field=field, invalid=invalid):
                payload = valid_protocol()
                payload[field] = invalid
                self.assert_protocol_error(payload)
        payload = valid_protocol()
        payload['environment']['status'] = 'MISMATCH'
        self.assert_protocol_error(payload)

    def test_identity_tests_minimal_and_bootstrap_success_without_upf(self):
        for action, worker_action in (
                ('identity', '--check-environment'), ('tests', '--unit-tests'),
                ('minimal', '--upstream-minimal'), ('bootstrap', '--check-environment')):
            with self.subTest(action=action):
                payload = recorder.empty_result()
                payload.update(overall_status='PASS', exit_code=0, action=worker_action,
                               environment=valid_protocol()['environment'])
                result = invoke(payload, action=action)
                self.assertIsNone(result['error'], result)
                self.assertEqual(result['exit_code'], 0, result)
                saved = result['records'][0]
                self.assertEqual(saved['overall_status'], 'PASS')
                for field in ('parse_status', 'metadata_validation_status', 'dftk_construction_status'):
                    self.assertEqual(saved[field], 'NOT_RUN')

    def test_identity_success_cannot_substitute_for_tests_or_minimal(self):
        for action in ('tests', 'minimal'):
            with self.subTest(action=action):
                payload = recorder.empty_result()
                payload.update(overall_status='PASS', exit_code=0, action='--check-environment',
                               environment=valid_protocol()['environment'])
                self.assert_protocol_error(payload, action=action)
        self.assert_protocol_error(valid_protocol(), action='identity')

    def test_bootstrap_setup_failure_skips_identity(self):
        for worker_exit, expected_exit, expected_status in (
                (7, 7, 'BLOCKED'), (2, 9, 'ERROR'), (17, 9, 'ERROR')):
            with self.subTest(worker_exit=worker_exit):
                result = invoke(valid_protocol(), action='bootstrap', process_exit=worker_exit)
                self.assertIsNone(result['error'], result)
                self.assertEqual(result['exit_code'], expected_exit, result)
                self.assertEqual(result['worker_invocations'], 1, result)
                self.assertEqual(len(result['records']), 1, result)
                saved = result['records'][0]
                self.assertEqual(saved['overall_status'], expected_status)
                self.assertEqual(saved['worker_exit_code'], worker_exit)
                self.assertTrue(saved['reasons'])
                for field in ('environment', 'input', 'mode'):
                    self.assertNotIn(field, saved)

    def test_process_and_json_exit_codes_must_agree(self):
        self.assert_protocol_error(valid_protocol(), process_exit=7)

    def test_legitimate_failure_codes_are_preserved(self):
        cases = [
            (2, 'ARGUMENT_ERROR', 'NOT_RUN', 'NOT_RUN', 'NOT_RUN'),
            (3, 'FAIL', 'FAIL', 'NOT_RUN', 'NOT_RUN'),
            (4, 'FAIL', 'PASS', 'FAIL', 'NOT_RUN'),
            (4, 'UNSUPPORTED', 'PASS', 'UNSUPPORTED', 'NOT_RUN'),
            (5, 'FAIL', 'PASS', 'PASS', 'UNEXPECTED_ERROR'),
            (5, 'FAIL', 'PASS', 'PASS', 'UNEXPECTED_SUCCESS'),
            (6, 'ENVIRONMENT_MISMATCH', 'NOT_RUN', 'NOT_RUN', 'NOT_RUN'),
            (6, 'BLOCKED', 'NOT_RUN', 'NOT_RUN', 'NOT_RUN'),
            (7, 'BLOCKED', 'NOT_RUN', 'NOT_RUN', 'NOT_RUN'),
            (8, 'INPUT_MISMATCH', 'NOT_RUN', 'NOT_RUN', 'NOT_RUN'),
            (9, 'ERROR', 'NOT_RUN', 'NOT_RUN', 'NOT_RUN'),
        ]
        for code, overall, parsing, metadata, construction in cases:
            with self.subTest(code=code, overall=overall, construction=construction):
                payload = recorder.empty_result()
                payload.update(exit_code=code, overall_status=overall, parse_status=parsing,
                               metadata_validation_status=metadata,
                               dftk_construction_status=construction,
                               reasons=['Synthetic worker failure; no physics performed'])
                if code in (3, 4, 5, 8):
                    payload.update(environment=valid_protocol()['environment'],
                                   input=valid_protocol()['input'], mode='fr-nc')
                result = invoke(payload, process_exit=code)
                self.assertIsNone(result['error'], result)
                self.assertEqual(result['exit_code'], code, result)
                saved = result['records'][0]
                self.assertEqual(saved['overall_status'], overall)
                self.assertEqual(saved['worker_exit_code'], code)
                self.assertEqual(saved['reasons'], payload['reasons'])

    def test_non_upf_runtime_failure_can_omit_worker_action(self):
        for action in ('identity', 'tests', 'minimal'):
            with self.subTest(action=action):
                payload = recorder.empty_result()
                payload.update(overall_status='ERROR', exit_code=9,
                               environment=valid_protocol()['environment'],
                               reasons=['Synthetic runtime failure'])
                result = invoke(payload, action=action, process_exit=9)
                self.assertIsNone(result['error'], result)
                self.assertEqual(result['exit_code'], 9)
                self.assertEqual(result['records'][0]['reasons'], payload['reasons'])

    def test_summary_rendering_failure_replaces_current_record_with_fresh_error(self):
        result = self.assert_protocol_error(valid_protocol(), render_error=True)
        self.assertEqual(result['summary_failures'], 1)
        self.assertEqual(result['summary_ready_before_pass'], [])

    def test_summary_write_failure_never_publishes_current_pass(self):
        result = self.assert_protocol_error(valid_protocol(), summary_write_error=True)
        self.assertEqual(result['summary_failures'], 1)
        self.assertEqual(result['status_before_summary'], ['BLOCKED'])
        self.assertEqual(result['summary_ready_before_pass'], [])

    def test_unwritable_disk_reports_persistence_failure_without_crashing(self):
        result = invoke(valid_protocol(), disk_error=True)
        self.assertIsNone(result['error'], result)
        self.assertEqual(result['exit_code'], 9, result)
        self.assertEqual(result['records'], [])
        self.assertEqual(json.loads(result['stdout'])['overall_status'], 'ERROR')
        self.assertIn('persist', (result['stdout'] + result['stderr']).lower())


if __name__ == '__main__':
    unittest.main()
