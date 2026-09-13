"""Read-only arithmetic checks of the public short-diagnostic evidence."""
import argparse
import csv
import gzip
import itertools
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



def public_map_data(directory, data, tasks):
    """Read authenticated small summaries only; never follow private density paths."""
    name='map-spectra.json.gz'
    require(name in data['public_files_sha256'],'Public map/spectrum package is not authenticated')
    package=json.loads(gzip.decompress((directory/name).read_bytes()))
    require(type(package) is dict and set(package)==set(tasks),'Map package task matrix differs')
    def finite(x):return type(x) in (int,float) and math.isfinite(x)
    indexed={}
    for task,row in tasks.items():
        records=package[task]
        count=row.get('completed_maps',0)
        require(type(count) is int and 0<=count<=2 and type(records) is list and len(records)==count,
                'Published map count differs from completed maps')
        require([r.get('map_index') for r in records]==list(range(1,count+1)) and
                all(type(r.get('map_index')) is int for r in records),'Map indices missing or duplicated')
        axis=(0.,.25,.5,.75) if task=='T-K4-TIMED' else (0.,.5)
        expected=set(itertools.product(axis,repeat=3));bound=[]
        for rec in records:
            for key in ('run_id','task_id','execution_commit','source_commit','case_sha256'):
                require(key in rec and key in row and rec[key]==row[key],'Map identity differs: '+key)
            points,levels,occupations=rec['kpoints'],rec['eigenvalues_ha'],rec['occupations']
            require(len(points)==len(levels)==len(occupations)==len(expected),'Wrong explicit k or state-row count')
            require(all(type(k) is list and len(k)==3 and all(finite(x) for x in k) for k in points),'Invalid k coordinate')
            keys=[tuple(float(x)%1 for x in k) for k in points]
            require(len(set(keys))==len(keys) and set(keys)==expected,'Missing, duplicate or unexpected k coordinate')
            require(all(type(v) is list and len(v)==24 and all(finite(x) for x in v)
                        for v in levels+occupations),'Expected 24 finite physical states per k')
            require(all(finite(rec[key]) for key in ('internal_energy_ha','free_energy_ha')),'Nonfinite map energy')
            bound.append((rec,dict(zip(keys,levels))))
        indexed[task]=bound
    return indexed


def b0_energy_spectrum_replay(indexed, pair):
    if pair['status'] not in ('PASS','FAIL'):
        return dict(status='NOT_ASSESSED',reason='No completed paired comparison')
    ref,new=indexed['T-B0-REF'],indexed['T-B0-TIMED']
    require(len(ref)==len(new)==2 and [m['map_index'] for m in pair['maps']]==[1,2],
            'Paired energy/spectrum comparison requires two complete B0 maps')
    output=[]
    for imap,((a,ak),(b,bk)),stored in zip((1,2),zip(ref,new),pair['maps']):
        require(a['case_sha256']==b['case_sha256'],'Paired B0 physical cases differ')
        # Match fractional coordinates modulo reciprocal integers, never levels
        # by proximity. Preserve all 24 original energies and the global offset.
        differences=[y-x for key in ak for x,y in zip(ak[key],bk[key])]
        values=dict(delta_E_ha=b['internal_energy_ha']-a['internal_energy_ha'],
                    delta_F_ha=b['free_energy_ha']-a['free_energy_ha'],
                    raw_level_max_abs_ha=max(abs(x) for x in differences),
                    raw_level_rms_ha=math.sqrt(math.fsum(x*x for x in differences))/math.sqrt(len(differences)))
        for key,value in values.items():
            require(type(stored.get(key)) in (int,float) and math.isfinite(stored[key]) and stored[key]==value,
                    'Stored B0 metric differs from published energies/levels: '+key)
        output.append(dict(map_index=imap,**values))
    return dict(status='PASS',maps=output,
                density_scope='RUNNER_REPORTED_PRIVATE_ARRAY_COMPARISON; density arrays are not opened by public replay')


def replay(directory):
    directory=Path(directory)
    data=json.loads((directory/'runs.json').read_text())
    require(data['schema_version']==1 and data['phase']=='9A-timing-cancellation','Wrong evidence schema/scope')
    for name,digest in data['public_files_sha256'].items():
        p=directory/name
        require(p.resolve().is_relative_to(directory.resolve()) and not p.is_symlink(),'Escaping public evidence path')
        require(hashlib.sha256(p.read_bytes()).hexdigest()==digest,'Public bytes changed: '+name)
    with (directory/'timing.csv').open(newline='') as stream:timing=spans(list(csv.DictReader(stream)))
    require(type(data['runs']) is list and len(data['runs'])==3 and
            all(type(r) is dict for r in data['runs']),'Exactly three task records required')
    require(len({r['task_id'] for r in data['runs']})==3,'Duplicate task records')
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
        b0=[tasks[name] for name in ('T-B0-REF','T-B0-TIMED')]
        require(all(r['execution_status']=='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED'
                    for r in b0),'B0 pair PASS requires both qualified diagnostics')
        require(type(pair.get('execution_commit')) is str and
                all(r.get('execution_commit')==pair['execution_commit'] for r in b0),
                'B0 pair execution differs from its task records')
        require(pair.get('run_ids')==[r['run_id'] for r in b0],
                'B0 pair belongs to different runs')
        require([m['map_index'] for m in pair['maps']]==[1,2],'Incomplete B0 pair')
        for m in pair['maps']:
            require(abs(m['delta_E_ha'])<=1e-10 and abs(m['delta_F_ha'])<=1e-10 and
                    0<=m['density_relative_l2']<=1e-10 and 0<=m['raw_level_max_abs_ha']<=1e-9,'B0 pair exceeds fixed observation contract')
    public_maps=public_map_data(directory,data,tasks)
    public_pair=b0_energy_spectrum_replay(public_maps,pair)
    if tasks['T-K4-TIMED']['execution_status']=='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED':
        require(pair['status']=='PASS','K4 lacked the paired B0 gate')
    return dict(replay_status='PASS',scope='Published byte identities and timing/scalar arithmetic; no material calculation or private-density re-evaluation',
                task_status={k:v['execution_status'] for k,v in tasks.items()},b0_equivalence_status=pair['status'],
                b0_public_energy_spectrum_replay=public_pair,
                scientific_convergence_status='NOT_ASSESSED',instrumentation_overhead_status=data['instrumentation_overhead_status'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,default=Path(__file__).resolve().parents[2]/'results/soc-timing')
    args=parser.parse_args()
    try:print(json.dumps(replay(args.results),indent=2))
    except Exception as error:print(type(error).__name__+': '+str(error),file=sys.stderr);sys.exit(9)
