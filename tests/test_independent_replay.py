"""Synthetic protocol checks only: no public physical inputs are evaluated."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location('replay_public_independent', SCRIPTS / 'replay_public_independent.py')
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


def synthetic_plan():
    return {'input_commit': 'a' * 40, 'I': {'independence': 'synthetic test'},
            'thresholds': {'energy': 1e-9}}


class SyntheticIndependentProtocol(unittest.TestCase):
    def test_gate_retains_measured_failure_nonfinite_and_shape(self):
        records = []
        gates = replay.Checks({'energy': 1e-9}, records)
        gates.bound('synthetic.first', 2e-9, 'energy')
        gates.bound('synthetic.second', 0., 'energy')
        gates.bound('synthetic.nonfinite', float('nan'), 'energy')
        gates.compare('synthetic.dimensions', [1, 2], [1], 'energy')
        with self.assertRaises(replay.GateFailure):
            gates.checkpoint('synthetic stage')
        self.assertEqual(records[0]['error'], 2e-9)
        self.assertEqual(records[1]['status'], 'PASS')
        self.assertEqual(records[2]['status'], 'FAIL')
        self.assertEqual(records[3]['status'], 'FAIL')
        json.dumps(records, allow_nan=False)

    def test_unoccupied_state_nonlocal_mismatch_is_checked(self):
        records = []
        gates = replay.Checks({'energy': 1e-9}, records)
        result = {'max_imaginary_expectation_ha': 0., 'spin_decomposition_difference_ha': 0.,
                  'projected_ha': 2., 'kpoints': [{'bands': 2, 'projected_unweighted_ha': [2., 8.],
                   'up_unweighted_ha': [1., 4.], 'down_unweighted_ha': [1., 4.],
                   'cross_unweighted_ha': [0., 0.]}]}
        old = {'energy_projected_ha': 2., 'kpoints': [{'rows': [
            {'projected_ha': 2., 'up_up_ha': 1., 'down_down_ha': 1., 'spin_cross_ha': 0.},
            {'projected_ha': 7., 'up_up_ha': 3., 'down_down_ha': 4., 'spin_cross_ha': 0.}]}]}
        replay.validate_nonlocal(result, old, gates, 'A', 'energy')
        with self.assertRaises(replay.GateFailure):
            gates.checkpoint('all states')
        self.assertTrue(any(x['status'] == 'FAIL' and 'all_states_projected' in x['name'] for x in records))

    def test_scope_never_claims_native_qe_nonlocal_or_ab_orbital_recovery(self):
        report = replay.initial_report(synthetic_plan())
        self.assertEqual(report['native_QE_nonlocal_status'], 'NOT_MEASURED')
        self.assertEqual(report['A_B_replay_scope'], 'SCALAR_AND_PROJECTED_ONLY')
        self.assertEqual(report['original_Q_H_input_residual_status'], 'NOT_AVAILABLE')
        self.assertEqual(report['physical_convergence_status'], 'NOT_ESTABLISHED')

    def test_complex_projection_phase_is_checked_without_alignment(self):
        records = []
        gates = replay.Checks({}, records)
        up = np.array([[1. + 2.j, 3. - 4.j]])
        down = np.array([[5. - 6.j, 7. + 8.j]])
        result = replay.validate_projection_amplitudes([{'up': -up, 'down': down}],
                  {'Q_k1_up': up, 'Q_k1_down': down}, gates, 'a' * 40)
        self.assertEqual(result[0]['up']['values_checked'], 2)
        self.assertEqual(records[0]['status'], 'FAIL')
        self.assertEqual(records[0]['absolute_limit'], 1e-11)
        self.assertEqual(records[1]['status'], 'PASS')
        with self.assertRaises(replay.GateFailure):
            gates.checkpoint('phase identity')

    def test_output_directory_refuses_stale_receipt_without_deleting_it(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'old'
            output.mkdir()
            receipt = output / 'independent.json'
            receipt.write_text('{"status":"PASS","scope":"synthetic old fixture"}')
            before = receipt.read_bytes()
            with self.assertRaisesRegex(ValueError, 'stale'):
                replay.prepare_output(output)
            self.assertEqual(receipt.read_bytes(), before)

    def test_cli_failure_is_nonzero_and_keeps_partial_measurements(self):
        def synthetic_failure(root, plan, output, report):
            report['Q'] = {'synthetic_measured_error': 2e-9}
            report['checks'].append({'name': 'synthetic.failed', 'status': 'FAIL', 'error': 2e-9})
            raise replay.GateFailure('synthetic measured failure')
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            plan = base / 'synthetic-plan.json'
            plan.write_text(json.dumps(synthetic_plan()))
            out = base / 'out'
            with mock.patch.object(replay.subprocess, 'check_output', return_value='a' * 40 + '\n'), \
                 mock.patch.object(replay, 'run_replay', side_effect=synthetic_failure):
                code = replay.main(['--source-root', str(base), '--plan', str(plan), '--output', str(out)])
            result = json.loads((out / 'independent.json').read_text())
            self.assertEqual(code, 1)
            self.assertEqual(result['exit_code'], 1)
            self.assertEqual(result['status'], 'FAIL')
            self.assertEqual(result['Q_full_public_numeric_replay_status'], 'FAIL')
            self.assertEqual(result['Q']['synthetic_measured_error'], 2e-9)
            self.assertEqual(result['checks'][0]['error'], 2e-9)
            self.assertFalse((out / 'rho.npy').exists())

    def test_main_source_commit_mismatch_never_starts_numerical_path(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            plan = base / 'synthetic-plan.json'
            plan.write_text(json.dumps(synthetic_plan()))
            out = base / 'out'
            with mock.patch.object(replay.subprocess, 'check_output', return_value='b' * 40 + '\n'), \
                 mock.patch.object(replay, 'run_replay') as run:
                code = replay.main(['--source-root', str(base), '--plan', str(plan), '--output', str(out)])
            self.assertEqual(code, 1)
            run.assert_not_called()
            self.assertEqual(json.loads((out / 'independent.json').read_text())['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
