"""Synthetic arithmetic only; no material calculations."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
import tempfile

ROOT=Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location('timing_'+name,ROOT/'benchmarks/soc-timing-v1'/f'{name}.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
C=load('compare')
R=load('replay')

class Comparison(unittest.TestCase):
    def setUp(self):
        self.record=dict(map_index=1,kpoints=[[a,b,c] for a in [0,-.5] for b in [0,-.5] for c in [0,-.5]],
                         eigenvalues_ha=[[i/10 for i in range(24)] for _ in range(8)],
                         internal_energy_ha=-8.,free_energy_ha=-8.01)
    def test_same_map(self):
        self.assertEqual(C.compare_values(self.record,self.record,[1.,2.],[1.,2.])['status'],'PASS')
    def test_original_energy_difference_is_not_removed(self):
        changed=copy.deepcopy(self.record);changed['internal_energy_ha']+=1e-6
        self.assertEqual(C.compare_values(self.record,changed,[1.,2.],[1.,2.])['status'],'FAIL')
    def test_common_level_shift_is_not_fitted(self):
        changed=copy.deepcopy(self.record);changed['eigenvalues_ha']=[[v+.01 for v in k] for k in changed['eigenvalues_ha']]
        self.assertEqual(C.compare_values(self.record,changed,[1.,2.],[1.,2.])['status'],'FAIL')
    def test_different_map_or_k_rejected(self):
        changed=copy.deepcopy(self.record);changed['map_index']=2
        with self.assertRaises(ValueError):C.compare_values(self.record,changed,[1.],[1.])
        changed=copy.deepcopy(self.record);changed['kpoints'][0]=[.25,0,0]
        with self.assertRaises(ValueError):C.compare_values(self.record,changed,[1.],[1.])
    def test_density_failure_and_nan(self):
        self.assertEqual(C.compare_values(self.record,self.record,[1.,2.],[1.,2.1])['status'],'FAIL')
        with self.assertRaises(ValueError):C.compare_values(self.record,self.record,[1.],[float('nan')])
    def test_wrong_source_receipt_cannot_enter_array_pair(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();area=root/'.work/soc-timing';area.mkdir(parents=True)
            for task in ('T-B0-REF','T-B0-TIMED'):
                run_id=task+'-synthetic';directory=area/'runs'/run_id;(directory/'worker').mkdir(parents=True)
                worker=dict(run_id=run_id,task_id=task,execution_commit='a'*40,source_commit='b'*40,
                            exit_code=0,execution_status='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED')
                raw=json.dumps(worker).encode();(directory/'worker/result.json').write_bytes(raw)
                outer=dict(worker,worker_result_sha256=hashlib.sha256(raw).hexdigest())
                (directory/'result.json').write_text(json.dumps(outer))
                (area/(task+'-accepted.json')).write_text(json.dumps(dict(run_id=run_id,directory=str(directory),execution_commit='a'*40)))
            with self.assertRaisesRegex(ValueError,'source identity'):C.pair(root)

class SpanArithmetic(unittest.TestCase):
    def row(self,i,parent,start,end,self_ns):
        return dict(run_id='synthetic',pid=12,span_id=i,parent_span=parent,name='example',
                    map_index=0,k_index=0,start_offset_ns=start,end_offset_ns=end,
                    inclusive_ns=end-start,exclusive_ns=self_ns,calls=1,status='COMPLETE')
    def test_nested_not_double_counted(self):
        rows=[self.row(1,0,0,100,60),self.row(2,1,10,50,40)]
        self.assertEqual(R.spans(rows)['synthetic']['attributed_exclusive_ns'],100)
    def test_diagnostic_stop_is_closed_without_claiming_convergence(self):
        row=self.row(1,0,0,100,100);row['status']='DIAGNOSTIC_COMPLETED'
        self.assertEqual(R.spans([row])['synthetic']['attributed_exclusive_ns'],100)
    def test_wrong_self_and_missing_parent(self):
        with self.assertRaises(ValueError):R.spans([self.row(1,0,0,100,100),self.row(2,1,10,50,40)])
        with self.assertRaises(ValueError):R.spans([self.row(2,1,10,50,40)])
    def test_duplicate_or_overlapping_children(self):
        x=self.row(1,0,0,100,100)
        with self.assertRaises(ValueError):R.spans([x,x])
        with self.assertRaises(ValueError):R.spans([self.row(1,0,0,100,10),self.row(2,1,10,60,50),self.row(3,1,50,90,40)])

class BatchControl(unittest.TestCase):
    def test_sleep_and_backward_calendar_do_not_extend_budget(self):
        m=load('run');batch=dict(started_epoch=1000,started_monotonic_ns=1000000000)
        self.assertEqual(m.remaining(batch,now_epoch=2000,now_ns=11000000000),2600)
        self.assertEqual(m.remaining(batch,now_epoch=900,now_ns=1001000000000),2600)
    def test_failed_owned_launch_keeps_locks(self):
        m=load('run')
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                with m.locks(Path(d),'synthetic-run') as lease:
                    lease['launched']=True
                    raise RuntimeError('Synthetic unconfirmed cleanup')
            self.assertTrue((Path(d)/'.work/soc-timing/active.json').exists())
    def test_before_launch_failure_releases_only_owned_locks(self):
        m=load('run')
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                with m.locks(Path(d),'synthetic-run'):
                    raise RuntimeError('Synthetic preparation failure')
            self.assertFalse((Path(d)/'.work/soc-timing/active.json').exists())

if __name__=='__main__':unittest.main()
