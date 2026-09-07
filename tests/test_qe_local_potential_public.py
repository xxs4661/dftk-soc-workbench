"""Synthetic publication contracts; no pp execution or physical data evaluation."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import check_qe_local_potential as K
import compare_qe_local_potential as C
from test_qe_local_fields_replay import run_fixture
from test_qe_local_potential_comparison import fixture


def slot_fixture(root):
    directory=root/'results/mg-soc-qe-local-potential/P2';directory.mkdir(parents=True)
    inp=root/'benchmarks/mg-soc-qe-local-potential-v1/P2.in';inp.parent.mkdir(parents=True)
    inp.write_text("&INPUTPP\n plot_num=2,\n/\n")
    native=b'SYNTHETIC NONPHYSICAL FILPLOT RECEIPT BYTES\n'
    field=directory/'local-ionic.pp.gz';field.write_bytes(gzip.compress(native,mtime=0))
    (directory/'qe.stdout').write_text('Program POST-PROC v.7.5\n JOB DONE.\n')
    (directory/'qe.stderr').write_text('IEEE_OVERFLOW_FLAG\n')
    run='synthetic-P2-current';sha=hashlib.sha256(native).hexdigest();input_sha=K.digest(inp)
    spec={'run_id':run,'formal_call_count':1,'process_exit_code':0,'source_preservation_status':'PASS',
        'input_sha256':input_sha,'filplot_raw_sha256':sha,'receipt_path':str((directory/'receipt.json').relative_to(root))}
    state=dict(spec,slot='P2',schema_version=1,source_run_id=K.G40,execution_status='PASS',postprocessing_status='PASS',
        parse_status='PASS',exit_code=0,copied_files_preservation_status='PASS',filplot_sha256=sha,
        stdout_sha256=K.digest(directory/'qe.stdout'),stderr_sha256=K.digest(directory/'qe.stderr'),
        warnings={'stdout':{'ieee_flags':[]},'stderr':{'ieee_flags':['IEEE_OVERFLOW_FLAG']}},
        field_provenance='QE_PP_RECONSTRUCTION_BOUND_TO_HISTORICAL_G40',
        qe_historical_in_memory_vloc_status='NOT_EXTRACTED',qe_internal_tab_vloc_status='NOT_EXTRACTED')
    identity={'single_thread_environment':{'OMP_NUM_THREADS':'1'},'source':'synthetic identity only'}
    plan={'slots':{'P2':{'input_path':str(inp.relative_to(root)),'input_sha256':input_sha}},
          'source_files':{'scratch/mg_soc_qe_v1.save/'+name:{'sha256':'1'*64} for name in ('Mg.upf','charge-density.dat','data-file-schema.xml')},'qe_identity':identity}
    evidence={'plan_sha256':'2'*64,'preparation_commit':'3'*40,'execution_commit':'4'*40,
        'execution_source_sha256':{'scripts/example.py':'5'*64},'P2_path':str(field.relative_to(root)),
        'public_sha256':{str((directory/name).relative_to(root)):K.digest(directory/name) for name in ('qe.stdout','qe.stderr')}}
    pre={'run_id':run,'slot':'P2','source_run_id':K.G40,'plan_sha256':evidence['plan_sha256'],
        'preparation_commit':evidence['preparation_commit'],'execution_commit':evidence['execution_commit'],
        'source_files':plan['source_files'],'qe_identity':identity,'environment':identity['single_thread_environment'],
        'copy_sha256_before':{**{k:v['sha256'] for k,v in plan['source_files'].items()},'pseudo/Mg.upf':'1'*64},
        'field_provenance':state['field_provenance'],'input_sha256':input_sha,'output_absent_before':True,
        'execution_source_sha256':evidence['execution_source_sha256']}
    receipt={'schema_version':1,'state':state,'preflight':pre,'preservation':{'status':'PASS','source_run_id':K.G40,
        'source_changes':{},'copy_changes':{}}}
    return spec,receipt,plan,evidence


class PublicContractTests(unittest.TestCase):
    def test_native_gzip_hash_and_honest_warning_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);spec,r,p,e=slot_fixture(root)
            out=K.validate_slot(root,'P2',spec,r,p,e)
            self.assertEqual(out['formal_call_count'],1)
            self.assertEqual(out['status'],'PASS')
            self.assertIn('IEEE_OVERFLOW_FLAG',(root/'results/mg-soc-qe-local-potential/P2/qe.stderr').read_text())

    def test_lossless_stdout_gzip_preserves_native_spaces_and_receipt_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);spec,r,p,e=slot_fixture(root)
            native=root/'results/mg-soc-qe-local-potential/P2/qe.stdout'
            raw=b'Program POST-PROC v.7.5   \n JOB DONE.  \n'
            r['state']['stdout_sha256']=hashlib.sha256(raw).hexdigest()
            compressed=native.with_name(native.name+'.gz');compressed.write_bytes(gzip.compress(raw,mtime=0))
            native.unlink();del e['public_sha256'][str(native.relative_to(root))]
            e['public_sha256'][str(compressed.relative_to(root))]=K.digest(compressed)
            self.assertEqual(K.raw_bytes(compressed),raw)
            self.assertEqual(K.raw_digest(compressed),r['state']['stdout_sha256'])
            self.assertEqual(K.validate_slot(root,'P2',spec,r,p,e)['status'],'PASS')

    def test_plain_and_gzip_native_stream_together_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);spec,r,p,e=slot_fixture(root)
            native=root/'results/mg-soc-qe-local-potential/P2/qe.stdout'
            compressed=native.with_name(native.name+'.gz');compressed.write_bytes(gzip.compress(native.read_bytes(),mtime=0))
            e['public_sha256'][str(compressed.relative_to(root))]=K.digest(compressed)
            with self.assertRaisesRegex(ValueError,'ambiguous native stream'):
                K.validate_slot(root,'P2',spec,r,p,e)

    def test_nonzero_false_exit_multiple_calls_and_old_output_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);spec,r,p,e=slot_fixture(root)
            variants=[]
            for key,value in [('process_exit_code',1),('process_exit_code',False),('formal_call_count',0),('formal_call_count',2),('execution_status','FAIL')]:
                bad=copy.deepcopy(r);bad['state'][key]=value;variants.append(bad)
            bad=copy.deepcopy(r);bad['preflight']['output_absent_before']=False;variants.append(bad)
            for bad in variants:
                with self.assertRaises(ValueError):K.validate_slot(root,'P2',spec,bad,p,e)

    def test_wrong_run_or_D40_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);spec,r,p,e=slot_fixture(root)
            for section,key,value in [('state','run_id','synthetic-old'),('preflight','source_run_id','D40-bands'),
                                      ('preflight','slot','P0'),('preflight','execution_commit','a'*40)]:
                bad=copy.deepcopy(r);bad[section][key]=value
                with self.assertRaises(ValueError):K.validate_slot(root,'P2',spec,bad,p,e)

    def test_changed_original_or_copy_cannot_be_hidden_by_PASS(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);spec,r,p,e=slot_fixture(root)
            for key in ('source_changes','copy_changes'):
                bad=copy.deepcopy(r);bad['preservation'][key]={'charge-density.dat':{'before':'a','after':'b'}}
                with self.assertRaisesRegex(ValueError,'changes'):K.validate_slot(root,'P2',spec,bad,p,e)

    def test_raw_native_byte_change_or_stream_hash_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);spec,r,p,e=slot_fixture(root)
            path=root/e['P2_path'];path.write_bytes(gzip.compress(b'CHANGED SAME RUN',mtime=0))
            with self.assertRaisesRegex(ValueError,'filplot'):K.validate_slot(root,'P2',spec,r,p,e)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);spec,r,p,e=slot_fixture(root)
            (root/'results/mg-soc-qe-local-potential/P2/qe.stderr').write_text('')
            with self.assertRaisesRegex(ValueError,'stream'):K.validate_slot(root,'P2',spec,r,p,e)

    def test_input_and_build_identity_mismatches_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);spec,r,p,e=slot_fixture(root)
            for key,value in [('input_sha256','0'*64),('qe_identity',{'single_thread_environment':{'OMP_NUM_THREADS':'8'}}),
                              ('execution_source_sha256',{'scripts/example.py':'0'*64})]:
                bad=copy.deepcopy(r);bad['preflight'][key]=value
                with self.assertRaises(ValueError):K.validate_slot(root,'P2',spec,bad,p,e)

    def test_copy_digest_and_recorded_warning_cannot_be_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);spec,r,p,e=slot_fixture(root)
            bad=copy.deepcopy(r);bad['preflight']['copy_sha256_before']['pseudo/Mg.upf']='0'*64
            with self.assertRaisesRegex(ValueError,'copy hashes'):K.validate_slot(root,'P2',spec,bad,p,e)
            bad=copy.deepcopy(r);bad['state']['warnings']['stderr']['ieee_flags']=[]
            with self.assertRaisesRegex(ValueError,'IEEE'):K.validate_slot(root,'P2',spec,bad,p,e)

    def test_missing_completion_or_unexpected_solver_output_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);spec,r,p,e=slot_fixture(root)
            path=root/'results/mg-soc-qe-local-potential/P2/qe.stdout'
            for text in ('Program POST-PROC v.7.5\n','Program POST-PROC v.7.5\n iteration # 1\nJOB DONE.\n'):
                path.write_text(text);bad=copy.deepcopy(r);bad['state']['stdout_sha256']=K.digest(path)
                with self.assertRaises(ValueError):K.validate_slot(root,'P2',spec,bad,p,e)

    def test_private_traversal_and_symlink_are_not_public_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for path in ('.work/secret','/private/tmp/no','../outside','results/../../outside'):
                with self.assertRaises(ValueError):K.public_path(root,path)
            (root/'link').symlink_to('/private/tmp')
            with self.assertRaises(ValueError):K.public_path(root,'link/secret')

    def test_saved_scope_and_derived_remainder_are_validated(self):
        result=run_fixture(fixture());K.validate_comparison(result)
        for key,value in [('Q_TNL_record_kind','DIRECT_OPERATOR_MEASUREMENT'),('native_E_F_modified',True),
                          ('physical_convergence_status','PASS'),('qe_internal_tab_vloc_status','EXTRACTED'),
                          ('new_scf_status','PASS'),('P0_density_registration_status','FAIL')]:
            bad=copy.deepcopy(result);bad['comparison'][key]=value
            with self.assertRaises(ValueError):K.validate_comparison(bad)

    def test_missing_phase_check_or_original_public_relabel_fails(self):
        result=run_fixture(fixture())
        for action in ('missing','failure','original'):
            bad=copy.deepcopy(result)
            if action=='missing':bad['p0_phase_checks'].pop()
            if action=='failure':bad['p0_phase_checks'][0]['status']='FAIL'
            if action=='original':bad['density_integral_source']='ORIGINAL_ARCHIVED_ARRAYS'
            with self.assertRaises(ValueError):K.validate_comparison(bad)

    def test_tiny_print_bound_cannot_be_doubled_under_large_absolute_tolerance(self):
        good={'quantization':{'u_L_Q_ha':2e-10},'energy':-70.}
        K.equivalent(good,copy.deepcopy(good),C.DEFAULT_THRESHOLDS)
        bad=copy.deepcopy(good);bad['quantization']['u_L_Q_ha']*=2
        with self.assertRaisesRegex(ValueError,'numeric'):K.equivalent(good,bad,C.DEFAULT_THRESHOLDS)
        bad=copy.deepcopy(good);bad['energy']+=1e-7
        with self.assertRaisesRegex(ValueError,'numeric'):K.equivalent(good,bad,C.DEFAULT_THRESHOLDS)

    def test_scalar_count_status_fields_cannot_change_types(self):
        for bad in ({'count':True},{'count':2},{'count':'1'}):
            with self.assertRaises(ValueError):K.equivalent({'count':1},bad,C.DEFAULT_THRESHOLDS)

    def test_git_version_helper_requires_exact_commit_and_propagates_missing_blob(self):
        with self.assertRaisesRegex(ValueError,'Exact commit'):K._git_bytes(Path('.'),'HEAD','scripts/a.py')
        with mock.patch.object(K.subprocess,'check_output',return_value=b'bound source') as call:
            self.assertEqual(K._git_bytes(Path('.'),'a'*40,'scripts/a.py'),b'bound source')
            self.assertIn('a'*40+':scripts/a.py',call.call_args.args[0])

    def field_fixture(self):
        common={'environment':{'status':'PASS','julia_version':'1.12.7'},'constants':{'model_ne':10}}
        prior={'run_id':'historical-7D','execution_commit':'b'*40,'backup':{'status':'PASS'},
            'execution_source_sha256':{'scripts/evaluate_common_energy_terms.jl':'c'*64},
            'execution_logs':{'common/arrays.bin':'1'*64,'common/metadata.json':'2'*64,'result.json':'3'*64}}
        plan={'julia_version':'1.12.7','dftk_source_run_id':'historical-7D'}
        evidence={'field_run_id':'current-field-only','execution_commit':'a'*40,'plan_sha256':'4'*64,
            'execution_source_sha256':{K.FIELD_SCRIPT:'5'*64}}
        receipt={'schema_version':1,'execution_status':'PASS','exit_code':0,'source_preservation_status':'PASS',
            'run_id':evidence['field_run_id'],'execution_commit':evidence['execution_commit'],'plan_sha256':evidence['plan_sha256'],
            'executed_script_sha256':'5'*64,'environment':common['environment'],'constants':common['constants'],
            'outputs_local_sha256':{'native':'7'*64},'original_array_scope':'ORIGINAL_ARCHIVED_ARRAYS; synthetic receipt only',
            'source_binding':{'source_evidence_path':'results/mg-soc-energy-reference/evidence.json','source_evidence_sha256':'6'*64,
                'source_run_id':prior['run_id'],'source_execution_commit':prior['execution_commit'],'arrays_sha256':'1'*64,
                'metadata_sha256':'2'*64,'receipt_sha256':'3'*64,'producer_script_sha256':'c'*64,
                'production_julia_version':'1.12.7','historical_archive':prior['backup']}}
        return receipt,evidence,plan,prior,common

    def test_wrong_7D_source_or_loaded_environment_rejected(self):
        r,e,p,h,c=self.field_fixture();K.validate_field_binding(r,e,p,h,c,'6'*64,'7'*64)
        for key,value in [('source_run_id','unrelated-40cubed'),('arrays_sha256','f'*64),('metadata_sha256','f'*64),
                          ('receipt_sha256','f'*64),('source_execution_commit','f'*40)]:
            bad=copy.deepcopy(r);bad['source_binding'][key]=value
            with self.assertRaises(ValueError):K.validate_field_binding(bad,e,p,h,c,'6'*64,'7'*64)
        bad=copy.deepcopy(r);bad['environment']['julia_version']='1.12.8'
        with self.assertRaisesRegex(ValueError,'environment'):K.validate_field_binding(bad,e,p,h,c,'6'*64,'7'*64)

    def test_D_columns_reconstruct_exact_native_strings_and_order(self):
        header='m1,m2,m3,V_D_real,V_D_imag,V_Qpp_real,V_Qpp_imag\n'
        rows='0,0,0,-0.0,0.0,0.5,0.0\n1,0,0,0.12,-0.03,0.0,0.0\n'
        expected='m1,m2,m3,V_D_real,V_D_imag\n0,0,0,-0.0,0.0\n1,0,0,0.12,-0.03\n'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'field.csv.gz';p.write_bytes(gzip.compress((header+rows).encode(),mtime=0))
            sha=hashlib.sha256(expected.encode()).hexdigest();self.assertEqual(K.dftk_export_digest(p),sha)
            p.write_bytes(gzip.compress((header+rows.replace('-0.0','0.0')).encode(),mtime=0))
            self.assertNotEqual(K.dftk_export_digest(p),sha)

    def test_different_D_field_with_refreshed_public_hash_still_fails_native_receipt(self):
        r,e,p,h,c=self.field_fixture()
        with self.assertRaisesRegex(ValueError,'whole native export'):
            K.validate_field_binding(r,e,p,h,c,'6'*64,'8'*64)
        bad=copy.deepcopy(r);bad['executed_script_sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'executed script'):K.validate_field_binding(bad,e,p,h,c,'6'*64,'7'*64)


if __name__=='__main__':unittest.main()
