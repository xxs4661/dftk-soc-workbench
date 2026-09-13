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


def compare_values(ref, new, nr, nn):
    if ref['map_index']!=new['map_index'] or ref['map_index'] not in (1,2):
        raise ValueError('Must pair identical new map numbers')
    if ref['kpoints']!=new['kpoints'] or len(ref['kpoints'])!=8:
        raise ValueError('B0 k coordinates differ; output-order matching is forbidden')
    a,b=ref['eigenvalues_ha'],new['eigenvalues_ha']
    if len(a)!=8 or len(b)!=8 or any(len(x)!=24 for x in a+b):
        raise ValueError('Eight k points and 24 physical levels required')
    diffs=[y-x for xk,yk in zip(a,b) for x,y in zip(xk,yk)]
    de=new['internal_energy_ha']-ref['internal_energy_ha']
    df=new['free_energy_ha']-ref['free_energy_ha']
    if len(nr)!=len(nn) or not nr:
        raise ValueError('Density shape differs')
    dn=norm([y-x for x,y in zip(nr,nn)])/max(norm(nr),norm(nn),1)
    error=max(abs(x) for x in diffs)
    if not all(math.isfinite(x) for x in [de,df,dn,error,*diffs]):
        raise ValueError('Nonfinite comparison')
    return dict(map_index=ref['map_index'],delta_E_ha=de,delta_F_ha=df,
                density_relative_l2=dn,raw_level_max_abs_ha=error,
                raw_level_rms_ha=norm(diffs)/math.sqrt(len(diffs)),
                status='PASS' if abs(de)<=ENERGY_ATOL and abs(df)<=ENERGY_ATOL and
                dn<=DENSITY_RTOL and error<=LEVEL_ATOL else 'FAIL')


def pair(root):
    area=Path(root)/'.work/soc-timing'
    parents=[json.loads((area/(task+'-accepted.json')).read_text()) for task in ('T-B0-REF','T-B0-TIMED')]
    if parents[0]['execution_commit']!=parents[1]['execution_commit']:
        raise ValueError('B0 pair adapter commits differ')
    workers=[]
    for parent,task in zip(parents,('T-B0-REF','T-B0-TIMED')):
        directory=Path(parent['directory'])
        if directory!=directory.resolve() or directory.parent!=area.resolve()/'runs' or directory.name!=parent['run_id']:
            raise ValueError('B0 parent directory does not belong to this batch')
        outer=json.loads((directory/'result.json').read_text())
        raw=(directory/'worker/result.json').read_bytes();worker=json.loads(raw)
        if hashlib.sha256(raw).hexdigest()!=outer.get('worker_result_sha256'):
            raise ValueError('Worker bytes do not match recorder')
        source=E0 if task=='T-B0-REF' else parent['execution_commit']
        for rec in (outer,worker):
            if any(rec.get(k)!=v for k,v in dict(task_id=task,run_id=parent['run_id'],
                    execution_commit=parent['execution_commit'],source_commit=source,exit_code=0,
                    execution_status='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED').items()):
                raise ValueError('B0 parent status/source identity differs')
        workers.append(worker)
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
            if any(rec.get(k)!=receipt[k] for k in ('run_id','execution_commit','source_commit')):
                raise ValueError('Map summary belongs to another execution')
            if rec['density_file']!=f'map-{imap:03d}-density.f64':
                raise ValueError('Unconfined/wrong-map density export')
            records.append(rec)
            densities.append(density(worker/rec['density_file'],rec['density_file_sha256']))
        result['maps'].append(compare_values(*records,*densities))
    result['status']='PASS' if all(m['status']=='PASS' for m in result['maps']) else 'FAIL'
    path=area/'b0-equivalence.json'
    with path.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    return result


if __name__=='__main__':
    try:
        value=pair(Path(__file__).resolve().parents[2]);print(json.dumps(value,indent=2))
        sys.exit(0 if value['status']=='PASS' else 1)
    except Exception as error:
        print(type(error).__name__+': '+str(error),file=sys.stderr);sys.exit(9)
