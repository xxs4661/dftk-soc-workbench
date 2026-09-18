"""Same-map B0 regression, using only this batch's new raw density exports."""
import array
import hashlib
import json
import math
from pathlib import Path
import sys

ENERGY_ATOL=1e-10
DENSITY_RTOL=1e-10
LEVEL_ATOL=1e-9
E0='30befbc22ee52283a19a96694bfe20259891b583'


def norm(values):
    return math.sqrt(math.fsum(x*x for x in values))


def density(path, expected_hash):
    raw=Path(path).read_bytes()
    if len(raw)!=48**3*8 or hashlib.sha256(raw).hexdigest()!=expected_hash:
        raise ValueError('Current-map density bytes do not match their receipt')
    values=array.array('d');values.frombytes(raw)
    if sys.byteorder!='little': values.byteswap()
    if not all(math.isfinite(x) for x in values):
        raise ValueError('Nonfinite raw density')
    return values


def compare_values(ref, new, nr, nn, *, expected_kpoints=8, boundary=False):
    if ref['map_index']!=new['map_index'] or ref['map_index'] not in (1,2):
        raise ValueError('Must pair identical new map numbers')
    if expected_kpoints not in (8,64) or type(expected_kpoints)is not int:
        raise ValueError('Only explicitly requested B0/K4 point counts are supported')
    if (not boundary and ref['kpoints']!=new['kpoints']) or any(len(r['kpoints'])!=expected_kpoints for r in (ref,new)):
        raise ValueError('B0 k coordinates differ; output-order matching is forbidden')
    if boundary:
        axis=[0,-.5] if expected_kpoints==8 else [0,.25,-.5,-.25]
        expected={(x,y,z) for x in axis for y in axis for z in axis}
        coordinate_keys=[]
        for record in (ref,new):
            if any(type(p)is not list or len(p)!=3 or any(type(x)not in (int,float) or not math.isfinite(x) for x in p) for p in record['kpoints']):
                raise ValueError('Invalid explicit coordinate')
            keys=[tuple((float(x)+.5)%1-.5 for x in point) for point in record['kpoints']]
            if len(set(keys))!=expected_kpoints or set(keys)!=expected:
                raise ValueError('Declared complete coordinate set is missing/duplicated/changed')
            coordinate_keys.append(keys)
    a,b=ref['eigenvalues_ha'],new['eigenvalues_ha']
    if len(a)!=expected_kpoints or len(b)!=expected_kpoints or any(len(x)!=24 for x in a+b):
        raise ValueError('Declared point count and 24 physical levels required')
    if boundary:
        by_coordinate=dict(zip(coordinate_keys[1],b));b=[by_coordinate[k] for k in coordinate_keys[0]]
    diffs=[y-x for xk,yk in zip(a,b) for x,y in zip(xk,yk)]
    de=new['internal_energy_ha']-ref['internal_energy_ha']
    df=new['free_energy_ha']-ref['free_energy_ha']
    if len(nr)!=len(nn) or not nr:
        raise ValueError('Density shape differs')
    rn,nnorm=norm(nr),norm(nn);difference=norm([y-x for x,y in zip(nr,nn)])
    denominator=max(rn,nnorm,1);dn=difference/denominator
    error=max(abs(x) for x in diffs)
    if not all(math.isfinite(x) for x in [de,df,dn,error,*diffs]):
        raise ValueError('Nonfinite comparison')
    result=dict(map_index=ref['map_index'],delta_E_ha=de,delta_F_ha=df,
                density_relative_l2=dn,raw_level_max_abs_ha=error,
                raw_level_rms_ha=norm(diffs)/math.sqrt(len(diffs)),
                status='PASS' if abs(de)<=ENERGY_ATOL and abs(df)<=ENERGY_ATOL and
                dn<=DENSITY_RTOL and error<=LEVEL_ATOL else 'FAIL')
    if boundary:
        terms=[rec['energy_terms_ha'] for rec in (ref,new)]
        if type(terms[0])is not dict or type(terms[1])is not dict or set(terms[0])!=set(terms[1]) or len(terms[0])!=7:
            raise ValueError('Seven original energy terms required on both paths')
        if not all(type(x)in(int,float) and math.isfinite(x) for t in terms for x in t.values()):
            raise ValueError('Nonfinite/non-numeric original energy term')
        result.update(density_reference_norm=rn,density_candidate_norm=nnorm,
                      density_difference_norm=difference,density_denominator=denominator,
                      energy_terms_reference_ha=terms[0],energy_terms_candidate_ha=terms[1],
                      energy_terms_delta_ha={k:terms[1][k]-terms[0][k] for k in terms[0]})
    return result


def pair(root, *, boundary_profile=None, write_result=True):
    root=Path(root).resolve()
    if boundary_profile is None:
        area=root/'.work/soc-timing';tasks=('T-B0-REF','T-B0-TIMED');reference=E0;nk=8
    else:
        if boundary_profile not in ('B0','K4'):raise ValueError('Only registered B0/K4 boundary pairs')
        import importlib.util
        spec=importlib.util.spec_from_file_location('boundary_pair_control',Path(__file__).with_name('control.py'))
        control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)
        area=root/'.work/soc-boundary';tasks=tuple('V-'+boundary_profile+'-'+r for r in ('REF','OPT'))
        reference=control.BOUNDARY_REFERENCE;nk=8 if boundary_profile=='B0' else 64
    parents=[json.loads((area/(task+'-accepted.json')).read_text()) for task in tasks]
    if parents[0]['execution_commit']!=parents[1]['execution_commit']:
        raise ValueError('B0 pair adapter commits differ')
    workers=[]
    for parent,task in zip(parents,tasks):
        directory=Path(parent['directory'])
        if directory!=directory.resolve() or directory.parent!=area.resolve()/'runs' or directory.name!=parent['run_id']:
            raise ValueError('B0 parent directory does not belong to this batch')
        outer=json.loads((directory/'result.json').read_text())
        raw=(directory/'worker/result.json').read_bytes();worker=json.loads(raw)
        if hashlib.sha256(raw).hexdigest()!=outer.get('worker_result_sha256'):
            raise ValueError('Worker bytes do not match recorder')
        source=reference if task==tasks[0] else parent['execution_commit']
        for rec in (outer,worker):
            if any(rec.get(k)!=v for k,v in dict(task_id=task,run_id=parent['run_id'],
                    execution_commit=parent['execution_commit'],source_commit=source,exit_code=0,
                    execution_status='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED').items()):
                raise ValueError('B0 parent status/source identity differs')
        if boundary_profile is not None:
            cfg=control.load_control(directory);control.worker_contract(worker,0,cfg,directory)
            if outer.get('native_exit_code')!=0 or outer.get('resource',{}).get('owned_process_cleanup_status')!='PASS':
                raise ValueError('Boundary parent native/cleanup failed')
        workers.append(worker)
    if boundary_profile is not None and workers[0]['case_sha256']!=workers[1]['case_sha256']:
        raise ValueError('Boundary physical cases differ')
    result=dict(schema_version=1,execution_commit=parents[0]['execution_commit'],
                run_ids=[p['run_id'] for p in parents],maps=[],status='NOT_ASSESSED',
                thresholds=dict(energy_abs_ha=ENERGY_ATOL,density_relative_l2=DENSITY_RTOL,raw_level_abs_ha=LEVEL_ATOL),
                array_scope='Actual new run-local Float64 density exports; not a comparison to historical converged endpoints',
                public_scope='Runner-reported density norm comparison; public scalar arithmetic alone does not repeat the private array comparison')
    for imap in (1,2):
        records=[];densities=[]
        for parent,receipt in zip(parents,workers):
            worker=Path(parent['directory'])/'worker'
            name=f'map-{imap:03d}-summary.json';raw=(worker/name).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=receipt['map_summaries_sha256'][name]:
                raise ValueError('Map summary bytes not bound by completed worker')
            rec=json.loads(raw)
            if type(rec.get('map_index')) is not int or rec['map_index']!=imap:
                raise ValueError('Map summary index differs from its numbered file')
            keys=('run_id','execution_commit','source_commit') if boundary_profile is None else ('run_id','task_id','case_sha256','execution_commit','source_commit','validation_policy')
            if any(rec.get(k)!=receipt[k] for k in keys):
                raise ValueError('Map summary belongs to another execution')
            if rec['density_file']!=f'map-{imap:03d}-density.f64':
                raise ValueError('Unconfined/wrong-map density export')
            records.append(rec)
            densities.append(density(worker/rec['density_file'],rec['density_file_sha256']))
        result['maps'].append(compare_values(*records,*densities,expected_kpoints=nk,boundary=boundary_profile is not None))
    result['status']='PASS' if all(m['status']=='PASS' for m in result['maps']) else 'FAIL'
    if boundary_profile is not None:result.update(experiment='soc-boundary-v1',profile=boundary_profile,reference_commit=reference)
    path=area/((boundary_profile or 'B0').lower()+'-equivalence.json')
    if write_result:
        with path.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    return result


if __name__=='__main__':
    try:
        value=pair(Path(__file__).resolve().parents[2]);print(json.dumps(value,indent=2))
        sys.exit(0 if value['status']=='PASS' else 1)
    except Exception as error:
        print(type(error).__name__+': '+str(error),file=sys.stderr);sys.exit(9)
