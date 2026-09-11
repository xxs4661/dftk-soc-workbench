"""Independent synthetic WFC writer; records are not physical QE orbitals."""
import copy
import hashlib
import itertools
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from parse_qe_wavefunction import (WavefunctionParseError, parse_wfc, read_header,
                                   _unique_candidate)

B = [[.6, .03, -.02], [.08, .7, .04], [-.01, .09, .8]]
K = [.071, -.023, .109]
MILLER = [[2, 0, -1], [-1, 2, 0], [0, 1, 1], [3, -1, 0]]


def coefficient(component, g, band):
    if g == 0 and band == 0:
        return complex(1, -0.0) if component == 0 else complex(-0.0, 2)
    return complex((band+1)*.13+(g+1)*.07+component*.011,
                   -(band+1)*.019+(g+1)*.033-component*.051)


def synthetic_records(*, endian='<', integer_bytes=4, logical_bytes=4,
                      ik=2, k=K, b=B, ngw=9, miller=MILLER, npol=2, nbnd=24,
                      ispin=1, gamma=0, scalef=1.0, transform=None):
    # Deliberately written from the documented sequence, without production
    # decoder/index/size helpers. Coefficients are nonnormalized format data.
    intcode = 'i' if integer_bytes == 4 else 'q'
    logcode = 'i' if logical_bytes == 4 else 'q'
    records = [struct.pack(endian+intcode, ik)+struct.pack(endian+'3d', *k)
               +struct.pack(endian+intcode, ispin)+struct.pack(endian+logcode, gamma)
               +struct.pack(endian+'d', scalef),
               struct.pack(endian+4*intcode, ngw, len(miller), npol, nbnd),
               struct.pack(endian+'9d', *(x for column in b for x in column)),
               struct.pack(endian+intcode*3*len(miller), *(x for m in miller for x in m))]
    for band in range(nbnd):
        values = []
        for component in range(npol):
            for g in range(len(miller)):
                z = coefficient(component, g, band)
                if transform is not None:
                    z = transform(z, component, g, band)
                values.extend([z.real, z.imag])
        records.append(struct.pack(endian+'d'*len(values), *values))
    return records


def envelope(records, endian='<', marker_bytes=4):
    code = endian+('i' if marker_bytes == 4 else 'q')
    return b''.join(struct.pack(code, len(r))+r+struct.pack(code, len(r)) for r in records)


class WavefunctionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'arbitrary-name.dat'

    def tearDown(self):
        self.temp.cleanup()

    def install(self, data=None, **options):
        data = envelope(synthetic_records(**options)) if data is None else data
        self.path.write_bytes(data)
        return {'source_sha256': hashlib.sha256(data).hexdigest(), 'ik': 2,
                'k_cart_bohr_inv': list(K), 'b_columns_bohr_inv': copy.deepcopy(B),
                'npw': 4, 'nbnd': 24, 'ngw': 9}

    def reject(self, data, message=None):
        expected = self.install(data)
        with self.assertRaisesRegex(WavefunctionParseError, message or '.'):
            parse_wfc(self.path, expected)

    def test_all_supported_envelope_and_integer_logical_widths(self):
        for endian, marker, integer, logical in itertools.product(('<', '>'), (4, 8), (4, 8), (4, 8)):
            with self.subTest(endian=endian, marker=marker, integer=integer, logical=logical):
                data = envelope(synthetic_records(endian=endian, integer_bytes=integer,
                                                  logical_bytes=logical), endian, marker)
                expected = self.install(data)
                parsed = parse_wfc(self.path, expected)
                actual = parsed['metadata']['format']
                self.assertEqual(actual['endian'], 'little' if endian == '<' else 'big')
                self.assertEqual(actual['integer_bytes'], integer)
                self.assertEqual(actual['logical_bytes'], logical)
                self.assertEqual(actual['record_marker_bytes'], marker)
                self.assertEqual(parsed['shape'], [2, 4, 24])
                self.assertEqual(parsed['metadata']['candidate_count'], 1)
                self.assertEqual(parsed['miller'], MILLER)

    def test_ngw_is_max_global_index_not_selected_plane_wave_count(self):
        parsed = parse_wfc(self.path, self.install())
        self.assertEqual(parsed['metadata']['ngw'], 9)
        self.assertEqual(parsed['metadata']['igwx'], 4)
        self.assertNotEqual(parsed['metadata']['ngw'], parsed['metadata']['igwx'])
        expected = self.install()
        expected['npw'] = 9
        with self.assertRaisesRegex(WavefunctionParseError, 'XML npw'):
            parse_wfc(self.path, expected)

    def test_no_G0_or_negative_G_closure_requirement(self):
        parsed = parse_wfc(self.path, self.install())
        self.assertNotIn([0, 0, 0], parsed['miller'])
        self.assertNotIn([-2, 0, 1], parsed['miller'])
        self.assertEqual(parsed['qe_wfc_format_status'], 'PASS')

    def test_component_blocks_original_bands_and_signed_zero_preserved(self):
        expected = self.install()
        original = self.path.read_bytes()
        parsed = parse_wfc(self.path, expected)
        c = parsed['coefficients']
        for band in range(24):
            for component in range(2):
                for g in range(4):
                    a, b = c[component][g][band], coefficient(component, g, band)
                    self.assertEqual(struct.pack('<dd', a.real, a.imag), struct.pack('<dd', b.real, b.imag))
        # An interleaved export is an explicit permutation, never a reshape
        # of the QE component blocks. Relative spin phase gives nonzero sigma_y.
        interleaved = [c[s][g][0] for g in range(4) for s in range(2)]
        self.assertEqual(interleaved[:2], [complex(1, -0.0), complex(-0.0, 2)])
        self.assertEqual(2*(interleaved[0].conjugate()*interleaved[1]).imag, 4)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(parsed['metadata']['coefficient_bitwise_roundtrip_status'], 'PASS')

    def test_header_only_does_not_read_or_validate_coefficient_values(self):
        records = synthetic_records(transform=lambda z,s,g,b: complex(float('nan'), 0) if b == 4 else z)
        expected = self.install(envelope(records))
        header = read_header(self.path)
        self.assertEqual(header['coefficient_values_status'], 'NOT_READ')
        self.assertEqual(header['miller_values_status'], 'NOT_READ')
        self.assertEqual(header['header_validation_status'], 'HEADER_AND_RECORD_ENVELOPES_ONLY')
        with self.assertRaisesRegex(WavefunctionParseError, 'Nonfinite coefficient'):
            parse_wfc(self.path, expected)

    def test_record_truncation_and_missing_full_band_record(self):
        data = envelope(synthetic_records())
        for cut in (1, 4, 20, 40, 153, len(data)-1, len(data)-8):
            with self.subTest(cut=cut):
                self.reject(data[:cut])
        self.reject(envelope(synthetic_records()[:-1]))

    def test_extra_record_extra_byte_and_mismatched_trailer(self):
        records = synthetic_records()
        for data in (envelope(records)+b'X', envelope(records+[b'junk']),
                     envelope(records)[:-4]+struct.pack('<i', 7)):
            with self.subTest(length=len(data)):
                self.reject(data)

    def test_negative_split_or_oversized_record_markers(self):
        data = envelope(synthetic_records())
        for marker in (-44, 0, 2_000_000_000):
            self.reject(struct.pack('<i', marker)+data[4:])

    def test_wrong_record_byte_counts(self):
        for index in (0, 1, 2, 3, 4, 27):
            with self.subTest(index=index):
                records = synthetic_records()
                records[index] = records[index]+b'\x00'*8
                self.reject(envelope(records))

    def test_wrong_spin_band_gamma_and_scale_are_explicitly_unsupported(self):
        for options, status in [({'npol': 1}, 'UNSUPPORTED_SPIN_LAYOUT'),
                                ({'ispin': 2}, 'UNSUPPORTED_SPIN_LAYOUT'),
                                ({'nbnd': 23}, 'UNSUPPORTED_BAND_COUNT'),
                                ({'gamma': 1}, 'UNSUPPORTED_GAMMA_ONLY'),
                                ({'gamma': -1}, 'UNSUPPORTED_GAMMA_ONLY'),
                                ({'scalef': .03162277660168379}, 'UNSUPPORTED_SCALE_CONVENTION'),
                                ({'scalef': 2.}, 'UNSUPPORTED_SCALE_CONVENTION')]:
            with self.subTest(options=options):
                expected = self.install(**options)
                with self.assertRaises(WavefunctionParseError) as caught:
                    parse_wfc(self.path, expected)
                self.assertEqual(caught.exception.status, status)

    def test_duplicate_miller_and_malformed_dimensions(self):
        bad = copy.deepcopy(MILLER)
        bad[-1] = bad[0]
        self.reject(envelope(synthetic_records(miller=bad)), 'Duplicate')
        for options in ({'ngw': 3}, {'ngw': 1_000_001}, {'npol': 3}, {'nbnd': 0}, {'gamma': 2}):
            with self.subTest(options=options):
                self.reject(envelope(synthetic_records(**options)))

    def test_native_miller_order_is_preserved_not_sorted_or_integerized_k(self):
        permutation = [3, 0, 2, 1]
        records = synthetic_records(miller=[MILLER[i] for i in permutation],
                                    transform=lambda z,s,g,b: coefficient(s, permutation[g], b))
        parsed = parse_wfc(self.path, self.install(envelope(records)))
        self.assertEqual(parsed['miller'], [MILLER[i] for i in permutation])
        for s in range(2):
            for g in range(4):
                self.assertEqual(parsed['coefficients'][s][g][7], coefficient(s, permutation[g], 7))
        self.assertEqual(parsed['metadata']['k_cart_bohr_inv'], K)

    def test_filename_never_authenticates_k_and_same_size_other_state_rejected(self):
        expected = self.install()
        changed = envelope(synthetic_records(ik=3, k=[-x for x in K]))
        self.assertEqual(len(changed), self.path.stat().st_size)
        self.path.write_bytes(changed)
        with self.assertRaisesRegex(WavefunctionParseError, 'SHA-256'):
            parse_wfc(self.path, expected)
        expected['source_sha256'] = hashlib.sha256(changed).hexdigest()
        with self.assertRaisesRegex(WavefunctionParseError, 'ik'):
            parse_wfc(self.path, expected)

    def test_nonaxial_k_wrong_2pi_and_transposed_reciprocal_vectors(self):
        for key, value in [('k_cart_bohr_inv', [0., 0., 0.]),
                           ('k_cart_bohr_inv', [x*2*math.pi for x in K]),
                           ('b_columns_bohr_inv', list(map(list, zip(*B))))]:
            with self.subTest(key=key, value=value):
                expected = self.install()
                expected[key] = value
                with self.assertRaisesRegex(WavefunctionParseError, 'geometry'):
                    parse_wfc(self.path, expected)

    def test_nonfinite_header_and_coefficients(self):
        for options in ({'scalef': float('nan')}, {'k': [0., float('inf'), 0.]},
                        {'b': [[0., 0., float('nan')], B[1], B[2]]}):
            self.reject(envelope(synthetic_records(**options)))
        for value in (float('nan'), float('inf'), float('-inf')):
            for part in ('real', 'imag'):
                with self.subTest(value=value, part=part):
                    def transform(z,s,g,b):
                        if s == 1 and g == 3 and b == 23:
                            return complex(value, z.imag) if part == 'real' else complex(z.real, value)
                        return z
                    self.reject(envelope(synthetic_records(transform=transform)), 'Nonfinite coefficient')

    def test_unsupported_hdf5_and_explicit_ambiguous_candidate_guard(self):
        expected = self.install(b'\x89HDF\r\n\x1a\n'+b'synthetic')
        with self.assertRaises(WavefunctionParseError) as caught:
            parse_wfc(self.path, expected)
        self.assertEqual(caught.exception.status, 'UNSUPPORTED_HDF5')
        # Strict header lengths distinguish the actual formats. This synthetic
        # candidate-level counterexample verifies the no-first-match policy.
        with self.assertRaises(WavefunctionParseError) as caught:
            _unique_candidate([{'format': 'synthetic-A'}, {'format': 'synthetic-B'}], [])
        self.assertEqual(caught.exception.status, 'UNSUPPORTED_AMBIGUOUS_FORMAT')

    def test_zero_and_empty_states_preserved_no_normalization_or_band_drop(self):
        records = synthetic_records(transform=lambda z,s,g,b: 0j if b == 23 else z)
        parsed = parse_wfc(self.path, self.install(envelope(records)))
        self.assertEqual(parsed['shape'][2], 24)
        self.assertTrue(all(parsed['coefficients'][s][g][23] == 0 for s in range(2) for g in range(4)))
        norm = sum(abs(parsed['coefficients'][s][g][0])**2 for s in range(2) for g in range(4))
        self.assertGreater(norm, 5)
        self.assertEqual(parsed['physical_validation_status'], 'NOT_PERFORMED_BY_FORMAT_READER')


if __name__ == '__main__':
    unittest.main()
