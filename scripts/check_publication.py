#!/usr/bin/env python3
"""Check the curated public tree and recompute existing tables; never run SCF/QE.

Standard library only. Exact historical scalar replay requires Python 3.9.
This checks current-tree bytes, not the size or erasure of Git history.
"""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import re
import subprocess
import sys
from collections import defaultdict
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
BASE = '8658992afa936f6cdb1a8055699ae9aa47b32297'
UPF_EXTRACTOR_COMMIT = 'ac22a64421c4a5444a399477b9a3215dbd913487'
UPF_EXTRACTOR_PATH = 'scripts/check_publication.py'
UPF_EXTRACTOR_BLOB = '062aa1660a9bc1366d1bdbe181c05885aa57e575'
BASE_FILES, BASE_BYTES, BASE_DUPLICATE_GROUPS = 442, 5420130, 13
CASES = ('upf-acceptance', 'scalar-si-baseline', 'scalar-si-sensitivity',
         'spinor-no-soc', 'relativistic-projectors', 'fr-hamiltonian-energy', 'mg-soc-scf',
         'mg-soc-qe-comparison')
LOCAL_PREFIXES = ('.work/', '.agent-work/', 'local_archive/', 'private_data/',
                  'source-trees/', 'downloads/', 'results/runs/')
PRIVATE = re.compile(r'/(?:Users|home)/[^/\s<>]+/|[A-Za-z]:\\Users\\[^\\\s]+\\')
SECRET = re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{24,}|github_pat_[A-Za-z0-9_]{30,}'
                    r'|AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def public_files(root):
    result = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others',
                             '--exclude-standard'], cwd=root, capture_output=True, check=True)
    return sorted({p for p in result.stdout.decode().split('\0') if p and (root / p).is_file()})


def check_paths(root, paths):
    required = ['README.md', 'CONTRIBUTING.md', 'AGENTS.md', 'docs/status.md',
                'docs/ai-assistance.md', 'docs/evidence-policy.md', 'results/shared/environment.json']
    required += ['results/' + case + '/' + name for case in CASES for name in ('README.md', 'evidence.json')]
    for path in required:
        if path not in paths:
            raise ValueError('Missing public prerequisite: ' + path)
    for path in paths:
        if path in ('HANDOFF_TO_GPT56PRO.md', 'MANUAL_ACTIONS.md') or path.startswith(LOCAL_PREFIXES):
            raise ValueError('Local/process artifact in publication: ' + path)
        if Path(path).suffix.lower() in ('.upf', '.bin', '.bundle'):
            raise ValueError('Unapproved payload in publication: ' + path)
        text = (root / path).read_text(errors='replace')
        if PRIVATE.search(text) or SECRET.search(text):
            # Report location only; never echo possible private content.
            raise ValueError('Potential private path/credential; inspect locally: ' + path)
        if path.endswith('.md'):
            for raw in re.findall(r'!?\[[^\]\n]*\]\(([^)\n]+)\)', text):
                target = raw.strip().split(' "', 1)[0].strip('<>')
                if re.match(r'^[A-Za-z][\w+.-]*:', target) or target.startswith('#'):
                    continue
                target = unquote(target.split('#', 1)[0])
                resolved = (root / path).parent / target
                if target and not resolved.exists():
                    raise ValueError('Broken relative link in ' + path + ': ' + target)
    return len(required)


def check_frozen(root):
    record = json.loads((root / 'results/shared/frozen-science.json').read_text())
    assert record['base_commit'] == BASE
    for path, expected in record['sha256'].items():
        if digest(root / path) != expected:
            raise ValueError('Frozen scientific file changed: ' + path)
    env = json.loads((root / 'results/shared/environment.json').read_text())
    assert env['status'] == 'PASS'
    for field, path in [('project_sha256', 'environment/workbench/Project.toml'),
                        ('manifest_sha256', 'environment/workbench/Manifest.toml'),
                        ('source_lock_sha256', 'config/sources.lock')]:
        assert digest(root / path) == env[field], path
    return len(record['sha256'])


def export_upf(root):
    """The evolving verifier must never rewrite evidence of the old exporter."""
    raise ValueError('Historical UPF export is frozen; use the reviewed checkout '
                     + UPF_EXTRACTOR_COMMIT + ' to reproduce that export')


def check_historical_upf_extractor(root, extractor):
    if extractor['path'] != UPF_EXTRACTOR_PATH:
        raise ValueError('Historical UPF extractor path differs from its fixed binding')
    try:
        raw = subprocess.check_output(['git', 'show',
            UPF_EXTRACTOR_COMMIT + ':' + UPF_EXTRACTOR_PATH], cwd=root,
            stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as error:
        raise ValueError('Historical UPF extractor Git object is unavailable: '
                         + UPF_EXTRACTOR_COMMIT) from error
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if blob != UPF_EXTRACTOR_BLOB or hashlib.sha256(raw).hexdigest() != extractor['sha256']:
        raise ValueError('Historical UPF extractor hash differs from its fixed Git blob')
    return {'commit': UPF_EXTRACTOR_COMMIT, 'blob': blob, 'path': UPF_EXTRACTOR_PATH}


def check_upf(root):
    directory = root / 'results/upf-acceptance'
    evidence = json.loads((directory / 'evidence.json').read_text())
    extractor = check_historical_upf_extractor(root, evidence['extractor'])
    for entry in evidence['sources']:
        assert digest(root / entry['public_path']) == entry['public_sha256']
    strict = json.loads((directory / 'strict-mg.json').read_text())
    assert strict['run_id'] == evidence['strict_mg_run_id']
    for key in ('overall_status', 'parse_status', 'metadata_validation_status'):
        assert strict[key] == 'PASS'
    assert strict['dftk_construction_status'] == 'EXPECTED_SOC_REJECTION'
    ref = strict['environment_reference']
    assert digest(root / ref['path']) == ref['sha256'] and ref['status'] == 'PASS'
    assert evidence['historical_minimal']['passed'] == evidence['historical_minimal']['total'] == 1387
    assert '1387/1387' in (directory / 'README.md').read_text()
    return {'scope': 'historical schema/provenance only; Julia/UPF checks NOT_RUN', 'sources': 3,
            'historical_extractor': extractor}


def check_prepared_qe_input(root):
    data = json.loads((root / 'benchmarks/mg-soc-fermi/parameters.json').read_text())
    assert data['qe_soc_input_status'] == 'PREPARED_NOT_EXECUTED'
    assert data['qe_soc_benchmark_status'] == 'NOT_RUN'
    checklist = (root / 'benchmarks/mg-soc-fermi/checklist.md').read_text()
    assert 'Status: **PREPARED_NOT_EXECUTED**. QE SOC benchmark: **NOT RUN**.' in checklist
    return 'Historical input remains PREPARED_NOT_EXECUTED; historical benchmark NOT_RUN'


def check_status(root):
    historical = check_prepared_qe_input(root)
    data = json.loads((root / 'results/mg-soc-qe-comparison/evidence.json').read_text())
    execution = data['qe_execution_status']
    comparison = data['comparison_execution_status']
    if execution not in ('PASS', 'FAIL', 'BLOCKED', 'INCOMPLETE'):
        raise ValueError('Unsupported current QE execution status')
    if data['numerical_agreement_status'] != 'REVIEW_REQUIRED':
        raise ValueError('Current numerical agreement requires human review')
    if data['physical_convergence_status'] != 'NOT_ESTABLISHED':
        raise ValueError('Current physical convergence is not established')
    if data['historical_reference_status'] != 'HISTORICAL_REUSED':
        raise ValueError('DFTK A/B must remain historical references')
    if execution == 'PASS':
        if comparison not in ('PASS', 'FAIL', 'BLOCKED'):
            raise ValueError('Successful QE execution requires an explicit comparison outcome')
        if data['process']['exit_code'] != 0:
            raise ValueError('Successful QE status contradicts process exit code')
    elif comparison != 'NOT_RUN':
        raise ValueError('Unsuccessful QE execution cannot publish a completed comparison')
    if execution != 'PASS' or comparison != 'PASS':
        reasons = data.get('reasons', [])
        if not isinstance(reasons, list) or not reasons or any(
                not isinstance(reason, str) or not reason.strip() for reason in reasons):
            raise ValueError('Unsuccessful current result requires explicit reasons')
    for path in ('README.md', 'docs/status.md'):
        text = (root / path).read_text()
        for marker in ('mg-soc-qe-comparison/', 'QE execution: **' + execution + '**',
                       'REVIEW_REQUIRED', 'NOT_ESTABLISHED', 'HISTORICAL_REUSED'):
            if marker not in text:
                raise ValueError('Current QE state missing or inconsistent in ' + path + ': ' + marker)
    return {'historical_preparation': historical, 'current_qe_execution_status': execution,
            'comparison_execution_status': comparison,
            'numerical_agreement_status': 'REVIEW_REQUIRED',
            'physical_convergence_status': 'NOT_ESTABLISHED'}


def check(root=ROOT, modern_python="python3.12"):
    root = Path(root).resolve()
    paths = public_files(root)
    checks = {'required_paths': check_paths(root, paths), 'frozen_files': check_frozen(root),
              'status': check_status(root), 'upf': check_upf(root)}
    checks['scalar'] = importlib.import_module('curate_scalar_evidence').check(root)
    for name, mode in [('prototype', '--check'), ('soc', 'check')]:
        command = [modern_python, str(root / ('scripts/curate_' + name + '_evidence.py')),
                   mode, '--root', str(root)]
        result = subprocess.run(command, cwd=root, capture_output=True, text=True)
        if result.returncode:
            raise ValueError(name + ' offline check failed (exit ' + str(result.returncode) + '): ' + result.stderr.strip())
        checks[name] = json.loads(result.stdout)
    command = [modern_python, str(root / 'scripts/check_qe_soc_evidence.py'), '--root', str(root)]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True)
    if result.returncode:
        raise ValueError('QE SOC offline check failed (exit ' + str(result.returncode) + '): '
                         + (result.stderr.strip() or result.stdout.strip()))
    checks['qe_soc'] = json.loads(result.stdout)
    groups = defaultdict(list)
    for path in paths:
        groups[digest(root / path)].append(path)
    return {'status': 'PASS', 'scope': 'public offline arithmetic and publication consistency; no SCF/QE',
            'python': sys.version.split()[0], 'base_commit': BASE,
            'current_tree': {'before_files': BASE_FILES, 'before_bytes': BASE_BYTES,
                             'after_files': len(paths), 'after_bytes': sum((root / p).stat().st_size for p in paths),
                             'baseline_exact_duplicate_groups': BASE_DUPLICATE_GROUPS,
                             'remaining_exact_duplicate_groups': [v for v in groups.values() if len(v) > 1],
                             'note': 'logical file lengths, not Git history or external raw archive'},
            'checks': checks, 'unresolved_migration_items': [],
            'not_run_by_this_publication_checker': ['new Julia identity/UPF check', 'SCF/QE', 'full upstream tests',
                        'array-dependent physical reproduction', 'public reintegration from original UPF bytes']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--modern-python', default='python3.12',
                        help='Python 3.11+ with stdlib tomllib for prototype/SOC checks')
    parser.add_argument('--export-upf', action='store_true', help='refused by this evolving verifier; historical reproduction requires the reviewed checkout')
    args = parser.parse_args()
    try:
        result = export_upf(args.root.resolve()) if args.export_upf else check(args.root, args.modern_python)
    except Exception as exc:
        print(json.dumps({'status': 'FAIL', 'error_type': type(exc).__name__, 'reason': str(exc)}))
        return 1
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
