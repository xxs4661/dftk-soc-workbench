"""Optional real synthetic control checks, never a material/static slot.

The owner must first establish process/RSS observation and run this under the
task's shared 300-second synthetic allowance. A default test discovery honestly
reports NOT_RUN instead of starting an unobservable subprocess.
"""
import importlib.util
import os
from pathlib import Path
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj
SUP = module(ROOT/'benchmarks/soc-validation-local-v1/supervisor.py','local_control_test_supervisor')
OLD = module(ROOT/'tests/test_soc_timing_control.py','local_control_reused_synthetic_fixtures')
OLD.C = SUP.CONTROL
# These are synthetic scalars only. Do not manufacture the old two-map receipt.
OLD.PYWORKER = OLD.PYWORKER.replace('completed_maps=0,','').replace(',completed_maps=2','').replace(
    'DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED',SUP.SUCCESS)
OLD.JLWORKER = OLD.JLWORKER.replace('r["completed_maps"]=0;','')


@unittest.skipUnless(os.environ.get('SOC_LOCAL_REAL_CONTROL_TESTS') == '1',
                    'NOT_RUN: owner must authorize bounded synthetic launcher after resource-observer preflight')
class LocalRealControlTests(unittest.TestCase):
    make = OLD.ControlTests.make
    invoke = OLD.ControlTests.invoke
    @classmethod
    def setUpClass(cls):
        resources=SUP.module(ROOT/'benchmarks/soc-extra-v1/resources.py','local_control_observer')
        observation=SUP.observer_preflight(resources,ROOT)
        if observation['status'] != 'ELIGIBLE':
            raise unittest.SkipTest('BLOCKED_RESOURCE_OBSERVATION: '+observation['reason'])
        cls.start=time.monotonic()
        cls.base=ROOT/'.work/soc-validation-local/control-tests'/('synthetic-'+uuid.uuid4().hex)
        cls.base.mkdir(parents=True);cls.records=[]
    @classmethod
    def tearDownClass(cls):
        OLD.C.atomic_json(cls.base/'cancel-tests.json',dict(
            scope='SYNTHETIC shared registered control only; no static context or numerical slot',
            elapsed_seconds=time.monotonic()-cls.start,records=cls.records))
    def test_cooperative_cancel(self):
        code,state,d=self.invoke('local-cooperate',action='cancel',julia=True,budget=9)
        self.assertEqual((code,state['native_exit_code']),(130,130),state)
        self.assertEqual(state['worker']['control']['stop_reason'],'USER_CANCELLED')
        self.assertNotIn('completed_maps',state['worker'])
    def test_independent_timeout(self):
        code,state,d=self.invoke('local-timeout',julia=True,budget=4)
        self.assertEqual((code,state['native_exit_code']),(124,124),state)
        self.assertEqual(state['worker']['control']['stop_reason'],'TIME_BUDGET_EXCEEDED')
        self.assertNotIn('completed_maps',state['worker'])


if __name__ == '__main__': unittest.main(verbosity=2)
