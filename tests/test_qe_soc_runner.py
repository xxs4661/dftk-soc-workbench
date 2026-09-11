"""Synthetic recorder tests: mocks/temporary workers are not physical QE evidence."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_qe_soc as runner


class RecorderTests(unittest.TestCase):
    def test_missing_prerequisite_does_not_reuse_old_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            parent = root / 'runs'
            old = parent / 'old'
            old.mkdir(parents=True)
            (old / 'result.json').write_text('{"qe_execution_status":"PASS"}')
            with contextlib.redirect_stdout(io.StringIO()):
                code = runner.run(root=root, parent=parent)
            self.assertNotEqual(code, 0)
            new = [p for p in parent.iterdir() if p != old]
            self.assertEqual(len(new), 1)
            self.assertNotEqual(json.loads((new[0] / 'result.json').read_text())['qe_execution_status'], 'PASS')
            self.assertEqual(json.loads((old / 'result.json').read_text())['qe_execution_status'], 'PASS')

    def test_distinct_failures_have_distinct_ids(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with contextlib.redirect_stdout(io.StringIO()):
                runner.run(root=root)
                runner.run(root=root)
            self.assertEqual(len(list((root / '.work/phase7a').iterdir())), 2)

    def test_actual_worker_nonzero_is_retained(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            code = runner.execute([sys.executable, '-c', 'raise SystemExit(7)'], directory, {})
            self.assertEqual(code, 7)
            self.assertEqual(json.loads((directory / 'process-exit.json').read_text())['exit_code'], 7)

    def test_zero_worker_alone_does_not_publish_success(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            self.assertEqual(runner.execute([sys.executable, '-c', 'print("JOB DONE")'], directory, {}), 0)
            self.assertFalse((directory / 'result.json').exists())
            self.assertFalse((directory / 'qe-result.json').exists())

    def test_unwritable_storage_reports_nonzero(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            root.joinpath('file').touch()
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = runner.run(root=root, parent=root / 'file')
            self.assertNotEqual(code, 0)
            self.assertIn('persistence failed', stderr.getvalue())
            self.assertNotEqual(json.loads(stdout.getvalue())['qe_execution_status'], 'PASS')

    def test_failed_start_receipt_stops_launcher_and_child(self):
        # Synthetic parent/child only: an I/O failure after spawn must leave no worker running.
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            ticker = directory / 'ticks'
            child = "import time; from pathlib import Path; p=Path('ticks'); " + \
                    "exec(\"while True:\\n p.write_text(str(time.time_ns())); time.sleep(.01)\")"
            parent = 'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",' + repr(child) + ']); time.sleep(30)'
            original = runner.write_json
            def fail_start(path, value):
                if path.name == 'process-start.json':
                    end = time.monotonic() + 3
                    while not ticker.exists() and time.monotonic() < end:
                        time.sleep(.01)
                    self.assertTrue(ticker.exists(), 'Synthetic child did not start')
                    raise OSError('synthetic receipt failure')
                return original(path, value)
            with mock.patch.object(runner, 'write_json', side_effect=fail_start):
                with self.assertRaisesRegex(OSError, 'synthetic receipt failure'):
                    runner.execute([sys.executable, '-c', parent], directory, {})
            before = ticker.read_text()
            time.sleep(.1)
            self.assertEqual(ticker.read_text(), before)
            receipt = json.loads((directory / 'process-exit.json').read_text())
            self.assertTrue(receipt['interrupted'])
            self.assertNotEqual(receipt['exit_code'], 0)

    def test_nonfinite_json_cannot_replace_existing_marker(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'result.json'
            runner.write_json(path, {'qe_execution_status': 'INCOMPLETE'})
            with self.assertRaises(ValueError):
                runner.write_json(path, {'qe_execution_status': 'PASS', 'energy': float('nan')})
            self.assertEqual(json.loads(path.read_text())['qe_execution_status'], 'INCOMPLETE')


if __name__ == '__main__':
    unittest.main()
