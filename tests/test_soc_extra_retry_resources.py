"""Synthetic policy and harmless Python process tests; no material calculation.

RSS values are explicitly injected into real process-table rows. They do not
represent actual large memory allocations, material workers or measured peaks.
"""
import copy
import importlib.util
import inspect
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


R = module('benchmarks/soc-extra-v1/resources.py', 'retry_resources')
S = module('scripts/si_qe_reference_evidence.py', 'retry_sampler')
GIB = 1024**3
GROWTH = 2021087414
NORMAL = dict(status='KNOWN', severe=False)


def once_policy():
    # Synthetic shape only: this cannot pass the production controller's
    # source/reservation authentication and is never supplied to that path.
    return dict(schema_version=1, policy_id='k6-scf-attempt2-10gib-v1',
                limit_bytes=10*GIB, warning_bytes=8*GIB,
                remaining_growth_bytes=GROWTH, run_id='SYNTHETIC-K6-ATTEMPT2',
                action='X-K6-SCF', case_sha256='a'*64, execution_commit='b'*40)


class PolicyTests(unittest.TestCase):
    def decision(self, rss, **kwargs):
        return R.monitor_decision(rss, pressure=copy.deepcopy(NORMAL), **kwargs)

    def test_historical_counterexample_and_equal_headroom_stop(self):
        self.assertEqual(self.decision(7447937024, remaining_growth_bytes=GROWTH)['status'],
                         'STOP_AT_SAFE_BOUNDARY')
        self.assertEqual(self.decision(8*GIB-GROWTH, remaining_growth_bytes=GROWTH)['status'],
                         'STOP_AT_SAFE_BOUNDARY')
        self.assertEqual(R.LIMIT_BYTES, 8*GIB)
        self.assertEqual(R.WARNING_BYTES, 7*GIB)
        self.assertEqual(S.MAX_RSS, 8*GIB)

    def test_single_policy_warning_stop_equality_and_emergency(self):
        policy = once_policy()
        self.assertEqual(self.decision(8*GIB, policy=policy)['status'], 'WARNING')
        self.assertEqual(self.decision(10*GIB-GROWTH, policy=policy)['status'], 'STOP_AT_SAFE_BOUNDARY')
        self.assertEqual(self.decision(10*GIB, policy=policy)['status'], 'RESOURCE_LIMIT')
        self.assertEqual(R.monitor_decision(1, policy=policy, pressure=dict(status='KNOWN', severe=True))['status'], 'RESOURCE_LIMIT')

    def test_peak_and_worker_max_are_not_added_or_lowered(self):
        first = self.decision(7447937024, remaining_growth_bytes=GROWTH)
        later = self.decision(1, peak_group_rss_bytes=7447937024,
                              worker_highwater_bytes=7528939520,
                              remaining_growth_bytes=GROWTH, stop_request=first)
        self.assertEqual(later['screen_peak_bytes'], 7528939520)
        self.assertEqual(later['reason'], first['reason'])
        self.assertEqual(later['status'], 'STOP_AT_SAFE_BOUNDARY')
        self.assertTrue(later['stop_latched'])
        self.assertEqual(self.decision(1, peak_group_rss_bytes=10*GIB, policy=once_policy())['status'], 'RESOURCE_LIMIT')
        self.assertEqual(self.decision(1, worker_highwater_bytes=10*GIB, policy=once_policy())['status'], 'RESOURCE_LIMIT')
        self.assertEqual(self.decision(1)['worker_highwater_status'], 'NOT_YET_AVAILABLE')
        self.assertIsNone(self.decision(1)['worker_highwater_bytes'])

    def test_unknown_values_and_reduced_policy_growth_fail_closed(self):
        for key, value in [('rss_bytes', -1), ('rss_bytes', True), ('rss_bytes', math.nan),
                           ('peak_group_rss_bytes', 0), ('worker_highwater_bytes', 0),
                           ('remaining_growth_bytes', 0), ('worker_highwater_bytes', 'bytes'),
                           ('stop_request', {'status': 'PASS'})]:
            args = dict(rss_bytes=1, pressure=NORMAL); args[key] = value
            with self.subTest(key=key, value=value):
                self.assertEqual(R.monitor_decision(**args)['status'], 'MONITORING_UNAVAILABLE')
        self.assertEqual(R.monitor_decision(1, pressure=dict(status='UNKNOWN', severe=None))['status'], 'MONITORING_UNAVAILABLE')
        self.assertEqual(self.decision(1, policy=once_policy(), remaining_growth_bytes=GROWTH-1)['status'], 'MONITORING_UNAVAILABLE')

    def test_policy_scope_and_shape_are_fixed(self):
        for key, value in [('limit_bytes', 10000000000), ('limit_bytes', 11*GIB),
                           ('warning_bytes', 9*GIB), ('schema_version', True),
                           ('remaining_growth_bytes', GROWTH-1), ('policy_id', 'renamed'),
                           ('execution_commit', 'wrong'), ('case_sha256', 'wrong'), ('run_id', '')]:
            policy = once_policy(); policy[key] = value
            with self.subTest(key=key):
                with self.assertRaises(ValueError): R.validate_policy(policy)
        for action in ('X-B0-SCF', 'X-K6-PILOT', 'X-K8-SCF', 'X-K6-GAMMA'):
            policy = once_policy(); policy['action'] = action
            with self.subTest(action=action), self.assertRaises(ValueError): R.validate_policy(policy)
        gamma = once_policy(); gamma.update(policy_id='k6-gamma-attempt1-8gib-v1', action='X-K6-GAMMA',
                                             limit_bytes=8*GIB, warning_bytes=7*GIB,
                                             remaining_growth_bytes=GIB)
        self.assertEqual(R.validate_policy(gamma)['limit_bytes'], 8*GIB)
        gamma['limit_bytes'] = 10*GIB
        with self.assertRaises(ValueError): R.validate_policy(gamma)

    def test_kernel_pressure_failure_is_not_silently_dropped(self):
        with patch.object(R.platform, 'system', return_value='Darwin'), \
             patch.object(R, '_command', side_effect=['System-wide memory free percentage: 40%\n', ValueError('sysctl failed')]):
            result = R.host_pressure()
        self.assertEqual(result['status'], 'UNKNOWN')
        self.assertIsNone(result['severe'])
        self.assertIn('sysctl failed', result['reason'])


WORKER = '''import json,pathlib,sys,time
p=pathlib.Path(sys.argv[1]); ignore=sys.argv[2]=='ignore'; end=time.monotonic()+.45
while time.monotonic()<end:
 if p.exists() and not ignore:
  request=json.loads(p.read_text())
  if request['run_id']!='SYNTHETIC-K6-ATTEMPT2':sys.exit(29)
  sys.exit(17)
 time.sleep(.005)
sys.exit(0)
'''


class SamplerTests(unittest.TestCase):
    def run_worker(self, directory, *, rss_bytes, policy=None, callback_mode='policy',
                   ignore_stop=False, timeout=30, callback_error=False):
        directory = Path(directory); stop = directory / 'stop.json'
        command = [sys.executable, '-B', '-c', WORKER, str(stop), 'ignore' if ignore_stop else 'respect']
        launched = []; decisions = []; saved = []

        def executor(command, directory, env):
            with (directory/'native.stdout').open('wb') as out, (directory/'native.stderr').open('wb') as err:
                child = subprocess.Popen(command, stdout=out, stderr=err, env=env, start_new_session=True)
                launched.append(child)
                S.write(directory/'process-start.json', dict(pid=child.pid, command=command))
                code = child.wait()
                S.write(directory/'process-exit.json', dict(exit_code=code))
                return code

        actual_rows = S.ps_rows
        def synthetic_rows():
            rows = actual_rows()
            if launched:
                owned = S.owned_rows(rows, launched[0].pid)
                for row in owned: row['rss_kib'] = 0
                if owned: owned[0]['rss_kib'] = rss_bytes // 1024
            return rows

        def observe(sample):
            if callback_error: raise ValueError('SYNTHETIC pressure reader failure')
            if callback_mode == 'continue': decision = dict(status='CONTINUE', reason=None)
            elif callback_mode == 'wrong_limit': decision = dict(status='CONTINUE', reason=None, limit_bytes=11*GIB)
            elif callback_mode == 'retract' and saved: decision = dict(status='CONTINUE', reason=None)
            else:
                decision = R.monitor_decision(sample['current_group_rss_bytes'],
                    peak_group_rss_bytes=sample['peak_group_rss_bytes'], remaining_growth_bytes=GROWTH,
                    pressure=NORMAL, policy=policy)
            decisions.append(decision)
            if decision['status'] == 'STOP_AT_SAFE_BOUNDARY' and not saved:
                record = dict(decision, run_id='SYNTHETIC-K6-ATTEMPT2')
                raw = json.dumps(record).encode()
                # Exclusive first request in this synthetic protocol. Production
                # atomic request/identity is separately tested by the runner.
                with stop.open('xb') as stream: stream.write(raw)
                saved.append(raw)
            return decision

        try:
            with patch.object(S, 'ps_rows', side_effect=synthetic_rows):
                code, state = S.monitored_execute(executor, command, directory, os.environ.copy(),
                    limit_bytes=8*GIB if policy is None else policy['limit_bytes'],
                    observation_callback=observe, safe_stop_timeout_seconds=timeout)
            if saved: self.assertEqual(stop.read_bytes(), saved[0])
            self.assertEqual(state['native_exit_code'], code)
            self.assertEqual(state['owned_process_cleanup_status'], 'PASS')
            self.assertGreater(state['nonempty_samples'], 0)
            self.assertEqual(json.loads((directory/'resource.json').read_text()), state)
            self.assertTrue(all(child.poll() is not None for child in launched))
            return code, state, decisions
        finally:
            for child in launched:
                if child.poll() is None: child.kill(); child.wait()

    def test_actual_sampler_to_stop_file_to_worker_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            code, state, decisions = self.run_worker(directory, rss_bytes=7447937024)
        self.assertEqual(code, 17)
        self.assertEqual(state['resource_policy_status'], 'STOP_AT_SAFE_BOUNDARY')
        self.assertEqual(state['status'], 'RESOURCE_BLOCKED')
        self.assertTrue(state['safe_stop_requested'])
        self.assertFalse(state['safe_stop_escalated'])
        self.assertEqual(decisions[0]['status'], 'STOP_AT_SAFE_BOUNDARY')

    def test_call_specific_bottom_limit_preserves_default_and_does_not_sum(self):
        with tempfile.TemporaryDirectory() as directory:
            code, state, _ = self.run_worker(directory, rss_bytes=8*GIB+20*1024**2,
                                            policy=once_policy())
        self.assertEqual(code, 0)
        self.assertEqual(state['status'], 'PASS')
        self.assertEqual(state['limit_bytes'], 10*GIB)
        self.assertTrue(state['warning_observed'])
        with tempfile.TemporaryDirectory() as directory:
            code, state, _ = self.run_worker(directory, rss_bytes=8*GIB+20*1024**2,
                                            callback_mode='continue')
        self.assertNotEqual(code, 0)
        self.assertEqual(state['limit_bytes'], 8*GIB)
        self.assertEqual(state['resource_policy_status'], 'RESOURCE_LIMIT')
        with tempfile.TemporaryDirectory() as directory:
            code, state, _ = self.run_worker(directory, rss_bytes=10*GIB,
                                            policy=once_policy(), callback_mode='continue')
        self.assertNotEqual(code, 0)
        self.assertEqual(state['resource_policy_status'], 'RESOURCE_LIMIT')

    def test_latched_safe_stop_escalates_and_preserves_unrelated_process(self):
        unrelated = subprocess.Popen([sys.executable, '-B', '-c', 'import time;time.sleep(10)'], start_new_session=True)
        try:
            with tempfile.TemporaryDirectory() as directory:
                code, state, decisions = self.run_worker(directory, rss_bytes=7447937024,
                    callback_mode='retract', ignore_stop=True, timeout=.15)
            self.assertNotEqual(code, 0)
            self.assertTrue(state['safe_stop_escalated'])
            self.assertEqual(state['safe_stop_first_decision']['status'], 'STOP_AT_SAFE_BOUNDARY')
            self.assertEqual(state['resource_policy_status'], 'STOP_AT_SAFE_BOUNDARY')
            self.assertTrue(any(x['status']=='CONTINUE' for x in decisions[1:]))
            self.assertIsNone(unrelated.poll())
            self.assertEqual(inspect.signature(S.monitored_execute).parameters['safe_stop_timeout_seconds'].default, 30)
        finally:
            unrelated.terminate(); unrelated.wait()

    def test_callback_failure_closes_owned_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            code, state, _ = self.run_worker(directory, rss_bytes=100*1024**2, callback_error=True)
        self.assertNotEqual(code, 0)
        self.assertEqual(state['resource_policy_status'], 'MONITORING_UNAVAILABLE')
        self.assertIn('SYNTHETIC pressure reader failure', state['reason'])

    def test_native_zero_cannot_publish_resource_pass_after_safe_request(self):
        with tempfile.TemporaryDirectory() as directory:
            code, state, _ = self.run_worker(directory, rss_bytes=7447937024, ignore_stop=True)
        self.assertEqual(code, 0)
        self.assertEqual(state['native_exit_code'], 0)
        self.assertEqual(state['status'], 'RESOURCE_BLOCKED')
        self.assertEqual(state['resource_policy_status'], 'STOP_AT_SAFE_BOUNDARY')
        self.assertEqual(state['owned_process_cleanup_status'], 'PASS')

    def test_callback_cannot_report_another_bottom_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            code, state, _ = self.run_worker(directory, rss_bytes=100*1024**2, callback_mode='wrong_limit')
        self.assertNotEqual(code, 0)
        self.assertEqual(state['resource_policy_status'], 'MONITORING_UNAVAILABLE')
        self.assertIn('effective limits differ', state['reason'])

    def test_invalid_internal_calls_do_not_start_executor(self):
        for kwargs in ({'limit_bytes': 10*GIB}, {'limit_bytes': 11*GIB},
                       {'safe_stop_timeout_seconds': 31}, {'safe_stop_timeout_seconds': math.nan},
                       {'observation_callback': 'bad'}):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    S.monitored_execute(lambda *_: self.fail('invalid call started worker'), [], directory, {}, **kwargs)
        with patch.object(S, 'ps_rows', return_value=[]), tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                S.monitored_execute(lambda *_: self.fail('missing monitoring started worker'), [], directory, {})


if __name__ == '__main__':
    unittest.main(verbosity=2)
