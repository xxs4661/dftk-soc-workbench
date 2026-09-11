"""Synthetic recorded-arithmetic protocols; no Julia, kernels or real arrays.

Fixtures represent recorder numbers and owner tables, not physical states.
The public frozen plan is read only to test its unchanged declared thresholds.
"""
import contextlib
import copy
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import replay_soc_core_memory as replay

EXECUTION = 'a' * 40
HASH = 'b' * 64


def measurement(name, *, allocated=100, seconds=1.0):
    def sample(index):
        return dict(index=index, status='PASS', allocated_bytes=allocated,
                    time_seconds=seconds, gc_seconds=0., compile_seconds=0.,
                    recompile_seconds=0., lock_conflicts=0,
                    gcstats={key: 0 for key in replay.GC_FIELDS},
                    consumed=dict(real=1., imaginary=0.))
    result = dict(operation=name, status='PASS', requested_samples=5,
                  completed_samples=5, warmup_count=1, warmup=sample(0),
                  samples=[sample(i) for i in range(1, 6)])
    result['statistics'] = {field: dict(min=result['samples'][0][field], median=result['samples'][0][field], max=result['samples'][0][field]) for field in replay.FIELDS}
    return result


def dispatch(name, core):
    operator, n = name.rsplit('_', 1); n = int(n)
    module, path, receiver = (('Main.FRIntegration', '<workbench>/prototypes/fr_integration/runtime.jl', {'FR': 'RuntimeFRBlock', 'component': 'RuntimeComponentBlock', 'full_H': 'RuntimeFullHamiltonian'}[operator]) if core else
        {'FR': ('Main.RelativisticProjectors', '<reference-root>/prototypes/relativistic/operator.jl', 'FRNonlocalOperator'),
         'component': ('Main.SpinorPrototype', '<reference-root>/prototypes/spinor/operators.jl', 'ComponentOperator'),
         'full_H': ('Main.FRIntegration', '<reference-root>/prototypes/fr_integration/hamiltonian.jl', 'FullHamiltonianBlock')}[operator])
    before = dict(full_mul_calls=0, fr_mul_calls=0, full_columns=0, fr_columns=0,
                  common=dict(operator_mul_calls=0, operator_columns=0, scalar_mul_calls=0, scalar_columns=0))
    after = copy.deepcopy(before)
    if operator != 'FR':
        after['common'] = dict(operator_mul_calls=6, operator_columns=6 * n, scalar_mul_calls=12, scalar_columns=12 * n)
    if operator == 'full_H':
        after.update(full_mul_calls=6, fr_mul_calls=6, full_columns=6 * n, fr_columns=6 * n)
    return dict(module_name=module, source=path, receiver_type=module + '.' + receiver,
                line=1, columns_per_call=n, call_count_including_warmup=6, before_counts=before, after_counts=after)


def graph(*, core=False):
    sizes = [100, 20] if core else [100, 100]
    return dict(status='COMPLETE_FOR_RECOGNIZED_JULIA_STORAGE',
                unaccounted_arrays=[], combined_summarysize_bytes=sum(sizes) + 80,
                dense_unique_payload_bytes=sum(sizes), backing_owner_payload_sum_bytes=sum(sizes),
                overlap_payload_bytes=0, backing_owners=2, array_objects=2,
                opaque_pointer_fields=0,
                storage=[dict(storage_id=i + 1, first_path='roots.data.X' if i == 0 else 'roots.context_registry.ht', element_type='UInt8', allocated_elements=size, sizeof_payload_bytes=size) for i, size in enumerate(sizes)],
                arrays=[dict(object_id=i + 1, storage_id=i + 1, parent_object_id=None) for i in range(2)])


def fixtures():
    contract, sources = replay.preparation(ROOT)
    data = dict(schema_version=1, phase='9A', execution_commit=EXECUTION, suites={})
    for suite in replay.SUITES:
        core = suite.startswith('CORE-'); label = suite.split('-')[1]
        original = sources['historical_endpoints'][label]
        native = dict(exit_code=0, interrupted=False)
        resource = dict(status='PASS', owned_process_cleanup_status='PASS', native_exit_code=0,
                        limit_bytes=8 * 1024**3, sample_interval_seconds=.1,
                        peak_aggregate_rss_bytes=1000, samples=2, nonempty_samples=1,
                        remaining_observed_processes=[])
        outer = dict(suite=suite, run_id=suite + '-synthetic', execution_commit=EXECUTION if core else replay.REFERENCE,
                     overall_status='PASS', exit_code=0, process_exit_code=0, worker_started=True,
                     resource=resource, worker_result_sha256=HASH)
        worker = dict(schema_version=1, phase='9A', suite=suite, run_id=outer['run_id'],
                      execution_commit=outer['execution_commit'], base_commit=replay.BASE,
                      preparation_commit=replay.PREPARATION, backend='OWNED_CORE' if core else 'LEGACY_REFERENCE',
                      overall_status='PASS', execution_status='PASS', measurement_status='COMPLETE', exit_code=0,
                      environment={'status': 'PASS'}, parallelism=dict(julia=1, blas=1, fft=1, mpi=1),
                      input_unchanged=dict(payload=True, rhs=True, checkpoint=True, original_result=True),
                      input=dict(checkpoint_sha256=original['checkpoint_sha256'], checkpoint_bytes=original['checkpoint_bytes'],
                                 raw_result_sha256=original['raw_result_sha256'], historical_execution_commit=original['execution_commit'],
                                 historical_status='HISTORICAL_REUSED', k_count=8 if label == 'B0' else 64,
                                 target_states=24, no_scf=True, no_eigensolve=True, no_occupation_solve=True,
                                 physical_payload_sha256=HASH, case_sha256=HASH, n_in_sha256=HASH, n_out_sha256=HASH),
                      canonical_inputs={'sha256': HASH}, outputs={name: {'sha256': HASH} for name in replay.OPERATIONS},
                      measurements={name: measurement(name, allocated=(80 if name == 'pipeline' else 40) if core else 100) for name in replay.OPERATIONS},
                      cold_initialization={key: dict(time=1., bytes=100, gctime=0., compile_time=0., recompile_time=0., lock_conflicts=0) for key in ('context_construction', 'H_construction')},
                      live_memory={phase: replay.compact_storage(graph(core=core)) for phase in replay.PHASES},
                      legacy_lifetime=dict(expected_contexts=0 if core else 7,
                                           global_source_registrations=0 if core else 7,
                                           global_context_registrations=0 if core else 7,
                                           registry_cleared=False, forced_gc=False,
                                           close_api='SCOPED_PRIVATE_OWNERS' if core else 'NONE'))
        if core:
            worker.update(runtime_before_close=dict(backend='soc-core', closed=False, owned_source_entries=1, max_rhs=30, workspace_capacity={'max_rhs': 30}),
                          runtime_after_close=dict(backend='soc-core', closed=True, owned_source_entries=0, workspace_released=True, max_rhs=30))
        for name in replay.MICRO:
            worker['measurements'][name]['dispatch'] = dispatch(name, core)
        data['suites'][suite] = dict(outer=outer, worker=worker, native=native, resource=resource,
                                    raw_worker_sha256=HASH,
                                    raw_outer_descriptor=dict(path='.work/phase9a/static/' + suite + '-synthetic/result.json', sha256=HASH))
    comparison = dict(schema_version=1, phase='9A', execution_commit=EXECUTION,
                      overall_status='PASS', exit_code=0, environment={'status': 'PASS'}, pairs=[])
    for label in ('B0', 'K4'):
        arrays, scalars = replay.expected_comparison_labels(8 if label == 'B0' else 64)
        rows = [dict(kind='array', label=name, reference_norm=1., candidate_norm=1., absolute_L2=0., relative=0., max_abs=0.,
                     bitwise_equal=True, limit=1e-12, status='PASS', shape=[1], element_type='Float64',
                     evidence_level='RUNNER_REPORTED_PRIVATE_ARRAY_COMPARISON') for name in sorted(arrays)]
        for name in sorted(scalars):
            value = 0.
            if '/terms_ha/' in name:
                value = -1.
            elif name.endswith('/internal_energy_ha'):
                value = -7.
            elif name.endswith('/free_energy_ha'):
                value = -7.002
            elif name.endswith('/entropy_energy_ha'):
                value = -.002
            elif name.endswith('/entropy_dimensionless'):
                value = 2.
            rows.append(dict(kind='scalar', label=name, reference=value, candidate=value, difference=0.,
                             limit=0. if name.endswith('/entropy_dimensionless') else 1e-10,
                             unit='dimensionless' if name.endswith('/entropy_dimensionless') else 'Ha/cell',
                             status='PASS', evidence_level='PUBLIC_ARITHMETIC'))
        comparison['pairs'].append(dict(label=label, status='PASS',
            reference=data['suites']['REF-' + label]['raw_outer_descriptor'],
            candidate=data['suites']['CORE-' + label]['raw_outer_descriptor'],
            input_identity=HASH, checkpoint_sha256=sources['historical_endpoints'][label]['checkpoint_sha256'], rows=rows,
            density_integrals=[dict(label=name, reference_electrons=8., candidate_electrons=8., reference_error=0., candidate_error=0., electron_limit=1e-8, status='PASS') for name in ('density', 'energy', 'pipeline')]))
    return data, comparison


class ReplayArithmeticTests(unittest.TestCase):
    def setUp(self):
        self.data, self.comparison = fixtures()
        self.addCleanup(patch.stopall)
        patch.object(replay, 'environment_check').start()
        patch.object(replay, 'source_check').start()
        patch.object(replay, 'comparison_source_check').start()

    def assess(self):
        return replay.assessment(ROOT, self.data, self.comparison)[0]

    def replace_measurement(self, worker, name, **kwargs):
        original = worker['measurements'][name].get('dispatch')
        worker['measurements'][name] = measurement(name, **kwargs)
        if original:
            worker['measurements'][name]['dispatch'] = original

    def test_all_four_all_five_and_all_operations_pass(self):
        result = self.assess()
        self.assertEqual((result['overall_status'], result['exit_code']), ('PASS', 0))
        self.assertEqual(set(result['statistics']), set(replay.SUITES))
        self.assertEqual(result['pairs']['K4']['operations']['FR_24']['allocation_median_ratio'], .4)

    def test_missing_fifth_sample_is_rejected(self):
        self.data['suites']['CORE-B0']['worker']['measurements']['FR_24']['samples'].pop()
        with self.assertRaisesRegex(ValueError, 'five samples'):
            self.assess()

    def test_middle_sample_changes_median_not_only_extremes(self):
        item = measurement('FR_24')
        for sample, value in zip(item['samples'], (10, 20, 30, 40, 50)):
            sample['allocated_bytes'] = value
        item['statistics']['allocated_bytes'] = dict(min=10, median=30, max=50)
        self.assertEqual(replay.sample_statistics(item, 'FR_24')['allocated_bytes']['median'], 30)
        item['statistics']['allocated_bytes']['median'] = 20
        with self.assertRaisesRegex(ValueError, 'statistics'):
            replay.sample_statistics(item, 'FR_24')

    def test_nan_in_sample_or_consumed_output_is_rejected(self):
        for field in ('time_seconds', 'consumed'):
            with self.subTest(field=field):
                item = measurement('FR_24')
                item['samples'][3][field] = math.nan if field != 'consumed' else dict(real=math.nan)
                with self.assertRaises(ValueError):
                    replay.sample_statistics(item, 'FR_24')

    def test_boolean_counts_and_fractional_allocation_are_rejected(self):
        for field, value in (('index', True), ('allocated_bytes', 100.5)):
            item = measurement('FR_24'); item['samples'][0][field] = value
            with self.assertRaises(ValueError):
                replay.sample_statistics(item, 'FR_24')

    def test_warmup_failure_and_reordering_are_not_pass(self):
        for mutate in (lambda item: item['warmup'].update(status='FAIL'), lambda item: item['samples'].reverse()):
            item = measurement('FR_24'); mutate(item)
            with self.assertRaises(ValueError):
                replay.sample_statistics(item, 'FR_24')

    def test_failed_suite_cannot_be_replaced_by_old_pass(self):
        self.data['suites']['CORE-K4']['worker']['overall_status'] = 'FAIL'
        with self.assertRaisesRegex(ValueError, 'Unsuccessful'):
            self.assess()

    def test_mismatched_execution_and_input_are_rejected(self):
        self.data['suites']['CORE-K4']['worker']['execution_commit'] = replay.REFERENCE
        with self.assertRaisesRegex(ValueError, 'execution'):
            self.assess()

    def test_resource_failure_and_missing_samples_are_rejected(self):
        for field, value in (('status', 'RESOURCE_BLOCKED'), ('nonempty_samples', 0), ('peak_aggregate_rss_bytes', 8 * 1024**3)):
            data = copy.deepcopy(self.data)
            self.data['suites']['CORE-B0']['resource'][field] = value
            with self.assertRaises(ValueError):
                self.assess()
            self.data = data

    def test_native_failure_not_swallowed(self):
        self.data['suites']['CORE-B0']['native']['exit_code'] = 1
        with self.assertRaisesRegex(ValueError, 'native'):
            self.assess()

    def test_allocation_boundaries_apply_to_each_material_grid(self):
        for name, allowed, failed in (('FR_24', 50, 51), ('pipeline', 110, 111)):
            worker = self.data['suites']['CORE-K4']['worker']
            self.replace_measurement(worker, name, allocated=allowed)
            self.assertEqual(self.assess()['allocation_status'], 'PASS')
            self.replace_measurement(worker, name, allocated=failed)
            result = self.assess()
            self.assertEqual((result['allocation_status'], result['overall_status'], result['exit_code']), ('FAIL', 'FAIL', 9))
            self.replace_measurement(worker, name, allocated=40)

    def test_time_review_is_not_failure_and_boundary_is_strict(self):
        worker = self.data['suites']['CORE-B0']['worker']
        self.replace_measurement(worker, 'FR_24', allocated=40, seconds=1.1)
        self.assertEqual(self.assess()['time_status'], 'PASS')
        self.replace_measurement(worker, 'FR_24', allocated=40, seconds=math.nextafter(1.1, math.inf))
        result = self.assess()
        self.assertEqual((result['time_status'], result['overall_status'], result['exit_code']), ('PERFORMANCE_REVIEW_REQUIRED', 'PASS', 0))

    def test_no_live_reduction_is_failure_without_time_excuse(self):
        for label in ('B0', 'K4'):
            self.data['suites']['CORE-' + label]['worker']['live_memory'] = copy.deepcopy(self.data['suites']['REF-' + label]['worker']['live_memory'])
        result = self.assess()
        self.assertEqual((result['live_storage_reduction_status'], result['exit_code']), ('FAIL', 9))

    def test_fake_unique_size_cannot_pass_owner_arithmetic(self):
        self.data['suites']['CORE-B0']['worker']['live_memory']['session_closed']['dense_unique_payload_bytes'] = 1
        with self.assertRaisesRegex(ValueError, 'unique storage'):
            self.assess()

    def test_fake_zero_registry_or_unclosed_runtime_is_rejected(self):
        worker = self.data['suites']['CORE-B0']['worker']
        worker['legacy_lifetime']['global_context_registrations'] = 1
        with self.assertRaisesRegex(ValueError, 'registrations'):
            self.assess()
        worker['legacy_lifetime']['global_context_registrations'] = 0
        worker['runtime_after_close']['workspace_released'] = False
        with self.assertRaisesRegex(ValueError, 'closed/released'):
            self.assess()

    def test_missing_comparison_row_or_looser_limit_is_rejected(self):
        row = self.comparison['pairs'][0]['rows'].pop()
        with self.assertRaisesRegex(ValueError, 'Missing comparison'):
            self.assess()
        self.comparison['pairs'][0]['rows'].append(row)
        row['limit'] = 1e-8
        with self.assertRaisesRegex(ValueError, 'tolerance'):
            self.assess()

    def test_failed_comparison_preserves_nonpass_gate(self):
        row = next(r for r in self.comparison['pairs'][0]['rows'] if r['kind'] == 'array')
        row.update(absolute_L2=1e-6, relative=1e-6, max_abs=1e-6, bitwise_equal=False, status='FAIL')
        self.comparison['pairs'][0]['status'] = 'FAIL'
        self.comparison.update(overall_status='FAIL', exit_code=9)
        result = self.assess()
        self.assertEqual((result['equivalence_status'], result['overall_status'], result['exit_code']), ('FAIL', 'FAIL', 9))

    def test_norm_ratio_and_signed_scalar_arithmetic_checked(self):
        row = next(r for r in self.comparison['pairs'][0]['rows'] if r['kind'] == 'array')
        row['relative'] = 1e-15
        with self.assertRaisesRegex(ValueError, 'Relative norm arithmetic'):
            self.assess()

    def test_energy_terms_and_entropy_are_not_reinterpreted(self):
        for name in ('energy/internal_energy_ha', 'energy/entropy_dimensionless'):
            row = next(r for r in self.comparison['pairs'][0]['rows'] if r['label'] == name)
            saved = copy.deepcopy(row)
            row.update(reference=row['reference'] + 1., candidate=row['candidate'] + 1.)
            with self.assertRaisesRegex(ValueError, 'arithmetic'):
                self.assess()
            row.update(saved)

    def test_wrong_actual_dispatch_and_scalar_units_rejected(self):
        record = self.data['suites']['CORE-B0']['worker']['measurements']['FR_24']['dispatch']
        record['receiver_type'] = 'Main.RelativisticProjectors.FRNonlocalOperator'
        with self.assertRaisesRegex(ValueError, 'dispatch'):
            self.assess()
        record.update(dispatch('FR_24', True))
        row = next(r for r in self.comparison['pairs'][0]['rows'] if r['kind'] == 'scalar')
        row['unit'] = 'eV'
        with self.assertRaisesRegex(ValueError, 'unit'):
            self.assess()


class ReplayTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.area = self.root / 'results/soc-core-memory'; self.area.mkdir(parents=True)

    def test_raw_hash_tamper_symlink_and_private_path_rejected(self):
        path = self.area / 'record.json'; path.write_text('{}\n')
        entry = replay.descriptor(self.root, path)
        self.assertEqual(replay.bound(self.root, entry)[0], {})
        path.write_text('{"tamper":true}\n')
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            replay.bound(self.root, entry)
        alias = self.area / 'alias.json'; alias.symlink_to(path)
        with self.assertRaisesRegex(ValueError, 'aliased'):
            replay.relative_file(self.root, alias.relative_to(self.root).as_posix())
        with self.assertRaises(ValueError):
            replay.relative_file(self.root, '../record.json')

    def test_duplicate_keys_nonfinite_and_overflow_are_rejected(self):
        path = self.area / 'record.json'
        for encoded in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}'):
            path.write_text(encoded)
            with self.assertRaises(ValueError):
                replay.read(path)

    def test_private_owner_duplicate_missing_alias_and_size_tamper(self):
        for mutation in (lambda g: g['storage'][1].update(storage_id=1),
                         lambda g: g['arrays'][1].update(storage_id=3),
                         lambda g: g['arrays'][1].update(parent_object_id=42),
                         lambda g: g.update(backing_owner_payload_sum_bytes=1)):
            value = graph(); mutation(value)
            with self.assertRaises(ValueError):
                replay.compact_storage(value)

    def test_parent_cycles_and_different_backing_owners_rejected(self):
        value = graph(); value['arrays'][1]['parent_object_id'] = 1
        with self.assertRaisesRegex(ValueError, 'different-owner'):
            replay.compact_storage(value)
        value['arrays'][1]['storage_id'] = 1
        value['arrays'][0]['parent_object_id'] = 2
        with self.assertRaisesRegex(ValueError, 'Cyclic'):
            replay.compact_storage(value)

    def test_private_failure_writes_new_nonpass_gate(self):
        request = self.root / 'request.json'; request.write_text('{"execution_commit":"' + EXECUTION + '","suite_receipts":{}}')
        output = self.root / '.work/phase9a/new-gate'
        result = replay.build_gate(self.root, request, output)
        self.assertEqual(result['exit_code'], 9)
        self.assertEqual(replay.read(output / 'gate.json')['overall_status'], 'FAIL')
        self.assertFalse((output / 'performance.json').exists())
        with self.assertRaises(ValueError):
            replay.build_gate(self.root, request, output)

    def test_public_replay_rejects_forged_time_status(self):
        tool_sources = {path: replay.hashlib.sha256(b'synthetic source').hexdigest() for path in ('scripts/replay_soc_core_memory.py', replay.BENCH + 'run.py')}
        data = dict(execution_commit=EXECUTION, gate_tool_sources=tool_sources, suites={name: {'raw_outer_descriptor': {'path': name, 'sha256': HASH}} for name in replay.SUITES})
        fresh = dict(overall_status='PASS', exit_code=0, identity_status='PASS', equivalence_status='PASS', allocation_status='PASS', resource_status='PASS', live_storage_reduction_status='PASS', time_status='PERFORMANCE_REVIEW_REQUIRED', scope='Synthetic recorder arithmetic only')
        gate = dict(fresh, execution_commit=EXECUTION, gate_tool_sources=tool_sources, suite_receipts={name: data['suites'][name]['raw_outer_descriptor'] for name in replay.SUITES})
        manifest = dict(schema_version=1, phase='9A', execution_commit=EXECUTION)
        for name, value in (('replay_data', data), ('comparison', {}), ('performance', fresh)):
            path = self.area / (name + '.json'); path.write_text(json.dumps(value))
            manifest[name] = replay.descriptor(self.root, path)
            gate[name] = manifest[name]
        path = self.area / 'gate.json'; path.write_text(json.dumps(gate)); manifest['gate'] = replay.descriptor(self.root, path)
        evidence = self.area / 'evidence.json'; evidence.write_text(json.dumps(manifest))
        with patch.object(replay, 'assessment', return_value=(fresh, {})), patch.object(replay, 'git_bytes', return_value=b'synthetic source'):
            self.assertEqual(replay.replay(self.root, evidence)['replay_exit_code'], 0)
            gate['time_status'] = 'PASS'; path = self.area / 'gate.json'; path.write_text(json.dumps(gate))
            manifest['gate'] = replay.descriptor(self.root, path); evidence.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'contradicts'):
                replay.replay(self.root, evidence)

    def test_gate_source_head_and_clean_tree_are_required(self):
        with patch.object(replay.subprocess, 'check_output', return_value='c' * 40 + '\n'):
            with self.assertRaisesRegex(ValueError, 'candidate HEAD'):
                replay.gate_tool_guard(self.root, EXECUTION)
        with patch.object(replay.subprocess, 'check_output', side_effect=[EXECUTION + '\n', ' M scripts/replay_soc_core_memory.py\n']):
            with self.assertRaisesRegex(ValueError, 'clean'):
                replay.gate_tool_guard(self.root, EXECUTION)

    def test_cli_help_zero_protocol_error_nonzero(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                replay.main(['--help'])
            self.assertEqual(caught.exception.code, 0)
            self.assertEqual(replay.main(['replay', '--root', str(self.root), '--evidence', str(self.area / 'missing.json')]), 9)


if __name__ == '__main__':
    unittest.main()
