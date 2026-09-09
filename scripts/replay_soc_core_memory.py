#!/usr/bin/env python3
"""Phase9A recorded arithmetic, never a kernel/SCF/array reconstruction.

build-gate authenticates the four private static runs, including their native
payload hashes, with the existing runner contract. replay reads public JSON
only. Public owner tables are histograms of the authenticated private object
census: their sums are replayable, but object reachability, address unions and
the numerical array comparisons remain explicitly RUNNER_REPORTED.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
BASE = 'c764311a5422b5c3cab5a7b78a02d420910c4e56'
PREPARATION = 'e4f16a51a0304f5e70f5ae038563d6760409c2c4'
REFERENCE = 'bbe9aa7755f052900e6e9c4618252a410e1cc8f0'
BENCH = 'benchmarks/soc-core-memory-v1/'
PREPARED_HASHES = {
    'contract.json': 'aa1956cba470f6ac1a7f88bfffdfefeebdad1a87831e1ce7e04f3e70dd904ec7',
    'plan.json': '09887791d1b76b0d59ca4735264a05f8f8f924edb5073a94fae1b0f5f5d7c52c',
    'sources.json': '1713dd5e1462a857a91a88031b59f2c6e942851d4d2ba4ddb3dbce9b2c0e3066',
}
SUITES = ('REF-B0', 'REF-K4', 'CORE-B0', 'CORE-K4')
MICRO = {f'{operator}_{n}' for operator in ('FR', 'component', 'full_H') for n in (1, 24, 30)}
OPERATIONS = MICRO | {'density', 'nonlocal', 'energy', 'pipeline'}
FIELDS = ('time_seconds', 'allocated_bytes', 'gc_seconds', 'compile_seconds', 'recompile_seconds', 'lock_conflicts')
GC_FIELDS = {'freecall', 'poolalloc', 'total_time', 'full_sweep', 'allocd', 'malloc', 'realloc', 'bigalloc', 'pause'}
TERMS = ('Kinetic', 'AtomicLocal', 'AtomicNonlocalFR', 'Hartree', 'Xc', 'Ewald', 'PspCorrection')
SCALARS = ('internal_energy_ha', 'free_energy_ha', 'entropy_energy_ha', 'entropy_dimensionless', 'direct_kinetic_ha', 'nonlocal_ha')
PHASES = ('context_ready', 'H_constructed', 'one_static_solve_storage_proxy_no_eigensolve',
          'density', 'energy', 'callback_or_save_boundary', 'next_map_boundary', 'session_closed')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def finite(value):
    if isinstance(value, dict):
        for item in value.values():
            finite(item)
    elif isinstance(value, list):
        for item in value:
            finite(item)
    elif type(value) in (int, float):
        require(math.isfinite(value), 'Nonfinite JSON number')


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Nonfinite JSON constant: ' + value)
    result = json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=invalid)
    finite(result)
    return result


def number(value, label, minimum=0):
    require(type(value) in (int, float) and math.isfinite(value) and value >= minimum, 'Invalid number: ' + label)
    return value


def integer(value, label, minimum=0):
    require(type(value) is int and value >= minimum, 'Invalid integer: ' + label)
    return value


def hex_value(value, length=64):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(length) + '}', value), 'Invalid exact hash/commit')
    return value


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def object_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def exact_record(recorded, expected):
    """JSON booleans cannot masquerade as numeric counts/status codes."""
    if isinstance(expected, dict):
        return isinstance(recorded, dict) and set(recorded) == set(expected) and all(exact_record(recorded[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(recorded, list) and len(recorded) == len(expected) and all(exact_record(a, b) for a, b in zip(recorded, expected))
    return type(recorded) is type(expected) and recorded == expected


def relative_file(root, relative, *, private=False):
    require(isinstance(relative, str), 'Evidence path must be a string')
    part = Path(relative)
    require(not part.is_absolute() and '..' not in part.parts and relative == part.as_posix(), 'Unconfined evidence path')
    require(part.suffix == '.json', 'Only JSON evidence is accepted here')
    root = Path(root).resolve()
    path = root / part
    require(path.is_file() and not path.is_symlink() and path.resolve() == path, 'Missing or aliased evidence file')
    area = root / ('.work/phase9a' if private else 'results/soc-core-memory')
    require(area in path.parents, 'Evidence outside its declared area')
    return path


def bound(root, entry, *, private=False):
    require(isinstance(entry, dict), 'Missing evidence descriptor')
    path = relative_file(root, entry['path'], private=private)
    require(sha(path) == hex_value(entry['sha256']), 'Evidence receipt bytes differ: ' + entry['path'])
    if 'bytes' in entry:
        require(path.stat().st_size == integer(entry['bytes'], 'evidence bytes'), 'Evidence byte count differs')
    return read(path), path


def descriptor(root, path):
    return dict(path=path.relative_to(root).as_posix(), sha256=sha(path), bytes=path.stat().st_size)


def git_bytes(root, commit, path):
    hex_value(commit, 40)
    require(not Path(path).is_absolute() and '..' not in Path(path).parts, 'Unconfined source path')
    return subprocess.check_output(['git', '-C', str(root), 'show', commit + ':' + path])


def preparation(root):
    records = {}
    for name, expected in PREPARED_HASHES.items():
        path = root / (BENCH + name)
        require(not path.is_symlink() and sha(path) == expected, 'Frozen preparation changed: ' + name)
        records[name] = read(path)
    return records['contract.json'], records['sources.json']


def sample_statistics(item, name):
    require(isinstance(item, dict) and item.get('operation') == name and item.get('status') == 'PASS', 'Wrong/failed operation: ' + name)
    for key, expected in (('requested_samples', 5), ('completed_samples', 5), ('warmup_count', 1)):
        require(type(item.get(key)) is int and item[key] == expected, 'Incomplete sample set: ' + name)
    samples = item.get('samples')
    require(isinstance(samples, list) and len(samples) == 5, 'Exactly five samples required: ' + name)
    for index, sample in enumerate([item.get('warmup'), *samples]):
        require(isinstance(sample, dict) and sample.get('status') == 'PASS' and type(sample.get('index')) is int and sample['index'] == index, 'Missing/reordered/failed sample: ' + name)
        for field in FIELDS:
            value = number(sample.get(field), name + '/' + field)
            if field in ('allocated_bytes', 'lock_conflicts'):
                integer(value, field)
        require(isinstance(sample.get('consumed'), dict) and bool(sample['consumed']), 'Unconsumed output: ' + name)
        gc = sample.get('gcstats')
        require(isinstance(gc, dict) and set(gc) == GC_FIELDS and all(type(value) is int for value in gc.values()), 'Incomplete/invalid recorded GC counters')
        finite(sample)
    result = {}
    for field in FIELDS:
        values = sorted(sample[field] for sample in samples)
        result[field] = dict(median=values[2], min=values[0], max=values[-1])
    require(exact_record(item.get('statistics'), result), 'Recorded statistics differ from all five samples: ' + name)
    return result


def dispatch_check(item, name, core):
    operator, columns = name.rsplit('_', 1); columns = int(columns)
    record = item.get('dispatch'); require(isinstance(record, dict), 'Missing actual micro dispatch')
    if core:
        module = 'Main.FRIntegration'; source = '<workbench>/prototypes/fr_integration/runtime.jl'
        receiver = module + '.' + {'FR': 'RuntimeFRBlock', 'component': 'RuntimeComponentBlock', 'full_H': 'RuntimeFullHamiltonian'}[operator]
    else:
        module, path, typename = {'FR': ('Main.RelativisticProjectors', 'prototypes/relativistic/operator.jl', 'FRNonlocalOperator'),
                                 'component': ('Main.SpinorPrototype', 'prototypes/spinor/operators.jl', 'ComponentOperator'),
                                 'full_H': ('Main.FRIntegration', 'prototypes/fr_integration/hamiltonian.jl', 'FullHamiltonianBlock')}[operator]
        source = '<reference-root>/' + path; receiver = module + '.' + typename
    require(record.get('module_name') == module and record.get('source') == source and isinstance(record.get('receiver_type'), str) and (record['receiver_type'] == receiver or record['receiver_type'].startswith(receiver + '{')), 'Wrong actual micro operator/source dispatch')
    require(integer(record.get('call_count_including_warmup'), 'dispatch calls') == 6 and integer(record.get('columns_per_call'), 'dispatch columns') == columns and integer(record.get('line'), 'method line', 1) > 0, 'Wrong micro call/column count')
    before, after = record['before_counts'], record['after_counts']
    expected = dict(full_mul_calls=6 if operator == 'full_H' else 0, fr_mul_calls=6 if operator == 'full_H' else 0,
                    full_columns=6 * columns if operator == 'full_H' else 0, fr_columns=6 * columns if operator == 'full_H' else 0)
    for key, delta in expected.items():
        require(integer(after.get(key), key) - integer(before.get(key), key) == delta, 'Full/FR dispatch counter mismatch')
    for key, delta in dict(operator_mul_calls=6, operator_columns=6 * columns, scalar_mul_calls=12, scalar_columns=12 * columns).items():
        require(integer(after['common'].get(key), key) - integer(before['common'].get(key), key) == (0 if operator == 'FR' else delta), 'Component dispatch counter mismatch')


def resource_check(outer, native, resource):
    for record in (outer, native):
        require(type(record.get('exit_code')) is int and record['exit_code'] == 0, 'Unsuccessful native/wrapper exit')
    require(type(outer.get('process_exit_code')) is int and outer['process_exit_code'] == 0 and outer.get('worker_started') is True, 'Worker did not execute successfully')
    require(native.get('interrupted') is False and resource == outer.get('resource'), 'Native interruption or changed resource receipt')
    require(resource.get('status') == resource.get('owned_process_cleanup_status') == 'PASS', 'Resource observer/cleanup failed')
    require(type(resource.get('native_exit_code')) is int and resource['native_exit_code'] == 0, 'Resource/native exit differs')
    require(integer(resource.get('limit_bytes'), 'RSS limit') == 8 * 1024**3 and resource.get('sample_interval_seconds') == .1, 'Changed resource contract')
    peak = integer(resource.get('peak_aggregate_rss_bytes'), 'sampled RSS', 1)
    require(peak < 8 * 1024**3 and integer(resource.get('nonempty_samples'), 'RSS samples', 1) <= integer(resource.get('samples'), 'RSS samples', 1), 'Missing samples or RSS limit exceeded')
    require(resource.get('remaining_observed_processes') == [], 'Owned processes remain')


def environment_check(root, environment, sources):
    require(isinstance(environment, dict) and environment.get('status') == 'PASS' and environment.get('reasons') == [], 'Environment did not pass')
    require(environment.get('julia_version') == '1.12.7', 'Wrong Julia serialization/runtime version')
    paths = {'project_sha256': 'environment/workbench/Project.toml', 'manifest_sha256': 'environment/workbench/Manifest.toml', 'source_lock_sha256': 'config/sources.lock'}
    for key, path in paths.items():
        require(environment.get(key) == sources['frozen_inputs_and_history'][path]['sha256'] == sha(root / path), 'Frozen environment hash mismatch: ' + key)
    require(environment.get('active_project') == '<workbench>/' + paths['project_sha256'] and environment.get('active_manifest') == '<workbench>/' + paths['manifest_sha256'], 'Wrong loaded environment path')
    manifest = tomllib.loads((root / paths['manifest_sha256']).read_text())
    lock = tomllib.loads((root / paths['source_lock_sha256']).read_text())
    packages = environment.get('packages')
    require(isinstance(packages, dict) and set(packages) == {'dftk', 'pseudopotentialio'}, 'Incomplete loaded package identities')
    for short, package in (('dftk', 'DFTK'), ('pseudopotentialio', 'PseudoPotentialIO')):
        record = packages[short]; expected = manifest['deps'][package][0]
        for field in ('uuid', 'version'):
            require(record.get(field) == record.get('expected_' + field) == expected[field], 'Wrong actual package ' + field)
        require(record.get('commit') == record.get('expected_commit') == lock['source'][short]['commit'] and record.get('worktree_status') == 'clean', 'Wrong/dirty loaded checkout')
        path = '<workbench>/' + lock['source'][short]['checkout'] + '/src/' + package + '.jl'
        require(record.get('path') == record.get('expected_path') == path, 'Wrong loaded source path')


def source_check(root, worker, sources):
    require(worker.get('reference_source_sha256') == sources['reference_implementation']['files'], 'Reference source identity differs')
    execution = hex_value(worker['execution_commit'], 40)
    require(set(worker.get('harness_sources', {})) == {'measure.jl', 'memory.jl'}, 'Missing executed measurement source')
    for path, expected in worker['harness_sources'].items():
        require(hashlib.sha256(git_bytes(root, execution, BENCH + path)).hexdigest() == hex_value(expected), 'Executed harness Git blob differs')
    if worker['suite'].startswith('CORE-'):
        command = ['git', '-C', str(root), 'ls-tree', '-r', '--name-only', execution, '--', 'src', 'prototypes', 'scripts/workbench_environment.jl', 'scripts/upf_validation.jl', 'scripts/upf_runtime.jl']
        paths = [p for p in subprocess.check_output(command, text=True).splitlines() if p.endswith('.jl')]
        mapping = worker.get('candidate_source_sha256')
        require(isinstance(mapping, dict) and set(mapping) == set(paths), 'Candidate source map is incomplete')
        for path, expected in mapping.items():
            require(hashlib.sha256(git_bytes(root, execution, path)).hexdigest() == hex_value(expected), 'Executed candidate Git blob differs: ' + path)


def compact_storage(graph):
    """Validate the actual private owner graph, then aggregate sizes, not arrays."""
    require(graph.get('status') == 'COMPLETE_FOR_RECOGNIZED_JULIA_STORAGE' and graph.get('unaccounted_arrays') == [], 'Incomplete storage census')
    storage = graph.get('storage'); arrays = graph.get('arrays')
    require(isinstance(storage, list) and isinstance(arrays, list), 'Missing actual owner/array graph')
    require(len(storage) == integer(graph.get('backing_owners'), 'owner count', 1) and len(arrays) == integer(graph.get('array_objects'), 'array count', 1), 'Storage count differs from actual graph')
    require([row.get('storage_id') for row in storage] == list(range(1, len(storage) + 1)), 'Duplicate/missing owner IDs')
    ids = [integer(row.get('object_id'), 'array object id', 1) for row in arrays]
    require(len(ids) == len(set(ids)), 'Duplicate array wrapper identity')
    wrappers = {row['object_id']: row for row in arrays}
    for row in arrays:
        owner = integer(row.get('storage_id'), 'array owner id', 1)
        require(owner <= len(storage), 'Array refers to an absent owner')
        parent = row.get('parent_object_id')
        require(parent is None or (type(parent) is int and parent in ids and parent != row['object_id']), 'Invalid parent/alias edge')
        visited = {row['object_id']}
        while parent is not None:
            require(parent not in visited and wrappers[parent]['storage_id'] == owner, 'Cyclic or different-owner parent edge')
            visited.add(parent); parent = wrappers[parent]['parent_object_id']
            require(parent is None or (type(parent) is int and parent in wrappers), 'Invalid parent chain')
    groups = Counter()
    for row in storage:
        integer(row['storage_id'], 'owner ID', 1)
        size = integer(row.get('sizeof_payload_bytes'), 'owner bytes')
        integer(row.get('allocated_elements'), 'owner capacity')
        path = row.get('first_path'); element = row.get('element_type')
        require(isinstance(path, str) and path.startswith('roots.') and isinstance(element, str) and element, 'Unlabeled owner')
        category = 'source_registry' if path.startswith('roots.source_registry.') else 'context_registry' if path.startswith('roots.context_registry.') else 'other_retained_roots'
        groups[(category, size)] += 1
    result = {key: graph[key] for key in ('status', 'combined_summarysize_bytes', 'dense_unique_payload_bytes', 'backing_owner_payload_sum_bytes', 'overlap_payload_bytes', 'backing_owners', 'array_objects', 'opaque_pointer_fields')}
    result.update(owner_size_histogram=[dict(category=category, payload_bytes=size, count=count) for (category, size), count in sorted(groups.items())],
                  private_graph_canonical_sha256=object_sha(graph), evidence_level='RUNNER_REPORTED_OWNER_IDENTITY_PUBLIC_SIZE_ARITHMETIC')
    storage_arithmetic(result)
    return result


def storage_arithmetic(graph):
    require(graph.get('status') == 'COMPLETE_FOR_RECOGNIZED_JULIA_STORAGE', 'Incomplete storage evidence')
    hex_value(graph['private_graph_canonical_sha256'])
    rows = graph.get('owner_size_histogram')
    require(isinstance(rows, list) and rows, 'Owner histogram missing')
    seen = set(); count = total = registry = 0
    for row in rows:
        category = row.get('category'); size = integer(row.get('payload_bytes'), 'owner size'); n = integer(row.get('count'), 'owner count', 1)
        require(category in ('source_registry', 'context_registry', 'other_retained_roots') and (category, size) not in seen, 'Duplicate/unrecognized owner size class')
        seen.add((category, size)); count += n; total += n * size
        if category != 'other_retained_roots':
            registry += n * size
    require(count == integer(graph.get('backing_owners'), 'backing owners') and total == integer(graph.get('backing_owner_payload_sum_bytes'), 'owner sum'), 'Owner histogram arithmetic differs')
    unique = integer(graph.get('dense_unique_payload_bytes'), 'unique payload')
    overlap = integer(graph.get('overlap_payload_bytes'), 'overlap')
    require(unique > 0 and total - overlap == unique and overlap == 0, 'Unreplayable address overlap or fake unique storage total')
    require(integer(graph.get('combined_summarysize_bytes'), 'combined size') >= unique, 'Combined object size smaller than backing payload')
    return dict(unique_payload_bytes=unique, registry_owner_payload_bytes=registry, backing_owners=count)


def suite_check(root, suite, entry, execution, sources, *, private=False):
    outer, worker, native, resource = (entry[key] for key in ('outer', 'worker', 'native', 'resource'))
    expected = REFERENCE if suite.startswith('REF-') else execution
    require(outer.get('suite') == worker.get('suite') == suite and outer.get('execution_commit') == worker.get('execution_commit') == expected, 'Wrong suite/execution identity')
    require(isinstance(outer.get('run_id'), str) and outer['run_id'].startswith(suite + '-') and outer['run_id'] == worker.get('run_id'), 'Stale/wrong run identity')
    require(type(worker.get('schema_version')) is int and worker['schema_version'] == 1 and worker.get('phase') == '9A', 'Unsupported worker schema')
    require(worker.get('base_commit') == BASE and worker.get('preparation_commit') == PREPARATION, 'Wrong worker base/preparation')
    require(worker.get('backend') == ('LEGACY_REFERENCE' if suite.startswith('REF-') else 'OWNED_CORE'), 'Wrong numerical backend')
    require(outer.get('overall_status') == worker.get('overall_status') == worker.get('execution_status') == 'PASS' and worker.get('measurement_status') == 'COMPLETE', 'Unsuccessful/incomplete measurement suite')
    require(type(worker.get('exit_code')) is int and worker['exit_code'] == 0, 'Worker failure')
    resource_check(outer, native, resource)
    require(hex_value(entry['raw_worker_sha256']) == outer.get('worker_result_sha256'), 'Raw worker receipt identity differs')
    environment_check(root, worker['environment'], sources)
    source_check(root, worker, sources)
    require(worker.get('parallelism') == dict(julia=1, blas=1, fft=1, mpi=1) and all(type(v) is int for v in worker['parallelism'].values()), 'Different parallelism')
    require(worker.get('input_unchanged') == dict(payload=True, rhs=True, checkpoint=True, original_result=True) and all(v is True for v in worker['input_unchanged'].values()), 'Original inputs changed')
    label = suite.split('-')[1]; old = sources['historical_endpoints'][label]; inp = worker['input']
    for key in ('checkpoint_sha256', 'checkpoint_bytes', 'raw_result_sha256'):
        require(inp.get(key) == old[key], 'Historical input identity differs: ' + key)
    require(inp.get('historical_execution_commit') == old['execution_commit'] and inp.get('historical_status') == 'HISTORICAL_REUSED', 'Historical input mislabeled')
    require(type(inp.get('k_count')) is int and inp['k_count'] == (8 if label == 'B0' else 64) and type(inp.get('target_states')) is int and inp['target_states'] == 24, 'Changed k/state counts')
    require(all(inp.get(key) is True for key in ('no_scf', 'no_eigensolve', 'no_occupation_solve')), 'Static scope changed')
    for key in ('physical_payload_sha256', 'case_sha256', 'n_in_sha256', 'n_out_sha256'):
        hex_value(inp[key])
    require(worker['canonical_inputs']['sha256'] == inp['physical_payload_sha256'], 'Physical payload descriptor differs')
    require(set(worker.get('measurements', {})) == set(worker.get('outputs', {})) == OPERATIONS, 'Incomplete operation/output matrix')
    statistics = {name: sample_statistics(worker['measurements'][name], name) for name in sorted(OPERATIONS)}
    for name in MICRO:
        dispatch_check(worker['measurements'][name], name, suite.startswith('CORE-'))
    cold = worker.get('cold_initialization')
    require(isinstance(cold, dict) and set(cold) == {'context_construction', 'H_construction'}, 'Missing separate cold construction costs')
    for item in cold.values():
        require(isinstance(item, dict) and set(item) == {'time', 'bytes', 'gctime', 'compile_time', 'recompile_time', 'lock_conflicts'}, 'Incomplete cold timing record')
        for key, value in item.items():
            number(value, 'cold/' + key)
            if key in ('bytes', 'lock_conflicts'):
                integer(value, 'cold/' + key)
    require(set(worker.get('live_memory', {})) == set(PHASES), 'Missing lifecycle census')
    memories = {phase: compact_storage(worker['live_memory'][phase]) if private else worker['live_memory'][phase] for phase in PHASES}
    for graph in memories.values():
        storage_arithmetic(graph)
    lifetime = worker['legacy_lifetime']; expected_count = 7 if suite.startswith('REF-') else 0
    for key in ('expected_contexts', 'global_source_registrations', 'global_context_registrations'):
        require(type(lifetime.get(key)) is int and lifetime[key] == expected_count, 'Unaccounted context/source registrations')
    require(lifetime.get('registry_cleared') is False and lifetime.get('forced_gc') is False, 'Altered registry/GC observation')
    require(lifetime.get('close_api') == ('NONE' if expected_count else 'SCOPED_PRIVATE_OWNERS'), 'Incorrect close boundary')
    if not expected_count:
        before = worker['runtime_before_close']; after = worker['runtime_after_close']
        require(before.get('backend') == after.get('backend') == 'soc-core' and before.get('closed') is False and after.get('closed') is True and after.get('workspace_released') is True, 'Owned runtime not closed/released')
        require(integer(before.get('owned_source_entries'), 'owned sources before', 1) > 0 and type(after.get('owned_source_entries')) is int and after['owned_source_entries'] == 0, 'Sources not scoped/released')
        require(integer(before.get('max_rhs'), 'RHS capacity') == integer(after.get('max_rhs'), 'closed RHS capacity') == 30 and before.get('workspace_capacity', {}).get('max_rhs') == 30, 'Wrong actual runtime capacity')
    return statistics, memories


def expected_comparison_labels(nk):
    arrays = set(MICRO) | {'pipeline/actions/' + k for k in MICRO}
    scalars = set()
    for prefix in ('density', 'energy', 'pipeline/density', 'pipeline/energy'):
        arrays |= {prefix + '/' + key for key in ('R', 'n', 'm')}
    for prefix in ('nonlocal', 'pipeline/nonlocal'):
        scalars |= {prefix + '/' + key for key in ('direct_ha', 'projected_ha')}
    for prefix in ('energy', 'pipeline/energy'):
        scalars |= {prefix + '/' + key for key in SCALARS}
        scalars |= {prefix + '/terms_ha/' + key for key in TERMS}
    arrays |= {f'operators/{k}/{part}' for k in range(1, nk + 1) for part in ('P', 'D')}
    return arrays, scalars


def comparison_check(comparison, suites, execution, contract):
    require(type(comparison.get('schema_version')) is int and comparison['schema_version'] == 1 and comparison.get('phase') == '9A' and comparison.get('execution_commit') == execution, 'Wrong comparison identity')
    require(comparison.get('overall_status') in ('PASS', 'FAIL') and type(comparison.get('exit_code')) is int and comparison['exit_code'] == (0 if comparison['overall_status'] == 'PASS' else 9), 'Comparison status/exit conflict')
    require(comparison.get('environment', {}).get('status') == 'PASS', 'Comparison environment failed')
    pairs = comparison.get('pairs'); require(isinstance(pairs, list) and [p.get('label') for p in pairs] == ['B0', 'K4'], 'Both complete comparison pairs required')
    statuses = []
    for pair in pairs:
        label = pair['label']; old = suites['REF-' + label]; new = suites['CORE-' + label]
        require(pair.get('reference') == old['raw_outer_descriptor'] and pair.get('candidate') == new['raw_outer_descriptor'], 'Comparison bound to different runs')
        require(pair.get('input_identity') == old['worker']['input']['physical_payload_sha256'] == new['worker']['input']['physical_payload_sha256'] and pair.get('checkpoint_sha256') == old['worker']['input']['checkpoint_sha256'] == new['worker']['input']['checkpoint_sha256'], 'Comparison input identity differs')
        arrays, scalars = expected_comparison_labels(8 if label == 'B0' else 64)
        rows = pair.get('rows'); require(isinstance(rows, list) and len(rows) == len(arrays | scalars), 'Missing comparison rows')
        mapping = {r['label']: r for r in rows}; require(set(mapping) == arrays | scalars, 'Duplicate or missing comparison labels')
        results = []
        for name, row in mapping.items():
            limit = 0.0 if name.endswith('/entropy_dimensionless') else contract['accuracy']['energy_each_and_total_abs_ha'] if name in scalars else contract['accuracy']['operator_relative']
            require(row.get('limit') == limit, 'Altered comparison tolerance')
            if name in arrays:
                require(row.get('kind') == 'array' and row.get('evidence_level') == 'RUNNER_REPORTED_PRIVATE_ARRAY_COMPARISON', 'Array evidence mislabeled')
                a = number(row.get('reference_norm'), name); b = number(row.get('candidate_norm'), name); delta = number(row.get('absolute_L2'), name)
                require(row.get('relative') == delta / max(a, b, 1), 'Relative norm arithmetic differs')
                number(row.get('max_abs'), name); require(type(row.get('bitwise_equal')) is bool, 'Missing exact-array diagnostic')
                require(row['max_abs'] <= delta + 1e-30 and (not row['bitwise_equal'] or delta == row['max_abs'] == 0), 'Array norm/identity contradiction')
                ok = row['relative'] <= limit
            else:
                require(row.get('kind') == 'scalar' and row.get('evidence_level') == 'PUBLIC_ARITHMETIC', 'Scalar evidence mislabeled')
                require(row.get('unit') == ('dimensionless' if name.endswith('/entropy_dimensionless') else 'Ha/cell'), 'Incorrect scalar unit')
                a = number(row.get('reference'), name, -math.inf); b = number(row.get('candidate'), name, -math.inf)
                require(row.get('difference') == b - a, 'Signed scalar difference differs')
                ok = abs(b - a) <= limit
            require(row.get('status') == ('PASS' if ok else 'FAIL'), 'False comparison row status')
            results.append(ok)
        for prefix in ('energy', 'pipeline/energy'):
            for side in ('reference', 'candidate'):
                terms = sum(mapping[prefix + '/terms_ha/' + key][side] for key in TERMS)
                energy = mapping[prefix + '/internal_energy_ha'][side]
                entropy = mapping[prefix + '/entropy_energy_ha'][side]
                require(abs(terms - energy) <= 1e-10 and abs(mapping[prefix + '/free_energy_ha'][side] - energy - entropy) <= 1e-10, 'Seven-term/E/F arithmetic differs')
                require(abs(entropy + .001 * mapping[prefix + '/entropy_dimensionless'][side]) <= 1e-10, 'Entropy unit/sign arithmetic differs')
        integrals = pair.get('density_integrals')
        require(isinstance(integrals, list) and [r.get('label') for r in integrals] == ['density', 'energy', 'pipeline'], 'Missing same-source density integrals')
        for row in integrals:
            limit = contract['accuracy']['valence_electron_abs']; require(row.get('electron_limit') == limit, 'Changed electron tolerance')
            for side in ('reference', 'candidate'):
                value = number(row.get(side + '_electrons'), 'electrons')
                require(row.get(side + '_error') == value - 8, 'Electron residual differs')
            ok = max(abs(row['reference_error']), abs(row['candidate_error'])) <= limit
            require(row.get('status') == ('PASS' if ok else 'FAIL'), 'False electron status'); results.append(ok)
        passed = all(results); require(pair.get('status') == ('PASS' if passed else 'FAIL'), 'False pair status'); statuses.append(passed)
    passed = all(statuses)
    require(comparison['overall_status'] == ('PASS' if passed else 'FAIL'), 'False overall numerical comparison status')
    return 'PASS' if passed else 'FAIL'


def assessment(root, data, comparison, *, private=False):
    finite(data); finite(comparison)
    require(type(data.get('schema_version')) is int and data['schema_version'] == 1 and data.get('phase') == '9A', 'Unsupported replay schema')
    execution = hex_value(data['execution_commit'], 40)
    contract, sources = preparation(root)
    suites = data.get('suites'); require(isinstance(suites, dict) and set(suites) == set(SUITES), 'Exactly four static runs required')
    stats = {}; memory = {}
    for name in SUITES:
        stats[name], memory[name] = suite_check(root, name, suites[name], execution, sources, private=private)
    environment_check(root, comparison.get('environment'), sources)
    comparison_source_check(root, comparison, execution)
    equivalence = comparison_check(comparison, suites, execution, contract)
    pairs = {}; time_review = False; allocation_pass = True; live_pass = False
    for label in ('B0', 'K4'):
        ref = 'REF-' + label; core = 'CORE-' + label
        for key in ('checkpoint_sha256', 'physical_payload_sha256', 'case_sha256', 'n_in_sha256', 'n_out_sha256', 'target_states', 'k_count'):
            require(suites[ref]['worker']['input'][key] == suites[core]['worker']['input'][key], 'Different corresponding static inputs')
        ratios = {}
        for name in sorted(OPERATIONS):
            a = stats[ref][name]; b = stats[core][name]
            require(a['allocated_bytes']['median'] > 0 and a['time_seconds']['median'] > 0, 'Nonpositive reference ratio denominator')
            allocation = b['allocated_bytes']['median'] / a['allocated_bytes']['median']
            time = b['time_seconds']['median'] / a['time_seconds']['median']
            limit = contract['performance']['FR_24_allocation_median_ratio_max'] if name == 'FR_24' else contract['performance']['pipeline_allocation_median_ratio_max'] if name == 'pipeline' else None
            ok = limit is None or allocation <= limit
            review = time > contract['performance']['time_median_ratio_review_above']
            allocation_pass &= ok; time_review |= review
            ratios[name] = dict(allocation_median_ratio=allocation, allocation_limit=limit, allocation_status='NOT_GATED' if limit is None else 'PASS' if ok else 'FAIL', time_median_ratio=time, time_status='PERFORMANCE_REVIEW_REQUIRED' if review else 'PASS')
        old = storage_arithmetic(memory[ref]['session_closed']); new = storage_arithmetic(memory[core]['session_closed'])
        reduction = old['unique_payload_bytes'] - new['unique_payload_bytes']
        registry_reduction = old['registry_owner_payload_bytes'] - new['registry_owner_payload_bytes']
        measurable = reduction > 0 and registry_reduction > 0
        live_pass |= measurable
        pairs[label] = dict(operations=ratios, live_storage=dict(reference=old, candidate=new, unique_payload_reduction_bytes=reduction, registry_owner_payload_reduction_bytes=registry_reduction, status='PASS' if measurable else 'NO_MEASURABLE_REDUCTION', evidence_level='RUNNER_REPORTED_OWNER_IDENTITY_PUBLIC_SIZE_ARITHMETIC'))
    passed = equivalence == 'PASS' and allocation_pass and live_pass
    result = dict(schema_version=1, phase='9A', execution_commit=execution, overall_status='PASS' if passed else 'FAIL', exit_code=0 if passed else 9,
                  identity_status='PASS', resource_status='PASS', equivalence_status=equivalence,
                  allocation_status='PASS' if allocation_pass else 'FAIL', live_storage_reduction_status='PASS' if live_pass else 'FAIL',
                  time_status='PERFORMANCE_REVIEW_REQUIRED' if time_review else 'PASS', statistics=stats, pairs=pairs,
                  contract_sha256=PREPARED_HASHES['contract.json'], scope='Recorded five-sample, norm/scalar and owner-size arithmetic only; private array evaluation, object identity/reachability and RSS observations are RUNNER_REPORTED; no kernel or waveform replay')
    return result, memory


def comparison_source_check(root, comparison, execution):
    record = comparison.get('arithmetic_sources')
    expected = {BENCH + 'compare.jl', 'scripts/workbench_environment.jl'}
    require(isinstance(record, dict) and record.get('execution_commit') == execution and set(record.get('source_sha256', {})) == expected, 'Missing original arithmetic source binding')
    for path, identity in record['source_sha256'].items():
        require(hashlib.sha256(git_bytes(root, execution, path)).hexdigest() == hex_value(identity), 'Arithmetic source Git blob differs')


def tools_module(root):
    spec = importlib.util.spec_from_file_location('soc_core_static_protocol', root / (BENCH + 'run.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def gate_tool_guard(root, execution):
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    require(head == hex_value(execution, 40), 'Gate must use the exact candidate HEAD')
    require(not subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain', '--untracked-files=all'], text=True).strip(), 'Gate requires a clean execution tree')
    mapping = {}
    for path in ('scripts/replay_soc_core_memory.py', BENCH + 'run.py'):
        local = root / path
        require(not local.is_symlink() and local.read_bytes() == git_bytes(root, execution, path), 'Uncommitted gate/protocol tool: ' + path)
        mapping[path] = sha(local)
    return mapping


def write_new(path, value):
    finite(value)
    with path.open('x') as handle:
        handle.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')


def build_gate(root, request_path, output):
    root = Path(root).resolve(); output = Path(output).absolute()
    require(root / '.work/phase9a' in output.parents and not output.exists() and output.resolve() == output, 'A new confined output directory is required')
    output.mkdir(parents=True, exist_ok=False)
    gate = dict(schema_version=1, phase='9A', overall_status='FAIL', exit_code=9)
    try:
        request = read(request_path); execution = hex_value(request['execution_commit'], 40); gate['execution_commit'] = execution
        require(set(request['suite_receipts']) == set(SUITES), 'All four static receipts required')
        gate_sources = gate_tool_guard(root, execution)
        tool = tools_module(root); tool.preparation(root)
        data = dict(schema_version=1, phase='9A', execution_commit=execution, gate_tool_sources=gate_sources, suites={})
        for suite in SUITES:
            entry = request['suite_receipts'][suite]
            outer, path = bound(root, entry, private=True)
            tool.prior_contract(outer, path.parent)
            worker = read(path.parent / 'worker-result.json')
            data['suites'][suite] = dict(outer=outer, worker=worker, native=read(path.parent / 'process-exit.json'), resource=read(path.parent / 'resource.json'), raw_worker_sha256=sha(path.parent / 'worker-result.json'), raw_outer_descriptor=entry)
        comparison, comparison_path = bound(root, request['comparison'], private=True)
        performance, memories = assessment(root, data, comparison, private=True)
        for suite, entry in data['suites'].items():
            worker = entry['worker']
            # Preserve timing samples and checksums but not full native type or
            # repeated object graphs. All original worker bytes remain private.
            keep = ('schema_version', 'phase', 'suite', 'run_id', 'execution_commit', 'base_commit', 'preparation_commit', 'backend', 'overall_status', 'execution_status', 'exit_code', 'measurement_status', 'environment', 'parallelism', 'input_unchanged', 'input', 'canonical_inputs', 'canonical_operators', 'outputs', 'measurements', 'cold_initialization', 'legacy_lifetime', 'runtime_before_close', 'runtime_after_close', 'reference_source_sha256', 'candidate_source_sha256', 'harness_sources')
            entry['worker'] = {key: value for key, value in worker.items() if key in keep}
            entry['worker']['input'] = {key: value for key, value in worker['input'].items() if key != 'native_type'}
            entry['worker']['live_memory'] = memories[suite]
        write_new(output / 'replay-data.json', data)
        write_new(output / 'performance.json', performance)
        # Re-evaluate the exact public representation before publishing a gate.
        public_result, _ = assessment(root, read(output / 'replay-data.json'), comparison)
        require(public_result == performance, 'Public/private arithmetic projection differs')
        require(gate_tool_guard(root, execution) == gate_sources, 'Gate tool source changed during assessment')
        gate.update({key: performance[key] for key in ('overall_status', 'exit_code', 'identity_status', 'equivalence_status', 'allocation_status', 'resource_status', 'live_storage_reduction_status', 'time_status')})
        gate.update(gate_tool_sources=gate_sources, suite_receipts=request['suite_receipts'], comparison=request['comparison'], performance=descriptor(root, output / 'performance.json'), replay_data=descriptor(root, output / 'replay-data.json'))
    except Exception as error:
        gate.update(overall_status='FAIL', exit_code=9, reason=str(error))
    # gate.json is the final publication. No earlier file grants permission.
    write_new(output / 'gate.json', gate)
    return gate


def replay(root, evidence):
    root = Path(root).resolve(); manifest = read(evidence)
    require(type(manifest.get('schema_version')) is int and manifest['schema_version'] == 1 and manifest.get('phase') == '9A', 'Wrong public evidence schema')
    data, _ = bound(root, manifest['replay_data']); comparison, _ = bound(root, manifest['comparison'])
    recorded, _ = bound(root, manifest['performance']); gate, _ = bound(root, manifest['gate'])
    require(manifest.get('execution_commit') == data.get('execution_commit') == gate.get('execution_commit'), 'Mixed publication/execution identity')
    require(gate.get('gate_tool_sources') == data.get('gate_tool_sources') and isinstance(data.get('gate_tool_sources'), dict) and set(data['gate_tool_sources']) == {'scripts/replay_soc_core_memory.py', BENCH + 'run.py'}, 'Missing original gate tool binding')
    for path, expected in data['gate_tool_sources'].items():
        require(hashlib.sha256(git_bytes(root, data['execution_commit'], path)).hexdigest() == hex_value(expected), 'Original gate tool Git blob differs')
    for key in ('comparison', 'performance', 'replay_data'):
        require(gate.get(key, {}).get('sha256') == manifest[key]['sha256'], 'Public data bytes differ from the original gate: ' + key)
    fresh, _ = assessment(root, data, comparison)
    require(exact_record(recorded, fresh), 'Published performance arithmetic/status differs')
    for key in ('overall_status', 'exit_code', 'identity_status', 'equivalence_status', 'allocation_status', 'resource_status', 'live_storage_reduction_status', 'time_status'):
        require(type(gate.get(key)) is type(fresh[key]) and gate[key] == fresh[key], 'Published gate contradicts arithmetic: ' + key)
    require(gate.get('suite_receipts') == {name: data['suites'][name]['raw_outer_descriptor'] for name in SUITES}, 'Gate refers to different original static runs')
    return dict(schema_version=1, phase='9A', execution_commit=data['execution_commit'], replay_status='PASS', replay_exit_code=0,
                assessment_status=fresh['overall_status'], assessment_exit_code=fresh['exit_code'], time_status=fresh['time_status'],
                scope=fresh['scope'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    build = sub.add_parser('build-gate'); build.add_argument('--request', required=True); build.add_argument('--output', required=True)
    public = sub.add_parser('replay'); public.add_argument('--evidence', required=True)
    for command in (build, public):
        command.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        result = build_gate(args.root, args.request, args.output) if args.action == 'build-gate' else replay(args.root, args.evidence)
        print(json.dumps(result, allow_nan=False))
        return result.get('exit_code', result.get('replay_exit_code', 9))
    except Exception as error:
        print(json.dumps(dict(overall_status='FAIL', exit_code=9, reason=str(error)), allow_nan=False))
        print('Recorded-evidence replay failed: ' + str(error), file=sys.stderr)
        return 9


if __name__ == '__main__':
    sys.exit(main())
