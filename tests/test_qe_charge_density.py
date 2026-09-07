"""Independent synthetic binary writer and analytic periodic-density fixtures.

No historical charge file, QE program, pseudopotential or Julia is used. The
writer uses byte concatenation, not the production parser's record functions.
"""
import cmath
import hashlib
import itertools
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from parse_qe_charge_density import (parse_qe_charge_density, parse_charge_density_bytes,
                                      ChargeDensityParseError, _select_unique)

M = (1, -2, 3)
P = (2, 1, -1)
MILLER = [(0, 0, 0), M, tuple(-v for v in M), P, tuple(-v for v in P)]
CM = .001*cmath.exp(.37j)
CP = -.0005j*cmath.exp(-.21j)
COEFFICIENTS = [.01+0j, CM, CM.conjugate(), CP, CP.conjugate()]
B_COLUMNS = [[.5, .1, -.2], [.4, .75, .05], [-.1, .2, .9]]


def synthetic_records(*, byteorder='little', marker_bytes=4, integer_bytes=4,
                      logical_bytes=4, miller=MILLER, values=COEFFICIENTS,
                      gamma=0, nspin=1, ngm=None, columns=B_COLUMNS):
    """Build documented record CONTENTS independently of the production reader."""
    integer = lambda value, size: int(value).to_bytes(size, byteorder, signed=True)
    real = lambda value: struct.pack('<d' if byteorder == 'little' else '>d', value)
    count = len(miller) if ngm is None else ngm
    header = integer(gamma, logical_bytes) + integer(count, integer_bytes) + integer(nspin, integer_bytes)
    reciprocal = b''.join(real(value) for column in columns for value in column)
    indices = b''.join(integer(value, integer_bytes) for point in miller for value in point)
    density = b''.join(real(value.real)+real(value.imag) for value in values)
    return [header, reciprocal, indices] + [density]*max(0, nspin)


def envelope(records, *, byteorder='little', marker_bytes=4):
    output = bytearray()
    for record in records:
        marker = len(record).to_bytes(marker_bytes, byteorder, signed=True)
        output.extend(marker); output.extend(record); output.extend(marker)
    return bytes(output)


def synthetic_bytes(**options):
    return envelope(synthetic_records(**options),
                    **{key:value for key,value in options.items() if key in ('byteorder','marker_bytes')})


def direct_reference(point):
    """Direct sum of an analytic positive, nonaxial, phase-bearing density."""
    terms = []
    for i, j, k in itertools.product(range(8), range(9), range(10)):
        s = (i/8, j/9, k/10)
        dot = lambda m: sum(a*b for a,b in zip(m,s))
        rho = .01 + .002*math.cos(2*math.pi*dot(M)+.37) + .001*math.sin(2*math.pi*dot(P)-.21)
        assert rho > 0
        terms.append(rho*cmath.exp(-2j*math.pi*dot(point)))
    return complex(math.fsum(z.real for z in terms), math.fsum(z.imag for z in terms))/720


class QeChargeDensityTests(unittest.TestCase):
    def test_all_sixteen_encoding_candidates_are_identified_uniquely(self):
        for byteorder, marker, integer, logical in itertools.product(('little','big'), (4,8), (4,8), (4,8)):
            with self.subTest(byteorder=byteorder, marker=marker, integer=integer, logical=logical):
                raw = synthetic_bytes(byteorder=byteorder, marker_bytes=marker, integer_bytes=integer, logical_bytes=logical)
                parsed = parse_charge_density_bytes(raw, expected_ngm=5)
                self.assertEqual(parsed['candidate_count'], 1)
                self.assertEqual(parsed['encoding'], {'endian':byteorder, 'record_marker_bytes':marker,
                    'integer_bytes':integer, 'logical_bytes':logical, 'real_bytes':8, 'complex_bytes':16})
                self.assertEqual(parsed['miller'], MILLER)
                self.assertEqual(parsed['rho_g'], COEFFICIENTS)
                self.assertEqual(parsed['b_columns_bohr_inv'], B_COLUMNS)

    def test_file_bytes_and_hash_preserved_without_provenance_invention(self):
        raw = synthetic_bytes()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'synthetic-charge.dat'; path.write_bytes(raw)
            parsed = parse_qe_charge_density(path)
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(parsed['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(parsed['size_bytes'], len(raw))
            self.assertEqual(parsed['source_binding_status'], 'REQUIRES_HISTORICAL_RECEIPT')

    def test_explicit_columns_fortran_miller_and_real_imag_order(self):
        parsed = parse_charge_density_bytes(synthetic_bytes())
        self.assertNotEqual(B_COLUMNS, [list(row) for row in zip(*B_COLUMNS)])
        self.assertEqual(parsed['b_columns_bohr_inv'][1], [.4,.75,.05])
        self.assertEqual(parsed['miller'][1], (1,-2,3))
        self.assertEqual(parsed['rho_g'][3].imag, CP.imag)
        self.assertEqual(parsed['rho_g'][3].real, CP.real)

    def test_analytic_nonaxial_phase_reference_and_no_normalization(self):
        parsed = parse_charge_density_bytes(synthetic_bytes())
        for point, coefficient in zip(parsed['miller'], parsed['rho_g']):
            with self.subTest(point=point):
                self.assertLessEqual(abs(coefficient-direct_reference(point)), 1e-16)
        self.assertEqual(parsed['rho_g'][0], .01+0j)
        self.assertAlmostEqual(1000*parsed['rho_g'][0].real, 10)

    def test_joint_permutation_retains_exact_mode_value_map(self):
        order = [3,0,4,2,1]
        parsed = parse_charge_density_bytes(synthetic_bytes(miller=[MILLER[i] for i in order], values=[COEFFICIENTS[i] for i in order]))
        self.assertEqual(dict(zip(parsed['miller'], parsed['rho_g'])), dict(zip(MILLER, COEFFICIENTS)))
        self.assertEqual(parsed['g_zero_index'], 1)

    def test_one_sided_permutation_detected_by_independent_phase_reference(self):
        # A structurally valid permutation is not detectable from lengths alone.
        order = [0,3,4,1,2]
        for raw in (synthetic_bytes(miller=[MILLER[i] for i in order]),
                    synthetic_bytes(values=[COEFFICIENTS[i] for i in order])):
            parsed = parse_charge_density_bytes(raw)
            errors = [abs(z-direct_reference(m)) for m,z in zip(parsed['miller'], parsed['rho_g'])]
            self.assertGreater(max(errors), 1e-4)

    def test_each_truncated_boundary_and_final_byte_fails(self):
        raw = synthetic_bytes()
        for stop in (0,1,3,4,8,15,19,20,24,95,len(raw)-5,len(raw)-1):
            with self.subTest(stop=stop), self.assertRaises(ChargeDensityParseError):
                parse_charge_density_bytes(raw[:stop])

    def test_mismatched_markers_and_negative_subrecords_fail(self):
        for offset, value in ((0,13),(16,13),(0,-12)):
            raw = bytearray(synthetic_bytes()); raw[offset:offset+4] = value.to_bytes(4,'little',signed=True)
            with self.subTest(offset=offset,value=value), self.assertRaises(ChargeDensityParseError):
                parse_charge_density_bytes(bytes(raw))

    def test_trailing_bytes_and_extra_records_fail(self):
        for tail in (b'\x00', b'garbage', envelope([b'new record'])):
            with self.subTest(tail=tail), self.assertRaises(ChargeDensityParseError):
                parse_charge_density_bytes(synthetic_bytes()+tail)

    def test_wrong_ngm_and_external_expected_ngm_fail(self):
        for count in (0,-1,4,6,1_000_001):
            with self.subTest(count=count), self.assertRaises(ChargeDensityParseError):
                parse_charge_density_bytes(synthetic_bytes(ngm=count))
        with self.assertRaisesRegex(ChargeDensityParseError, 'independently expected'):
            parse_charge_density_bytes(synthetic_bytes(), expected_ngm=2777)

    def test_invalid_nspin_or_component_record_count_fail(self):
        for count in (0,-1,5):
            with self.subTest(count=count), self.assertRaises(ChargeDensityParseError):
                parse_charge_density_bytes(synthetic_bytes(nspin=count))
        records = synthetic_records(nspin=2); records.pop()
        with self.assertRaises(ChargeDensityParseError): parse_charge_density_bytes(envelope(records))

    def test_multiple_saved_components_are_explicitly_unsupported(self):
        for count in (2,3,4):
            with self.subTest(count=count), self.assertRaises(ChargeDensityParseError) as error:
                parse_charge_density_bytes(synthetic_bytes(nspin=count))
            self.assertEqual(error.exception.status, 'UNSUPPORTED')

    def test_half_g_is_rejected_not_completed_or_doubled(self):
        for gamma in (1,-1):
            with self.subTest(gamma=gamma), self.assertRaisesRegex(ChargeDensityParseError, 'gamma_only=false') as error:
                parse_charge_density_bytes(synthetic_bytes(gamma=gamma))
            self.assertEqual(error.exception.status, 'UNSUPPORTED')

    def test_unknown_logical_encoding_not_assumed_false(self):
        with self.assertRaises(ChargeDensityParseError): parse_charge_density_bytes(synthetic_bytes(gamma=2))

    def test_hdf5_signature_explicitly_unsupported(self):
        with self.assertRaisesRegex(ChargeDensityParseError, 'HDF5') as error:
            parse_charge_density_bytes(b'\x89HDF\r\n\x1a\n'+b'fixture')
        self.assertEqual(error.exception.status, 'UNSUPPORTED')

    def test_nonfinite_real_or_imaginary_coefficients_fail(self):
        for number in (complex(math.nan,0), complex(0,math.nan), complex(math.inf,0), complex(0,-math.inf)):
            values = list(COEFFICIENTS); values[2] = number
            with self.subTest(number=number), self.assertRaises(ChargeDensityParseError):
                parse_charge_density_bytes(synthetic_bytes(values=values))

    def test_nonfinite_or_singular_reciprocal_columns_fail(self):
        for columns in ([[math.nan,0,0],[0,1,0],[0,0,1]], [[1,0,0],[2,0,0],[0,0,1]]):
            with self.subTest(columns=columns), self.assertRaises(ChargeDensityParseError):
                parse_charge_density_bytes(synthetic_bytes(columns=columns))

    def test_duplicate_g_and_duplicate_or_missing_zero_fail(self):
        for indices in ([MILLER[0]]*2+MILLER[2:], MILLER[:2]+[MILLER[1]]+MILLER[3:], [(4,3,2)]+MILLER[1:]):
            with self.subTest(indices=indices), self.assertRaises(ChargeDensityParseError):
                parse_charge_density_bytes(synthetic_bytes(miller=indices))

    def test_zero_valued_mode_is_preserved_as_present(self):
        values = list(COEFFICIENTS); values[3] = 0j
        parsed = parse_charge_density_bytes(synthetic_bytes(values=values))
        self.assertIn(P, parsed['miller'])
        self.assertEqual(dict(zip(parsed['miller'], parsed['rho_g']))[P], 0j)
        self.assertEqual(parsed['ngm'], 5)

    def test_payload_sizes_for_lattice_miller_and_complex_fail(self):
        for index in (1,2,3):
            records = synthetic_records(); records[index] = records[index][:-1]
            with self.subTest(index=index), self.assertRaises(ChargeDensityParseError):
                parse_charge_density_bytes(envelope(records))

    def test_ambiguous_candidate_selection_rejects_without_physics_tiebreaker(self):
        # Synthetic candidate-selection unit test, not a claim that these two
        # dictionaries came from an actual ambiguous QE file.
        with self.assertRaisesRegex(ChargeDensityParseError, 'multiple fully validated') as error:
            _select_unique([{'encoding':'candidate one'}, {'encoding':'candidate two'}])
        self.assertEqual(error.exception.status, 'UNSUPPORTED')

    def test_size_ceiling_and_input_type_are_explicit(self):
        with self.assertRaises(ChargeDensityParseError): parse_charge_density_bytes(bytearray(synthetic_bytes()))
        with self.assertRaises(ChargeDensityParseError): parse_charge_density_bytes(synthetic_bytes(), max_ngm=4)
        for size in (0,-1,True,1_000_001):
            with self.subTest(size=size), self.assertRaises(ChargeDensityParseError):
                parse_charge_density_bytes(synthetic_bytes(), max_ngm=size)

    def test_missing_source_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ChargeDensityParseError) as error:
                parse_qe_charge_density(Path(directory)/'missing.dat')
            self.assertEqual(error.exception.status, 'BLOCKED')


if __name__ == '__main__':
    unittest.main()
