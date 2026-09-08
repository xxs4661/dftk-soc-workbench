"""Synthetic Phase8A.1 semantics/protocol tests; no historical numerical run.

The old fixtures and numerical functions are reused unchanged. Mocked subprocess
receipts represent recorder protocols only, never a real historical replay.
"""
import contextlib
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'tests')]
import check_si_soc_status as semantics
from si_soc_comparison import compare_spectra, HARTREE_EV
from test_si_soc_comparison import receipt, case


def plan():
    # Public predeclared rules only; no real spectra, densities or checkpoints.
    return json.loads((ROOT/semantics.CASE/'plan.json').read_text())


def inputs(low=()):
    d, q, null = receipt('D'), receipt('Q'), receipt('D', null=True)
    for label, value in (('D', d), ('Q', q)):
        if label in low:
            value['fermi_energy_ha'] = .3/HARTREE_EV
    return d, q, null, case()


def evaluation(low=()):
    return semantics.evaluate(*inputs(low), plan())


class StatusRulesTests(unittest.TestCase):
    def test_old_numeric_pass_but_incomplete_occupation_prerequisites(self):
        summary, fresh = evaluation(('D', 'Q'))
        self.assertEqual(fresh['manifold_assignment_status'], 'PASS')
        self.assertEqual(summary['legacy']['manifold_assignment_status'], 'PASS')
        for key in ('fixed_window_structure_status', 'fixed_window_splitting_comparison_status', 'spin_trace_control_status'):
            self.assertEqual(summary[key], 'PASS')
        self.assertEqual(summary['gamma_occupation_diagnostic_status'], 'REVIEW_REQUIRED')
        self.assertEqual(summary['manifold_prerequisites_status'], 'REVIEW_REQUIRED')
        self.assertEqual(summary['manifold_assignment_status'], 'MANIFOLD_ASSIGNMENT_REVIEW_REQUIRED')
        self.assertAlmostEqual(summary['key_numbers']['D_delta_so_ev'], .031)

    def test_each_program_occupation_is_required_independently(self):
        for low in ('D', 'Q'):
            with self.subTest(low=low):
                summary, _ = evaluation((low,))
                self.assertIn(low+'_occupation', summary['unmet_measured_prerequisites'])
                other = 'Q' if low == 'D' else 'D'
                self.assertNotIn(other+'_occupation', summary['unmet_measured_prerequisites'])
                self.assertEqual(summary['manifold_assignment_status'], 'MANIFOLD_ASSIGNMENT_REVIEW_REQUIRED')

    def test_exact_inclusive_boundary_and_adjacent_float_values(self):
        _, original = evaluation()
        p = plan(); threshold = p['grouping']['occupation_near_full_min']
        indices = p['grouping']['lower_doublet_one_based']+p['grouping']['upper_quartet_one_based']
        for value, accepted in ((math.nextafter(threshold, -math.inf), False),
                                (threshold, True), (math.nextafter(threshold, math.inf), True)):
            for label in ('D', 'Q'):
                fresh = copy.deepcopy(original)
                for i in indices:
                    fresh['gamma_fd_occupations_at_existing_scf_mu'][label][i-1] = value
                with self.subTest(value=value, label=label):
                    summary = semantics.derive_status(fresh, p)
                    self.assertEqual(summary['occupation_rule']['minimum_FD'][label], value)
                    self.assertEqual(summary['gamma_occupation_diagnostic_status'], 'PASS' if accepted else 'REVIEW_REQUIRED')
                    self.assertEqual(summary['manifold_prerequisites_status'], 'PASS' if accepted else 'REVIEW_REQUIRED')

    def test_all_measured_prerequisites_do_not_certify_physics(self):
        summary, _ = evaluation()
        self.assertEqual(summary['manifold_prerequisites_status'], 'PASS')
        self.assertEqual(summary['manifold_assignment_status'], 'MEASURED_PREREQUISITES_PASS')
        self.assertNotEqual(summary['manifold_assignment_status'], 'PASS')
        self.assertEqual(summary['physical_manifold_interpretation'], 'REVIEW_REQUIRED')
        self.assertEqual(summary['limits']['physical_convergence'], 'NOT_ESTABLISHED')
        self.assertEqual(summary['limits']['space_group_irrep_assignment'], 'NOT_COMPUTED')
        self.assertIn('NOT_MEASURED', summary['limits']['band_crossing_between_sampled_probes'])

    def test_isolation_and_quartet_width_failure_with_full_occupation(self):
        for defect in ('isolation', 'width'):
            d, q, null, cfg = inputs()
            if defect == 'isolation':
                d['kpoints'][0]['eigenvalues_ha'][:2] = [-.04/HARTREE_EV]*2
            else:
                d['kpoints'][0]['eigenvalues_ha'][6:8] = [.001/HARTREE_EV]*2
            with self.subTest(defect=defect):
                summary, fresh = semantics.evaluate(d, q, null, cfg, plan())
                self.assertEqual(summary['gamma_occupation_diagnostic_status'], 'PASS')
                self.assertEqual(summary['fixed_window_structure_status'], 'MISMATCH')
                self.assertEqual(summary['manifold_assignment_status'], 'MANIFOLD_ASSIGNMENT_REVIEW_REQUIRED')
                self.assertEqual(len(fresh['D_gamma']['values_ha']), 24)

    def test_other_required_measured_gates_cannot_be_dropped(self):
        _, original = evaluation()
        for path in (('spin_trace_control_status',), ('splitting_comparison_status',),
                     ('time_reversal', 'Q', 'status'), ('D_precision', 'D_full', 'status'),
                     ('D_precision', 'D_null', 'status'), ('Q_eigensolver_status',)):
            fresh = copy.deepcopy(original); target = fresh
            for key in path[:-1]: target = target[key]
            target[path[-1]] = 'EIGENSOLVER_REVIEW_REQUIRED' if path == ('Q_eigensolver_status',) else 'MISMATCH'
            with self.subTest(path=path):
                summary = semantics.derive_status(fresh, plan())
                self.assertEqual(summary['manifold_prerequisites_status'], 'REVIEW_REQUIRED')
                self.assertNotEqual(summary['manifold_assignment_status'], 'PASS')

    def test_independent_energy_zero_shifts_require_matching_mu_shift(self):
        d, q, null, cfg = inputs()
        expected, _ = semantics.evaluate(d, q, null, cfg, plan())
        for value, offset in ((d, -.21), (q, .17), (null, -.21)):
            value['fermi_energy_ha'] += offset
            for point in value['kpoints']:
                point['eigenvalues_ha'] = [x+offset for x in point['eigenvalues_ha']]
        shifted, _ = semantics.evaluate(d, q, null, cfg, plan())
        for key in ('fixed_window_structure_status', 'fixed_window_splitting_comparison_status',
                    'gamma_occupation_diagnostic_status', 'manifold_prerequisites_status'):
            self.assertEqual(shifted[key], expected[key])
        self.assertAlmostEqual(shifted['key_numbers']['D_delta_so_ev'], expected['key_numbers']['D_delta_so_ev'], places=12)
        for label in ('D', 'Q'):
            self.assertAlmostEqual(shifted['occupation_rule']['minimum_FD'][label], expected['occupation_rule']['minimum_FD'][label], places=15)
        # Removing Q's accompanying mu shift must change the FD diagnosis.
        q['fermi_energy_ha'] -= .17
        unpaired, _ = semantics.evaluate(d, q, null, cfg, plan())
        self.assertEqual(unpaired['gamma_occupation_diagnostic_status'], 'REVIEW_REQUIRED')
        self.assertIn('Q_occupation', unpaired['unmet_measured_prerequisites'])

    def test_null_no_soc_signal_is_compatible_with_control_success(self):
        summary, fresh = evaluation()
        self.assertEqual(fresh['D_null_gamma']['resolvable_soc_status'], 'MISMATCH')
        self.assertEqual(summary['spin_trace_control_status'], 'PASS')
        self.assertEqual(summary['manifold_prerequisites_status'], 'PASS')

    def test_numeric_output_and_all_input_objects_remain_unchanged(self):
        args = inputs(('D', 'Q'))
        before = json.dumps(args, sort_keys=True, allow_nan=False)
        original = compare_spectra(*args)
        _, fresh = semantics.evaluate(*args, plan())
        semantics.close(fresh, original)
        self.assertEqual(fresh, original)
        self.assertEqual(json.dumps(args, sort_keys=True, allow_nan=False), before)
        self.assertEqual(fresh['Q_warnings'], original['Q_warnings'])

    def test_malformed_values_shapes_and_required_states_are_errors(self):
        _, original = evaluation()
        for value in (float('nan'), float('inf'), -.01, 1.01, True, '1'):
            fresh = copy.deepcopy(original)
            fresh['gamma_fd_occupations_at_existing_scf_mu']['Q'][3] = value
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                semantics.derive_status(fresh, plan())
        for defect in ('short', 'missing_status', 'bad_status', 'nonfinite_splitting'):
            fresh = copy.deepcopy(original)
            if defect == 'short': fresh['gamma_fd_occupations_at_existing_scf_mu']['D'].pop()
            if defect == 'missing_status': del fresh['Q_eigensolver_status']
            if defect == 'bad_status': fresh['spin_trace_control_status'] = 'INFO_ONLY'
            if defect == 'nonfinite_splitting': fresh['D_gamma']['delta_so_ev'] = float('nan')
            with self.subTest(defect=defect), self.assertRaises((ValueError, TypeError, KeyError)):
                semantics.derive_status(fresh, plan())

    def test_wrong_source_missing_state_and_unauthorized_plan_rejected(self):
        for defect in ('density_source_sha256', 'source_scf_run_id', 'run_id', 'missing_band'):
            d, q, null, cfg = inputs()
            if defect == 'missing_band': d['kpoints'][0]['eigenvalues_ha'].pop()
            else: d[defect] = 'wrong-source'
            with self.subTest(defect=defect), self.assertRaises((ValueError, KeyError)):
                semantics.evaluate(d, q, null, cfg, plan())
        for threshold in (.9999, math.nextafter(.99999999, math.inf)):
            p = plan(); p['grouping']['occupation_near_full_min'] = threshold
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                semantics.evaluate(*inputs(), p)
        p = plan(); p['grouping']['upper_quartet_one_based'] = [7, 8, 9, 10]
        with self.assertRaises(ValueError): semantics.evaluate(*inputs(), p)
        p = plan(); p['gates']['split_D_minus_Q_abs_ev'] = .1
        with self.assertRaises(ValueError): semantics.evaluate(*inputs(), p)

    def test_receipt_counts_and_warning_evidence_keep_exact_types(self):
        for key, bad in (('schema_version', True), ('schema_version', 1.),
                         ('n_electrons', 8.), ('n_bands', '24'), ('occupation_capacity', True)):
            args = inputs(); args[0][key] = bad
            with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                semantics.evaluate(*args, plan())
        for bad in (None, 0, 'false'):
            args = inputs(); args[1]['warning_evidence']['eigenvalues_not_converged'] = bad
            with self.subTest(warning=bad), self.assertRaises(ValueError):
                semantics.evaluate(*args, plan())

    def test_replayed_types_and_integer_indices_are_exact(self):
        original = {'version': 2, 'indices': [3, 4], 'threshold': .99999999, 'status': 'PASS'}
        semantics.exact_discrete(original, copy.deepcopy(original))
        for key, bad in (('version', 2.), ('indices', [3, 4.00000000000001]),
                         ('indices', [3, 5]), ('threshold', '0.99999999')):
            changed = copy.deepcopy(original); changed[key] = bad
            with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                semantics.exact_discrete(original, changed)


class StatusProtocolTests(unittest.TestCase):
    @contextlib.contextmanager
    def protocol(self, low=('D', 'Q'), process=None):
        d, q, null, cfg = inputs(low)
        documents = {'case.json': cfg, 'plan.json': plan(), 'D-spectrum.json': d,
                     'Q-spectrum.json': q, 'D-null.json': null,
                     'D-SCF.json': {'run_id': cfg['binding']['D']['scf_run_id'],
                                    'final': {'mu_ha': d['fermi_energy_ha'],
                                              'n_out_sha256': cfg['binding']['D']['density_sha256']}},
                     'qe-result.json': {'run_id': cfg['binding']['Q']['scf_run_id'],
                                        'fermi_energy_ha': q['fermi_energy_ha'],
                                        'density_source_sha256': cfg['binding']['Q']['density_sha256']},
                     'comparison.json': compare_spectra(d, q, null, cfg),
                     'evidence.json': {'bindings': cfg['binding'], 'execution_commit': 'b'*40}}
        process = process or SimpleNamespace(returncode=0, stdout='{"offline_status":"PASS"}\n', stderr='')
        source_bytes = (ROOT/semantics.SELF).read_bytes()
        def git(_root, *args):
            if args == ('rev-parse', 'HEAD'): return b'c'*40+b'\n'
            if args[0] == 'show' and args[1].endswith(':'+semantics.SELF): return source_bytes
            if args[0] == 'show' and args[1].endswith('/status-correction/README.md'): return b'Synthetic status rules\n'
            raise AssertionError('Unexpected mocked Git query: '+repr(args))
        def digest(path):
            return hashlib.sha256(source_bytes).hexdigest() if path == ROOT/semantics.SELF else 'f'*64
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(semantics, 'authenticate', return_value=12))
            stack.enter_context(patch.object(semantics.subprocess, 'run', return_value=process))
            stack.enter_context(patch.object(semantics, 'read', side_effect=lambda p: copy.deepcopy(documents[p.name])))
            stack.enter_context(patch.object(semantics, 'digest', side_effect=digest))
            stack.enter_context(patch.object(semantics, 'git', side_effect=git))
            yield documents

    def cli(self, strict=False, record=False):
        output = io.StringIO()
        args = ['--source-root', 'synthetic-public-source']+(['--require-manifold-pass'] if strict else [])
        if record: args += ['--check-record', 'synthetic-assessment.json']
        with contextlib.redirect_stdout(output): code = semantics.main(args)
        return code, json.loads(output.getvalue())

    def test_default_zero_and_strict_one_keep_same_scientific_review(self):
        with self.protocol():
            default_code, default = self.cli()
            strict_code, strict = self.cli(True)
        self.assertEqual((default_code, strict_code), (0, 1))
        self.assertEqual((default['exit_code'], strict['exit_code']), (0, 1))
        for value in (default, strict):
            self.assertEqual(value['semantic_validation_status'], 'PASS')
            self.assertEqual(value['historical_replay_status'], 'PASS')
            self.assertEqual(value['historical_process']['exit_code'], 0)
            self.assertEqual(value['manifold_assignment_status'], 'MANIFOLD_ASSIGNMENT_REVIEW_REQUIRED')
            self.assertNotIn('overall_scientific_PASS', value)
        self.assertEqual({k:v for k,v in default.items() if k not in ('exit_code', 'mode')},
                         {k:v for k,v in strict.items() if k not in ('exit_code', 'mode')})

    def test_strict_zero_only_for_all_measured_synthetic_prerequisites(self):
        with self.protocol(low=()): code, result = self.cli(True)
        self.assertEqual(code, 0)
        self.assertEqual(result['manifold_prerequisites_status'], 'PASS')
        self.assertEqual(result['physical_manifold_interpretation'], 'REVIEW_REQUIRED')

    def test_authentication_and_success_protocol_errors_are_distinct_exit_two(self):
        with patch.object(semantics, 'authenticate', side_effect=ValueError('synthetic byte mismatch')):
            code, result = self.cli()
        self.assertEqual((code, result['exit_code']), (2, 2))
        self.assertEqual(result['semantic_validation_status'], 'FAIL')
        for stdout in ('not JSON', '{"offline_status":"FAIL"}'):
            with self.protocol(process=SimpleNamespace(returncode=0, stdout=stdout, stderr='')):
                code, result = self.cli()
            self.assertEqual(code, 2); self.assertEqual(result['semantic_validation_status'], 'FAIL')

    def test_original_checker_failure_exit_and_streams_are_never_hidden(self):
        for raw_code in (7, -15):
            process = SimpleNamespace(returncode=raw_code, stdout='synthetic old failure\n', stderr='synthetic reason\n')
            with self.protocol(process=process), patch.object(semantics, 'evaluate') as evaluate:
                code, result = self.cli(True)
            self.assertEqual(code, 2)
            self.assertEqual(result['historical_process'], {'exit_code': raw_code, 'stdout': process.stdout, 'stderr': process.stderr})
            self.assertEqual(result['historical_replay_status'], 'FAIL')
            evaluate.assert_not_called()

    def test_parent_mu_run_id_and_density_must_match_saved_spectrum(self):
        for name, key in (('D-SCF.json', 'mu_ha'), ('D-SCF.json', 'run_id'),
                          ('qe-result.json', 'fermi_energy_ha'), ('qe-result.json', 'density_source_sha256')):
            with self.protocol() as docs:
                target = docs[name]['final'] if key == 'mu_ha' else docs[name]
                target[key] = target[key]+.01 if key.endswith('_ha') else 'wrong-parent'
                code, result = self.cli()
            with self.subTest(parent=name, key=key):
                self.assertEqual(code, 2)
                self.assertIn('provenance mismatch', result['reason'])

    def test_record_roundtrip_rejects_threshold_type_count_and_numeric_changes(self):
        with self.protocol() as docs:
            code, result = self.cli()
            self.assertEqual(code, 0)
            core = {k:v for k,v in result.items() if k not in ('mode', 'exit_code')}
            docs['synthetic-assessment.json'] = {'assessment': copy.deepcopy(core)}
            code, replayed = self.cli(record=True)
            self.assertEqual(code, 0); self.assertEqual(replayed, result)
            for defect in ('threshold', 'type', 'count', 'numeric'):
                changed = copy.deepcopy(core)
                if defect == 'threshold':
                    changed['occupation_rule']['minimum_inclusive'] = math.nextafter(.99999999, -math.inf)
                if defect == 'type': changed['semantics_version'] = 2.
                if defect == 'count': changed['occupation_rule']['indices_one_based'][0] = 4
                if defect == 'numeric': changed['key_numbers']['D_delta_so_ev'] += .01
                docs['synthetic-assessment.json'] = {'assessment': changed}
                code, rejected = self.cli(record=True)
                with self.subTest(defect=defect):
                    self.assertEqual(code, 2)
                    self.assertEqual(rejected['semantic_validation_status'], 'FAIL')


class SourceByteTests(unittest.TestCase):
    def authenticate_fixture(self, *, historical, mutate=None, head=None, branch='HEAD', dirty=b''):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            originals = {'README.md': b'Synthetic original navigation\n', 'science.json': b'{"synthetic":true,"energy":1.25}\n'}
            entries = []
            for name, raw in originals.items():
                (root/name).write_bytes(raw)
                blob = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
                entries.append(b'100644 blob '+blob.encode()+b'\t'+name.encode()+b'\0')
            if mutate is not None: (root/mutate).write_text('synthetic changed bytes\n')
            def git(_root, *args):
                if args == ('rev-parse', 'HEAD'): return ((head or semantics.BASE)+'\n').encode()
                if args == ('rev-parse', '--abbrev-ref', 'HEAD'): return (branch+'\n').encode()
                if args[0] == 'status': return dirty
                if args == ('ls-tree', '-rz', semantics.BASE): return b''.join(entries)
                raise AssertionError('Unexpected synthetic Git request')
            with patch.object(semantics, 'git', side_effect=git), \
                 patch.object(semantics, 'public_files', return_value=list(originals)), \
                 patch.object(semantics, 'check_paths', return_value=0):
                return semantics.authenticate(root, historical=historical)

    def test_only_current_navigation_may_change_not_science_or_old_docs(self):
        self.assertEqual(self.authenticate_fixture(historical=True), 2)
        self.assertEqual(self.authenticate_fixture(historical=False, mutate='README.md'), 2)
        for historical, name in ((True, 'README.md'), (True, 'science.json'), (False, 'science.json')):
            with self.subTest(historical=historical, name=name), self.assertRaisesRegex(ValueError, 'Frozen byte mismatch'):
                self.authenticate_fixture(historical=historical, mutate=name)

    def test_historical_snapshot_requires_exact_detached_clean_public_state(self):
        for options in ({'head': '0'*40}, {'branch': 'main'}, {'dirty': b'?? unexpected.json\n'}, {'dirty': b'!! .work/\n'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.authenticate_fixture(historical=True, **options)


if __name__ == '__main__':
    unittest.main()
