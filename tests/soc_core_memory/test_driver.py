"""Synthetic Phase9A driver/gate protocols; no Julia, SCF or real arrays are run."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import run_si_dftk as driver

HEAD='a'*40
GATE='b'*64
SUITES=('REF-B0','REF-K4','CORE-B0','CORE-K4')

class CoreDriverTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name).resolve()
        self.area=self.root/'.work/phase9a';self.area.mkdir(parents=True)
        self.case=self.root/'benchmarks/si-soc-splitting-v1/case.json';self.case.parent.mkdir(parents=True);self.case.write_text('{}\n')
        self.depot=self.root/'synthetic-existing-cache';self.depot.mkdir()
        self.tool=types.SimpleNamespace(SUITES=SUITES,read=lambda p:json.loads(p.read_text()),prior_contract=Mock(),preparation=Mock(),
            ps_rows=Mock(return_value=[]),execute=Mock(),monitored_execute=Mock(),resource_contract=Mock())
        self.addCleanup(patch.stopall)
        patch.object(driver,'core_tools',return_value=self.tool).start()

    def write(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,allow_nan=False)+'\n');return path

    def gate(self):
        gate=dict(schema_version=1,phase='9A',execution_commit=HEAD,overall_status='PASS',exit_code=0,
            time_status='PERFORMANCE_REVIEW_REQUIRED',suite_receipts={})
        for name in ('identity_status','equivalence_status','allocation_status','resource_status','live_storage_reduction_status'):gate[name]='PASS'
        for name in SUITES:
            record=self.write(self.area/'static'/name/'result.json',dict(suite=name,execution_commit=driver.CORE_REFERENCE_EXECUTION if name.startswith('REF-') else HEAD))
            gate['suite_receipts'][name]=dict(path=record.relative_to(self.root).as_posix(),sha256=driver.digest(record))
        for label in ('comparison','performance'):
            record=self.write(self.area/(label+'.json'),dict(schema_version=1,phase='9A',execution_commit=HEAD,overall_status='PASS',exit_code=0))
            gate[label]=dict(path=record.relative_to(self.root).as_posix(),sha256=driver.digest(record))
        return self.write(self.area/'gate.json',gate)

    def worker(self,action='OPT-B0-SCF',name='synthetic-dftk'):
        value=dict(schema_version=1,phase='9A',backend='soc-core',case='si-soc-splitting-v1',action=action,run_id=name,
            execution_commit=HEAD,core_gate_sha256=GATE,base_commit=driver.CORE_BASE,preparation_commit=driver.CORE_PREPARATION,
            execution_status='PASS',exit_code=0,environment={'status':'PASS'},input={'element':'Si','nlcc_present':True},grid={'status':'PASS'},
            case_sha256=driver.digest(self.case),runtime_closed=True,runtime_dispatch_status='PASS',
            runtime={'backend':'soc-core','closed':False,'max_rhs':30,'counters':{'fr_mul_calls':2,'component_mul_calls':2,'full_mul_calls':2}},
            runtime_after_close={'closed':True,'owned_source_entries':0,'workspace_released':True},
            final={'map_count':180},checkpoint_sha256='c'*64)
        if action=='OPT-B0-GAMMA':
            value.update(time_reversal={'status':'PASS'},source_scf_run_id='own-scf-dftk',density_source_sha256='d'*64)
            value['spectrum']=dict(execution_status='PASS',process_exit_code=0,physical_operator='full_soc',backend='soc-core',temperature_ha=.001,
                occupations_use='DIAGNOSTIC_ONLY_NOT_DENSITY_FEEDBACK',source_scf_run_id=value['source_scf_run_id'],density_source_sha256=value['density_source_sha256'],
                kpoints=[dict(coordinate_fractional=[0.,0.,0.],weight_spatial=1.,eigenvalues_ha=list(range(24)),residuals_ha=[0.]*24)])
        return value

    def validate(self,value,code=0):
        return driver.validate_core_worker(value,code,value['action'],value['run_id'],root=self.root,execution_commit=HEAD,gate_sha256=GATE)

    def setup_launch(self):
        patch.object(driver,'verify_preparation',return_value={'sha256':'c'*64}).start()
        patch.object(driver,'verify_core_gate',return_value=GATE).start()
        patch.dict(driver.os.environ,{'JULIA_DEPOT_PATH':str(self.depot)}).start()
        patch.object(driver.subprocess,'check_output',side_effect=lambda cmd,**kw: HEAD+'\n' if 'rev-parse' in cmd else '').start()

    def launch(self,name='new',action='OPT-B0-SCF',**extra):
        return driver.launch(action,self.area/'endpoints'/name,root=self.root,backend='soc-core',execution_commit=HEAD,core_gate=self.area/'gate.json',**extra)

    def fake_monitor(self,code=0,resource_ok=True):
        def invoke(execute,command,directory,environment):
            self.assertEqual(command[0],'julia');self.assertEqual(environment['SOC_CORE_PYTHON'],sys.executable)
            self.assertEqual(command[-4:-1],['--backend','soc-core','--core-gate'])
            resource=dict(status='PASS' if resource_ok else 'RESOURCE_BLOCKED',owned_process_cleanup_status='PASS',native_exit_code=code,
                          peak_aggregate_rss_bytes=100,nonempty_samples=1)
            self.write(directory/'resource.json',resource);self.write(directory/'process-exit.json',dict(exit_code=code,interrupted=False))
            self.write(directory/'process-start.json',dict(command=command))
            if code==0:
                worker=directory/(directory.name+'-dftk');worker.mkdir()
                value=self.worker(name=worker.name);(worker/'final.bin').write_bytes(b'synthetic transport, not physical data')
                value['checkpoint_sha256']=driver.digest(worker/'final.bin');self.write(worker/'result.json',value)
            return code,resource
        self.tool.monitored_execute.side_effect=invoke
        self.tool.resource_contract.side_effect=lambda resource,code: driver.require(resource['status']=='PASS' and code==0,'synthetic resource failure')

    def test_gate_delegates_all_four_complete_suite_checks(self):
        p=self.gate();self.assertEqual(driver.verify_core_gate(self.root,p,HEAD),driver.digest(p))
        self.assertEqual(self.tool.prior_contract.call_count,4)

    def test_time_review_is_retained_and_not_a_hard_failure(self):
        p=self.gate();driver.verify_core_gate(self.root,p,HEAD)
        self.assertEqual(json.loads(p.read_text())['time_status'],'PERFORMANCE_REVIEW_REQUIRED')

    def test_each_hard_gate_failure_rejected(self):
        for key in ('identity_status','equivalence_status','allocation_status','resource_status','live_storage_reduction_status'):
            p=self.gate();d=json.loads(p.read_text());d[key]='REVIEW_REQUIRED';self.write(p,d)
            with self.subTest(key=key),self.assertRaises(ValueError):driver.verify_core_gate(self.root,p,HEAD)

    def test_commit_must_be_exact_current_sha(self):
        p=self.gate()
        for head in ('HEAD','--help','a'*39,'b'*40):
            with self.subTest(head=head),self.assertRaises(ValueError):driver.verify_core_gate(self.root,p,head)

    def test_schema_and_exit_boolean_rejected(self):
        for key,value in (('schema_version',True),('schema_version',999),('exit_code',False),('overall_status','FAIL')):
            p=self.gate();d=json.loads(p.read_text());d[key]=value;self.write(p,d)
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):driver.verify_core_gate(self.root,p,HEAD)

    def test_missing_suite_and_wrong_reference_execution_rejected(self):
        p=self.gate();d=json.loads(p.read_text());del d['suite_receipts']['REF-K4'];self.write(p,d)
        with self.assertRaises(ValueError):driver.verify_core_gate(self.root,p,HEAD)
        p=self.gate();d=json.loads(p.read_text());entry=d['suite_receipts']['REF-B0'];r=self.root/entry['path'];self.write(r,dict(suite='REF-B0',execution_commit=HEAD));entry['sha256']=driver.digest(r);self.write(p,d)
        with self.assertRaises(ValueError):driver.verify_core_gate(self.root,p,HEAD)

    def test_complete_suite_validator_failure_propagates(self):
        p=self.gate();self.tool.prior_contract.side_effect=ValueError('synthetic missing sample or changed canonical output')
        with self.assertRaisesRegex(ValueError,'missing sample'):driver.verify_core_gate(self.root,p,HEAD)

    def test_hashed_comparison_and_performance_cannot_be_replaced(self):
        for label in ('comparison','performance'):
            p=self.gate();d=json.loads(p.read_text());(self.root/d[label]['path']).write_text('{}')
            with self.subTest(label=label),self.assertRaises(ValueError):driver.verify_core_gate(self.root,p,HEAD)

    def test_source_path_escape_and_symlink_rejected(self):
        p=self.gate();link=self.area/'link.json';link.symlink_to(p)
        with self.assertRaises(ValueError):driver.verify_core_gate(self.root,link,HEAD)
        with self.assertRaises(ValueError):driver.core_file(self.root,'.work/phase9a/../phase8a/old.json')

    def test_explicit_owned_scf_and_gamma_worker(self):
        self.validate(self.worker());self.validate(self.worker('OPT-B0-GAMMA'))

    def test_label_without_actual_dispatch_or_cleanup_rejected(self):
        for key,value in [('backend','legacy'),('runtime_dispatch_status','NOT_RUN'),('runtime_closed',False)]:
            r=self.worker();r[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate(r)
        for key in ('fr_mul_calls','component_mul_calls','full_mul_calls'):
            r=self.worker();r['runtime']['counters'][key]=0
            with self.subTest(counter=key),self.assertRaises(ValueError):self.validate(r)
        r=self.worker();r['runtime_after_close']['workspace_released']=False
        with self.assertRaises(ValueError):self.validate(r)

    def test_gamma_one_point_same_source_mu_diagnostic_protocol(self):
        for edit in ('three_points','wrong_weight','wrong_point','wrong_density','wrong_mode'):
            r=self.worker('OPT-B0-GAMMA');s=r['spectrum']
            if edit=='three_points':s['kpoints']*=3
            if edit=='wrong_weight':s['kpoints'][0]['weight_spatial']=.125
            if edit=='wrong_point':s['kpoints'][0]['coordinate_fractional']=[.1,0,0]
            if edit=='wrong_density':s['density_source_sha256']='e'*64
            if edit=='wrong_mode':s['occupations_use']='DENSITY_FEEDBACK'
            with self.subTest(edit=edit),self.assertRaises(ValueError):self.validate(r)

    def test_valid_native_worker_failure_keeps_its_code(self):
        r=self.worker();r.update(exit_code=7,execution_status='FAIL',reason='synthetic solver failure')
        self.validate(r,7)
        with self.assertRaises(ValueError):self.validate(r,0)

    def test_opt_in_does_not_accept_legacy_action_or_profile(self):
        with self.assertRaises(ValueError):self.launch(profile='K4')
        self.setup_launch();self.assertEqual(self.launch(action='D-SCF'),9)
        self.tool.monitored_execute.assert_not_called()

    def test_old_default_prepare_contract_still_accepted(self):
        r=self.worker();r['action']='prepare';driver.validate_worker(r,0,'prepare',r['run_id'])

    def test_failed_gate_no_claim_or_worker_and_current_failure(self):
        self.setup_launch();driver.verify_core_gate.side_effect=ValueError('synthetic allocation gate FAIL')
        self.assertEqual(self.launch(),9);p=self.area/'endpoints/new'
        r=json.loads((p/'receipt.json').read_text());self.assertEqual(r['execution_status'],'FAIL');self.assertFalse(r['worker_started'])
        self.assertFalse((p.parent/'slots/OPT-B0-SCF.json').exists());self.tool.monitored_execute.assert_not_called()

    def test_missing_gamma_parent_is_blocked_before_worker(self):
        self.setup_launch();self.assertEqual(self.launch(action='OPT-B0-GAMMA'),9)
        r=json.loads((self.area/'endpoints/new/receipt.json').read_text())
        self.assertEqual(r['failure_status'],'BLOCKED_PARENT');self.assertFalse(r['worker_started']);self.tool.monitored_execute.assert_not_called()

    def test_missing_cache_and_observer_fail_before_slot_claim(self):
        self.setup_launch()
        with patch.dict(driver.os.environ,{'JULIA_DEPOT_PATH':''}):self.assertEqual(self.launch('cache'),9)
        self.assertFalse((self.area/'endpoints/slots').exists())
        self.tool.ps_rows.side_effect=PermissionError('synthetic unavailable observer');self.assertEqual(self.launch('observer'),9)
        self.assertFalse((self.area/'endpoints/slots').exists());self.tool.monitored_execute.assert_not_called()

    def test_native_failure_exit_retained_and_attempt_never_retried(self):
        self.setup_launch();self.fake_monitor(code=7);self.assertEqual(self.launch(),9)
        r=json.loads((self.area/'endpoints/new/receipt.json').read_text());self.assertEqual(r['worker_exit_code'],7)
        self.assertEqual(self.launch('retry'),9);self.assertEqual(self.tool.monitored_execute.call_count,1)
        self.assertTrue((self.area/'endpoints/slots/OPT-B0-SCF.json').exists())

    def test_native_zero_resource_failure_never_produces_outer_pass(self):
        self.setup_launch();self.fake_monitor(resource_ok=False);self.assertEqual(self.launch(),9)
        p=self.area/'endpoints/new';r=json.loads((p/'receipt.json').read_text())
        self.assertEqual(r['worker_exit_code'],0);self.assertEqual(r['execution_status'],'FAIL')
        with self.assertRaises(ValueError):driver.checked_core_parent(p,root=self.root,execution_commit=HEAD,gate_sha256=GATE)

    def test_same_execution_successful_parent_and_tampered_checkpoint(self):
        self.setup_launch();self.fake_monitor();self.assertEqual(self.launch(),0)
        p=self.area/'endpoints/new';worker=driver.checked_core_parent(p,root=self.root,execution_commit=HEAD,gate_sha256=GATE)
        self.assertEqual(worker.name,'new-dftk')
        for head,gate in [('b'*40,GATE),(HEAD,'a'*64)]:
            with self.assertRaises(ValueError):driver.checked_core_parent(p,root=self.root,execution_commit=head,gate_sha256=gate)
        (worker/'final.bin').write_bytes(b'changed synthetic bytes')
        with self.assertRaises(ValueError):driver.checked_core_parent(p,root=self.root,execution_commit=HEAD,gate_sha256=GATE)

    def test_existing_success_directory_is_refused_unchanged(self):
        p=self.area/'endpoints/old';self.write(p/'receipt.json',{'execution_status':'PASS'})
        with self.assertRaises(ValueError):self.launch('old')
        self.assertEqual(json.loads((p/'receipt.json').read_text())['execution_status'],'PASS')

if __name__=='__main__':unittest.main()
