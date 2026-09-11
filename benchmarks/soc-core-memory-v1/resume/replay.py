#!/usr/bin/env python3
"""Public Phase9A continuation arithmetic. No private data or numerical worker.

Default exit 0 certifies replay of the recorded delivery, including FAIL or
BLOCKED endpoints. --require-endpoints exits 1 unless both endpoints and their
comparisons passed. Invalid/missing evidence exits 2. Original static evidence,
the failed first attempt and all scientific reviews remain separate and intact.
"""
import argparse
import ast
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys

SELF = 'benchmarks/soc-core-memory-v1/resume/replay.py'
AREA = 'results/soc-core-memory/completion/'
MANIFEST = AREA + 'evidence.json'
PLAN = 'benchmarks/soc-core-memory-v1/resume/plan.json'
PARTIAL = '98781fd0ce6c2f4138ed010e115a13e370410d58'
PREPARATION = '234fe85d4e9386d9889bd1af256a28394ba88089'
STATIC = '1b42a27063ca65757d2c4f34d46fe4f1cd9929ed'
RESUME = 'phase9a-completion-20260910'
EXECUTION = '281c53525a70cf21c36973956d5303d3201a73eb'
AUTHORIZATION_SHA256 = '119447d08eb037475696e26829799a56d8bc6865fb7ef438e836a55d9bf7b59b'
ACTIONS = {'OPT-B0-SCF': 2, 'OPT-B0-GAMMA': 1}
RAW_ARRAY_KEYS = {'R', 'rho', 'wavefunctions', 'orbitals', 'psi', 'X', 'P', 'D', 'G_vectors'}
IDENTITY_KEYS = {'schema_version', 'phase', 'case', 'action', 'run_id', 'base_commit', 'preparation_commit',
                 'execution_commit', 'endpoint_execution_commit', 'backend', 'core_gate_sha256', 'case_sha256', 'resume_id', 'resume_from_commit',
                 'resume_preparation_commit', 'static_execution_commit', 'resume_authorization_sha256', 'attempt',
                 'started_utc', 'finished_utc', 'execution_status', 'exit_code', 'reason'}
OUTER_KEYS = IDENTITY_KEYS | {'worker_directory', 'worker_started', 'worker_exit_code', 'worker_result_sha256',
    'resource', 'failure_status', 'pseudo_sha256', 'native_process', 'log_labels', 'resume_authorization_path',
    'reservation_path', 'resource_failure_reason', 'command', 'check_only', 'formal_slot_reserved'}
WORKER_KEYS = IDENTITY_KEYS | {'executed_source_sha256', 'environment', 'input', 'grid', 'parallelism',
    'runtime', 'runtime_after_close', 'runtime_closed', 'runtime_dispatch_status', 'checkpoint_sha256',
    'final', 'spectrum', 'source_scf_run_id', 'density_source_sha256', 'parent_result_sha256',
    'parent_checkpoint_sha256', 'time_reversal', 'peak_rss_bytes', 'numerical_review_status',
    'cleanup_reason', 'last_map', 'completed_maps', 'last_progress', 'progress_records'}
WORKER_KEYS |= {'latest_map', 'latest_map_scope'}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def exact_hash(value, length=64):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(length) + '}', value), 'Invalid exact hash/commit')
    return value


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), 'Nonfinite or nonnumeric value')
    return value


def integer(value, minimum=0):
    require(type(value) is int and value >= minimum, 'Invalid integer')
    return value


def read(path):
    return json.loads(path.read_text(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Illegal JSON constant: ' + value)))


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE)


def blob(root, commit, path):
    return git(root, 'show', exact_hash(commit, 40) + ':' + path)


def tree(root, commit):
    result = {}
    for row in git(root, 'ls-tree', '-r', '-z', exact_hash(commit, 40)).split(b'\0'):
        if not row:
            continue
        prefix, name = row.split(b'\t'); mode, kind, oid = prefix.decode().split()
        require(kind == 'blob' and mode in ('100644', '100755'), 'Unexpected Git object type')
        result[name.decode()] = oid
    return result


def path(root, relative):
    require(isinstance(relative, str), 'Missing public relative path')
    part = Path(relative); value = root / part
    require(not part.is_absolute() and '..' not in part.parts and part.as_posix() == relative, 'Unconfined public path')
    require(value.is_file() and not value.is_symlink() and value.resolve() == value, 'Missing or aliased public file')
    return value


def artifact(root, entry):
    require(isinstance(entry, dict), 'Missing artifact descriptor')
    require(entry.get('path', '').startswith('results/'), 'Artifact must be public results data')
    p = path(root, entry['path']); data = p.read_bytes()
    require(sha(data) == exact_hash(entry.get('sha256')) and len(data) == integer(entry.get('bytes')), 'Artifact bytes changed: ' + entry['path'])
    if 'raw_sha256' in entry:
        exact_hash(entry['raw_sha256'])
    if p.suffix == '.gz':
        public = gzip.decompress(data)
        require(sha(public) == exact_hash(entry.get('public_text_sha256')) and len(public) == integer(entry.get('public_text_bytes')), 'Decompressed public bytes changed')
        exact_hash(entry.get('raw_sha256')); integer(entry.get('raw_bytes'))
        require(not re.search(rb'/(?:Users|home|private|Volumes|tmp)/', public), 'Private absolute path in public stream')
        return public.decode('utf-8'), p
    require(p.suffix == '.json', 'Only JSON and declared gzip streams accepted')
    return read(p), p


def module(root, relative, name):
    spec = importlib.util.spec_from_file_location(name, path(root, relative))
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def region(text, start, end):
    require(text.count(start) == 1, 'Ambiguous source boundary')
    begin = text.index(start)
    return text[begin:text.index(end, begin)]


def approved_constants(source):
    """Read literal routing approval only; never import the private controller."""
    names = {'APPROVED_ROUTING_SHA256', 'APPROVED_NEW_EXECUTABLES'}; values = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in names:
                    require(target.id not in values and len(node.targets) == 1, 'Ambiguous routing approval constant')
                    values[target.id] = ast.literal_eval(node.value)
    require(set(values) == names, 'Missing routing approval constants')
    routing, executables = values['APPROVED_ROUTING_SHA256'], values['APPROVED_NEW_EXECUTABLES']
    require(isinstance(routing, dict) and set(routing) == {'scripts/run_si_dftk.py', 'scripts/run_si_soc.jl',
            'benchmarks/soc-core-memory-v1/endpoint_metrics.py', 'benchmarks/soc-core-memory-v1/endpoint_compare.jl'}, 'Incomplete approved routing set')
    for checksum in routing.values():
        exact_hash(checksum)
    require(isinstance(executables, set) and all(isinstance(v, str) for v in executables), 'Invalid approved executable set')
    return routing, executables


def source_check(root, evidence, authorization):
    execution = exact_hash(evidence.get('endpoint_execution_commit'), 40)
    require(execution == EXECUTION, 'Only the actual signed continuation execution is accepted')
    head = exact_hash(git(root, 'rev-parse', 'HEAD').decode().strip(), 40)
    require(evidence.get('resume_id') == RESUME and evidence.get('resume_from_commit') == PARTIAL and
            evidence.get('resume_preparation_commit') == PREPARATION and evidence.get('static_execution_commit') == STATIC, 'Wrong continuation identity')
    require(not git(root, 'status', '--porcelain', '--untracked-files=all').strip(), 'Public checkout must be clean')
    git(root, 'merge-base', '--is-ancestor', execution, head)
    git(root, 'merge-base', '--is-ancestor', PARTIAL, execution)
    plan = json.loads(blob(root, PREPARATION, PLAN))
    require(path(root, PLAN).read_bytes() == blob(root, PREPARATION, PLAN), 'Preparation plan changed')
    previous, executed, current, measured = (tree(root, c) for c in (PARTIAL, execution, head, STATIC))
    control = blob(root, execution, 'benchmarks/soc-core-memory-v1/resume/control.py')
    routing, executables = approved_constants(control)
    for relative, checksum in routing.items():
        require(sha(blob(root, execution, relative)) == checksum, 'Execution routing differs from its approved exact bytes: ' + relative)
    require(set(previous) <= set(executed) <= set(current), 'Historical or execution file deleted')
    for rel, oid in current.items():
        data = path(root, rel).read_bytes()
        require(hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == oid, 'Current Git/file mismatch: ' + rel)
        if executed.get(rel) != oid:
            require(rel.startswith(AREA) or rel in plan['allowed_navigation'] or rel == SELF, 'Post-execution source change: ' + rel)
    require(path(root, SELF).read_bytes() == Path(__file__).read_bytes(), 'Running another replay implementation')
    proof = authorization.get('source_proof'); require(isinstance(proof, dict) and proof.get('status') == 'PASS', 'Missing original source proof')
    require(proof.get('static_execution_commit') == STATIC and proof.get('endpoint_execution_commit') == execution and
            proof.get('default_gate_rule') == proof.get('endpoint_numerical_functions') == 'UNCHANGED', 'Unbound source proof')
    allowed = set(plan['allowed_existing_code']) | set(plan['allowed_navigation']); changes = {}
    numerical = {}
    for rel, oid in executed.items():
        if rel in previous and previous[rel] != oid:
            require(rel in allowed, 'Unauthorized endpoint implementation change: ' + rel)
            changes[rel] = (previous[rel], oid)
        elif rel not in previous:
            require(any(rel.startswith(p) for p in plan['allowed_new_paths']), 'Unauthorized new execution source: ' + rel)
            if Path(rel).suffix in ('.py', '.jl', '.sh'):
                require(rel in executables, 'Unreviewed new execution/dispatch file: ' + rel)
        if rel.startswith(('src/', 'prototypes/')) or rel.startswith('scripts/') and rel.endswith('.jl') and rel != 'scripts/run_si_soc.jl':
            require(measured.get(rel) == previous.get(rel) == oid, 'Measured numerical source changed: ' + rel)
            numerical[rel] = sha(blob(root, execution, rel))
    require(numerical == proof.get('numerical_sources'), 'Recorded numerical source map differs from Git')
    require(set(k for k in measured if k.startswith(('src/', 'prototypes/'))) == set(k for k in numerical if k.startswith(('src/', 'prototypes/'))), 'Numerical source set changed')
    rows = proof.get('partial_to_endpoint_diff'); require(isinstance(rows, list), 'Missing allowed diff')
    require(len(rows) == len(changes) and {r['path']: (r['partial_blob'], r['endpoint_blob']) for r in rows} == changes, 'Recorded allowed diff differs')
    require(proof.get('new_files') == sorted(set(executed) - set(previous)), 'Recorded new source set differs')
    driver = blob(root, execution, 'scripts/run_si_soc.jl').decode()
    for row in plan['numerical_driver_regions']:
        require(sha(region(driver, row['start'], row['end']).encode()) == row['sha256'], 'Numerical driver region changed: ' + row['name'])
    for rel, start, end in (
        ('benchmarks/soc-core-memory-v1/endpoint_metrics.py', 'def evaluate(', '\ndef main('),
        ('benchmarks/soc-core-memory-v1/endpoint_compare.jl', '        accuracy=', '        require_value(arithmetic_source_identity'),
        ('scripts/run_si_dftk.py', 'def verify_core_gate(', '\ndef validate_core_worker(')):
        require(region(blob(root, PARTIAL, rel).decode(), start, end) == region(blob(root, execution, rel).decode(), start, end), 'Inherited formula or gate changed: ' + rel)
    return dict(status='PASS', actual_checkout_commit=head, endpoint_execution_commit=execution, static_execution_commit=STATIC,
                execution_control_sha256=sha(control), approved_routing_sha256=routing,
                scope='Exact public Git source identities; original private environment/checkpoint bindings RUNNER_REPORTED')


def resume_fields(record, auth, action):
    fields = dict(resume_id=RESUME, resume_from_commit=PARTIAL, resume_preparation_commit=PREPARATION,
                  static_execution_commit=STATIC, resume_authorization_sha256=auth['authorization_sha256'], attempt=ACTIONS[action])
    for key, expected in fields.items():
        require(type(record.get(key)) is type(expected) and record[key] == expected, 'Wrong resume field: ' + key)
    require(record.get('execution_commit') == record.get('endpoint_execution_commit') == auth['endpoint_execution_commit'] and
            record.get('core_gate_sha256') == auth['core_gate_sha256'], 'Wrong endpoint E/static gate')


def no_raw_arrays(record):
    if isinstance(record, dict):
        require(not (set(record) & RAW_ARRAY_KEYS), 'Private numerical array in public projection')
        for key, value in record.items():
            require(not (key in ('n_in', 'n_out', 'n_next') and isinstance(value, list)), 'Private real-space density array')
            no_raw_arrays(value)
    elif isinstance(record, list):
        for value in record:
            no_raw_arrays(value)
    elif isinstance(record, float):
        number(record)
    elif isinstance(record, str):
        require(not re.search(r'/(?:Users|home|private|Volumes|tmp)/', record), 'Private absolute path in public projection')


def resource_check(record, native):
    require(record.get('evidence_level') == 'RUNNER_REPORTED', 'RSS must remain a runner observation')
    require(type(record.get('native_exit_code')) is int and record['native_exit_code'] == native, 'RSS/native exit mismatch')
    integer(record.get('peak_aggregate_rss_bytes')); integer(record.get('samples')); integer(record.get('nonempty_samples'))
    number(record.get('elapsed_seconds'))
    require(record.get('limit_bytes') == 8 * 1024**3 and record.get('sample_interval_seconds') == .1, 'Changed resource limit/interval')
    if record.get('status') == 'PASS':
        require(record.get('owned_process_cleanup_status') == 'PASS' and record.get('remaining_observed_processes') == [] and
                0 < record['peak_aggregate_rss_bytes'] < record['limit_bytes'] and 0 < record['nonempty_samples'] <= record['samples'], 'Invalid reported resource success')


def trace_check(trace, worker, success, settings):
    require(trace.get('run_id') == worker['run_id'] and trace.get('evidence_level') == 'RUNNER_REPORTED', 'Unbound compact map trace')
    rows = trace.get('rows'); require(isinstance(rows, list), 'Missing all compact maps')
    require([integer(row.get('map_index'), 1) for row in rows] == list(range(1, len(rows) + 1)), 'Missing/reordered map')
    for row in rows:
        require(row.get('map_role') in ('iteration', 'closure') and row.get('status') in ('CONTINUE', 'CANDIDATE', 'PASS', 'FAIL'), 'Unknown map outcome')
        require(type(row.get('closure_checks_passed')) is bool, 'Missing closure decision')
        number(row['unmixed_residual_l2'])
        for key in ('n_in', 'n_out', 'n_next'):
            exact_hash(row[key]['sha256']); number(row[key]['electron_count'])
        diag = row['diagnostics']
        for key in ('internal_energy_ha', 'free_energy_ha', 'entropy_energy_ha', 'real_electron_count', 'orbital_electron_count',
                    'max_input_h_residual_ha', 'max_gram_norm', 'max_self_density_h_residual_ha', 'max_self_rayleigh_residual_ha', 'pauli_density_relative_l2'):
            number(diag[key])
        require(diag['consumed_input_sha256'] == row['n_in']['sha256'] and diag['orbital_density_sha256'] == row['n_out']['sha256'], 'Map density provenance differs')
    if success:
        require(rows and len(rows) == worker['final']['map_count'], 'Successful SCF missing completed maps')
        last = rows[-1]; diag = last['diagnostics']; thresholds = settings['thresholds']
        require(last['map_role'] == 'closure' and last['status'] == 'PASS' and last['closure_checks_passed'], 'Missing successful final closure')
        require(last['n_out']['sha256'] == worker['final']['n_out_sha256'] and last['n_in']['sha256'] == worker['final']['n_in_sha256'], 'Wrong final density hashes')
        limits = {'unmixed_residual_l2': thresholds['density_fixedpoint_l2'], 'max_input_h_residual_ha': thresholds['residual_ha'],
                  'max_gram_norm': thresholds['gram_norm'], 'max_self_density_h_residual_ha': thresholds['self_density_residual_ha'],
                  'max_self_rayleigh_residual_ha': thresholds['self_density_residual_ha'], 'pauli_density_relative_l2': thresholds['pauli_density_relative']}
        for key, limit in limits.items():
            value = last[key] if key == 'unmixed_residual_l2' else diag[key]
            require(0 <= value <= limit, 'Reported final closure threshold failed: ' + key)
        for key in ('internal_energy_ha', 'free_energy_ha', 'entropy_energy_ha', 'energy_terms_ha', 'max_input_h_residual_ha',
                    'max_gram_norm', 'max_self_density_h_residual_ha', 'max_self_rayleigh_residual_ha', 'pauli_density_relative_l2'):
            require(diag[key] == worker['final']['diagnostics'][key], 'Final trace/worker disagreement: ' + key)
        for key in ('real_electron_count', 'orbital_electron_count'):
            require(abs(diag[key] - 8) <= thresholds['electron_count_abs'], 'Reported final electron count failed')
        band = diag['band_completeness']; require(band['status'] == 'PASS' and band['target'] == 24 and
            band['threshold'] == settings['ensemble']['boundary_occupation_max'] and 0 <= number(band['maximum_top_occupation']) <= band['threshold'], 'Reported final band closure failed')
        stationarity = diag['occupation_stationarity']; require(stationarity['status'] in ('EVALUATED', 'NO_RESOLVABLE_PARTIAL_OCCUPATIONS') and
            0 <= number(stationarity['max_abs_residual_ha']) <= settings['ensemble']['stationarity_abs_ha'], 'Reported final stationarity failed')
        require(0 <= number(diag['rayleigh_occupations']['max_occupation_difference']) <= thresholds['self_rayleigh_occupation_abs'], 'Reported Rayleigh occupation closure failed')
        require(abs(sum(diag['energy_terms_ha'].values()) - diag['internal_energy_ha']) <= thresholds['energy_abs_ha'], 'Recorded final energy sum differs')
        for key, value in diag['energy_checks'].items():
            if key.endswith('difference_ha'):
                require(abs(number(value)) <= thresholds['energy_abs_ha'], 'Reported final energy consistency failed: ' + key)
    return dict(map_count=len(rows), status='RECORDED_MAPS_VALIDATED', evidence_level='RUNNER_REPORTED')


def endpoints_check(root, endpoints, auth, settings):
    slots = endpoints.get('slots'); require(isinstance(slots, dict) and set(slots) == set(ACTIONS), 'Exactly two endpoint slots required')
    workers = {}; summaries = {}
    for action, attempt in ACTIONS.items():
        slot = slots[action]; status = slot.get('status')
        require(status in ('PASS', 'FAIL', 'BLOCKED_PARENT', 'NOT_RUN'), 'Unknown endpoint status')
        require(type(slot.get('attempt')) is int and slot['attempt'] == attempt, 'Wrong cumulative attempt')
        if status in ('BLOCKED_PARENT', 'NOT_RUN'):
            require(slot.get('formal_slot_reserved') is False and slot.get('native_process_started') is False, 'Unrun slot claimed numerical execution')
            require(all(slot.get(k) is None for k in ('run_id', 'native_exit_code', 'recorder_exit_code', 'outer', 'worker', 'trace')), 'Unrun slot contains results/exits')
            if status == 'BLOCKED_PARENT':
                require(action == 'OPT-B0-GAMMA' and slots['OPT-B0-SCF']['status'] != 'PASS', 'False blocked parent')
            summaries[action] = dict(status=status, numerical_execution='NOT_RUN'); continue
        require(type(slot.get('formal_slot_reserved')) is bool and type(slot.get('native_process_started')) is bool, 'Missing formal reservation/process state')
        require(not slot['native_process_started'] or slot['formal_slot_reserved'], 'Native worker started without formal reservation')
        native, code = slot.get('native_exit_code'), slot.get('recorder_exit_code')
        require(type(code) is int and (native is None or type(native) is int), 'Invalid native/recorder code')
        outer, _ = artifact(root, slot['outer']); no_raw_arrays(outer); resume_fields(outer, auth, action)
        require(set(outer) <= OUTER_KEYS, 'Unreviewed outer projection fields: ' + str(sorted(set(outer) - OUTER_KEYS)))
        require(outer.get('run_id') == slot.get('run_id') and outer.get('action') == action and outer.get('backend') == 'soc-core' and
                outer.get('exit_code') == code and outer.get('worker_exit_code') == native and outer.get('execution_status') == status and
                outer.get('worker_started') == slot['native_process_started'], 'Outer contradicts declared slot')
        if native is not None:
            resource_check(outer['resource'], native)
        for stream in slot.get('streams', []):
            artifact(root, stream)
        worker = None
        if slot.get('worker') is not None:
            worker, _ = artifact(root, slot['worker']); no_raw_arrays(worker); resume_fields(worker, auth, action)
            require(set(worker) <= WORKER_KEYS, 'Unreviewed worker projection fields: ' + str(sorted(set(worker) - WORKER_KEYS)))
            require(outer.get('worker_result_sha256') == exact_hash(slot['worker'].get('raw_sha256')) and worker.get('run_id') == outer.get('worker_directory') and
                    worker['run_id'] == outer['run_id'] + '-dftk' and worker.get('action') == action and worker.get('backend') == 'soc-core', 'Worker/raw source binding differs')
            if slot.get('trace') is not None:
                require(action == 'OPT-B0-SCF', 'Gamma has an SCF trace')
                trace, _ = artifact(root, slot['trace']); no_raw_arrays(trace)
                trace_check(trace, worker, status == 'PASS', settings)
        if status == 'PASS':
            require(slot['formal_slot_reserved'] and slot['native_process_started'] and native == code == 0 and worker is not None and worker.get('execution_status') == 'PASS' and worker.get('exit_code') == 0 and
                    worker.get('runtime_closed') is True and worker.get('runtime_dispatch_status') == 'PASS' and outer['resource']['status'] == 'PASS', 'No successful native/worker/core endpoint')
            require(worker.get('runtime_after_close', {}).get('closed') is True and worker['runtime_after_close'].get('workspace_released') is True and
                    worker['runtime_after_close'].get('owned_source_entries') == 0, 'Runtime did not release ownership')
            require(worker.get('environment', {}).get('status') == 'PASS' and worker.get('input', {}).get('nlcc_present') is True and worker.get('grid', {}).get('status') == 'PASS', 'Missing frozen worker setup checks')
            for source, checksum in worker['executed_source_sha256'].items():
                require(sha(blob(root, auth['endpoint_execution_commit'], source)) == exact_hash(checksum), 'Worker executed source mismatch')
            for counter in ('fr_mul_calls', 'component_mul_calls', 'full_mul_calls'):
                integer(worker['runtime']['counters'][counter], 1)
            require(worker['runtime']['max_rhs'] == 30, 'Wrong owned workspace capacity')
            claim, _ = artifact(root, slot['reservation']); resume_fields(dict(claim, core_gate_sha256=auth['core_gate_sha256']), auth, action)
            require(claim.get('run_id') == outer['run_id'], 'Reservation belongs to another endpoint')
            process = slot.get('process'); require(isinstance(process, dict) and set(process) == {'process-start.json', 'process-exit.json', 'resource.json'}, 'Missing original process metadata')
            native_record, _ = artifact(root, process['process-exit.json']); resource_record, _ = artifact(root, process['resource.json'])
            start_record, _ = artifact(root, process['process-start.json'])
            require(native_record['exit_code'] == native == outer['worker_exit_code'] and native_record.get('interrupted') is False, 'Native exit/interruption differs')
            if 'native_process' in outer:
                require(native_record == outer['native_process'], 'Embedded/native process records differ')
            require(resource_record == {k: v for k, v in outer['resource'].items() if k != 'evidence_level'}, 'Public native resource differs')
            require(start_record.get('command') == outer.get('command'), 'Original process command differs')
            initial, _ = artifact(root, slot['initial_solver']); expected_count = 8 if action == 'OPT-B0-SCF' else 1
            require(initial.get('run_id') == worker['run_id'] and initial.get('evidence_level') == 'RUNNER_REPORTED' and
                len(initial['rows']) == expected_count, 'Missing initial subspace identity table')
            for i, row in enumerate(initial['rows'], 1):
                require(row['map_index'] == 1 and row['k_index'] == i and row['target_states'] == 24 and row['auxiliary_states'] == 6 and
                    row['initial_seed'] == (81001 if action == 'OPT-B0-SCF' else 81201) + i - 1 and
                    row['initial_source'] == 'Independent ComplexF64 Gaussian whole-column QR' and row['initial_unchanged'] is True and
                    0 <= number(row['initial_gram_norm']) <= settings['thresholds']['gram_norm'] and number(row['initial_imaginary_norm']) > 0,
                    'Initial state was not the declared fresh seeded whole-spinor state')
                exact_hash(row['initial_sha256'])
            if action == 'OPT-B0-SCF':
                require(slot.get('trace') is not None, 'Successful SCF missing full compact trace')
                final = worker['final']; number(final['mu_ha'])
                for key in ('eigenvalues_ha', 'occupations'):
                    require(isinstance(final.get(key), list) and len(final[key]) == 8 and
                            all(isinstance(row, list) and len(row) == 24 for row in final[key]), 'Missing original SCF8x24 table: ' + key)
                    for row in final[key]:
                        for value in row:
                            number(value)
                require(all(0 <= value <= 1 for row in final['occupations'] for value in row), 'Invalid capacity-one occupations')
                require(abs(sum(sum(row) for row in final['occupations']) / 8 - 8) <= settings['thresholds']['electron_count_abs'], 'Recorded SCF occupation electron count failed')
            workers[action] = worker
        else:
            require(code != 0 and isinstance(outer.get('reason'), str) and outer['reason'], 'Failure missing original nonzero reason')
            # A native/worker success followed by recorder/resource failure is
            # retained literally. Only an authoritative outer PASS is usable.
        summaries[action] = dict(status=status, native_exit_code=native, recorder_exit_code=code,
                                 resource_evidence_level='RUNNER_REPORTED')
    if 'OPT-B0-GAMMA' in workers:
        require('OPT-B0-SCF' in workers, 'Gamma succeeded without successful own SCF')
        scf, gamma = workers['OPT-B0-SCF'], workers['OPT-B0-GAMMA']
        require(gamma.get('source_scf_run_id') == scf['run_id'] and gamma.get('parent_result_sha256') == slots['OPT-B0-SCF']['worker']['raw_sha256'] and
                gamma.get('parent_checkpoint_sha256') == scf.get('checkpoint_sha256') and gamma.get('density_source_sha256') == scf['final']['n_out_sha256'], 'Gamma used another parent')
        require(gamma['spectrum']['fermi_energy_ha'] == scf['final']['mu_ha'], 'Gamma did not use its parent chemical potential')
        spectrum = gamma['spectrum']; require(spectrum.get('temperature_ha') == settings['ensemble']['tau_ha'] and
            spectrum.get('occupations_use') == 'DIAGNOSTIC_ONLY_NOT_DENSITY_FEEDBACK', 'Changed Gamma temperature/occupation meaning')
        require(len(spectrum['kpoints']) == 1, 'Only Gamma allowed'); point = spectrum['kpoints'][0]
        require(number(point['weight_spatial']) == 1 and len(point['residuals_ha']) == 24 and
            all(0 <= number(v) <= settings['thresholds']['residual_ha'] for v in point['residuals_ha']) and
            0 <= number(point['gram_frobenius']) <= settings['thresholds']['gram_norm'], 'Reported Gamma solve failed')
        tr = gamma['time_reversal']; require(tr['status'] == 'PASS' and len(tr['time_reversal']) == 1 and
            tr['time_reversal'][0]['bijection'] is True and 0 <= number(tr['time_reversal'][0]['normalized_error']) <= settings['thresholds']['time_reversal_normalized'], 'Reported Gamma time reversal failed')
    return workers, summaries


def density_check(root, density, auth, workers, slots, contract):
    require(density.get('execution_commit') == EXECUTION and type(density.get('exit_code')) is int and
        density.get('overall_status') in ('PASS', 'FAIL'), 'Wrong density arithmetic execution/status')
    sources = density.get('arithmetic_sources'); expected_paths = {'benchmarks/soc-core-memory-v1/endpoint_compare.jl',
        'benchmarks/soc-core-memory-v1/compare.jl', 'scripts/workbench_environment.jl',
        'benchmarks/soc-core-memory-v1/resume/control.py', PLAN}
    require(isinstance(sources, dict) and sources.get('execution_commit') == EXECUTION and
        set(sources.get('source_sha256', {})) == expected_paths, 'Missing density arithmetic source identity')
    for relative, checksum in sources['source_sha256'].items():
        require(sha(blob(root, EXECUTION, relative)) == exact_hash(checksum), 'Wrong density arithmetic Git source')
    if 'n_out' not in density:
        require(density['overall_status'] == 'FAIL' and density['exit_code'] != 0 and isinstance(density.get('reason'), str) and density['reason'], 'Incomplete density calculation cannot pass')
        return False
    binding = density['resume_authentication']; require(binding.get('status') == 'PASS' and
        binding.get('endpoint_execution_commit') == EXECUTION and binding.get('authorization_sha256') == AUTHORIZATION_SHA256 and
        binding.get('core_gate_sha256') == auth['core_gate_sha256'], 'Density used another authorization/gate')
    scf, gamma = workers['OPT-B0-SCF'], workers['OPT-B0-GAMMA']
    history = read(path(root, 'benchmarks/soc-core-memory-v1/sources.json'))['historical_endpoints']['B0']
    old = read(path(root, 'results/si-soc-splitting/D-SCF.json'))
    refs = density['sources']; require(refs['historical_status'] == 'HISTORICAL_REUSED' and
        refs['historical_checkpoint_sha256'] == history['checkpoint_sha256'] and refs['historical_execution_commit'] == history['execution_commit'] and
        refs['new_checkpoint_sha256'] == scf['checkpoint_sha256'] == gamma['parent_checkpoint_sha256'] and
        refs['new_scf_run_id'] == scf['run_id'] and refs['new_gamma_run_id'] == gamma['run_id'], 'Density checkpoint/source identities differ')
    for action, name in (('OPT-B0-SCF', 'scf_result_sha256'), ('OPT-B0-GAMMA', 'gamma_result_sha256')):
        require(refs[name] == slots[action]['worker']['raw_sha256'] == binding['endpoint_bindings'][action]['worker']['sha256'] and
            slots[action]['outer']['raw_sha256'] == binding['endpoint_bindings'][action]['recorder']['sha256'], 'Density original worker/recorder hashes differ')
    row = density['n_out']; require(row['evidence_level'] == 'RUNNER_REPORTED_PRIVATE_ENDPOINT_ARRAY_COMPARISON' and
        row['reference_sha256'] == old['final']['n_out_sha256'] and row['candidate_sha256'] == scf['final']['n_out_sha256'], 'Density state/hash differs')
    for key in ('reference_norm', 'candidate_norm', 'absolute_L2', 'relative'):
        require(type(row.get(key)) is float and number(row[key]) >= 0, 'Invalid normalized density scalar')
    require(row['relative'] == row['absolute_L2'] / max(row['reference_norm'], row['candidate_norm'], 1), 'Density norm quotient differs')
    require(row['limit'] == contract['endpoint']['n_out_relative_L2'], 'Changed density threshold')
    passed = row['relative'] <= row['limit']
    require(row['status'] == ('PASS' if passed else 'FAIL'), 'Density scalar/status contradiction')
    if density['overall_status'] == 'PASS':
        require(passed and density['exit_code'] == 0, 'Density success contradicts scalar threshold/exit')
    else:
        require(density['exit_code'] != 0 and (not passed or isinstance(density.get('reason'), str) and density['reason']), 'Density failure lacks failed gate or original exception')
    return True


def delivery_outcome(complete, assessment, require_endpoints=False):
    accepted = complete and isinstance(assessment, dict) and assessment.get('overall_status') == 'PASS'
    return dict(delivery_status='COMPLETE' if accepted else 'PARTIAL', end_to_end_status='PASS' if accepted else 'FAIL',
                exit_code=0 if not require_endpoints or accepted else 1)


def run(root, manifest=None, *, require_endpoints=False):
    root = Path(root).resolve(); evidence = read(path(root, manifest or MANIFEST))
    require(type(evidence.get('schema_version')) is int and evidence['schema_version'] == 1 and evidence.get('phase') == '9A', 'Invalid completion schema')
    authorization, _ = artifact(root, evidence['authorization'])
    no_raw_arrays(authorization)
    require(exact_hash(authorization.get('authorization_sha256')) == AUTHORIZATION_SHA256, 'Only the actual immutable authorization is accepted')
    require(authorization.get('status') == 'STATIC_EVIDENCE_REUSED_UNCHANGED_CORE' and authorization.get('endpoint_execution_commit') == evidence['endpoint_execution_commit'], 'Missing inherited static authorization')
    for key in ('resume_id', 'resume_from_commit', 'resume_preparation_commit', 'static_execution_commit'):
        require(authorization.get(key) == evidence.get(key), 'Authorization identity differs: ' + key)
    source = source_check(root, evidence, authorization)
    public_files = evidence.get('public_files'); require(isinstance(public_files, dict), 'Missing complete publication inventory')
    expected = {p for p in tree(root, source['actual_checkout_commit']) if p.startswith(AREA) and p != (manifest or MANIFEST)}
    require(set(public_files) == expected, 'Completion public inventory incomplete or contains unrelated files')
    for relative, entry in public_files.items():
        data = path(root, relative).read_bytes()
        require(sha(data) == exact_hash(entry.get('sha256')) and len(data) == integer(entry.get('bytes')), 'Public inventory hash mismatch')
    sys.path.insert(0, str(root / 'scripts'))
    static = module(root, 'scripts/replay_soc_core_memory.py', 'phase9a_static_replay')
    prior = module(root, 'benchmarks/soc-core-memory-v1/replay_delivery.py', 'phase9a_original_delivery')
    old, oldpath = artifact(root, evidence['original_delivery']); _, staticpath = artifact(root, evidence['static_evidence'])
    require(oldpath.relative_to(root).as_posix() == 'results/soc-core-memory/delivery-evidence.json' and
            staticpath.relative_to(root).as_posix() == 'results/soc-core-memory/static-evidence.json', 'Historical evidence must be referenced without duplication')
    old_replay = prior.run(root, oldpath); static_result = static.replay(root, staticpath)
    require(old_replay['delivery_status'] == 'PARTIAL' and old_replay['end_to_end_status'] == 'FAIL' and old_replay['time_status'] == 'PERFORMANCE_REVIEW_REQUIRED', 'Original failure/review reclassified')
    require(authorization['core_gate_sha256'] == read(staticpath)['gate']['sha256'], 'Another inherited static gate')
    endpoints, _ = artifact(root, evidence['endpoints']); settings = read(path(root, 'benchmarks/si-soc-splitting-v1/case.json'))['settings']
    workers, summaries = endpoints_check(root, endpoints, authorization, settings)
    frozen_sources = read(path(root, 'benchmarks/soc-core-memory-v1/sources.json'))
    for worker in workers.values():
        static.environment_check(root, worker['environment'], frozen_sources)
    complete = set(workers) == set(ACTIONS); assessment = None
    if complete and evidence.get('density_comparison') is not None:
        density, _ = artifact(root, evidence['density_comparison'])
        contract = read(path(root, 'benchmarks/soc-core-memory-v1/contract.json'))
        has_norm = density_check(root, density, authorization, workers, endpoints['slots'], contract)
        if evidence.get('endpoint_metrics') is not None:
            require(has_norm, 'Metrics cannot replace a failed pre-norm density operation')
            recorded, _ = artifact(root, evidence['endpoint_metrics'])
            metrics = module(root, 'benchmarks/soc-core-memory-v1/endpoint_metrics.py', 'phase9a_completion_metrics')
            assessment = metrics.evaluate(read(metrics.historical_path(root, metrics.HISTORICAL_SCF)), workers['OPT-B0-SCF'],
                read(metrics.historical_path(root, metrics.HISTORICAL_SPECTRUM)), workers['OPT-B0-GAMMA']['spectrum'], density, contract)
            require(static.exact_record(recorded, assessment), 'Recorded endpoint arithmetic/status differs')
    else:
        require(evidence.get('density_comparison') is None and evidence.get('endpoint_metrics') is None, 'Incomplete endpoints cannot publish complete comparisons')
    tests, _ = artifact(root, evidence['tests']); test_status = prior.tests_check(tests)
    outcome = delivery_outcome(complete, assessment, require_endpoints)
    return dict(schema_version=1, phase='9A', resume_id=RESUME, endpoint_execution_commit=evidence['endpoint_execution_commit'],
                replay_status='PASS', replay_exit_code=0, **outcome,
                mode='REQUIRE_ENDPOINTS' if require_endpoints else 'RECORDED_DELIVERY', source=source,
                endpoints=summaries,
                endpoint_assessment=assessment, original_delivery_status='PARTIAL', original_end_to_end_status='FAIL',
                time_status=static_result['time_status'], k6_budget_status=old_replay['k6_budget_status'],
                physical_convergence='NOT_ESTABLISHED', physical_interpretation='REVIEW_REQUIRED', DFTK_K6_SCF='NOT_RUN',
                tests=test_status, scope='Public recorded arithmetic and Git binding only; density/ownership/RSS/environment observations RUNNER_REPORTED; no numerical worker or test rerun')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True); parser.add_argument('--manifest')
    parser.add_argument('--require-endpoints', action='store_true'); args = parser.parse_args(argv)
    try:
        result = run(args.root, args.manifest, require_endpoints=args.require_endpoints)
        print(json.dumps(result, allow_nan=False)); return result['exit_code']
    except Exception as error:
        print(json.dumps(dict(replay_status='FAIL', exit_code=2, reason=type(error).__name__ + ': ' + str(error)), allow_nan=False)); return 2


if __name__ == '__main__':
    sys.exit(main())
