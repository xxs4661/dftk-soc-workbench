"""Public arithmetic replay of four bounded validation diagnostics, never a solve."""
import argparse
import csv
import gzip
import hashlib
import importlib.util
import io
import itertools
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('boundary_timing_arithmetic',ROOT/'benchmarks/soc-timing-v1/replay.py')
timing=importlib.util.module_from_spec(spec);spec.loader.exec_module(timing)
require=timing.require
TASKS=('V-B0-REF','V-B0-OPT','V-K4-REF','V-K4-OPT')
R='d9e19af3557c923a1e4f7e64510092d47975cc7c'
PROTECTION_CATEGORIES=frozenset(('protection-equivalence','hash-equivalence','cancellation-timeout',
    'source-entry','full-syntax','legacy-control','public-arithmetic','legacy-timer'))

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def finite(x):return type(x) in (int,float) and math.isfinite(x)
def digest(value,length):return type(value) is str and len(value)==length and all(c in '0123456789abcdef' for c in value)

def protection_receipt(proof,record):
    """Bind successful coverage to the exact preparation and executed source map.

    This replays a runner's public receipt, not execution of its private tests.
    The eight categories are the same required union as the physical launcher.
    """
    protection=record['protection_status']
    require(type(proof) is dict and type(proof.get('schema_version')) is int and
            proof['schema_version']==1 and proof.get('experiment')=='soc-boundary-v1',
            'Wrong protection receipt schema')
    require(proof.get('status')==protection,'Protection outcome contradicts its receipt')
    if protection!='PASS':return
    prepared=record.get('preparation_commit')
    require(digest(prepared,40) and proof.get('preparation_commit')==prepared,
            'Protection preparation commit is absent or differs')
    required=record.get('required_source_sha256');tested=proof.get('tested_source_sha256')
    require(type(required) is dict and bool(required) and all(
        type(path) is str and bool(path) and not Path(path).is_absolute() and
        '..' not in Path(path).parts and digest(value,64) for path,value in required.items()),
        'Missing valid required execution source map')
    require(type(tested) is dict and all(tested.get(path)==value for path,value in required.items()),
            'Protection tested source bytes differ from required execution source bytes')
    checks=proof.get('checks');categories=set()
    require(type(checks) is list and bool(checks),'Protection PASS lacks actual successful checks')
    for check in checks:
        require(type(check) is dict and type(check.get('exit_code')) is int and check['exit_code']==0 and
                type(check.get('command')) is list and bool(check['command']) and
                all(type(arg) is str and bool(arg) for arg in check['command']),
                'Protection PASS lacks actual successful checks')
        tags=check.get('categories')
        require(type(tags) is list and bool(tags) and all(type(t) is str and t in PROTECTION_CATEGORIES for t in tags),
                'Protection check has missing or unknown categories')
        categories.update(tags)
    require(categories==PROTECTION_CATEGORIES,'Required protection categories are incomplete')

def task_spans(rows,record,complete):
    """Validate task identity before the legacy tree reducer can group rows."""
    require(type(rows) is list,'Task spans must be a list')
    fields=('pid','span_id','parent_span','map_index','k_index','start_offset_ns',
            'end_offset_ns','inclusive_ns','exclusive_ns','calls')
    for row in rows:
        require(type(row) is dict and row.get('run_id')==record['run_id'],
                'Task span run identity differs')
        require(all(type(row.get(k)) is int and row[k]>=0 for k in fields) and
                row['pid']>0 and row['span_id']>0,'Invalid integer span identity or PID')
    if rows:
        pid=record.get('numerical_process_pid')
        require(type(pid) is int and pid>0 and all(row['pid']==pid for row in rows),
                'Span PID differs from authenticated numerical process PID')
    require(len({row['pid'] for row in rows})<=1,'Multiple worker PIDs in one task span stream')
    if not complete:return
    require(bool(rows),'Completed task has no spans')
    roots=[row for row in rows if row['parent_span']==0]
    workers=[row for row in rows if row.get('name')=='worker_total']
    require(len(roots)==len(workers)==1 and roots[0] is workers[0],
            'Completed task requires exactly one worker_total root')
    require(workers[0]['status'] in ('COMPLETE','DIAGNOSTIC_COMPLETED'),
            'Completed task has incomplete worker_total status')
    maps=sorted((row for row in rows if row.get('name')=='map_total'),key=lambda row:row['map_index'])
    require([row['map_index'] for row in maps]==[1,2],'Completed task requires both unique map_total spans')
    require(maps[0]['status']=='COMPLETE' and maps[1]['status'] in ('COMPLETE','DIAGNOSTIC_COMPLETED'),
            'Completed task has incomplete map_total status')

def spectrum(record,nk):
    coords=record['kpoints'];e=record['eigenvalues_ha'];f=record['occupations']
    require(len(coords)==len(e)==len(f)==nk,'Wrong declared k count')
    axis=(0.,.5) if nk==8 else (0.,.25,.5,.75)
    expected=set(itertools.product(axis,repeat=3));keys=[]
    for k in coords:
        require(type(k) is list and len(k)==3 and all(finite(x) for x in k),'Invalid k coordinate')
        keys.append(tuple(float(v)%1 for v in k))
    require(len(set(keys))==nk and set(keys)==expected,'Wrong/duplicate explicit k coordinates')
    require(all(type(v) is list and len(v)==24 and all(finite(x) for x in v) for v in e+f),'24 finite physical states required')
    require(all(0<=x<=1 for row in f for x in row),'Invalid capacity-one occupations')
    require(abs(math.fsum(x for row in f for x in row)/nk-8)<=1e-8,'Wrong valence electron count')
    require(all(finite(record[k]) for k in ('internal_energy_ha','free_energy_ha')),'Nonfinite E/F')
    return dict(zip(keys,e))

def compare_maps(a,b,nk):
    require(a['map_index']==b['map_index'] and type(a['map_index']) is int and a['map_index'] in (1,2),'Wrong same-map pair')
    x,y=spectrum(a,nk),spectrum(b,nk)
    ds=[new-old for k in x for old,new in zip(x[k],y[k])]
    return dict(map_index=a['map_index'],delta_E_ha=b['internal_energy_ha']-a['internal_energy_ha'],
                delta_F_ha=b['free_energy_ha']-a['free_energy_ha'],raw_level_max_abs_ha=max(map(abs,ds)),
                raw_level_rms_ha=math.sqrt(math.fsum(v*v for v in ds))/math.sqrt(len(ds)))

def aggregate(spans,contract):
    pids={}
    for row in spans:
        require(row['run_id'] not in pids or pids[row['run_id']]==row['pid'],
                'Multiple worker PIDs cannot overwrite one run timing result')
        pids[row['run_id']]=row['pid']
    trees=timing.spans(spans);out={}
    categories=contract['stage_categories']
    for run,tree in trees.items():
        rows=[];validation=0;legacy=0
        for name,p in sorted(tree['phases'].items()):
            require(name in categories,'Unclassified stage: '+name)
            category=categories[name]
            require(category in ('VALIDATION','VALIDATION_MIXED','OTHER_OR_UNATTRIBUTED'),'Unknown category')
            seconds=p['exclusive_ns']/1e9
            if category in ('VALIDATION','VALIDATION_MIXED'):validation+=seconds
            if name in ('runtime_boundary_entry','runtime_boundary_return','checkpoint_validation_before','checkpoint_validation_after'):legacy+=seconds
            rows.append(dict(name=name,category=category,calls=p['calls'],inclusive_seconds=p['inclusive_ns']/1e9,self_seconds=seconds))
        out[run]=dict(span_count=tree['span_count'],worker_span_seconds=tree['attributed_exclusive_ns']/1e9,
                      validation_total_seconds=validation,legacy_four_groups_self_seconds=legacy,phases=rows,maps=tree['maps'])
    return out

def replay(directory,contract_path=None):
    directory=Path(directory);contract_path=Path(contract_path or ROOT/'benchmarks/soc-boundary-v1/contract.json')
    contract=json.loads(contract_path.read_text());record=json.loads((directory/'runs.json').read_text())
    require(record['schema_version']==1 and record['experiment']=='soc-boundary-v1','Wrong result schema')
    require(record['contract_sha256']==sha(contract_path),'Declared contract bytes changed')
    require(contract['reference_commit']==R and tuple(contract['tasks'])==TASKS,'Fixed matrix/reference changed')
    require(contract['numerical_limits']==dict(energy_ha=1e-10,density_relative_l2=1e-10,raw_level_max_ha=1e-9),'Scientific thresholds changed')
    require(contract['performance_limits']==dict(k4_validation_ratio=.5,k4_monitor_wall_ratio=.8),'Performance targets changed')
    for name,digest in record['public_files_sha256'].items():
        p=directory/name
        require(p.resolve().is_relative_to(directory.resolve()) and not p.is_symlink(),'Escaping evidence path')
        require(sha(p)==digest,'Public bytes differ: '+name)
    require('data.json.gz' in record['public_files_sha256'],'Canonical numeric package unbound')
    data=json.loads(gzip.decompress((directory/'data.json.gz').read_bytes()))
    require(type(record['runs']) is list and len(record['runs'])==4,'Expected four slot records')
    require(tuple(r['task_id'] for r in record['runs'])==TASKS,'Wrong/duplicate task matrix')
    require(set(data)==set(TASKS),'Canonical numeric package differs from task matrix')
    bytask={r['task_id']:r for r in record['runs']};complete=[];spanrows=[];run_ids=set()
    for task,r in bytask.items():
        require(r['source_commit']==(R if task.endswith('REF') else record['execution_commit']),'Wrong numerical source')
        require(r['execution_commit']==record['execution_commit'],'Wrong adapter version')
        require(r['timing_enabled'] is True,'Both paths must have identical timing enabled')
        require(r['validation_policy']==contract['tasks'][task]['validation_policy'],'Wrong internal strategy')
        status=r['execution_status'];ok=status=='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED';complete.append(ok)
        if r['run_id'] is not None:
            require(type(r['run_id']) is str and bool(r['run_id']) and r['run_id'] not in run_ids,
                    'Tasks may not share or omit a run identity')
            run_ids.add(r['run_id'])
        if ok:
            require(r['run_id'] is not None,'Completed task has no run identity')
            require(r['native_exit_code']==r['worker_exit_code']==r['recorder_exit_code']==0,'Completion contradicts exit codes')
            require(r['completed_maps']==2 and r['runtime_closed'] is True and r['workspace_released'] is True and r['owned_process_cleanup_status']=='PASS','Incomplete diagnostic or cleanup')
            require(r['limit_bytes']==8*1024**3 and r['warning_bytes']==7*1024**3 and r['remaining_growth_bytes']==2*1024**3,'Wrong resource contract')
            require(r['final_bin_present'] is False,'Diagnostic must not publish a converged checkpoint')
            require([m['map_index'] for m in data[task]['maps']]==[1,2],'Incomplete map outputs')
        elif status.startswith(('NOT_RUN','BLOCKED')):
            require(r['native_exit_code'] is None,'Unrun slot claims a native exit')
        for m in data[task]['maps']:
            for key in ('task_id','run_id','source_commit','execution_commit','case_sha256'):
                require(m[key]==r[key],'Wrong map origin: '+key)
            spectrum(m,8 if '-B0-' in task else 64)
        task_spans(data[task]['spans'],r,ok)
        spanrows+=data[task]['spans']
    times=aggregate(spanrows,contract)
    for r in bytask.values():
        if r['run_id'] in times:
            elapsed=times[r['run_id']]['worker_span_seconds']
            require(finite(r['monitor_wall_seconds']) and elapsed<=r['monitor_wall_seconds']+.1,'Spans exceed monitored worker')
            times[r['run_id']]['uncovered_monitor_seconds']=r['monitor_wall_seconds']-elapsed
    pairs={};numeric=True
    for profile,nk in [('B0',8),('K4',64)]:
        a,b='V-'+profile+'-REF','V-'+profile+'-OPT'
        if not all(bytask[t]['execution_status']=='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED' for t in (a,b)):
            pairs[profile]={'status':'NOT_ASSESSED','maps':[]};numeric=False;continue
        require(bytask[a]['case_sha256']==bytask[b]['case_sha256'],'Paired REF/OPT physical case hashes differ')
        stored=record['pairs'][profile]
        require(stored['run_ids']==[bytask[t]['run_id'] for t in (a,b)] and stored['execution_commit']==record['execution_commit'],'Pair source identity differs')
        require(len(stored['maps'])==2,'Paired receipt incomplete')
        pairrows=[]
        for x,y,s in zip(data[a]['maps'],data[b]['maps'],stored['maps']):
            values=compare_maps(x,y,nk)
            require(s['map_index']==values['map_index'],'Pair map index differs')
            for key,value in values.items():require(s[key]==value,'Published comparison arithmetic differs: '+key)
            dn=s['density_relative_l2'];require(finite(dn) and dn>=0,'Invalid runner density metric')
            require(s['density_denominator']>=1 and all(finite(s[k]) for k in ('density_difference_norm','density_reference_norm','density_candidate_norm','density_denominator')),'Missing density norm provenance')
            require(s['density_denominator']==max(s['density_reference_norm'],s['density_candidate_norm'],1),'Density norm denominator differs')
            require(dn==s['density_difference_norm']/s['density_denominator'],'Density summary arithmetic differs')
            ok=abs(values['delta_E_ha'])<=1e-10 and abs(values['delta_F_ha'])<=1e-10 and values['raw_level_max_abs_ha']<=1e-9 and dn<=1e-10
            pairrows.append(dict(**values,density_relative_l2_runner_reported=dn,status='PASS' if ok else 'FAIL'))
        status='PASS' if all(r['status']=='PASS' for r in pairrows) else 'FAIL';numeric&=status=='PASS'
        require(stored['status']==status,'Stored numeric acceptance inconsistent')
        pairs[profile]=dict(status=status,maps=pairrows)
    performance={'status':'NOT_ASSESSED'}
    if all(bytask[t]['execution_status']=='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED' for t in ('V-K4-REF','V-K4-OPT')):
        a,b=(bytask[t] for t in ('V-K4-REF','V-K4-OPT'))
        validation=times[b['run_id']]['validation_total_seconds']/times[a['run_id']]['validation_total_seconds'];wall=b['monitor_wall_seconds']/a['monitor_wall_seconds']
        performance=dict(validation_ratio=validation,monitor_wall_ratio=wall,validation_target_status='PASS' if validation<=.5 else 'PERFORMANCE_TARGET_NOT_MET',wall_target_status='PASS' if wall<=.8 else 'PERFORMANCE_TARGET_NOT_MET',status='PASS' if validation<=.5 and wall<=.8 else 'PERFORMANCE_TARGET_NOT_MET')
    protection=record['protection_status'];require(protection in ('PASS','FAIL','NOT_ASSESSED'),'Unknown protection status')
    require('protection.json.gz' in record['public_files_sha256'],'Protection receipt is not bound')
    proof=json.loads(gzip.decompress((directory/'protection.json.gz').read_bytes()))
    protection_receipt(proof,record)
    accepted=all(complete) and numeric and protection=='PASS' and performance['status']=='PASS'
    return dict(replay_status='PASS',strict_optimization_status='PASS' if accepted else 'NOT_ACCEPTED',protection_status=protection,pairs=pairs,performance=performance,timing=times,scientific_convergence_status='NOT_ASSESSED',density_scope='Published norm arithmetic only; acquisition and array norms runner-reported, private density arrays not read',performance_scope='One fresh cold pair, not statistical generality or old K6 reconstruction')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--results',type=Path,default=ROOT/'results/soc-boundary');p.add_argument('--strict',action='store_true');p.add_argument('--tables',type=Path)
    args=p.parse_args()
    try:
        result=replay(args.results)
        if args.tables:
            args.tables.mkdir(parents=True,exist_ok=True)
            with (args.tables/'phases.csv').open('w',newline='') as stream:
                w=csv.DictWriter(stream,fieldnames=['run_id','name','category','calls','inclusive_seconds','self_seconds'],lineterminator='\n');w.writeheader()
                for run,value in result['timing'].items():
                    for row in value['phases']:w.writerow(dict(run_id=run,**row))
        brief={k:v for k,v in result.items() if k!='timing'}
        brief['timing']={run:{k:v for k,v in row.items() if k!='phases'} for run,row in result['timing'].items()}
        print(json.dumps(brief,indent=2,allow_nan=False));sys.exit(0 if not args.strict or result['strict_optimization_status']=='PASS' else 1)
    except Exception as error:print(type(error).__name__+': '+str(error),file=sys.stderr);sys.exit(9)
