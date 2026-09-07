"""Synthetic format/registration fixtures only; no physical QE calculation."""
import cmath
from decimal import Decimal
import gzip
import hashlib
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from parse_qe_filplot import FilplotParseError, decimal_token, parse_qe_filplot


# Independent fixture writer: explicit coordinates and its own padded table.
# It does not import parser layout, scale, or rounding helpers.
GRID = [4, 3, 5]
ALLOCATED = [6, 4, 7]
ALAT = 7.0
AT_COLUMNS = [[1.0, .2, .1], [.3, 1.1, .2], [.1, .4, 1.2]]
TAU = [.173, .237, .319]


def field(i, j, k):
    x, y, z = i/4, j/3, k/5
    return .37 + .12*math.cos(2*math.pi*(x+y)+.31) + .08*math.sin(2*math.pi*(y-z)+.47)


def fixture(plot=2, *, blank_title=False):
    lines = ['' if blank_title else 'SYNTHETIC FORMAT FIXTURE; NOT A PHYSICAL PSEUDOPOTENTIAL']
    lines.append(''.join('%8d' % n for n in ALLOCATED+GRID+[1, 1]))
    lines.append('%6d  ' % 0 + ''.join('%16.8f' % n for n in [ALAT, 0, 0, 0, 0, 0]))
    lines.extend(' '.join('%.16E' % v for v in col) for col in AT_COLUMNS)
    lines.append(''.join('%20.10f' % n for n in [148.9459799554, 4, 30])+'%6d' % plot)
    lines.append('%4d   %2s   %5.2f' % (1, 'Mg', 10))
    lines.append('%4d   ' % 1 + ''.join('%15.9f' % n for n in TAU)+'   %2d' % 1)
    # The retained planes stop at physical nz=5, while nr3x=7 is metadata.
    table = [[[999+i+10*j+100*k for i in range(6)] for j in range(4)] for k in range(5)]
    for k in range(5):
        for j in range(3):
            for i in range(4):
                table[k][j][i] = field(i, j, k)
    native = [v for plane in table for row in plane for v in row]
    for start in range(0, len(native), 5):
        lines.append(''.join('%17.9E' % v for v in native[start:start+5]))
    return '\n'.join(lines)+'\n'


def expectations(plot=2):
    return {'grid': GRID, 'lattice_columns_bohr': [[ALAT*v for v in col] for col in AT_COLUMNS],
            'positions_cartesian_bohr': [[ALAT*v for v in TAU]],
            'species': [{'symbol': 'Mg', 'z_valence': 10}], 'atom_species_indices': [1],
            'cutoffs': {'gcutm': 148.9459799554, 'dual': 4, 'ecut_ry': 30},
            'unit': 'Ha' if plot == 2 else 'electron/bohr^3'}


class FilplotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'synthetic.pp'

    def tearDown(self):
        self.temp.cleanup()

    def read(self, text=None, plot=2, expected=True):
        self.path.write_text(fixture(plot) if text is None else text, encoding='ascii')
        return parse_qe_filplot(self.path, expected_plot_num=plot,
                               expected=expectations(plot) if expected else None)

    def reject(self, text, message=None, plot=2):
        with self.assertRaisesRegex(FilplotParseError, message or '.'):
            self.read(text, plot)

    def test_noncubic_padding_first_axis_fastest_and_nr3_not_nr3x(self):
        parsed = self.read()
        self.assertEqual(parsed['payload_count'], 6*4*5)
        self.assertEqual(parsed['physical_count'], 4*3*5)
        self.assertEqual(parsed['padding_count_excluded'], 60)
        self.assertEqual(parsed['allocated_grid'], [6, 4, 7])
        expected = [field(i, j, k)/2 for k in range(5) for j in range(3) for i in range(4)]
        for actual, want, width in zip(parsed['values'], expected, parsed['halfwidths']):
            self.assertLessEqual(abs(actual-want), width+1e-16)
        self.assertAlmostEqual(sum(parsed['values'])/60, .37/2, places=11)
        self.assertLess(max(parsed['values']), 1)
        self.assertGreater(max(float(t) for t in parsed['payload_tokens']), 999)

    def test_plot2_rydberg_to_hartree_exactly_once(self):
        parsed = self.read()
        self.assertEqual(parsed['native_unit'], 'Ry')
        self.assertEqual(parsed['unit'], 'Ha')
        self.assertEqual(parsed['unit_scale'], .5)
        self.assertEqual(parsed['values'][0], float(parsed['raw_tokens'][0])/2)
        self.assertNotEqual(parsed['values'][0], float(parsed['raw_tokens'][0]))
        self.assertNotEqual(parsed['values'][0], float(parsed['raw_tokens'][0])/4)

    def test_plot0_density_no_spin_or_volume_factor(self):
        parsed = self.read(plot=0)
        self.assertEqual(parsed['unit_scale'], 1)
        self.assertEqual(parsed['unit'], 'electron/bohr^3')
        self.assertEqual(parsed['values'][0], float(parsed['raw_tokens'][0]))
        self.assertAlmostEqual(sum(parsed['values'])/60, .37, places=10)

    def test_sheared_columns_alat_tau_and_source_geometry(self):
        parsed = self.read()
        self.assertEqual(parsed['expected_validation_status'], 'PASS')
        self.assertEqual(parsed['header']['lattice_columns_bohr'], expectations()['lattice_columns_bohr'])
        bad = expectations()
        bad['lattice_columns_bohr'] = list(map(list, zip(*bad['lattice_columns_bohr'])))
        with self.assertRaisesRegex(FilplotParseError, 'print interval'):
            parse_qe_filplot(self.path, expected_plot_num=2, expected=bad)

    def test_transposed_tau_or_shifted_origin_rejected_by_geometry(self):
        self.read()
        for position in ([ALAT*TAU[1], ALAT*TAU[0], ALAT*TAU[2]],
                         [ALAT*TAU[0]+.1, ALAT*TAU[1], ALAT*TAU[2]]):
            with self.subTest(position=position):
                bad = expectations()
                bad['positions_cartesian_bohr'] = [position]
                with self.assertRaises(FilplotParseError):
                    parse_qe_filplot(self.path, expected_plot_num=2, expected=bad)

    def test_phase_nonaxial_modes_and_wrong_registration_detectable(self):
        parsed = self.read(plot=0)
        modes = [(1, 1, 0), (0, 1, -1)]
        want = [.06*cmath.exp(.31j), -.04j*cmath.exp(.47j)]
        coords = [(i/4, j/3, k/5) for k in range(5) for j in range(3) for i in range(4)]
        def coeff(values, q, coordinates=coords):
            return sum(v*cmath.exp(-2j*math.pi*sum(a*b for a, b in zip(q, x)))
                       for v, x in zip(values, coordinates))/60
        for q, target in zip(modes, want):
            self.assertLess(abs(coeff(parsed['values'], q)-target), 1e-10)
            self.assertGreater(abs(coeff(parsed['values'], tuple(-m for m in q))-target), .01)
            shifted = [(x+.125, y+.11, z) for x, y, z in coords]
            self.assertGreater(abs(coeff(parsed['values'], q, shifted)-target), .01)
        swapped = [(y, x, z) for x, y, z in coords]
        self.assertGreater(abs(coeff(parsed['values'], modes[1], swapped)-want[1]), .01)
        endpoints = [(i/3, j/2, k/4) for k in range(5) for j in range(3) for i in range(4)]
        self.assertGreater(abs(coeff(parsed['values'], modes[0], endpoints)-want[0]), .01)

    def test_token_precision_positive_negative_zero_E_D_scales(self):
        for token, value, width in [('1.2300E+02', '123.00', '.005'),
                                   ('-7.30D-03', '-.00730', '.000005'),
                                   ('0.000000000E+00', '0', '.0000000005'),
                                   ('+1.2e-8', '.000000012', '.0000000005'),
                                   ('-0.000', '0', '.0005')]:
            with self.subTest(token=token):
                self.assertEqual(decimal_token(token), (Decimal(value), Decimal(width)))
        parsed = self.read(fixture().replace('E', 'D'))
        self.assertEqual(parsed['halfwidths'][0], float(decimal_token(parsed['raw_tokens'][0])[1])/2)

    def test_original_token_hash_and_gzip_container_preserved(self):
        text = fixture()
        parsed = self.read(text)
        self.assertEqual(parsed['source_sha256'], hashlib.sha256(text.encode()).hexdigest())
        path = Path(self.temp.name)/'synthetic.pp.gz'
        path.write_bytes(gzip.compress(text.encode(), mtime=0))
        compressed = parse_qe_filplot(path, expected_plot_num=2, expected=expectations())
        self.assertEqual(compressed['source_sha256'], parsed['source_sha256'])
        self.assertEqual(compressed['payload_tokens'], parsed['payload_tokens'])
        self.assertNotEqual(compressed['stored_sha256'], compressed['source_sha256'])

    def test_blank_title_supported(self):
        self.assertEqual(self.read(fixture(blank_title=True))['header']['title'], '')

    def test_missing_title_header_or_payload_line(self):
        lines = fixture().splitlines()
        for index in (0, 1, 3, 7, 8, 9, len(lines)-1):
            with self.subTest(index=index):
                self.reject('\n'.join(lines[:index]+lines[index+1:])+'\n')

    def test_missing_extra_token_or_repeated_header(self):
        lines = fixture().splitlines()
        for replacement in (' '.join(lines[9].split()[:-1]), lines[9]+' 1.0', lines[1]):
            with self.subTest(replacement=replacement):
                modified = lines.copy()
                modified[9] = replacement
                self.reject('\n'.join(modified)+'\n')
        self.reject(fixture()+fixture())
        self.reject(fixture()+'1.0\n')

    def test_nonfinite_overflow_and_malformed_payload_rejected_even_in_padding(self):
        lines = fixture().splitlines()
        for token in ('NaN', 'Inf', '-Inf', '*****************', '1.2X+00', '1.2E999', '1,2'):
            with self.subTest(token=token):
                altered = lines.copy()
                # The fifth value is padding; it still must be parsed as finite.
                altered[9] = ' '.join(altered[9].split()[:4]+[token])
                self.reject('\n'.join(altered)+'\n')

    def test_wrong_plot_number_and_unit_expectation(self):
        self.reject(fixture(0), 'plot_num')
        self.read()
        with self.assertRaisesRegex(FilplotParseError, 'unit'):
            parse_qe_filplot(self.path, expected_plot_num=2, expected={'unit': 'Ry'})
        with self.assertRaisesRegex(FilplotParseError, 'Only requested'):
            parse_qe_filplot(self.path, expected_plot_num=1)

    def test_wrong_species_valence_and_atom_association(self):
        lines = fixture().splitlines()
        for index, value in ((7, '1 Si 10.00'), (7, '1 Mg 2.00'), (7, '2 Mg 10.00'),
                             (8, '1 .173 .237 .319 2'), (8, '2 .173 .237 .319 1')):
            with self.subTest(value=value):
                modified = lines.copy()
                modified[index] = value
                self.reject('\n'.join(modified)+'\n')

    def test_nonzero_ibrav_invalid_dimensions_and_cutoffs(self):
        lines = fixture().splitlines()
        mutations = [(2, '1 7 0 0 0 0 0'), (1, '3 4 7 4 3 5 1 1'),
                     (1, '6 4 4 4 3 5 1 1'), (1, '6 4 7 4 3 0 1 1'),
                     (1, '6 4 7 4 3 5 1 2'), (6, '148.9459799554 4 15 2')]
        for index, value in mutations:
            with self.subTest(value=value):
                changed = lines.copy()
                changed[index] = value
                self.reject('\n'.join(changed)+'\n')

    def test_requested_grid_and_geometry_types_are_not_silently_ignored(self):
        self.read()
        for expected in ({'grid': [5, 3, 4]}, {'grid': None}, {'lattice_columns_bohr': None},
                         {'positions_cartesian_bohr': [[float('nan'), 1, 2]]}, {'typo': 1},
                         {'species': None}, {'cutoffs': {}}):
            with self.subTest(expected=expected):
                with self.assertRaises(FilplotParseError):
                    parse_qe_filplot(self.path, expected_plot_num=2, expected=expected)

    def test_precision_interval_accepts_rounding_but_rejects_large_geometry_drift(self):
        self.read()
        expected = expectations()
        expected['positions_cartesian_bohr'][0][0] += 1e-9
        parse_qe_filplot(self.path, expected_plot_num=2, expected=expected)
        expected['positions_cartesian_bohr'][0][0] += 1e-6
        with self.assertRaises(FilplotParseError):
            parse_qe_filplot(self.path, expected_plot_num=2, expected=expected)


if __name__ == '__main__':
    unittest.main()
