"""Synthetic public protocol/arithmetic tests, no material or private arrays."""
import copy
import gzip
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'benchmarks/soc-boundary-v1/replay.py';s=importlib.util.spec_from_file_location('boundary_replay_tests',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class PublicBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.dir=Path(self.tmp.name)
        self.c=ROOT/'benchmarks/soc-boundary-v1/contract.json';self.E='a'*40
        self.rec=dict(schema_version=1,experiment='soc-boundary-v1',contract_sha256=m.sha(self.c),execution_commit=self.E,runs=[],pairs={},protection_status='PASS',public_files_sha256={})
        self.data={}
        for task in m.TASKS:
            opt=task.endswith('OPT');nk=64 if '-K4-' in task else 8;run='synthetic-'+task
            ident=dict(task_id=task,run_id=run,source_commit=self.E if opt else m.R,execution_commit=self.E,case_sha256='c'*64)
            r=dict(**ident,timing_enabled=True,validation_policy='single_validation_v1' if opt else 'strict',execution_status='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED',native_exit_code=0,worker_exit_code=0,recorder_exit_code=0,completed_maps=2,runtime_closed=True,workspace_released=True,owned_process_cleanup_status='PASS',limit_bytes=8*1024**3,warning_bytes=7*1024**3,remaining_growth_bytes=2*1024**3,final_bin_present=False,monitor_wall_seconds=6 if opt else 12)
            self.rec['runs'].append(r);axis=(0.,.5) if nk==8 else (0.,.25,.5,.75);coords=[list(x) for x in itertools.product(axis,repeat=3)]
            maps=[dict(**ident,map_index=i,kpoints=coords,eigenvalues_ha=[[j/32 for j in range(24)] for k in coords],occupations=[[1.]*8+[0.]*16 for k in coords],internal_energy_ha=-8-i/32,free_energy_ha=-8-i/32) for i in (1,2)]
            total=5 if opt else 10;validation=4 if opt else 8
            spans=[dict(run_id=run,pid=1,span_id=1,parent_span=0,map_index=0,k_index=0,name='worker_total',start_offset_ns=0,end_offset_ns=total*10**9,inclusive_ns=total*10**9,exclusive_ns=(total-validation)*10**9,calls=1,status='COMPLETE'),dict(run_id=run,pid=1,span_id=2,parent_span=1,map_index=0,k_index=0,name='runtime_boundary_entry',start_offset_ns=0,end_offset_ns=validation*10**9,inclusive_ns=validation*10**9,exclusive_ns=validation*10**9,calls=1,status='COMPLETE')]
            self.data[task]={'maps':maps,'spans':spans}
        for profile,nk in [('B0',8),('K4',64)]:
            a,b='V-'+profile+'-REF','V-'+profile+'-OPT';rows=[]
            for x,y in zip(self.data[a]['maps'],self.data[b]['maps']):
                rows.append(dict(**m.compare_maps(x,y,nk),density_relative_l2=0.,density_difference_norm=0.,density_reference_norm=2.,density_candidate_norm=2.,density_denominator=2.,status='PASS'))
            self.rec['pairs'][profile]=dict(execution_commit=self.E,run_ids=['synthetic-'+a,'synthetic-'+b],maps=rows,status='PASS')
    def save(self):
        raw=gzip.compress(json.dumps(self.data).encode(),mtime=0);(self.dir/'data.json.gz').write_bytes(raw);self.rec['public_files_sha256']['data.json.gz']=hashlib.sha256(raw).hexdigest()
        proof=gzip.compress(json.dumps({'status':self.rec['protection_status'],'checks':[{'command':['SYNTHETIC'],'exit_code':0}]}).encode(),mtime=0)
        (self.dir/'protection.json.gz').write_bytes(proof);self.rec['public_files_sha256']['protection.json.gz']=hashlib.sha256(proof).hexdigest();(self.dir/'runs.json').write_text(json.dumps(self.rec))
    def replay(self):self.save();return m.replay(self.dir)
    def test_complete_synthetic_replay(self):
        r=self.replay();self.assertEqual(r['strict_optimization_status'],'PASS');self.assertEqual(r['performance']['validation_ratio'],.5)
    def test_performance_failure_is_not_protocol_failure(self):
        self.rec['runs'][-1]['monitor_wall_seconds']=11;r=self.replay();self.assertEqual(r['replay_status'],'PASS');self.assertEqual(r['strict_optimization_status'],'NOT_ACCEPTED');self.assertEqual(r['performance']['status'],'PERFORMANCE_TARGET_NOT_MET')
        self.assertEqual(subprocess.run([sys.executable,'-B',str(p),'--results',str(self.dir),'--strict'],capture_output=True).returncode,1)
        self.assertEqual(subprocess.run([sys.executable,'-B',str(p),'--results',str(self.dir)],capture_output=True).returncode,0)
    def test_protection_failure_not_masked_by_numeric(self):
        self.rec['protection_status']='FAIL';self.assertEqual(self.replay()['strict_optimization_status'],'NOT_ACCEPTED')
    def test_missing_slot_not_accepted(self):
        r=self.rec['runs'][-1];r.update(execution_status='BLOCKED_PARENT',native_exit_code=None);self.data[r['task_id']]={'maps':[],'spans':[]};self.assertEqual(self.replay()['performance']['status'],'NOT_ASSESSED')
    def test_wrong_reference_rejected(self):
        self.rec['runs'][0]['source_commit']=self.E
        with self.assertRaisesRegex(ValueError,'source'):self.replay()
    def test_reference_timer_must_be_on(self):
        self.rec['runs'][0]['timing_enabled']=False
        with self.assertRaisesRegex(ValueError,'timing'):self.replay()
    def test_duplicate_missing_k_rejected(self):
        for nk,task in [(8,'V-B0-REF'),(64,'V-K4-REF')]:
            original=copy.deepcopy(self.data[task]);self.data[task]['maps'][0]['kpoints'][1]=self.data[task]['maps'][0]['kpoints'][0]
            with self.assertRaisesRegex(ValueError,'k coordinates'):self.replay()
            self.data[task]=original
    def test_reordered_k_matches_coordinates(self):
        d=self.data['V-K4-OPT']['maps'][0]
        for name in ('kpoints','eigenvalues_ha','occupations'):d[name]=list(reversed(d[name]))
        self.assertEqual(self.replay()['pairs']['K4']['status'],'PASS')
    def test_nonfinite_or_wrong_band_count(self):
        a=self.data['V-B0-OPT']['maps'][0]['eigenvalues_ha'][0];a.pop()
        with self.assertRaisesRegex(ValueError,'24 finite'):self.replay()
    def test_electron_count_fixed(self):
        self.data['V-B0-OPT']['maps'][0]['occupations'][0][0]=0.
        with self.assertRaisesRegex(ValueError,'electron'):self.replay()
    def test_stored_error_not_trusted(self):
        self.rec['pairs']['B0']['maps'][0]['raw_level_rms_ha']=1e-8
        with self.assertRaisesRegex(ValueError,'arithmetic'):self.replay()
    def test_density_denominator_not_tuned(self):
        self.rec['pairs']['B0']['maps'][0]['density_denominator']=3.
        with self.assertRaisesRegex(ValueError,'denominator'):self.replay()
    def test_unclassified_new_cost_rejected(self):
        self.data['V-K4-OPT']['spans'][1]['name']='new_free_cache_cost'
        with self.assertRaisesRegex(ValueError,'Unclassified'):self.replay()
    def test_child_time_not_double_counted(self):
        r=self.replay();t=r['timing']['synthetic-V-K4-REF'];self.assertEqual(t['worker_span_seconds'],10);self.assertEqual(t['validation_total_seconds'],8)
    def test_final_bin_cannot_be_published(self):
        self.rec['runs'][1]['final_bin_present']=True
        with self.assertRaisesRegex(ValueError,'checkpoint'):self.replay()
    def test_byte_identity_required(self):
        self.save();(self.dir/'data.json.gz').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Public bytes'):m.replay(self.dir)
    def test_changed_contract_rejected(self):
        self.rec['contract_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'contract'):self.replay()
    def test_exit_code_contradiction_rejected(self):
        self.rec['runs'][1]['native_exit_code']=1
        with self.assertRaisesRegex(ValueError,'exit codes'):self.replay()

if __name__=='__main__':unittest.main()
