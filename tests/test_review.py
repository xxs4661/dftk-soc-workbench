"""Synthetic public snapshots test the wrapper; no historical science is executed."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('public_review_wrapper', ROOT / 'scripts/review.py')
review = importlib.util.module_from_spec(spec); spec.loader.exec_module(review)

SYNTHETIC_CHECKER = '''import argparse,json,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--require-endpoints',action='store_true');a=p.parse_args()
r=Path(a.root);assert r.resolve()==r and a.require_endpoints
assert not (r/'.work').exists(), 'Private workspace was copied'
v=json.loads((r/'public.json').read_text());code=v.pop('synthetic_exit',0)
v.update(actual_root=str(r),actual_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip(),marker=(r/'marker.txt').read_text())
print(json.dumps(v));print('SYNTHETIC retained native warning',file=sys.stderr);sys.exit(code)
'''


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='review-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.area = Path(self.temp.name).resolve(); self.repo = self.area / 'repo'; self.repo.mkdir()
        self.git('init', '-q', '-b', 'researcher-fixture')
        self.git('config', 'user.name', 'Synthetic fixture'); self.git('config', 'user.email', 'fixture@example.invalid')
        script = self.repo / review.CHECKER; script.parent.mkdir(parents=True); script.write_text(SYNTHETIC_CHECKER)
        self.payload = dict(replay_status='PASS', delivery_status='COMPLETE', end_to_end_status='PASS',
            time_status='PERFORMANCE_REVIEW_REQUIRED', physical_interpretation='REVIEW_REQUIRED',
            k6_budget_status='INSUFFICIENT_EVIDENCE', physical_convergence='NOT_ESTABLISHED',
            scope='SYNTHETIC public arithmetic only; no numerical worker', original_end_to_end_status='FAIL')
        (self.repo / 'public.json').write_text(json.dumps(self.payload)); (self.repo / 'marker.txt').write_text('historical')
        self.git('add', '.'); self.git('commit', '-qm', 'Synthetic historical snapshot')
        self.snapshot = self.git('rev-parse', 'HEAD')
        self.addCleanup(patch.stopall); patch.object(review, 'SNAPSHOT', self.snapshot).start()
        (self.repo / 'marker.txt').write_text('current user branch'); self.git('commit', '-qam', 'Synthetic current branch')
        (self.repo / '.work').mkdir(); (self.repo / '.work/private.txt').write_text('must never be copied or read')
        self.logs = self.area / 'new-logs'

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.PIPE, text=True).strip()

    def invoke(self, **kwargs):
        out = io.StringIO(); err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = review.review(self.repo, log_dir=self.logs, **kwargs)
        return code, out.getvalue(), err.getvalue()

    def test_real_local_clone_replays_exact_snapshot_and_cleans_only_owned_copy(self):
        sentinel = self.area / 'keep'; sentinel.write_text('user file')
        code, out, err = self.invoke()
        self.assertEqual(code, 0)
        native = json.loads((self.logs / 'checker.stdout').read_text())
        metadata = json.loads((self.logs / 'review.json').read_text())
        self.assertEqual(native['actual_head'], self.snapshot); self.assertEqual(native['marker'], 'historical')
        self.assertNotIn(self.repo, Path(native['actual_root']).parents)
        self.assertFalse(Path(native['actual_root']).exists()); self.assertTrue(metadata['temporary_copy_removed'])
        self.assertEqual(sentinel.read_text(), 'user file'); self.assertEqual(metadata['child_exit_code'], 0)
        self.assertIn('PERFORMANCE_REVIEW_REQUIRED', out); self.assertIn('INSUFFICIENT_EVIDENCE', out)
        self.assertIn('NOT_ESTABLISHED', out); self.assertIn('SYNTHETIC retained native warning', err)
        self.assertEqual(metadata['checker_command'][-1], '--require-endpoints')

    def test_metadata_write_failure_is_nonzero_and_preserves_failed_child_code(self):
        original_open = Path.open
        def fail_metadata(path, *args, **kwargs):
            if path.name == 'review.json':
                raise OSError('SYNTHETIC metadata persistence failure')
            return original_open(path, *args, **kwargs)
        for native_code in (0, 7):
            self.logs = self.area / ('logs-native-' + str(native_code))
            self.payload.update(synthetic_exit=native_code)
            (self.repo / 'public.json').write_text(json.dumps(self.payload))
            self.git('add', 'public.json'); self.git('commit', '-qm', 'Synthetic exit ' + str(native_code))
            with self.subTest(native_code=native_code), patch.object(review, 'SNAPSHOT', self.git('rev-parse', 'HEAD')), patch.object(Path, 'open', fail_metadata):
                code, out, err = self.invoke()
            self.assertEqual(code, 2 if native_code == 0 else native_code)
            self.assertIn('Frozen checker exit: ' + str(native_code), out)
            self.assertIn('SYNTHETIC metadata persistence failure', err)
            native = json.loads((self.logs / 'checker.stdout').read_text())
            self.assertFalse(Path(native['actual_root']).exists())
            self.assertTrue((self.logs / 'checker.stderr').exists()); self.assertFalse((self.logs / 'review.json').exists())

    def test_additional_unmeasured_statuses_are_retained_in_success_summary(self):
        value = {'replay_status': 'PASS', 'measurement': {'rss': 'NOT_MEASURED', 'input': 'NOT_AVAILABLE', 'model': 'NOT_ASSESSED'}}
        child = subprocess.CompletedProcess([], 0, json.dumps(value).encode(), b'')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            review.present(child)
        summary = json.loads(output.getvalue().split('\n', 1)[1])
        self.assertEqual(summary['retained_qualifications'],
                         {'measurement.rss': 'NOT_MEASURED', 'measurement.input': 'NOT_AVAILABLE', 'measurement.model': 'NOT_ASSESSED'})

    def test_current_branch_index_dirty_files_and_refs_unchanged(self):
        (self.repo / 'marker.txt').write_text('staged user content'); self.git('add', 'marker.txt')
        (self.repo / 'marker.txt').write_text('unstaged user content')
        before = (self.git('symbolic-ref', 'HEAD'), self.git('show-ref'), self.git('status', '--porcelain'),
                  (self.repo / '.git/index').read_bytes(), (self.repo / 'marker.txt').read_bytes())
        self.assertEqual(self.invoke()[0], 0)
        after = (self.git('symbolic-ref', 'HEAD'), self.git('show-ref'), self.git('status', '--porcelain'),
                 (self.repo / '.git/index').read_bytes(), (self.repo / 'marker.txt').read_bytes())
        self.assertEqual(before, after)

    def test_child_failure_retains_actual_exit_and_all_reason_text(self):
        self.payload.update(replay_status='FAIL', synthetic_exit=7, reason='SYNTHETIC evidence mismatch', details={'reason':'nested original reason'})
        (self.repo / 'public.json').write_text(json.dumps(self.payload)); self.git('add', 'public.json'); self.git('commit', '-qm', 'Synthetic failure snapshot')
        with patch.object(review, 'SNAPSHOT', self.git('rev-parse', 'HEAD')):
            code, out, err = self.invoke()
        self.assertEqual(code, 7); self.assertIn('nested original reason', out); self.assertIn('SYNTHETIC evidence mismatch', out)
        meta = json.loads((self.logs / 'review.json').read_text())
        self.assertEqual(meta['child_exit_code'], 7); self.assertTrue(meta['temporary_copy_removed'])
        self.assertIn('SYNTHETIC retained native warning', err)

    def test_missing_history_does_not_select_current_head_or_create_copy(self):
        with patch.object(review, 'SNAPSHOT', '0' * 40):
            code, out, err = self.invoke()
        self.assertEqual(code, 2); self.assertIn('complete local repository history', err)
        meta = json.loads((self.logs / 'review.json').read_text())
        self.assertIsNone(meta['child_exit_code']); self.assertNotIn('temporary_copy', meta)
        self.assertFalse((self.logs / 'checker.stdout').exists())

    def test_shallow_history_requires_user_action_without_fetch(self):
        (self.repo / '.git/shallow').write_text(self.git('rev-parse', 'HEAD') + '\n')
        code, out, err = self.invoke(); self.assertEqual(code, 2); self.assertIn('does not fetch', err)
        meta = json.loads((self.logs / 'review.json').read_text())
        self.assertFalse(any('fetch' in step['command'] for step in meta['commands']))
        self.assertNotIn('temporary_copy', meta)

    def test_clone_start_failure_cleans_temporary_directory(self):
        original = subprocess.run
        def fail_clone(command, **kwargs):
            if 'clone' in command:
                raise OSError('SYNTHETIC clone failure')
            return original(command, **kwargs)
        with patch.object(review.subprocess, 'run', side_effect=fail_clone):
            self.assertEqual(self.invoke()[0], 2)
        meta = json.loads((self.logs / 'review.json').read_text())
        self.assertTrue(meta['temporary_copy_removed']); self.assertFalse(Path(meta['temporary_copy']).parent.exists())

    def test_existing_or_in_repository_log_path_does_not_modify_user_files(self):
        self.logs.mkdir(); sentinel = self.logs / 'checker.stdout'; sentinel.write_bytes(b'user bytes')
        before = list(self.logs.iterdir()); self.assertEqual(self.invoke()[0], 2)
        self.assertEqual(list(self.logs.iterdir()), before); self.assertEqual(sentinel.read_bytes(), b'user bytes')
        self.logs = self.repo / 'new-log-path'; self.assertEqual(self.invoke()[0], 2); self.assertFalse(self.logs.exists())

    def test_canonical_alias_and_in_repository_temp_setting_are_safe(self):
        alias = self.area / 'alias'; alias.symlink_to(self.repo, target_is_directory=True)
        with patch.object(review.tempfile, 'gettempdir', return_value=str(self.repo / '.work')):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(review.review(alias, log_dir=self.logs), 0)
        meta = json.loads((self.logs / 'review.json').read_text())
        self.assertNotIn(self.repo, Path(meta['temporary_copy']).parents); self.assertTrue(meta['temporary_copy_removed'])

    def test_prerequisite_and_unknown_case_do_not_invoke_git_or_create_logs(self):
        with patch.object(review.subprocess, 'run') as run:
            with patch.object(review.sys, 'version_info', (3, 11, 0)):
                self.assertEqual(self.invoke()[0], 2)
            self.assertEqual(self.invoke(case='unregistered')[0], 2)
            run.assert_not_called()
        self.assertFalse(self.logs.exists())

    def test_cli_unknown_case_and_help_are_real_nonnumerical_processes(self):
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/review.py'), 'unregistered'], capture_output=True)
        self.assertEqual(result.returncode, 2)
        help_result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/review.py'), '--help'], capture_output=True)
        self.assertEqual(help_result.returncode, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
