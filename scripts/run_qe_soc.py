#!/usr/bin/env python3
"""Run only the prescribed Phase 7A Mg SOC SCF in a fresh local directory.

No DFTK solve, parameter scan, dependency installation, or automatic retry.
Raw output and a durable process receipt precede parsing. Never reuse a PASS.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

from run_scalar_baseline import qe_identity

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / 'benchmarks/mg-soc-qe-v1/case.json'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    encoded = json.dumps(value, indent=2, allow_nan=False) + '\n'
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(encoded)
    temporary.replace(path)


def require(value, reason):
    if not value:
        raise ValueError(reason)


def verify_inputs(root, case, pseudo):
    """Check bytes before any external worker starts; receipts do not replace parsing."""
    for path, expected in case['frozen_environment'].items():
        require(digest(root / path) == expected, 'Frozen environment changed: ' + path)
    historical = case['historical']
    for ref in [historical['evidence'], *historical['references'].values()]:
        require(digest(root / ref['path']) == ref['sha256'], 'Historical source mismatch: ' + ref['path'])
    evidence = json.loads((root / historical['evidence']['path']).read_text())
    for path, expected in evidence['public_sha256'].items():
        require(digest(root / 'results/mg-soc-scf' / path) == expected, 'Historical public bytes changed: ' + path)
    for path, expected in evidence['executed_source_sha256'].items():
        require(digest(root / path) == expected, 'Historical execution source changed: ' + path)
    qe_input = root / 'benchmarks/mg-soc-qe-v1/qe.in'
    require(digest(qe_input) == case['qe_input_sha256'], 'QE input differs from predeclared case')
    require(digest(pseudo) == case['pseudo']['sha256'], 'UPF SHA-256 mismatch')
    header = ET.parse(pseudo).getroot().find('PP_HEADER').attrib
    expected = {'element': 'Mg', 'pseudo_type': 'NC', 'relativistic': 'full',
                'has_so': 'T', 'core_correction': 'F', 'functional': 'PBESOL'}
    require(all(header.get(k, '').strip() == v for k, v in expected.items()), 'UPF header mismatch')
    require(float(header['z_valence']) == 10, 'UPF valence mismatch')
    return qe_input


def execute(command, directory, env):
    """Preserve the actual exit and reap our entire launcher group on interruption."""
    with (directory / 'qe.stdout').open('w') as out, (directory / 'qe.stderr').open('w') as err:
        worker = subprocess.Popen(command, cwd=directory, env=env, stdout=out, stderr=err,
                                  start_new_session=True)
        try:
            write_json(directory / 'process-start.json', {'pid': worker.pid, 'command': command,
                'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()})
            code = worker.wait()
        except (Exception, KeyboardInterrupt):
            # This process group was created by this invocation; no unrelated worker is signaled.
            try: os.killpg(worker.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try:
                code = worker.wait(timeout=30)
            except subprocess.TimeoutExpired:
                try: os.killpg(worker.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                code = worker.wait()
            try: write_json(directory / 'process-exit.json', {'exit_code': code, 'interrupted': True})
            except OSError: print('Process stopped; exit receipt persistence failed.', file=sys.stderr)
            raise
    write_json(directory / 'process-exit.json', {'exit_code': code, 'interrupted': False,
        'finished_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()})
    return code


def run(root=ROOT, parent=None, pseudo=None, launcher=None):
    root = Path(root).resolve()
    parent = Path(parent) if parent else root / '.work/phase7a'
    run_id = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8]
    directory = parent / run_id
    state = {'schema_version': 1, 'run_id': run_id, 'qe_execution_status': 'INCOMPLETE',
             'parse_status': 'NOT_RUN', 'comparison_status': 'NOT_RUN', 'exit_code': 9}
    try:
        directory.mkdir(parents=True, exist_ok=False)
        write_json(directory / 'result.json', state)
        case_path = root / 'benchmarks/mg-soc-qe-v1/case.json'
        case = json.loads(case_path.read_text())
        pseudo = Path(pseudo) if pseudo else root / '.work/pseudos/Mg.upf'
        qe_input = verify_inputs(root, case, pseudo)
        env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                   MKL_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1', JULIA_NUM_THREADS='1')
        launcher = launcher or os.environ.get('PW_X') or shutil.which('pw.x')
        require(launcher, 'No existing QE launcher available')
        identity = qe_identity(launcher, directory, env)
        shutil.copyfile(case_path, directory / 'case.json')
        shutil.copyfile(qe_input, directory / 'qe.in')
        (directory / 'pseudo').mkdir()
        shutil.copyfile(pseudo, directory / 'pseudo/Mg.upf')
        require(digest(directory / 'pseudo/Mg.upf') == case['pseudo']['sha256'], 'Copied UPF mismatch')
        command = [str(launcher), '-in', 'qe.in']
        preflight = {'saved_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'run_id': run_id, 'case_sha256': digest(case_path), 'qe_input_sha256': digest(qe_input),
            'pseudo_sha256_before': digest(pseudo), 'qe_identity': identity, 'command': command,
            'environment': {k: env[k] for k in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
                'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'JULIA_NUM_THREADS']},
            'source_sha256': {p: digest(root / p) for p in
                ['scripts/run_qe_soc.py', 'scripts/parse_qe_soc.py', 'scripts/run_scalar_baseline.py']},
            'workbench_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
            'fresh_scratch': not (directory / 'scratch').exists()}
        write_json(directory / 'preflight.json', preflight)
        code = execute(command, directory, env)
        state['process_exit_code'] = code
        state['qe_execution_status'] = 'FAILED' if code else 'PROCESS_COMPLETED_PENDING_PARSE'
        write_json(directory / 'result.json', state)
        require(code == 0, 'QE process returned nonzero: ' + str(code))
        require(digest(pseudo) == case['pseudo']['sha256'] == digest(directory / 'pseudo/Mg.upf'), 'UPF changed during run')
        require(digest(identity['binary_path']) == identity['binary_sha256'], 'QE binary changed during run')
        xml = directory / 'scratch/mg_soc_qe_v1.save/data-file-schema.xml'
        shutil.copyfile(xml, directory / 'qe-data-file-schema.xml')
        from parse_qe_soc import parse_qe_soc
        verified_case = dict(case, verified_pseudo_sha256=digest(directory / 'pseudo/Mg.upf'))
        parsed = parse_qe_soc(directory / 'qe-data-file-schema.xml', directory / 'qe.stdout', verified_case,
                              process_exit_code=code, calculation='scf')
        write_json(directory / 'qe-result.json', parsed)
        state.update(qe_execution_status='PASS', parse_status='PASS', exit_code=0,
                     pseudo_sha256_after=digest(pseudo), binary_sha256_after=digest(identity['binary_path']))
        write_json(directory / 'result.json', state)
    except (Exception, KeyboardInterrupt) as error:
        state = dict(schema_version=1, run_id=run_id, qe_execution_status='INCOMPLETE_OR_FAILED',
                     parse_status='FAIL', comparison_status='NOT_RUN', exit_code=9,
                     error_type=type(error).__name__, reason=str(error))
        try:
            write_json(directory / 'result.json', state)
        except Exception:
            print('Result persistence failed; this run is not PASS.', file=sys.stderr)
    print(json.dumps(dict(state, directory=str(directory)), allow_nan=False))
    return state['exit_code']



def run_refinement(source, root=ROOT):
    """One explicitly requested same-input bands solve; SCF source is read-only."""
    root, source = Path(root).resolve(), Path(source).resolve()
    parent = root / '.work/phase7a'
    run_id = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-bands-' + uuid.uuid4().hex[:8]
    directory = parent / run_id
    state = dict(schema_version=1, run_id=run_id, calculation='bands',
                 qe_execution_status='INCOMPLETE', exit_code=9)
    try:
        directory.mkdir(parents=True, exist_ok=False)
        write_json(directory / 'result.json', state)
        original = json.loads((source / 'preflight.json').read_text())
        process = json.loads((source / 'process-exit.json').read_text())
        require(process['exit_code'] == 0 and not process['interrupted'], 'Source SCF process not complete')
        require('convergence has been achieved' in (source / 'qe.stdout').read_text(), 'No converged source SCF')
        require('eigenvalues not converged' in (source / 'qe.stdout').read_text(), 'No source eigenvalue warning warrants refinement')
        for prior in parent.glob('*/preflight.json'):
            record = json.loads(prior.read_text())
            require(record.get('refinement_source_run_id') != source.name, 'A refinement was already attempted for this SCF')
        claim = parent / ('.refinement-claim-' + source.name)
        with claim.open('x') as handle:
            handle.write(run_id + '\n')
        case_path = root / 'benchmarks/mg-soc-qe-v1/case.json'
        case = json.loads(case_path.read_text())
        verify_inputs(root, case, source / 'pseudo/Mg.upf')
        require(original['qe_input_sha256'] == case['qe_input_sha256'], 'Source physical input differs')
        protected = {str(p.relative_to(source)): digest(p) for p in source.rglob('*') if p.is_file()}
        shutil.copytree(source / 'scratch', directory / 'scratch')
        shutil.copytree(source / 'pseudo', directory / 'pseudo')
        shutil.copyfile(case_path, directory / 'case.json')
        input_text = (source / 'qe.in').read_text().replace("calculation = 'scf'", "calculation = 'bands'")
        input_text = input_text.replace('&ELECTRONS', "&ELECTRONS\n startingpot = 'file', startingwfc = 'file',")
        (directory / 'qe.in').write_text(input_text)
        env = dict(os.environ, **original['environment'])
        command = original['command']
        identity = qe_identity(command[0], directory, env)
        require(identity['binary_sha256'] == original['qe_identity']['binary_sha256'], 'QE identity changed')
        write_json(directory / 'preflight.json', dict(run_id=run_id, calculation='bands',
            refinement_source_run_id=source.name, source_protected_sha256=protected,
            saved_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            case_sha256=digest(case_path), qe_input_sha256=digest(directory / 'qe.in'),
            qe_identity=identity, command=command, environment=original['environment'],
            purpose='One warning-triggered spectral refinement only; E/F remain from SCF',
            source_sha256={'scripts/run_qe_soc.py': digest(root / 'scripts/run_qe_soc.py')}))
        code = execute(command, directory, env)
        unchanged = all(digest(source / p) == h for p,h in protected.items())
        write_json(directory / 'source-preservation.json', {'status': 'PASS' if unchanged else 'FAIL',
                   'checked_files': len(protected), 'source_run_id': source.name})
        require(unchanged, 'Source SCF files changed')
        require(code == 0, 'Refinement process failed: ' + str(code))
        require(digest(directory / 'pseudo/Mg.upf') == case['pseudo']['sha256'], 'Refinement UPF changed')
        shutil.copyfile(directory / 'scratch/mg_soc_qe_v1.save/data-file-schema.xml',
                        directory / 'qe-data-file-schema.xml')
        state.update(qe_execution_status='PROCESS_COMPLETED_PENDING_PARSE', exit_code=0,
                     process_exit_code=code, source_scf_preservation='PASS')
        write_json(directory / 'result.json', state)
    except (Exception, KeyboardInterrupt) as error:
        state = dict(schema_version=1, run_id=run_id, calculation='bands', qe_execution_status='INCOMPLETE_OR_FAILED',
                     exit_code=9, error_type=type(error).__name__, reason=str(error))
        try: write_json(directory / 'result.json', state)
        except Exception: print('Refinement persistence failed; no PASS.', file=sys.stderr)
    print(json.dumps(dict(state, directory=str(directory)), allow_nan=False))
    return state['exit_code']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pseudo', type=Path)
    parser.add_argument('--pw-x')
    parser.add_argument('--refine-from', type=Path, help='One warning-triggered bands solve in copied scratch')
    args = parser.parse_args()
    if args.refine_from:
        if args.pseudo or args.pw_x: parser.error('Refinement reuses source identity and input; no overrides')
        return run_refinement(args.refine_from)
    return run(pseudo=args.pseudo, launcher=args.pw_x)


if __name__ == '__main__':
    sys.exit(main())
