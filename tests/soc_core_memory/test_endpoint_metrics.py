"""Synthetic protocol mutations of public scalar tables, not new physical runs."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('phase9a_endpoint_metrics',ROOT/'benchmarks/soc-core-memory-v1/endpoint_metrics.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class EndpointArithmetic(unittest.TestCase):
    def setUp(self):
        read=lambda p:json.loads((ROOT/p).read_text())
        self.old=read('results/si-soc-splitting/D-SCF.json')
        self.oldg=read('results/si-soc-splitting/D-SPECTRUM.json')
        self.new=copy.deepcopy(self.old)
        self.new.update(action='OPT-B0-SCF',backend='soc-core',runtime_closed=True,run_id='SYNTHETIC-SCF',execution_status='PASS',exit_code=0)
        self.newg=copy.deepcopy(self.oldg);self.newg.update(backend='soc-core',run_id='SYNTHETIC-GAMMA',source_scf_run_id=self.new['run_id'],execution_status='PASS',process_exit_code=0)
        self.newg['kpoints']=self.newg['kpoints'][:1]
        self.density=dict(overall_status='PASS',n_out=dict(candidate_sha256=self.new['final']['n_out_sha256'],relative=0.),sources=dict(new_scf_run_id='SYNTHETIC-SCF'))
        self.contract=read('benchmarks/soc-core-memory-v1/contract.json')
    def run_case(self):return m.evaluate(self.old,self.new,self.oldg,self.newg,self.density,self.contract)
    def test_zero_difference_keeps_occupation_review(self):
        r=self.run_case();self.assertEqual(r['overall_status'],'PASS')
        self.assertEqual(r['gamma']['raw_max_abs_ha'],0)
        self.assertEqual(r['gamma_occupation_diagnostic']['status'],'REVIEW_REQUIRED')
        self.assertEqual(r['physical_convergence'],'NOT_ESTABLISHED')
    def test_raw_shift_is_not_fitted_out(self):
        self.newg['kpoints'][0]['eigenvalues_ha']=[e+1e-5 for e in self.newg['kpoints'][0]['eigenvalues_ha']]
        self.assertEqual(self.run_case()['gamma']['status'],'FAIL')
    def test_free_energy_failure_retained(self):
        self.new['final']['diagnostics']['free_energy_ha']+=1e-5
        self.assertEqual(self.run_case()['overall_status'],'FAIL')
    def test_wrong_parent_rejected(self):
        self.newg['source_scf_run_id']='HISTORICAL'
        with self.assertRaises(ValueError):self.run_case()
    def test_failed_gamma_rejected(self):
        self.newg['execution_status']='FAIL'
        with self.assertRaises(ValueError):self.run_case()
    def test_no_wrong_point_or_extra_gamma(self):
        self.newg['kpoints'][0]['coordinate_fractional']=[0.,0.,.1]
        with self.assertRaises(ValueError):self.run_case()
    def test_private_density_failure_stays_failure(self):
        self.density['overall_status']='FAIL'
        self.assertEqual(self.run_case()['overall_status'],'FAIL')
    def test_missing_levels_not_inferred(self):
        self.newg['kpoints'][0]['eigenvalues_ha'].pop()
        with self.assertRaises(ValueError):self.run_case()
if __name__=='__main__':unittest.main()
