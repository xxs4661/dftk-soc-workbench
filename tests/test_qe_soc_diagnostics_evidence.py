"""Synthetic publication receipts, distinct from real QE restart evidence."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from check_qe_soc_diagnostics import check_receipt, check_source_binding, check_native_execution, check, RESULTS
from run_qe_soc_diagnostics import object_hash, digest, write_json
from compare_qe_soc_diagnostics import payload_sha256
ROOT=Path(__file__).resolve().parents[1]


class ReceiptContract(unittest.TestCase):
    def setUp(self):
        self.plan=json.loads((ROOT/'benchmarks/mg-soc-qe-diagnostics-v1/plan.json').read_text())
        self.record={'slot':'D36','run_id':'synthetic-D36-receipt',
            'recorder_exit_code':0,
            'input_path':self.plan['slots']['D36']['input_path'],
            'input_sha256':self.plan['slots']['D36']['input_sha256'],
            'plan_sha256':'synthetic-hash','preflight':{'plan_sha256':'synthetic-hash','saved_utc':'2099-01-01T00:00:00Z'},
            'started_utc':'2099-01-01T00:01:00Z','finished_utc':'2099-01-01T00:02:00Z',
            'process_interrupted':False,'qe_identity':self.plan['qe_identity'],
            'pseudo_before_sha256':self.plan['pseudo']['sha256'],'pseudo_after_sha256':self.plan['pseudo']['sha256'],
            'source_preservation_status':'PASS',
            'thread_environment':{k:'1' for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','JULIA_NUM_THREADS')}}

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
                          ('pseudo_after_sha256','different'),('started_utc','2000-01-01'),
                          ('started_utc',None),('recorder_exit_code',9)]:
            with self.subTest(key=key):
                r=copy.deepcopy(self.record);r[key]=value
                with self.assertRaises(ValueError):check_receipt(self.plan,'D36',r)

    def test_launch_identity_not_just_version(self):
        r=copy.deepcopy(self.record);r['qe_identity']['binary_sha256']='changed'
        with self.assertRaises(ValueError):check_receipt(self.plan,'D36',r)

    def test_failed_receipt_is_retained_without_inventing_identity(self):
        r=copy.deepcopy(self.record)
        r.update(execution_status='FAIL',reason='synthetic startup failure',recorder_exit_code=9)
        r.pop('qe_identity')
        check_receipt(self.plan,'D36',r)
        r['recorder_exit_code']=0
        with self.assertRaises(ValueError):check_receipt(self.plan,'D36',r)

    def test_both_solvers_cannot_share_a_wrong_initial_snapshot(self):
        files={name:'a'*64 for name in ('charge-density.dat','wfc1.dat','wfc2.dat','wfc3.dat')}
        snapshots={'Q36':{'run_id':'synthetic-original','save_sha256':files}}
        binding={'source_run_id':'synthetic-original','source_slot':'Q36',
                 'source_snapshot_sha256':object_hash(files),'charge_before_sha256':'a'*64,
                 'charge_after_sha256':'a'*64,'initial_wfc_sha256':{p:h for p,h in files.items() if p.startswith('wfc')}}
        r={'execution_status':'PASS','source_binding':binding}
        check_source_binding('D36',r,snapshots)
        r['source_binding']['initial_wfc_sha256']['wfc1.dat']='b'*64
        for slot in ('D36','C36'):
            with self.assertRaises(ValueError):check_source_binding(slot,r,snapshots)

    def test_actual_parallelism_cannot_be_inferred_from_request(self):
        native='Parallel version (MPI), running on 1 processors\nMPI processes distributed on 1 nodes\na serial algorithm will be used'
        check_native_execution(native)
        with self.assertRaisesRegex(ValueError,'Native MPI process count'):
            check_native_execution(native.replace('1 processors','2 processors'))

    def test_scf_fresh_scratch_is_required(self):
        r=copy.deepcopy(self.record);cfg=self.plan['slots']['G40']
        r.update(slot='G40',run_id='synthetic-G40-receipt',input_path=cfg['input_path'],
                 input_sha256=cfg['input_sha256'],source_binding={'fresh_scratch':False})
        with self.assertRaisesRegex(ValueError,'Fresh initialization/SCF'):check_receipt(self.plan,'G40',r)


class PublicNativeContract(unittest.TestCase):
    """Historical/new native reparse plus deliberately corrupted public copies.

    No solver runs. The corrupt copies are test objects, not physical evidence.
    """
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        paths=subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT).decode().split('\0')
        for name in set(paths):
            if name and (ROOT/name).is_file():
                target=self.root/name;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/name,target)
        self.directory=self.root/RESULTS
        self.evidence=json.loads((self.directory/'evidence.json').read_text())

    def save_evidence(self):write_json(self.directory/'evidence.json',self.evidence)

    def test_all_native_reparse_without_private_prerequisites(self):
        for name in ('.work','.agent-work'):self.assertFalse((self.root/name).exists())
        self.assertEqual(check(self.root)['status'],'PASS')

    def test_ieee_stream_cannot_be_dropped_even_if_file_hash_is_refreshed(self):
        item=self.evidence['run_slots']['D36']['native_files']['stderr'];path=self.root/item['public_path']
        path.write_text('');item['public_sha256']=digest(path);self.evidence['public_sha256'][item['public_path']]=digest(path)
        self.save_evidence()
        with self.assertRaisesRegex(ValueError,'Canonical record differs'):check(self.root)

    def test_hybrid_numerical_payload_cannot_replace_raw_native(self):
        path=self.directory/'canonical.json';r=json.loads(path.read_text())
        r['D36']['kpoints'][0]['eigenvalues_ha'][0]=r['D40']['kpoints'][0]['eigenvalues_ha'][0]
        r['D36']['parsed_payload_sha256']=payload_sha256(r['D36'])
        write_json(path,r);self.evidence['public_sha256'][path.relative_to(self.root).as_posix()]=digest(path);self.save_evidence()
        with self.assertRaisesRegex(ValueError,'Canonical record differs'):check(self.root)

    def test_started_failed_slot_cannot_omit_native_bad_streams(self):
        receipt=self.evidence['run_slots']['C36'];receipt.update(execution_status='FAIL',reason='synthetic failure',recorder_exit_code=9)
        lost=receipt['native_files'].pop('stderr');self.evidence['public_sha256'].pop(lost['public_path']);(self.root/lost['public_path']).unlink()
        path=self.directory/'canonical.json';r=json.loads(path.read_text());r['C36']={'slot':'C36','run_id':receipt['run_id'],'execution_status':'FAIL','reason':'synthetic failure','exit_code':9};write_json(path,r)
        self.evidence['public_sha256'][path.relative_to(self.root).as_posix()]=digest(path);self.save_evidence()
        with self.assertRaisesRegex(ValueError,'Started run lost a native stream'):check(self.root)

    def test_missing_slot_cannot_be_replaced_by_previous_result(self):
        self.evidence['run_slots'].pop('C40');self.save_evidence()
        with self.assertRaisesRegex(ValueError,'Missing/extra slot receipt'):check(self.root)


if __name__=='__main__':unittest.main()
