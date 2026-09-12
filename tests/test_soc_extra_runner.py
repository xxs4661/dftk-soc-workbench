"""Synthetic protocol fixtures only: no Julia, UPF, SCF or physical evidence."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('soc_extra_runner_test', ROOT / 'benchmarks/soc-extra-v1/run.py')
RUN = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(RUN)


def auth(profile='B0'):
    return {'profile': profile, 'execution_commit': 'a' * 40, 'contract_sha256': 'b' * 64,
            'contract_path': '.work/phase9a-extra/authorizations/synthetic.json',
            'case_sha256': 'c' * 64, 'executed_source_sha256': {'synthetic.jl': 'd' * 64},
            'numerical_change_requires_B0': True}


def worker(action='X-B0-SCF', run_id='synthetic-dftk', profile='B0', check=False):
    a = auth(profile)
    value = {'schema_version': 1, 'phase': '9A-extra', 'backend': 'soc-core',
             'case': 'soc-extra-v1/' + profile, 'extra_profile': profile, 'action': action, 'run_id': run_id,
             'execution_commit': a['execution_commit'], 'contract_sha256': a['contract_sha256'],
             'case_sha256': a['case_sha256'], 'executed_source_sha256': a['executed_source_sha256'],
             'execution_status': 'PASS', 'exit_code': 0, 'environment': {'status': 'PASS'}}
    if check:
        return dict(value, execution_status='CHECK_ONLY_PASS', check_only=True, context_constructed=False,
                    numerical_execution_status='NOT_RUN')
    value.update(parallelism={'julia': 1, 'blas': 1, 'fft': 1, 'mpi': 1},
                 input={'element': 'Si', 'nlcc_present': True, 'sha256': 'cc91a6be43c3c89daf6c34410096e8d870f25152dbfb513bcf01afa5ab53eabf'},
                 grid={'status': 'PASS'}, runtime_closed=True, runtime_dispatch_status='PASS',
                 runtime={'backend': 'soc-core', 'max_rhs': 30, 'counters': {k: 1 for k in
                     ('fr_mul_calls', 'component_mul_calls', 'full_mul_calls')}},
                 runtime_after_close={'closed': True, 'owned_source_entries': 0, 'workspace_released': True})
    if action == 'X-K6-PILOT':
        value.update(execution_status=RUN.PILOT,
                     pilot={'completed_maps': 2, 'lifecycle': {'synthetic': True}, 'geometry': {'synthetic': True}})
    elif action.endswith('-SCF'):
        value.update(checkpoint_sha256='e' * 64,
                     final={'map_count': 3, 'closure_status': 'PASS', 'n_out_sha256': 'f' * 64,
                            'diagnostics': {'target_states': 24},
                            'eigenvalues_ha': [[0.] * 24 for _ in range(8 if profile == 'B0' else 216)],
                            'occupations': [[0.] * 24 for _ in range(8 if profile == 'B0' else 216)]})
    else:
        value.update(source_scf_run_id='own-scf', density_source_sha256='f' * 64,
                     time_reversal={'status': 'PASS'},
                     spectrum={'execution_status': 'PASS', 'process_exit_code': 0, 'physical_operator': 'full_soc',
                               'temperature_ha': .001, 'occupations_use': 'DIAGNOSTIC_ONLY_NOT_DENSITY_FEEDBACK',
                               'source_scf_run_id': 'own-scf', 'density_source_sha256': 'f' * 64,
                               'kpoints': [{'coordinate_fractional': [0., 0., 0.], 'weight_spatial': 1,
                                            'eigenvalues_ha': [0.] * 24, 'residuals_ha': [0.] * 24}]})
    return value


def resource(code=0):
    return {'status': 'PASS', 'native_exit_code': code, 'owned_process_cleanup_status': 'PASS',
            'peak_aggregate_rss_bytes': 1000, 'nonempty_samples': 1}


class WorkerProtocol(unittest.TestCase):
    def validate(self, value, code=0, check=False):
        RUN.worker_contract(value, code, {'action': value['action'], 'worker_directory': 'synthetic-dftk'},
                            auth(value['extra_profile']), check=check)

    def test_all_registered_success_kinds(self):
        for action in RUN.ACTIONS:
            with self.subTest(action=action):
                self.validate(worker(action, profile='K6' if 'K6' in action else 'B0'))

    def test_pilot_is_not_formal_success(self):
        value = worker('X-K6-PILOT', profile='K6')
        for status in ('PASS', 'CHECK_ONLY_PASS'):
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.validate(dict(value, execution_status=status))
        for maps in (0, 3, True):
            bad = copy.deepcopy(value); bad['pilot']['completed_maps'] = maps
            with self.subTest(maps=maps), self.assertRaises(ValueError): self.validate(bad)
        with self.assertRaises(ValueError): self.validate(dict(value, final={'closure_status': 'PASS'}))

    def test_source_types_identity_status_exit_and_dispatch_reject(self):
        valid = worker()
        for field, wrong in [('schema_version', 999), ('execution_status', 'FAIL'), ('exit_code', True),
                             ('environment', None), ('input', []), ('case', 'si-soc-splitting-v1'),
                             ('execution_commit', '0' * 40), ('contract_sha256', '0' * 64),
                             ('runtime_closed', False), ('runtime_dispatch_status', 'NOT_RUN')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.validate(dict(valid, **{field: wrong}))
        bad = copy.deepcopy(valid); bad['runtime']['counters']['fr_mul_calls'] = 0
        with self.assertRaises(ValueError): self.validate(bad)
        bad = copy.deepcopy(valid); bad['final']['eigenvalues_ha'][0][0] = float('nan')
        with self.assertRaises(ValueError): self.validate(bad)

    def test_closure_point_band_count_remain_required(self):
        for field, value in [('closure_status', 'FAIL'), ('eigenvalues_ha', [[0.] * 24]),
                             ('occupations', [[0.] * 30] * 8)]:
            bad = worker(); bad['final'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.validate(bad)

    def test_native_failure_preserved_but_contradictory_failure_rejected(self):
        value = dict(worker(), execution_status='FAIL', exit_code=7, reason='Synthetic deliberate failure')
        self.validate(value, 7)
        with self.assertRaises(ValueError): self.validate(value, 0)
        with self.assertRaises(ValueError): self.validate(dict(value, execution_status='PASS'), 7)

    def test_entry_check_cannot_claim_physics(self):
        value = worker(check=True); self.validate(value, check=True)
        for fields in ({'context_constructed': True}, {'execution_status': 'PASS'}, {'numerical_execution_status': 'PASS'}):
            with self.subTest(fields=fields), self.assertRaises(ValueError): self.validate(dict(value, **fields), check=True)

    def test_gamma_uses_parent_and_embedded_spectrum_no_filename_assumption(self):
        value = worker('X-B0-GAMMA'); self.validate(value)
        bad = copy.deepcopy(value); bad['spectrum']['density_source_sha256'] = 'different'
        with self.assertRaises(ValueError): self.validate(bad)
        bad = copy.deepcopy(value); bad['spectrum']['kpoints'][0]['coordinate_fractional'] = [.1, 0, 0]
        with self.assertRaises(ValueError): self.validate(bad)


class SyntheticLaunch(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.area = self.root / '.work/phase9a-extra/runs'; self.area.mkdir(parents=True)
        self.resources = types.SimpleNamespace(host_preflight=lambda root: {'status': 'ELIGIBLE'})

    def tearDown(self): self.temp.cleanup()

    def run_synthetic(self, name, *, code=0, malformed=False, check=False, precondition_error=False):
        path = self.area / name
        def execute(command, directory, env, resources, remaining):
            output = Path(command[6]); output.mkdir()
            value = worker('X-B0-SCF', output.name, check=check)
            if code: value.update(exit_code=code, execution_status='FAIL', reason='Synthetic worker failure')
            if malformed: value['environment'] = None
            RUN.write(output / 'result.json', value)
            RUN.write(directory / 'process-start.json', {'pid': 999999})
            RUN.write(directory / 'process-exit.json', {'exit_code': code, 'interrupted': False})
            RUN.write(directory / 'resource.json', resource(code))
            return code, resource(code)
        with patch.object(RUN.control, 'verify_contract', return_value=auth()), \
             patch.object(RUN, 'module', return_value=self.resources), \
             patch.object(RUN, 'prerequisites', side_effect=ValueError('RESOURCE_BLOCKED synthetic') if precondition_error else None,
                          return_value={'status': 'ELIGIBLE', 'remaining_growth_bytes': 1024}), \
             patch.object(RUN, 'monitored', side_effect=execute) as monitor, \
             patch.object(RUN.shutil, 'which', return_value='/synthetic/julia'), \
             patch.dict(os.environ, JULIA_DEPOT_PATH=str(self.root)):
            result = RUN.launch('X-B0-SCF', profile='B0', contract=self.root / 'auth.json', execution_commit='a' * 40,
                                directory=path, check_entry=check, root=self.root)
        return result, RUN.read(path / 'result.json'), monitor.call_count

    def test_failure_code_and_one_time_slot(self):
        code, rec, count = self.run_synthetic('first', code=7)
        self.assertEqual((code, rec['native_exit_code'], count), (7, 7, 1))
        before = (self.root / '.work/phase9a-extra/slots/X-B0-SCF.json').read_bytes()
        code, rec, count = self.run_synthetic('second')
        self.assertEqual((code, rec['native_exit_code'], count), (9, None, 0))
        self.assertEqual(before, (self.root / '.work/phase9a-extra/slots/X-B0-SCF.json').read_bytes())
        self.assertFalse((self.root / '.work/phase9a/static/active.json').exists())

    def test_malformed_success_cannot_publish_pass(self):
        code, rec, count = self.run_synthetic('bad', malformed=True)
        self.assertEqual((code, rec['execution_status'], rec['native_exit_code']), (9, 'FAIL', 0))
        self.assertEqual(count, 1)

    def test_check_entry_does_not_consume_or_claim_slot(self):
        code, rec, count = self.run_synthetic('entry', check=True)
        self.assertEqual((code, rec['execution_status'], count), (0, 'CHECK_ONLY_PASS', 1))
        self.assertFalse(rec['formal_slot_reserved']); self.assertFalse(rec['worker_started'])
        self.assertFalse((self.root / '.work/phase9a-extra/slots').exists())

    def test_precondition_failure_has_null_native_and_no_slot(self):
        code, rec, count = self.run_synthetic('blocked', precondition_error=True)
        self.assertEqual((code, rec['native_exit_code'], count), (9, None, 0))
        self.assertFalse(rec['worker_started']); self.assertFalse(rec['formal_slot_reserved'])

    def test_existing_lock_and_existing_output_are_preserved(self):
        lock = self.root / '.work/phase9a/endpoints/active.json'; lock.parent.mkdir(parents=True)
        lock.write_text('{"run_id":"other-owned-run"}')
        before = lock.read_bytes()
        code, rec, count = self.run_synthetic('locked')
        self.assertEqual((code, count), (9, 0)); self.assertEqual(before, lock.read_bytes())
        previous = (self.area / 'locked/result.json').read_bytes()
        with self.assertRaises(ValueError): self.run_synthetic('locked')
        self.assertEqual(previous, (self.area / 'locked/result.json').read_bytes())

    def test_missing_parent_is_blocked_before_worker(self):
        with patch.object(RUN.control, 'verify_contract') as verify:
            code = RUN.launch('X-B0-GAMMA', profile='B0', contract='missing', execution_commit='a' * 40,
                              root=self.root, directory=self.area / 'no-parent')
        self.assertEqual(code, 9); self.assertFalse(verify.called)
        self.assertIsNone(RUN.read(self.area / 'no-parent/result.json')['native_exit_code'])


if __name__ == '__main__':
    unittest.main()
