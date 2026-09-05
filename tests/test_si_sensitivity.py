"""Synthetic spectra/protocol tests only; these do not execute or simulate SCF."""
import copy
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from analyze_si_sensitivity import (B0_RUN_ID, check_historical_hashes, check_independent_reference,
                                    check_matrix_case, common_points, read_run,
                                    reference_diagnostic, save_analysis, setting_change)
from run_scalar_baseline import sha256
from compare_scalar_baseline import compare, HARTREE_EV
from test_scalar_baseline import case_fixture, result_fixture


def matrix_case(label):
    return json.loads((ROOT / 'benchmarks/si-sr-lda/phase4c' / (label + '.json')).read_text())


def synthetic_result(case, engine):
    data = result_fixture(case, engine)
    data['ecut_ha'] = case['cutoffs']['dftk_ecut_ha']
    data['ecutrho_ha'] = case['cutoffs']['qe_ecutrho_ry'] / 2
    for point in data['kpoints']:
        spatial = point['weight_spatial']
        point['weight_raw'] = spatial * (2 if engine == 'QE' else 1)
        # Artificial gapped spectrum depending on coordinates, not output order.
        point['eigenvalues_ha'] = [-1 + .1 * band + .01 * sum(point['coordinate_fractional'])
                                    + (.5 if band >= 4 else 0) for band in range(8)]
    return data


class SiSensitivityTests(unittest.TestCase):
    def test_saved_csv_preserves_full_diagnostic_rows_and_totals(self):
        case = case_fixture()
        d, q = (synthetic_result(case, code) for code in ('DFTK', 'QE'))
        pair = reference_diagnostic(compare(case, d, q), .25)
        result = {'paired_comparisons': {'B0': pair}, 'within_code_changes': {}}
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / 'new-analysis'
            save_analysis(directory, result)
            summary = json.loads((directory / 'sensitivity.json').read_text())
            self.assertEqual(summary['paired_comparisons']['B0']['total_energy'], pair['total_energy'])
            self.assertEqual(summary['paired_comparisons']['B0']['eigenvalues_file'], 'B0.csv')
            with (directory / 'B0.csv').open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 64)
            for actual, expected in zip(rows, pair['eigenvalues']):
                for key in ('delta_ha', 'global_reference_delta_ha', 'independent_C_residual_ha'):
                    self.assertEqual(float(actual[key]), expected[key])
            self.assertEqual(len(pair['eigenvalues']), 64)

    def test_independent_reference_requires_success_and_independence(self):
        path = ROOT / 'benchmarks/si-sr-lda/case.json'
        reference = {'schema_version': 1, 'reference_inspection_status': 'PASS',
                     'spectral_data_used': False, 'dftk_correction_called': False,
                     'scf_total_energy_modified': False, 'case_sha256': sha256(path)}
        check_independent_reference(reference, path)
        for key, value in [('schema_version', 999), ('reference_inspection_status', 'FAIL'),
                           ('spectral_data_used', True), ('dftk_correction_called', True),
                           ('scf_total_energy_modified', True), ('case_sha256', '0' * 64)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                check_independent_reference(dict(reference, **{key: value}), path)

    def test_historical_name_alone_cannot_replace_accepted_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            file = root / 'result.json'; file.write_text('synthetic historical byte anchor')
            manifest = {'files': [{'file': 'result.json', 'raw_sha256': sha256(file),
                                  'raw_path': '<workbench>/.work/scalar-baseline/' + B0_RUN_ID + '/result.json'}]}
            check_historical_hashes(root, manifest)
            file.write_text('synthetic replacement with the same historical name')
            with self.assertRaisesRegex(ValueError, 'historical raw hash mismatch'):
                check_historical_hashes(root, manifest)

    def test_independent_constant_sign_and_energy_immutability(self):
        case = case_fixture()
        d, q = (synthetic_result(case, code) for code in ('DFTK', 'QE'))
        for point in d['kpoints']:
            point['eigenvalues_ha'] = [e - .25 for e in point['eigenvalues_ha']]
        d['energy_ha'] = d['energy_raw']['value'] = -9
        original = compare(case, d, q)
        snapshot = copy.deepcopy(original)
        diagnostic = reference_diagnostic(original, .25)
        self.assertEqual(original, snapshot)
        self.assertEqual(diagnostic['total_energy'], snapshot['total_energy'])
        self.assertEqual(diagnostic['total_energy']['delta_DFTK_minus_QE']['ha_cell'], 1)
        self.assertLess(diagnostic['independent_reference']['summary']['all']['max_abs_ha'], 1e-15)
        self.assertEqual(diagnostic['independent_reference']['predicted_delta_DFTK_minus_QE_ha'], -.25)
        self.assertFalse(diagnostic['independent_reference']['qe_internal_G0_value_directly_extracted'])

    def test_wrong_prediction_is_not_refitted_to_the_spectrum(self):
        case = case_fixture()
        d, q = (synthetic_result(case, code) for code in ('DFTK', 'QE'))
        for point in d['kpoints']:
            point['eigenvalues_ha'] = [e - .25 for e in point['eigenvalues_ha']]
        data = reference_diagnostic(compare(case, d, q), .10)
        for row in data['eigenvalues']:
            self.assertAlmostEqual(row['independent_C_residual_ha'], -.15)
            self.assertAlmostEqual(row['delta_ha'], -.25)
        self.assertAlmostEqual(data['independent_reference']['summary']['occupied']['rms_ha'], .15)
        self.assertAlmostEqual(data['independent_reference']['summary']['empty']['max_abs_ev'], .15 * HARTREE_EV)

    def test_nonfinite_prediction_is_rejected(self):
        for invalid in (float('nan'), float('inf'), True, None):
            with self.assertRaises(ValueError):
                reference_diagnostic({}, invalid)

    def test_eight_points_are_coordinate_subset_of_sixty_four(self):
        requested = case_fixture()['kpoints']
        actual = list(reversed(copy.deepcopy(matrix_case('C3')['kpoints'])))
        for point in actual:
            point['coordinate_fractional'] = [x + 2 for x in point['coordinate_fractional']]
        selected = common_points(requested, actual)
        self.assertEqual(len(selected), 8)
        for source, point in zip(requested, selected):
            self.assertEqual([x + 2 for x in source['coordinate_fractional']], point['coordinate_fractional'])

    def test_missing_duplicate_common_and_extra_grid_points_are_rejected(self):
        points = matrix_case('C3')['kpoints']
        for bad in (points[1:], points + [points[0]], points + [points[1]]):
            with self.assertRaises(ValueError):
                common_points(case_fixture()['kpoints'], bad)
        with self.assertRaises(ValueError):
            common_points([case_fixture()['kpoints'][0]] * 2, points)

    def test_cross_grid_uses_one_gamma_reference_even_when_global_homo_moves(self):
        old_case, new_case = matrix_case('C2'), matrix_case('C3')
        before, after = synthetic_result(old_case, 'DFTK'), synthetic_result(new_case, 'DFTK')
        for point in after['kpoints']:
            perturbation = .001 * sum(point['coordinate_fractional'])
            point['eigenvalues_ha'] = [e + .2 + perturbation for e in point['eigenvalues_ha']]
        # Move the sampled global HOMO to an added point; it must NOT set the reference.
        added = next(p for p in after['kpoints'] if p['coordinate_fractional'] == [.25, .25, .25])
        added['eigenvalues_ha'] = [e + .1 for e in added['eigenvalues_ha']]
        after['kpoints'].reverse()
        after['energy_ha'] = after['energy_raw']['value'] = -10.01
        result = setting_change(old_case, before, new_case, after, 'DFTK')
        self.assertEqual(result['common_kpoint_count'], 8)
        self.assertEqual(result['reference_location_fractional'], [0, 0, 0])
        self.assertAlmostEqual(result['reference_delta_ha'], .2)
        self.assertEqual(len(result['eigenvalues']), 64)
        for row in result['eigenvalues']:
            self.assertAlmostEqual(row['raw_delta_ha'], .2 + .001 * sum(row['k_fractional']))
            self.assertAlmostEqual(row['gamma_reference_delta_ha'], .001 * sum(row['k_fractional']))
        self.assertAlmostEqual(result['total_energy']['delta_ha_cell'], -.01)
        self.assertAlmostEqual(result['total_energy']['delta_mev_atom'], -.01 * HARTREE_EV * 500)

    def test_cutoff_changes_retain_energies_and_separate_occupied_empty(self):
        old_case, new_case = case_fixture(), matrix_case('C1')
        before, after = synthetic_result(old_case, 'QE'), synthetic_result(new_case, 'QE')
        for point in after['kpoints']:
            point['eigenvalues_ha'] = [e + (.001 if i < 4 else .003)
                                      for i, e in enumerate(point['eigenvalues_ha'])]
        result = setting_change(old_case, before, new_case, after, 'QE')
        self.assertAlmostEqual(result['reference_delta_ha'], .001)
        self.assertLess(result['gamma_reference_summary']['occupied']['max_abs_ha'], 1e-15)
        self.assertAlmostEqual(result['gamma_reference_summary']['empty']['rms_ha'], .002)
        self.assertEqual(result['total_energy']['delta_ha_cell'], 0)

    def test_matrix_does_not_admit_additional_physical_changes(self):
        for label in ('C1', 'C2', 'C3'):
            check_matrix_case(matrix_case(label), case_fixture(), label)
        for field in ('geometry', 'xc', 'pseudo', 'electrons', 'scf', 'runtime'):
            with self.subTest(field=field):
                bad = matrix_case('C3'); bad[field] = {}
                with self.assertRaises(ValueError):
                    check_matrix_case(bad, case_fixture(), 'C3')
        bad = matrix_case('C2'); bad['cutoffs']['dftk_ecut_ha'] = 60
        with self.assertRaises(ValueError):
            check_matrix_case(bad, case_fixture(), 'C2')

    def test_analysis_rejects_current_failure_without_reading_old_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = root / 'old'; old.mkdir()
            (old / 'result.json').write_text('{"execution_status":"PASS"}')
            current = root / 'current'; current.mkdir()
            (current / 'result.json').write_text(json.dumps({'execution_status': 'FAIL',
                'input_comparability_status': 'FAIL', 'exit_code': 1, 'run_id': 'current'}))
            with self.assertRaisesRegex(ValueError, 'current run is not successful'):
                read_run(current, 'C3')
            self.assertEqual((old / 'result.json').read_text(), '{"execution_status":"PASS"}')


if __name__ == '__main__':
    unittest.main()
