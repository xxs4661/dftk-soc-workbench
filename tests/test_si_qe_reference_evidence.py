"""Synthetic publication protocol tests; no QE/Julia or physical execution."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import si_qe_reference_evidence as e
import si_qe_reference as r

class PublicEvidence(unittest.TestCase):
    def test_compressed_and_raw_identity_are_distinct_and_verified(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.gz';raw=b'Synthetic text 1.2345000 warning\n'*10
            info=e.packed(p,raw)
            self.assertNotEqual(info['gzip_sha256'],info['public_sha256'])
            self.assertEqual(e.unpacked(d,'x.gz',info),raw)
            p.write_bytes(gzip.compress(raw+b'changed',mtime=0))
            with self.assertRaises(ValueError):e.unpacked(d,'x.gz',info)
    def test_decompressed_hash_not_treated_as_gzip_hash(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.gz';info=e.packed(p,b'synthetic');info['public_sha256']='0'*64
            with self.assertRaises(ValueError):e.unpacked(d,'x.gz',info)
    def test_earlier_public_result_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.gz';e.packed(p,b'original')
            with self.assertRaises(ValueError):e.packed(p,b'replacement')
            self.assertEqual(gzip.decompress(p.read_bytes()),b'original')
    def test_hash_verified_corrupt_gzip_still_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.gz';p.write_bytes(b'not gzip')
            info={'gzip_bytes':8,'gzip_sha256':e.sha(p),'public_bytes':0,'public_sha256':'0'*64}
            with self.assertRaises(OSError):e.unpacked(d,'x.gz',info)
    def test_complete_high_band_mismatch_not_hidden_by_good_splitting(self):
        a={'e':[float(x) for x in range(24)]};b=copy.deepcopy(a);b['e'][23]+=.01
        with self.assertRaises(ValueError):e.close(a,b)
    def test_nonfinite_type_missing_fields_are_not_replay_tolerance(self):
        for a,b in [(float('nan'),1.),({'x':1},{}),(True,1),([1],[1,2])]:
            with self.subTest(a=a,b=b),self.assertRaises(ValueError):e.close(a,b)
    def test_redaction_preserves_numeric_and_warning_tokens(self):
        text=str(ROOT)+'/run 1.23456789e-9 IEEE_INVALID_FLAG\n'
        actual=e.redacted(text,ROOT)
        self.assertEqual(actual,'<WORKBENCH>/run 1.23456789e-9 IEEE_INVALID_FLAG\n')
    def test_compact_iteration_complete_warning_and_threshold_indices(self):
        stdout='iteration # 1\n ethr = 1.0E-10\n c_bands: eigenvalues not converged\niteration # 2\n ethr = 2.0E-12\n'
        parsed={'scf':{'trace':[{'iteration':1,'printed_free_ry':-1.,'estimated_scf_accuracy_ry':.1},{'iteration':2,'printed_free_ry':-2.,'estimated_scf_accuracy_ry':.01}]}}
        rows=e.iteration_rows(stdout,parsed)
        self.assertEqual(len(rows),2);self.assertEqual(rows[0]['warning_lines_one_based'],[3]);self.assertEqual(rows[1]['ethr_ry'],[2e-12])
        parsed['scf']['trace'].pop()
        with self.assertRaises(ValueError):e.iteration_rows(stdout,parsed)
    def test_bands_iteration_cannot_be_present(self):
        with self.assertRaises(ValueError):e.iteration_rows('iteration # 1\n',{'scf':None})
    def test_native_input_cannot_be_scf_for_gamma(self):
        native={'qe.in':(ROOT/r.CASE_DIR/'K6/qe-scf.in').read_bytes()}
        with self.assertRaisesRegex(ValueError,'Native input differs'):
            e.parse_public_native(ROOT,'K6',native,{'action':'Q-GAMMA'})
    def test_worker_nonzero_cannot_use_native_success(self):
        native={'qe.in':(ROOT/r.CASE_DIR/'K8/qe-scf.in').read_bytes()}
        with self.assertRaisesRegex(ValueError,'Failed native process'):
            e.parse_public_native(ROOT,'K8',native,{'action':'Q-SCF','execution_status':'PASS','process_exit_code':7})
    def test_missing_new_data_never_falls_back_to_old(self):
        with tempfile.TemporaryDirectory() as d:
            index=Path(d)/'index.json';index.write_text(json.dumps({'K6':{'Q-SCF':'.work/phase8c/K6/missing','Q-GAMMA':'.work/phase8c/K6/missing2'},'K8':{'Q-SCF':'.work/phase8c/K8/missing','Q-GAMMA':'.work/phase8c/K8/missing2'}}))
            with patch.object(r,'load_history',return_value={'B0':{},'K4':{}}),self.assertRaises(FileNotFoundError):e.export_runs(d,index)
            self.assertFalse((Path(d)/e.PUBLIC_DIR/'trend.json').exists())
if __name__=='__main__':unittest.main()
