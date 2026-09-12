#!/usr/bin/env python3
"""Read-only public retry arithmetic. Exit 0 certifies records, not SCF success.

--require-k6 exits 1 for a valid incomplete/failed pair or unmet 0.1 meV screens.
Malformed evidence or failure of the unchanged historical replay exits 2.
No private arrays, package environment, numerical worker or QE execution.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types

START = 'e40def9dcfd243131adae1ce16d8b22815560a87'
PLAN = 'benchmarks/soc-extra-v1/k6-retry-10gib.json'
OLD = 'benchmarks/soc-extra-v1/replay.py'
EXPERIMENT = 'soc-extra-k6-retry-10gib-v1'
ACTIONS = ('X-K6-SCF', 'X-K6-GAMMA')


def require(ok, reason):
    if not ok: raise ValueError(reason)


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def helpers(root):
    """Execute fixed, authenticated Python definitions; never call its old slots gate."""
    raw = git(root, 'show', START + ':' + OLD)
    require((root / OLD).read_bytes() == raw, 'Historical replay bytes changed')
    module = types.ModuleType('retry_frozen_extra_arithmetic'); module.__file__ = str(root / OLD)
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    source = 'scripts/si_soc_comparison.py'
    require((root / source).read_bytes() == git(root, 'show', START + ':' + source), 'Historical arithmetic changed')
    for name in ('parse_qe_baseline', 'parse_qe_soc', 'parse_qe_soc_diagnostics'):
        relative = 'scripts/' + name + '.py'
        require((root / relative).read_bytes() == git(root, 'show', START + ':' + relative), 'Imported arithmetic dependency changed')
    # Its imports are frozen parser definitions, not a calculation entry.
    directory = str(root / 'scripts')
    if directory not in sys.path: sys.path.insert(0, directory)
    spec = importlib.util.spec_from_file_location('retry_fixed_si_arithmetic', root / source)
    arithmetic = importlib.util.module_from_spec(spec); spec.loader.exec_module(arithmetic)
    return module, arithmetic


def historical_replay(root):
    """The old checker runs in its own clean full-history snapshot, not current docs."""
    with tempfile.TemporaryDirectory(prefix='soc-retry-public-history-') as temporary:
        snapshot = Path(temporary) / 'snapshot'
        subprocess.run(['git', 'clone', '--quiet', '--no-hardlinks', '--no-checkout', str(root), str(snapshot)], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(snapshot), 'checkout', '--quiet', '--detach', START], check=True, capture_output=True)
        require(git(snapshot, 'rev-parse', 'HEAD').decode().strip() == START and not git(snapshot, 'status', '--porcelain'), 'Historical snapshot not clean/exact')
        command = [sys.executable, '-B', str(snapshot / OLD), '--root', str(snapshot)]
        process = subprocess.run(command, text=True, capture_output=True)
        receipt = dict(snapshot_commit=START, native_exit_code=process.returncode,
                       stdout_sha256=sha(process.stdout.encode()), stderr_sha256=sha(process.stderr.encode()))
        require(process.returncode == 0, 'Frozen historical replay failed: ' + json.dumps(dict(receipt, stderr=process.stderr)))
        result = json.loads(process.stdout)
        require(result.get('replay_status') == 'PASS' and result.get('historical_native_slots_reparsed') == 2, 'Historical native reparse incomplete')
        receipt.update(default_replay_status=result['replay_status'], strict_k6_exit_code=None, strict_k6_status='NOT_RUN', strict_k6_expected_exit_code=0 if result['K6']['comparison_status'] == 'PASS' else 1,
                       source_status='HISTORICAL_REUSED', prior_K6_status=result['K6']['comparison_status'])
        return result, receipt


def policy_for(plan, action, execution, *, check=False):
    row = plan['slots'][action]
    return dict(schema_version=1, policy_id='extra-default-8gib-v2' if check else row['policy_id'],
                run_id=row['check_run_id' if check else 'run_id'], action=action,
                case_sha256=plan['case_sha256'], execution_commit=execution,
                limit_bytes=8 * 1024**3 if check else row['limit_bytes'],
                warning_bytes=7 * 1024**3 if check else row['warning_bytes'],
                remaining_growth_bytes=1024**3 if check else row['remaining_growth_bytes'])


def policy_hash(policy):
    return sha(json.dumps(policy, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def validate_row(row, action, data, plan, old, *, check=False):
    require(type(row) is dict, 'Missing explicit action/check record')
    status = row.get('status'); native = row.get('native_exit_code'); outer = row.get('recorder_exit_code')
    policy = policy_for(plan, action, data['execution_commit'], check=check)
    require(row.get('policy') == policy and policy_hash(row['policy']) == row.get('policy_sha256') == policy_hash(policy), 'Wrong per-action policy/run/E')
    require(row.get('run_id') == policy['run_id'], 'Wrong prescribed one-use run')
    if status in ('NOT_RUN', 'BLOCKED_PARENT', 'BLOCKED_PRECONDITION'):
        require(native is None and row.get('worker') is None and bool(row.get('reason')) and
                (outer is None or type(outer) is int and outer != 0), 'Unrun slot contains stale worker/success')
        return False
    require(status in ('PASS', 'FAIL', 'RESOURCE_BLOCKED', 'RESOURCE_LIMIT'), 'Unknown retry status')
    require(type(outer) is int and (native is None or type(native) is int), 'Missing actual process/recorder exits')
    worker = row.get('worker'); accepted = status == 'PASS'
    if not accepted: require(outer != 0 and bool(row.get('reason')), 'Failure lost its actual nonzero exit/reason')
    if native is not None: old.exact_hash(row.get('raw_recorder_sha256'))
    if worker is not None:
        require(type(worker) is dict and worker.get('schema_version') == 1 and type(worker['schema_version']) is int and
                worker.get('phase') == '9A-extra' and worker.get('case') == 'soc-extra-v1/K6' and worker.get('backend') == 'soc-core' and
                worker.get('action') == action and worker.get('run_id') == row['run_id'] + '-dftk' and
                worker.get('execution_commit') == data['execution_commit'], 'Worker identity differs')
        require(type(worker.get('exit_code')) is int and worker['exit_code'] == native, 'Worker/native exit contradiction')
        old.exact_hash(row.get('raw_worker_sha256')); old.exact_hash(worker.get('contract_sha256'))
        require(worker.get('executed_source_sha256') == data['executed_source_sha256'] and
                worker.get('case_sha256') == plan['case_sha256'], 'Worker sources/case differ')
    resource = row.get('resource')
    if resource is not None:
        require(resource.get('resource_policy') == policy and resource.get('resource_policy_sha256') == policy_hash(policy), 'Resource identity differs')
        require(resource.get('native_exit_code') == native, 'Sampler/native exit differs')
        group = old.integer(resource.get('peak_aggregate_rss_bytes'))
        high = resource.get('authenticated_worker_highwater_bytes')
        if high is not None: old.integer(high, 1)
        screen = max(group, high or group)
        require(resource.get('screen_peak_bytes') == screen, 'Native and process-group peaks must be max, not sum')
        stop = resource.get('first_stop_request')
        if stop is not None:
            require(not accepted and resource.get('resource_policy_status') != 'PASS', 'Latched stop cannot pass')
            for key in ('run_id', 'action', 'case_sha256', 'execution_commit', 'policy_id'):
                require(stop.get(key) == policy[key], 'Stop belongs to another run/policy')
            require(stop.get('resource_policy_sha256') == policy_hash(policy), 'Stop policy hash differs')
            decision = stop['resource_decision']
            for key in ('limit_bytes', 'remaining_growth_bytes', 'warning_bytes'):
                require(decision[key] == policy[key], 'Stop changed fixed resource rule')
            require(decision['status'] in ('STOP_AT_SAFE_BOUNDARY', 'RESOURCE_LIMIT') and bool(decision.get('reason')), 'Invalid first stop cause')
            historical_peak = max(decision.get('peak_group_rss_bytes') or 0, decision.get('worker_highwater_bytes') or 0)
            require(decision.get('screen_peak_bytes') == historical_peak, 'First stop peak is not a max')
            if decision['status'] == 'STOP_AT_SAFE_BOUNDARY':
                require(historical_peak + policy['remaining_growth_bytes'] >= policy['limit_bytes'], 'Unsupported headroom stop')
    if not accepted: return False
    require(native == outer == 0 and type(worker) is dict and type(resource) is dict, 'PASS needs actual native/outer success')
    require(resource.get('status') == resource.get('resource_policy_status') == resource.get('owned_process_cleanup_status') == 'PASS' and
            resource.get('first_stop_request') is None and resource.get('safe_stop_requested') is False and
            old.integer(resource.get('nonempty_samples'), 1) > 0 and high is not None and
            screen + policy['remaining_growth_bytes'] < policy['limit_bytes'], 'Resource admission/monitor/cleanup not passed')
    require(worker.get('resource_policy') == policy and worker.get('resource_policy_sha256') == policy_hash(policy) and
            worker.get('resource_policy_status') == 'WORKER_BOUNDARY_CHECKS_PASS' and worker.get('safe_boundary_stop_requested', False) is False and
            worker.get('environment', {}).get('status') == 'PASS', 'Worker boundaries/environment not passed')
    if check:
        require(worker.get('execution_status') == 'CHECK_ONLY_PASS' and worker.get('check_only') is True and
                worker.get('context_constructed') is False and worker.get('formal_slot_reserved') is False and
                worker.get('numerical_execution_status') == 'NOT_RUN', 'Check entry performed/claimed a calculation')
    else:
        require(worker.get('execution_status') == 'PASS' and worker.get('parallelism') == dict(julia=1, blas=1, fft=1, mpi=1) and
                worker.get('runtime_closed') is True and worker.get('runtime_dispatch_status') == 'PASS' and
                worker.get('input', {}).get('sha256') == plan['upf_sha256'], 'Calculation/dispatch/source incomplete')
        runtime = worker.get('runtime', {})
        require(runtime.get('backend') == 'soc-core' and runtime.get('max_rhs') == 30 and
                all(old.integer(runtime.get('counters', {}).get(k), 1) > 0 for k in ('fr_mul_calls','component_mul_calls','full_mul_calls')), 'Owned numerical dispatch counters missing')
        closed = worker.get('runtime_after_close', {})
        require(closed.get('closed') is True and closed.get('workspace_released') is True and closed.get('owned_source_entries') == 0, 'Owned runtime not released')
    return True


def evaluate(data, plan, history, old, arithmetic, case):
    old.finite_public(data)
    old.exact_hash(data.get('execution_commit'), 40)
    require(data.get('schema_version') == 1 and type(data['schema_version']) is int and data.get('experiment') == EXPERIMENT and
            set(data.get('slots', {})) == set(ACTIONS) and set(data.get('checks', {})) == set(ACTIONS), 'Wrong public retry schema/actions')
    accepted = {a: validate_row(data['slots'][a], a, data, plan, old) for a in ACTIONS}
    checked = {a: validate_row(data['checks'][a], a, data, plan, old, check=True) for a in ACTIONS}
    scf, gamma = (data['slots'][a] for a in ACTIONS)
    contracts = {r['worker']['contract_sha256'] for rows in (data['slots'], data['checks']) for r in rows.values() if r.get('worker') is not None}
    require(len(contracts) <= 1, 'Retry slots/checks changed their common authorization')
    for a in ACTIONS:
        if accepted[a]: require(checked[a], 'Successful numerical slot has no accepted entry check')
    for row in (gamma, data['checks']['X-K6-GAMMA']):
        if row['status'] == 'PASS':
            require(accepted['X-K6-SCF'], 'Gamma has no qualified own SCF')
            w, parent = row['worker'], scf['worker']
            require(w.get('source_scf_run_id') == parent['run_id'] and w.get('parent_result_sha256') == scf['raw_worker_sha256'] and
                    w.get('parent_checkpoint_sha256') == parent['checkpoint_sha256'] and
                    w.get('density_source_sha256') == parent['final']['n_out_sha256'], 'Gamma/check parent hashes or n_out differ')
    result = dict(schema_version=1, experiment=EXPERIMENT, replay_status='PASS', execution_commit=data['execution_commit'],
                  original_9A_status='COMPLETED_UNCHANGED', slot_status={a:r['status'] for a,r in data['slots'].items()},
                  K4=history['K4'], K6=dict(D=None, Q=history['K6']['Q'], comparison_status='NOT_ASSESSED', comparison=None),
                  QE_native_energy=history['QE_native_energy'], QE_warnings=history['QE_warnings'],
                  physical_convergence='NOT_ESTABLISHED', manifold_assignment='MANIFOLD_ASSIGNMENT_REVIEW_REQUIRED',
                  scope='Public arithmetic; checkpoints/environment/resource observations remain runner-reported. No SCF or QE replay.')
    if not accepted['X-K6-SCF']: return result
    energy = old.d_scf_quantities(scf['worker'], case)
    require(len(case['kpoints']) == 216 and scf['complete_map_count'] == energy['map_count'], 'Qualified SCF must contain all complete maps')
    result['K6']['D_energy'] = energy
    if not accepted['X-K6-GAMMA']: return result
    d = old.gamma_check(gamma['worker'], energy, case, arithmetic); q = history['K6']['Q']
    vd, vq = d['values_ha'], q['values_ha']; delta = d['delta_so_ev'] - q['delta_so_ev']
    dr = d['delta_so_ev'] - history['K4']['D']['delta_so_ev']; qr = q['delta_so_ev'] - history['K4']['Q']['delta_so_ev']
    raw = [x-y for x,y in zip(vd,vq)]; shifted = [(x-vd[7])-(y-vq[7]) for x,y in zip(vd,vq)]
    comparison = dict(delta_D_minus_Q_mev=1000*delta, D_K4_to_K6_mev=1000*dr, Q_K4_to_K6_mev=1000*qr,
        response_difference_mev=1000*(dr-qr), screen_window_mev=.1,
        D_minus_Q_screen='PASS' if abs(delta)<=1e-4 else 'REVIEW_REQUIRED', response_screen='PASS' if abs(dr-qr)<=1e-4 else 'REVIEW_REQUIRED',
        raw_D_minus_Q_ha=raw, global_referenced_D_minus_Q_ha=shifted, raw_summary_ha=old.stats(raw), global_referenced_summary_ha=old.stats(shifted),
        reference=dict(rule='One Gamma state8 reference per program for all24 states', D_ha=vd[7], Q_ha=vq[7]),
        raw_internal_D_minus_Q_ha=energy['internal_ha']-history['QE_native_energy']['internal_ha'],
        raw_free_D_minus_Q_ha=energy['free_ha']-history['QE_native_energy']['free_ha'], total_energy_zero_difference_gate='NOT_DECLARED',
        response_scope='HISTORICAL_K4_LEGACY_TO_CURRENT_SOC_CORE_MIXED_VERSION_RESPONSE')
    result['K6'].update(D=d, comparison=comparison, comparison_status='PASS' if comparison['D_minus_Q_screen']==comparison['response_screen']=='PASS' else 'REVIEW_REQUIRED')
    return result


def audit_artifacts(root, entries, data, old):
    artifacts = {}; descriptors = {}
    for entry in entries:
        require(type(entry.get('check', False)) is bool, 'Artifact check flag must be boolean')
        key = (entry['action'], entry.get('check', False), entry['kind'])
        require(key not in artifacts and key[0] in ACTIONS, 'Duplicate/unknown artifact role')
        artifacts[key] = old.artifact(root, entry); descriptors[key] = entry
    for check, rows in ((False, data['slots']), (True, data['checks'])):
        for action, row in rows.items():
            if row['native_exit_code'] is not None:
                require(all((action,check,k) in artifacts for k in ('native_stdout','native_stderr')), 'Complete native streams missing')
            resource = row.get('resource') or {}; stop = resource.get('first_stop_request'); key = (action,check,'resource_stop')
            if stop is not None or key in artifacts:
                require(key in artifacts and json.loads(artifacts[key]) == stop, 'First stop data/artifact differ')
                require(descriptors[key].get('raw_sha256') == resource.get('first_stop_sha256'), 'Raw first-stop identity differs')
            key = (action,check,'resource_highwater')
            if row['status'] == 'PASS' or key in artifacts:
                require(key in artifacts, 'Authenticated highwater artifact missing')
                high = json.loads(artifacts[key]); policy = row['policy']
                require(all(high.get(k) == policy[k] for k in ('run_id','action','case_sha256','execution_commit','policy_id')) and
                        high.get('resource_policy_sha256') == row['policy_sha256'] and high.get('units') == 'bytes' and
                        high.get('highwater_bytes') == resource.get('authenticated_worker_highwater_bytes'), 'Published highwater identity/value differs')
            if action.endswith('SCF') and not check:
                key = (action,check,'compact_trace')
                trace = [json.loads(line) for line in artifacts.get(key,b'').splitlines() if line.strip()]
                complete = sum(r.get('status') in ('CONTINUE','PASS') and r.get('diagnostics') is not None for r in trace)
                require(row.get('complete_map_count') == complete, 'Failed/missing trace row counted as complete map')
    return dict(status='PASS', artifacts_checked=len(artifacts))


def replay(root, manifest_path):
    root = Path(root).resolve(); old, arithmetic = helpers(root)
    manifest = old.read(old.path(root, manifest_path)); E = old.exact_hash(manifest['execution_commit'], 40)
    require(manifest.get('schema_version') == 1 and type(manifest['schema_version']) is int and manifest.get('experiment') == EXPERIMENT, 'Invalid retry manifest')
    plan_raw = git(root, 'show', E + ':' + PLAN); plan = json.loads(plan_raw)
    require(manifest['plan_sha256'] == sha(plan_raw) and plan['start'] == START, 'Execution plan identity differs')
    require(git(root, 'merge-base', '--is-ancestor', START, E) == b'', 'Execution is outside retry history')
    require(plan['slots']['X-K6-SCF']['limit_bytes'] == 10*1024**3 and plan['slots']['X-K6-GAMMA']['limit_bytes'] == 8*1024**3 and
            plan['slots']['X-K6-SCF']['remaining_growth_bytes'] >= 2021087414, 'Unapproved resource/physical plan')
    require(plan['comparison']['split_difference_limit_mev'] == plan['comparison']['response_difference_limit_mev'] == .1, 'Comparison screen changed')
    data = json.loads(old.artifact(root, manifest['data'])); require(data['execution_commit'] == E, 'Data execution differs')
    source = data.get('executed_source_sha256'); require(type(source) is dict and source, 'Execution source inventory missing')
    require(set(plan['source_boundary']['allowed_existing_control_edits']) | set(plan['source_boundary']['new_sources']) <= set(source), 'Execution source closure omits active control files')
    for relative, digest in source.items(): require(sha(git(root, 'show', E + ':' + relative)) == old.exact_hash(digest), 'Executed source mismatch: '+relative)
    case_raw = git(root, 'show', E + ':' + plan['case']); require(sha(case_raw) == plan['case_sha256'] and case_raw == git(root, 'show', START + ':' + plan['case']), 'Frozen K6 case differs')
    artifact_audit = audit_artifacts(root, manifest.get('artifacts', []), data, old)
    history, receipt = historical_replay(root)
    result = evaluate(data, plan, history, old, arithmetic, json.loads(case_raw))
    result.update(historical_replay=receipt, historical_sources=history['historical_sources'], artifact_audit=artifact_audit)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--manifest', default='results/soc-extra/k6-retry-10gib/evidence.json')
    parser.add_argument('--require-k6', action='store_true'); args = parser.parse_args(argv)
    try:
        result = replay(args.root, args.manifest)
        code = 1 if args.require_k6 and result['K6']['comparison_status'] != 'PASS' else 0
        result['exit_code'] = code; print(json.dumps(result, allow_nan=False, separators=(',', ':'))); return code
    except (Exception, KeyboardInterrupt) as error:
        print(json.dumps(dict(replay_status='FAIL', exit_code=2, reason=str(error))), file=sys.stderr); return 2


if __name__ == '__main__': sys.exit(main())
