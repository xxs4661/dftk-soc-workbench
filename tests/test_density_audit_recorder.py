"""Synthetic protocol/binding tests; never scientific calculations or raw files."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_density_hartree_audit as audit


class DensityAuditRecorderTests(unittest.TestCase):
    def receipt(self):
        endpoint = {'n_in_sha256':'in', 'n_out_sha256':'out', 'map_count':191,
                    'unmixed_residual_l2':1e-9,
                    'diagnostics':{'orbital_density_sha256':'out','consumed_input_sha256':'in'}}
        spec = {'run_id':'synthetic-A', 'checkpoint':{'sha256':'bound'}}
        raw = {'run_id':'synthetic-A','label':'A','checkpoint_sha256':'bound',
               'execution_status':'PASS','exit_code':0,'final':copy.deepcopy(endpoint)}
        return spec, raw, endpoint

    def test_bound_synthetic_receipt(self):
        audit.validate_dftk_receipt('A', *self.receipt())

    def test_wrong_run_id_rejected(self):
        spec, raw, endpoint = self.receipt()
        raw['run_id'] = 'synthetic-B'
        with self.assertRaisesRegex(ValueError, 'run ID'):
            audit.validate_dftk_receipt('A', spec, raw, endpoint)

    def test_wrong_checkpoint_rejected(self):
        spec, raw, endpoint = self.receipt()
        raw['checkpoint_sha256'] = 'unbound'
        with self.assertRaisesRegex(ValueError, 'checkpoint'):
            audit.validate_dftk_receipt('A', spec, raw, endpoint)

    def test_n_in_n_out_swapped_rejected(self):
        spec, raw, endpoint = self.receipt()
        endpoint['n_in_sha256'], endpoint['n_out_sha256'] = endpoint['n_out_sha256'], endpoint['n_in_sha256']
        with self.assertRaisesRegex(ValueError, 'Endpoint state'):
            audit.validate_dftk_receipt('A', spec, raw, endpoint)

    def test_self_consistent_hash_swap_still_rejected(self):
        spec, raw, endpoint = self.receipt()
        for d in (raw['final'], endpoint):
            d['n_in_sha256'], d['n_out_sha256'] = 'out','in'
        with self.assertRaisesRegex(ValueError, 'state swap'):
            audit.validate_dftk_receipt('A', spec, raw, endpoint)

    def test_source_bytes_hash_and_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'synthetic.dat'
            p.write_bytes(b'synthetic source')
            spec = {'bytes':len(p.read_bytes()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            audit.checked_file(p,spec)
            p.write_bytes(b'Synthetic source')
            with self.assertRaisesRegex(ValueError,'bytes differ'):
                audit.checked_file(p,spec)

    def test_old_pass_directory_rejected_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path/'result.json').write_text('{"execution_status":"PASS","run_id":"old"}')
            with self.assertRaises(FileExistsError):
                audit.execute(path,path,path,path,'never-run')
            self.assertEqual(json.loads((path/'result.json').read_text())['run_id'],'old')

    def test_summary_generation_failure_leaves_current_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            with self.assertRaises(RuntimeError):
                audit.save_completion(p, {'execution_status':'PASS','sources':{}},
                                      lambda _: (_ for _ in ()).throw(RuntimeError('synthetic')))
            self.assertEqual(json.loads((p/'result.json').read_text())['execution_status'],'FAIL')

    def test_summary_write_failure_leaves_current_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            (p/'summary.md').mkdir()
            with self.assertRaises(IsADirectoryError):
                audit.save_completion(p, {'execution_status':'PASS','sources':{}})
            self.assertEqual(json.loads((p/'result.json').read_text())['exit_code'],9)

    def test_invalid_nested_record_cannot_publish_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            for sources in (None, [], 'wrong', 1):
                with self.assertRaises(ValueError):
                    audit.save_completion(p, {'execution_status':'PASS','sources':sources})
                self.assertNotEqual(json.loads((p/'result.json').read_text())['execution_status'],'PASS')

    def test_nonfinite_output_cannot_publish_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            with self.assertRaises(ValueError):
                audit.save_completion(p, {'execution_status':'PASS','sources':{},'number':float('nan')})
            self.assertEqual(json.loads((p/'result.json').read_text())['execution_status'],'FAIL')

    def test_qe_coefficient_write_failure_cannot_enter_completion_set(self):
        parsed={'miller':[(0,0,0)], 'rho_g':[0.01+0j]}
        datasets={'A_out':{}, 'A_in':{}, 'B_out':{}, 'B_in':{}}
        with tempfile.TemporaryDirectory() as tmp:
            def broken_writer(*args):
                raise OSError('synthetic output failure')
            with self.assertRaises(OSError):
                audit.store_qe_coefficients(Path(tmp),parsed,datasets,broken_writer)
        self.assertNotIn('QE',datasets)
        self.assertIn('rho_g',parsed)

    def test_actual_historical_xml_schema_read_only(self):
        root=Path(__file__).resolve().parents[1]
        result=audit.validate_qe_xml(root/'results/mg-soc-qe-diagnostics/G40/qe.xml', audit.load(root/audit.PLAN))
        self.assertEqual(result['hartree_ha'],28.51678477992461)
        self.assertIsNone(result['exact_installed_qe_source_commit'])

    def test_native_csv_transfer_binding_rejects_changed_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'synthetic.csv'
            p.write_text('m1,m2,m3,n_in_real,n_in_imag,n_out_real,n_out_imag\n0,0,0,0.01,0.0,0.01,0.0\n')
            metadata={'coefficients':{'sha256':audit.digest(p),'row_count':1}}
            audit.read_bound_native_csv(p,'A',metadata,[1,1,1])
            p.write_text(p.read_text().replace('0.01','0.02'))
            with self.assertRaisesRegex(ValueError,'receipt'):
                audit.read_bound_native_csv(p,'A',metadata,[1,1,1])

    def test_persistence_failure_explicit(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(audit,'write_json',side_effect=OSError('synthetic disk')):
            with patch('sys.stderr') as stderr, self.assertRaises(OSError):
                audit.save_completion(Path(tmp), {'execution_status':'PASS','sources':{}})
            self.assertIn('Persistence failed',str(stderr.write.call_args_list))

    def test_nonorthogonal_reciprocal_and_wrong_2pi(self):
        import math
        # Columns A=(2,0,0),(1,3,0),(0,0,4); hand-derived inverse transpose.
        plan={'lattice_vectors_bohr':[[2,0,0],[1,3,0],[0,0,4]],'thresholds':{'reciprocal_duality_abs':1e-12}}
        b=[[math.pi,-math.pi/3,0],[0,2*math.pi/3,0],[0,0,math.pi/2]]
        self.assertLess(audit.validate_reciprocal_columns(b,plan),1e-12)
        with self.assertRaises(ValueError):
            audit.validate_reciprocal_columns([[x*2*math.pi for x in c] for c in b],plan)

    def test_entry_subprocesses_only_git_and_density_extractor(self):
        # Audit concrete dispatch sites, not comments mentioning forbidden work.
        tree=ast.parse(Path(audit.__file__).read_text())
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
               and isinstance(n.func.value,ast.Name) and n.func.value.id=='subprocess']
        self.assertEqual(len(calls),3)
        source=Path(audit.__file__).read_text()
        self.assertIn("str(root / 'scripts/extract_soc_density.jl')",source)
        for forbidden in ('run_soc_scf.jl','run_qe_soc.py','pw.x','pp.x','run_spinor_scf'):
            self.assertNotIn(forbidden,source)


if __name__=='__main__':
    unittest.main()
