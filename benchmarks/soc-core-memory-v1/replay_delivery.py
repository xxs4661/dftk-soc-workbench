#!/usr/bin/env python3
"""Replay this Phase9A partial delivery; never execute numerical workers.

This version deliberately certifies the recorded parse-failure outcome at the
one original execution, not a generic endpoint framework. Replay success does
not mean end-to-end success. --require-endpoints exits 1 for this incomplete
delivery; malformed evidence exits 2.
"""
import argparse
import gzip
import hashlib
import importlib.util
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import replay_soc_core_memory as static

spec = importlib.util.spec_from_file_location('phase9a_integer_budget', Path(__file__).with_name('budget.py'))
budget = importlib.util.module_from_spec(spec); spec.loader.exec_module(budget)
EXECUTION = '1b42a27063ca65757d2c4f34d46fe4f1cd9929ed'
DRIVER = 'scripts/run_si_soc.jl'
RUN_ID = 'OPT-B0-SCF-20260909T114559Z-0600f2bf'
MANIFEST = 'results/soc-core-memory/delivery-evidence.json'
require = static.require


def artifact(root, entry, *, compressed=False):
    require(isinstance(entry, dict), 'Missing public descriptor')
    rel = entry.get('path'); require(isinstance(rel, str), 'Invalid public path')
    part = Path(rel); path = root / part
    require(not part.is_absolute() and '..' not in part.parts and rel == part.as_posix() and root / 'results/soc-core-memory' in path.parents, 'Unconfined public evidence')
    require(path.is_file() and not path.is_symlink() and path.resolve() == path, 'Missing/aliased public evidence')
    require(part.suffix == ('.gz' if compressed else '.json'), 'Unexpected public artifact type')
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == static.hex_value(entry.get('sha256')) and len(data) == static.integer(entry.get('bytes'), 'artifact bytes'), 'Public artifact bytes differ')
    return data if compressed else static.read(path), path


def no_physical_results(value):
    forbidden = {'final', 'n_in', 'n_out', 'checkpoint_sha256', 'n_out_sha256', 'eigenvalues_ha', 'occupations', 'energy_terms_ha', 'internal_energy_ha', 'free_energy_ha', 'spectrum', 'E', 'F'}
    if isinstance(value, dict):
        require(not (set(value) & forbidden), 'Fabricated physical result in failed endpoint evidence')
        for child in value.values():
            no_physical_results(child)
    elif isinstance(value, list):
        for child in value:
            no_physical_results(child)


def endpoints_check(root, record, compressed, stderr_descriptor, static_manifest):
    require(type(record.get('schema_version')) is int and record['schema_version'] == 1 and record.get('phase') == '9A' and record.get('execution_commit') == EXECUTION, 'Wrong failed endpoint execution')
    require(record.get('base_commit') == static.BASE and record.get('preparation_commit') == static.PREPARATION, 'Wrong endpoint base/preparation')
    require(record['static_gate']['sha256'] == static_manifest['gate']['sha256'], 'Endpoint used another static gate')
    slots = record.get('slots'); require(isinstance(slots, dict) and set(slots) == {'OPT-B0-SCF', 'OPT-B0-GAMMA'}, 'Exactly two declared endpoint slots required')
    scf, gamma = slots['OPT-B0-SCF'], slots['OPT-B0-GAMMA']; no_physical_results(slots)
    require(scf.get('status') == 'FAIL' and scf.get('run_id') == RUN_ID and scf.get('formal_slot_claimed') is True and scf.get('native_process_started') is True, 'Original failed formal attempt missing')
    require(type(scf.get('formal_attempt')) is int and scf['formal_attempt'] == 1, 'Unexpected retry')
    require(scf.get('failure_stage') == 'JULIA_PARSE_BEFORE_DRIVER_ENTRY' and scf.get('scf_status') == 'NOT_STARTED', 'Parse failure reclassified as numerical SCF')
    for key in ('map_count', 'progress_records'):
        require(type(scf.get(key)) is int and scf[key] == 0, 'No SCF maps/progress were produced')
    require(scf.get('worker_result_present') is False and scf.get('checkpoint_present') is False and scf.get('worker_environment_validation_status') == 'NOT_REACHED' and scf.get('energy_density_occupation_and_gamma_results') == 'NOT_AVAILABLE', 'Failed worker claimed unavailable results/environment')
    receipt = scf['receipt']; native = receipt['native_process']; resource = receipt['resource']
    require(receipt.get('run_id') == RUN_ID and receipt.get('action') == 'OPT-B0-SCF' and receipt.get('backend') == 'soc-core' and receipt.get('execution_commit') == EXECUTION and receipt.get('execution_status') == receipt.get('failure_status') == 'FAIL' and receipt.get('worker_started') is True, 'Recorder failed-attempt identity differs')
    for actual, expected in ((scf.get('recorder_exit_code'), 9), (receipt.get('exit_code'), 9), (scf['launch_exit'].get('exit_code'), 9), (scf.get('native_exit_code'), 1), (receipt.get('worker_exit_code'), 1), (native.get('exit_code'), 1), (resource.get('native_exit_code'), 1)):
        require(type(actual) is int and actual == expected, 'Original native1/recorder9 must be preserved')
    require(native.get('interrupted') is False and receipt.get('core_gate_sha256') == record['static_gate']['sha256'], 'Different/interrupted native run')
    require(scf['formal_slot_claim'] == {'execution_commit': EXECUTION, 'run_id': RUN_ID}, 'Wrong once-only claim')
    require(scf['launch_stdout_summary'].get('exit_code') == 9 and scf['launch_stdout_summary'].get('worker_exit_code') == 1 and scf['launch_stdout_summary'].get('execution_status') == 'FAIL', 'Launcher contradicts failure')
    require(gamma.get('status') == 'BLOCKED_PARENT' and gamma.get('spectrum_status') == 'NOT_RUN' and gamma.get('formal_slot_claimed') is False and gamma.get('native_process_started') is False and gamma.get('parent_run_id') == RUN_ID and gamma.get('parent_status') == 'FAIL', 'Failed parent must block Gamma')
    require(all(gamma.get(key) is None for key in ('run_id', 'recorder_exit_code', 'native_exit_code')), 'Unexecuted Gamma cannot have an exit/result')
    observation = scf['resource_samples']; rows = observation['rows']
    require(observation['columns'] == ['elapsed_s', 'aggregate_rss_bytes', 'process_count'] and isinstance(rows, list) and len(rows) == 31, 'Missing failure resource samples')
    previous = -1
    for row in rows:
        require(isinstance(row, list) and len(row) == 3, 'Wrong RSS row shape')
        elapsed = static.number(row[0], 'RSS time'); require(elapsed > previous, 'Unordered RSS samples'); previous = elapsed
        static.integer(row[1], 'RSS bytes', 1); static.integer(row[2], 'process count', 1)
    peak = max(row[1] for row in rows)
    for value in (resource['peak_aggregate_rss_bytes'], resource['samples'], resource['nonempty_samples'], resource['limit_bytes'], observation['sampled_peak_rss_bytes']):
        static.integer(value, 'recorded RSS count/bytes', 1)
    require(peak == observation['sampled_peak_rss_bytes'] == resource['peak_aggregate_rss_bytes'] == 741703680 and resource['samples'] == resource['nonempty_samples'] == 31, 'Failure RSS arithmetic differs')
    require(resource['elapsed_seconds'] == observation['observer_elapsed_seconds'] == 3.7200854169932427 and previous <= resource['elapsed_seconds'], 'Failure observer duration differs')
    require(resource.get('status') == resource.get('owned_process_cleanup_status') == 'PASS' and resource.get('remaining_observed_processes') == [] and resource['limit_bytes'] == 8 * 1024**3 and resource['sample_interval_seconds'] == .1, 'Failure resource cleanup/contract differs')
    descriptor = scf['native_stderr']; text_bytes = gzip.decompress(compressed)
    require(descriptor['path'] == stderr_descriptor['path'] and descriptor['compressed_sha256'] == stderr_descriptor['sha256'] and descriptor['compressed_bytes'] == len(compressed), 'Native stderr binding differs')
    require(hashlib.sha256(text_bytes).hexdigest() == descriptor['public_text_sha256'] and len(text_bytes) == descriptor['public_text_bytes'] and len(text_bytes.splitlines()) == descriptor['public_text_lines'], 'Native stderr decompression/hash differs')
    text = text_bytes.decode('utf-8')
    require('ERROR: LoadError: ParseError:' in text and 'space required after `:` in `?` expression' in text and '<workbench>/scripts/run_si_soc.jl:330:52' in text, 'Expected original ParseError not present')
    require(not re.search(r'/(?:Users|home|private|Volumes|tmp)/|~/Documents/', text), 'Private path in public stderr')
    source = record['failed_driver_source']
    static.integer(source.get('error_line'), 'source error line', 1); static.integer(source.get('error_column'), 'source error column', 1)
    require(source.get('path') == DRIVER and source.get('execution_commit') == EXECUTION and source.get('error_line') == 330 and source.get('error_column') == 52, 'Wrong original failed source binding')
    original = static.git_bytes(root, EXECUTION, DRIVER)
    require(hashlib.sha256(original).hexdigest() == static.hex_value(source['sha256']) and len(original) == static.integer(source['bytes'], 'driver bytes'), 'Original failed driver Git bytes differ')
    lines = original.decode().splitlines()
    require(':isnothing(profile)' in lines[329] and lines[328].strip() in text and lines[329].strip() in text, 'Stderr excerpt does not match exact original failed driver')
    require(record['raw_sources']['.work/phase9a/endpoints/' + RUN_ID + '/qe.stderr']['sha256'] == descriptor['raw_text_sha256'], 'Original/native stderr hash mismatch')
    return dict(scf_status='FAIL', scf_numerical_execution='NOT_STARTED', native_exit_code=1, recorder_exit_code=9, gamma_status='BLOCKED_PARENT', end_to_end_status='FAIL', resource_scope='Parse/startup failure only; not an SCF peak')


def tests_check(record):
    require(type(record.get('schema_version')) is int and record['schema_version'] == 1 and record.get('phase') == '9A', 'Invalid test ledger schema')
    require(isinstance(record.get('entries'), list) and record['entries'], 'Missing test ledger')
    for row in record['entries'] + record.get('original_publication_checks', []):
        code = row.get('exit_code'); require(type(code) is int and row.get('status') == ('PASS' if code == 0 else 'FAIL'), 'Test status contradicts real exit')
        require(isinstance(row.get('scope', row.get('reason')), str), 'Missing test/failure scope')
        if 'assertions_or_tests' in row:
            static.integer(row['assertions_or_tests'], 'test count')
    return dict(status='RECORDED_TEST_METADATA_VALIDATED', execution='NOT_RERUN', original_publication_failure_count=sum(row['exit_code'] != 0 for row in record.get('original_publication_checks', [])))


def run(root=ROOT, manifest_path=None, *, require_endpoints=False):
    root = Path(root).resolve(); manifest = static.read(manifest_path or root / MANIFEST)
    require(type(manifest.get('schema_version')) is int and manifest['schema_version'] == 1 and manifest.get('phase') == '9A' and manifest.get('execution_commit') == EXECUTION, 'This replay only covers the original Phase9A execution')
    records = {}; paths = {}
    for key in ('static_evidence', 'memory_budget', 'endpoints', 'tests'):
        records[key], paths[key] = artifact(root, manifest[key])
    compressed, _ = artifact(root, manifest['endpoint_stderr_gzip'], compressed=True)
    result = static.replay(root, paths['static_evidence'])
    require(result['replay_exit_code'] == result['assessment_exit_code'] == 0 and result['assessment_status'] == 'PASS' and result['execution_commit'] == EXECUTION and result['time_status'] == 'PERFORMANCE_REVIEW_REQUIRED', 'Static result altered or incomplete')
    ledger = records['memory_budget']; require(ledger.get('execution_commit') == EXECUTION and ledger.get('schema_version') == 1 and ledger.get('phase') == '9A', 'Wrong budget execution')
    for key in ('nk', 'ng_max', 'sum_ng', 'projectors_per_k', 'target_states', 'solver_columns'):
        static.integer(ledger['geometry'][key], 'geometry/' + key, 1)
    require(all(type(n) is int for n in ledger['geometry']['fft_size']), 'FFT counts must be integers')
    budget_result = budget.replay(ledger)
    budget_path = 'benchmarks/soc-core-memory-v1/budget.py'
    require(static.sha(root / budget_path) == ledger['source_sha256'][budget_path] == hashlib.sha256(static.git_bytes(root, EXECUTION, budget_path)).hexdigest(), 'Budget implementation is not the frozen integer model')
    for key in ('gate', 'performance', 'replay_data'):
        require(ledger['static_evidence_reference'][key]['sha256'] == records['static_evidence'][key]['sha256'], 'Budget bound to other static evidence')
    endpoints = endpoints_check(root, records['endpoints'], compressed, manifest['endpoint_stderr_gzip'], records['static_evidence'])
    tests = tests_check(records['tests'])
    return dict(schema_version=1, phase='9A', execution_commit=EXECUTION, replay_status='PASS', replay_exit_code=0,
                exit_code=1 if require_endpoints else 0, mode='REQUIRE_ENDPOINTS' if require_endpoints else 'RECORDED_DELIVERY',
                delivery_status='PARTIAL', end_to_end_status='FAIL', time_status=result['time_status'],
                k6_budget_status=budget_result['status'], k6_known_subtotal_bytes=budget_result['subtotal_bytes'], DFTK_K6_SCF='NOT_RUN',
                endpoints=endpoints, tests=tests,
                scope='Public recorded arithmetic and exact original parse-failure/source binding only; static array/owner identity remains RUNNER_REPORTED; no numerical workers, tests, SCF or Gamma executed')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT); parser.add_argument('--manifest', type=Path)
    parser.add_argument('--require-endpoints', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = run(args.root, args.manifest, require_endpoints=args.require_endpoints)
        print(static.json.dumps(result, allow_nan=False)); return result['exit_code']
    except Exception as error:
        print(static.json.dumps(dict(replay_status='FAIL', exit_code=2, reason=str(error)), allow_nan=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
