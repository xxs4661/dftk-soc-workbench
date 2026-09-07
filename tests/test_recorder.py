"""Subprocess/output failures only; no physical inputs or fake scientific results."""
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

spec = importlib.util.spec_from_file_location('recorder', Path(__file__).resolve().parents[1] / 'scripts/run_recorded.py')
recorder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recorder)


class RecorderTests(unittest.TestCase):
    def run_worker(self, code, *, filter_error=False, log_error=False):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / 'worker.log'
            if log_error:
                log.mkdir()
            with patch.object(recorder, 'sanitize', side_effect=ValueError('filter failed')) if filter_error else contextlib.nullcontext():
                return recorder.execute([sys.executable, '-c', code], log, os.environ.copy())

    def test_nonzero_worker_never_passes(self):
        result = self.run_worker('import sys; sys.exit(17)')
        self.assertEqual(result['exit_code'], 9)
        self.assertEqual(result['worker_exit_code'], 17)
        self.assertNotEqual(result['overall_status'], 'PASS')

    def test_zero_without_json_fails(self):
        self.assertEqual(self.run_worker('pass')['exit_code'], 9)

    def test_invalid_json_fails(self):
        self.assertEqual(self.run_worker("print('not JSON')")['exit_code'], 9)

    def test_filter_failure_fails(self):
        self.assertEqual(self.run_worker('pass', filter_error=True)['exit_code'], 9)

    def test_log_write_failure_fails(self):
        self.assertEqual(self.run_worker('pass', log_error=True)['exit_code'], 9)

    def test_result_cannot_contradict_exit(self):
        payload = recorder.empty_result()
        payload.update(exit_code=0, overall_status='PASS')
        code = 'import sys; print(' + repr(json.dumps(payload)) + '); sys.exit(17)'
        self.assertEqual(self.run_worker(code)['exit_code'], 9)

    def test_two_early_failures_have_distinct_current_records(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(recorder, 'ROOT', Path(temp)):
                outputs = []
                for _ in range(2):
                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
                        code = recorder.main(['invalid-action'])
                    self.assertEqual(code, 2)
                    outputs.append(json.loads(stdout.getvalue()))
                self.assertNotEqual(outputs[0]['run_id'], outputs[1]['run_id'])
                for result in outputs:
                    saved = json.loads((Path(temp) / 'results/runs' / result['run_id'] / 'result.json').read_text())
                    self.assertEqual(saved['overall_status'], 'ARGUMENT_ERROR')
                    self.assertEqual(saved['parse_status'], 'NOT_RUN')


if __name__ == '__main__':
    unittest.main()
