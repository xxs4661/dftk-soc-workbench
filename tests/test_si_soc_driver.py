"""Synthetic recorder contracts only; never a Julia or physical Si validation."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_si_dftk as m

class DriverContract(unittest.TestCase):
    def good(self):
        return dict(schema_version=1,case='si-soc-splitting-v1',run_id='synthetic-dftk',action='prepare',exit_code=0,execution_status='PASS',environment={'status':'PASS'},input={'element':'Si','nlcc_present':True},grid={'status':'PASS'})
    def test_current_prepare(self):m.validate_worker(self.good(),0,'prepare','synthetic-dftk')
    def test_negative_worker_retained(self):
        v=self.good();v.update(exit_code=1,execution_status='FAIL',reason='synthetic convergence failure');m.validate_worker(v,1,'prepare','synthetic-dftk')
    def test_wrong_exit(self):
        with self.assertRaises(ValueError):m.validate_worker(self.good(),1,'prepare','synthetic-dftk')
    def test_false_pass(self):
        v=self.good();v['execution_status']='FAIL'
        with self.assertRaises(ValueError):m.validate_worker(v,0,'prepare','synthetic-dftk')
    def test_stale_action_or_run(self):
        for k,val in [('action','D-SCF'),('run_id','old-success')]:
            v=self.good();v[k]=val
            with self.subTest(k=k),self.assertRaises(ValueError):m.validate_worker(v,0,'prepare','synthetic-dftk')
    def test_bad_nested(self):
        for k in ['input','environment','grid']:
            for x in [None,[],False]:
                v=self.good();v[k]=x
                with self.subTest(k=k,x=x),self.assertRaises(ValueError):m.validate_worker(v,0,'prepare','synthetic-dftk')
    def test_static_needs_all_three(self):
        v=self.good();v['action']='static'
        for k in ['nlcc','spin_trace','time_reversal']:v[k]={'status':'PASS'}
        m.validate_worker(v,0,'static','synthetic-dftk')
        for k in ['nlcc','spin_trace','time_reversal']:
            b=copy.deepcopy(v);b[k]['status']='INCONCLUSIVE'
            with self.assertRaises(ValueError):m.validate_worker(b,0,'static','synthetic-dftk')
    def test_spectrum_cannot_be_null(self):
        v=self.good();v.update(action='D-SPECTRUM',spectrum={'execution_status':'PASS','process_exit_code':0,'physical_operator':'spin_trace_null'})
        with self.assertRaises(ValueError):m.validate_worker(v,0,'D-SPECTRUM','synthetic-dftk')
    def test_no_old_directory_reused(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=root/'.work/phase8a/existing';p.mkdir(parents=True);old=p/'receipt.json';old.write_text('{"execution_status":"PASS"}')
            with self.assertRaises(ValueError):m.launch('prepare',p,root=root)
            self.assertEqual(json.loads(old.read_text())['execution_status'],'PASS') # Old file untouched; explicitly refused, never accepted.
    def test_current_early_failure_durable(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=root/'.work/phase8a/new'
            with patch.object(m,'verify_preparation',side_effect=ValueError('synthetic missing source')):
                code=m.launch('prepare',p,root=root)
            self.assertEqual(code,1);r=json.loads((p/'receipt.json').read_text());self.assertEqual(r['execution_status'],'FAIL');self.assertNotIn('worker_exit_code',r)
    def test_parent_failure_cannot_supply_density(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'receipt.json').write_text(json.dumps(dict(action='D-SCF',execution_status='FAIL',exit_code=1)))
            with self.assertRaises(ValueError):m.checked_parent(p)
if __name__=='__main__':unittest.main()
