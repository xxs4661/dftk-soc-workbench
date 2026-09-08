"""Synthetic worker/recorder tests only: no Julia, QE, UPF or physical solve."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import run_si_qe as runner


class SiQeRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.runs = self.root/'.work/phase8a'
        self.pseudo = self.root/'synthetic-source.dat'
        self.pseudo.write_text('Synthetic recorder bytes. Not a UPF.')
        case_dir = self.root/runner.CASE_DIR
        case_dir.mkdir(parents=True)
        self.prepared = {'case': {'case': 'si-soc-splitting-v1'},
                         'source': {'sha256': runner.digest(self.pseudo)}, 'pseudo_path': str(self.pseudo),
                         'preparation_commit': runner.PREPARATION, 'execution_commit': 'a'*40,
                         'prepared_sha256': {}, 'frozen_sha256': {}, 'source_sha256': {}, 'upstream': {}}
        for name in ('qe-scf.in', 'qe-spectrum.in'):
            (case_dir/name).write_text('Synthetic recorder '+name+'\n')
            self.prepared['prepared_sha256'][runner.CASE_DIR+'/'+name] = runner.digest(case_dir/name)
        self.observed = {'status': 'PASS', 'numerical_executions': 0, 'dependency_sha256': {},
                         'qe_identity': {'selected_path': 'synthetic-worker'}}
        self.mock_frozen = patch.object(runner, 'frozen_inputs', return_value=self.prepared).start()
        self.mock_identity = patch.object(runner, 'identity', return_value=self.observed).start()
        self.mock_recheck = patch.object(runner, '_recheck').start()
        self.mock_execute = patch.object(runner, 'execute', side_effect=self.worker).start()
        self.mock_parse = patch.object(runner, 'parse_si_qe', side_effect=self.parsed).start()
        self.mock_env = patch.dict(runner.os.environ, {k: v for k, v in runner.os.environ.items()
                                                    if k not in runner.FORBIDDEN_ENV}, clear=True).start()
        self.addCleanup(patch.stopall)

    def worker(self, command, directory, env):
        save = directory/runner.SAVE
        save.mkdir(parents=True, exist_ok=True)
        for name, raw in [('charge-density.dat', b'synthetic charge'), ('data-file-schema.xml', b'<synthetic/>'),
                          ('Si_r.upf', self.pseudo.read_bytes())]:
            (save/name).write_bytes(raw)
        for i in range(1, 9): (save/f'wfc{i}.dat').write_text(f'synthetic orbital placeholder {i}')
        (directory/'qe.stdout').write_text('Synthetic worker, not QE.\n'
            'Parallel version (MPI), running on 1 processors\nMPI processes distributed on 1 nodes\n')
        (directory/'qe.stderr').write_text('')
        runner.write_json(directory/'process-exit.json', {'exit_code': 0, 'interrupted': False})
        return 0

    def parsed(self, xml, stdout, stderr, *, kind, case, process_exit_code):
        return {'schema_version': 1, 'case': 'si-soc-splitting-v1', 'kind': kind,
                'raw_sha256': {'xml': runner.digest(xml)}, 'scf': {'converged': True} if kind == 'scf' else None,
                'fermi_energy_ha': .1, 'warning_evidence': {'eigenvalues_not_converged': False},
                'eigensolver_status': 'REPORTED_THRESHOLD_AVAILABLE'}

    def run_action(self, action, name='new-run', parent=None):
        return runner.run(action, self.runs/name, parent=parent, root=self.root)

    def current(self, name='new-run'):
        return json.loads((self.runs/name/'result.json').read_text())

    def test_identity_queries_never_execute_numerical_worker(self):
        out = self.run_action('identity')
        self.assertEqual(out['execution_status'], 'PASS')
        self.assertEqual(out['numerical_executions'], 0)
        self.mock_execute.assert_not_called(); self.mock_parse.assert_not_called()
        self.assertFalse((self.root/'.work/phase8a/slots').exists())

    def test_valid_scf_durable_receipt_and_all_save_hashes(self):
        out = self.run_action('Q-SCF')
        self.assertEqual((out['execution_status'], out['exit_code'], out['process_exit_code']), ('PASS', 0, 0))
        self.assertEqual(out, self.current())
        self.assertEqual(len(out['save_files']), 11)
        self.assertTrue((self.root/'.work/phase8a/slots/Q-SCF.json').exists())
        parsed = json.loads((self.runs/'new-run/qe-result.json').read_text())
        self.assertEqual(parsed['run_id'], 'new-run')
        self.assertEqual(out['parsed_sha256'], runner.digest(self.runs/'new-run/qe-result.json'))

    def test_worker_failure_retains_actual_code_and_not_old_pass(self):
        self.mock_execute.side_effect = lambda *a: 7
        out = self.run_action('Q-SCF')
        self.assertEqual(out['exit_code'], 7); self.assertEqual(out['process_exit_code'], 7)
        self.assertEqual(out['execution_status'], 'FAIL')
        self.assertNotEqual(self.current()['execution_status'], 'PASS')
        self.mock_parse.assert_not_called()

    def test_signal_or_interrupt_preserves_raw_exit_receipt(self):
        def interrupted(command, directory, env):
            runner.write_json(directory/'process-exit.json', {'exit_code': -15, 'interrupted': True})
            raise KeyboardInterrupt('synthetic interrupt')
        self.mock_execute.side_effect = interrupted
        out = self.run_action('Q-SCF')
        self.assertEqual(out['process_exit_code'], -15); self.assertNotEqual(out['exit_code'], 0)
        self.assertEqual(self.current()['execution_status'], 'FAIL')

    def test_parse_failure_after_worker_zero_is_not_success(self):
        self.mock_parse.side_effect = ValueError('synthetic malformed XML')
        out = self.run_action('Q-SCF')
        self.assertEqual(out['process_exit_code'], 0); self.assertEqual(out['exit_code'], 9)
        self.assertEqual(self.current()['execution_status'], 'FAIL')

    def test_existing_directory_is_not_reused_or_overwritten(self):
        path = self.runs/'old'
        path.mkdir(parents=True); (path/'result.json').write_text('{"execution_status":"PASS","historical":true}\n')
        before = (path/'result.json').read_bytes()
        with contextlib.redirect_stderr(io.StringIO()): out = self.run_action('Q-SCF', name='old')
        self.assertNotEqual(out['exit_code'], 0); self.mock_execute.assert_not_called()
        self.assertEqual((path/'result.json').read_bytes(), before)

    def test_slot_cannot_be_repeated_even_to_new_directory(self):
        self.run_action('Q-SCF', name='first')
        out = self.run_action('Q-SCF', name='second')
        self.assertNotEqual(out['exit_code'], 0)
        self.assertEqual(self.mock_execute.call_count, 1)
        self.assertEqual(self.current('second')['execution_status'], 'BLOCKED')

    def test_formal_failure_still_consumes_slot(self):
        self.mock_execute.side_effect = lambda *args: 5
        self.run_action('Q-SCF', name='failed')
        out = self.run_action('Q-SCF', name='retry')
        self.assertNotEqual(out['exit_code'], 0); self.assertEqual(self.mock_execute.call_count, 1)

    def test_preflight_failure_does_not_launch_or_consume_numerical_slot(self):
        self.mock_identity.side_effect = ValueError('synthetic changed build')
        out = self.run_action('Q-SCF')
        self.assertEqual(out['execution_status'], 'BLOCKED')
        self.mock_execute.assert_not_called()
        self.assertFalse((self.root/'.work/phase8a/slots/Q-SCF.json').exists())

    def test_parent_required_and_wrong_action_rejected(self):
        out = self.run_action('Q-SPECTRUM')
        self.assertNotEqual(out['exit_code'], 0); self.mock_execute.assert_not_called()
        out = self.run_action('Q-SCF', name='other', parent=self.runs/'missing')
        self.assertNotEqual(out['exit_code'], 0); self.mock_execute.assert_not_called()

    def test_spectrum_uses_copied_bound_parent_and_preserves_source(self):
        self.run_action('Q-SCF', name='parent')
        parent = self.runs/'parent'
        before = runner.file_map(parent)
        out = self.run_action('Q-SPECTRUM', name='bands', parent=parent)
        self.assertEqual(out['execution_status'], 'PASS')
        self.assertEqual(out['source_preservation_status'], 'PASS')
        self.assertEqual(runner.file_map(parent), before)
        copied = self.runs/'bands'/runner.SAVE
        self.assertFalse(runner.os.path.samefile(parent/runner.SAVE/'charge-density.dat', copied/'charge-density.dat'))
        parsed = json.loads((self.runs/'bands/qe-result.json').read_text())
        self.assertEqual(parsed['source_scf_run_id'], 'parent')
        self.assertEqual(parsed['density_source_sha256'], runner.digest(parent/runner.SAVE/'charge-density.dat'))

    def test_parent_tamper_missing_save_and_wrong_current_receipt_rejected(self):
        self.run_action('Q-SCF', name='parent')
        parent = self.runs/'parent'
        (parent/runner.SAVE/'wfc1.dat').write_text('synthetic tamper')
        out = self.run_action('Q-SPECTRUM', name='badbands', parent=parent)
        self.assertEqual(out['execution_status'], 'BLOCKED')
        self.assertEqual(self.mock_execute.call_count, 1)

    def test_wrong_parent_success_code_cannot_be_swallowed(self):
        self.run_action('Q-SCF', name='parent')
        value = self.current('parent'); value['process_exit_code'] = 1
        runner.write_json(self.runs/'parent/result.json', value)
        out = self.run_action('Q-SPECTRUM', name='bands', parent=self.runs/'parent')
        self.assertNotEqual(out['exit_code'], 0); self.assertEqual(self.mock_execute.call_count, 1)

    def test_post_run_original_source_change_is_not_pass(self):
        self.run_action('Q-SCF', name='parent')
        def corrupt(command, directory, env):
            code = self.worker(command, directory, env)
            (self.runs/'parent'/runner.SAVE/'charge-density.dat').write_text('synthetic corrupted parent')
            return code
        self.mock_execute.side_effect = corrupt
        out = self.run_action('Q-SPECTRUM', name='bands', parent=self.runs/'parent')
        self.assertEqual(out['source_preservation_status'], 'FAIL')
        self.assertEqual(out['execution_status'], 'FAIL')
        self.assertNotEqual(self.current('bands')['execution_status'], 'PASS')

    def test_bands_must_not_write_feedback_charge(self):
        self.run_action('Q-SCF', name='parent')
        def wrong_charge(command, directory, env):
            code = self.worker(command, directory, env)
            (directory/runner.SAVE/'charge-density.dat').write_text('synthetic changed bands density')
            return code
        self.mock_execute.side_effect = wrong_charge
        out = self.run_action('Q-SPECTRUM', name='bands', parent=self.runs/'parent')
        self.assertEqual(out['execution_status'], 'FAIL')
        self.assertEqual(out['source_preservation_status'], 'PASS')

    def test_success_publication_exception_replaces_current_result_safely(self):
        original = runner.write_json
        def fail_success(path, value):
            if path.name == 'result.json' and value.get('execution_status') == 'PASS':
                raise OSError('synthetic result publication failure')
            return original(path, value)
        with patch.object(runner, 'write_json', side_effect=fail_success): out = self.run_action('Q-SCF')
        self.assertEqual(out['exit_code'], 9)
        self.assertEqual(self.current()['execution_status'], 'FAIL')
        self.assertEqual(json.loads((self.runs/'new-run/qe-result.json').read_text())['execution_status'], 'FAIL')

    def test_failure_to_write_any_record_is_explicit_nonzero(self):
        error_stream = io.StringIO()
        with patch.object(runner, 'write_json', side_effect=OSError('synthetic full disk')), contextlib.redirect_stderr(error_stream):
            out = self.run_action('Q-SCF')
        self.assertNotEqual(out['exit_code'], 0)
        self.assertIn('Persistence failure', error_stream.getvalue())
        self.mock_execute.assert_not_called()

    def test_wrong_native_mpi_count_rejected_after_zero_exit(self):
        def wrong_parallelism(command, directory, env):
            code = self.worker(command, directory, env)
            (directory/'qe.stdout').write_text('Parallel version (MPI), running on 2 processors\nMPI processes distributed on 1 nodes\n')
            return code
        self.mock_execute.side_effect = wrong_parallelism
        out = self.run_action('Q-SCF')
        self.assertEqual(out['execution_status'], 'FAIL')
        self.mock_parse.assert_not_called()

    def test_inherited_dependency_override_refused(self):
        with patch.dict(runner.os.environ, {'JULIA_PROJECT': 'synthetic-foreign-project'}):
            out = self.run_action('Q-SCF')
        self.assertEqual(out['execution_status'], 'BLOCKED'); self.mock_identity.assert_not_called()

    def test_symlink_save_rejected(self):
        source = self.root/'synthetic-save'; source.mkdir()
        (source/'alias').symlink_to(self.pseudo)
        with self.assertRaisesRegex(ValueError, 'Symlinks'): runner.file_map(source)

    def test_output_and_parent_are_confined_to_current_phase(self):
        for path in (self.root/'history', self.runs):
            with self.subTest(path=path), contextlib.redirect_stderr(io.StringIO()):
                out = runner.run('Q-SCF', path, root=self.root)
            self.assertNotEqual(out['exit_code'], 0)
        with contextlib.redirect_stderr(io.StringIO()):
            out = self.run_action('Q-SPECTRUM', parent=self.root/'historical-parent')
        self.assertNotEqual(out['exit_code'], 0)
        self.mock_execute.assert_not_called()

    def test_dirty_or_changed_execution_head_rejected(self):
        for responses in ((b'a'*40+b'\n', b' M synthetic.py\n'), (b'b'*40+b'\n',)):
            with patch.object(runner, 'git', side_effect=responses), self.assertRaises(ValueError):
                runner.clean_execution(self.root, 'a'*40)

    def test_parent_execution_commit_and_code_hash_must_match(self):
        self.run_action('Q-SCF', name='parent')
        before = self.current('parent')
        for key, value in [('execution_commit', 'b'*40), ('executed_source_sha256', {'wrong.py': '0'*64})]:
            changed = dict(before, **{key: value})
            runner.write_json(self.runs/'parent/result.json', changed)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'execution commit/source'):
                runner.bind_parent(self.runs/'parent', self.prepared)


if __name__ == '__main__':
    unittest.main()
