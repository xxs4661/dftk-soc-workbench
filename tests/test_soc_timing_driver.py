"""Synthetic route/source contracts. No Julia or numerical launcher is invoked."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('timing_route', ROOT/'benchmarks/soc-timing-v1/route.py')
R = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(R)


def route(task='T-B0-TIMED'):
    root = Path('/tmp/synthetic-timing-adapter').resolve()
    profile, budget, timed = R.TASKS[task]
    execution = 'b'*40
    return dict(schema_version=1, task_id=task, profile=profile, budget_seconds=budget,
                timing_enabled=timed, seed=81001, diagnostic_maps=2, limit_bytes=8*R.GIB,
                warning_bytes=7*R.GIB, remaining_growth_bytes=2*R.GIB,
                case_path=R.CASES[profile], case_sha256='c'*64, deadline_epoch=1900000000.,
                execution_commit=execution, source_commit=execution if timed else R.E0,
                adapter_root=str(root), numerical_root=str(root if timed else root.parent/'synthetic-e0'),
                run_id='synthetic-run', worker_id='worker', outdir=str(root/'.work/soc-timing/runs/synthetic-run/worker'),
                source_sha256={R.CASES[profile]:'c'*64}, adapter_sha256={'driver':'d'*64})


class RouteTests(unittest.TestCase):
    def test_exact_three_profiles(self):
        for task in R.TASKS:
            with self.subTest(task=task):
                self.assertEqual(R.validate_route(route(task))['task_id'], task)

    def test_ref_cannot_load_e1_tree(self):
        value=route('T-B0-REF'); value['numerical_root']=value['adapter_root']
        with self.assertRaises(ValueError): R.validate_route(value)

    def test_ref_cannot_relabel_e1_commit_as_e0(self):
        value=route('T-B0-REF'); value['source_commit']=value['execution_commit']
        with self.assertRaises(ValueError): R.validate_route(value)

    def test_no_k6_or_gamma_or_other_task(self):
        for task in ('T-K6-TIMED','T-K8-TIMED','X-K6-PILOT','T-B0-GAMMA'):
            value=route();value['task_id']=task
            with self.subTest(task=task),self.assertRaises(ValueError):R.validate_route(value)

    def test_fixed_limits_seed_and_map_count(self):
        for key,value in [('limit_bytes',10*R.GIB),('warning_bytes',8*R.GIB),
                          ('remaining_growth_bytes',0),('seed',81002),('diagnostic_maps',3),
                          ('budget_seconds',1800),('schema_version',True),('diagnostic_maps',True)]:
            item=route();item[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):R.validate_route(item)

    def test_noncanonical_source_roots_refused(self):
        for key in ('numerical_root','adapter_root'):
            item=route();item[key]+='/unused/..'
            with self.subTest(key=key),self.assertRaises(ValueError):R.validate_route(item)

    def test_old_area_and_worker_alias_refused(self):
        for out in ('/tmp/synthetic-timing-adapter/.work/phase9a-extra/runs/synthetic-run/worker',
                    '/tmp/synthetic-timing-adapter/.work/soc-timing/runs/synthetic-run/not-worker'):
            value=route();value['outdir']=out
            with self.subTest(out=out),self.assertRaises(ValueError):R.validate_route(value)

    def test_nonfinite_deadline_and_case_mismatch_refused(self):
        for field,value in [('deadline_epoch',float('nan')),('deadline_epoch',True),
                            ('case_sha256','f'*64),('source_commit','HEAD')]:
            item=route();item[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):R.validate_route(item)

    def test_exact_file_detects_changed_and_linked_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();(root/'source.jl').write_bytes(b'# synthetic source\n')
            with patch.object(R,'git',return_value=b'# synthetic source\n'):
                self.assertEqual(R.exact_file(root,'a'*40,'source.jl'),hashlib.sha256(b'# synthetic source\n').hexdigest())
            with patch.object(R,'git',return_value=b'# other bytes\n'):
                with self.assertRaises(ValueError):R.exact_file(root,'a'*40,'source.jl')
            (root/'alias.jl').symlink_to(root/'source.jl')
            with self.assertRaises(ValueError):R.exact_file(root,'a'*40,'alias.jl')

    def test_source_inventory_includes_loaded_extra_driver_and_toml(self):
        paths=['scripts/run_si_soc.jl','prototypes/soc_scf/scf.jl',
               'prototypes/soc_scf/solver.jl','prototypes/spinor/scf.jl','src/SOCKernels.jl',
               'benchmarks/soc-extra-v1/driver.jl','prototypes/soc_scf/phase6c.toml']
        with patch.object(R,'git',return_value=('\n'.join(paths)+'\n').encode()), \
             patch.object(R,'exact_file',return_value='a'*64):
            inventory=R.source_files(Path('/synthetic'),'b'*40,R.CASES['B0'])
        self.assertIn('benchmarks/soc-extra-v1/driver.jl',inventory)
        self.assertIn('prototypes/soc_scf/phase6c.toml',inventory)
        self.assertIn('environment/workbench/Manifest.toml',inventory)


if __name__=='__main__':
    unittest.main()
