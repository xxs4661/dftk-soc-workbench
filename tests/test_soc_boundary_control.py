"""Two bounded stdlib control tests through the new adapter; no material context.

The parent runs these with the existing signal suite within its shared five
minute allowance. They use explicitly synthetic controls, never V slot receipts.
"""
import importlib.util
from pathlib import Path
import time
import unittest
import uuid

ROOT=Path(__file__).resolve().parents[1]
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
OLD=module(ROOT/'tests/test_soc_timing_control.py','boundary_reused_synthetic_control')
ENTRY=module(ROOT/'benchmarks/soc-boundary-v1/run.py','boundary_registered_entry')
OLD.C=ENTRY.shared.control
OLD.JLWORKER=OLD.JLWORKER.replace(
    'include(joinpath(repo,"prototypes","diagnostics.jl"))\ninclude(joinpath(repo,"benchmarks","soc-timing-v1","control.jl"))',
    'driver=joinpath(repo,"benchmarks","soc-timing-v1","driver.jl")\n'
    'definitions=replace(read(driver,String),"isempty(ARGS) ? exit(2) : exit(timing_main(ARGS))"=>"")\n'
    'include_string(Main,definitions,driver)')

class BoundaryControlTests(unittest.TestCase):
    make=OLD.ControlTests.make
    invoke=OLD.ControlTests.invoke
    @classmethod
    def setUpClass(cls):
        cls.start=time.monotonic();cls.base=ROOT/'.work/soc-boundary/cancel-tests'/('synthetic-'+uuid.uuid4().hex)
        cls.base.mkdir(parents=True);cls.records=[]
    @classmethod
    def tearDownClass(cls):
        OLD.C.atomic_json(cls.base/'cancel-tests.json',dict(
            scope='SYNTHETIC actual registered adapter/control definitions; no V slot or material context',
            elapsed_seconds=time.monotonic()-cls.start,records=cls.records))
    def test_new_adapter_cooperative_cancel(self):
        code,state,d=self.invoke('boundary-cooperate',action='cancel',julia=True,budget=9)
        self.assertEqual((code,state['native_exit_code']),(130,130),state)
        self.assertEqual(state['worker']['control']['stop_reason'],'USER_CANCELLED')
        self.assertTrue(state['worker']['runtime_closed']);self.assertFalse((d/'worker/final.bin').exists())
    def test_new_adapter_independent_timeout(self):
        code,state,d=self.invoke('boundary-timeout',julia=True,budget=4)
        self.assertEqual((code,state['native_exit_code']),(124,124),state)
        self.assertEqual(state['worker']['control']['stop_reason'],'TIME_BUDGET_EXCEEDED')
        self.assertTrue(state['worker']['runtime_closed']);self.assertFalse((d/'worker/final.bin').exists())

if __name__=='__main__':unittest.main(verbosity=2)
