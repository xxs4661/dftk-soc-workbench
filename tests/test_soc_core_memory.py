"""Synthetic launcher contracts only: no Julia, context, SCF, QE or scientific data.

Each fixture is a disposable tiny Git repository. Its "checkpoint" and worker
JSON are explicitly synthetic protocol objects, never physical evidence.
"""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'synthetic_soc_memory_launcher', REPO / 'benchmarks/soc-core-memory-v1/run.py')
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


class StaticLauncherContract(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='synthetic-soc-memory-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.git('init', '--quiet', '--initial-branch=' + launcher.BRANCH)
        self.git('config', 'user.name', 'Synthetic protocol fixture')
        self.git('config', 'user.email', 'synthetic@example.invalid')
        self.put('.gitignore', '.work/\n')
        self.put('implementation.jl', '# Synthetic source bytes; never executed.\n')
        self.put('frozen.txt', 'Synthetic frozen input, no physical data.\n')
        self.git('add', '.')
        self.git('commit', '--quiet', '-m', 'Synthetic accepted base')
        self.base = self.git('rev-parse', 'HEAD')
        self.relative = 'benchmarks/soc-core-memory-v1'
        for name in ('README.md', 'plan.json', 'contract.json'):
            self.put(self.relative + '/' + name, '{}\n' if name.endswith('.json') else '# Synthetic plan\n')
        self.sources = dict(schema_version=1, base=self.base,
            reference_implementation=dict(git_commit=self.base,
                files={'implementation.jl': self.identity('implementation.jl')}),
            frozen_inputs_and_history={'frozen.txt': self.identity('frozen.txt')},
            historical_endpoints={})
        for label in ('B0', 'K4'):
            relative = '.work/synthetic-history/' + label
            self.put(relative + '/final.bin', 'SYNTHETIC CHECKPOINT BYTES ' + label)
            self.put(relative + '/result.json', '{}\n')
            self.sources['historical_endpoints'][label] = dict(
                directory=relative, status='HISTORICAL_REUSED',
                checkpoint_sha256=self.identity(relative + '/final.bin')['sha256'],
                checkpoint_bytes=self.identity(relative + '/final.bin')['bytes'],
                raw_result_sha256=self.identity(relative + '/result.json')['sha256'],
                execution_commit='a' * 40, publication_commit='b' * 40)
        self.put(self.relative + '/sources.json', json.dumps(self.sources))
        self.git('add', '.')
        self.git('commit', '--quiet', '-m', 'Synthetic frozen preparation')
        self.plan = self.git('rev-parse', 'HEAD')
        # A committed harmless harness makes exact-HEAD source tests concrete.
        self.put(self.relative + '/run.py', (REPO / self.relative / 'run.py').read_text())
        self.put(self.relative + '/measure.jl', '# Synthetic harness; never executed.\n')
        self.put(self.relative + '/memory.jl', '# Synthetic helper; never executed.\n')
        self.git('add', '.')
        self.git('commit', '--quiet', '-m', 'Synthetic execution source')
        self.head = self.git('rev-parse', 'HEAD')
        self.reference = self.root / '.work/phase9a/reference-tree'
        self.git('worktree', 'add', '--quiet', '--detach', str(self.reference), self.base)
        self.worker_calls = []
        self.native_code = 0
        self.worker_mutation = lambda value: value
        self.resource_mutation = lambda value: value
        self.after_worker = lambda directory: None
        self.omit_worker = False
        self.raw_worker = None
        for attribute, replacement in (
            ('BASE', self.base), ('PLAN', self.plan),
            ('execute', unittest.mock.Mock(side_effect=AssertionError('No real executor is allowed'))),
            ('ps_rows', lambda: [dict(pid=123, rss=1024)]),
            ('monitored_execute', self.synthetic_worker)):
            p = patch.object(launcher, attribute, replacement)
            p.start(); self.addCleanup(p.stop)
        p = patch.object(launcher.shutil, 'disk_usage', return_value=SimpleNamespace(free=100 * 1024**3))
        p.start(); self.addCleanup(p.stop)

    def git(self, *arguments, root=None):
        return subprocess.check_output(['git', '-C', str(root or self.root), *arguments],
                                       text=True, stderr=subprocess.PIPE).strip()

    def put(self, relative, contents):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        return path

    def identity(self, relative):
        data = (self.root / relative).read_bytes()
        return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())

    def synthetic_worker(self, executor, command, directory, env):
        self.worker_calls.append((command, directory, env))
        suite = command[command.index('--suite') + 1]
        value = dict(schema_version=1, phase='9A', suite=suite, run_id=directory.name,
            base_commit=self.base, preparation_commit=self.plan, execution_commit=self.head,
            execution_status='PASS' if self.native_code == 0 else 'FAIL',
            overall_status='PASS' if self.native_code == 0 else 'FAIL', exit_code=self.native_code,
            measurement_status='COMPLETE' if self.native_code == 0 else 'INCOMPLETE',
            backend='LEGACY_REFERENCE' if suite.startswith('REF-') else 'OWNED_CORE',
            environment={'status': 'PASS'}, parallelism={'julia': 1, 'blas': 1, 'fft': 1, 'mpi': 1},
            input={'historical_status': 'HISTORICAL_REUSED',
                'checkpoint_sha256': self.sources['historical_endpoints'][suite.split('-')[1]]['checkpoint_sha256']},
            measurements={}, outputs={}, live_memory={}, comparison_status='NOT_RUN')
        sample = dict(status='PASS', time_seconds=.01, allocated_bytes=1234,
                      gc_seconds=0., compile_seconds=0., recompile_seconds=0.)
        for operation in sorted(launcher.OPERATIONS):
            value['measurements'][operation] = dict(status='PASS', completed_samples=5,
                requested_samples=5, warmup_count=1, warmup=copy.deepcopy(sample),
                samples=[dict(sample, index=i) for i in range(1, 6)])
            path = directory / (operation + '.bin')
            path.write_bytes(('SYNTHETIC PROTOCOL OUTPUT, NOT NUMERICAL: ' + operation).encode())
            value['outputs'][operation] = dict(path=path.name, bytes=path.stat().st_size,
                                              sha256=launcher.sha(path))
        canonical = directory / 'inputs.bin'
        canonical.write_bytes(b'SYNTHETIC PROTOCOL INPUT, NOT PHYSICAL')
        value['canonical_inputs'] = dict(path=canonical.name, bytes=canonical.stat().st_size,
                                        sha256=launcher.sha(canonical))
        value['input_unchanged'] = dict(payload=True, rhs=True, checkpoint=True, original_result=True)
        value = self.worker_mutation(value)
        if not self.omit_worker:
            (directory / 'worker-result.json').write_text(
                self.raw_worker if self.raw_worker is not None else json.dumps(value))
        resource = self.resource_mutation(dict(schema_version=1, status='PASS',
            owned_process_cleanup_status='PASS', native_exit_code=self.native_code,
            peak_aggregate_rss_bytes=1024 * 1024, nonempty_samples=5,
            remaining_observed_processes=[], reason=None))
        (directory / 'resource.json').write_text(json.dumps(resource))
        (directory / 'process-start.json').write_text(json.dumps({'synthetic_only': True, 'pid': 123}))
        (directory / 'process-exit.json').write_text(json.dumps(dict(
            synthetic_only=True, exit_code=self.native_code, interrupted=False)))
        self.after_worker(directory)
        return self.native_code, resource

    def invoke(self, suite='REF-B0'):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = launcher.run(suite, sys.executable, root=self.root)
        state = json.loads(stdout.getvalue().splitlines()[-1])
        directory = self.root / state['directory']
        self.assertEqual(json.loads((directory / 'result.json').read_text())['overall_status'], state['overall_status'])
        self.assertEqual(code, state['exit_code'])
        return code, state, directory

    def assert_rejected(self, suite='REF-B0', *, started=False):
        code, state, directory = self.invoke(suite)
        self.assertNotEqual(code, 0)
        self.assertNotEqual(state['overall_status'], 'PASS')
        self.assertIs(state['worker_started'], started)
        self.assertNotEqual(json.loads((directory / 'result.json').read_text())['overall_status'], 'PASS')
        return state, directory

    def reset_synthetic_runs(self):
        area = self.root / '.work/phase9a/static'
        if area.exists(): shutil.rmtree(area)
        self.worker_calls.clear()

    def test_valid_ref_launch_is_synthetic_and_single_threaded(self):
        code, state, _ = self.invoke()
        self.assertEqual(code, 0); self.assertEqual(state['overall_status'], 'PASS')
        command, _, env = self.worker_calls[0]
        self.assertIn('--startup-file=no', command)
        self.assertEqual(command[command.index('--code-root') + 1], str(self.reference))
        for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'JULIA_NUM_THREADS'):
            self.assertEqual(env[key], '1')
        launcher.execute.assert_not_called()

    def test_preparation_authenticates_exact_git_bytes(self):
        self.assertEqual(launcher.preparation(self.root), self.sources)
        path = self.root / self.relative / 'contract.json'
        path.write_text(path.read_text() + ' ')
        with self.assertRaises(ValueError): launcher.preparation(self.root)

    def test_frozen_source_hash_size_and_symlink_are_rejected(self):
        path = self.root / 'frozen.txt'; original = path.read_bytes()
        for replacement in (b'x' * len(original), original + b'x'):
            path.write_bytes(replacement)
            with self.subTest(replacement=replacement), self.assertRaises(ValueError): launcher.preparation(self.root)
        path.write_bytes(original); alternate = self.put('.work/identical.txt', original.decode())
        path.unlink(); path.symlink_to(alternate)
        with self.assertRaises(ValueError): launcher.preparation(self.root)

    def test_dirty_execution_checkout_refused_before_worker(self):
        self.put('untracked-user-file.txt', 'preserve me')
        self.assert_rejected()
        self.assertFalse(self.worker_calls)
        self.assertEqual((self.root / 'untracked-user-file.txt').read_text(), 'preserve me')

    def test_wrong_branch_and_missing_base_refused(self):
        self.git('branch', '-m', 'synthetic-wrong-branch'); self.assert_rejected()
        self.git('branch', '-m', launcher.BRANCH)
        with patch.object(launcher, 'BASE', 'f' * 40): self.assert_rejected()
        self.assertFalse(self.worker_calls)

    def test_reference_requires_exact_clean_base(self):
        self.git('checkout', '--quiet', self.plan, root=self.reference)
        self.assert_rejected(); self.assertFalse(self.worker_calls)
        self.git('checkout', '--quiet', self.base, root=self.reference)
        (self.reference / 'implementation.jl').write_text('# changed synthetic reference\n')
        self.assert_rejected(); self.assertFalse(self.worker_calls)

    def test_reference_source_binding_is_checked(self):
        bad = copy.deepcopy(self.sources)
        bad['reference_implementation']['files']['implementation.jl']['sha256'] = 'f' * 64
        with patch.object(launcher, 'preparation', return_value=bad): self.assert_rejected()
        self.assertFalse(self.worker_calls)

    def test_missing_checkpoint_and_disk_reserve_fail_before_start(self):
        path = self.root / self.sources['historical_endpoints']['B0']['directory'] / 'final.bin'
        raw = path.read_bytes(); path.unlink(); self.assert_rejected(); path.write_bytes(raw)
        with patch.object(launcher.shutil, 'disk_usage', return_value=SimpleNamespace(free=1)):
            self.assert_rejected()
        self.assertFalse(self.worker_calls)

    def test_missing_rss_observer_and_existing_lock_refuse_worker(self):
        with patch.object(launcher, 'ps_rows', side_effect=RuntimeError('synthetic missing observer')):
            self.assert_rejected()
        lock = self.put('.work/phase9a/static/active.json', '{"run_id":"another-owner"}')
        before = lock.read_bytes(); self.assert_rejected()
        self.assertEqual(lock.read_bytes(), before); self.assertFalse(self.worker_calls)

    def test_worker_native_nonzero_is_retained_not_pass(self):
        self.native_code = 17
        state, _ = self.assert_rejected(started=True)
        self.assertEqual(state['process_exit_code'], 17)
        self.assertEqual(state['resource']['native_exit_code'], 17)

    def test_negative_native_signal_is_retained(self):
        self.native_code = -15
        state, _ = self.assert_rejected(started=True)
        self.assertEqual(state['process_exit_code'], -15)

    def test_false_pass_exit_or_suite_is_rejected(self):
        for updates in ({'overall_status': 'FAIL'}, {'exit_code': 3}, {'exit_code': False}, {'suite': 'REF-K4'}):
            self.reset_synthetic_runs()
            self.worker_mutation = lambda value, updates=updates: dict(value, **updates)
            with self.subTest(updates=updates): self.assert_rejected(started=True)

    def test_worker_schema_identity_and_stage_contract(self):
        for updates in ({'schema_version': 999}, {'schema_version': True}, {'phase': '8C'},
                        {'run_id': 'old-success'}, {'execution_commit': 'f' * 40},
                        {'base_commit': 'f' * 40}, {'preparation_commit': 'f' * 40},
                        {'execution_status': 'FAIL'}, {'measurement_status': 'INCOMPLETE'},
                        {'environment': None}, {'environment': {'status': 'FAIL'}}):
            self.reset_synthetic_runs()
            self.worker_mutation = lambda value, updates=updates: dict(value, **updates)
            with self.subTest(updates=updates): self.assert_rejected(started=True)

    def test_missing_or_malformed_worker_is_current_failure(self):
        self.omit_worker = True; self.assert_rejected(started=True)
        self.reset_synthetic_runs(); self.omit_worker = False; self.raw_worker = '{malformed'
        self.assert_rejected(started=True)

    def test_failed_rss_or_cleanup_blocks_pass(self):
        for updates in ({'status': 'RESOURCE_BLOCKED'}, {'owned_process_cleanup_status': 'UNCONFIRMED'}):
            self.reset_synthetic_runs()
            self.resource_mutation = lambda value, updates=updates: dict(value, **updates)
            with self.subTest(updates=updates): self.assert_rejected(started=True)

    def test_resource_claim_requires_real_sample_budget_and_exit_consistency(self):
        for updates in ({'peak_aggregate_rss_bytes': 8 * 1024**3}, {'peak_aggregate_rss_bytes': 0},
                        {'nonempty_samples': 0}, {'native_exit_code': 17}):
            self.reset_synthetic_runs()
            self.resource_mutation = lambda value, updates=updates: dict(value, **updates)
            with self.subTest(updates=updates): self.assert_rejected(started=True)

    def test_same_suite_is_never_restarted_after_worker_started(self):
        _, _, old = self.invoke(); old_bytes = (old / 'result.json').read_bytes()
        self.assert_rejected(); self.assertEqual(len(self.worker_calls), 1)
        self.assertEqual((old / 'result.json').read_bytes(), old_bytes)

    def test_failed_suite_is_never_restarted_or_replaced(self):
        self.native_code = 7; _, old = self.assert_rejected(started=True)
        old_bytes = (old / 'result.json').read_bytes(); self.native_code = 0
        self.assert_rejected(); self.assertEqual(len(self.worker_calls), 1)
        self.assertEqual((old / 'result.json').read_bytes(), old_bytes)

    def test_early_failed_preflight_kept_then_new_run_has_new_identity(self):
        with patch.object(launcher, 'ps_rows', side_effect=RuntimeError('synthetic missing observer')):
            _, old = self.assert_rejected()
        old_bytes = (old / 'result.json').read_bytes()
        code, _, new = self.invoke(); self.assertEqual(code, 0); self.assertNotEqual(old, new)
        self.assertEqual((old / 'result.json').read_bytes(), old_bytes)

    def test_only_prescribed_suite_sequence_is_allowed(self):
        for suite in ('REF-K4', 'CORE-B0', 'CORE-K4'):
            self.assert_rejected(suite)
        self.assertFalse(self.worker_calls)
        for suite in launcher.SUITES:
            code, _, _ = self.invoke(suite)
            self.assertEqual(code, 0)
        self.assertEqual(len(self.worker_calls), 4)

    def test_old_pass_without_bound_native_worker_is_not_a_prerequisite(self):
        self.put('.work/phase9a/static/old-ref/result.json', json.dumps(dict(
            schema_version=1, suite='REF-B0', run_id='old-ref', execution_commit=self.head,
            worker_started=True, overall_status='PASS', exit_code=0, process_exit_code=0)))
        self.assert_rejected('REF-K4'); self.assertFalse(self.worker_calls)

    def test_corrupt_prior_worker_cannot_supply_success_to_next_suite(self):
        _, _, old = self.invoke()
        path = old / 'worker-result.json'; value = json.loads(path.read_text())
        value['run_id'] = 'unrelated-old-run'; path.write_text(json.dumps(value))
        self.assert_rejected('REF-K4'); self.assertEqual(len(self.worker_calls), 1)

    def test_paired_static_suites_require_same_committed_harness(self):
        self.invoke(); self.git('commit', '--quiet', '--allow-empty', '-m', 'Synthetic different execution')
        self.assert_rejected('REF-K4'); self.assertEqual(len(self.worker_calls), 1)

    def test_execution_tree_mutation_during_worker_is_current_failure(self):
        self.after_worker = lambda directory: self.put('worker-changed-source.txt', 'synthetic mutation')
        self.assert_rejected(started=True)

    def test_reference_mutation_during_worker_is_current_failure(self):
        self.after_worker = lambda directory: (self.reference / 'implementation.jl').write_text('# mutation during synthetic worker\n')
        self.assert_rejected(started=True)

    def test_cleanup_metadata_error_cannot_hide_final_failure_record_or_native_exit(self):
        self.native_code = 23
        self.after_worker = lambda directory: (directory / 'resource.json').write_text('{bad cleanup JSON')
        state, directory = self.assert_rejected(started=True)
        self.assertEqual(state['process_exit_code'], 23)
        self.assertEqual(json.loads((directory / 'result.json').read_text())['process_exit_code'], 23)

    def test_incomplete_operations_samples_and_input_preservation_rejected(self):
        _, state, directory = self.invoke()
        good = json.loads((directory / 'worker-result.json').read_text())
        changes = (
            lambda value: value['measurements'].pop('pipeline'),
            lambda value: value['measurements']['FR_24'].update(completed_samples=4),
            lambda value: value['measurements']['FR_24'].update(warmup_count=0),
            lambda value: value['measurements']['FR_24']['samples'].pop(),
            lambda value: value['measurements']['FR_24']['samples'].reverse(),
            lambda value: value['measurements']['FR_24']['samples'][0].update(status='FAIL'),
            lambda value: value['measurements']['FR_24']['samples'][0].update(allocated_bytes=-1),
            lambda value: value['measurements']['FR_24']['samples'][0].update(time_seconds=float('nan')),
            lambda value: value['measurements']['FR_24']['warmup'].update(status='FAIL'),
            lambda value: value['input_unchanged'].update(checkpoint=False),
            lambda value: value['input_unchanged'].update(rhs=1),
            lambda value: value['input_unchanged'].pop('original_result'),
        )
        for index, change in enumerate(changes):
            value = copy.deepcopy(good); change(value)
            with self.subTest(index=index), self.assertRaises(ValueError):
                launcher.worker_contract(value, state, directory)

    def test_canonical_outputs_are_complete_confined_and_byte_bound(self):
        _, state, directory = self.invoke()
        good = json.loads((directory / 'worker-result.json').read_text())
        changes = (
            lambda value: value['outputs'].pop('energy'),
            lambda value: value['outputs']['density'].update(path='../density.bin'),
            lambda value: value['outputs']['density'].update(sha256='f' * 64),
            lambda value: value['outputs']['density'].update(bytes=0),
            lambda value: value.update(canonical_inputs=None),
        )
        for index, change in enumerate(changes):
            value = copy.deepcopy(good); change(value)
            with self.subTest(index=index), self.assertRaises(ValueError):
                launcher.worker_contract(value, state, directory)
        path = directory / good['outputs']['density']['path']; original = path.read_bytes()
        path.write_bytes(original + b'changed')
        with self.assertRaises(ValueError): launcher.worker_contract(good, state, directory)
        path.unlink(); alternate = directory / 'alternate.bin'; alternate.write_bytes(original)
        path.symlink_to(alternate)
        with self.assertRaises(ValueError): launcher.worker_contract(good, state, directory)

    def test_current_native_exit_and_resource_files_bind_before_pass(self):
        self.after_worker = lambda directory: (directory / 'process-exit.json').write_text(
            json.dumps(dict(exit_code=19, interrupted=False)))
        state, _ = self.assert_rejected(started=True)
        self.assertEqual(state['process_exit_code'], 19)
        self.reset_synthetic_runs()
        self.after_worker = lambda directory: (directory / 'resource.json').write_text(
            json.dumps(dict(status='RESOURCE_BLOCKED', owned_process_cleanup_status='PASS')))
        self.assert_rejected(started=True)

    def test_wrong_backend_or_boolean_parallelism_is_not_accepted(self):
        for updates in ({'backend': 'OWNED_CORE'},
                        {'parallelism': {'julia': True, 'blas': 1, 'fft': 1, 'mpi': 1}}):
            self.reset_synthetic_runs()
            self.worker_mutation = lambda value, updates=updates: dict(value, **updates)
            with self.subTest(updates=updates): self.assert_rejected(started=True)


if __name__ == '__main__':
    unittest.main()
