"""Synthetic Git/JSON continuation contracts; no Julia, physics or performance run."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
CONTROL = ROOT / 'benchmarks/soc-core-memory-v1/resume/control.py'
spec = importlib.util.spec_from_file_location('synthetic_resume_control', CONTROL)
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False) + '\n')
    return path


class SourceContractTests(unittest.TestCase):
    """The temporary Git tree has only synthetic text, never executable Julia."""
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='synthetic-resume-source-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.text = {
            '.gitignore': '.work/\n',
            'src/SOCKernels.jl': '# SYNTHETIC frozen kernel\n',
            'prototypes/spinor/operators.jl': '# SYNTHETIC frozen adapter\n',
            'scripts/other_numerical.jl': '# SYNTHETIC frozen include\n',
            'scripts/run_si_soc.jl': '# SYNTHETIC driver\ncase=fixture\nBEGIN_NUMERIC\nseed=81001\nEND_NUMERIC\n',
            'scripts/run_si_dftk.py': 'def verify_core_gate():\n    return "same execution"\ndef validate_core_worker():\n    pass\n',
            'benchmarks/soc-core-memory-v1/endpoint_metrics.py': 'def evaluate():\n    return 1.0\ndef main():\n    pass\n',
            'benchmarks/soc-core-memory-v1/endpoint_compare.jl': '        accuracy=1e-9\n        result["sources"]=nothing\n',
            'README.md': 'SYNTHETIC source-contract fixture\n',
        }
        for path, text in self.text.items():
            p = self.root / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        self.command('init', '-q')
        self.base = self.commit()
        region = control.chunk(self.text['scripts/run_si_soc.jl'], 'BEGIN_NUMERIC', 'END_NUMERIC')
        self.plan = dict(
            allowed_existing_code={p: 'SYNTHETIC permitted identity changes only' for p in (
                'scripts/run_si_soc.jl', 'scripts/run_si_dftk.py',
                'benchmarks/soc-core-memory-v1/endpoint_metrics.py',
                'benchmarks/soc-core-memory-v1/endpoint_compare.jl')},
            allowed_navigation=['README.md'],
            allowed_new_paths=['benchmarks/soc-core-memory-v1/resume/', 'tests/soc_core_memory/resume/'],
            numerical_driver_regions=[dict(name='synthetic_science', start='BEGIN_NUMERIC', end='END_NUMERIC',
                sha256=hashlib.sha256(region.encode()).hexdigest())],
            accepted_static_to_partial_diff=[])
        for name, value in [('STATIC', self.base), ('RESUME_FROM', self.base)]:
            p = patch.object(control, name, value); p.start(); self.addCleanup(p.stop)
        p = patch.object(control, 'plan', return_value=self.plan); p.start(); self.addCleanup(p.stop)
        routing = {name: hashlib.sha256(self.text[name].encode()).hexdigest() for name in control.APPROVED_ROUTING_SHA256}
        p = patch.object(control, 'APPROVED_ROUTING_SHA256', routing); p.start(); self.addCleanup(p.stop)

    def command(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.PIPE).decode().strip()

    def commit(self):
        self.command('add', '.')
        self.command('-c', 'user.name=Synthetic contract test', '-c', 'user.email=synthetic@example.invalid',
                     'commit', '-q', '--allow-empty', '-m', 'Synthetic fixture only')
        return self.command('rev-parse', 'HEAD')

    def change(self, path, value):
        p = self.root / path; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(value)
        return self.commit()

    def test_unchanged_science_and_navigation_only_are_accepted(self):
        sha = self.change('README.md', 'SYNTHETIC updated navigation\n')
        result = control.source_proof(self.root, sha)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['default_gate_rule'], 'UNCHANGED')
        self.assertEqual(set(result['numerical_sources']), {'src/SOCKernels.jl', 'prototypes/spinor/operators.jl', 'scripts/other_numerical.jl'})

    def test_core_adapter_and_old_include_changes_are_rejected(self):
        for path in ('src/SOCKernels.jl', 'prototypes/spinor/operators.jl', 'scripts/other_numerical.jl'):
            with self.subTest(path=path):
                sha = self.change(path, '# SYNTHETIC changed mathematics\n')
                with self.assertRaises(ValueError): control.source_proof(self.root, sha)
                self.change(path, self.text[path])

    def test_added_dispatch_file_is_rejected(self):
        sha = self.change('prototypes/new_dispatch.jl', '# SYNTHETIC dispatch addition\n')
        with self.assertRaises(ValueError): control.source_proof(self.root, sha)

    def test_measured_static_identity_is_not_replaceable(self):
        sha = self.change('README.md', 'SYNTHETIC changed endpoint\n')
        with patch.object(control, 'STATIC', '0' * 40), self.assertRaises(subprocess.CalledProcessError):
            control.source_proof(self.root, sha)

    def test_allowed_driver_cannot_change_protected_numerics(self):
        sha = self.change('scripts/run_si_soc.jl', self.text['scripts/run_si_soc.jl'].replace('seed=81001', 'seed=999'))
        with patch.dict(control.APPROVED_ROUTING_SHA256, {'scripts/run_si_soc.jl': control.digest(self.root/'scripts/run_si_soc.jl')}):
            with self.assertRaisesRegex(ValueError, 'numerical region'): control.source_proof(self.root, sha)

    def test_allowed_python_driver_cannot_relax_default_gate(self):
        sha = self.change('scripts/run_si_dftk.py', self.text['scripts/run_si_dftk.py'].replace('same execution', 'any execution'))
        with patch.dict(control.APPROVED_ROUTING_SHA256, {'scripts/run_si_dftk.py': control.digest(self.root/'scripts/run_si_dftk.py')}):
            with self.assertRaisesRegex(ValueError, 'Default gate'): control.source_proof(self.root, sha)

    def test_metrics_and_norm_formulas_cannot_change(self):
        for path, old, new in (
            ('benchmarks/soc-core-memory-v1/endpoint_metrics.py', '1.0', '2.0'),
            ('benchmarks/soc-core-memory-v1/endpoint_compare.jl', '1e-9', '1e-1')):
            with self.subTest(path=path):
                sha = self.change(path, self.text[path].replace(old, new))
                with self.assertRaises(ValueError): control.source_proof(self.root, sha)
                self.change(path, self.text[path])

    def test_science_insertion_outside_protected_regions_is_rejected(self):
        # Regression: six unchanged chunks do not authorize arbitrary earlier code.
        sha = self.change('scripts/run_si_soc.jl', self.text['scripts/run_si_soc.jl'].replace(
            'case=fixture\n', 'case=fixture\ncase["cutoff"]=999\n'))
        with self.assertRaises(ValueError): control.source_proof(self.root, sha)

    def test_new_resume_file_cannot_supply_dispatch_override(self):
        # A new allowed prefix must not authorize numerical dispatch through an include.
        p = self.root / 'benchmarks/soc-core-memory-v1/resume/override.jl'
        p.parent.mkdir(parents=True, exist_ok=True); p.write_text('# SYNTHETIC replacement dispatch\n')
        sha = self.change('scripts/run_si_soc.jl', self.text['scripts/run_si_soc.jl'] + '\ninclude("../benchmarks/soc-core-memory-v1/resume/override.jl")\n')
        with self.assertRaises(ValueError): control.source_proof(self.root, sha)

    def test_clean_tree_and_exact_execution_are_required(self):
        (self.root / 'README.md').write_text('Uncommitted SYNTHETIC change\n')
        with self.assertRaisesRegex(ValueError, 'Clean'): control.source_proof(self.root, self.base)
        with self.assertRaisesRegex(ValueError, 'Exact execution'): control.source_proof(self.root, self.base[:7])


class AuthorizationContractTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='synthetic-resume-auth-')
        self.addCleanup(temp.cleanup); self.root = Path(temp.name).resolve()
        self.payload = dict(schema_version=1, phase='9A', resume_id=control.RESUME_ID,
            resume_from_commit=control.RESUME_FROM, static_execution_commit=control.STATIC,
            resume_preparation_commit=control.PREPARATION, endpoint_execution_commit='e' * 40,
            core_gate_sha256='a' * 64, attempts=copy.deepcopy(control.ACTIONS))
        self.auth = dict(self.payload, authorization_sha256='b' * 64)

    def test_issue_is_once_per_preparation_and_can_be_verified_without_reissue(self):
        with patch.object(control, 'make_payload', side_effect=lambda *a: copy.deepcopy(self.payload)), \
             patch.object(control.shutil, 'disk_usage', return_value=SimpleNamespace(free=20 * 1024**3)):
            issued = control.issue(self.root, 'e' * 40, 'SYNTHETIC gate')
            target = control.authorization_path(self.root); original = target.read_bytes()
            self.assertEqual(issued['authorization_sha256'], control.digest(target))
            self.assertEqual(control.verify_authorization(self.root, target, 'e' * 40, 'SYNTHETIC gate'), issued)
            with self.assertRaisesRegex(ValueError, 'already issued'): control.issue(self.root, 'e' * 40, 'SYNTHETIC gate')
            self.assertEqual(target.read_bytes(), original)

    def test_alternative_authority_path_preparation_and_mutation_are_rejected(self):
        receipt = dict(copy.deepcopy(self.payload), issued_utc='2026-09-10T00:00:00+00:00')
        correct = dump(control.authorization_path(self.root), receipt)
        duplicate = dump(self.root / '.work/alternative/authorization.json', receipt)
        with patch.object(control, 'make_payload', return_value=self.payload):
            with self.assertRaisesRegex(ValueError, 'preparation authorization'): control.verify_authorization(self.root, duplicate, 'e' * 40, 'gate')
            receipt['attempts']['OPT-B0-SCF'] = 3; dump(correct, receipt)
            with self.assertRaisesRegex(ValueError, 'no longer matches'): control.verify_authorization(self.root, correct, 'e' * 40, 'gate')
        for key, value in [('resume_id', 'phase9a-again'), ('resume_preparation_commit', 'f' * 40), ('attempts', {'OPT-B0-SCF':3,'OPT-B0-GAMMA':1})]:
            bad = copy.deepcopy(self.auth); bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): control.reservation_directory(self.root, bad)

    def test_parent_fields_types_execution_and_gate_are_exact(self):
        record = dict(control.resume_fields(self.auth, 'OPT-B0-GAMMA'), execution_commit='e' * 40, core_gate_sha256='a' * 64)
        control.verify_worker_resume(record, self.auth, 'OPT-B0-GAMMA')
        for key, value in [('attempt', True), ('attempt', 2), ('resume_id', 'different'), ('resume_authorization_sha256','c'*64), ('execution_commit', control.STATIC), ('core_gate_sha256', 'd'*64)]:
            bad = dict(record); bad[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): control.verify_worker_resume(bad, self.auth, 'OPT-B0-GAMMA')

    def test_static_export_uses_historical_operators_field_and_original_gate(self):
        raw = self.root/'.work/export/operators.bin'; raw.parent.mkdir(parents=True); raw.write_bytes(b'SYNTHETIC operator transport only')
        export = dump(raw.parent/'operator-export.json', {'operators': dict(path='operators.bin', sha256=control.digest(raw), bytes=raw.stat().st_size)})
        comparison = dump(self.root/'.work/comparison.json', {'pairs':[{'reference_operators':control.descriptor(self.root, export)}]})
        arithmetic = dump(self.root/'.work/arithmetic.json', {'SYNTHETIC':True})
        gate = dump(self.root/'.work/gate.json', dict(suite_receipts={}, comparison=control.descriptor(self.root, comparison),
            performance=control.descriptor(self.root, arithmetic), replay_data=control.descriptor(self.root, arithmetic)))
        p = {'static_gate':control.descriptor(self.root, gate)}
        def original_gate(root, path, execution):
            self.assertEqual(execution, control.STATIC)
        old_replay = SimpleNamespace(replay=lambda *a: dict(assessment_status='PASS', time_status='PERFORMANCE_REVIEW_REQUIRED'))
        with patch.object(control, 'launcher', return_value=SimpleNamespace(verify_core_gate=original_gate)), patch.object(control,'module',return_value=old_replay):
            result = control.static_proof(self.root, p, gate)
            self.assertEqual(result['status'],'STATIC_EVIDENCE_REUSED_UNCHANGED_CORE')
            self.assertIn(control.descriptor(self.root, raw),result['files'])
            p['static_gate']['sha256'] = '0'*64
            with self.assertRaisesRegex(ValueError,'original static gate'): control.static_proof(self.root,p,gate)

    def test_environment_uses_actual_frozen_checksums_path(self):
        paths = ('environment/workbench/Project.toml','environment/workbench/Manifest.toml',
            'environment/workbench/checksums.toml','benchmarks/si-soc-splitting-v1/source.json',
            'benchmarks/si-soc-splitting-v1/case.json','results/si-soc-splitting/D-spectrum.json','results/si-soc-splitting/D-SCF.json')
        for path in paths: dump(self.root/path, {'SYNTHETIC':True})
        lock = self.root/'config/sources.lock'; lock.parent.mkdir()
        lock.write_text('[source.dftk]\ncheckout=".work/dftk"\ncommit="synthetic-DFTK"\n[source.pseudopotentialio]\ncheckout=".work/pseudopotentialio"\ncommit="synthetic-PseudoPotentialIO"\n')
        raw = self.root/'.work/historical/final.bin'; raw.parent.mkdir(parents=True);raw.write_bytes(b'SYNTHETIC opaque checkpoint')
        result = dump(raw.parent/'result.json', {'SYNTHETIC':True})
        dump(self.root/'benchmarks/soc-core-memory-v1/sources.json',{'historical_endpoints':{'B0':dict(
            directory='.work/historical',checkpoint_sha256=control.digest(raw),checkpoint_bytes=raw.stat().st_size,raw_result_sha256=control.digest(result))}})
        def git(root,*args):
            if args[0]=='status':return b''
            return (('synthetic-DFTK' if Path(root).name=='dftk' else 'synthetic-PseudoPotentialIO')+'\n').encode()
        env={'JULIA_DEPOT_PATH':str(self.root),'JULIA_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
        with patch.object(control,'git',side_effect=git), patch.object(control,'tree',return_value={'results/si-soc-splitting/D-spectrum.json':'synthetic'}), \
             patch.object(control,'launcher',return_value=SimpleNamespace(verify_preparation=lambda *a: {'sha256':'c'*64})), patch.dict(control.os.environ,env):
            actual=control.environment_inputs(self.root)
            self.assertIn('environment/workbench/checksums.toml',actual['files'])
            self.assertFalse((self.root/'config/checksums.toml').exists())
            self.assertEqual(actual['historical_checkpoint_sha256'],control.digest(raw))

    def test_alias_duplicate_key_and_nonfinite_authority_rejected(self):
        original = dump(self.root/'original.json', {'x': 1})
        alias = self.root/'alias.json'; alias.symlink_to(original)
        with self.assertRaises(ValueError): control.bound(self.root, dict(path='alias.json', sha256=control.digest(original)))
        for text in ('{"x":1,"x":2}', '{"x":NaN}'):
            original.write_text(text)
            with self.subTest(text=text), self.assertRaises(ValueError): control.read(original)

    def entry(self, **worker_changes):
        common = dict(control.resume_fields(self.auth, 'OPT-B0-SCF'), execution_commit='e'*40,
            core_gate_sha256='a'*64, check_only=True, execution_status='CHECK_ONLY_PASS', check_status='PASS',
            numerical_execution_status='NOT_RUN', formal_slot_reserved=False, exit_code=0)
        worker = dict(common, run_id='SYNTHETIC-entry-dftk', action='OPT-B0-SCF', environment={'status':'PASS','julia_version':'1.12.7'},
            context_constructed=False, context_registrations=0, source_registrations=0, source_status='PASS',
            settings_status='PASS', executed_source_sha256={'synthetic':'c'*64})
        source = self.root/'SYNTHETIC-entry-source.txt'; source.write_text('Synthetic loaded source identity only\n')
        worker['executed_source_sha256'] = {'SYNTHETIC-entry-source.txt':control.digest(source)}
        worker.update(worker_changes)
        area = self.root/'.work/phase9a/endpoints/SYNTHETIC-entry'
        worker_path = dump(area/'SYNTHETIC-entry-dftk/result.json', worker)
        resource = dict(status='PASS', owned_process_cleanup_status='PASS', native_exit_code=0, peak_aggregate_rss_bytes=1, nonempty_samples=1)
        outer = dict(common, run_id='SYNTHETIC-entry', action='OPT-B0-SCF', worker_directory='SYNTHETIC-entry-dftk',
            worker_result_sha256=control.digest(worker_path), worker_started=False, check_process_started=True,
            worker_exit_code=0, resource=resource)
        outer_path = dump(area/'receipt.json', outer)
        dump(area/'resource.json', resource); dump(area/'process-exit.json', dict(exit_code=0, interrupted=False))
        dump(area/'process-start.json', dict(command=['SYNTHETIC only', '--check-entry']))
        manifest = dict(schema_version=1, phase='9A', endpoint_execution_commit='e'*40,
            resume_authorization_sha256='b'*64, launcher_receipt=control.descriptor(self.root, outer_path),
            worker_result=control.descriptor(self.root, worker_path))
        dump(control.authorization_path(self.root).with_name('entry-check.json'), manifest)
        return outer_path, worker_path

    def fake_launcher(self):
        def resource_contract(resource, native):
            control.require(type(native) is int and native == 0 and resource['native_exit_code'] == 0
                and resource['status'] == 'PASS' and resource['owned_process_cleanup_status'] == 'PASS', 'Synthetic resource contract failure')
        def validate_entry_worker(worker, native, action, run_id, **kwargs):
            control.require(native == 0 and worker['context_constructed'] is False
                and type(worker['context_registrations']) is int and worker['context_registrations'] == 0
                and type(worker['source_registrations']) is int and worker['source_registrations'] == 0
                and worker['source_status'] == 'PASS' and worker['settings_status'] == 'PASS'
                and worker.get('environment',{}).get('status') == 'PASS', 'Synthetic physical entry rejected')
        return SimpleNamespace(core_tools=lambda root: SimpleNamespace(resource_contract=resource_contract), validate_entry_worker=validate_entry_worker)

    def rebind_entry(self, outer_path, worker_path):
        outer = control.read(outer_path); outer['worker_result_sha256'] = control.digest(worker_path); dump(outer_path, outer)
        manifest_path = control.authorization_path(self.root).with_name('entry-check.json')
        manifest = control.read(manifest_path)
        manifest.update(launcher_receipt=control.descriptor(self.root, outer_path), worker_result=control.descriptor(self.root, worker_path))
        dump(manifest_path, manifest)

    def test_entry_requires_real_check_only_success_not_physical_or_missing_exit(self):
        with patch.object(control, 'launcher', return_value=self.fake_launcher()):
            self.entry(); self.assertEqual(control.validate_entry_receipt(self.root, self.auth)['status'], 'PASS')
            for key, value in [('check_only', False), ('execution_status','PASS'), ('numerical_execution_status','PASS'), ('formal_slot_reserved',True), ('exit_code',None), ('exit_code',False), ('environment',{'status':'FAIL'})]:
                self.entry(**{key:value})
                with self.subTest(key=key, value=value), self.assertRaises(ValueError): control.validate_entry_receipt(self.root, self.auth)

    def test_entry_missing_native_exit_and_wrong_worker_binding_rejected(self):
        with patch.object(control, 'launcher', return_value=self.fake_launcher()):
            for key, value in [('worker_exit_code',None), ('worker_exit_code',False), ('worker_exit_code',7), ('worker_directory','wrong-parent')]:
                outer_path, worker_path = self.entry(); outer = control.read(outer_path); outer[key] = value; dump(outer_path, outer); self.rebind_entry(outer_path, worker_path)
                with self.subTest(key=key, value=value), self.assertRaises(ValueError): control.validate_entry_receipt(self.root, self.auth)

    def test_entry_revalidates_zero_numerical_context_and_no_registrations(self):
        with patch.object(control, 'launcher', return_value=self.fake_launcher()):
            for key, value in [('context_constructed',True), ('context_registrations',1), ('source_registrations',1), ('settings_status','FAIL')]:
                self.entry(**{key:value})
                with self.subTest(key=key), self.assertRaises(ValueError): control.validate_entry_receipt(self.root, self.auth)

    def test_entry_requires_matching_persisted_native_exit_and_resource(self):
        with patch.object(control, 'launcher', return_value=self.fake_launcher()):
            for filename, value in [('process-exit.json',{'exit_code':7}), ('resource.json',{'status':'FAIL'})]:
                outer_path, worker_path = self.entry(); dump(outer_path.parent/filename, value)
                with self.subTest(filename=filename), self.assertRaises(ValueError): control.validate_entry_receipt(self.root, self.auth)


if __name__ == '__main__':
    print('SYNTHETIC control source SHA256:', control.digest(CONTROL), flush=True)
    unittest.main(verbosity=2)
