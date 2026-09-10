"""Synthetic continuation protocol only: no Julia, source bundle or physical run."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('original_core_driver_test',ROOT/'tests/soc_core_memory/test_driver.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
driver=old.driver

class ResumeDriverTests(unittest.TestCase):
    setUp=old.CoreDriverTests.setUp
    write=old.CoreDriverTests.write
    worker=old.CoreDriverTests.worker
    setup_launch=old.CoreDriverTests.setup_launch

    def setup_resume(self):
        self.setup_launch()
        self.auth=dict(resume_id='phase9a-completion-20260910',resume_preparation_commit='e'*40,
            resume_from_commit='f'*40,static_execution_commit='b'*40,endpoint_execution_commit=old.HEAD,
            authorization_sha256='d'*64,core_gate_sha256=old.GATE,authorization_path='.work/phase9a/resume/authorization.json')
        real=driver.resume_tools(ROOT)
        self.control=type('SyntheticControl',(),{})()
        self.control.verify_authorization=Mock(side_effect=lambda *args:copy.deepcopy(self.auth))
        self.control.verify_worker_resume=real.verify_worker_resume
        self.control.process_proof=real.process_proof
        patch.object(real,'launcher',return_value=driver).start()
        self.control.validate_entry_receipt=Mock(return_value={'status':'PASS'})
        self.control.reservation_directory=Mock(return_value=self.area/'endpoints/resume-slots'/self.auth['resume_preparation_commit'])
        patch.object(driver,'resume_tools',return_value=self.control).start()
        self.monitor_records=[]
        self.tool.monitored_execute.side_effect=self.monitor

    def entry_worker(self,name,action='OPT-B0-SCF'):
        result=self.worker(action,name)
        result.update(driver.resume_fields(self.auth,action),check_only=True,check_status='PASS',execution_status='CHECK_ONLY_PASS',
            numerical_execution_status='NOT_RUN',formal_slot_reserved=False,context_constructed=False,
            context_registrations=0,source_registrations=0,source_status='PASS',settings_status='PASS',executed_source_sha256={'synthetic': 'a'*64})
        return result

    def monitor(self,execute,command,directory,environment):
        self.assertIn('--resume-authorization',command)
        check='--check-entry' in command
        self.assertEqual((directory.parent/'active.json').exists(),not check)
        if check:self.assertFalse(self.control.reservation_directory.return_value.exists())
        resource=dict(status='PASS',owned_process_cleanup_status='PASS',native_exit_code=0,peak_aggregate_rss_bytes=100,nonempty_samples=1)
        self.write(directory/'resource.json',resource);self.write(directory/'process-exit.json',dict(exit_code=0,interrupted=False))
        self.write(directory/'process-start.json',dict(command=command))
        worker=Path(command[6]);worker.mkdir()
        value=self.entry_worker(worker.name,command[5]) if check else self.worker(command[5],worker.name)
        if not check:
            value.update(driver.resume_fields(self.auth,command[5]));(worker/'final.bin').write_bytes(b'SYNTHETIC checkpoint transport only')
            value['checkpoint_sha256']=driver.digest(worker/'final.bin')
        self.write(worker/'result.json',value);self.monitor_records.append(value)
        return 0,resource

    def launch(self,name='new',action='OPT-B0-SCF',**kwargs):
        return driver.launch(action,self.area/'endpoints'/name,root=self.root,backend='soc-core',execution_commit=old.HEAD,
            core_gate=self.area/'gate.json',resume_authorization=self.area/'resume/authorization.json',**kwargs)

    def test_default_gate_function_bytes_are_unchanged(self):
        import subprocess
        historical=subprocess.check_output(['git','show','98781fd0ce6c2f4138ed010e115a13e370410d58:scripts/run_si_dftk.py'],cwd=ROOT,text=True)
        current=(ROOT/'scripts/run_si_dftk.py').read_text()
        extract=lambda s:s[s.index('def verify_core_gate('):s.index('def validate_core_worker(')]
        self.assertEqual(extract(historical),extract(current))

    def test_all_predeclared_numerical_regions_unchanged(self):
        plan=json.loads((ROOT/'benchmarks/soc-core-memory-v1/resume/plan.json').read_text())
        source=(ROOT/'scripts/run_si_soc.jl').read_text()
        for item in plan['numerical_driver_regions']:
            start=source.index(item['start']);end=source.index(item['end'],start)
            with self.subTest(region=item['name']):self.assertEqual(hashlib.sha256(source[start:end].encode()).hexdigest(),item['sha256'])

    def test_check_entry_is_nonphysical_and_does_not_reserve(self):
        self.setup_resume();self.assertEqual(self.launch(check_entry=True),0)
        r=json.loads((self.area/'endpoints/new/receipt.json').read_text())
        self.assertEqual(r['execution_status'],'CHECK_ONLY_PASS');self.assertFalse(r['worker_started']);self.assertTrue(r['check_process_started'])
        self.assertFalse(r['formal_slot_reserved']);self.assertEqual(r['numerical_execution_status'],'NOT_RUN')
        self.control.validate_entry_receipt.assert_not_called();self.control.reservation_directory.assert_not_called()
        self.assertEqual(self.control.verify_authorization.call_count,2)
        driver.verify_core_gate.assert_not_called()

    def test_formal_requires_real_entry_receipt_before_slot(self):
        self.setup_resume();self.control.validate_entry_receipt.side_effect=ValueError('Synthetic missing entry manifest')
        self.assertEqual(self.launch(),9);self.tool.monitored_execute.assert_not_called()
        self.assertFalse(self.control.reservation_directory.return_value.exists());self.assertFalse((self.area/'endpoints/active.json').exists())

    def test_formal_uses_fixed_new_namespace_and_preserves_old_slot(self):
        self.setup_resume();oldslot=self.write(self.area/'endpoints/slots/OPT-B0-SCF.json',{'historical_failure':'untouched'})
        before=oldslot.read_bytes();self.assertEqual(self.launch(),0);self.assertEqual(oldslot.read_bytes(),before)
        self.control.validate_entry_receipt.assert_called_once();self.control.reservation_directory.assert_called_once()
        reservation=json.loads((self.control.reservation_directory.return_value/'OPT-B0-SCF.json').read_text())
        self.assertEqual(reservation['attempt'],2);self.assertEqual(reservation['resume_authorization_sha256'],self.auth['authorization_sha256'])
        self.assertEqual(self.launch('again'),9);self.assertEqual(self.tool.monitored_execute.call_count,1)

    def test_native_failure_still_consumes_once_and_preserves_native_exit(self):
        self.setup_resume()
        def failure(execute,cmd,directory,env):
            resource=dict(status='PASS',owned_process_cleanup_status='PASS',native_exit_code=7)
            self.write(directory/'resource.json',resource);self.write(directory/'process-exit.json',dict(exit_code=7))
            return 7,resource
        self.tool.monitored_execute.side_effect=failure
        self.assertEqual(self.launch(),9);r=json.loads((self.area/'endpoints/new/receipt.json').read_text())
        self.assertEqual(r['worker_exit_code'],7);self.assertEqual(r['attempt'],2);self.assertEqual(r['execution_status'],'FAIL')
        self.assertEqual(self.launch('again'),9);self.assertEqual(self.tool.monitored_execute.call_count,1)

    def test_auth_failure_and_change_cannot_publish_pass(self):
        self.setup_resume();self.control.verify_authorization.side_effect=ValueError('Synthetic incompatible frozen source')
        self.assertEqual(self.launch('bad'),9);self.tool.monitored_execute.assert_not_called()
        changed=copy.deepcopy(self.auth);changed['authorization_sha256']='0'*64
        self.control.verify_authorization.side_effect=[copy.deepcopy(self.auth),changed]
        self.assertEqual(self.launch('changed',check_entry=True),9)
        self.assertEqual(json.loads((self.area/'endpoints/changed/receipt.json').read_text())['execution_status'],'FAIL')

    def test_active_global_and_static_locks_block_checks_without_deleting(self):
        self.setup_resume()
        for scope in ('endpoints','static'):
            lock=self.write(self.area/scope/'active.json',{'prior':'untouched'})
            with self.subTest(scope=scope):self.assertEqual(self.launch(scope,check_entry=True),9)
            self.assertTrue(lock.exists());lock.unlink()
        self.tool.monitored_execute.assert_not_called()

    def test_entry_contract_rejects_physical_pass_missing_exit_and_fake_sources(self):
        self.setup_resume()
        for key,value in (('execution_status','PASS'),('exit_code',None),('exit_code',False),('context_constructed',True),
                          ('context_registrations',1),('source_registrations',False),('source_status','NOT_RUN'),('settings_status','FAIL'),
                          ('executed_source_sha256',{}),('formal_slot_reserved',True),('attempt',1),('resume_authorization_sha256','0'*64)):
            record=self.entry_worker('test');record[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                driver.validate_entry_worker(record,0,'OPT-B0-SCF','test',root=self.root,execution_commit=old.HEAD,auth=self.auth)

    def test_successful_formal_worker_requires_same_resume_but_failure_keeps_code(self):
        self.setup_resume();r=self.worker();r.update(driver.resume_fields(self.auth,'OPT-B0-SCF'))
        r['resume_authorization_sha256']='0'*64
        with self.assertRaises(ValueError):driver.validate_core_worker(r,0,'OPT-B0-SCF',r['run_id'],root=self.root,execution_commit=old.HEAD,gate_sha256=old.GATE,resume_auth=self.auth)
        r.update(exit_code=7,execution_status='FAIL',reason='SYNTHETIC failure')
        driver.validate_core_worker(r,7,'OPT-B0-SCF',r['run_id'],root=self.root,execution_commit=old.HEAD,gate_sha256=old.GATE,resume_auth=self.auth)

    def test_parent_outer_and_worker_auth_are_both_bound(self):
        self.setup_resume();self.assertEqual(self.launch(),0);p=self.area/'endpoints/new'
        driver.checked_core_parent(p,root=self.root,execution_commit=old.HEAD,gate_sha256=old.GATE,resume_auth=self.auth)
        outer=json.loads((p/'receipt.json').read_text());worker=p/outer['worker_directory']/'result.json'
        for target in ('outer','worker'):
            changed=copy.deepcopy(outer)
            if target=='outer':changed['resume_id']='other-attempt'
            else:
                value=json.loads(worker.read_text());value['resume_authorization_sha256']='0'*64;self.write(worker,value)
                changed['worker_result_sha256']=driver.digest(worker)
            self.write(p/'receipt.json',changed)
            with self.subTest(target=target),self.assertRaises(ValueError):driver.checked_core_parent(p,root=self.root,execution_commit=old.HEAD,gate_sha256=old.GATE,resume_auth=self.auth)

    def test_missing_gamma_parent_is_blocked_without_slot_native_or_worker(self):
        self.setup_resume();self.assertEqual(self.launch(action='OPT-B0-GAMMA'),9)
        r=json.loads((self.area/'endpoints/new/receipt.json').read_text())
        self.assertEqual(r['failure_status'],'BLOCKED_PARENT');self.assertIsNone(r.get('worker_exit_code'))
        self.assertFalse(r['worker_started']);self.control.reservation_directory.assert_not_called()

    def test_no_implicit_continuation_or_unbound_check(self):
        with self.assertRaises(ValueError):driver.launch('OPT-B0-SCF',self.area/'x',root=self.root,resume_authorization='auth')
        with self.assertRaises(ValueError):driver.launch('OPT-B0-SCF',self.area/'x',root=self.root,backend='soc-core',check_entry=True)

    def test_verify_resume_cli_forwards_exact_arguments(self):
        self.setup_resume()
        with patch.object(sys,'argv',['run_si_dftk.py','--verify-resume',str(self.root),'AUTH',old.HEAD,'GATE']):self.assertEqual(driver.main(),0)
        self.control.verify_authorization.assert_called_once_with(self.root,'AUTH',old.HEAD,'GATE')

if __name__=='__main__':unittest.main(verbosity=2)
