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
BASE_FILES, BASE_BYTES, BASE_DUPLICATE_GROUPS = 442, 5420130, 13
CASES = ('upf-acceptance', 'scalar-si-baseline', 'scalar-si-sensitivity',
         'spinor-no-soc', 'relativistic-projectors', 'fr-hamiltonian-energy', 'mg-soc-scf')
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
    """Explicit historical tool-evidence whitelist, read from immutable Git blobs."""
    directory = root / 'results/upf-acceptance'
    directory.mkdir(parents=True, exist_ok=True)
    selections = [
        ('results/upf-inspection.json', 'phase3-inspection.json'),
        ('results/phase4a1/mg-20260905T030611379883Z-0094f2da.json', 'strict-mg.json'),
        ('results/logs/dftk-minimal-20260904T170554Z.log', 'historical-minimal.log')]
    entries = []
    for old, new in selections:
        raw = subprocess.check_output(['git', 'show', BASE + ':' + old], cwd=root)
        published = raw
        if new == 'strict-mg.json':
            record = json.loads(raw)
            env = record.pop('environment')
            assert env == json.loads((root / 'results/shared/environment.json').read_text())
            record['environment_reference'] = {'path': 'results/shared/environment.json',
                'sha256': digest(root / 'results/shared/environment.json'), 'status': env['status']}
            published = (json.dumps(record, indent=2) + '\n').encode()
        (directory / new).write_bytes(published)
        entries.append({'source_path': old, 'source_commit': BASE,
            'source_blob': subprocess.check_output(['git', 'rev-parse', BASE + ':' + old], cwd=root, text=True).strip(),
            'source_sha256': hashlib.sha256(raw).hexdigest(), 'public_path': str((directory / new).relative_to(root)),
            'public_sha256': digest(directory / new),
            'transformation': 'environment replaced by equal shared object reference' if new == 'strict-mg.json' else 'byte-identical'})
    data = {'schema_version': 1, 'scope': 'HISTORICAL_REUSED; export performs no Julia/UPF check',
        'sources': entries, 'extractor': {'path': 'scripts/check_publication.py',
                                       'sha256': digest(root / 'scripts/check_publication.py')},
        'historical_minimal': {'started_utc': '2026-09-04T17:05:54Z', 'ended_utc': '2026-09-04T17:21:27Z',
            'dftk_commit': '2f51b91213e26726fb9c6a17e5fae235a1412d01', 'selection': ':minimal',
            'passed': 1387, 'total': 1387, 'exit_code': 0},
        'strict_mg_run_id': '20260905T030611379883Z-0094f2da'}
    (directory / 'evidence.json').write_text(json.dumps(data, indent=2) + '\n')
    return {'status': 'EXPORTED_HISTORICAL_ONLY', 'files': 3}


def check_upf(root):
    directory = root / 'results/upf-acceptance'
    evidence = json.loads((directory / 'evidence.json').read_text())
    assert digest(root / evidence['extractor']['path']) == evidence['extractor']['sha256']
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
    return {'scope': 'historical schema/provenance only; Julia/UPF checks NOT_RUN', 'sources': 3}


def check_status(root):
    data = json.loads((root / 'benchmarks/mg-soc-fermi/parameters.json').read_text())
    assert data['qe_soc_input_status'] == 'PREPARED_NOT_EXECUTED'
    assert data['qe_soc_benchmark_status'] == 'NOT_RUN'
    for path in ('README.md', 'docs/status.md'):
        text = (root / path).read_text()
        assert 'NOT_RUN' in text, path
    checklist = (root / 'benchmarks/mg-soc-fermi/checklist.md').read_text()
    assert 'Status: **PREPARED_NOT_EXECUTED**. QE SOC benchmark: **NOT RUN**.' in checklist
    status = (root / 'docs/status.md').read_text()
    for text in ('PREPARED_NOT_EXECUTED', 'NOT_ESTABLISHED', 'NOT_IMPLEMENTED', '191', '24'):
        assert text in status
    return 'QE SOC prepared only; no new physical-validation claim'


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
    parser.add_argument('--export-upf', action='store_true', help='export only historical UPF/minimal whitelist from the fixed Git snapshot')
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
