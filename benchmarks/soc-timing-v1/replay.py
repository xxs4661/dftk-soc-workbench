"""Read-only arithmetic checks of the public short-diagnostic evidence."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys


def require(condition, reason):
    if not condition:raise ValueError(reason)


def spans(rows):
    """Validate complete serial span trees without adding inclusive parents twice."""
    groups={}
    integer_fields=('pid','span_id','parent_span','map_index','k_index','start_offset_ns',
                    'end_offset_ns','inclusive_ns','exclusive_ns','calls')
    for source in rows:
        row=dict(source)
        for field in integer_fields:row[field]=int(row[field])
        require(row['status'] in ('COMPLETE','DIAGNOSTIC_COMPLETED','STOPPED','ERROR'),'Unknown closed span status')
        require(row['inclusive_ns']==row['end_offset_ns']-row['start_offset_ns']>=0,'Span elapsed mismatch')
        require(0<=row['exclusive_ns']<=row['inclusive_ns'] and row['calls']==1,'Span self/call mismatch')
        key=(row['run_id'],row['pid']);group=groups.setdefault(key,{})
        require(row['span_id'] not in group,'Duplicate span id')
        group[row['span_id']]=row
    result={}
    for (run,pid),byid in groups.items():
        children={key:[] for key in byid};roots=[]
        for key,row in byid.items():
            parent=row['parent_span']
            if not parent:roots.append(row);continue
            require(parent in byid,'Parent span not published; coverage is incomplete')
            p=byid[parent]
            require(p['start_offset_ns']<=row['start_offset_ns']<=row['end_offset_ns']<=p['end_offset_ns'],'Child interval escapes parent')
            require(parent<key,'Invalid ancestry/cycle')
            children[parent].append(row)
        for key,row in byid.items():
            ordered=sorted(children[key],key=lambda r:r['start_offset_ns'])
            require(all(a['end_offset_ns']<=b['start_offset_ns'] for a,b in zip(ordered,ordered[1:])),'Overlapping serial child intervals')
            require(row['inclusive_ns']-sum(c['inclusive_ns'] for c in ordered)==row['exclusive_ns'],'Exclusive arithmetic mismatch')
        ordered=sorted(roots,key=lambda r:r['start_offset_ns'])
        require(all(a['end_offset_ns']<=b['start_offset_ns'] for a,b in zip(ordered,ordered[1:])),'Overlapping root spans')
        attributed=sum(row['exclusive_ns'] for row in byid.values())
        require(attributed==sum(row['inclusive_ns'] for row in roots),'Hierarchy accounting does not close')
        phase={}
        for row in byid.values():
            p=phase.setdefault(row['name'],dict(inclusive_ns=0,exclusive_ns=0,calls=0))
            for field in p:p[field]+=row[field]
        result[run]=dict(pid=pid,span_count=len(byid),attributed_exclusive_ns=attributed,
                         phases=phase,maps=[dict(map_index=r['map_index'],inclusive_ns=r['inclusive_ns'],status=r['status'])
                                           for r in byid.values() if r['name']=='map_total'])
    return result


def replay(directory):
    directory=Path(directory)
    data=json.loads((directory/'runs.json').read_text())
    require(data['schema_version']==1 and data['phase']=='9A-timing-cancellation','Wrong evidence schema/scope')
    for name,digest in data['public_files_sha256'].items():
        p=directory/name
        require(p.resolve().is_relative_to(directory.resolve()) and not p.is_symlink(),'Escaping public evidence path')
        require(hashlib.sha256(p.read_bytes()).hexdigest()==digest,'Public bytes changed: '+name)
    with (directory/'timing.csv').open(newline='') as stream:timing=spans(list(csv.DictReader(stream)))
    tasks={r['task_id']:r for r in data['runs']}
    require(set(tasks)=={'T-B0-REF','T-B0-TIMED','T-K4-TIMED'},'Fixed three-slot matrix missing')
    for name,r in tasks.items():
        if r['execution_status'].startswith(('NOT_RUN','BLOCKED')):
            require(r.get('native_exit_code') is None,'Unrun task claims a native exit');continue
        require(r['limit_bytes']==8*1024**3 and r['warning_bytes']==7*1024**3,'Wrong diagnostic resource limits')
        if r['execution_status']=='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED':
            require(r['native_exit_code']==r['recorder_exit_code']==0 and r['completed_maps']==2,'Diagnostic completion contradicts process/maps')
            require(r['runtime_closed'] and r['workspace_released'] and r['owned_process_cleanup_status']=='PASS','Unconfirmed diagnostic close')
        if r['run_id'] in timing:
            measured=timing[r['run_id']]['attributed_exclusive_ns']/1e9
            require(measured<=r['worker_wall_seconds']+0.1,'Spans exceed parent worker lifetime')
            require(math.isclose(r['attributed_exclusive_seconds'],measured,rel_tol=1e-12,abs_tol=1e-8),'Published attributed time differs')
            require(math.isclose(r['uncovered_seconds'],r['worker_wall_seconds']-measured,abs_tol=1e-8),'Uncovered arithmetic differs')
    pair=json.loads((directory/'b0-equivalence.json').read_text())
    if pair['status']=='PASS':
        require([m['map_index'] for m in pair['maps']]==[1,2],'Incomplete B0 pair')
        for m in pair['maps']:
            require(abs(m['delta_E_ha'])<=1e-10 and abs(m['delta_F_ha'])<=1e-10 and
                    0<=m['density_relative_l2']<=1e-10 and 0<=m['raw_level_max_abs_ha']<=1e-9,'B0 pair exceeds fixed observation contract')
    if tasks['T-K4-TIMED']['execution_status']=='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED':
        require(pair['status']=='PASS','K4 lacked the paired B0 gate')
    return dict(replay_status='PASS',scope='Published byte identities and timing/scalar arithmetic; no material calculation or private-density re-evaluation',
                task_status={k:v['execution_status'] for k,v in tasks.items()},b0_equivalence_status=pair['status'],
                scientific_convergence_status='NOT_ASSESSED',instrumentation_overhead_status=data['instrumentation_overhead_status'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,default=Path(__file__).resolve().parents[2]/'results/soc-timing')
    args=parser.parse_args()
    try:print(json.dumps(replay(args.results),indent=2))
    except Exception as error:print(type(error).__name__+': '+str(error),file=sys.stderr);sys.exit(9)
