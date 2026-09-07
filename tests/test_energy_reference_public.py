"""Recorder/public-table contracts; synthetic faults never execute Julia or QE."""
import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from run_energy_reference_audit import validate_worker_receipt


class WorkerReceipt(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        (self.root/'common').mkdir()
        # Not a Julia Serialization object: only tests the recorder's byte hash.
        self.arrays=b'synthetic opaque bytes; not physical arrays'
        (self.root/'common/arrays.bin').write_bytes(self.arrays)
        self.record={'run_id':'synthetic-current', 'plan_sha256':'1'*64,
            'execution_source_sha256':{'scripts/evaluate_common_energy_terms.jl':'2'*64}}
        self.receipt={'execution_status':'PASS','exit_code':0,
            'run_id':'synthetic-current','plan_sha256':'1'*64,'executed_script_sha256':'2'*64,
            'local_arrays':{'path':'arrays.bin','sha256':hashlib.sha256(self.arrays).hexdigest()}}

    def tearDown(self):
        self.temp.cleanup()

    def test_complete_current_receipt(self):
        validate_worker_receipt(self.receipt,self.record,self.root)

    def test_wrong_current_run_or_plan_rejected(self):
        for key in ('run_id','plan_sha256'):
            with self.subTest(field=key):
                altered=copy.deepcopy(self.receipt);altered[key]='stale'
                with self.assertRaisesRegex(ValueError,'current identity'):
                    validate_worker_receipt(altered,self.record,self.root)

    def test_wrong_executed_source_rejected(self):
        altered=copy.deepcopy(self.receipt);altered['executed_script_sha256']='3'*64
        with self.assertRaisesRegex(ValueError,'execution source'):
            validate_worker_receipt(altered,self.record,self.root)

    def test_failed_or_incomplete_worker_rejected(self):
        for change in [{'execution_status':'FAIL'},{'execution_status':'INCOMPLETE'},{'exit_code':1}]:
            with self.subTest(change=change):
                altered={**self.receipt,**change}
                with self.assertRaises(ValueError): validate_worker_receipt(altered,self.record,self.root)

    def test_null_or_wrong_type_worker_rejected(self):
        for value in (None,[],True,'PASS'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                validate_worker_receipt(value,self.record,self.root)

    def test_missing_array_receipt_rejected(self):
        for value in (None,[],{},'arrays.bin'):
            with self.subTest(value=value):
                altered={**self.receipt,'local_arrays':value}
                with self.assertRaises(ValueError): validate_worker_receipt(altered,self.record,self.root)

    def test_other_array_path_cannot_replace_current_file(self):
        altered=copy.deepcopy(self.receipt);altered['local_arrays']['path']='../previous/arrays.bin'
        with self.assertRaises(ValueError): validate_worker_receipt(altered,self.record,self.root)

    def test_changed_array_bytes_rejected(self):
        (self.root/'common/arrays.bin').write_bytes(b'changed synthetic bytes')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):
            validate_worker_receipt(self.receipt,self.record,self.root)

    def test_missing_array_file_rejected(self):
        (self.root/'common/arrays.bin').unlink()
        with self.assertRaises(FileNotFoundError): validate_worker_receipt(self.receipt,self.record,self.root)


if __name__=='__main__':
    unittest.main()
