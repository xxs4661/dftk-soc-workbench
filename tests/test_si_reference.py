"""Synthetic analytic radial arrays; these are not physical pseudopotential files."""
import contextlib
import copy
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import inspect_si_reference as reference


class SiReferenceTests(unittest.TestCase):
    def test_nonuniform_quadratic_exact_even_and_odd_intervals(self):
        for grid in ([0, .13, .71, 1.4, 3], [0, .13, .71, 1.4, 2, 3]):
            values = [2+3*x-4*x*x for x in grid]
            expected = 2*3+3*3**2/2-4*3**3/3
            self.assertAlmostEqual(reference.quadratic_integral(grid, values), expected, places=12)

    def test_two_samples_use_exact_linear_integral(self):
        self.assertEqual(reference.quadratic_integral([1, 3], [5, 9]), 14)
        self.assertEqual(reference.trapezoid([1, 3], [5, 9]), 14)

    def test_analytic_constant_potential_checks_ry_to_ha_and_coulomb_sign(self):
        grid = [0, .1, .8, 1.7, 2.6, 3]
        # V_Ry=-2 -> V_Ha=-1. Integral of -r^2+4r from 0 to 3 is 9.
        result = reference.reference_from_arrays(grid, [-2]*len(grid), 4, 2, 27)
        self.assertAlmostEqual(result['alpha_ha_bohr3'], 4*math.pi*9, places=11)
        self.assertAlmostEqual(result['C_ha'], 8*math.pi/3, places=12)

    def test_negative_reference_is_not_changed_to_an_absolute_value(self):
        grid = [0, .3, 1.1, 2, 3]
        # V_Ha=-3 gives integral -9 on this range, testing the retained sign.
        result = reference.reference_from_arrays(grid, [-6]*len(grid), 4, 2, 27)
        self.assertAlmostEqual(result['alpha_ha_bohr3'], -4*math.pi*9, places=11)
        self.assertLess(result['C_ha'], 0)

    def test_atom_count_and_inverse_volume_scaling(self):
        grid, potential = [0, .2, 1, 2], [-2]*4
        one = reference.reference_from_arrays(grid, potential, 4, 1, 10)
        two = reference.reference_from_arrays(grid, potential, 4, 2, 10)
        larger = reference.reference_from_arrays(grid, potential, 4, 2, 20)
        self.assertEqual(two['C_ha'], 2*one['C_ha'])
        self.assertEqual(larger['C_ha'], one['C_ha'])
        self.assertEqual(one['alpha_ha_bohr3'], larger['alpha_ha_bohr3'])

    def test_second_method_reveals_quadrature_sensitivity(self):
        grid = [0, .15, .7, 1.2, 2]
        result = reference.reference_from_arrays(grid, [-2]*len(grid), 4, 2, 10)
        self.assertNotEqual(result['quadrature']['quadratic_minus_trapezoid_C_ha'], 0)
        self.assertEqual(len(result['quadrature']['coarsening_checks']), 3)
        self.assertIn('not strict error bounds', result['quadrature']['interpretation'])

    def test_inputs_are_not_mutated_and_origin_has_no_division_by_zero(self):
        grid, potential = [0, .3, 1, 2], [-2]*4
        before = copy.deepcopy((grid, potential))
        result = reference.reference_from_arrays(grid, potential, 4, 2, 10)
        self.assertEqual((grid, potential), before)
        self.assertTrue(math.isfinite(result['C_ha']))
        self.assertFalse(result['scf_total_energy_modified'])

    def test_missing_origin_nonfinite_or_invalid_grid_is_rejected(self):
        for grid, values in [([.1, 1], [-1, -1]), ([0, 0], [-1, -1]),
                             ([0, -1], [-1, -1]), ([0, 1], [float('nan'), -1]),
                             ([0, float('inf')], [-1, -1]), ([0, 1, 2], [-1, -1])]:
            with self.assertRaises(ValueError):
                reference.reference_from_arrays(grid, values, 4, 2, 10)

    def test_invalid_atom_count_and_volume_are_rejected(self):
        for count, volume in [(0, 10), (1.5, 10), (True, 10), (2, 0), (2, -1), (2, float('nan'))]:
            with self.assertRaises(ValueError):
                reference.reference_from_arrays([0, 1], [-1, -1], 4, count, volume)

    def test_nonsymmetric_cell_volume(self):
        self.assertEqual(reference.cell_volume([[2, 1, 0], [0, 3, 1], [1, 0, 4]]), 25)

    def test_bad_checksum_is_rejected_before_any_pseudopotential_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            data = temp/'synthetic-checksum-only.txt'
            data.write_text('Not UPF or a physical potential; checksum rejection only')
            case = temp/'case.json'
            case.write_text(json.dumps({'pseudo': {'sha256': '0'*64}}))
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                reference.inspect_file(data, case)

    def test_missing_input_cli_fails_without_replacing_previous_output(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            output = temp/'reference.json'
            output.write_text('{"reference_inspection_status":"historical fixture"}\n')
            before = output.read_bytes()
            with contextlib.redirect_stderr(io.StringIO()):
                code = reference.main(['--case', str(temp/'missing-case.json'), '--output', str(output)])
            self.assertNotEqual(code, 0)
            self.assertEqual(output.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
