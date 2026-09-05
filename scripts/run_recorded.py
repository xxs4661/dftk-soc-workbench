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


def execute(command, log_path, env, expect_json=True):
    """Check process, filtering, JSON parsing and log writes separately."""
    result = empty_result()
    try:
        process = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    except OSError as error:
        result.update(exit_code=7, reasons=['Cannot start prerequisite: ' + sanitize(str(error))])
        return result
    try:
        stderr = sanitize(process.stderr)
        stdout = sanitize(process.stdout)
        log_path.write_text(stderr + ('' if expect_json else stdout))
        if expect_json and stdout.strip():
            result = json.loads(stdout)
            if not isinstance(result, dict) or not all(k in result for k in empty_result()):
                raise ValueError('Worker result lacks required status fields')
            if result.get('exit_code') != process.returncode:
                raise ValueError('Worker JSON exit code disagrees with process exit')
            if process.returncode != 0 and result['overall_status'] in ('PASS', 'INFO_ONLY'):
                raise ValueError('Nonzero worker exit cannot report success')
        elif process.returncode == 0 and expect_json:
            raise ValueError('Worker exited zero without a JSON result')
        elif not expect_json and process.returncode == 0:
            result['overall_status'] = 'PASS'
        else:
            result['reasons'] = ['Worker produced no JSON; see this run log']
        result['exit_code'] = process.returncode
        if process.returncode not in range(10):
            result.update(overall_status='ERROR', exit_code=9,
                          reasons=['Worker terminated with an unexpected exit/signal; see worker_exit_code'])
        elif process.returncode == 1:
            result.update(overall_status='ERROR', exit_code=9,
                          reasons=['Unexpected worker runtime failure; see this run log'])
    except (OSError, ValueError, TypeError) as error:
        result = empty_result()
        result.update(overall_status='ERROR', exit_code=9,
                      reasons=['Output filtering/JSON/log recording failed (' + type(error).__name__ + ')'])
    result['worker_exit_code'] = process.returncode
    return result


def save_run(directory, record):
    temporary = directory / 'result.json.tmp'
    temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    temporary.replace(directory / 'result.json')
    environment = record.get('environment', {})
    input_data = record.get('input', {})
    (directory / 'summary.md').write_text(
        '# Workbench run\n\n'
        f"- Run ID: `{record['run_id']}`\n"
        f"- Status: `{record['overall_status']}`; exit: `{record['exit_code']}`\n"
        f"- Input SHA-256: `{input_data.get('sha256', 'NOT_AVAILABLE')}`\n"
        f"- Environment: `{environment.get('status', 'NOT_RUN')}`\n"
        f"- Manifest SHA-256: `{environment.get('manifest_sha256', 'NOT_AVAILABLE')}`\n"
        '- Details: [result.json](result.json); [worker.log](worker.log)\n')


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
            flag = {'identity': '--check-environment', 'tests': '--unit-tests',
                    'minimal': '--upstream-minimal', 'bootstrap': '--check-environment'}[action]
            command = worker + [flag]
        else:
            command = None
            record.update(overall_status='ARGUMENT_ERROR', exit_code=2, reasons=['Unknown action or extra arguments'])
        if command is not None:
            if action == 'bootstrap':
                record = execute(julia + [str(ROOT / 'scripts/setup_workbench.jl'), 'instantiate'],
                                 directory / 'bootstrap.log', env, expect_json=False)
            if action != 'bootstrap' or record['exit_code'] == 0:
                record = execute(command, directory / 'worker.log', env)
            record['command'] = [sanitize(part) for part in command]
        record.update(run_id=run_id, action=action)
        save_run(directory, record)
    except (OSError, ValueError, KeyboardInterrupt) as error:
        record.update(run_id=run_id, action=action, overall_status='ERROR', exit_code=9,
                      reasons=['Run recording interrupted/failed: ' + sanitize(str(error))])
        # If disk writes themselves fail, stdout still carries this invocation's failure.
        try:
            save_run(directory, record)
        except OSError:
            pass
    print(json.dumps(record, ensure_ascii=False, allow_nan=False))
    print(f"Run {run_id}: {record['overall_status']} (exit {record['exit_code']}); "
          f"results/runs/{run_id}/result.json", file=sys.stderr)
    return record['exit_code']


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
