#!/usr/bin/env python3
"""Replay the explicit resource-blocked record; never run a static or SOC worker.

Exit 0: public identities and the unmeasured/blocked record are consistent.
Exit 1 with --strict: the requested local benchmark was not executed or accepted.
Exit 9: missing, contradictory, malformed, or changed public evidence.
This version supports only this blocked record, never a fabricated future PASS.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = 'de2d3661bdd4a0a5081ae322b7c7e723ef0e6fdd'
REFERENCE = 'd9e19af3557c923a1e4f7e64510092d47975cc7c'
OLD_EXECUTION = '761e09d8fe99f99fcccb0f1b10704916d336ccb8'
BRANCH = 'codex/phase9a-validation-local-probe'
EXPERIMENT = 'soc-validation-local-v1'
RECORD = 'results/soc-validation-local/record.json'
FIXTURE = 'benchmarks/soc-validation-local-v1/fixture.json'
SLOTS = ('DIAG-S', 'DIAG-F', 'BENCH-S', 'BENCH-F', 'BENCH-C')
HEADERS = {
    'types': ('implementation', 'position', 'label', 'concrete_type', 'eltype', 'shape', 'branch', 'count', 'bytes'),
    'work': ('implementation', 'operation', 'hash_calls', 'hash_bytes', 'reuses', 'fallbacks', 'invalidations', 'status'),
    'samples': ('implementation', 'operation', 'kind', 'index', 'elapsed_seconds', 'allocation_bytes', 'gc_seconds', 'compile_seconds', 'status'),
}
DENSITY_SHA = '3a18d5b9774d8d6db4aa73e7f5176983398044b52698f7186e062a826dc870cc'
CASE_SHA = '7874f0007f8df69763b7a7032d580bb05a6b39bdcba412c72cc155a8b2e039ce'
UPF_SHA = 'cc91a6be43c3c89daf6c34410096e8d870f25152dbfb513bcf01afa5ab53eabf'


class EvidenceError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def integer(value):
    return type(value) is int


def sha_string(value, digits=64):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(digits) + '}', value) is not None


def text(value):
    return isinstance(value, str) and bool(value.strip())


def object_fields(value, required, optional=()):
    require(isinstance(value, dict), 'Expected an object')
    require(set(required) <= set(value) <= set(required) | set(optional), 'Missing or unexpected record fields')


def json_bytes(data):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def invalid_constant(value):
        raise EvidenceError('Nonfinite JSON constant: ' + value)
    return json.loads(data, object_pairs_hook=unique_pairs, parse_constant=invalid_constant)


def public_file(root, relative):
    require(text(relative), 'Missing public path')
    path = Path(relative)
    require(not path.is_absolute() and '..' not in path.parts and '.' not in path.parts
            and path.parts and path.parts[0] in ('results', 'benchmarks'), 'Nonpublic or unsafe evidence path')
    target = root / path
    require(target.is_file() and target.resolve().is_relative_to(root), 'Missing or escaped public file: ' + relative)
    require(not any((root / Path(*path.parts[:i])).is_symlink() for i in range(1, len(path.parts) + 1)),
            'Public evidence symlink is not accepted')
    return target.read_bytes()


def artifact(root, descriptor, expected_path=None):
    object_fields(descriptor, ('path', 'sha256'))
    require(sha_string(descriptor['sha256']), 'Invalid evidence SHA-256')
    if expected_path is not None:
        require(descriptor['path'] == expected_path, 'Unexpected canonical evidence path')
    data = public_file(root, descriptor['path'])
    require(hashlib.sha256(data).hexdigest() == descriptor['sha256'], 'Evidence checksum mismatch: ' + descriptor['path'])
    return data


def validate_fixture(fixture):
    require(isinstance(fixture, dict), 'Fixture must be an object')
    require(type(fixture.get('schema_version')) is int and fixture['schema_version'] == 1, 'Unsupported fixture schema')
    for key, value in (('experiment', EXPERIMENT), ('base_commit', BASE), ('reference_commit', REFERENCE),
                       ('failed_candidate_execution_commit', OLD_EXECUTION),
                       ('status', 'INPUT_BYTES_AUTHENTICATED_STATIC_CONTEXT_NOT_RUN'), ('candidate_C', 'NOT_SELECTED')):
        require(fixture.get(key) == value, 'Changed fixture identity/status: ' + key)
    case = fixture.get('case')
    require(isinstance(case, dict) and case.get('sha256') == CASE_SHA and case.get('kpoints') == 64
            and case.get('fft_size') == [48, 48, 48] and case.get('electrons') == 8
            and case.get('ecut_ha') == 30 and case.get('tau_ha') == 0.001, 'Changed fixed K4 case')
    density = fixture.get('density')
    require(isinstance(density, dict), 'Missing fixed density identity')
    expected = dict(selection='HISTORICAL_REUSED_V_K4_REF_MAP_1_N_OUT',
                    source_run_id='V-K4-REF-20260918T163741147858Z-37f8e6d7', map_index=1,
                    source_commit=REFERENCE, execution_commit=OLD_EXECUTION, sha256=DENSITY_SHA,
                    bytes=884736, count=110592, fft_shape=[48, 48, 48], encoding='little-endian Float64',
                    convergence='NOT_SCF_CONVERGED', fallback_uniform_density='NOT_SELECTED')
    for key, value in expected.items():
        require(density.get(key) == value and not isinstance(density.get(key), bool), 'Changed density fixture: ' + key)
    pseudo = fixture.get('pseudopotential')
    comparability = fixture.get('type_shape_alias_comparability')
    require(isinstance(pseudo, dict) and pseudo.get('sha256') == UPF_SHA, 'Changed locked Si input')
    require(isinstance(comparability, dict) and comparability.get('status') == 'NOT_OBSERVED',
            'Blocked fixture cannot claim measured actual types/layout')
    implementations = fixture.get('implementations')
    require(isinstance(implementations, dict) and set(implementations) == {'S', 'F'}, 'Unmeasured candidate implementation')
    for label, commit, policy in (('S', REFERENCE, 'strict'), ('F', BASE, 'single_validation_v1')):
        item = implementations[label]
        require(isinstance(item, dict) and item.get('commit') == commit and item.get('policy') == policy,
                'Implementation identity or strict default changed')
    volume, dvol, electrons = (density.get(k) for k in ('volume_bohr3', 'dvol_bohr3', 'electron_count_python_fsum'))
    require(all(type(v) in (int, float) and math.isfinite(v) for v in (volume, dvol, electrons)),
            'Invalid recorded normalization scalars')
    require(volume == 270.011394 and dvol == volume / 110592 and abs(electrons - 8) <= 1e-8,
            'Inconsistent historical density normalization')


def audit(root=ROOT):
    root = Path(root).resolve()
    record = json_bytes(public_file(root, RECORD))
    fields = ('schema_version', 'experiment', 'status', 'branch', 'base_commit', 'reference_commit',
              'failed_candidate_execution_commit', 'preparation_commit', 'execution_commit',
              'static_processes_started', 'slots', 'candidate_status', 'local_target_status',
              'counts_status', 'actual_types_status', 'fresh_numerical_results_status',
              'artifacts', 'checks', 'blocker', 'limitations')
    object_fields(record, fields, ('resource_observer_exit',))
    require(integer(record['schema_version']) and record['schema_version'] == 1, 'Unsupported record schema')
    for key, value in (('experiment', EXPERIMENT), ('status', 'BLOCKED_RESOURCE_OBSERVATION'), ('branch', BRANCH),
                       ('base_commit', BASE), ('reference_commit', REFERENCE), ('failed_candidate_execution_commit', OLD_EXECUTION),
                       ('candidate_status', 'NO_CANDIDATE_SELECTED'), ('local_target_status', 'NOT_ASSESSED'),
                       ('counts_status', 'NOT_MEASURED'), ('actual_types_status', 'NOT_OBSERVED'),
                       ('fresh_numerical_results_status', 'NOT_RUN')):
        require(record[key] == value, 'Blocked contract contradicted: ' + key)
    require(sha_string(record['preparation_commit'], 40) and sha_string(record['execution_commit'], 40),
            'Preparation/nonphysical execution commit must be a full SHA')
    require(integer(record['static_processes_started']) and record['static_processes_started'] == 0,
            'This blocked record started no static process')
    slots = record['slots']
    require(isinstance(slots, list) and len(slots) == len(SLOTS), 'Wrong static slot list')
    for slot, expected in zip(slots, SLOTS):
        object_fields(slot, ('slot_id', 'status'))
        require(slot == dict(slot_id=expected, status='NOT_RUN'), 'Static slot falsely executed, duplicated or reordered')
    object_fields(record['artifacts'], ('fixture', 'types', 'work', 'samples'))
    fixture = json_bytes(artifact(root, record['artifacts']['fixture'], FIXTURE))
    validate_fixture(fixture)
    for label, header in HEADERS.items():
        data = artifact(root, record['artifacts'][label], 'results/soc-validation-local/' + label + '.csv')
        rows = list(csv.reader(io.StringIO(data.decode('utf-8'))))
        require(rows == [list(header)], 'Unmeasured ' + label + ' table must contain its header only')
    checks = record['checks']
    require(isinstance(checks, list) and bool(checks), 'Missing nonphysical check receipts')
    names = set()
    for check in checks:
        object_fields(check, ('name', 'scope', 'exit_code', 'status', 'log_sha256'), ('log_path',))
        require(text(check['name']) and check['name'] not in names, 'Duplicate/empty preparation check name')
        names.add(check['name'])
        require(check['scope'] == 'NONPHYSICAL_PREPARATION' and integer(check['exit_code']), 'Invalid check scope/exit')
        require(check['status'] in ('PASS', 'FAIL', 'BLOCKED') and
                ((check['status'] == 'PASS') == (check['exit_code'] == 0)), 'Check status contradicts its original exit')
        require(sha_string(check['log_sha256']), 'Missing public check log hash')
        if 'log_path' in check:
            artifact(root, {'path': check['log_path'], 'sha256': check['log_sha256']})
    blocker = record['blocker']
    object_fields(blocker, ('operation', 'exit_code', 'reason'))
    require(blocker['operation'] == 'PROCESS_OBSERVATION' and integer(blocker['exit_code']) and
            blocker['exit_code'] == 127 and text(blocker['reason']), 'Resource-denial receipt differs')
    if 'resource_observer_exit' in record:
        require(integer(record['resource_observer_exit']) and record['resource_observer_exit'] == 127,
                'Contradictory resource-observer exit')
    require(isinstance(record['limitations'], list) and record['limitations'] and all(map(text, record['limitations'])),
            'Missing blocked-scope limitations')
    return {'schema_version': 1, 'evidence_status': 'CONSISTENT', 'status': record['status'],
            'static_processes_started': 0, 'candidate_status': record['candidate_status'],
            'local_target_status': record['local_target_status'], 'table_rows': dict.fromkeys(HEADERS, 0),
            'counts_status': record['counts_status'], 'strict_acceptance': 'NOT_MET_NOT_RUN',
            'scope': 'Public hashes/status arithmetic only; historical input authentication and checks are runner-reported. No private density read, actual-type observation, static benchmark or SOC execution.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--strict', action='store_true', help='Return 1 for the preserved blocked/not-run acceptance state')
    args = parser.parse_args(argv)
    try:
        result = audit()
    except (EvidenceError, OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({'evidence_status': 'FAIL', 'reason': str(error)}, allow_nan=False), file=sys.stderr)
        return 9
    print(json.dumps(result, indent=2, allow_nan=False))
    return 1 if args.strict else 0


if __name__ == '__main__':
    raise SystemExit(main())
