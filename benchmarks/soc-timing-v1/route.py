"""Source and input identity for three bounded diagnostics; never starts a worker."""
import hashlib
import json
import math
import re
from pathlib import Path
import subprocess

E0 = '30befbc22ee52283a19a96694bfe20259891b583'
TASKS = {'T-B0-REF': ('B0', 900, False), 'T-B0-TIMED': ('B0', 900, True),
         'T-K4-TIMED': ('K4', 1800, True)}
CASES = {'B0': 'benchmarks/si-soc-splitting-v1/case.json',
         'K4': 'benchmarks/si-soc-sensitivity-v1/K4/case.json'}
GIB = 1024**3
BOUNDARY_REFERENCE = 'd9e19af3557c923a1e4f7e64510092d47975cc7c'
BOUNDARY_TASKS = ('V-B0-REF','V-B0-OPT','V-K4-REF','V-K4-OPT')


def task_spec(task, root=None):
    """Two explicit experiment registrations; timing never selects the source."""
    if task in TASKS:
        profile,budget,timed=TASKS[task]
        return dict(profile=profile,budget_seconds=budget,timing_enabled=timed,
                    role='OPT' if timed else 'REF',reference_commit=E0,
                    validation_policy='strict',area='.work/soc-timing',slots='soc-timing-consumed',
                    branch='codex/phase9a-timing-cancellation',batch_seconds=3600,
                    tasks=tuple(TASKS),experiment='soc-timing-v1')
    require(task in BOUNDARY_TASKS,'Unregistered diagnostic task')
    root=Path(root or Path(__file__).resolve().parents[2])
    path=root/'benchmarks/soc-boundary-v1/contract.json'
    c=json.loads(path.read_text())
    require(type(c.get('schema_version')) is int and c['schema_version']==1 and
            c.get('experiment')=='soc-boundary-v1' and c.get('reference_commit')==BOUNDARY_REFERENCE,
            'Boundary registration identity differs')
    fixed={'batch_seconds':5400,'minimum_remaining_start_seconds':300,'map_limit':2,
           'limit_bytes':8*GIB,'warning_bytes':7*GIB,'remaining_growth_bytes':2*GIB,
           'branch':'codex/phase9a-validation-boundaries','policy':'single_validation_v1',
           'grace_seconds':[120,10,5]}
    require(all(type(c.get(k)) is type(v) and c[k]==v for k,v in fixed.items()),'Boundary contract limits changed')
    require(list(c.get('tasks',{}))==list(BOUNDARY_TASKS),'Boundary task sequence differs')
    for name,entry in c['tasks'].items():
        profile=name.split('-')[1];role=name.split('-')[2]
        expected=dict(profile=profile,role=role,timing_enabled=True,
                      budget_seconds=900 if profile=='B0' else 1800,
                      validation_policy='strict' if role=='REF' else 'single_validation_v1')
        require(type(entry) is dict and entry==expected and all(type(entry[k])is type(v) for k,v in expected.items()),
                'Boundary task registration differs: '+name)
    return dict(c['tasks'][task],reference_commit=BOUNDARY_REFERENCE,
                area='.work/soc-boundary',slots='soc-boundary-consumed',
                branch=c['branch'],batch_seconds=c['batch_seconds'],tasks=BOUNDARY_TASKS,
                experiment=c['experiment'],registration_sha256=sha(path))


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            digest.update(block)
    return digest.hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', '--no-optional-locks', '-C', str(root), *args])


def exact_file(root, commit, relative):
    path = root / relative
    require(path.is_file() and not path.is_symlink(), 'Source missing or linked: ' + relative)
    require(path.resolve().is_relative_to(root), 'Source path escapes its tree')
    recorded = git(root, 'show', commit + ':' + relative)
    require(path.read_bytes() == recorded, 'Uncommitted executed source: ' + relative)
    return hashlib.sha256(recorded).hexdigest()


def source_files(root, commit, case_path):
    names = git(root, 'ls-tree', '-r', '--name-only', commit).decode().splitlines()
    selected = {p for p in names if p.endswith(('.jl', '.toml')) and
                p.startswith(('src/', 'prototypes/', 'scripts/', 'benchmarks/'))}
    required = {'scripts/run_si_soc.jl', 'prototypes/soc_scf/scf.jl',
                'prototypes/soc_scf/solver.jl', 'prototypes/spinor/scf.jl', 'src/SOCKernels.jl'}
    require(required <= selected, 'Incomplete numerical source tree')
    selected |= {case_path, 'benchmarks/si-soc-splitting-v1/source.json',
                 'environment/workbench/Project.toml', 'environment/workbench/Manifest.toml',
                 'environment/workbench/checksums.toml', 'config/sources.lock'}
    return {p: exact_file(root, commit, p) for p in sorted(selected)}


def adapter_files(root, commit, *, boundary=False):
    names = git(root, 'ls-tree', '-r', '--name-only', commit).decode().splitlines()
    selected = {p for p in names if (p.startswith('benchmarks/soc-timing-v1/') or
                boundary and p.startswith('benchmarks/soc-boundary-v1/')) and
                p.endswith(('.py', '.jl', '.json', '.toml', '.md'))}
    selected.add('prototypes/diagnostics.jl')
    if boundary:
        selected.update({'scripts/si_qe_reference_evidence.py','scripts/run_qe_soc.py',
                         'scripts/run_scalar_baseline.py','scripts/compare_scalar_baseline.py',
                         'scripts/parse_qe_baseline.py','benchmarks/soc-extra-v1/resources.py',
                         'results/soc-core-memory/memory-budget.json'})
    require({'benchmarks/soc-timing-v1/driver.jl', 'benchmarks/soc-timing-v1/route.py'} <= selected,
            'Missing current diagnostic adapter')
    return {p: exact_file(root, commit, p) for p in sorted(selected)}


def tree_identity(root, commit):
    require(git(root, 'rev-parse', 'HEAD').decode().strip() == commit, 'Wrong source HEAD')
    require(not git(root, 'status', '--porcelain', '--untracked-files=all'), 'Dirty source tree')


def validate_route(route):
    require(type(route) is dict and type(route.get('schema_version')) is int and route['schema_version'] == 1, 'Wrong route schema')
    task = route.get('task_id')
    spec=task_spec(task,route.get('adapter_root'))
    profile,budget,timed=spec['profile'],spec['budget_seconds'],spec['timing_enabled']
    for key, expected in [('profile', profile), ('budget_seconds', budget), ('timing_enabled', timed),
                          ('seed', 81001), ('diagnostic_maps', 2), ('limit_bytes', 8*GIB),
                          ('warning_bytes', 7*GIB), ('remaining_growth_bytes', 2*GIB),
                          ('case_path', CASES[profile])]:
        require(type(route.get(key)) is type(expected) and route[key] == expected, 'Route field differs: ' + key)
    require(type(route.get('deadline_epoch')) in (int, float) and
            math.isfinite(route['deadline_epoch']), 'Finite wall deadline required')
    require(all(type(route.get(key)) is str and Path(route[key]).is_absolute() and
                str(Path(route[key]).resolve()) == route[key]
                for key in ('numerical_root', 'adapter_root')), 'Source roots must be canonical absolute paths')
    source = Path(route['numerical_root']).resolve()
    adapter = Path(route['adapter_root']).resolve()
    require(all(isinstance(route.get(k), str) and re.fullmatch('[0-9a-f]{40}', route[k])
                for k in ('source_commit', 'execution_commit')), 'Exact source and adapter commits required')
    candidate=spec['role']=='OPT'
    require(route['source_commit'] == (route['execution_commit'] if candidate else spec['reference_commit']), 'Wrong numerical version')
    require((source == adapter) == candidate, 'REF must load an independent reference source tree')
    if task in BOUNDARY_TASKS:
        for key in ('experiment','role','validation_policy','registration_sha256'):
            require(route.get(key)==spec[key],'Boundary route differs: '+key)
    out = Path(route['outdir'])
    require(out.is_absolute() and out == out.resolve() and out.name == route['worker_id'] == 'worker',
            'Worker path/identity mismatch')
    require(out.parent.name == route['run_id'] and out.parent.is_relative_to(adapter / spec['area']),
            'Run must be in the independent timing area')
    require(bool(route['run_id']), 'Missing run identity')
    require(isinstance(route.get('source_sha256'), dict) and
            route['source_sha256'].get(route['case_path']) == route['case_sha256'], 'Case source map mismatch')
    return route


def prepare_route(root, numerical_root, task, outdir, execution, deadline_epoch):
    """Return an authenticated contract without making a directory or taking a slot."""
    root = Path(root).resolve(); numerical_root = Path(numerical_root).resolve()
    spec=task_spec(task,root)
    profile,budget,timed=spec['profile'],spec['budget_seconds'],spec['timing_enabled']
    numerical = execution if spec['role']=='OPT' else spec['reference_commit']
    tree_identity(root, execution); tree_identity(numerical_root, numerical)
    case_path = CASES[profile]
    sources = source_files(numerical_root, numerical, case_path)
    require(git(numerical_root, 'show', numerical+':'+case_path) ==
            git(numerical_root, 'show', spec['reference_commit']+':'+case_path), 'Historical physical input changed')
    route = dict(schema_version=1, task_id=task, profile=profile, timing_enabled=timed,
                 run_id=Path(outdir).resolve().parent.name, worker_id='worker', outdir=str(Path(outdir).resolve()),
                 adapter_root=str(root), numerical_root=str(numerical_root), execution_commit=execution,
                 source_commit=numerical, source_sha256=sources, adapter_sha256=adapter_files(root, execution,boundary=task in BOUNDARY_TASKS),
                 case_path=case_path, case_sha256=sources[case_path], diagnostic_maps=2, seed=81001,
                 budget_seconds=budget, deadline_epoch=deadline_epoch, limit_bytes=8*GIB,
                 warning_bytes=7*GIB, remaining_growth_bytes=2*GIB)
    if task in BOUNDARY_TASKS:
        route.update({k:spec[k] for k in ('experiment','role','validation_policy','registration_sha256')})
    return validate_route(route)


def verify_route(path, task, outdir):
    original = Path(path)
    require(original.is_file() and not original.is_symlink(), 'Route missing/linked')
    route = validate_route(json.loads(original.read_text()))
    require(route['task_id'] == task and Path(route['outdir']) == Path(outdir).resolve(), 'Route invocation differs')
    require(original.resolve().parent == Path(route['outdir']).parent, 'Route must belong to this run')
    root, numerical = Path(route['adapter_root']), Path(route['numerical_root'])
    expected = prepare_route(root, numerical, task, outdir, route['execution_commit'], route['deadline_epoch'])
    require(route == expected, 'Route/current executed identity differs')
    return dict(route, route_sha256=sha(original))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['verify'])
    parser.add_argument('route'); parser.add_argument('task'); parser.add_argument('outdir')
    args = parser.parse_args()
    try:
        print(json.dumps(verify_route(args.route, args.task, args.outdir), allow_nan=False))
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(9, 'Diagnostic route rejected: ' + str(error) + '\n')
