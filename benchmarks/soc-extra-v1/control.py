#!/usr/bin/env python3
"""Read-only identity contract for the explicitly selected 9A extra experiment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

BASE = '7630172808773a3d4ac2da825c27fe43a8705fb8'
BRANCH = 'codex/phase9a-extra-validation'
AREA = Path('benchmarks/soc-extra-v1')
PROFILES = ('B0', 'K6')
ACTIONS = ('X-B0-SCF', 'X-B0-GAMMA', 'X-K6-PILOT', 'X-K6-SCF', 'X-K6-GAMMA')


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    def invalid(value):
        raise ValueError('Nonfinite JSON constant: ' + value)
    return json.loads(Path(path).read_text(), parse_constant=invalid)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def bound_path(root, relative):
    require(isinstance(relative, str), 'Source path must be a string')
    p = Path(relative)
    require(not p.is_absolute() and '..' not in p.parts, 'Unconfined source path')
    path = root / p
    require(path.is_file() and not path.is_symlink() and path.resolve() == path,
            'Missing, linked or noncanonical source: ' + relative)
    return path


def required_sources(root, sources):
    # Keep the broad predeclared source inventory; documentation is not executed.
    required = {p for p in sources['baseline_source_sha256'] if not p.endswith('.md')}
    required |= {p.relative_to(root).as_posix() for p in (root / AREA).iterdir()
                 if p.is_file() and p.suffix in ('.py', '.jl', '.json', '.toml')}
    return required


def verify_contract(root, path, execution, profile):
    root = Path(root).resolve()
    original = Path(path)
    path = original.resolve()
    require(not original.is_symlink() and root / '.work/phase9a-extra/authorizations' in path.parents,
            'Extra contract must be a new local authorization, not an old gate')
    auth = read(path)
    require(isinstance(auth, dict) and type(auth.get('schema_version')) is int and auth['schema_version'] == 1,
            'Unsupported extra contract schema')
    require(auth.get('experiment') == 'soc-extra-v1' and auth.get('base') == BASE,
            'Wrong experiment/base')
    require(profile in PROFILES and auth.get('profile') == profile, 'Wrong extra profile')
    require(isinstance(execution, str) and re.fullmatch('[0-9a-f]{40}', execution) and
            auth.get('execution_commit') == execution == git(root, 'rev-parse', 'HEAD'),
            'Contract must bind the actual execution commit')
    require(git(root, 'branch', '--show-current') == BRANCH, 'Wrong execution branch')
    require(not git(root, 'status', '--porcelain', '--untracked-files=all'), 'Execution tree must be clean')
    require(subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', BASE, execution],
                           capture_output=True).returncode == 0, 'Accepted base missing')
    require(auth.get('core_selection') in ('baseline', 'candidate'), 'Explicit final core selection required')
    require(type(auth.get('numerical_change_requires_B0')) is bool, 'Explicit B0 dependency required')
    require(auth.get('resource_policy') == '8GiB/7GiB', 'Resource policy changed')
    require(auth.get('plan_sha256') == sha(root / AREA / 'plan.json'), 'Prepared plan differs')
    require(auth.get('case_sha256') == sha(root / AREA / (profile + '.json')), 'Prepared case differs')
    decision = read(root / AREA / 'decision.json')
    require(auth['core_selection'] == decision['core_selection'] and
            auth['numerical_change_requires_B0'] == decision['numerical_change_requires_B0'],
            'Execution contract cannot change the committed core/B0 decision')
    sources = read(root / AREA / 'sources.json')
    require(sources.get('base') == BASE, 'Prepared source base differs')
    for relative, entry in sources['historical'].items():
        source = bound_path(root, relative)
        original = subprocess.check_output(['git', '-C', str(root), 'show', BASE + ':' + relative])
        require(source.stat().st_size == entry['bytes'] and sha(source) == entry['sha256'] and
                original == source.read_bytes(), 'Historical source changed: ' + relative)
    actual = auth.get('executed_source_sha256')
    require(isinstance(actual, dict) and set(actual) == required_sources(root, sources),
            'Executed source inventory must match all declared code and extra dependencies')
    for relative, expected in actual.items():
        source = bound_path(root, relative)
        committed = subprocess.check_output(['git', '-C', str(root), 'show', execution + ':' + relative])
        require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected) and
                sha(source) == expected and committed == source.read_bytes(), 'Executed source differs: ' + relative)
    if auth['core_selection'] == 'baseline':
        for relative, expected in sources['baseline_source_sha256'].items():
            if relative.startswith(('src/', 'prototypes/fr_integration/')) and not relative.endswith('.md'):
                require(sha(bound_path(root, relative)) == expected, 'Baseline core changed: ' + relative)
    source = read(root / 'benchmarks/si-soc-splitting-v1/source.json')
    pseudo = bound_path(root, source['local_path'])
    require(pseudo.stat().st_size == source['bytes'] and sha(pseudo) == source['sha256'] == sources['upf_sha256'],
            'Runtime UPF identity mismatch')
    return dict(auth, contract_sha256=sha(path), contract_path=path.relative_to(root).as_posix(),
                allowed_actions=[a for a in ACTIONS if ('-' + profile + '-') in a])


def verify_slot(root, auth, action):
    require(action in auth['allowed_actions'], 'Action does not match contract profile')
    relative = os.environ.get('SOC_EXTRA_SLOT_RECEIPT')
    require(relative, 'Numerical worker requires its own consumed extra slot')
    path = Path(relative).resolve()
    require(path.parent == Path(root).resolve() / '.work/phase9a-extra/slots' and
            path.name == action + '.json' and not Path(relative).is_symlink(), 'Wrong slot reservation path')
    slot = read(path)
    for key, expected in [('action', action), ('execution_commit', auth['execution_commit']),
                          ('profile', auth['profile']), ('contract_sha256', auth['contract_sha256'])]:
        require(slot.get(key) == expected, 'Slot identity mismatch: ' + key)
    require(slot.get('run_id') == os.environ.get('SOC_EXTRA_RUN_ID') and
            slot.get('worker_directory') == os.environ.get('SOC_EXTRA_WORKER_DIRECTORY'), 'Slot/run directory mismatch')
    require(slot.get('numerical_authorization_status') == 'ELIGIBLE', 'Numerical prerequisites missing')
    return slot


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['verify'])
    parser.add_argument('root'); parser.add_argument('contract'); parser.add_argument('execution')
    parser.add_argument('profile', choices=PROFILES)
    parser.add_argument('action', nargs='?', choices=ACTIONS)
    args = parser.parse_args(argv)
    try:
        auth = verify_contract(args.root, args.contract, args.execution, args.profile)
        if args.action is not None:
            auth['slot'] = verify_slot(args.root, auth, args.action)
        print(json.dumps(auth, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print('Extra identity rejected: ' + str(error), file=sys.stderr)
        return 9


if __name__ == '__main__':
    sys.exit(main())
