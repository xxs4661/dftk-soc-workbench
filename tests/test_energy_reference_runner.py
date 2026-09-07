"""Synthetic recorder/transfer contracts, not Mg or Julia evaluation evidence."""
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_energy_reference_audit as audit


class EnergyRecorder(unittest.TestCase):
    def test_missing_source_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'BLOCKED_MISSING_SOURCE'):
                audit.bind_public(Path(d),dict(source_sha256={'absent':'x'},source_bytes={'absent':1}))

    def test_changed_source_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'source'; p.write_bytes(b'new')
            with self.assertRaisesRegex(ValueError,'changed'):
                audit.bind_public(Path(d),dict(source_sha256={'source':'0'*64},source_bytes={'source':3}))

    def test_transfer_preserves_entire_complex_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); p=root/'source.gz'
            raw=b'm1,m2,m3,QE_real,QE_imag\n1,2,-3,0.002,-0.0004\n'
            p.write_bytes(gzip.compress(raw,mtime=0))
            info=audit.prepare_transfer(root,root,dict(source_sha256={'source.gz':audit.digest(p)}),'qe','source.gz')
            self.assertEqual((root/'qe.csv').read_bytes(),raw)
            self.assertEqual(info['bytes'],len(raw))
            self.assertEqual(info['public_sha256'],audit.digest(p))

    def test_corrupt_transfer_not_pass(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); p=root/'source.gz'; p.write_bytes(b'notgzip')
            with self.assertRaises(gzip.BadGzipFile):
                audit.prepare_transfer(root,root,dict(source_sha256={'source.gz':audit.digest(p)}),'qe','source.gz')

    def test_missing_plan_creates_current_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); new=root/'new'
            self.assertEqual(audit.execute(root,new,'never-start-julia'),9)
            self.assertEqual(json.loads((new/'result.json').read_text())['execution_status'],'FAIL')

    def test_existing_run_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'result.json').write_text('{"execution_status":"PASS"}')
            before=(root/'result.json').read_bytes()
            with self.assertRaises(FileExistsError): audit.execute(root,root,'never-start-julia')
            self.assertEqual((root/'result.json').read_bytes(),before)

    def test_summary_failure_replaces_pass_with_safe_error(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); audit.write_json(root/'result.json',dict(execution_status='PASS'))
            def fail(_): raise ValueError('synthetic summary failure')
            with self.assertRaises(ValueError): audit.save_completion(root,dict(sources={},execution_status='PASS'),fail)
            self.assertEqual(json.loads((root/'result.json').read_text())['execution_status'],'FAIL')

    def test_summary_write_failure_leaves_no_current_pass(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'summary.md').mkdir()
            audit.write_json(root/'result.json',dict(execution_status='PASS'))
            with self.assertRaises(OSError): audit.save_completion(root,dict(sources={},execution_status='PASS'))
            self.assertEqual(json.loads((root/'result.json').read_text())['execution_status'],'FAIL')

    def test_null_worker_sources_cannot_publish_pass(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(ValueError): audit.save_completion(root,dict(sources=None,execution_status='PASS'))
            self.assertEqual(json.loads((root/'result.json').read_text())['execution_status'],'FAIL')

    def test_nonfinite_payload_cannot_publish_pass(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(ValueError): audit.save_completion(root,dict(sources={},execution_status='PASS',x=float('nan')))
            self.assertEqual(json.loads((root/'result.json').read_text())['execution_status'],'FAIL')

    def test_total_disk_failure_reports_nonzero(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(audit,'write_json',side_effect=OSError('synthetic disk full')):
                self.assertEqual(audit.execute(root,root/'new','never-start-julia'),9)


if __name__=='__main__': unittest.main()
