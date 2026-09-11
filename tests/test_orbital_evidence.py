"""Synthetic transport/recorder fixtures; no physical orbital validation."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import orbital_evidence as evidence


def synthetic_state():
    # Deliberately unnormalized, general complex bytes test representation only.
    numbers = np.arange(2*3*24, dtype='<f8').reshape(2, 3, 24)
    c = (numbers + 1j*(numbers+0.25)).astype('<c16')
    c[0, 0, 0] = complex(-0.0, -0.0)
    return {'label': 'Q', 'lattice_columns': np.array([[4., .2, 0.], [0., 5., .3], [0., 0., 6.]], dtype='<f8'),
            'reciprocal_columns': np.arange(9, dtype='<f8').reshape(3, 3), 'fft_size': [4, 6, 8],
            'kpoints': [{'millers': np.array([[1, 0, 0], [-1, 2, 0], [0, 0, 0]], dtype='<i8'),
                'coefficients': c, 'occupations': np.linspace(0., 1., 24, dtype='<f8'),
                'eigenvalues': np.linspace(-1., 2., 24, dtype='<f8'),
                'k_cart': np.array([.125, -.25, .0625], dtype='<f8'),
                'coordinate_fractional': [.125, -.25, .0625], 'weight': 1., 'source_k_index': 2}],
            'raw_metadata': {'schema_version': 1, 'phase': '7F', 'execution_status': 'PASS',
                'label': 'Q', 'source_run_id': 'SYNTHETIC-Q', 'plan_sha256': 'a'*64,
                'n_bands': 24, 'occupation_capacity': 1, 'normalization_applied': False,
                'orbital_rotation_applied': False, 'source_binding_status': 'PASS',
                'data_roundtrip_status': 'PASS', 'fixture_scope': 'SYNTHETIC_TRANSPORT_ONLY'}}


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.path = self.root/'data.npz'
        self.arrays = {'real': np.array([[-0., 2.], [3., 4.]], dtype='<f8', order='F'),
                       'complex': np.array([1+2j, -3+4j], dtype='<c16'),
                       'miller': np.array([[2, 0, -1], [0, 0, 0]], dtype='<i8'),
                       'scalar': np.array(-0., dtype='<f8')}

    def test_numeric_c_order_roundtrip_keeps_shape_signed_zero_and_inputs(self):
        before = {k: (v.shape, v.tobytes(order='C')) for k, v in self.arrays.items()}
        manifest = evidence.save_package(self.path, self.arrays)
        restored = evidence.load_package(self.path, manifest)
        self.assertFalse(manifest['allow_pickle'])
        for key, value in restored.items():
            self.assertTrue(value.flags.c_contiguous)
            self.assertEqual((value.shape, value.tobytes()), before[key])
            self.assertEqual((self.arrays[key].shape, self.arrays[key].tobytes(order='C')), before[key])
            self.assertEqual(manifest['arrays'][key]['sha256'], hashlib.sha256(value.tobytes()).hexdigest())
        restored['real'][0, 0] = 99.
        self.assertEqual(evidence.load_package(self.path, manifest)['real'].tobytes(), before['real'][1])

    def test_existing_package_is_never_replaced(self):
        manifest = evidence.save_package(self.path, self.arrays); original = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Existing'): evidence.save_package(self.path, self.arrays)
        self.assertEqual(self.path.read_bytes(), original)
        evidence.load_package(self.path, manifest)

    def test_wrong_dtypes_and_nonfinite_rejected_before_write(self):
        for array in (np.array([1], dtype='>f8'), np.array([1], dtype='<f4'), np.array([object()], dtype=object),
                      np.array([np.nan], dtype='<f8'), np.array([complex(1, np.inf)], dtype='<c16')):
            with self.subTest(dtype=str(array.dtype)):
                with self.assertRaises(ValueError): evidence.save_package(self.path, {'x': array})
                self.assertFalse(self.path.exists())

    def test_unsafe_keys_rejected(self):
        for key in ('../x', 'x/y', 'x.npy', '', 3):
            with self.subTest(key=key):
                with self.assertRaises(ValueError): evidence.save_package(self.path, {key: self.arrays['real']})

    def test_file_missing_size_hash_and_link_rejected(self):
        manifest = evidence.save_package(self.path, self.arrays)
        wrong = copy.deepcopy(manifest); wrong['sha256'] = 'b'*64
        with self.assertRaisesRegex(ValueError, 'hash'): evidence.load_package(self.path, wrong)
        self.path.write_bytes(self.path.read_bytes()+b'x')
        with self.assertRaisesRegex(ValueError, 'size'): evidence.load_package(self.path, manifest)
        self.path.unlink()
        with self.assertRaisesRegex(ValueError, 'missing'): evidence.load_package(self.path, manifest)
        target = self.root/'target'; target.write_bytes(b'x'); self.path.symlink_to(target)
        with self.assertRaises(ValueError): evidence.load_package(self.path, manifest)

    def test_expanded_hash_shape_dtype_and_order_are_binding(self):
        manifest = evidence.save_package(self.path, self.arrays)
        changes = [('sha256', 'b'*64), ('dtype', '<i8'), ('shape', [4]), ('order', 'F'), ('bytes', 31)]
        for key, value in changes:
            wrong = copy.deepcopy(manifest); wrong['arrays']['real'][key] = value
            with self.subTest(field=key):
                with self.assertRaises(ValueError): evidence.load_package(self.path, wrong)

    def test_missing_extra_duplicate_members_rejected_even_with_new_container_hash(self):
        manifest = evidence.save_package(self.path, self.arrays)
        original = self.path.read_bytes()
        with zipfile.ZipFile(io.BytesIO(original)) as z:
            entries = [(name, z.read(name)) for name in z.namelist()]
        for variant in (entries[:-1], entries+[('extra.npy', entries[0][1])], entries+[entries[0]]):
            with self.subTest(entries=len(variant)):
                with zipfile.ZipFile(self.path, 'w') as z:
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter('ignore', UserWarning)
                        for name, data in variant: z.writestr(name, data)
                mutated = copy.deepcopy(manifest); data = self.path.read_bytes()
                mutated.update(bytes=len(data), sha256=evidence.sha256(data))
                with self.assertRaisesRegex(ValueError, 'members'): evidence.load_package(self.path, mutated)

    def test_compression_and_publication_write_failures_leave_no_package(self):
        with patch.object(evidence.np, 'savez_compressed', side_effect=OSError('synthetic compression failure')):
            with self.assertRaises(OSError): evidence.save_package(self.path, self.arrays)
        self.assertFalse(self.path.exists()); self.assertEqual(list(self.root.iterdir()), [])
        with patch.object(evidence.os, 'replace', side_effect=OSError('synthetic rename failure')):
            with self.assertRaises(OSError): evidence.save_package(self.path, self.arrays)
        self.assertFalse(self.path.exists()); self.assertEqual(list(self.root.iterdir()), [])


class PrimitiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.state = synthetic_state()

    def test_independent_julia_f_order_bytes_decode_without_component_swap(self):
        # Independent explicit ordering: spin changes first, then G, then band.
        c = self.state['kpoints'][0]['coefficients']
        data = b''.join(np.array([c[s, g, b]], dtype='<c16').tobytes()
                        for b in range(24) for g in range(3) for s in range(2))
        (self.root/'spinor.bin').write_bytes(data)
        desc = {'path': 'spinor.bin', 'dtype': '<c16', 'shape': [2, 3, 24], 'order': 'F',
                'bytes': len(data), 'sha256': evidence.sha256(data)}
        restored = evidence.read_primitive(self.root, desc)
        self.assertEqual(restored.tobytes(order='C'), c.tobytes(order='C'))

    def test_state_export_import_preserves_original_all_arrays_and_provenance(self):
        self.state['n_out'] = np.arange(4*6*8, dtype='<f8').reshape(4, 6, 8, order='F')
        path = evidence.write_state_metadata(self.state, self.root/'new')
        restored = evidence.load_state_metadata(path, expected_sha256=evidence.sha256(path.read_bytes()))
        self.assertEqual(restored['raw_metadata']['source_run_id'], 'SYNTHETIC-Q')
        self.assertEqual(restored['raw_metadata']['fixture_scope'], 'SYNTHETIC_TRANSPORT_ONLY')
        for key in ('lattice_columns', 'reciprocal_columns', 'n_out'):
            self.assertEqual(restored[key].tobytes(order='C'), self.state[key].tobytes(order='C'))
        for key in ('millers', 'coefficients', 'occupations', 'eigenvalues', 'k_cart'):
            self.assertEqual(restored['kpoints'][0][key].tobytes(order='C'), self.state['kpoints'][0][key].tobytes(order='C'))
        for key in ('coordinate_fractional', 'weight', 'source_k_index'):
            self.assertEqual(restored['kpoints'][0][key], self.state['kpoints'][0][key])
        self.assertFalse(restored['raw_metadata']['normalization_applied'])
        self.assertFalse(restored['raw_metadata']['orbital_rotation_applied'])

    def test_wrong_metadata_hash_missing_primitive_and_mutated_bytes_rejected(self):
        path = evidence.write_state_metadata(self.state, self.root/'new')
        with self.assertRaisesRegex(ValueError, 'metadata hash'): evidence.load_state_metadata(path, expected_sha256='b'*64)
        primitive = path.parent/'k1-coefficients.bin'; original = primitive.read_bytes()
        primitive.write_bytes(bytes([original[0]^1])+original[1:])
        with self.assertRaisesRegex(ValueError, 'Primitive hash'): evidence.load_state_metadata(path)
        primitive.unlink()
        with self.assertRaisesRegex(ValueError, 'Primitive file'): evidence.load_state_metadata(path)

    def test_primitive_descriptor_corruption_and_traversal(self):
        path = evidence.write_state_metadata(self.state, self.root/'new')
        descriptor = json.loads(path.read_text())['kpoints'][0]['coefficients']
        for field, value in [('dtype', '>c16'), ('shape', [2, 3, 23]), ('order', 'C'), ('bytes', 3),
                             ('path', '../coefficients.bin'), ('sha256', None)]:
            wrong = dict(descriptor, **{field: value})
            with self.subTest(field=field):
                with self.assertRaises(ValueError): evidence.read_primitive(path.parent, wrong)

    def test_missing_and_invalid_metadata_fields_rejected(self):
        path = evidence.write_state_metadata(self.state, self.root/'new'); good = json.loads(path.read_text())
        for field, value in [('execution_status', 'FAIL'), ('phase', '7E'), ('n_bands', 23),
                             ('occupation_capacity', True), ('normalization_applied', True),
                             ('source_binding_status', 'UNKNOWN'), ('coefficient_layout', 'block'),
                             ('plan_sha256', ''), ('kpoints', None)]:
            with self.subTest(field=field):
                path.write_text(json.dumps(dict(good, **{field: value})))
                with self.assertRaises((ValueError, TypeError, KeyError)): evidence.load_state_metadata(path)
        path.write_text(json.dumps({k: v for k, v in good.items() if k != 'lattice_columns'}))
        with self.assertRaises((ValueError, KeyError)): evidence.load_state_metadata(path)

    def test_bad_state_capacity_duplicate_g_and_geometry_shape_rejected(self):
        for variant in ('occupation', 'duplicate', 'geometry', 'nan', 'bands'):
            state = copy.deepcopy(self.state)
            if variant == 'occupation': state['kpoints'][0]['occupations'][0] = 1.01
            if variant == 'duplicate': state['kpoints'][0]['millers'][1] = state['kpoints'][0]['millers'][0]
            if variant == 'geometry': state['lattice_columns'] = np.zeros((9,), dtype='<f8')
            if variant == 'nan': state['kpoints'][0]['coefficients'][0, 0, 0] = np.nan
            if variant == 'bands': state['kpoints'][0]['coefficients'] = state['kpoints'][0]['coefficients'][:, :, :23]
            with self.subTest(variant=variant):
                with self.assertRaises(ValueError): evidence.write_state_metadata(state, self.root/variant)
                self.assertFalse((self.root/variant).exists())

    def test_state_storage_failure_never_publishes_metadata_pass(self):
        with patch.object(evidence, '_write_primitive', side_effect=OSError('synthetic primitive storage failure')):
            with self.assertRaises(OSError): evidence.write_state_metadata(self.state, self.root/'new')
        self.assertFalse((self.root/'new'/'metadata.json').exists())

    def test_existing_state_directory_preserved(self):
        path = evidence.write_state_metadata(self.state, self.root/'new'); old = path.read_bytes()
        with self.assertRaises(FileExistsError): evidence.write_state_metadata(self.state, path.parent)
        self.assertEqual(path.read_bytes(), old)


class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.directory = self.root/'current'

    def run_record(self, work, directory=None):
        stdout = io.StringIO(); stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = evidence.recorded_run(directory or self.directory, work, run_id='synthetic-run-1')
        return code, json.loads(stdout.getvalue()), stderr.getvalue()

    def assert_failed(self, code, output):
        self.assertNotEqual(code, 0); self.assertEqual(output['execution_status'], 'FAIL')
        current = json.loads((self.directory/'result.json').read_text())
        self.assertEqual(current['execution_status'], 'FAIL'); self.assertEqual(current['exit_code'], code)

    def test_running_and_summary_exist_before_final_pass_publication(self):
        original = evidence._atomic_bytes; seen = []
        def spy(path, data):
            if path.name == 'result.json':
                result = json.loads(data); seen.append(result['execution_status'])
                if result['execution_status'] == 'PASS':
                    summary = (path.parent/'summary.txt').read_bytes()
                    self.assertEqual(evidence.sha256(summary), result['summary_sha256'])
            return original(path, data)
        def work(directory):
            self.assertEqual(json.loads((directory/'result.json').read_text())['execution_status'], 'RUNNING')
            return {'execution_status': 'PASS', 'exit_code': 0, 'summary': 'synthetic success'}
        with patch.object(evidence, '_atomic_bytes', side_effect=spy): code, result, error = self.run_record(work)
        self.assertEqual(code, 0); self.assertEqual(seen, ['RUNNING', 'PASS']); self.assertEqual(error, '')

    def test_legitimate_worker_failure_retains_code(self):
        code, result, _ = self.run_record(lambda d: {'execution_status': 'BLOCKED', 'exit_code': 5, 'reason': 'synthetic absent prerequisite'})
        self.assertEqual(code, 5); self.assertEqual(result['execution_status'], 'BLOCKED')
        self.assertEqual(json.loads((self.directory/'result.json').read_text())['exit_code'], 5)

    def test_bad_status_identity_types_and_nonfinite_cannot_publish_pass(self):
        variants = [None, {'execution_status': 'PASS', 'exit_code': 2}, {'execution_status': 'FAIL', 'exit_code': 0},
                    {'execution_status': 'PASS', 'exit_code': True}, {'execution_status': 'PASS', 'exit_code': 0, 'run_id': 'old'},
                    {'execution_status': 'PASS', 'exit_code': 0, 'schema_version': 999},
                    {'execution_status': 'PASS', 'exit_code': 0, 'summary': None},
                    {'execution_status': 'PASS', 'exit_code': 0, 'data': {'x': float('nan')}}]
        for index, variant in enumerate(variants):
            self.directory = self.root/str(index)
            with self.subTest(variant=variant):
                code, result, _ = self.run_record(lambda d: variant); self.assert_failed(code, result)
                self.assertEqual(set(result), {'schema_version', 'run_id', 'execution_status', 'exit_code', 'reason'})

    def test_exception_after_worker_premature_pass_is_replaced_safely(self):
        def work(directory):
            (directory/'result.json').write_text('{"execution_status":"PASS","bad_nested":null}')
            raise RuntimeError('synthetic worker failure')
        code, result, _ = self.run_record(work); self.assert_failed(code, result)
        self.assertNotIn('bad_nested', result)

    def test_missing_required_source_is_blocked_with_distinct_exit(self):
        def work(directory):
            raise FileNotFoundError('synthetic original source unavailable')
        code, result, _ = self.run_record(work)
        self.assertEqual(code, 10); self.assertEqual(result['execution_status'], 'BLOCKED')
        self.assertIn('original source unavailable', result['reason'])
        self.assertEqual(json.loads((self.directory/'result.json').read_text()), result)

    def test_summary_encoding_failure_is_safe(self):
        code, result, _ = self.run_record(lambda d: {'execution_status': 'PASS', 'exit_code': 0, 'summary': '\ud800'})
        self.assert_failed(code, result)

    def test_summary_write_failure_is_safe(self):
        original = evidence._atomic_bytes
        def fail(path, data):
            if path.name == 'summary.txt': raise OSError('synthetic summary write failure')
            return original(path, data)
        with patch.object(evidence, '_atomic_bytes', side_effect=fail):
            code, result, _ = self.run_record(lambda d: {'execution_status': 'PASS', 'exit_code': 0})
        self.assert_failed(code, result)

    def test_final_result_write_failure_falls_back_to_fresh_fail(self):
        original = evidence._atomic_bytes
        def fail(path, data):
            if path.name == 'result.json' and json.loads(data)['execution_status'] != 'RUNNING':
                raise OSError('synthetic atomic result failure')
            return original(path, data)
        with patch.object(evidence, '_atomic_bytes', side_effect=fail):
            code, result, _ = self.run_record(lambda d: {'execution_status': 'PASS', 'exit_code': 0})
        self.assert_failed(code, result)

    def test_genuine_unwritable_output_reports_nonzero_and_persistence_failure(self):
        with patch.object(evidence.Path, 'mkdir', side_effect=PermissionError('synthetic unwritable filesystem')):
            code, result, stderr = self.run_record(lambda d: {'execution_status': 'PASS', 'exit_code': 0})
        self.assertEqual(code, 9); self.assertEqual(result['persistence_status'], 'FAIL')
        self.assertIn('persistence failed', stderr); self.assertFalse(self.directory.exists())

    def test_old_pass_is_preserved_and_not_reused_as_current_result(self):
        self.directory.mkdir(); old = b'{"execution_status":"PASS","run_id":"old-run"}\n'
        (self.directory/'result.json').write_bytes(old)
        with patch.object(evidence, '_atomic_bytes') as save:
            code, result, _ = self.run_record(lambda d: self.fail('Worker must not run'))
        self.assertEqual(code, 2); self.assertEqual(result['execution_status'], 'FAIL'); save.assert_not_called()
        self.assertEqual((self.directory/'result.json').read_bytes(), old)


if __name__ == '__main__':
    unittest.main()
