#!/usr/bin/env python3
"""Replay the published core regression at its fixed historical snapshot.

Python 3.12.x and complete local Git history are required. This entry uses only
public tracked files: it runs no Julia/QE calculation and never fetches history.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

SNAPSHOT = 'e98552ccfb96fb27e07c9816559856d133b58310'
CHECKER = 'benchmarks/soc-core-memory-v1/resume/replay.py'
ROOT = Path(__file__).resolve().parents[1]
CASE = 'core-regression'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def local_environment():
    # Do not inherit Git redirection or user checkout hooks/filters into the copy.
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT='0', PYTHONDONTWRITEBYTECODE='1')
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    return env


def review_fields(value, prefix=''):
    """Present the checker's own qualifications without recomputing any status."""
    result = {}
    if isinstance(value, dict):
        for key, item in value.items():
            result.update(review_fields(item, prefix + ('.' if prefix else '') + key))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            result.update(review_fields(item, prefix + '[' + str(i) + ']'))
    elif isinstance(value, str) and any(word in value for word in ('REVIEW_REQUIRED', 'NOT_ESTABLISHED', 'INSUFFICIENT_EVIDENCE',
                                                                   'NOT_RUN', 'NOT_MEASURED', 'NOT_AVAILABLE', 'NOT_ASSESSED')):
        result[prefix] = value
    return result


def present(child):
    stdout = child.stdout.decode('utf-8', errors='replace')
    stderr = child.stderr.decode('utf-8', errors='replace')
    print('Frozen checker exit: ' + str(child.returncode))
    if stderr:
        print(stderr, end='' if stderr.endswith('\n') else '\n', file=sys.stderr)
    try:
        value = json.loads(stdout)
    except (ValueError, TypeError):
        value = None
    if child.returncode != 0 or not isinstance(value, dict):
        # Original failure text, including nested reasons, is never filtered.
        print(stdout, end='' if stdout.endswith('\n') else '\n')
        return
    keys = ('replay_status', 'mode', 'delivery_status', 'end_to_end_status',
            'original_delivery_status', 'original_end_to_end_status',
            'endpoint_execution_commit', 'scope')
    summary = {key: value[key] for key in keys if key in value}
    summary['retained_qualifications'] = review_fields(value)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def review(root=ROOT, *, case=CASE, log_dir=None):
    metadata = {'case': case, 'historical_snapshot': SNAPSHOT, 'commands': [],
                'scope': 'Public recorded arithmetic and Git identities only; no new physics calculation',
                'child_exit_code': None, 'temporary_copy_removed': False}
    logs = None
    owns_logs = False
    try:
        require(case == CASE, 'Unknown review case: ' + str(case))
        require(sys.version_info[:2] == (3, 12), 'Use an existing Python 3.12.x interpreter (historically 3.12.14); nothing is installed automatically.')
        root = Path(root).resolve(strict=True)
        if log_dir is not None:
            logs = Path(log_dir).expanduser().resolve()
            require(logs != root and root not in logs.parents, 'The optional log directory must be outside the repository.')
            require(not logs.exists(), 'Refusing an existing log path; select a new directory.')
            logs.mkdir()  # Its parent must exist; no user file is replaced.
            owns_logs = True
        env = local_environment()

        def git(*args, cwd=root):
            command = ['git', '-c', 'core.hooksPath=' + os.devnull, '-C', str(cwd), *args]
            result = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            metadata['commands'].append({'command': command, 'exit_code': result.returncode,
                                         'stdout': result.stdout.decode(errors='replace'), 'stderr': result.stderr.decode(errors='replace')})
            require(result.returncode == 0, 'Local Git preparation failed:\n' + result.stderr.decode(errors='replace') + result.stdout.decode(errors='replace'))
            return result.stdout.decode().strip()

        require(Path(git('rev-parse', '--show-toplevel')).resolve() == root, 'Run this entry from its repository copy.')
        require(git('rev-parse', '--is-shallow-repository') == 'false',
                'Complete local Git history is required. Obtain the full repository history before retrying; this entry does not fetch it.')
        try:
            git('cat-file', '-e', SNAPSHOT + '^{commit}')
        except ValueError as error:
            raise ValueError('Required historical snapshot ' + SNAPSHOT + ' is missing. Obtain the complete local repository history; no alternate revision or automatic fetch is used.\n' + str(error)) from error
        temp_parent = Path(tempfile.gettempdir()).resolve()
        if temp_parent == root or root in temp_parent.parents:
            temp_parent = Path('/tmp').resolve()
        require(temp_parent != root and root not in temp_parent.parents, 'No outside-repository temporary directory is available.')
        print('Review: ' + CASE + '\nHistorical snapshot: ' + SNAPSHOT + '\n' + metadata['scope'])
        with tempfile.TemporaryDirectory(prefix='dftk-soc-review-', dir=temp_parent) as temporary:
            owned = Path(temporary).resolve()
            copy = owned / 'snapshot'
            metadata['temporary_copy'] = str(copy)
            git('clone', '--quiet', '--no-hardlinks', '--no-checkout', '--', str(root), str(copy), cwd=owned)
            git('checkout', '--quiet', '--detach', SNAPSHOT, cwd=copy)
            require(git('rev-parse', 'HEAD', cwd=copy) == SNAPSHOT, 'Temporary checkout differs from the fixed snapshot.')
            require(not git('status', '--porcelain', '--untracked-files=all', cwd=copy), 'Historical checkout is not clean.')
            command = [sys.executable, '-B', CHECKER, '--root', str(copy), '--require-endpoints']
            child = subprocess.run(command, cwd=copy, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            metadata.update(checker_command=command, child_exit_code=child.returncode)
            present(child)
            if logs is not None:
                for name, data in (('checker.stdout', child.stdout), ('checker.stderr', child.stderr)):
                    with (logs / name).open('xb') as stream:
                        stream.write(data)
        metadata['temporary_copy_removed'] = not owned.exists()
        return child.returncode
    except (OSError, ValueError) as error:
        metadata['wrapper_error'] = str(error)
        print('Review could not complete: ' + str(error), file=sys.stderr)
        return child.returncode if 'child' in locals() and child.returncode else 2
    finally:
        if 'owned' in locals():
            metadata['temporary_copy_removed'] = not owned.exists()
        if owns_logs:
            try:
                with (logs / 'review.json').open('x') as stream:
                    json.dump(metadata, stream, indent=2); stream.write('\n')
                print('Review logs and preparation metadata: ' + str(logs))
            except OSError as error:
                print('Could not persist review metadata: ' + str(error), file=sys.stderr)
                return child.returncode if 'child' in locals() and child.returncode else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', nargs='?', default=CASE, choices=(CASE,))
    parser.add_argument('--log-dir', type=Path, help='New directory outside the repository; its parent must already exist.')
    args = parser.parse_args(argv)
    return review(case=args.case, log_dir=args.log_dir)


if __name__ == '__main__':
    sys.exit(main())
