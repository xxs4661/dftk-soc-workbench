"""Synthetic subprocess/receipt tests only; never run QE or a physical model."""
import contextlib
import io
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import run_qe_local_postprocess as runner
from test_qe_filplot import fixture, expectations

REPO = Path(__file__).resolve().parents[1]


class LocalPostprocessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)/'synthetic-repo'
        self.root.mkdir()
        self.parent = self.root/'.work/phase7e'
        self.parent.mkdir(parents=True)
        self.source = self.root/'synthetic-G40'
        for name in runner.REQUIRED:
            path = self.source/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('SYNTHETIC PROTOCOL BYTES ONLY: '+name+'\n')
        for name in runner.EXECUTION_SOURCES:
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO/name, path)
        (self.root/'frozen.txt').write_text('Synthetic frozen reference\n')
        self.git('init', '-q')
        self.git('config', 'user.name', 'Synthetic Fixture')
        self.git('config', 'user.email', 'synthetic@example.invalid')

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, stderr=subprocess.PIPE).decode().strip()

    def setup_case(self, mode='good'):
        launcher = self.root/'synthetic-worker'
        source = str(self.source/(runner.SAVE+'charge-density.dat'))
        text = ('#!'+sys.executable+'\n'
                '# SYNTHETIC WORKER: tests recorder protocol, not QE physics.\n'
                'from pathlib import Path\nimport sys\n'
                'mode='+repr(mode)+'\n'
                'text=Path("pp.in").read_text()\n'
                'plot=0 if "plot_num = 0" in text else 2\n'
                'payloads='+repr({0: fixture(0), 2: fixture(2)})+'\n'
                'print("Program POST-PROC v.7.5")\n'
                'if mode == "sourcechange": Path('+repr(source)+').write_text("changed")\n'
                'if mode == "copychange": Path("scratch/mg_soc_qe_v1.save/Mg.upf").write_text("changed")\n'
                'if mode == "failure": print("synthetic failure",file=sys.stderr);sys.exit(23)\n'
                'if mode != "nooutput":\n'
                '    payload=payloads[plot]\n'
                '    if mode == "truncated": payload=payload[:-30]\n'
                '    Path("charge.pp" if plot == 0 else "local-ionic.pp").write_text(payload)\n'
                'if mode == "fatal": print("Error in routine synthetic")\n'
                'if mode == "solver": print("Self-consistent Calculation")\n'
                'print("Note: IEEE_INVALID_FLAG IEEE_OVERFLOW_FLAG",file=sys.stderr)\n'
                'if mode != "nojob": print("JOB DONE.")\n')
        launcher.write_text(text)
        launcher.chmod(0o755)
        source_files = {p: {'sha256': runner.digest(self.source/p), 'bytes': (self.source/p).stat().st_size}
                        for p in runner.REQUIRED}
        h = runner.digest(launcher)
        identity = {'synthetic_fixture': True, 'pp_build_identity_status': 'PASS',
                    'historical_pw_verification_status': 'PASS', 'launcher_sha256': h,
                    'products': {p: {'sha256': h} for p in ('pp', 'pw')},
                    'shared_dependencies': {'synthetic-library': h}}
        identity.update({k: h for k in ('runner_sha256', 'package_project_sha256',
                        'artifacts_toml_sha256', 'wrapper_sha256', 'probe_script_sha256')})
        identity_path = self.root/'identity.json'
        identity_path.write_text(json.dumps(identity))
        plan = {'schema_version': 1, 'synthetic_fixture': True, 'source_run_id': runner.G40_RUN,
                'slots': {}, 'filplot_expected': {k: v for k, v in expectations().items() if k != 'unit'},
                'source_files': source_files, 'qe_identity': identity,
                'identity_path': 'identity.json', 'identity_sha256': runner.digest(identity_path)}
        plan['source_mapping'] = {'full_G40_snapshot_sha256': hashlib.sha256(
            json.dumps(runner.snapshot(self.source), sort_keys=True).encode()).hexdigest()}
        plan_dir = (self.root/runner.PLAN).parent
        plan_dir.mkdir(parents=True, exist_ok=True)
        for slot in ('P2', 'P0'):
            path = plan_dir/(slot+'.in')
            path.write_text(runner.input_text(slot))
            plan['slots'][slot] = {'input_path': str(path.relative_to(self.root)),
                                  'input_sha256': runner.digest(path), 'plot_num': 2 if slot == 'P2' else 0,
                                  'filplot': 'local-ionic.pp' if slot == 'P2' else 'charge.pp'}
        (self.root/runner.PLAN).write_text(json.dumps(plan))
        self.git('add', 'scripts', 'benchmarks', 'identity.json', 'frozen.txt', 'synthetic-worker')
        self.git('commit', '-qm', 'Synthetic protocol setup; no numerical evidence')
        prep = {'source_run_id': runner.G40_RUN, 'plan_sha256': runner.digest(self.root/runner.PLAN),
                'preparation_commit': self.git('rev-parse', 'HEAD'), 'launcher': str(launcher),
                'dependency_sha256': {str(launcher): runner.digest(launcher)},
                'environment': {k: '1' for k in runner.THREADS}, 'source_files': source_files,
                'protected_sources': {'G40': {'path': str(self.source), 'sha256': runner.snapshot(self.source)}},
                'frozen_public_sha256': {'frozen.txt': runner.digest(self.root/'frozen.txt')}}
        (self.parent/'preparation.json').write_text(json.dumps(prep))
        return prep, plan

    def run_slot(self, slot='P2'):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = runner.run_slot(slot, self.root)
        reported = json.loads(output.getvalue().splitlines()[-1])
        result = json.loads((Path(reported['directory'])/'result.json').read_text())
        self.assertEqual(code, reported['exit_code'])
        self.assertEqual(result['exit_code'], code)
        return code, result, Path(reported['directory'])

    def test_two_independent_synthetic_successes_and_read_only_sources(self):
        prep, _ = self.setup_case()
        results = [self.run_slot(s) for s in ('P2', 'P0')]
        for code, record, directory in results:
            self.assertEqual(code, 0)
            self.assertEqual(record['parse_status'], 'PASS')
            self.assertEqual(record['formal_call_count'], 1)
            self.assertEqual(record['warnings']['stderr']['ieee_flags'], ['IEEE_INVALID_FLAG', 'IEEE_OVERFLOW_FLAG'])
            self.assertEqual(runner.snapshot(self.source), prep['protected_sources']['G40']['sha256'])
            for rel in runner.REQUIRED:
                self.assertFalse((directory/rel).is_symlink())
                self.assertEqual((directory/rel).stat().st_nlink, 1)
                self.assertNotEqual((directory/rel).stat().st_ino, (self.source/rel).stat().st_ino)
        self.assertNotEqual(results[0][2], results[1][2])
        self.assertNotEqual((results[0][2]/(runner.SAVE+'Mg.upf')).stat().st_ino,
                            (results[1][2]/(runner.SAVE+'Mg.upf')).stat().st_ino)

    def test_p0_before_p2_has_no_formal_call(self):
        self.setup_case()
        code, record, _ = self.run_slot('P0')
        self.assertNotEqual(code, 0)
        self.assertEqual(record['formal_call_count'], 0)
        self.assertFalse((self.parent/'P0.claim.json').exists())

    def test_claim_consumed_once_old_pass_not_reused_or_overwritten(self):
        self.setup_case()
        _, first, directory = self.run_slot()
        before = (directory/'result.json').read_bytes()
        code, second, _ = self.run_slot()
        self.assertNotEqual(code, 0)
        self.assertEqual(second['formal_call_count'], 0)
        self.assertNotEqual(first['run_id'], second['run_id'])
        self.assertEqual((directory/'result.json').read_bytes(), before)

    def test_failed_p2_attempt_permits_p0_but_never_retries_p2(self):
        self.setup_case('failure')
        code, record, _ = self.run_slot()
        self.assertNotEqual(code, 0)
        self.assertEqual(record['process_exit_code'], 23)
        self.assertEqual(self.run_slot('P0')[1]['formal_call_count'], 1)
        self.assertEqual(self.run_slot('P2')[1]['formal_call_count'], 0)

    def test_process_exit_no_output_truncation_and_false_completion_fail(self):
        for mode in ('failure', 'nooutput', 'truncated', 'nojob', 'fatal', 'solver'):
            with self.subTest(mode=mode):
                # Isolated setup for each distinct synthetic requested attempt.
                self.tearDown(); self.setUp()
                self.setup_case(mode)
                code, record, directory = self.run_slot()
                self.assertNotEqual(code, 0)
                self.assertEqual(record['execution_status'], 'FAIL')
                self.assertEqual(record['formal_call_count'], 1)
                self.assertTrue((directory/'process-exit.json').exists())
                self.assertTrue((self.parent/'P2.claim.json').exists())

    def test_wrong_d40_c40_binding_and_wrong_hash_block_before_process(self):
        for mutation in ('D40', 'C40', 'source_hash', 'copy_receipt_hash'):
            with self.subTest(mutation=mutation):
                self.tearDown(); self.setUp()
                prep, _ = self.setup_case()
                if mutation in ('D40', 'C40'):
                    prep['source_run_id'] = 'synthetic-'+mutation
                elif mutation == 'source_hash':
                    (self.source/(runner.SAVE+'charge-density.dat')).write_text('same size wrong bytes'.ljust(100))
                else:
                    prep['source_files'][runner.SAVE+'charge-density.dat']['sha256'] = '0'*64
                (self.parent/'preparation.json').write_text(json.dumps(prep))
                code, record, directory = self.run_slot()
                self.assertNotEqual(code, 0)
                self.assertEqual(record['formal_call_count'], 0)
                self.assertFalse((directory/'process-start.json').exists())

    def test_source_and_controlled_copy_changes_are_recorded_without_reset(self):
        for mode, key in (('sourcechange', 'source_changes'), ('copychange', 'copy_changes')):
            with self.subTest(mode=mode):
                self.tearDown(); self.setUp()
                self.setup_case(mode)
                code, _, directory = self.run_slot()
                self.assertNotEqual(code, 0)
                record = json.loads((directory/'source-preservation.json').read_text())
                self.assertEqual(record['status'], 'FAIL')
                self.assertTrue(record[key])

    def test_changed_launcher_frozen_file_and_uncommitted_runner_block(self):
        for path in ('synthetic-worker', 'frozen.txt', 'scripts/run_qe_local_postprocess.py'):
            with self.subTest(path=path):
                self.tearDown(); self.setUp()
                self.setup_case()
                with (self.root/path).open('a') as stream: stream.write('\nchanged\n')
                code, record, _ = self.run_slot()
                self.assertNotEqual(code, 0)
                self.assertEqual(record['formal_call_count'], 0)

    def test_committed_plan_input_and_thread_settings_not_silently_changed(self):
        for mutation in ('plan', 'input', 'threads', 'identity'):
            with self.subTest(mutation=mutation):
                self.tearDown(); self.setUp()
                prep, plan = self.setup_case()
                if mutation == 'plan':
                    plan['source_run_id'] = 'wrong'
                    (self.root/runner.PLAN).write_text(json.dumps(plan))
                    prep['plan_sha256'] = runner.digest(self.root/runner.PLAN)
                elif mutation == 'input':
                    (self.root/plan['slots']['P2']['input_path']).write_text('&PLOT\n/\n')
                elif mutation == 'identity':
                    (self.root/'identity.json').write_text('{}')
                else:
                    prep['environment']['OMP_NUM_THREADS'] = '2'
                (self.parent/'preparation.json').write_text(json.dumps(prep))
                code, record, _ = self.run_slot()
                self.assertNotEqual(code, 0)
                self.assertEqual(record['formal_call_count'], 0)

    def test_persistence_failure_cannot_leave_current_pass(self):
        for stage in ('parsed', 'success', 'all'):
            with self.subTest(stage=stage):
                self.tearDown(); self.setUp()
                self.setup_case()
                original = runner.write_json
                def failing(path, value):
                    if (stage == 'all' or stage == 'parsed' and path.name == 'parsed-filplot.json'
                            or stage == 'success' and value.get('execution_status') == 'PASS'):
                        raise OSError('synthetic persistence failure')
                    return original(path, value)
                with patch.object(runner, 'write_json', side_effect=failing):
                    code, record, _ = self.run_slot()
                self.assertNotEqual(code, 0)
                self.assertEqual(record['execution_status'], 'FAIL')

    def test_symlink_source_refused_before_copy(self):
        prep, _ = self.setup_case()
        link = self.source/'unexpected-link'
        link.symlink_to(self.root/'frozen.txt')
        code, record, _ = self.run_slot()
        self.assertNotEqual(code, 0)
        self.assertEqual(record['formal_call_count'], 0)

    def test_inherited_environment_override_blocks_before_child(self):
        self.setup_case()
        with patch.dict(os.environ, {'JULIA_LOAD_PATH': '@:@stdlib'}):
            code, record, _ = self.run_slot()
        self.assertNotEqual(code, 0)
        self.assertEqual(record['formal_call_count'], 0)

    def test_self_consistent_but_uncommitted_source_snapshot_rejected(self):
        prep, _ = self.setup_case()
        (self.source/'unrequested-file').write_text('changed tree')
        prep['protected_sources']['G40']['sha256'] = runner.snapshot(self.source)
        (self.parent/'preparation.json').write_text(json.dumps(prep))
        code, record, _ = self.run_slot()
        self.assertNotEqual(code, 0)
        self.assertIn('detached from committed plan', record['reason'])
        self.assertEqual(record['formal_call_count'], 0)


if __name__ == '__main__':
    unittest.main()
