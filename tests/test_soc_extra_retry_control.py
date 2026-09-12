"""Synthetic retry protocol tests; no Julia, pseudopotential or scientific run.

Git/source discovery and host/executable availability are fixture boundaries.
Production grant, registry, policy, slot, worker and recorder checks execute on
real temporary bytes. A fixture PASS is never evidence of a physical result.
"""
from contextlib import ExitStack, redirect_stdout
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


RETRY = load('extra_retry_control_test', 'benchmarks/soc-extra-v1/retry.py')
RUN = load('extra_retry_runner_test', 'benchmarks/soc-extra-v1/run.py')
FIXTURE = load('extra_retry_old_fixture', 'tests/test_soc_extra_runner.py')
GIB = 1024**3
EXECUTION = 'a' * 40


class SyntheticGrant(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.store = self.root / '.work/phase9a-extra'
        for part in ('authorizations', 'slots', 'runs'):
            (self.store / part).mkdir(parents=True)
        (self.root / '.git').mkdir()
        self.registry = self.root / '.git' / RETRY.REGISTRY_NAME
        self.path = self.store / 'authorizations/synthetic-once.json'
        self.plan = copy.deepcopy(RETRY.read(ROOT / RETRY.PLAN))
        case = self.root / self.plan['case']
        case.parent.mkdir(parents=True)
        case.write_bytes(b'SYNTHETIC case bytes: no physical interpretation\n')
        self.plan['case_sha256'] = RETRY.sha(case)
        pseudo = self.root / '.work/synthetic-upf-bytes'
        pseudo.write_bytes(b'SYNTHETIC protocol bytes, not a UPF\n')
        self.plan['upf_sha256'] = RETRY.sha(pseudo)
        source = self.root / 'benchmarks/si-soc-splitting-v1/source.json'
        source.parent.mkdir(parents=True)
        RUN.write(source, dict(local_path=pseudo.relative_to(self.root).as_posix(),
                               sha256=RETRY.sha(pseudo), bytes=pseudo.stat().st_size))
        RUN.write(self.root / RETRY.PLAN, self.plan)
        self.proof = {'executed_source_sha256': {'synthetic-source.jl': 'b' * 64},
                      'scope': 'SYNTHETIC discovery boundary only'}
        actual, checks = RETRY.policies(self.root, EXECUTION)
        self.auth = dict(schema_version=1, continuation_id=RETRY.ID,
                         source_start=RETRY.START, execution_commit=EXECUTION,
                         profile='K6', experiment='soc-extra-v1', core_selection='baseline',
                         numerical_change_requires_B0=False,
                         continuation_plan_sha256=RETRY.sha(self.root / RETRY.PLAN),
                         case_sha256=self.plan['case_sha256'], run_store=str(self.store),
                         executed_source_sha256=self.proof['executed_source_sha256'],
                         source_proof_sha256=RETRY.digest(self.proof),
                         resource_policies=actual, check_resource_policies=checks,
                         resource_policy_hashes={k: RETRY.digest(v) for k, v in actual.items()},
                         check_resource_policy_hashes={k: RETRY.digest(v) for k, v in checks.items()})
        RUN.write(self.path, self.auth)
        RUN.write(self.registry, dict(continuation_id=RETRY.ID, start=RETRY.START,
                                     execution_commit=EXECUTION, contract_sha256=RETRY.sha(self.path),
                                     run_store=str(self.store), workbench_root=str(self.root),
                                     allowed_starts=1))
        self.stack = self.enterContext(ExitStack())
        self.stack.enter_context(patch.object(RETRY, 'git', side_effect=self.synthetic_git))
        self.proof_call = self.stack.enter_context(patch.object(RETRY, 'source_proof', return_value=self.proof))
        self.stack.enter_context(patch.object(RETRY.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0)))
        self.stack.enter_context(patch.object(RUN.control, 'retry_module', return_value=RETRY))

    def synthetic_git(self, root, *args):
        answers = {('rev-parse', 'HEAD'): EXECUTION,
                   ('branch', '--show-current'): self.plan['branch'],
                   ('status', '--porcelain', '--untracked-files=all'): '',
                   ('rev-parse', '--path-format=absolute', '--git-common-dir'): str(self.root / '.git')}
        if args not in answers:
            raise AssertionError('Unexpected Git discovery outside synthetic fixture: ' + repr(args))
        return answers[args]

    def verified(self):
        return RUN.control.verify_contract(self.root, self.path, EXECUTION, 'K6')

    def policy(self, action='X-K6-SCF', check=False):
        return RETRY.policy_for(self.auth, action, check=check)

    def resource(self, action='X-K6-SCF', check=False):
        policy = self.policy(action, check)
        # Parent is deliberately above 8 GiB but fits its own 10 GiB headroom.
        peak = 8*GIB + 32*1024**2 if action == 'X-K6-SCF' and not check else GIB
        return dict(status='PASS', native_exit_code=0, owned_process_cleanup_status='PASS',
                    peak_aggregate_rss_bytes=peak, nonempty_samples=2,
                    limit_bytes=policy['limit_bytes'], resource_policy=policy,
                    resource_policy_sha256=RETRY.digest(policy), resource_policy_status='PASS',
                    first_stop_request=None, safe_stop_requested=False,
                    authenticated_worker_highwater_bytes=peak, screen_peak_bytes=peak)

    def worker(self, action, check=False):
        auth = self.verified(); policy = self.policy(action, check)
        value = FIXTURE.worker(action, policy['run_id'] + '-dftk', 'K6', check)
        value.update(contract_sha256=auth['contract_sha256'], case_sha256=auth['case_sha256'],
                     executed_source_sha256=auth['executed_source_sha256'], resource_policy=policy,
                     resource_policy_sha256=RETRY.digest(policy),
                     resource_policy_status='WORKER_BOUNDARY_CHECKS_PASS')
        if check:
            value['formal_slot_reserved'] = False
        return value

    def slot(self, action='X-K6-SCF'):
        auth = self.verified(); policy = self.policy(action)
        path = self.store / 'slots' / self.plan['slots'][action]['slot_key']
        value = dict(action=action, run_id=policy['run_id'], execution_commit=EXECUTION,
                     contract_sha256=auth['contract_sha256'], resource_policy_sha256=RETRY.digest(policy),
                     attempt=self.plan['slots'][action]['attempt'],
                     worker_directory=policy['run_id'] + '-dftk', numerical_authorization_status='ELIGIBLE')
        return path, value

    def slot_environment(self, path, slot):
        return patch.dict(os.environ, SOC_EXTRA_SLOT_RECEIPT=str(path),
                          SOC_EXTRA_RUN_ID=slot['run_id'], SOC_EXTRA_WORKER_DIRECTORY=slot['worker_directory'])

    def test_template_parent_10_gamma_8_and_checks_8_are_distinct(self):
        auth = self.verified()
        self.proof_call.assert_called_with(self.root, EXECUTION)
        self.assertEqual(set(auth['allowed_actions']), {'X-K6-SCF', 'X-K6-GAMMA'})
        for action, limit, warning in [('X-K6-SCF', 10*GIB, 8*GIB), ('X-K6-GAMMA', 8*GIB, 7*GIB)]:
            with self.subTest(action=action):
                p, c = self.policy(action), self.policy(action, True)
                self.assertEqual((p['limit_bytes'], p['warning_bytes']), (limit, warning))
                self.assertEqual((c['limit_bytes'], c['warning_bytes']), (8*GIB, 7*GIB))
                self.assertNotEqual(p['run_id'], c['run_id'])
        for action in ('X-B0-SCF', 'X-K6-PILOT', 'X-K8-SCF'):
            with self.subTest(action=action), self.assertRaises(ValueError):
                RETRY.policy_for(auth, action)

    def test_changed_action_run_execution_case_or_hash_rejected(self):
        original = self.path.read_bytes()
        for key, value in [('action', 'X-K6-GAMMA'), ('run_id', 'new-uuid'),
                           ('execution_commit', 'c'*40), ('case_sha256', 'd'*64),
                           ('limit_bytes', 11*GIB)]:
            with self.subTest(key=key):
                bad = copy.deepcopy(self.auth)
                bad['resource_policies']['X-K6-SCF'][key] = value
                # Even self-consistent attacker-supplied digests cannot alter the plan.
                bad['resource_policy_hashes']['X-K6-SCF'] = RETRY.digest(bad['resource_policies']['X-K6-SCF'])
                RUN.write(self.path, bad)
                with self.assertRaises(ValueError): self.verified()
                self.path.write_bytes(original)
        bad = copy.deepcopy(self.auth); bad['resource_policies']['X-K6-SCF']['run_id'] = 'wrong'
        with self.assertRaises(ValueError): RETRY.policy_for(bad, 'X-K6-SCF')
        with self.assertRaises(ValueError): RUN.control.verify_contract(self.root, self.path, 'c'*40, 'K6')
        with self.assertRaises(ValueError): RUN.control.verify_contract(self.root, self.path, EXECUTION, 'B0')

    def test_registry_binds_exact_grant_bytes_and_changed_registry(self):
        self.verified(); original = self.path.read_bytes()
        self.path.write_bytes(original + b'\n')
        with self.assertRaisesRegex(ValueError, 'exact grant bytes'): self.verified()
        self.path.write_bytes(original)
        registry = RETRY.read(self.registry)
        for key, value in [('continuation_id', 'another-grant'), ('start', 'b'*40),
                           ('execution_commit', 'c'*40), ('contract_sha256', 'd'*64),
                           ('allowed_starts', 2), ('workbench_root', str(self.root / 'alias'))]:
            with self.subTest(key=key):
                RUN.write(self.registry, dict(registry, **{key: value}))
                with self.assertRaises(ValueError): self.verified()
        RUN.write(self.registry, registry)
        self.assertEqual(RETRY.verify_registry(self.root, self.path, self.auth), registry)

    def test_new_grant_uuid_and_alternate_root_do_not_create_a_second_allowance(self):
        before = self.registry.read_bytes()
        other = self.path.with_name('new-uuid.json')
        RUN.write(other, dict(self.auth, request_nonce='another-uuid'))
        with self.assertRaisesRegex(ValueError, 'exact grant bytes'):
            RUN.control.verify_contract(self.root, other, EXECUTION, 'K6')
        alias = self.root / 'alias'; alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError): RETRY.verify_registry(alias, self.path, self.auth)
        self.assertEqual(before, self.registry.read_bytes())
        linked = self.path.with_name('linked.json'); linked.symlink_to(self.path)
        with self.assertRaises(ValueError): RUN.control.verify_contract(self.root, linked, EXECUTION, 'K6')

    def test_fixed_shared_slot_is_exclusive_even_for_new_uuid(self):
        path, slot = self.slot(); RUN.write(path, slot, exclusive=True)
        before = path.read_bytes()
        with self.slot_environment(path, slot):
            self.assertEqual(RETRY.verify_slot(self.root, self.verified(), 'X-K6-SCF'), slot)
        with self.assertRaises(FileExistsError):
            RUN.write(path, dict(slot, run_id='new-uuid'), exclusive=True)
        alternate = path.with_name('X-K6-SCF-new-uuid.json'); RUN.write(alternate, dict(slot, run_id='new-uuid'))
        with self.slot_environment(alternate, dict(slot, run_id='new-uuid')), self.assertRaises(ValueError):
            RETRY.verify_slot(self.root, self.verified(), 'X-K6-SCF')
        self.assertEqual(before, path.read_bytes())

    def test_slot_binds_every_identity_field_and_environment(self):
        path, slot = self.slot()
        for key, value in [('action', 'X-K6-GAMMA'), ('run_id', 'new-uuid'), ('execution_commit', 'b'*40),
                           ('contract_sha256', 'c'*64), ('resource_policy_sha256', 'd'*64),
                           ('attempt', 3), ('worker_directory', 'other-dftk'),
                           ('numerical_authorization_status', 'BLOCKED')]:
            with self.subTest(key=key):
                RUN.write(path, dict(slot, **{key: value}))
                with self.slot_environment(path, slot), self.assertRaises(ValueError):
                    RETRY.verify_slot(self.root, self.verified(), 'X-K6-SCF')
        RUN.write(path, slot)
        for key in ('SOC_EXTRA_RUN_ID', 'SOC_EXTRA_WORKER_DIRECTORY'):
            with self.subTest(key=key), self.slot_environment(path, slot), patch.dict(os.environ, {key: 'wrong'}), self.assertRaises(ValueError):
                RETRY.verify_slot(self.root, self.verified(), 'X-K6-SCF')

    def test_parent_10_resource_and_gamma_8_validate_only_against_own_policy(self):
        for action in ('X-K6-SCF', 'X-K6-GAMMA'):
            RUN.resource_contract(self.resource(action), 0, policy=self.policy(action))
        with self.assertRaises(ValueError): RUN.resource_contract(self.resource(), 0)
        with self.assertRaises(ValueError): RUN.resource_contract(self.resource(), 0, policy=self.policy('X-K6-GAMMA'))
        with self.assertRaises(ValueError): RUN.resource_contract(self.resource('X-K6-GAMMA'), 0, policy=self.policy())

    def test_native_zero_resource_stop_and_wrong_highwater_cannot_pass(self):
        changes = [{'resource_policy_status': 'STOP_AT_SAFE_BOUNDARY'}, {'first_stop_request': {'reason': 'synthetic stop'}},
                   {'safe_stop_requested': True}, {'authenticated_worker_highwater_bytes': None},
                   {'screen_peak_bytes': 1}, {'resource_policy_sha256': '0'*64},
                   {'authenticated_worker_highwater_bytes': 10*GIB, 'screen_peak_bytes': 10*GIB}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                RUN.resource_contract(dict(self.resource(), **change), 0, policy=self.policy())
        value = self.worker('X-K6-SCF'); value['resource_policy_status'] = 'STOP_REQUESTED'
        state = dict(action='X-K6-SCF', worker_directory=value['run_id'], resource_policy=self.policy(),
                     resource_policy_sha256=RETRY.digest(self.policy()))
        with self.assertRaises(ValueError): RUN.worker_contract(value, 0, state, self.verified())

    def test_entry_worker_must_explicitly_disclaim_formal_slot(self):
        value = self.worker('X-K6-GAMMA', check=True)
        policy = self.policy('X-K6-GAMMA', True)
        state = dict(action='X-K6-GAMMA', worker_directory=value['run_id'], resource_policy=policy,
                     resource_policy_sha256=RETRY.digest(policy))
        RUN.worker_contract(value, 0, state, self.verified(), check=True)
        for label, fields in [('missing', {}), ('true', {'formal_slot_reserved': True}),
                              ('null', {'formal_slot_reserved': None})]:
            bad = dict(value); bad.pop('formal_slot_reserved'); bad.update(fields)
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, 'cannot claim a formal slot'):
                RUN.worker_contract(bad, 0, state, self.verified(), check=True)

    def parent_run(self):
        action = 'X-K6-SCF'; policy = self.policy(action); auth = self.verified()
        directory = self.store / 'runs' / policy['run_id']; directory.mkdir()
        worker_dir = directory / (policy['run_id'] + '-dftk'); worker_dir.mkdir()
        (worker_dir / 'final.bin').write_bytes(b'SYNTHETIC checkpoint, no Julia serialization')
        value = self.worker(action); value['checkpoint_sha256'] = RETRY.sha(worker_dir / 'final.bin')
        RUN.write(worker_dir / 'result.json', value)
        record = dict(schema_version=1, run_id=directory.name, action=action, execution_commit=EXECUTION,
                      execution_status='PASS', exit_code=0, native_exit_code=0, worker_started=True,
                      contract_path=auth['contract_path'], profile='K6', worker_directory=worker_dir.name,
                      worker_result_sha256=RETRY.sha(worker_dir/'result.json'), resource=self.resource(action),
                      resource_policy=policy, resource_policy_sha256=RETRY.digest(policy))
        RUN.write(directory/'result.json', record)
        RUN.write(directory/'resource.json', record['resource'])
        RUN.write(directory/'process-exit.json', dict(exit_code=0, interrupted=False))
        return directory, worker_dir

    def synthetic_launch(self, action, *, check=False, stop=False, parent=None, native=0):
        policy = self.policy(action, check); calls = []
        synthetic_environment = {'JULIA_DEPOT_PATH': str(self.root)}
        if 'SOC_EXTRA_SLOT_RECEIPT' in os.environ:
            synthetic_environment['SOC_EXTRA_SLOT_RECEIPT'] = os.environ['SOC_EXTRA_SLOT_RECEIPT']

        def execute(command, directory, env, resources, remaining, **kwargs):
            calls.append(dict(command=command, env=env, policy=kwargs['policy']))
            worker_dir = directory/(directory.name+'-dftk'); worker_dir.mkdir()
            value = self.worker(action, check)
            if native:
                value.update(exit_code=native, execution_status='FAIL', reason='SYNTHETIC worker failure')
            if parent is not None:
                wd = parent/(parent.name+'-dftk')
                value.update(parent_result_sha256=RETRY.sha(wd/'result.json'),
                             parent_checkpoint_sha256=RETRY.sha(wd/'final.bin'))
            RUN.write(worker_dir/'result.json', value)
            resource = self.resource(action, check)
            resource['native_exit_code'] = native
            if stop:
                resource.update(resource_policy_status='STOP_AT_SAFE_BOUNDARY', safe_stop_requested=True,
                                first_stop_request={'reason': 'SYNTHETIC headroom stop'})
            # A process receipt fixture is not an actual launch.
            RUN.write(directory/'process-start.json', {'synthetic': True})
            RUN.write(directory/'process-exit.json', dict(exit_code=native, interrupted=False))
            RUN.write(directory/'resource.json', resource)
            return native, resource

        with patch.object(RUN, 'module', return_value=types.SimpleNamespace()), \
             patch.object(RUN, 'prerequisites', return_value={'status':'ELIGIBLE', 'remaining_growth_bytes':policy['remaining_growth_bytes']}), \
             patch.object(RUN, 'monitored', side_effect=execute), \
             patch.object(RUN.shutil, 'which', return_value='/synthetic/never-executed-julia'), \
             patch.dict(os.environ, synthetic_environment, clear=True), redirect_stdout(io.StringIO()):
            code = RUN.launch(action, profile='K6', contract=self.path, execution_commit=EXECUTION,
                              parent=parent, check_entry=check, root=self.root)
        record = RETRY.read(self.store/'runs'/policy['run_id']/'result.json')
        return code, record, calls

    def test_gamma_entry_authenticates_parent_but_consumes_no_slot(self):
        parent, worker_dir = self.parent_run()
        before = (worker_dir/'result.json').read_bytes()
        code, record, calls = self.synthetic_launch('X-K6-GAMMA', check=True, parent=parent)
        self.assertEqual((code, record['execution_status'], record['native_exit_code']), (0, 'CHECK_ONLY_PASS', 0))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['policy']['limit_bytes'], 8*GIB)
        self.assertFalse('SOC_EXTRA_SLOT_RECEIPT' in calls[0]['env'], 'Entry forwarded a slot receipt')
        self.assertFalse(record['formal_slot_reserved']); self.assertFalse(record['worker_started'])
        self.assertEqual(list((self.store/'slots').iterdir()), [])
        self.assertEqual(record['parent_result_sha256'], RETRY.sha(worker_dir/'result.json'))
        self.assertEqual(before, (worker_dir/'result.json').read_bytes())

    def test_gamma_entry_refuses_a_foreign_parent_before_worker_or_slot(self):
        parent, _ = self.parent_run()
        receipt = RETRY.read(parent/'result.json'); receipt['execution_commit'] = 'f'*40
        RUN.write(parent/'result.json', receipt)
        code, record, calls = self.synthetic_launch('X-K6-GAMMA', check=True, parent=parent)
        self.assertNotEqual(code, 0); self.assertEqual(record['execution_status'], 'BLOCKED_PARENT')
        self.assertEqual(calls, []); self.assertIsNone(record['native_exit_code'])
        self.assertFalse(record['formal_slot_reserved']); self.assertFalse(record['worker_started'])
        self.assertEqual(list((self.store/'slots').iterdir()), [])

    def test_gamma_entry_does_not_forward_an_inherited_slot_environment(self):
        parent, _ = self.parent_run()
        with patch.dict(os.environ, SOC_EXTRA_SLOT_RECEIPT='/synthetic/old-slot.json'):
            code, record, calls = self.synthetic_launch('X-K6-GAMMA', check=True, parent=parent)
        self.assertEqual(code, 0)
        self.assertFalse('SOC_EXTRA_SLOT_RECEIPT' in calls[0]['env'], 'Entry forwarded an inherited slot receipt')
        self.assertFalse(record['formal_slot_reserved'])

    def test_launcher_native_zero_stop_retains_nonpass_result_and_slot(self):
        code, record, calls = self.synthetic_launch('X-K6-SCF', stop=True)
        self.assertNotEqual(code, 0); self.assertNotEqual(record['execution_status'], 'PASS')
        self.assertEqual(record['native_exit_code'], 0); self.assertEqual(len(calls), 1)
        slot = self.store/'slots'/self.plan['slots']['X-K6-SCF']['slot_key']
        self.assertTrue(record['formal_slot_reserved']); self.assertTrue(slot.is_file())
        self.assertEqual(RETRY.read(slot)['attempt'], 2)
        before = slot.read_bytes()
        with self.assertRaises(ValueError): self.synthetic_launch('X-K6-SCF')
        self.assertEqual(before, slot.read_bytes())

    def test_legitimate_worker_failure_keeps_its_native_code(self):
        code, record, calls = self.synthetic_launch('X-K6-SCF', native=7)
        self.assertEqual((code, record['native_exit_code'], record['execution_status']), (7, 7, 'FAIL'))
        self.assertEqual(record['reason'], 'SYNTHETIC worker failure')
        self.assertEqual(len(calls), 1); self.assertTrue(record['formal_slot_reserved'])


if __name__ == '__main__':
    unittest.main()
