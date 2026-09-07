"""Synthetic publication receipts, distinct from real QE restart evidence."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from check_qe_soc_diagnostics import check_receipt
ROOT=Path(__file__).resolve().parents[1]


class ReceiptContract(unittest.TestCase):
    def setUp(self):
        self.plan=json.loads((ROOT/'benchmarks/mg-soc-qe-diagnostics-v1/plan.json').read_text())
        self.record={'slot':'D36','run_id':'synthetic-D36-receipt',
            'input_path':self.plan['slots']['D36']['input_path'],
            'input_sha256':self.plan['slots']['D36']['input_sha256'],
            'plan_sha256':'synthetic-hash','preflight':{'plan_sha256':'synthetic-hash','saved_utc':'2099-01-01T00:00:00Z'},
            'started_utc':'2099-01-01T00:01:00Z','finished_utc':'2099-01-01T00:02:00Z',
            'process_interrupted':False,'qe_identity':self.plan['qe_identity'],
            'pseudo_before_sha256':self.plan['pseudo']['sha256'],'pseudo_after_sha256':self.plan['pseudo']['sha256'],
            'source_preservation_status':'PASS'}

    def test_supported_synthetic_receipt(self):
        check_receipt(self.plan,'D36',self.record)

    def test_mixed_slot_input_rejected(self):
        for key,value in [('slot','C36'),('run_id','synthetic-C36-receipt'),
                          ('input_path',self.plan['slots']['C36']['input_path']),
                          ('input_sha256',self.plan['slots']['C36']['input_sha256'])]:
            with self.subTest(key=key):
                r=copy.deepcopy(self.record);r[key]=value
                with self.assertRaises(ValueError):check_receipt(self.plan,'D36',r)

    def test_history_changed_or_interrupted_rejected(self):
        for key,value in [('source_preservation_status','FAIL'),('process_interrupted',True),
                          ('pseudo_after_sha256','different'),('started_utc','2000-01-01')]:
            with self.subTest(key=key):
                r=copy.deepcopy(self.record);r[key]=value
                with self.assertRaises(ValueError):check_receipt(self.plan,'D36',r)

    def test_launch_identity_not_just_version(self):
        r=copy.deepcopy(self.record);r['qe_identity']['binary_sha256']='changed'
        with self.assertRaises(ValueError):check_receipt(self.plan,'D36',r)


if __name__=='__main__':unittest.main()
