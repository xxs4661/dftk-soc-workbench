"""Synthetic protocol mutations of public scalar tables, not new physical runs."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('phase9a_endpoint_metrics',ROOT/'benchmarks/soc-core-memory-v1/endpoint_metrics.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class EndpointArithmetic(unittest.TestCase):
    def setUp(self):
        read=lambda p:json.loads((ROOT/p).read_text())
        self.old=read('results/si-soc-splitting/D-SCF.json')
        self.oldg=read('results/si-soc-splitting/D-spectrum.json')
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


# The host volume may be case-insensitive. This child-process audit gives the
# temporary fixture tree case-sensitive *read semantics* without formatting a
# volume, changing system settings, mocking evaluate(), or copying old data.
CASE_EXACT_CLI = r'''
import os, pathlib, runpy, sys
script, root = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[3]).resolve()
def exact_case(event, args):
    if event != 'open' or not isinstance(args[0], (str, bytes)):
        return
    mode, flags = args[1], args[2]
    if (isinstance(mode, str) and 'r' not in mode) or (mode is None and flags & os.O_ACCMODE != os.O_RDONLY):
        return
    path = pathlib.Path(os.fsdecode(args[0])).absolute()
    if root not in path.parents:
        return
    current = root
    for component in path.relative_to(root).parts:
        if component not in os.listdir(current):
            raise FileNotFoundError('Case-exact temporary tree has no entry: ' + component)
        current /= component
sys.addaudithook(exact_case)
sys.argv = [str(script), *sys.argv[2:]]
runpy.run_path(str(script), run_name='__main__')
'''


class EndpointCLIPaths(unittest.TestCase):
    """Small SYNTHETIC receipts exercise the actual CLI and file-opening path."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.historical = self.root/'results/si-soc-splitting'
        self.historical.mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True, capture_output=True)
        self.contract = json.loads((ROOT/'benchmarks/soc-core-memory-v1/contract.json').read_text())
        levels = [-.8, -.8, -.0017, -.0017, 0., 0., 0., 0.] + [.02 + i*.01 for i in range(16)]
        diagnostics = dict(internal_energy_ha=-7., free_energy_ha=-7.001, entropy_energy_ha=-.001,
                           energy_terms_ha={key: -1. for key in ('Kinetic','AtomicLocal','AtomicNonlocalFR','Hartree','Xc','Ewald','PspCorrection')})
        self.old = dict(run_id='SYNTHETIC-HISTORICAL-SCF', final=dict(diagnostics=diagnostics))
        self.oldg = dict(run_id='SYNTHETIC-HISTORICAL-SPECTRUM', kpoints=[dict(coordinate_fractional=[0.,0.,0.], eigenvalues_ha=levels)])
        self.new = dict(action='OPT-B0-SCF', backend='soc-core', runtime_closed=True,
                        execution_status='PASS', exit_code=0, run_id='SYNTHETIC-CURRENT-SCF', execution_commit='a'*40,
                        final=dict(diagnostics=copy.deepcopy(diagnostics), n_out_sha256='b'*64, map_count=2))
        self.newg = dict(execution_status='PASS', process_exit_code=0, backend='soc-core', physical_operator='full_soc',
                         source_scf_run_id=self.new['run_id'], density_source_sha256='b'*64,
                         n_bands=24, n_electrons=8, occupation_capacity=1, run_id='SYNTHETIC-CURRENT-GAMMA',
                         kpoints=[dict(coordinate_fractional=[0.,0.,0.], eigenvalues_ha=levels, occupations=[1.]*8+[0.]*16)])
        self.density = dict(overall_status='PASS', n_out=dict(candidate_sha256='b'*64, relative=0.),
                            sources=dict(new_scf_run_id=self.new['run_id']))
        for name, value in (('new-scf.json', self.new), ('new-gamma.json', self.newg), ('density.json', self.density),
                            ('benchmarks/soc-core-memory-v1/contract.json', self.contract), ('results/si-soc-splitting/D-SCF.json', self.old)):
            self.write(name, value)
        self.output = self.root/'output.json'

    def write(self, relative, value):
        path = self.root/relative; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, allow_nan=False)+'\n'); return path

    def track_history(self):
        subprocess.run(['git', '-C', str(self.root), 'add', '--', 'results/si-soc-splitting'], check=True, capture_output=True)

    def cli(self):
        return subprocess.run([sys.executable, '-B', '-c', CASE_EXACT_CLI,
            str(ROOT/'benchmarks/soc-core-memory-v1/endpoint_metrics.py'), '--root', str(self.root),
            '--scf', str(self.root/'new-scf.json'), '--gamma', str(self.root/'new-gamma.json'),
            '--density', str(self.root/'density.json'), '--output', str(self.output)],
            capture_output=True, text=True)

    def test_cli_loads_exact_lowercase_historical_spectrum(self):
        self.write('results/si-soc-splitting/D-spectrum.json', self.oldg); self.track_history()
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(self.output.read_text())
        self.assertEqual(record['historical']['spectrum_run_id'], 'SYNTHETIC-HISTORICAL-SPECTRUM')
        self.assertEqual(record['current']['scf_run_id'], 'SYNTHETIC-CURRENT-SCF')
        self.assertEqual(record['gamma']['raw_max_abs_ha'], 0.)

    def test_cli_rejects_uppercase_only_spectrum_without_output(self):
        self.write('results/si-soc-splitting/D-SPECTRUM.json', self.oldg); self.track_history()
        result = self.cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_cli_missing_historical_spectrum_does_not_reuse_output(self):
        self.track_history(); result = self.cli()
        self.assertNotEqual(result.returncode, 0); self.assertFalse(self.output.exists())

    def test_cli_untracked_canonical_file_is_not_historical_evidence(self):
        self.track_history()
        self.write('results/si-soc-splitting/D-spectrum.json', self.oldg)
        result = self.cli()
        self.assertNotEqual(result.returncode, 0); self.assertFalse(self.output.exists())

    def test_cli_refuses_existing_result_without_changing_bytes(self):
        self.write('results/si-soc-splitting/D-spectrum.json', self.oldg); self.track_history()
        self.output.write_bytes(b'SYNTHETIC PRIOR RESULT\n')
        result = self.cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_bytes(), b'SYNTHETIC PRIOR RESULT\n')

    def test_cli_physical_negative_remains_nonpass_after_path_load(self):
        self.write('results/si-soc-splitting/D-spectrum.json', self.oldg); self.track_history()
        self.new['final']['diagnostics']['free_energy_ha'] += 1e-5
        self.write('new-scf.json', self.new); result = self.cli()
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertEqual(json.loads(self.output.read_text())['overall_status'], 'FAIL')

    def test_current_repository_exact_git_path_and_original_public_bytes(self):
        relative='results/si-soc-splitting/D-spectrum.json'
        tracked=subprocess.check_output(['git','-C',str(ROOT),'ls-files','-z'], text=True).split('\0')
        self.assertIn(relative, tracked); self.assertNotIn('results/si-soc-splitting/D-SPECTRUM.json', tracked)
        original=subprocess.check_output(['git','-C',str(ROOT),'show','61cb1c226dcfa8dbeccc63e8f43e33b2790a07c6:'+relative])
        self.assertEqual((ROOT/relative).read_bytes(), original)
if __name__=='__main__':unittest.main()
