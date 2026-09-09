"""Bounded synthetic Python worker/process metadata tests; no Julia/QE/physics."""
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import si_qe_reference_evidence as p
from run_qe_soc import execute as original_executor

CURRENT='d'*40

class ProcessAccounting(unittest.TestCase):
    def test_group_and_descendants_sum_without_unrelated_processes(self):
        rows=[{'pid':100,'ppid':1,'pgid':100,'rss_kib':10},
              {'pid':101,'ppid':100,'pgid':100,'rss_kib':20},
              {'pid':102,'ppid':101,'pgid':102,'rss_kib':30},
              {'pid':103,'ppid':102,'pgid':103,'rss_kib':40},
              {'pid':200,'ppid':1,'pgid':200,'rss_kib':100000}]
        owned=p.owned_rows(rows,100)
        self.assertEqual({r['pid'] for r in owned},{100,101,102,103})
        self.assertEqual(sum(r['rss_kib'] for r in owned)*1024,102400)
        self.assertEqual(p.owned_rows(rows,999),[])

    def test_ps_empty_malformed_or_negative_refused(self):
        for stdout in ('', '1 2 3\n','1 2 3 -1\n','one two three four\n'):
            with self.subTest(stdout=stdout),patch.object(p.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout,'')):
                with self.assertRaises((ValueError,RuntimeError)):p.ps_rows()

    def command(self,code):
        return [sys.executable,'-c',code]

    def test_short_python_parent_and_child_are_sampled(self):
        code="import subprocess,sys,time; child=subprocess.Popen([sys.executable,'-c','import time; a=bytearray(2097152); time.sleep(.65)']); time.sleep(.65); child.wait()"
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            result,record=p.monitored_execute(original_executor,self.command(code),directory,dict(os.environ))
            self.assertEqual(result,0);self.assertEqual(record['native_exit_code'],0)
            self.assertEqual(record['status'],'PASS');self.assertGreater(record['samples'],0)
            samples=[json.loads(line) for line in (directory/'resource-samples.jsonl').read_text().splitlines()]
            self.assertTrue(any(len(row['processes'])>=2 for row in samples))
            for row in samples:self.assertEqual(row['aggregate_rss_bytes'],1024*sum(x['rss_kib'] for x in row['processes']))
            self.assertEqual(record['peak_aggregate_rss_bytes'],max(row['aggregate_rss_bytes'] for row in samples))
            native=json.loads((directory/'process-exit.json').read_text())
            self.assertEqual(native['exit_code'],result)

    def test_nonatomic_start_marker_is_waited_for_without_false_pass(self):
        import run_qe_soc
        original=run_qe_soc.write_json
        def slow_marker(path,value):
            if Path(path).name=='process-start.json':
                Path(path).write_text('{')
                time.sleep(.15)
            original(path,value)
        with tempfile.TemporaryDirectory() as temporary,patch.object(run_qe_soc,'write_json',side_effect=slow_marker):
            result,record=p.monitored_execute(original_executor,self.command('import time; time.sleep(.5)'),Path(temporary),dict(os.environ))
            self.assertEqual(result,0);self.assertEqual(record['status'],'PASS')
            self.assertGreater(record['nonempty_samples'],0)

    def test_actual_nonzero_native_code_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            result,record=p.monitored_execute(original_executor,self.command('import time; time.sleep(.35); raise SystemExit(7)'),Path(temporary),dict(os.environ))
            self.assertEqual(result,7);self.assertEqual(record['native_exit_code'],7)
            # A successful RSS check is only a resource status; the wrapper must
            # separately reject native exit 7, as the original runner does.
            self.assertEqual(json.loads((Path(temporary)/'process-exit.json').read_text())['exit_code'],7)

    def test_injected_small_rss_limit_terminates_only_synthetic_group(self):
        with tempfile.TemporaryDirectory() as temporary,patch.object(p,'MAX_RSS',1024*1024):
            result,record=p.monitored_execute(original_executor,self.command('import time; time.sleep(.7)'),Path(temporary),dict(os.environ))
            self.assertNotEqual(result,0);self.assertEqual(record['native_exit_code'],result)
            self.assertNotEqual(record['status'],'PASS');self.assertGreaterEqual(record['peak_aggregate_rss_bytes'],1024*1024)
            self.assertEqual(json.loads((Path(temporary)/'process-exit.json').read_text())['exit_code'],result)

    def test_persistent_ps_failure_still_persists_failure_and_native_exit(self):
        real=p.ps_rows;calls=0
        def fail_after_first_sample():
            nonlocal calls
            calls+=1
            if calls<=2:return real()
            raise RuntimeError('synthetic persistent ps failure')
        with tempfile.TemporaryDirectory() as temporary,patch.object(p,'ps_rows',side_effect=fail_after_first_sample):
            # Natural lifetime stays bounded even if the implementation's error
            # cleanup is defective. No real scientific process is launched.
            result,record=p.monitored_execute(original_executor,self.command('import time; time.sleep(.7)'),Path(temporary),dict(os.environ))
            self.assertNotEqual(record['status'],'PASS');self.assertIn('monitor',record['reason'].lower())
            self.assertEqual(record['native_exit_code'],result)
            self.assertEqual(json.loads((Path(temporary)/'resource.json').read_text())['native_exit_code'],result)
            self.assertEqual(json.loads((Path(temporary)/'process-exit.json').read_text())['exit_code'],result)

    def test_nonempty_zero_rss_accounting_cannot_pass(self):
        real=p.ps_rows
        def zero_measurements():
            return [dict(row,rss_kib=0) for row in real()]
        with tempfile.TemporaryDirectory() as temporary,patch.object(p,'ps_rows',side_effect=zero_measurements):
            result,record=p.monitored_execute(original_executor,self.command('import time; time.sleep(.35)'),Path(temporary),dict(os.environ))
            self.assertEqual(result,0);self.assertEqual(record['native_exit_code'],0)
            self.assertGreater(record['samples'],0);self.assertEqual(record['nonempty_samples'],0)
            self.assertNotEqual(record['status'],'PASS')
            self.assertEqual(record['peak_aggregate_rss_bytes'],0)

    def alive(self,pid):
        return any(row['pid']==pid and row['rss_kib']>0 for row in p.ps_rows())

    def reap_synthetic_if_needed(self,pid):
        if pid is None:return
        # This PID came only from the fresh synthetic directory's child file.
        # Keep a defective monitor test from leaving a child behind.
        try:os.kill(pid,signal.SIGKILL)
        except ProcessLookupError:pass
        until=time.monotonic()+2
        while time.monotonic()<until and self.alive(pid):time.sleep(.02)

    def test_early_leader_exit_does_not_leave_same_group_child_or_pass(self):
        child="import os,time; from pathlib import Path; Path('synthetic-child.pid').write_text(str(os.getpid())); time.sleep(.8)"
        parent="import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',"+repr(child)+"]); time.sleep(.3)"
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);pid=None
            try:
                result,record=p.monitored_execute(original_executor,self.command(parent),directory,dict(os.environ))
                pid=int((directory/'synthetic-child.pid').read_text())
                self.assertEqual(result,0);self.assertEqual(record['native_exit_code'],0)
                self.assertNotEqual(record['status'],'PASS')
                self.assertFalse(self.alive(pid),'Synthetic orphan is still consuming resources')
            finally:
                if pid is None and (directory/'synthetic-child.pid').exists():pid=int((directory/'synthetic-child.pid').read_text())
                self.reap_synthetic_if_needed(pid)

    def test_independent_group_ignoring_term_is_cleaned_after_limit(self):
        child="import os,signal,time; from pathlib import Path; signal.signal(signal.SIGTERM,signal.SIG_IGN); Path('synthetic-child.pid').write_text(str(os.getpid())); payload=bytearray(67108864); time.sleep(.9)"
        parent="import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',"+repr(child)+"],start_new_session=True); time.sleep(1.1)"
        with tempfile.TemporaryDirectory() as temporary,patch.object(p,'MAX_RSS',40*1024*1024):
            directory=Path(temporary);pid=None
            try:
                result,record=p.monitored_execute(original_executor,self.command(parent),directory,dict(os.environ))
                pid=int((directory/'synthetic-child.pid').read_text())
                self.assertNotEqual(result,0);self.assertEqual(record['native_exit_code'],result)
                self.assertNotEqual(record['status'],'PASS')
                self.assertFalse(self.alive(pid),'Independent synthetic child survived monitor cleanup')
            finally:
                if pid is None and (directory/'synthetic-child.pid').exists():pid=int((directory/'synthetic-child.pid').read_text())
                self.reap_synthetic_if_needed(pid)

    def test_accounting_unavailable_before_spawn_refuses_executor(self):
        with tempfile.TemporaryDirectory() as temporary,patch.object(p,'ps_rows',side_effect=RuntimeError('synthetic pre-spawn ps unavailable')):
            with patch('builtins.print'):
                with self.assertRaises(RuntimeError):
                    p.monitored_execute(lambda *args:self.fail('executor must not be called'),self.command('pass'),Path(temporary),dict(os.environ))

class MatrixGuard(unittest.TestCase):
    def terminal(self,root,profile,action,status='PASS',commit=CURRENT,name=None):
        run_id=name or action+'-synthetic'
        path=root/'.work/phase8c'/profile/run_id/'result.json';path.parent.mkdir(parents=True)
        worker=status in ('PASS','FAIL')
        path.write_text(json.dumps({'run_id':run_id,'action':action,'execution_status':status,
            'execution_commit':commit,'qe_reference_profile':profile,'profile_type':'QE_REFERENCE',
            'slot_id':'Q'+profile[1:]+'-'+action.removeprefix('Q-'),
            'worker_started':worker,'process_exit_code':0 if status=='PASS' else (4 if worker else None),
            'exit_code':0 if status=='PASS' else 9}))
        return path

    def test_exclusive_lock_and_stale_lock_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary,patch.object(p,'ps_rows',return_value=[]),patch.object(p,'head',return_value=CURRENT):
            root=Path(temporary);lock=root/'.work/phase8c/active-reference.json'
            with p.reference_execution_guard(root,root/'new','Q-SCF','K6'):
                before=lock.read_bytes()
                with self.assertRaises((ValueError,FileExistsError)):
                    with p.reference_execution_guard(root,root/'other','Q-SCF','K6'):self.fail('concurrent guard accepted')
                self.assertEqual(lock.read_bytes(),before)
            self.assertFalse(lock.exists())
            lock.write_text('{"owner_pid":99999999,"token":"stale synthetic"}')
            before=lock.read_bytes()
            with self.assertRaises((ValueError,FileExistsError)):
                with p.reference_execution_guard(root,root/'new','Q-SCF','K6'):self.fail('stale lock cleared')
            self.assertEqual(lock.read_bytes(),before)

    def test_missing_or_duplicate_predecessor_refused(self):
        with tempfile.TemporaryDirectory() as temporary,patch.object(p,'ps_rows',return_value=[]),patch.object(p,'head',return_value=CURRENT):
            root=Path(temporary)
            with self.assertRaises(ValueError):
                with p.reference_execution_guard(root,root/'new','Q-GAMMA','K6'):self.fail('missing SCF accepted')
            self.terminal(root,'K6','Q-SCF',name='first');self.terminal(root,'K6','Q-SCF',name='duplicate')
            with self.assertRaises(ValueError):
                with p.reference_execution_guard(root,root/'new','Q-GAMMA','K6'):self.fail('duplicate SCF accepted')
            self.assertFalse((root/'.work/phase8c/active-reference.json').exists())

    def test_old_execution_predecessor_is_not_current_parent(self):
        with tempfile.TemporaryDirectory() as temporary,patch.object(p,'ps_rows',return_value=[]),patch.object(p,'head',return_value=CURRENT):
            root=Path(temporary);self.terminal(root,'K6','Q-SCF',commit='a'*40)
            with self.assertRaises(ValueError):
                with p.reference_execution_guard(root,root/'new','Q-GAMMA','K6'):self.fail('stale execution accepted')

    def test_failed_parent_and_blocked_child_do_not_block_independent_k8(self):
        with tempfile.TemporaryDirectory() as temporary,patch.object(p,'ps_rows',return_value=[]),patch.object(p,'head',return_value=CURRENT):
            root=Path(temporary)
            self.terminal(root,'K6','Q-SCF',status='FAIL')
            self.terminal(root,'K6','Q-GAMMA',status='BLOCKED_PARENT')
            with p.reference_execution_guard(root,root/'new','Q-SCF','K8'):pass
            self.assertFalse((root/'.work/phase8c/active-reference.json').exists())

    def test_unregistered_slot_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for action,profile in (('D-SCF','K6'),('Q-SCF','K10'),('Q-SPECTRUM','K8')):
                with self.subTest(action=action,profile=profile),self.assertRaises(ValueError):
                    with p.reference_execution_guard(root,root/'new',action,profile):self.fail('unregistered slot accepted')

if __name__=='__main__':unittest.main(verbosity=2)
