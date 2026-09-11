"""Synthetic post-execution public provenance protocol regressions.

These mocks do not validate physical Si, UPF bytes, WFC arrays, or QE execution.
These tests run no numerical worker. SI_REFERENCE_TEST_ROOT permits explicit
relocation; the default is the repository containing this test file.
"""
import copy
from contextlib import ExitStack
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(os.environ.get('SI_REFERENCE_TEST_ROOT', str(Path(__file__).resolve().parents[1]))).resolve()
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'tests')]
import si_qe_reference as r
import si_qe_reference_evidence as e
import si_soc_comparison as comparison
import run_si_qe as runner

EXECUTION = 'a'*40
REPLAY = 'b'*40
REPLAY_PATH = 'scripts/si_qe_reference_evidence.py'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, separators=(',', ':'), allow_nan=False)+'\n')


class CompletePublicParent(unittest.TestCase):
    """Real new parent-binding checks; native physics parser deliberately mocked."""
    def setUp(self):
        self.profile = 'K6'; self.case = r.load_case(ROOT, self.profile)
        self.case_hash = r.case_sha256(self.profile, ROOT)
        self.ng = json.loads((ROOT/r.CASE_DIR/'resource-geometry.json').read_text())['profiles'][self.profile]['ng_in_declared_order']
        original_save = {f'wfc{i}.dat': {'sha256': digest(f'synthetic wfc identity {i}'.encode()), 'bytes': 16}
                         for i in range(1, 217)}
        original_save.update({'charge-density.dat': {'sha256': 'c'*64, 'bytes': 32},
                             'data-file-schema.xml': {'sha256': 'd'*64, 'bytes': 64},
                             'Si_r.upf': {'sha256': self.case['pseudo']['sha256'], 'bytes': 291215}})
        self.parent = {'run_id': 'synthetic-parent', 'density_source_sha256': 'c'*64,
                       'fermi_energy_ha': .25, 'temperature_ha': .001}
        self.parent_meta = {'run_id': 'synthetic-parent', 'density_source_sha256': 'c'*64,
            'case_sha256': self.case_hash, 'save_files': original_save,
            'raw_result_sha256': '1'*64, 'raw_parsed_sha256': '2'*64,
            'source_run_path': '.work/phase8c/K6/synthetic-parent'}
        binding = {'run_id': self.parent['run_id'], 'save_files': copy.deepcopy(original_save),
            'parent_result_sha256': '1'*64, 'parent_parsed_sha256': '2'*64,
            'charge_sha256': 'c'*64, 'fermi_energy_ha': .25, 'case_sha256': self.case_hash,
            'qe_reference_profile': self.profile, 'profile_type': 'QE_REFERENCE',
            'save_path': 'scratch/si8c_k6.save', 'directory': '<WORKBENCH>/'+self.parent_meta['source_run_path']}
        own_save = copy.deepcopy(original_save)
        own_save['data-file-schema.xml'] = {'sha256': 'e'*64, 'bytes': 80}
        own_save['wfc1.dat'] = {'sha256': 'f'*64, 'bytes': 18}
        self.meta = {'action': 'Q-GAMMA', 'execution_status': 'PASS', 'process_exit_code': 0,
            'run_id': 'synthetic-gamma', 'case_sha256': self.case_hash, 'density_source_sha256': 'c'*64,
            'save_files': own_save, 'native_files': {'qe.xml': {'raw_sha256': 'e'*64}},
            'source_preservation_status': 'PASS', 'parent_binding': binding}
        self.native = {'qe.in': (ROOT/r.CASE_DIR/self.profile/'qe-gamma.in').read_bytes(),
            'qe.xml': b'<synthetic/>', 'qe.stdout': b'Parallel version (MPI), running on 1 processors\nMPI processes distributed on 1 nodes\n',
            'qe.stderr': b''}
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.parser = self.stack.enter_context(patch.object(comparison, 'parse_si_qe', return_value={
            'kpoints': [{'npw': self.ng[0]}], 'energy': None, 'scf': None, 'electron_sum': None}))
        self.gamma = self.stack.enter_context(patch.object(r, 'validate_q_gamma', return_value={
            'precision_status': 'PASS', 'trend_usable': True, 'synthetic_protocol': True}))
        self.stack.enter_context(patch.object(r, 'validate_q_scf', return_value={'status': 'PASS'}))

    def parse(self):
        return e.parse_public_native(ROOT, self.profile, self.native, self.meta, self.parent, self.parent_meta)

    def test_complete_original_manifest_and_hashes_are_accepted(self):
        value = self.parse()
        self.assertEqual(value['source_scf_run_id'], self.parent['run_id'])
        self.assertEqual(value['fermi_energy_ha'], .25)

    def test_changed_missing_or_extra_original_wfc_manifest_entry_rejected(self):
        before = copy.deepcopy(self.meta['parent_binding']['save_files'])
        for change in ('hash', 'bytes', 'missing', 'extra'):
            self.meta['parent_binding']['save_files'] = copy.deepcopy(before)
            files = self.meta['parent_binding']['save_files']
            if change == 'hash': files['wfc216.dat']['sha256'] = '0'*64
            if change == 'bytes': files['wfc216.dat']['bytes'] += 1
            if change == 'missing': files.pop('wfc216.dat')
            if change == 'extra': files['wfc217.dat'] = {'sha256': '0'*64, 'bytes': 16}
            with self.subTest(change=change), self.assertRaises(ValueError): self.parse()

    def test_wrong_result_parsed_case_profile_savepath_or_runpath_rejected(self):
        original = copy.deepcopy(self.meta['parent_binding'])
        for field, value in (('parent_result_sha256', '0'*64), ('parent_parsed_sha256', '0'*64),
                            ('case_sha256', '0'*64), ('qe_reference_profile', 'K8'),
                            ('profile_type', 'SENSITIVITY'), ('save_path', 'scratch/si8b_k4.save'),
                            ('directory', '<WORKBENCH>/.work/phase8c/K8/other'), ('run_id', 'old-K4')):
            self.meta['parent_binding'] = dict(original, **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError): self.parse()

    def test_missing_original_parent_metadata_or_wrong_current_case_rejected(self):
        with self.assertRaises(ValueError):
            e.parse_public_native(ROOT, self.profile, self.native, self.meta, self.parent, None)
        self.meta['case_sha256'] = '0'*64
        with self.assertRaises(ValueError): self.parse()

    def test_native_npw_must_match_predeclared_integer_geometry(self):
        self.parser.return_value['kpoints'][0]['npw'] = self.ng[0]+1
        with self.assertRaises(ValueError): self.parse()

    def test_all_scf_npw_are_checked_without_using_splitting_to_match_points(self):
        geometry = json.loads((ROOT/r.CASE_DIR/'resource-geometry.json').read_text())
        for profile in ('K6', 'K8'):
            counts = geometry['profiles'][profile]['ng_in_declared_order']
            self.meta.update(action='Q-SCF', case_sha256=r.case_sha256(profile,ROOT))
            self.native['qe.in'] = (ROOT/r.CASE_DIR/profile/'qe-scf.in').read_bytes()
            for i in range(1,len(counts)+1):
                self.meta['save_files'].setdefault(f'wfc{i}.dat',{'sha256':digest(f'synthetic {i}'.encode()),'bytes':16})
            self.parser.return_value = {'kpoints': [{'npw': n} for n in counts]}
            value = e.parse_public_native(ROOT, profile, self.native, self.meta)
            self.assertEqual([p['npw'] for p in value['kpoints']], counts)
            self.parser.return_value['kpoints'][-1]['npw'] += 1
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                e.parse_public_native(ROOT, profile, self.native, self.meta)


class PublicReplayProvenance(unittest.TestCase):
    """Full gzip/index replay protocol with mocked numerics and synthetic Git bytes."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.out = self.root/e.PUBLIC_DIR
        self.source_paths = set(runner.SOURCES)|{'scripts/si_qe_reference.py', REPLAY_PATH, 'scripts/si_soc_sensitivity.py'}
        self.prepared_paths = set(r.prepared_paths())|{'benchmarks/si-soc-splitting-v1/source.json'}
        self.frozen_paths = set(runner.ENV_FILES)|set(runner.HISTORICAL)
        self.executed = {p: ('Synthetic execution source '+p).encode() for p in self.source_paths}
        for p in self.source_paths|self.prepared_paths|self.frozen_paths:
            path = self.root/p; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.executed.get(p, ('Synthetic input '+p).encode()))
        self.replay_bytes = b'Synthetic separately committed public replay implementation.'
        (self.root/REPLAY_PATH).write_bytes(self.replay_bytes)
        put(self.root/r.CASE_DIR/'sources.json', json.loads((ROOT/r.CASE_DIR/'sources.json').read_text()))
        identity = json.loads((ROOT/'results/si-soc-sensitivity/Q-environment.json').read_text())
        baseline = self.root/'results/si-soc-sensitivity/Q-environment.json'
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_bytes((ROOT/'results/si-soc-sensitivity/Q-environment.json').read_bytes())
        self.identity = dict(identity, numerical_executions=0)
        self.trend = {'synthetic_protocol': True, 'physical_convergence': 'NOT_ESTABLISHED'}
        self.manifest = {'schema_version': 1, 'provenance_schema_version': 2, 'execution_commit': EXECUTION,
            'expected_execution_commit': EXECUTION, 'replay_commit': REPLAY,
            'replay_source_sha256': digest(self.replay_bytes), 'profiles': {p:{} for p in ('K6', 'K8')}}
        self.metadata = {}; self.canonical = {}; self.counter = 0
        for profile in ('K6', 'K8'):
            for action in ('Q-SCF', 'Q-GAMMA'):
                run_id = profile+'-'+action+'-synthetic'
                native = {name: self.pack(profile, action, name, b'Synthetic native protocol text.\n') for name in e.NATIVE_NAMES}
                metadata = {'action': action, 'run_id': run_id, 'execution_commit': EXECUTION, 'native_files': native,
                    'source_sha256': {p:digest(v) for p,v in self.executed.items()},
                    'prepared_sha256': {p:e.sha(self.root/p) for p in self.prepared_paths},
                    'frozen_sha256': {p:e.sha(self.root/p) for p in self.frozen_paths},
                    'resource': {'status': 'PASS', 'owned_process_cleanup_status': 'PASS',
                        'peak_aggregate_rss_bytes': 1024, 'nonempty_samples': 1, 'synthetic_protocol': True}}
                canonical = {'scf': {'trace': []}} if action == 'Q-SCF' else {'scf': None, 'gamma_validation': {'synthetic_protocol': True}}
                self.metadata[profile, action] = metadata; self.canonical[profile, action] = canonical
                payloads = {name:self.pack(profile, action, name+'.json', json.dumps(value).encode()) for name,value in
                    (('metadata', metadata), ('endpoint', canonical), ('iterations', []), ('identity', self.identity))}
                self.manifest['profiles'][profile][action] = {'action': action, 'run_id': run_id, 'execution_commit': EXECUTION,
                    'execution_status': 'PASS', 'exit_code': 0, 'process_exit_code': 0, 'native_files': native, 'payloads': payloads}
        put(self.out/'trend.json', self.trend); self.manifest['trend_sha256'] = e.sha(self.out/'trend.json')
        self.save_manifest()
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(r, 'load_history', return_value={'B0': {}, 'K4': {}}))
        self.stack.enter_context(patch.object(r, 'compare_trend', return_value=self.trend))
        self.stack.enter_context(patch.object(e, 'parse_public_native', side_effect=lambda root,p,n,m,*parents: copy.deepcopy(self.canonical[p,m['action']])) )
        self.git = self.stack.enter_context(patch.object(e.subprocess, 'check_output', side_effect=self.git_bytes))

    def pack(self, profile, action, name, raw):
        self.counter += 1
        rel = f'{e.PUBLIC_DIR}/{profile}/{action}/{self.counter}-{name}.gz'
        info = e.packed(self.root/rel, raw); info['path'] = rel
        return info

    def save_manifest(self):
        put(self.out/'evidence.json', self.manifest)

    def update_metadata(self, profile, action):
        info = self.pack(profile, action, 'updated-metadata.json', json.dumps(self.metadata[profile,action]).encode())
        self.manifest['profiles'][profile][action]['payloads']['metadata'] = info
        self.save_manifest()

    def git_bytes(self, command, **kwargs):
        self.assertEqual(command[:2], ['git', 'show'])
        commit, path = command[2].split(':', 1)
        if commit == EXECUTION: return self.executed[path]
        if commit == REPLAY and path == REPLAY_PATH: return self.replay_bytes
        # Return plausible bytes for aliases too: the implementation must reject
        # the invalid commit spelling itself, rather than relying on Git to fail.
        if path == REPLAY_PATH: return self.replay_bytes
        return self.executed[path]

    def test_actual_execution_and_public_replay_versions_are_distinct(self):
        result = e.replay(self.root)
        self.assertEqual(result['exit_code'], 0); self.assertEqual(result['native_slots_reparsed'], 4)
        calls = [call.args[0][2] for call in self.git.call_args_list]
        self.assertIn(EXECUTION+':'+REPLAY_PATH, calls)
        self.assertIn(REPLAY+':'+REPLAY_PATH, calls)
        self.assertNotEqual(self.executed[REPLAY_PATH], self.replay_bytes)

    def test_postexecution_tool_bytes_cannot_impersonate_actual_execution_source(self):
        self.metadata['K6','Q-SCF']['source_sha256'][REPLAY_PATH] = digest(self.replay_bytes)
        self.update_metadata('K6', 'Q-SCF')
        with self.assertRaises(ValueError): e.replay(self.root)

    def test_changed_current_scientific_parser_is_not_a_permitted_tool_update(self):
        path = next(p for p in self.source_paths if p.endswith('si_soc_comparison.py'))
        (self.root/path).write_bytes(b'Synthetic forbidden parser change')
        with self.assertRaises(ValueError): e.replay(self.root)

    def test_wrong_replay_tool_hash_is_not_silently_bound_to_current_head(self):
        self.manifest['replay_source_sha256'] = '0'*64; self.save_manifest()
        with self.assertRaises(ValueError): e.replay(self.root)

    def test_commit_alias_type_option_and_nonhex_are_rejected(self):
        original = copy.deepcopy(self.manifest)
        for key in ('execution_commit', 'expected_execution_commit', 'replay_commit'):
            for bad in ('HEAD', '--help', 'g'*40, 'a'*39, 123, True):
                self.manifest = dict(original, **{key:bad}); self.save_manifest()
                with self.subTest(key=key, bad=bad), self.assertRaises((ValueError, TypeError)): e.replay(self.root)

    def test_complete_failure_preserves_original_native_exit_and_ieee_flags(self):
        profile, action = 'K6', 'Q-GAMMA'; entry = self.manifest['profiles'][profile][action]
        failure = {'action':action, 'run_id':entry['run_id'], 'execution_status':'RESOURCE_BLOCKED',
                   'exit_code':9, 'process_exit_code':-15, 'execution_commit':EXECUTION,
                   'reason':'Synthetic monitor failure; original native error retained',
                   'warnings':{'IEEE_INVALID_FLAG':'REPORTED', 'IEEE_DIVIDE_BY_ZERO':'REPORTED'},
                   'resource':{'status':'RESOURCE_BLOCKED', 'reason':'synthetic cap'}}
        info = self.pack(profile, action, 'failure.json', json.dumps(failure).encode()); info['raw_sha256'] = digest(json.dumps(failure).encode())
        entry.update(execution_status=failure['execution_status'], exit_code=9, process_exit_code=-15,
                     failure_reason=failure['reason'], payloads={'failure':info}); self.save_manifest()
        self.assertEqual(e.replay(self.root)['native_slots_reparsed'], 3)
        decoded = json.loads(e.unpacked(self.root, info['path'], info))
        self.assertEqual(decoded, failure)
        entry['process_exit_code'] = 0; self.save_manifest()
        with self.assertRaises(ValueError): e.replay(self.root)


class EarlyBlockedExport(unittest.TestCase):
    def fixture(self, root):
        profiles = {p:{} for p in ('K6', 'K8')}
        for p in profiles:
            for action in ('Q-SCF', 'Q-GAMMA'):
                relative = f'.work/phase8c/{p}/{p}-{action}-early'
                record = {'schema_version':1, 'action':action, 'run_id':Path(relative).name,
                    'execution_status':'BLOCKED_PARENT' if action=='Q-GAMMA' else 'BLOCKED',
                    'exit_code':9, 'process_exit_code':None, 'worker_started':False,
                    'reason':'Synthetic early failure before any observed execution binding'}
                put(root/relative/'result.json', record); profiles[p][action] = relative
        index = root/'index.json'; put(index, {'expected_execution_commit':EXECUTION, 'profiles':profiles})
        return index

    def test_early_blocked_actual_execution_remains_null_not_declared_sha(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve(); index = self.fixture(root)
            with patch.object(r, 'load_history', return_value={'B0':{},'K4':{}}), \
                 patch.object(r, 'compare_trend', return_value={'synthetic':'no new endpoints'}), \
                 patch.object(e, 'head', return_value=REPLAY), patch.object(e, 'replay', return_value={'exit_code':0}):
                e.export_runs(root, index)
            manifest = json.loads((root/e.PUBLIC_DIR/'evidence.json').read_text())
            self.assertIsNone(manifest['execution_commit'])
            self.assertEqual(manifest['expected_execution_commit'], EXECUTION)
            for entries in manifest['profiles'].values():
                for entry in entries.values():
                    self.assertIsNone(entry['execution_commit']); self.assertIsNone(entry['process_exit_code'])
                    payload = entry['payloads']['failure']
                    original = json.loads(e.unpacked(root,payload['path'],payload))
                    self.assertNotIn('execution_commit',original)
                    self.assertFalse(original['worker_started']); self.assertEqual(original['exit_code'],9)

    def test_invalid_declared_commit_rejected_before_export(self):
        for bad in ('HEAD', '--help', 'z'*40, 3, True):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as d:
                root=Path(d).resolve(); index=self.fixture(root); value=json.loads(index.read_text())
                value['expected_execution_commit']=bad; put(index,value)
                with self.assertRaises(ValueError): e.export_runs(root,index)

    def test_invalid_observed_commit_cannot_hide_in_all_failed_branch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve(); index=self.fixture(root); value=json.loads(index.read_text())
            value.pop('expected_execution_commit'); put(index,value)
            for paths in value['profiles'].values():
                for relative in paths.values():
                    path=root/relative/'result.json';record=json.loads(path.read_text());record['execution_commit']='HEAD';put(path,record)
            with patch.object(r,'load_history',return_value={'B0':{},'K4':{}}), \
                 patch.object(r,'compare_trend',return_value={}), patch.object(e,'head',return_value=REPLAY), \
                 patch.object(e,'replay',return_value={'exit_code':0}), self.assertRaises(ValueError):
                e.export_runs(root,index)


if __name__ == '__main__':
    unittest.main()
