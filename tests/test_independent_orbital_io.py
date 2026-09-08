"""Small synthetic-only tests; no public physical package is read or computed."""
import copy
import gzip
import hashlib
import importlib.util
import io
from pathlib import Path
import struct
import tempfile
import unittest
import warnings
import zipfile

import numpy as np

SPEC = importlib.util.spec_from_file_location(
    'independent_orbital_io', Path(__file__).resolve().parents[1] / 'scripts/independent_orbital_io.py')
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class SyntheticPublicInputs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def package(self, arrays, declared_order='C', duplicate=False):
        path = self.root / 'synthetic.npz'
        specs = {}
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
                for name, arr in arrays.items():
                    raw = io.BytesIO()
                    np.save(raw, arr, allow_pickle=True)
                    z.writestr(name + '.npy', raw.getvalue())
                    if duplicate:
                        z.writestr(name + '.npy', raw.getvalue())
                    specs[name] = {'dtype': arr.dtype.str, 'shape': list(arr.shape),
                                   'order': declared_order, 'bytes': arr.nbytes,
                                   'sha256': sha(arr.tobytes(order=declared_order))}
        raw = path.read_bytes()
        return path, {'bytes': len(raw), 'sha256': sha(raw), 'arrays': specs}

    def test_source_single_byte_change_unknown_and_escape(self):
        (self.root / 'synthetic.txt').write_bytes(b'abc')
        manifest = {'synthetic.txt': sha(b'abc')}
        self.assertEqual(reader.verify_sources(self.root, manifest)['synthetic.txt']['bytes'], 3)
        (self.root / 'synthetic.txt').write_bytes(b'abd')
        with self.assertRaisesRegex(reader.InputIdentityError, 'SHA mismatch'):
            reader.verify_sources(self.root, manifest)
        with self.assertRaisesRegex(reader.InputIdentityError, 'missing'):
            reader.verify_sources(self.root, {'missing.txt': sha(b'')})
        for p in ('../other', '.work/file', '/private/source'):
            with self.assertRaises(reader.InputIdentityError):
                reader.source_path(self.root, p)

    def test_npz_container_expanded_hash_and_fortran_distinction(self):
        arr = np.asfortranarray(np.arange(6, dtype='<f8').reshape(2, 3))
        path, meta = self.package({'x': arr})
        loaded, receipt = reader.load_canonical_npz(path, meta)
        self.assertTrue(np.array_equal(loaded['x'], arr))
        self.assertFalse(loaded['x'].flags.writeable)
        self.assertEqual(receipt['x']['npy_storage_order'], 'F')
        self.assertEqual(receipt['x']['expanded_order'], 'C')
        self.assertNotEqual(receipt['x']['npy_container_sha256'], receipt['x']['expanded_sha256'])
        self.assertEqual(reader.verify_array_immutability(loaded, receipt)['status'], 'EXACT_MATCH')
        modified = {'x': loaded['x'].copy()}
        modified['x'][0, 0] = np.nextafter(modified['x'][0, 0], 1.)
        with self.assertRaisesRegex(reader.InputIdentityError, 'original array bytes changed'):
            reader.verify_array_immutability(modified, receipt)
        wrong = copy.deepcopy(meta)
        wrong['arrays']['x']['sha256'] = sha(arr.tobytes(order='F'))
        with self.assertRaisesRegex(reader.InputIdentityError, 'expanded array SHA'):
            reader.load_canonical_npz(path, wrong)

    def test_npz_missing_extra_duplicate_and_truncated_rejected(self):
        arr = np.arange(3, dtype='<i8')
        path, meta = self.package({'x': arr})
        wrong = copy.deepcopy(meta)
        wrong['arrays']['missing'] = wrong['arrays'].pop('x')
        with self.assertRaisesRegex(reader.InputIdentityError, 'member'):
            reader.load_canonical_npz(path, wrong)
        path, meta = self.package({'x': arr}, duplicate=True)
        with self.assertRaisesRegex(reader.InputIdentityError, 'duplicate'):
            reader.load_canonical_npz(path, meta)
        path.write_bytes(path.read_bytes()[:-12])
        meta['bytes'], meta['sha256'] = path.stat().st_size, sha(path.read_bytes())
        with self.assertRaises(reader.InputIdentityError):
            reader.load_canonical_npz(path, meta)

    def test_npz_object_nonfinite_dtype_shape_and_expansion_rejected(self):
        for arr in (np.array([object()], dtype=object), np.array([np.inf], dtype='<f8')):
            path, meta = self.package({'x': arr})
            with self.assertRaises(reader.InputIdentityError):
                reader.load_canonical_npz(path, meta)
        path, meta = self.package({'x': np.arange(12, dtype='<f8').reshape(3, 4)})
        with self.assertRaisesRegex(reader.InputIdentityError, 'expansion limit'):
            reader.load_canonical_npz(path, meta, max_expanded_bytes=16)
        wrong = copy.deepcopy(meta)
        wrong['arrays']['x']['shape'] = [4, 3]
        with self.assertRaisesRegex(reader.InputIdentityError, 'shape'):
            reader.load_canonical_npz(path, wrong)
        wrong = copy.deepcopy(meta)
        wrong['arrays']['x']['dtype'] = '<i8'
        with self.assertRaisesRegex(reader.InputIdentityError, 'dtype'):
            reader.load_canonical_npz(path, wrong)

    def native_fixture(self):
        k = {'k_cart': np.array([0.1, -0.2, 0.3]),
             'millers': np.array([[0, 1, -1], [2, -3, 1]], dtype='<i8'),
             'coefficients': np.array([[[1 + 2j, 3 - 4j], [5 + 6j, 7 - 8j]],
                                       [[9 - 1j, 2 + 3j], [4 - 5j, 6 + 7j]]], dtype='<c16')}
        b = [[1., 0.1, 0.], [0., 2., 0.2], [0.3, 0., 3.]]
        head = [struct.pack('<i3diid', 1, .1, -.2, .3, 1, 0, 1.),
                struct.pack('<4i', 7, 2, 2, 2),
                struct.pack('<9d', 1., .1, 0., 0., 2., .2, .3, 0., 3.)]
        miller = struct.pack('<6i', 0, 1, -1, 2, -3, 1)
        bands = []
        for band in range(2):
            numbers = []
            for spin in range(2):
                for g in range(2):
                    z = k['coefficients'][spin, g, band]
                    numbers.extend([z.real, z.imag])
            bands.append(struct.pack('<8d', *numbers))
        all_parts = head + [miller] + bands
        raw = b''
        records = []
        for part in all_parts:
            records.append({'payload_offset': len(raw) + 4, 'payload_bytes': len(part)})
            raw += struct.pack('<i', len(part)) + part + struct.pack('<i', len(part))
        meta = {'format': {'endian': 'little', 'record_marker_bytes': 4, 'integer_bytes': 4,
                           'logical_bytes': 4, 'real_bytes': 8, 'complex_bytes': 16},
                'ik': 1, 'k_cart_bohr_inv': [.1, -.2, .3], 'b_columns_bohr_inv': b,
                'ispin': 1, 'gamma_only_raw': 0, 'gamma_only': False, 'scalef': 1.,
                'ngw': 7, 'igwx': 2, 'npol': 2, 'nbnd': 2,
                'header_payload_sha256': sha(b''.join(head)), 'records': records,
                'record_payload_bytes': [len(x) for x in all_parts],
                'file_bytes': len(raw), 'source_sha256': sha(raw)}
        original = {'metadata': meta, 'miller_payload_sha256': sha(miller),
                    'coefficient_payload_sha256': sha(b''.join(bands)), 'source_sha256': sha(raw)}
        return k, original

    def test_native_complete_records_spin_blocks_and_single_bit(self):
        k, original = self.native_fixture()
        receipt = reader.reconstruct_wfc(k, original)
        self.assertEqual(receipt['records'], 6)
        self.assertEqual(receipt['bands'], 2)
        self.assertFalse(receipt['native_file_written'])
        k['coefficients'] = k['coefficients'][::-1].copy()
        with self.assertRaisesRegex(reader.InputIdentityError, 'coefficient SHA'):
            reader.reconstruct_wfc(k, original)
        k, original = self.native_fixture()
        k['coefficients'].view(np.uint8).reshape(-1)[0] ^= 1
        with self.assertRaisesRegex(reader.InputIdentityError, 'coefficient SHA'):
            reader.reconstruct_wfc(k, original)

    def filplot_fixture(self):
        text = '\n2 2 1 2 2 1 1 1\n0 2.00000000 0 0 0 0 0\n'
        text += '1.0000000000 0.0000000000 0.0000000000\n'
        text += '0.2500000000 1.0000000000 0.0000000000\n'
        text += '0.0000000000 0.0000000000 1.0000000000\n'
        text += '100.0 4.0 30.0 2\n1 Mg 10.00\n1 .17 .23 .31 1\n'
        text += '2.000E+00 -4.00E+00 6.0D-01 8.0000E+00\n'
        path = self.root / 'synthetic.pp.gz'
        path.write_bytes(gzip.compress(text.encode('ascii')))
        return path, text, np.array([[2., .5, 0.], [0., 2., 0.], [0., 0., 2.]])

    def test_decimal_halfwidth_rydberg_once_first_index_fast(self):
        path, _, lattice = self.filplot_fixture()
        result = reader.read_filplot(path, lattice, (2, 2, 1))
        self.assertTrue(np.array_equal(result['values_ha'][:, :, 0], [[1., .3], [-2., 4.]]))
        self.assertEqual(result['halfwidth_ha'][0, 0, 0], 0.00025)
        self.assertEqual(result['halfwidth_ha'][1, 0, 0], 0.0025)
        self.assertFalse(result['header_lattice_used_for_volume'])
        self.assertEqual(result['unit_divisions_by_two'], 1)
        with self.assertRaises(reader.InputIdentityError):
            reader.decimal_token('NaN')

    def test_filplot_padding_grid_plotnum_cell_and_truncation(self):
        path, text, lattice = self.filplot_fixture()
        for modified in (text.replace('2 2 1 2 2 1', '3 2 1 2 2 1'),
                         text.replace('30.0 2', '30.0 0'),
                         text.replace('2.00000000', '3.00000000'),
                         text.replace(' 8.0000E+00', '')):
            path.write_bytes(gzip.compress(modified.encode('ascii')))
            with self.assertRaises(reader.InputIdentityError):
                reader.read_filplot(path, lattice, (2, 2, 1))

    def test_density_full_header_count_duplicates_and_nonfinite(self):
        path = self.root / 'synthetic.csv.gz'
        valid = 'm1,m2,m3,QE_real,QE_imag\n0,0,0,0.5,0\n1,-1,2,0.1,-0.2\n'
        path.write_bytes(gzip.compress(valid.encode('ascii')))
        result = reader.read_density_csv(path, 2)
        self.assertEqual(result['coefficients'][1], .1 - .2j)
        self.assertFalse(result['coefficients'].flags.writeable)
        for invalid in (valid.replace('QE_imag', 'imag'), valid.replace('1,-1,2', '0,0,0'),
                        valid.replace('0.1,-0.2', 'nan,-0.2'), valid.rsplit('\n', 2)[0] + '\n'):
            path.write_bytes(gzip.compress(invalid.encode('ascii')))
            with self.assertRaises(reader.InputIdentityError):
                reader.read_density_csv(path, 2)

    def test_xml_original_capacity_weights_and_unmodified_24_states(self):
        f = ['1.000E+00'] * 2 + ['0.000E+00'] * 22
        e = [str(i / 10) for i in range(24)]
        vectors = [['0', '0', '0'], ['0.125', '-0.25', '0.375'], ['-0.125', '0.25', '-0.375']]
        kpoints, tokens, sections = [], [], []
        for k in vectors:
            tokens.append({'k': k, 'weight': '0.3333333333333333',
                           'occupations': f, 'eigenvalues_ha': e})
            kpoints.append({'millers': np.zeros((2, 3), dtype='<i8'),
                            'occupations': np.array(f, dtype='<f8'),
                            'eigenvalues': np.array(e, dtype='<f8'),
                            'k_cart': np.array(k, dtype='<f8') * (2 * np.pi / 2),
                            'weight': 0.3333333333333333})
            sections.append('<ks_energies><k_point weight="0.3333333333333333">' + ' '.join(k) +
                            '</k_point><npw>2</npw><eigenvalues>' + ' '.join(e) +
                            '</eigenvalues><occupations>' + ' '.join(f) + '</occupations></ks_energies>')
        text = ('<synthetic><output><atomic_structure alat="2"><cell><a1>2 0 0</a1>'
                '<a2>0 2 0</a2><a3>0 0 2</a3></cell></atomic_structure><band_structure>'
                '<lsda>false</lsda><noncolin>true</noncolin><spinorbit>true</spinorbit>'
                '<nbnd>24</nbnd><nks>3</nks><nelec>2</nelec>' + ''.join(sections) +
                '</band_structure></output></synthetic>')
        path = self.root / 'synthetic.xml'
        path.write_text(text)
        state = {'lattice_columns': 2 * np.eye(3), 'kpoints': kpoints}
        meta = {'occupation_capacity': 1, 'xml': {'capacity': 1, 'native_tokens': tokens,
                                                'source_xml_sha256': sha(text.encode())}}
        self.assertEqual(reader.verify_xml(path, state, meta)['bands_per_k'], 24)
        wrong = copy.deepcopy(meta)
        wrong['occupation_capacity'] = 2
        with self.assertRaisesRegex(reader.InputIdentityError, 'capacity'):
            reader.verify_xml(path, state, wrong)
        state['kpoints'][0]['occupations'] = np.array(f, dtype='<f8') / 3
        with self.assertRaisesRegex(reader.InputIdentityError, 'original f/e'):
            reader.verify_xml(path, state, meta)


if __name__ == '__main__':
    unittest.main()
