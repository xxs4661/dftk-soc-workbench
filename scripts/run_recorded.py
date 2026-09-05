#!/usr/bin/env python3
"""Record each invocation independently; no shell pipeline or shared PASS file."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parent.parent
ENV_DIR = ROOT / 'environment/workbench'


def sanitize(text):
    tilde_root = str(ROOT).replace(str(Path.home()), '~', 1)
    return text.replace(str(ROOT), '<workbench>').replace(tilde_root, '<workbench>').replace(str(Path.home()), '<home>')


def empty_result():
    return dict(schema_version=2, parse_status='NOT_RUN',
                metadata_validation_status='NOT_RUN', dftk_construction_status='NOT_RUN',
                overall_status='BLOCKED', reasons=[])


class ProtocolError(ValueError):
    """The worker's JSON cannot be used as evidence for the requested action."""


ACTION_FLAGS = {'identity': '--check-environment', 'tests': '--unit-tests',
                'minimal': '--upstream-minimal', 'bootstrap': '--check-environment'}
STATES = {
    'parse_status': {'NOT_RUN', 'PASS', 'FAIL'},
    'metadata_validation_status': {'NOT_RUN', 'PASS', 'FAIL', 'UNSUPPORTED'},
    'dftk_construction_status': {'NOT_RUN', 'EXPECTED_SOC_REJECTION',
                                'UNEXPECTED_SUCCESS', 'UNEXPECTED_ERROR'},
    'overall_status': {'PASS', 'INFO_ONLY', 'FAIL', 'UNSUPPORTED', 'BLOCKED',
                       'ERROR', 'ARGUMENT_ERROR', 'ENVIRONMENT_MISMATCH', 'INPUT_MISMATCH'},
}


def require(condition, reason):
    if not condition:
        raise ProtocolError(reason)


def validate_fields(record):
    """Validate fields we use, including nested values, before rendering anything."""
    require(isinstance(record, dict), 'Worker result must be an object')
    require(type(record.get('schema_version')) is int and record['schema_version'] == 2,
            'Unsupported schema_version (expected integer 2)')
    for key, choices in STATES.items():
        require(isinstance(record.get(key), str) and record[key] in choices,
                'Invalid or missing ' + key)
    require(type(record.get('exit_code')) is int and record['exit_code'] in (0, 2, 3, 4, 5, 6, 7, 8, 9),
            'Invalid or missing exit_code')
    require(isinstance(record.get('reasons'), list) and
            all(isinstance(reason, str) for reason in record['reasons']), 'reasons must be a list of strings')
    for key in ('mode', 'action', 'run_id'):
        if key in record:
            require(isinstance(record[key], str), key + ' must be a string')
    for key in ('environment', 'input'):
        if key not in record:
            continue  # Early failures have not reached these stages.
        nested = record[key]
        require(isinstance(nested, dict), key + ' must be an object when present')
        for field in ('sha256', 'expected_sha256', 'manifest_sha256'):
            if field in nested:
                value = nested[field]
                require(isinstance(value, str) and len(value) == 64 and
                        all(c in '0123456789abcdefABCDEF' for c in value), key + '.' + field + ' must be a SHA-256 string')
        if key == 'environment':
            require(isinstance(nested.get('status'), str) and nested['status'] in ('PASS', 'MISMATCH'),
                    'Invalid or missing environment.status')
        elif 'path' in nested:
            require(isinstance(nested['path'], str), 'input.path must be a string')


def validate_protocol(record, process_exit, action='inspect'):
    """Schema 2 contract of the pinned worker, with action-specific success gates."""
    validate_fields(record)
    require(record['exit_code'] == process_exit, 'Worker JSON exit code disagrees with process exit')
    require(action == 'inspect' or action in ACTION_FLAGS, 'Unknown requested action')
    parse, metadata, construction = (record[key] for key in
        ('parse_status', 'metadata_validation_status', 'dftk_construction_status'))
    stages = (parse, metadata, construction)
    not_run = ('NOT_RUN', 'NOT_RUN', 'NOT_RUN')
    status, code = record['overall_status'], record['exit_code']
    environment = record.get('environment')
    environment_pass = environment is not None and environment['status'] == 'PASS'
    require(metadata == 'NOT_RUN' or parse == 'PASS', 'Metadata stage requires successful parsing')
    require(construction == 'NOT_RUN' or metadata == 'PASS', 'Construction stage requires successful metadata')
    if action == 'inspect':
        if 'action' in record:
            require(record['action'] == 'inspect', 'Worker action disagrees with requested inspection')
        if 'mode' in record:
            require(record['mode'] == 'fr-nc', 'Strict inspection requires mode=fr-nc')
        if stages != not_run or code in (0, 8):
            require(record.get('mode') == 'fr-nc', 'Inspection result lacks mode=fr-nc')
            require(environment_pass, 'Inspection stages require a successful environment')
            require('sha256' in record.get('input', {}), 'Inspection result lacks input.sha256')
    else:
        require(stages == not_run, 'Non-UPF action cannot report UPF stages')
        require('mode' not in record and 'input' not in record, 'Non-UPF action cannot report UPF mode/input')
        if 'action' in record or code == 0:
            require(record.get('action') == ACTION_FLAGS[action], 'Worker action disagrees with requested action')
    if code == 0:
        require(status == 'PASS', 'Zero exit requires PASS for the requested action; INFO_ONLY is not acceptance')
        require(environment_pass and 'manifest_sha256' in environment,
                'Success requires a successful environment with Manifest checksum')
        if action == 'inspect':
            require(stages == ('PASS', 'PASS', 'EXPECTED_SOC_REJECTION'),
                    'Strict success requires parse PASS, metadata PASS and EXPECTED_SOC_REJECTION')
        require(not record['reasons'], 'Successful result cannot contain failure reasons')
    else:
        require(bool(record['reasons']), 'Failed result must explain its failure')
        valid_failure = {
            2: status == 'ARGUMENT_ERROR' and stages == not_run,
            3: status == 'FAIL' and stages == ('FAIL', 'NOT_RUN', 'NOT_RUN'),
            4: (status, stages) in (
                ('FAIL', ('PASS', 'FAIL', 'NOT_RUN')),
                ('UNSUPPORTED', ('PASS', 'UNSUPPORTED', 'NOT_RUN'))),
            5: status == 'FAIL' and parse == metadata == 'PASS' and
               construction in ('UNEXPECTED_SUCCESS', 'UNEXPECTED_ERROR'),
            6: status in ('ENVIRONMENT_MISMATCH', 'BLOCKED') and stages == not_run and not environment_pass,
            7: status == 'BLOCKED' and stages == not_run,
            8: action == 'inspect' and status == 'INPUT_MISMATCH' and stages == not_run,
            9: status == 'ERROR',
        }
        require(valid_failure[code], 'Failure status/stages disagree with exit_code or action')


def recorder_error(reason):
    result = empty_result()
    result.update(overall_status='ERROR', exit_code=9, reasons=[reason])
    return result


def execute(command, log_path, env, expect_json=True, action='inspect'):
    """Check process, filtering, JSON protocol and log writes separately."""
    try:
        process = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    except OSError:
        result = empty_result()
        result.update(exit_code=7, reasons=['Cannot start worker prerequisite'])
        return result
    try:
        stderr = sanitize(process.stderr)
        stdout = sanitize(process.stdout)
        log_path.write_text(stderr + ('' if expect_json else stdout))
        if expect_json:
            if not stdout.strip():
                raise ProtocolError('Worker produced no JSON; see this run log')
            result = json.loads(stdout)
            validate_protocol(result, process.returncode, action)
        else:
            # Bootstrap's text-only setup is intermediate, never published as acceptance.
            result = empty_result()
            result.update(exit_code=process.returncode, overall_status='PASS' if process.returncode == 0 else 'BLOCKED',
                          reasons=[] if process.returncode == 0 else ['Bootstrap setup failed; see bootstrap.log'])
            # The locked setup script reports expected prerequisite failures with 7.
            if process.returncode not in (0, 7):
                result = recorder_error('Unexpected bootstrap exit/signal; see worker_exit_code')
    except ProtocolError as error:
        result = recorder_error('Worker protocol error: ' + str(error))
    except Exception as error:
        result = recorder_error('Output filtering/JSON/log recording failed (' + type(error).__name__ + ')')
    result['worker_exit_code'] = process.returncode
    return result


def render_summary(record):
    environment = record.get('environment', {})
    input_data = record.get('input', {})
    return (
        '# Workbench run\n\n'
        f"- Run ID: `{record['run_id']}`\n"
        f"- Status: `{record['overall_status']}`; exit: `{record['exit_code']}`\n"
        f"- Input SHA-256: `{input_data.get('sha256', 'NOT_AVAILABLE')}`\n"
        f"- Environment: `{environment.get('status', 'NOT_RUN')}`\n"
        f"- Manifest SHA-256: `{environment.get('manifest_sha256', 'NOT_AVAILABLE')}`\n"
        '- Details: [result.json](result.json); [worker.log](worker.log)\n')


def save_run(directory, record):
    validate_fields(record)
    encoded = json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    summary = render_summary(record)
    if not isinstance(summary, str) or not summary:
        raise ValueError('Summary must be nonempty text')
    temporary = directory / 'result.json.tmp'
    summary_temporary = directory / 'summary.md.tmp'
    try:
        summary_temporary.write_text(summary)
        temporary.write_text(encoded)
        summary_temporary.replace(directory / 'summary.md')
        # Authoritative result is published only after all required preparation/writes.
        temporary.replace(directory / 'result.json')
    finally:
        for path in (temporary, summary_temporary):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def save_error(directory, record):
    """Independent fallback: no worker fields or failing summary renderer are reused."""
    encoded = json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    temporary = directory / 'result.json.tmp'
    temporary.write_text(encoded)
    temporary.replace(directory / 'result.json')
    try:
        (directory / 'summary.md').write_text(
            '# Workbench run failed\n\nRecording failed; see [result.json](result.json).\n')
    except OSError:
        # The error JSON remains authoritative even when the summary cannot be written.
        print('Summary persistence failed; current result.json records ERROR.', file=sys.stderr)


def main(argv):
    if not argv:
        argv = ['inspect']
    action, *args = argv
    if args in (['--help'], ['-h']):
        print('Usage: run_recorded.py inspect [UPF_PATH] | identity | tests | bootstrap | minimal')
        print('inspect always uses explicit FR-NC acceptance; no path means checksum-locked Mg.')
        return 0
    run_id = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8]
    directory = ROOT / 'results/runs' / run_id
    record = empty_result()
    record['exit_code'] = 7
    try:
        directory.mkdir(parents=True, exist_ok=False)
        (directory / 'worker.log').touch()
        # Durable current-run marker exists even if Julia cannot start or is interrupted.
        record.update(run_id=run_id, action=action, reasons=['Run started; no acceptance result yet'])
        save_run(directory, record)
        env = os.environ.copy()
        env.setdefault('JULIA_DEPOT_PATH', str(ROOT / '.work/julia-depot'))
        # Exclude unrelated stacked user projects from dependency resolution.
        env['JULIA_LOAD_PATH'] = '@:@stdlib'
        julia = ['julia', '--startup-file=no', '--color=no', '--project=' + str(ENV_DIR)]
        worker = julia + [str(ROOT / 'scripts/inspect_relativistic_upf.jl')]
        if action == 'inspect':
            command = worker + ['--mode', 'fr-nc'] + (args or ['--default-input'])
        elif action in ('identity', 'tests', 'minimal', 'bootstrap') and not args:
            flag = ACTION_FLAGS[action]
            command = worker + [flag]
        else:
            command = None
            record.update(overall_status='ARGUMENT_ERROR', exit_code=2, reasons=['Unknown action or extra arguments'])
        if command is not None:
            if action == 'bootstrap':
                record = execute(julia + [str(ROOT / 'scripts/setup_workbench.jl'), 'instantiate'],
                                 directory / 'bootstrap.log', env, expect_json=False)
            if action != 'bootstrap' or record['exit_code'] == 0:
                record = execute(command, directory / 'worker.log', env, action=action)
            record['command'] = [sanitize(part) for part in command]
        record.update(run_id=run_id, action=action)
        save_run(directory, record)
    except (Exception, KeyboardInterrupt) as error:
        record = recorder_error('Run recording interrupted/failed (' + type(error).__name__ + ')')
        record.update(run_id=run_id, action=action)
        # Fresh safe error replaces the initial marker; malformed nested fields are discarded.
        try:
            save_error(directory, record)
        except Exception as persistence_error:
            record['reasons'].append('Result persistence failed (' + type(persistence_error).__name__ + ')')
            print('Result persistence failed; this run is ERROR (exit 9). See stdout for the error record.', file=sys.stderr)
    print(json.dumps(record, ensure_ascii=False, allow_nan=False))
    print(f"Run {run_id}: {record['overall_status']} (exit {record['exit_code']}); "
          f"results/runs/{run_id}/result.json", file=sys.stderr)
    return record['exit_code']


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
