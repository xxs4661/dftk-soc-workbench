#!/usr/bin/env python3
"""Execute one predeclared Phase 7B slot; no retries or parameter overrides.

Only bookkeeping and restricted input generation live here. The frozen Phase
7A process helper owns/reaps the child; all source snapshots are ordinary copies.
"""
import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib
import uuid

from run_qe_soc import digest, write_json, execute, verify_inputs
from run_scalar_baseline import qe_identity

ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = 'benchmarks/mg-soc-qe-diagnostics-v1'
ORDER = ('I36', 'D36', 'C36', 'G40', 'D40', 'C40')
Q36 = '20260907T001853989732Z-c88a8fa3'
OLD_BANDS = '20260907T002225710098Z-bands-1561a3f2'
BASE = '9d49ca88bfe3c4add0e6c80c1376f006d065e306'
SAVE = 'scratch/mg_soc_qe_v1.save'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def object_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def snapshot(directory):
    directory = Path(directory)
    require(directory.is_dir(), 'Missing complete local snapshot; public XML is not a restart')
    paths = sorted(directory.rglob('*'))
    require(not any(p.is_symlink() for p in paths), 'Snapshot contains a symlink')
    return {p.relative_to(directory).as_posix(): digest(p) for p in paths if p.is_file()}


def require_save(directory):
    files = snapshot(Path(directory) / SAVE)
    needed = {'charge-density.dat', 'data-file-schema.xml', 'Mg.upf',
              'wfc1.dat', 'wfc2.dat', 'wfc3.dat'}
    require(needed <= files.keys(), 'Missing original charge/wfc/XML/UPF; XML cannot reconstruct them')
    return files


def validate_snapshot(directory, expected):
    require(snapshot(directory) == expected, 'Protected source changed or file missing/added')


def copy_source(source, destination, expected):
    validate_snapshot(source, expected)
    files = require_save(source)
    shutil.copytree(Path(source) / 'scratch', Path(destination) / 'scratch', copy_function=shutil.copyfile)
    require(require_save(destination) == files, 'Initial copied snapshot does not match source')
    for rel in files:
        require(not os.path.samefile(Path(source) / SAVE / rel, Path(destination) / SAVE / rel),
                'Source and worker share a file inode')
    return files


def expected_input(original, slot):
    """Exact whitelist from frozen 7A bytes, keeping prefix equal within pairs."""
    require(slot in ORDER, 'Unknown slot')
    value = original
    if slot == 'I36':
        value = value.replace('&CONTROL\n', '&CONTROL\n nstep = 0,\n', 1)
    if slot in ('G40', 'D40', 'C40'):
        value = value.replace('&SYSTEM\n', '&SYSTEM\n nr1=40, nr2=40, nr3=40,\n nr1s=40, nr2s=40, nr3s=40,\n', 1)
    if slot.startswith(('D', 'C')):
        value = value.replace("calculation = 'scf'", "calculation = 'bands'", 1)
        method = (" diagonalization = 'david', diago_david_ndim = 2,\n" if slot.startswith('D') else
                  " diagonalization = 'cg', diago_cg_maxiter = 200,\n")
        value = value.replace('&ELECTRONS\n', "&ELECTRONS\n startingpot = 'file', startingwfc = 'file',\n" + method, 1)
        value = value.replace('diago_thr_init = 1.0d-10', 'diago_thr_init = 1.0d-13', 1)
    return value


def slot_case(plan, slot):
    case = copy.deepcopy(plan)
    cfg = plan['slots'][slot]
    case['qe'].update(calculation=cfg['calculation'], diagonalization=cfg['solver'],
                      diago_thr_init_ry=cfg['diago_thr_init_ry'])
    for key in ('diago_david_ndim', 'diago_cg_maxiter'):
        case['qe'].pop(key, None)
        if key in cfg:
            case['qe'][key] = cfg[key]
    return case


def validate_plan(root, plan):
    require(plan['case'] == 'mg-soc-qe-diagnostics-v1' and plan['phase'] == '7B'
            and plan['base_commit'] == BASE, 'Wrong diagnostic case/base')
    old = json.loads((root / 'benchmarks/mg-soc-qe-v1/case.json').read_text())
    for key in ('geometry', 'electrons', 'kpoints', 'pseudo', 'xc', 'cutoffs',
                'comparison', 'parsing', 'historical', 'frozen_environment', 'qe'):
        require(plan[key] == old[key], 'Frozen physical/reference contract changed: ' + key)
    require(plan['execution_order'] == list(ORDER), 'Calculation matrix changed')
    require(plan['cross_solver_gate_ha'] == 1e-7, 'Predeclared stability gate changed')
    original = (root / 'benchmarks/mg-soc-qe-v1/qe.in').read_text()
    require(digest(root / 'benchmarks/mg-soc-qe-v1/qe.in') == old['qe_input_sha256'], 'Historical input changed')
    for slot in ORDER:
        cfg = plan['slots'][slot]
        bands = slot[0] in 'DC'
        require(cfg['calculation'] == ('bands' if bands else 'scf'), 'Slot calculation changed')
        require(cfg['initialization_only'] == (slot == 'I36'), 'Slot initialization changed')
        require(cfg['solver'] == ('cg' if slot[0] == 'C' else 'david'), 'Slot solver changed')
        require(cfg['diago_thr_init_ry'] == (1e-13 if bands else 1e-10), 'Slot threshold changed')
        require(cfg['fft_grid'] == ([40]*3 if slot.endswith('40') else [36]*3), 'Slot grid changed')
        require(cfg['source_slot'] == (('G40' if slot.endswith('40') else 'Q36') if bands else None), 'Slot source changed')
        if bands:
            key = 'diago_cg_maxiter' if slot[0] == 'C' else 'diago_david_ndim'
            require(cfg.get(key) == (200 if slot[0] == 'C' else 2), 'Algorithm workspace/iteration control changed')
        path = root / cfg['input_path']
        require(path.read_text() == expected_input(original, slot), 'Non-whitelisted input difference: ' + slot)
        require(digest(path) == cfg['input_sha256'], 'Predeclared input hash differs: ' + slot)


def checked_identity(identity, expected):
    for key in ('binary_sha256', 'launcher_sha256', 'runner_sha256', 'jll_uuid', 'jll_version'):
        require(identity.get(key) == expected[key], 'QE launch identity changed: ' + key)


def prepare(root, historical_runs, raw_manifest, archive_data, launcher, dependency_receipt):
    """Bind existing real sources to the previously published raw archive manifest.

    This never recreates a save from XML, installs software, or deletes a claim.
    Absolute paths in this local receipt are intentionally not public evidence.
    """
    root, historical_runs = Path(root).resolve(), Path(historical_runs).resolve()
    raw_manifest, archive_data = Path(raw_manifest), Path(archive_data)
    plan_path = root / CASE_DIR / 'plan.json'
    plan = json.loads(plan_path.read_text())
    validate_plan(root, plan)
    expected_manifest = '097bd3c9539eb9ec5c35525e4243f1772dcda229e9b2de836c8fe3e955edb671'
    require(digest(raw_manifest) == expected_manifest, 'Wrong original Phase 7A raw archive manifest')
    manifest = json.loads(raw_manifest.read_text())
    protected = {}
    for label, run_id in (('Q36', Q36), ('old_bands', OLD_BANDS)):
        source = historical_runs / run_id
        entries = [x for x in manifest['files'] if x['path'].startswith(run_id + '/')]
        require(entries, 'No historical run in manifest')
        for item in entries:
            relative = Path(item['path'])
            require(not relative.is_absolute() and '..' not in relative.parts, 'Unsafe archive relative path')
            for p in (historical_runs / relative, archive_data / relative):
                require(p.is_file() and p.stat().st_size == item['bytes'] and digest(p) == item['sha256'],
                        'Missing or changed historical payload: ' + item['path'])
        protected[label] = dict(path=str(source), sha256=snapshot(source), save_sha256=require_save(source))
    original = json.loads((historical_runs / Q36 / 'preflight.json').read_text())
    allowed = {'README.md', 'docs/status.md', 'results/README.md', 'benchmarks/README.md', 'scripts/README.md'}
    paths = subprocess.check_output(['git','ls-tree','-r','--name-only',BASE], cwd=root, text=True).splitlines()
    frozen = {}
    for path in paths:
        if path in allowed:
            continue
        blob = subprocess.check_output(['git','show',BASE+':'+path], cwd=root)
        expected = hashlib.sha256(blob).hexdigest()
        require(digest(root/path) == expected, 'Base file changed: ' + path)
        frozen[path] = expected
    upstream = {}
    for path in ('.work/DFTK.jl', '.work/PseudoPotentialIO.jl'):
        upstream[path] = dict(commit=subprocess.check_output(['git','-C',str(root/path),'rev-parse','HEAD'],text=True).strip(),
                             status=subprocess.check_output(['git','-C',str(root/path),'status','--porcelain'],text=True))
        require(upstream[path]['status'] == '', 'Dirty frozen upstream checkout')
    receipt = dict(base_commit=BASE, saved_utc=now(), plan_sha256=digest(plan_path),
        historical_fixed_density_source_status='PASS', historical_manifest_sha256=expected_manifest,
        protected_sources=protected, frozen_public_sha256=frozen, upstream=upstream,
        launcher=str(Path(launcher).absolute()), environment=original['environment'])
    # The per-library baseline comes from the actual fresh JLL identity audit,
    # not inferred from a matching pw.x version or a directory's name.
    dependencies = json.loads(Path(dependency_receipt).read_text())
    require(dependencies['probe_exit_code'] == 0 and dependencies['binary_sha256'] == plan['qe_identity']['binary_sha256'],
            'Dependency audit does not identify the actual prescribed executable')
    receipt['dependency_sha256'] = dict(dependencies['dependency_sha256'])
    receipt['dependency_sha256'].update({dependencies['active_project']:dependencies['project_sha256'],
                                        dependencies['manifest']:dependencies['manifest_sha256']})
    parent = root / '.work/phase7b'
    parent.mkdir(parents=True, exist_ok=True)
    with (parent/'preparation.json').open('x') as handle:
        handle.write(json.dumps(receipt, indent=2, allow_nan=False)+'\n')
    protected_sources(root, receipt)
    return {'preparation_status':'PASS', 'plan_sha256':receipt['plan_sha256'],
            'historical_fixed_density_source_status':'PASS'}


def protected_sources(root, preparation):
    for name, item in preparation['protected_sources'].items():
        validate_snapshot(root / item['path'], item['sha256'])
    for path, sha in preparation['frozen_public_sha256'].items():
        require(digest(root / path) == sha, 'Historical public/source bytes changed: ' + path)
    source_lock = tomllib.loads((root / 'config/sources.lock').read_text())
    locked = {item['checkout']:item['commit'] for item in source_lock['source'].values()}
    for path, item in preparation['upstream'].items():
        actual = subprocess.check_output(['git', '-C', str(root / path), 'rev-parse', 'HEAD'], text=True).strip()
        status = subprocess.check_output(['git', '-C', str(root / path), 'status', '--porcelain'], text=True)
        require(actual == item['commit'] == locked[path] and status == item['status'] == '', 'Frozen checkout identity/status changed')
    dependencies = preparation.get('dependency_sha256')
    require(isinstance(dependencies,dict) and len(dependencies) >= 21, 'Missing audited QE libraries and environment hash baseline')
    for path, sha in dependencies.items():
        require(digest(path) == sha, 'Frozen QE dependency changed')


def run_slot(slot, root=ROOT):
    root = Path(root)
    parent = root / '.work/phase7b'
    parent.mkdir(parents=True, exist_ok=True)
    run_id = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + slot + '-' + uuid.uuid4().hex[:8]
    directory = parent / run_id
    directory.mkdir()
    state = dict(schema_version=1, slot=slot, run_id=run_id, execution_status='INCOMPLETE',
                 input_contract_status='NOT_RUN', exit_code=9)
    write_json(directory / 'result.json', state)
    source = None
    source_before = None
    prep = None
    try:
        require(slot in ORDER, 'Unknown slot')
        # Exclusive claims retain numerical failures and prevent silent repeats.
        with (parent / ('.claim-' + slot)).open('x') as f:
            f.write(run_id + '\n')
        for prior in ORDER[:ORDER.index(slot)]:
            claim = parent / ('.claim-' + prior)
            require(claim.is_file(), 'Earlier slot has no completed/blocked receipt: ' + prior)
            prior_record = json.loads((parent / claim.read_text().strip() / 'result.json').read_text())
            require(prior_record['execution_status'] != 'INCOMPLETE', 'Earlier slot still incomplete: ' + prior)
        plan_path = root / CASE_DIR / 'plan.json'
        plan = json.loads(plan_path.read_text())
        validate_plan(root, plan)
        prep = json.loads((parent / 'preparation.json').read_text())
        require(digest(plan_path) == prep['plan_sha256'], 'Plan changed after predeclaration')
        protected_sources(root, prep)
        cfg = plan['slots'][slot]
        case = slot_case(plan, slot)
        if cfg['source_slot'] == 'Q36':
            require(prep['historical_fixed_density_source_status'] == 'PASS', 'Historical source BLOCKED')
            source = root / prep['protected_sources']['Q36']['path']
        elif cfg['source_slot'] == 'G40':
            g_id = (parent / '.claim-G40').read_text().strip()
            source = parent / g_id
            g_result = json.loads((source / 'result.json').read_text())
            if g_result.get('execution_status') != 'PASS' or g_result.get('input_contract_status') != 'PASS':
                state.update(execution_status='BLOCKED', reason='G40 SCF dependency is not valid', exit_code=8)
                write_json(directory / 'result.json', state)
                return state
        if source:
            source_before = snapshot(source)
            initial = copy_source(source, directory, source_before)
            # G40 is pinned once; D/C may never start from each other's updated orbitals.
            if cfg['source_slot'] == 'G40':
                require(initial == json.loads((source / 'save-snapshot.json').read_text()), 'G40 original snapshot changed')
            binding = dict(status='PASS', source_slot=cfg['source_slot'], source_run_id=source.name,
                           source_snapshot_sha256=object_hash(initial),
                           charge_before_sha256=initial['charge-density.dat'],
                           initial_wfc_sha256={k:v for k,v in initial.items() if k.startswith('wfc')},
                           source_preservation_status='NOT_RUN')
        else:
            binding = dict(status='NOT_APPLICABLE', fresh_scratch=not (directory / 'scratch').exists())
        pseudo = root / '.work/pseudos/Mg.upf'
        old = json.loads((root / 'benchmarks/mg-soc-qe-v1/case.json').read_text())
        verify_inputs(root, old, pseudo)
        (directory / 'pseudo').mkdir()
        shutil.copyfile(pseudo, directory / 'pseudo/Mg.upf')
        shutil.copyfile(root / cfg['input_path'], directory / 'qe.in')
        case['verified_pseudo_sha256'] = digest(directory / 'pseudo/Mg.upf')
        write_json(directory / 'case.json', case)
        env = dict(os.environ, **prep['environment'])
        identity = qe_identity(prep['launcher'], directory, env)
        checked_identity(identity, plan['qe_identity'])
        source_code = ['scripts/run_qe_soc_diagnostics.py', 'scripts/parse_qe_soc_diagnostics.py',
                       'scripts/compare_qe_soc_diagnostics.py',
                       'scripts/run_qe_soc.py', 'scripts/parse_qe_soc.py', 'scripts/run_scalar_baseline.py']
        command = [prep['launcher'], '-in', 'qe.in']
        write_json(directory / 'preflight.json', dict(saved_utc=now(), run_id=run_id, slot=slot,
            plan_sha256=digest(plan_path), input_sha256=digest(directory / 'qe.in'),
            source_binding=binding, qe_identity=identity, environment=prep['environment'], command=command,
            workbench_head=subprocess.check_output(['git','rev-parse','HEAD'], cwd=root, text=True).strip(),
            source_sha256={p:digest(root/p) for p in source_code}))
        code = execute(command, directory, env)
        state['process_exit_code'] = code
        protected_sources(root, prep)
        if source:
            validate_snapshot(source, source_before)
            binding['source_preservation_status'] = 'PASS'
            binding['charge_after_sha256'] = digest(directory / SAVE / 'charge-density.dat')
            require(binding['charge_after_sha256'] == binding['charge_before_sha256'], 'Copied charge bytes changed; no payload equivalence assumed')
        after_identity = directory / 'identity-after'
        after_identity.mkdir()
        checked_identity(qe_identity(prep['launcher'], after_identity, env), plan['qe_identity'])
        require(digest(directory / 'pseudo/Mg.upf') == case['pseudo']['sha256'], 'UPF changed')
        xml = directory / SAVE / 'data-file-schema.xml'
        if xml.exists():
            shutil.copyfile(xml, directory / 'qe-data-file-schema.xml')
        from parse_qe_soc_diagnostics import parse_qe_soc_diagnostics
        parsed = parse_qe_soc_diagnostics(directory / 'qe-data-file-schema.xml', directory / 'qe.stdout',
            directory / 'qe.stderr', case, slot, process_exit_code=code)
        parsed.update(run_id=run_id, source_binding=binding)
        if slot != 'I36':
            from compare_qe_soc_diagnostics import payload_sha256
            parsed['parsed_payload_sha256'] = payload_sha256(parsed)
        write_json(directory / 'qe-result.json', parsed)
        state.update(execution_status='PASS', input_contract_status='PASS', exit_code=0,
                     source_binding=binding, purpose='INITIALIZATION_ONLY' if slot == 'I36' else 'NUMERICAL_SOLVE',
                     source_preservation_status='PASS')
        if slot == 'G40':
            write_json(directory / 'save-snapshot.json', require_save(directory))
    except (Exception, KeyboardInterrupt) as error:
        state.update(execution_status='FAIL', input_contract_status='FAIL', exit_code=9,
                     error_type=type(error).__name__, reason=str(error))
        # A process error never selects an old XML/result as a replacement.
        if prep is not None:
            try:
                protected_sources(root, prep)
                if source is not None and source_before is not None:
                    validate_snapshot(source, source_before)
                state['source_preservation_status'] = 'PASS'
            except Exception as preservation:
                state['source_preservation_status'] = 'FAIL'
                state['preservation_reason'] = str(preservation)
    write_json(directory / 'result.json', state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('slot', choices=ORDER, nargs='?')
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--historical-runs', type=Path)
    parser.add_argument('--raw-manifest', type=Path)
    parser.add_argument('--archive-data', type=Path)
    parser.add_argument('--dependency-receipt', type=Path, help='Local fresh-JLL identity audit with actual library/environment hashes')
    parser.add_argument('--pw-x', default=shutil.which('pw.x'))
    args = parser.parse_args()
    if args.prepare:
        if args.slot or not all((args.historical_runs,args.raw_manifest,args.archive_data,args.pw_x,args.dependency_receipt)):
            parser.error('Preparation requires historical runs, raw manifest, archive data, existing pw.x and dependency receipt; no slot')
        print(json.dumps(prepare(ROOT,args.historical_runs,args.raw_manifest,args.archive_data,args.pw_x,args.dependency_receipt)))
        return 0
    if not args.slot or any((args.historical_runs,args.raw_manifest,args.archive_data,args.dependency_receipt)):
        parser.error('Choose one slot; source overrides belong only to preparation')
    state = run_slot(args.slot)
    print(json.dumps(state, allow_nan=False))
    return state['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
