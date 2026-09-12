"""Synthetic admission/monitor contracts; no real context or numerical worker."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('soc_extra_resources', ROOT / 'benchmarks/soc-extra-v1/resources.py')
resources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resources)


def host():
    return dict(status='ELIGIBLE', severe_pressure=False, free_disk_bytes=40 * resources.GIB,
                active_numerical_processes=[])


def pilot():
    return dict(status='PILOT_COMPLETED_NOT_SCF_CONVERGED', completed_maps=2,
                native_exit_code=0, recorder_exit_code=0, geometry=resources.GEOMETRY.copy(),
                resource=dict(status='PASS', native_exit_code=0, limit_bytes=resources.LIMIT_BYTES,
                    peak_aggregate_rss_bytes=4 * resources.GIB, nonempty_samples=10,
                    owned_process_cleanup_status='PASS'),
                lifecycle=dict(history_bytes=1_000_000, history_map_count=2, max_record_bytes=600_000,
                    serialization_payload_bytes=790_191_936, serialization_buffer_capacity_bytes=800_000_000,
                    serialization_capacity_evidence='MEASURED_ACTIVE_BUFFER'))


class SourceAndBudgetTests(unittest.TestCase):
    def test_source_bytes_and_historical_runtime_reserve(self):
        sources = resources.bound_sources(ROOT)
        self.assertEqual(len(sources), 5)
        b = resources.engineering_budget(ROOT, maps=400)
        self.assertEqual(b['terms_bytes']['runtime_library_margin_unchanged'], 2 * resources.GIB)
        self.assertEqual(b['estimated_peak_bytes'], 7891363056)
        self.assertEqual(b['estimated_peak_bytes'], sum(b['terms_bytes'].values()))
        self.assertGreater(b['terms_bytes']['history_diagnostics'], 0)
        self.assertGreater(b['terms_bytes']['callback_serialization_active_buffer'], 0)

    def test_missing_and_changed_source_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, 'Missing'):
                resources.bound_sources(root)
            p = root / next(iter(resources.SOURCES))
            p.parent.mkdir(parents=True)
            p.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'hash differs'):
                resources.bound_sources(root)

    def test_two_map_budget_is_only_pilot_eligibility(self):
        b = resources.pilot_eligibility(ROOT, host=host())
        self.assertEqual(b['status'], 'PILOT_ELIGIBLE')
        self.assertIsNone(b['native_exit_code'])
        self.assertEqual(b['budget']['estimated_peak_bytes'], 7357176499)
        self.assertNotIn('PASS', b['status'])

    def test_geometry_only_declared_k6(self):
        # Real independent integer geometry arithmetic, no pseudopotential,
        # orbital arrays or DFTK context. Counts and hashes bind all216 points.
        g = resources.geometry(ROOT)
        self.assertEqual((g['nk'], g['sum_ng'], g['max_ng']), (216, 457287, 2138))
        self.assertEqual(g['maximum_G_difference'], 17)
        self.assertEqual(len(g['ng_in_declared_order']), 216)

    def test_unknown_lifecycle_cannot_be_zero(self):
        for field in pilot()['lifecycle']:
            o = pilot()['lifecycle']
            del o[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                resources.engineering_budget(ROOT, observed=o)
        with self.assertRaises(ValueError):
            resources.engineering_budget(ROOT, maps=3)

    def test_observed_large_history_or_buffer_monotonically_increases_budget(self):
        original = resources.engineering_budget(ROOT)['estimated_peak_bytes']
        for field, value in [('max_record_bytes', 2 * resources.MIB),
                             ('serialization_buffer_capacity_bytes', 2 * resources.GIB)]:
            o = pilot()['lifecycle']
            o[field] = value
            budget = resources.engineering_budget(ROOT, observed=o)
            self.assertGreater(budget['estimated_peak_bytes'], original)
            self.assertEqual(budget['status'], 'RESOURCE_BLOCKED')
            self.assertEqual(budget['terms_bytes']['runtime_library_margin_unchanged'], 2 * resources.GIB)

    def test_counting_io_capacity_inference_is_not_a_measured_claim(self):
        p = pilot()
        o = p['lifecycle']
        o.update(serialization_capacity_evidence='INFERRED_FROM_FROZEN_BUFFER_GROWTH',
                 serialization_capacity_source_sha256=resources.BUFFER_SOURCES.copy(), julia_version='1.12.7')
        o['serialization_buffer_capacity_bytes'] = resources.inferred_buffer_capacity(o['serialization_payload_bytes'])
        self.assertEqual(o['serialization_buffer_capacity_bytes'], 1090292520)
        self.assertEqual(resources.formal_admission(ROOT, p, host=host())['status'], 'PROVISIONAL_GO_WITH_MONITORING')
        for key, value in [('julia_version', '1.12.8'), ('serialization_capacity_source_sha256', {}),
                           ('serialization_buffer_capacity_bytes', 1090292519)]:
            changed = copy.deepcopy(p)
            changed['lifecycle'][key] = value
            with self.subTest(key=key):
                self.assertEqual(resources.formal_admission(ROOT, changed, host=host())['status'], 'RESOURCE_BLOCKED')


class FormalAdmissionTests(unittest.TestCase):
    def test_two_independent_screens_and_nonzero_uncovered_growth(self):
        value = resources.formal_admission(ROOT, pilot(), host=host())
        self.assertEqual(value['status'], 'PROVISIONAL_GO_WITH_MONITORING')
        self.assertIsNone(value['native_exit_code'])
        terms = value['observational_terms_bytes']
        self.assertEqual(terms['unobserved_fluctuation_margin'], resources.GIB)
        self.assertGreater(terms['later_output'], 0)
        self.assertGreater(terms['uncovered_history'], 0)
        self.assertEqual(value['observational_estimate_bytes'], sum(terms.values()))

    def test_formal_requires_actual_complete_pilot_not_scf_or_not_run(self):
        for key, value in [('status', 'PASS'), ('completed_maps', 3), ('completed_maps', 0),
                           ('native_exit_code', None), ('native_exit_code', True),
                           ('recorder_exit_code', 9), ('geometry', {})]:
            p = pilot()
            p[key] = value
            with self.subTest(key=key, value=value):
                self.assertEqual(resources.formal_admission(ROOT, p, host=host())['status'], 'RESOURCE_BLOCKED')

    def test_failed_or_missing_resource_measurement_blocks(self):
        for key, value in [('status', 'RESOURCE_BLOCKED'), ('owned_process_cleanup_status', 'UNCONFIRMED'),
                           ('nonempty_samples', 0), ('native_exit_code', None), ('limit_bytes', 9 * resources.GIB),
                           ('peak_aggregate_rss_bytes', 8 * resources.GIB)]:
            p = pilot()
            p['resource'][key] = value
            with self.subTest(key=key):
                self.assertEqual(resources.formal_admission(ROOT, p, host=host())['status'], 'RESOURCE_BLOCKED')

    def test_observational_extrapolation_can_block_passing_source_budget(self):
        p = pilot()
        p['resource']['peak_aggregate_rss_bytes'] = int(6.5 * resources.GIB)
        v = resources.formal_admission(ROOT, p, host=host())
        self.assertEqual(v['status'], 'RESOURCE_BLOCKED')
        self.assertIn('Pilot peak plus', v['reason'])

    def test_observed_excess_cannot_be_accepted_by_low_rss(self):
        for field in ('max_record_bytes', 'serialization_buffer_capacity_bytes'):
            p = pilot()
            p['lifecycle'][field] = 2 * resources.GIB
            with self.subTest(field=field):
                value = resources.formal_admission(ROOT, p, host=host())
                self.assertEqual(value['status'], 'RESOURCE_BLOCKED')
                self.assertIn('engineering estimate', value['reason'])

    def test_missing_host_pressure_disk_or_busy_host_cannot_admit(self):
        for key, value in [('status', 'INSUFFICIENT_EVIDENCE'), ('severe_pressure', None),
                           ('severe_pressure', True), ('free_disk_bytes', 0),
                           ('active_numerical_processes', [{'pid': 12}])]:
            h = host()
            h[key] = value
            with self.subTest(key=key):
                self.assertEqual(resources.pilot_eligibility(ROOT, host=h)['status'], 'RESOURCE_BLOCKED')
                self.assertEqual(resources.formal_admission(ROOT, pilot(), host=h)['status'], 'RESOURCE_BLOCKED')


class HostMonitorTests(unittest.TestCase):
    def test_declared_warning_and_stop_without_killing_processes(self):
        normal = dict(status='KNOWN', severe=False)
        self.assertEqual(resources.monitor_decision(6 * resources.GIB, pressure=normal)['status'], 'CONTINUE')
        self.assertEqual(resources.monitor_decision(7 * resources.GIB, pressure=normal)['status'], 'STOP_AT_SAFE_BOUNDARY')
        self.assertEqual(resources.monitor_decision(7 * resources.GIB, remaining_growth_bytes=1, pressure=normal)['status'], 'WARNING')
        self.assertEqual(resources.monitor_decision(7 * resources.GIB, remaining_growth_bytes=resources.GIB, pressure=normal)['status'], 'STOP_AT_SAFE_BOUNDARY')
        self.assertEqual(resources.monitor_decision(8 * resources.GIB, pressure=normal)['status'], 'RESOURCE_LIMIT')
        self.assertEqual(resources.monitor_decision(1, pressure=dict(status='KNOWN', severe=True))['status'], 'RESOURCE_LIMIT')
        self.assertEqual(resources.monitor_decision(1, pressure=dict(status='UNKNOWN', severe=None))['status'], 'MONITORING_UNAVAILABLE')

    def test_host_denial_preserves_unknown(self):
        with patch.object(resources, 'process_table', side_effect=ValueError('ps denied')):
            r = resources.host_preflight(ROOT)
        self.assertEqual(r['status'], 'INSUFFICIENT_EVIDENCE')
        self.assertIsNone(r['severe_pressure'])
        self.assertIsNone(r['native_exit_code'])
        self.assertIn('ps denied', r['reason'])

    def test_pressure_failure_does_not_become_normal(self):
        with patch.object(resources.platform, 'system', return_value='Darwin'), \
             patch.object(resources, '_command', side_effect=ValueError('query unavailable')):
            r = resources.host_pressure()
        self.assertEqual(r['status'], 'UNKNOWN')
        self.assertIsNone(r['severe'])

    def test_macos_reported_critical_pressure(self):
        with patch.object(resources.platform, 'system', return_value='Darwin'), \
             patch.object(resources, '_command', side_effect=['System-wide memory free percentage: 32%\n', '4\n']):
            self.assertTrue(resources.host_pressure()['severe'])

    def test_existing_worker_detection_ignores_document_read(self):
        def row(pid, command):
            return dict(pid=pid, pgid=pid, command=command)
        result = resources.active_numerical_processes([
            row(1, '/bin/zsh -c cat scripts/run_si_soc.jl'),
            row(2, '/path/julia --startup-file=no scripts/run_si_soc.jl extra'),
            row(3, '/path/pw.x -in x.in')])
        self.assertEqual([x['pid'] for x in result], [2, 3])


if __name__ == '__main__':
    unittest.main()
