"""One named continuation: authenticate inherited evidence and two fixed slots.

No numerical worker or authorization is created by this module. The local grant
is issued once by the task owner/agent after committing the prepared code; every
execution only reads that grant and the repository-common registry.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

START = 'e40def9dcfd243131adae1ce16d8b22815560a87'
OLD_E = '96795a6b2bf2ca4f6c8dcf6546287eb95bfe4504'
ID = 'k6-scf-attempt2-10gib-v1'
PLAN = 'benchmarks/soc-extra-v1/k6-retry-10gib.json'
GIB = 1024**3
MIN_GROWTH = 2021087414
REGISTRY_NAME = 'soc-extra-k6-attempt2-registry.json'


def require(ok, reason):
    if not ok: raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + x)))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(4*1024**2), b''): h.update(block)
    return h.hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def blob(root, revision, path):
    return subprocess.check_output(['git', '-C', str(root), 'show', revision + ':' + path])


def plan(root):
    p = read(Path(root) / PLAN)
    require(p['start'] == START and p['continuation_id'] == ID and p['numerical_core_changed'] is False,
            'Wrong fixed continuation plan')
    require(p['case']=='benchmarks/soc-extra-v1/K6.json','Wrong sole K6 input source')
    require(set(p['slots']) == {'X-K6-SCF', 'X-K6-GAMMA'}, 'Continuation permits only K6 SCF/Gamma')
    return p


def policy_for(auth, action, *, check=False):
    require(action in ('X-K6-SCF', 'X-K6-GAMMA'), 'One-time policy is not for B0/pilot/K8/another action')
    key = 'check_resource_policies' if check else 'resource_policies'
    hashes = 'check_resource_policy_hashes' if check else 'resource_policy_hashes'
    p = auth[key][action]
    require(digest(p) == auth[hashes][action], 'Resource policy byte digest differs')
    return p


def policies(root, execution):
    """Deterministic template; it conveys no authorization by itself."""
    p = plan(root); actual, checks = {}, {}
    for action, slot in p['slots'].items():
        require(slot['allowed_starts'] == 1 and type(slot['allowed_starts']) is int, 'Not a one-start slot')
        value = dict(schema_version=1, policy_id=slot['policy_id'], run_id=slot['run_id'], action=action,
                     case_sha256=p['case_sha256'], execution_commit=execution,
                     limit_bytes=slot['limit_bytes'], warning_bytes=slot['warning_bytes'],
                     remaining_growth_bytes=slot['remaining_growth_bytes'])
        if action == 'X-K6-SCF':
            require(value['policy_id'] == ID and value['limit_bytes'] == 10*GIB and value['warning_bytes'] == 8*GIB and
                    type(value['remaining_growth_bytes']) is int and value['remaining_growth_bytes'] >= MIN_GROWTH and slot['attempt'] == 2,
                    'The only larger policy must be the second K6 SCF')
        else:
            require(value['limit_bytes'] == 8*GIB and value['warning_bytes'] == 7*GIB and slot['attempt'] == 1,
                    'Gamma cannot inherit the parent limit')
        actual[action] = value
        checks[action] = dict(value, policy_id='extra-default-8gib-v2', run_id=slot['check_run_id'],
                              limit_bytes=8*GIB, warning_bytes=7*GIB, remaining_growth_bytes=GIB)
    return actual, checks


def common_registry(root):
    return Path(git(root, 'rev-parse', '--path-format=absolute', '--git-common-dir')) / REGISTRY_NAME


def verify_registry(root, path, auth):
    registry = common_registry(root)
    require(registry.is_file() and not registry.is_symlink(), 'One-time common registry is missing')
    value = read(registry)
    require(value.get('continuation_id') == ID and value.get('start') == START and
            value.get('execution_commit') == auth['execution_commit'] and value.get('contract_sha256') == sha(path),
            'Common registry does not authorize these exact grant bytes')
    store = Path(value['run_store'])
    require(store.is_dir() and not store.is_symlink() and store.resolve() == store and
            store == Path(auth['run_store']) and store == Path(root)/'.work/phase9a-extra',
            'All worktrees/directories must consult the original shared run store; alternate execution root refused')
    require(Path(value['workbench_root']) == Path(root) and value.get('allowed_starts') == 1,
            'Registry belongs to another root or start allowance')
    return value


def source_proof(root, execution):
    """Bind all old files; narrowly allow control edits, not numerical bodies."""
    root = Path(root); p = plan(root); allowed = set(p['source_boundary']['allowed_existing_control_edits'])
    old = git(root, 'ls-tree', '-r', '--name-only', START).splitlines()
    changed, unchanged = {}, {}
    for name in old:
        if name.endswith('.md') and name in {'README.md','docs/status.md','results/README.md','benchmarks/README.md','scripts/README.md','docs/reproducibility.md'}:
            continue
        path = root/name
        require(path.is_file() and not path.is_symlink(), 'Original path missing/linked: ' + name)
        before = hashlib.sha256(blob(root, START, name)).hexdigest(); after = sha(path)
        if before != after:
            require(name in allowed, 'Forbidden old numerical/input/evidence edit: ' + name)
            changed[name] = {'historical_sha256':before, 'executed_sha256':after, 'scope':'Declared control/protocol change only'}
        else: unchanged[name] = before
    # Old broad inventory remains the minimum. New continuation helpers also
    # enter the actual source map; plans/source locks are never refreshed.
    for region in p['source_boundary']['frozen_mathematical_regions']:
        before=blob(root,START,region['path'])[region['start_byte_zero_based']:region['end_byte_exclusive']]
        require(hashlib.sha256(before).hexdigest()==region['sha256'] and (root/region['path']).read_bytes().count(before)==1,
                'Frozen mathematical body changed or duplicated: '+region['label'])
    original_sources = read(root/'benchmarks/soc-extra-v1/sources.json')
    names = {s for s in original_sources['baseline_source_sha256'] if not s.endswith('.md')}
    names |= {q.relative_to(root).as_posix() for q in (root/'benchmarks/soc-extra-v1').iterdir()
              if q.is_file() and q.suffix in ('.py','.jl','.json','.toml')}
    current = {}
    for name in sorted(names):
        path=root/name; require(path.is_file() and not path.is_symlink() and path.resolve()==path, 'Invalid executed source: '+name)
        b=path.read_bytes();require(b==blob(root,execution,name),'Executed source is not committed: '+name);current[name]=hashlib.sha256(b).hexdigest()
    return dict(executed_source_sha256=current, control_changes=changed,
                unchanged_old_files_sha256=unchanged, scope='Whole old-file identity; allowed control diffs separately reviewed before E_new')


def inherited_records(root):
    import gzip
    root=Path(root); public=root/'results/soc-extra/data.json.gz';require(public.read_bytes()==blob(root,START,'results/soc-extra/data.json.gz'),'Old public data changed')
    data=json.loads(gzip.decompress(public.read_bytes()));require(data['execution_commit']==OLD_E,'Wrong historical execution')
    evidence={}
    for action in ('X-B0-SCF','X-B0-GAMMA','X-K6-PILOT','X-K6-SCF'):
        item=data['slots'][action];directory=root/'.work/phase9a-extra/runs'/item['run_id'];outer=read(directory/'result.json')
        require(sha(directory/'result.json')==item['raw_recorder_sha256'],'Historical raw recorder changed: '+action)
        worker_dir=directory/outer['worker_directory'];require(worker_dir.parent==directory and not worker_dir.is_symlink(),'Invalid historical worker directory')
        worker=read(worker_dir/'result.json');require(sha(worker_dir/'result.json')==item['raw_worker_sha256'],'Historical worker changed: '+action)
        require(outer['execution_commit']==worker['execution_commit']==OLD_E and outer['action']==worker['action']==action,'Historical run/E/action differs')
        require(sha(directory/'process-exit.json')==item['raw_native_exit_sha256'] and read(directory/'resource.json')==outer['resource'],'Historical native/resource receipt changed')
        require(outer['native_exit_code']==outer['exit_code']==(1 if action=='X-K6-SCF' else 0),'Historical exit changed')
        require(outer['resource']['owned_process_cleanup_status']=='PASS','Historical cleanup not certified')
        if action in ('X-B0-SCF','X-K6-PILOT'):
            cp='final.bin' if action=='X-B0-SCF' else 'pilot.bin';require(sha(worker_dir/cp)==worker['checkpoint_sha256'],'Historical inherited checkpoint changed')
        evidence[action]={'run_id':item['run_id'],'execution_commit':OLD_E,'raw_recorder_sha256':item['raw_recorder_sha256'],
                          'raw_worker_sha256':item['raw_worker_sha256'],'status':'HISTORICAL_REUSED','outer':outer,'worker':worker}
    require(sha(root/'.work/phase9a-extra/b0-regression.json')==data['b0_regression_raw_sha256'],'Historical B0 gate changed')
    gate=read(root/'.work/phase9a-extra/b0-regression.json');require(gate['status']=='PASS' and gate['exit_code']==0 and gate['execution_commit']==OLD_E,'Inherited B0 regression not passed')
    return evidence


def admission(root, auth, host):
    require(host.get('status')=='ELIGIBLE' and host.get('severe_pressure') is False and host.get('active_numerical_processes')==[], 'RESOURCE_BLOCKED: unavailable or unsafe current host')
    p=policy_for(auth,'X-K6-SCF');require(host['total_memory_bytes']>=p['limit_bytes'],'RESOURCE_BLOCKED: host physical memory below policy')
    history=inherited_records(root);old=history['X-K6-SCF']['outer'];worker=history['X-K6-SCF']['worker'];saved=old['admission']['decision']
    engine=json.loads(json.dumps(saved['engineering']));require(engine['terms_bytes']['runtime_library_margin_unchanged']==2*GIB,'Historical runtime margin changed')
    require(saved['observational_terms_bytes']['unobserved_fluctuation_margin']>=GIB and saved['remaining_growth_bytes']>=MIN_GROWTH,'Historical fluctuation/growth missing')
    group=old['resource']['peak_aggregate_rss_bytes'];native=worker['peak_rss_bytes'];require(group==7447937024 and native==7528939520,'Original formal observation differs')
    import gzip, math
    manifest=read(Path(root)/'results/soc-extra/evidence.json')
    entry=next(x for x in manifest['artifacts'] if x['action']=='X-K6-SCF' and x['kind']=='lifecycle')
    payload=Path(root)/entry['path'];require(sha(payload)==entry['sha256'],'Old lifecycle public bytes changed')
    plain=gzip.decompress(payload.read_bytes());require(hashlib.sha256(plain).hexdigest()==entry['public_sha256'],'Old lifecycle content changed')
    complete=[json.loads(line) for line in plain.splitlines() if json.loads(line).get('event')=='complete_map']
    require(len(complete)==1 and complete[0]['history_map_count']==1,'Old formal complete-map count differs')
    observed=complete[0];engine['serialization_allowance_bytes']=max(engine['serialization_allowance_bytes'],math.ceil(1.25*observed['serialization_buffer_capacity_bytes']))
    engine['terms_bytes']['callback_serialization_active_buffer']=engine['serialization_allowance_bytes']
    engine['map_estimate_bytes']=sum(engine['terms_bytes'].values());engine['estimated_peak_bytes']=max(engine['map_estimate_bytes'],engine['construction_estimate_bytes'])
    engine['estimated_peak_gib']=engine['estimated_peak_bytes']/GIB
    needed=engine['history_400_bytes']-observed['history_bytes']+engine['serialization_allowance_bytes']-observed['serialization_buffer_capacity_bytes']+128*1024**2+GIB
    require(p['remaining_growth_bytes']>=needed>=MIN_GROWTH,'Fixed growth does not cover original formal history/buffer observations')
    predicted=max(group,native)+p['remaining_growth_bytes'];require(p['remaining_growth_bytes']>=saved['remaining_growth_bytes'],'Fixed remaining growth reduced')
    require(engine['estimated_peak_bytes']==max(sum(engine['terms_bytes'].values()),sum(engine['construction_terms_bytes'].values())), 'Historical engineering arithmetic differs')
    require(predicted<p['limit_bytes'] and engine['estimated_peak_bytes']<p['limit_bytes'],'RESOURCE_BLOCKED: inherited formal observations plus fixed growth do not fit')
    return dict(status='PROVISIONAL_GO_WITH_MONITORING',source_engineering=engine,updated_growth_required_bytes=needed,historical_lifecycle_sha256=entry['public_sha256'],
                historical_formal_group_peak_bytes=group,historical_formal_worker_highwater_bytes=native,
                observed_floor_bytes=max(group,native),remaining_growth_bytes=p['remaining_growth_bytes'],
                observational_estimate_bytes=predicted,limit_bytes=p['limit_bytes'],host=host,
                inherited_receipts={a:{k:v for k,v in x.items() if k not in ('outer','worker')} for a,x in history.items()},
                scope='New admission from old formal observations and unchanged complete object budget; not a guarantee or execution PASS')


def verify_contract(root,path,execution,profile):
    root=Path(root).resolve();original=Path(path);require(not original.is_symlink(),'Linked continuation grant refused')
    path=original.resolve();auth=read(path);p=plan(root)
    require(type(auth.get('schema_version')) is int and auth['schema_version']==1 and auth.get('continuation_id')==ID and auth.get('source_start')==START,'Unrecognized continuation grant')
    require(profile=='K6' and auth.get('profile')=='K6' and auth.get('experiment')=='soc-extra-v1','Continuation cannot grant another case')
    require(re.fullmatch('[0-9a-f]{40}',execution) and auth['execution_commit']==execution==git(root,'rev-parse','HEAD'),'Wrong actual E_new')
    require(git(root,'branch','--show-current')==p['branch'] and not git(root,'status','--porcelain','--untracked-files=all'),'Wrong branch or dirty execution tree')
    require(subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',START,execution],capture_output=True).returncode==0,'Continuation start missing')
    require(path.parent==root/'.work/phase9a-extra/authorizations' and not path.is_symlink(),'Wrong local grant path')
    require(auth.get('continuation_plan_sha256')==sha(root/PLAN) and auth.get('case_sha256')==p['case_sha256']==sha(root/p['case']),'Case/plan changed')
    require(auth.get('core_selection')=='baseline' and auth.get('numerical_change_requires_B0') is False,'Only unchanged core inheritance allowed')
    a,c=policies(root,execution);require(auth.get('resource_policies')==a and auth.get('check_resource_policies')==c,'Policy/run/action allowance changed')
    require(auth.get('resource_policy_hashes')=={k:digest(v) for k,v in a.items()} and auth.get('check_resource_policy_hashes')=={k:digest(v) for k,v in c.items()},'Policy digest map differs')
    registry=verify_registry(root,path,auth)
    proof=source_proof(root,execution);require(auth.get('executed_source_sha256')==proof['executed_source_sha256'] and auth.get('source_proof_sha256')==digest(proof),'Source inheritance/current inventory changed')
    source=read(root/'benchmarks/si-soc-splitting-v1/source.json');upf=root/source['local_path'];require(upf.is_file() and not upf.is_symlink() and sha(upf)==p['upf_sha256']==source['sha256'] and upf.stat().st_size==source['bytes'],'Runtime UPF differs')
    return dict(auth,contract_sha256=sha(path),contract_path=path.relative_to(root).as_posix(),allowed_actions=list(a),registry_sha256=sha(common_registry(root)))


def verify_slot(root,auth,action):
    p=policy_for(auth,action);expected=Path(auth['run_store'])/'slots'/plan(root)['slots'][action]['slot_key']
    original=Path(os.environ.get('SOC_EXTRA_SLOT_RECEIPT',''))
    require(original.is_file() and not original.is_symlink() and original.resolve()==expected,'Wrong fixed continuation slot')
    slot=read(expected)
    for key,value in [('action',action),('run_id',p['run_id']),('execution_commit',auth['execution_commit']),('contract_sha256',auth['contract_sha256']),('resource_policy_sha256',digest(p)),('attempt',plan(root)['slots'][action]['attempt'])]:
        require(slot.get(key)==value,'Slot binding differs: '+key)
    require(slot.get('worker_directory')==p['run_id']+'-dftk'==os.environ.get('SOC_EXTRA_WORKER_DIRECTORY') and slot['run_id']==os.environ.get('SOC_EXTRA_RUN_ID'),'Slot worker/run identity differs')
    require(slot.get('numerical_authorization_status')=='ELIGIBLE','Slot admission missing')
    return slot
