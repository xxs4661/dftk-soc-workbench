#!/usr/bin/env python3
"""Public extra arithmetic; no physical worker, private arrays or fitted shift.

Default0 means a consistent public replay, including explicitly unrun/failed
slots. --require-k6 additionally needs the real pair and both0.1meV screens.
Malformed evidence exits2; a valid incomplete/unscreened pair exits1 in strict
mode. Occupation/manifold/physical interpretation remain separate.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import sys

BASE = '7630172808773a3d4ac2da825c27fe43a8705fb8'
QE_EXECUTION = '0af11bac432bfec7f9cf0d07b0571d3ae9449010'
Q_MANIFEST = 'results/si-soc-k-reference/evidence.json'
Q_HASH = 'fa31a34c6445dcf8c696fd1bb3d6646d661fff17b6673578a4ed53a703915132'
K4_PATH = 'results/si-soc-sensitivity/K4/data.json'
K4_HASH = 'f79c639d1260d20804d69afb6cca6eb308f4de7cc4c5318bf7651783866de5de'
B0_SOURCES = {
 'results/soc-core-memory/completion/OPT-B0-SCF/worker.json':'cd7457c4af7e14289c32626fe46a4533857c60abb816f24dc6d43884b58a7bbe',
 'results/soc-core-memory/completion/OPT-B0-GAMMA/worker.json':'a9b2dc6f69eca72d28eb871a34ea9f9b408ec8faaa55143081e119198e9b0546'}
UPF = 'cc91a6be43c3c89daf6c34410096e8d870f25152dbfb513bcf01afa5ab53eabf'
SLOTS = ('X-B0-SCF','X-B0-GAMMA','X-K6-PILOT','X-K6-SCF','X-K6-GAMMA','L-B0-SCF','L-B0-GAMMA')
OPS = ('FR_1','FR_24','full_H_24','pipeline_with_validation')
ENERGY_NAMES = {'Kinetic','AtomicLocal','AtomicNonlocalFR','Hartree','Xc','Ewald','PspCorrection'}
HARTREE_EV = 27.211386245981
WINDOW_EV = 1e-4
SATURATION = .99999999


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def number(x):
    require(type(x) in (int,float) and math.isfinite(x),'Finite numeric value required')
    return float(x)


def integer(x, minimum=0):
    require(type(x) is int and x>=minimum,'Integer field is missing or invalid')
    return x


def digest(raw): return hashlib.sha256(raw).hexdigest()


def exact_hash(value, length=64):
    require(type(value) is str and re.fullmatch('[0-9a-f]{'+str(length)+'}',value),'Malformed hash/commit')
    return value


def read(path):
    return json.loads(Path(path).read_text(),parse_constant=lambda s: (_ for _ in ()).throw(ValueError('Nonfinite JSON '+s)))


def finite_public(value):
    if type(value) is float: number(value)
    elif isinstance(value,dict):
        for key,item in value.items():
            require(not (key in {'X','all_X','P','D','wavefunctions','psi','rho','G_vectors'} and isinstance(item,list)),'Private large array field in public record')
            require(not (key in ('n_in','n_out') and isinstance(item,list)),'Private density array in public record')
            finite_public(item)
    elif isinstance(value,list):
        for item in value: finite_public(item)


def path(root, relative):
    require(type(relative) is str,'Relative public path required')
    part=Path(relative);p=Path(root).resolve()/part
    require(not part.is_absolute() and '..' not in part.parts and part.as_posix()==relative,'Escaped public path')
    require(p.is_file() and p.resolve()==p and not p.is_symlink(),'Missing/aliased public file: '+relative)
    require('.work' not in part.parts,'Private run files are not public evidence')
    return p


def fixed(root,relative,expected):
    raw=path(root,relative).read_bytes()
    require(digest(raw)==expected,'Historical file changed: '+relative)
    return raw


def artifact(root, spec):
    require(type(spec) is dict,'Artifact descriptor required')
    raw=path(root,spec['path']).read_bytes()
    require(digest(raw)==exact_hash(spec['sha256']) and len(raw)==integer(spec['bytes']),'Artifact identity mismatch')
    if 'raw_sha256' in spec: exact_hash(spec['raw_sha256'])
    if spec['path'].endswith('.gz'):
        raw=gzip.decompress(raw)
        require(digest(raw)==exact_hash(spec['public_sha256']) and len(raw)==integer(spec['public_bytes']),'Decompressed artifact differs')
    require(not re.search(rb'/(Users|home|private|Volumes)/',raw),'Private path in public evidence')
    return raw


def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],stderr=subprocess.PIPE)


def frozen_modules(root):
    names=('si_qe_reference_evidence','si_qe_reference','si_soc_comparison','parse_qe_soc',
           'parse_qe_baseline','parse_qe_soc_diagnostics','si_soc_sensitivity')
    for name in names:
        p='scripts/'+name+'.py'
        require(path(root,p).read_bytes()==git(root,'show',BASE+':'+p),'Historical parser changed: '+p)
    directory=str(Path(root).resolve()/'scripts')
    if directory not in sys.path: sys.path.insert(0,directory)
    import si_qe_reference_evidence as native
    import si_soc_comparison as arithmetic
    require(Path(native.__file__).resolve()==Path(root).resolve()/'scripts/si_qe_reference_evidence.py','Loaded another public parser')
    require(arithmetic.HARTREE_EV==HARTREE_EV,'Presentation unit convention changed')
    return native,arithmetic


def load_history(root):
    """Authenticate every K6 native/payload file, then reparse both actual slots."""
    native,arithmetic=frozen_modules(root)
    manifest=json.loads(fixed(root,Q_MANIFEST,Q_HASH))
    require(manifest['execution_commit']==QE_EXECUTION,'Wrong historical QE execution')
    parent=parent_metadata=None;slots={}
    for action in ('Q-SCF','Q-GAMMA'):
        entry=manifest['profiles']['K6'][action]
        require(entry['execution_status']=='PASS' and entry['exit_code']==entry['process_exit_code']==0 and
                entry['execution_commit']==QE_EXECUTION,'Failed/mixed historical QE slot')
        streams={k:native.unpacked(root,v['path'],v) for k,v in entry['native_files'].items()}
        payload={k:json.loads(native.unpacked(root,v['path'],v)) for k,v in entry['payloads'].items()}
        metadata=payload['metadata']
        require(metadata['native_files']==entry['native_files'] and metadata['execution_commit']==QE_EXECUTION,'Historical native source index mismatch')
        for category in ('source_sha256','prepared_sha256','frozen_sha256'):
            require(type(metadata.get(category)) is dict and metadata[category],'Missing historical source closure')
            for relative,expected in metadata[category].items():
                raw=git(root,'show',QE_EXECUTION+':'+relative) if category=='source_sha256' else path(root,relative).read_bytes()
                require(digest(raw)==expected,'Historical execution source mismatch: '+relative)
        parsed=native.parse_public_native(root,'K6',streams,metadata,parent,parent_metadata)
        native.close(parsed,payload['endpoint'],'extra/K6/'+action)
        native.close(native.iteration_rows(streams['qe.stdout'].decode(),parsed),payload['iterations'],'extra/K6/iterations')
        slots[action]=parsed
        if action=='Q-SCF': parent,parent_metadata=parsed,metadata
    k4=json.loads(fixed(root,K4_PATH,K4_HASH))
    require(k4['execution_commit']=='48da17f47e998030a50c954c3abc38bca3a9df8f','Wrong historical K4 execution')
    require(k4['case_sha256']=='7874f0007f8df69763b7a7032d580bb05a6b39bdcba412c72cc155a8b2e039ce','Wrong K4 case')
    b0={Path(k).parent.name:json.loads(fixed(root,k,h)) for k,h in B0_SOURCES.items()}
    require(all(w['execution_status']=='PASS' and w['execution_commit']=='281c53525a70cf21c36973956d5303d3201a73eb' for w in b0.values()),'Historical B0 completion identity changed')
    return dict(Q_K6_SCF=slots['Q-SCF'],Q_K6_GAMMA=slots['Q-GAMMA'],K4=k4,B0=b0,
        sources={Q_MANIFEST:Q_HASH,K4_PATH:K4_HASH,**B0_SOURCES},native_slots_reparsed=2,
        source_status='HISTORICAL_REUSED',arithmetic=arithmetic)


def stats(values):
    v=[number(x) for x in values];require(v,'Missing numerical vector')
    return dict(max_abs=max(map(abs,v)),rms=math.sqrt(math.fsum(x*x for x in v)/len(v)))


def fd(values,mu,tau=.001):
    require(tau==.001,'Extra temperature changed')
    result=[]
    for e in values:
        x=(number(e)-number(mu))/tau
        q=math.exp(-abs(x))
        result.append(q/(1+q) if x>=0 else 1/(1+q))
    return result


def gamma_metrics(point,mu,arithmetic):
    values=point['eigenvalues_ha']
    g=arithmetic.analyze_gamma(values)
    expected=fd(values,mu)
    if 'occupations' in point:
        occ=point['occupations'];require(type(occ) is list and len(occ)==24,'Missing Gamma occupations')
        require(max(abs(number(x)-y) for x,y in zip(occ,expected))<=1e-12,'Gamma occupations differ from parent-mu diagnostic')
    minimum=min(expected[2:8])
    paired=max(abs(values[i]-values[i+1]) for i in range(0,24,2))
    structure=(g['manifold_assignment_status']=='PASS' and g['multiplet_structure_status']=='PASS' and
               g['resolvable_soc_status']=='PASS' and paired<=1e-7)
    # The historical analyzer's assignment field describes a fixed window.
    # Do not propagate it as an irrep/complete physical manifold claim.
    g.pop('manifold_assignment_status')
    g.update(fixed_window_structure_status='PASS' if structure else 'REVIEW_REQUIRED',
        gamma_pair_max_ha=paired,occupation=dict(values=expected,minimum_3_to_8=minimum,
            maximum_hole_3_to_8=1-minimum,threshold=SATURATION,mu_ha=mu,tau_ha=.001,
            status='PASS' if minimum>=SATURATION else 'REVIEW_REQUIRED'),
        manifold_assignment_status='MANIFOLD_ASSIGNMENT_REVIEW_REQUIRED',
        physical_interpretation='REVIEW_REQUIRED',physical_convergence='NOT_ESTABLISHED')
    return g


def validate_slots(data):
    require(type(data) is dict and type(data.get('schema_version')) is int and data.get('schema_version')==1 and data.get('experiment')=='soc-extra-v1','Wrong extra public schema')
    require(data.get('original_9A_status')=='COMPLETED_UNCHANGED' and type(data.get('core_changed')) is bool,'Original completion/core identity unclear')
    require(type(data.get('b0_regression_required')) is bool,'Required B0 gate must be explicit')
    require(not data['core_changed'] or data['b0_regression_required'],'Changed numerical core omitted required B0')
    exact_hash(data.get('execution_commit'),40)
    require(type(data.get('slots')) is dict and set(data['slots'])==set(SLOTS),'Every authorized slot must be explicitly represented')
    finite_public(data)
    for action,row in data['slots'].items():
        require(type(row) is dict and type(row.get('status')) is str,'Invalid slot status')
        status=row['status'];worker=row.get('worker')
        if status.startswith('NOT_RUN') or status=='BLOCKED_PARENT':
            require(row.get('native_exit_code') is None and worker is None and bool(row.get('reason')),'Unrun/blocked slot has native result or lacks reason')
            require(row.get('recorder_exit_code') is None or type(row['recorder_exit_code']) is int and row['recorder_exit_code']!=0,'Unrun slot claims recorder success')
            continue
        require(status in ('PASS','PILOT_COMPLETED_NOT_SCF_CONVERGED','FAIL','RESOURCE_BLOCKED','RESOURCE_LIMIT'),'Unknown slot status')
        if status in ('FAIL','RESOURCE_BLOCKED','RESOURCE_LIMIT'):
            require(bool(row.get('reason')) and type(row.get('recorder_exit_code')) is int and row['recorder_exit_code']!=0,'Failed slot lost reason/nonzero exit')
            require(row.get('native_exit_code') is None or type(row['native_exit_code']) is int,'Invalid failed native exit')
            if worker is not None:
                require(type(worker) is dict and worker.get('action')==action and
                        worker.get('execution_commit')==data['execution_commit'] and
                        worker.get('run_id') in (row.get('run_id'),str(row.get('run_id'))+'-dftk'),'Failed slot carries another run worker')
                # A native worker can finish before a later resource/recorder failure.
                # Preserve its bytes but never use this unaccepted slot numerically.
            continue
        expected='PILOT_COMPLETED_NOT_SCF_CONVERGED' if action=='X-K6-PILOT' else 'PASS'
        require(status==expected and type(row.get('native_exit_code')) is int and row['native_exit_code']==0 and
                type(row.get('recorder_exit_code')) is int and row['recorder_exit_code']==0,'Successful status/process contradiction')
        require(type(worker) is dict and worker.get('action')==action and worker.get('execution_status')==expected and
                worker.get('phase')=='9A-extra' and worker.get('backend')=='soc-core' and
                worker.get('execution_commit')==data['execution_commit'],'Worker source/action/status mismatch')
        require(type(row.get('run_id')) is str and worker.get('run_id') in (row['run_id'],row['run_id']+'-dftk'),'Wrong worker/run binding')
        require(type(worker.get('exit_code')) is int and worker['exit_code']==0 and worker.get('schema_version')==1,'Successful worker exit/schema contradiction')
        resource=row.get('resource')
        require(type(resource) is dict and resource.get('status')=='PASS' and resource.get('native_exit_code')==0 and
                resource.get('owned_process_cleanup_status')=='PASS' and
                0<integer(resource.get('peak_aggregate_rss_bytes'))<8*1024**3 and
                integer(resource.get('nonempty_samples'),1)>0,'Missing/failed resource monitor')
        require(worker.get('parallelism')==dict(julia=1,blas=1,fft=1,mpi=1),'Worker thread count changed')
        require(worker.get('environment',{}).get('status')=='PASS' and worker.get('runtime_dispatch_status')=='PASS' and
                worker.get('runtime_closed') is True,'Worker environment/dispatch/cleanup not passed')
        runtime=worker.get('runtime',{});closed=worker.get('runtime_after_close',{})
        require(runtime.get('backend')=='soc-core' and runtime.get('max_rhs')==30 and
                all(integer(runtime.get('counters',{}).get(k),1)>0 for k in ('fr_mul_calls','component_mul_calls','full_mul_calls')) and
                closed.get('closed') is True and closed.get('owned_source_entries')==0 and
                closed.get('workspace_released') is True,'Owned numerical dispatch/storage release missing')
        require(worker.get('input',{}).get('sha256')==UPF and worker.get('input',{}).get('nlcc_present') is True,'Wrong Si/NLCC input')
        if action.endswith('-SCF'):
            exact_hash(worker.get('checkpoint_sha256'))
            exact_hash(worker.get('final',{}).get('n_out_sha256'))
        if action.endswith('-GAMMA'):
            spectrum=worker.get('spectrum',{})
            require(spectrum.get('execution_status')=='PASS' and spectrum.get('process_exit_code')==0 and
                    worker.get('time_reversal',{}).get('status')=='PASS','Gamma native/time reversal check missing')
        if action=='X-K6-PILOT':
            require(worker.get('final') is None and 1<=integer(worker.get('pilot',{}).get('completed_maps'),1)<=2,'Pilot substituted for SCF or exceeded map limit')
    for gamma in ('X-B0-GAMMA','X-K6-GAMMA','L-B0-GAMMA'):
        row=data['slots'][gamma]
        if row['status']=='PASS':
            parent=data['slots'][gamma.replace('GAMMA','SCF')]
            require(parent['status']=='PASS','Gamma without successful own parent')
            g,s=row['worker'],parent['worker']
            require(g.get('source_scf_run_id')==s.get('run_id') and
                    g.get('parent_checkpoint_sha256')==s.get('checkpoint_sha256') and
                    g.get('density_source_sha256')==s.get('final',{}).get('n_out_sha256'),'Gamma parent/checkpoint/n_out mismatch')
    return data['slots']


def d_scf_quantities(worker,case):
    f=worker.get('final');require(type(f) is dict and f.get('closure_status')=='PASS','Missing accepted final closure')
    require(1<integer(f.get('map_count'),1)<=400,'Invalid SCF map count')
    eigen,occ=f['eigenvalues_ha'],f['occupations'];nk=len(case['kpoints'])
    require(type(eigen) is list and type(occ) is list and len(eigen)==len(occ)==nk,'SCF k count changed')
    grid=worker['grid']['rows'];require(len(grid)==nk,'Missing all actual k geometry')
    actual=worker['grid']['basis'];ap=actual['kpoints']
    require(len(ap)==nk and actual['n_electrons']==8 and actual['fft_grid']==[48,48,48] and actual['ecut_ha']==30,'Actual geometry/electron/cutoff changed')
    count=entropy=fd_error=0.;mu=number(f['mu_ha'])
    for i,p in enumerate(case['kpoints']):
        require(grid[i]['coordinate_fractional']==ap[i]['coordinate_fractional']==p['coordinate_fractional'] and ap[i]['weight_spatial']==p['weight_spatial'],'SCF actual coordinate/weight differs from request')
        require(type(eigen[i]) is list and len(eigen[i])==len(occ[i])==24,'SCF physical band count changed')
        values=[number(v) for v in eigen[i]];expected=fd(values,mu)
        fs=[number(x) for x in occ[i]];require(all(0<=x<=1 for x in fs),'SCF occupation capacity changed')
        w=number(p['weight_spatial']);count+=w*math.fsum(fs)
        entropy-=w*math.fsum(x*math.log(x)+(1-x)*math.log1p(-x) for x in fs if 0<x<1)
        fd_error=max(fd_error,max(abs(x-y) for x,y in zip(fs,expected)))
    require(abs(count-8)<=1e-8 and fd_error<=1e-11,'SCF electron/FD mismatch')
    diag=f['diagnostics'];terms=diag['energy_terms_ha']
    require(set(terms)==ENERGY_NAMES,'Missing raw seven-term energy account')
    E=number(diag['internal_energy_ha']);F=number(diag['free_energy_ha']);ts=number(diag['entropy_energy_ha'])
    require(abs(math.fsum(number(x) for x in terms.values())-E)<=1e-8,'Raw seven terms do not sum toE')
    require(abs(F-E-ts)<=1e-12 and abs(ts+.001*entropy)<=1e-11,'SCF free-energy/entropy arithmetic mismatch')
    require(number(f['unmixed_residual_l2'])<=case['settings']['thresholds']['density_fixedpoint_l2'],'SCF fixedpoint gate violated')
    return dict(internal_ha=E,free_ha=F,minus_TS_ha=ts,entropy_dimensionless=entropy,
                terms_ha=terms,electron_sum=count,FD_max_abs=fd_error,mu_ha=mu,
                map_count=f['map_count'],diagnostics=diag,native_total_energy_corrected=False)



def gamma_check(worker,energy,case,arithmetic):
    spectrum=worker['spectrum'];points=spectrum['kpoints']
    require(len(points)==1 and points[0]['coordinate_fractional']==[0.,0.,0.] and points[0]['weight_spatial']==1,'Only own-density Gamma permitted')
    require(spectrum['physical_operator']=='full_soc' and spectrum['occupations_use']=='DIAGNOSTIC_ONLY_NOT_DENSITY_FEEDBACK' and
            spectrum['fermi_energy_ha']==energy['mu_ha'] and spectrum['temperature_ha']==.001,'Gamma physical/occupation role differs')
    result=gamma_metrics(points[0],energy['mu_ha'],arithmetic)
    residual=points[0]['residuals_ha'];require(type(residual) is list and len(residual)==24,'Missing Gamma explicit residuals')
    require(all(number(x)>=0 for x in residual),'Negative residual norm')
    residual_max=max(residual);gram=number(points[0]['gram_frobenius'])
    require(0<=gram<=case['settings']['thresholds']['gram_norm'] and
            residual_max<=case['settings']['thresholds']['residual_ha'],'Gamma explicit residual/Gram gate violated')
    result.update(explicit_residual_max_ha=residual_max,gram_frobenius=gram)
    return result


def b0_comparison(scf,gamma,energy,history,reported):
    old=history['B0']['OPT-B0-SCF'];oldg=history['B0']['OPT-B0-GAMMA']['spectrum']['kpoints'][0]['eigenvalues_ha']
    diag=old['final']['diagnostics'];new=gamma['values_ha'];require(len(oldg)==len(new)==24,'B0 raw spectrum size changed')
    rows={name:dict(difference_ha=energy[key]-diag[field],limit_ha=1e-8,
        status='PASS' if abs(energy[key]-diag[field])<=1e-8 else 'FAIL') for name,key,field in
        [('E','internal_ha','internal_energy_ha'),('F','free_ha','free_energy_ha')]}
    gap=gamma['delta_so_ev']-history['arithmetic'].analyze_gamma(oldg)['delta_so_ev'];raw=[a-b for a,b in zip(new,oldg)]
    rows['Gamma']=dict(raw_differences_ha=raw,max_abs_ha=max(map(abs,raw)),limit_ha=1e-7,
        status='PASS' if max(map(abs,raw))<=1e-7 else 'FAIL')
    rows['splitting']=dict(difference_ev=gap,limit_ev=1e-6,status='PASS' if abs(gap)<=1e-6 else 'FAIL')
    density=dict(status='NOT_ASSESSED',reason='Private n_out array comparison unavailable')
    if reported is not None:
        require(type(reported) is dict and reported.get('execution_commit')==scf['execution_commit'],'Wrong B0 comparison execution')
        density=reported['metrics']['n_out'];require(density.get('evidence_level')=='RUNNER_REPORTED_PRIVATE_ARRAY_COMPARISON','Private density evidence level missing')
        require(density['reference_source_sha256']==old['checkpoint_sha256'] and
                density['reference_n_out_sha256']==old['final']['n_out_sha256'] and
                density['candidate_n_out_sha256']==scf['final']['n_out_sha256'],'Private B0 density source mismatch')
        a,b,d=(number(density[k]) for k in ('reference_norm','candidate_norm','absolute_L2'))
        require(min(a,b,d)>=0 and density['limit']==1e-8,'Private density norm/limit invalid')
        relative=d/max(a,b,1)
        require(math.isclose(number(density['relative']),relative,rel_tol=1e-13,abs_tol=1e-30),'Private density ratio arithmetic differs')
        require(density['status']==('PASS' if relative<=1e-8 else 'FAIL'),'Private density status inconsistent')
    ok=all(row['status']=='PASS' for row in rows.values()) and density['status']=='PASS' and reported.get('status')=='PASS' if reported is not None else False
    return dict(status='PASS' if ok else 'NOT_ASSESSED' if density['status']=='NOT_ASSESSED' else 'FAIL',
        reference_status='HISTORICAL_REUSED',reference_execution_commit=old['execution_commit'],
        arithmetic=rows,n_out=density,scope='Public E/F/24-state Gamma arithmetic; private density comparison remains runner-reported')


def evaluate(data,root):
    slots=validate_slots(data);history=load_history(root);arithmetic=history['arithmetic']
    qscf,qgamma=history['Q_K6_SCF'],history['Q_K6_GAMMA'];k4=history['K4']
    q=gamma_metrics(qgamma['kpoints'][0],qscf['fermi_energy_ha'],arithmetic)
    d4=gamma_metrics(k4['D-GAMMA']['kpoints'][0],k4['D-SCF']['fermi_energy_ha'],arithmetic)
    q4=gamma_metrics(k4['Q-GAMMA']['kpoints'][0],k4['Q-SCF']['fermi_energy_ha'],arithmetic)
    result=dict(schema_version=1,experiment='soc-extra-v1',original_9A_status='COMPLETED_UNCHANGED',
        execution_commit=data['execution_commit'],slot_status={k:v['status'] for k,v in slots.items()},
        historical_source_status='HISTORICAL_REUSED',historical_sources=history['sources'],
        historical_native_slots_reparsed=history['native_slots_reparsed'],
        K4=dict(D=d4,Q=q4),K6=dict(D=None,Q=q,comparison_status='NOT_ASSESSED',comparison=None),
        B0=dict(status='NOT_RUN',comparison=None),Linux_B0=dict(status='NOT_RUN',comparison=None),
        QE_native_energy=qscf['energy'],QE_warnings=dict(SCF=qscf['warning_evidence'],Gamma=qgamma['warning_evidence']),
        limitations=dict(physical_convergence='NOT_ESTABLISHED',manifold_assignment='MANIFOLD_ASSIGNMENT_REVIEW_REQUIRED',
            IEEE_localization='NOT_LOCALIZED',QE_native_nonlocal_independent='NOT_MEASURED',
            extra_QE_execution='NOT_RUN',K8='NOT_RUN',upstream_native_integration='NOT_ESTABLISHED'),
        scope='Public spectrum/occupation/energy arithmetic; private arrays, loaded environment and resource measurements remain runner-reported')
    for prefix,label,report_key in (('X','B0','b0_regression'),('L','Linux_B0','linux_b0_regression')):
        if slots[prefix+'-B0-SCF']['status']=='PASS':
            bs=slots[prefix+'-B0-SCF']['worker'];bc=read(path(root,'benchmarks/soc-extra-v1/B0.json'))
            require(bs['case_sha256']==digest(path(root,'benchmarks/soc-extra-v1/B0.json').read_bytes()),'B0 case identity mismatch')
            energy=d_scf_quantities(bs,bc);result[label]=dict(status='SCF_ONLY',energy=energy,comparison=None)
            if slots[prefix+'-B0-GAMMA']['status']=='PASS':
                bg=gamma_check(slots[prefix+'-B0-GAMMA']['worker'],energy,bc,arithmetic)
                compared=b0_comparison(bs,bg,energy,history,data.get(report_key))
                result[label].update(status=compared['status'],Gamma=bg,comparison=compared)
    if data['b0_regression_required'] and any(slots[k]['status'] in ('PASS','PILOT_COMPLETED_NOT_SCF_CONVERGED') for k in ('X-K6-PILOT','X-K6-SCF','X-K6-GAMMA')):
        require(result['B0']['status']=='PASS','K6 ran without mandatory new B0 regression')
    if slots['X-K6-SCF']['status']=='PASS':
        kcase=read(path(root,'benchmarks/soc-extra-v1/K6.json'));ks=slots['X-K6-SCF']['worker']
        require(ks['case_sha256']==digest(path(root,'benchmarks/soc-extra-v1/K6.json').read_bytes()),'K6 case identity mismatch')
        result['K6']['D_energy']=d_scf_quantities(ks,kcase)
    if slots['X-K6-SCF']['status']!='PASS' or slots['X-K6-GAMMA']['status']!='PASS':
        return result
    sw,gw=slots['X-K6-SCF']['worker'],slots['X-K6-GAMMA']['worker']
    case=read(path(root,'benchmarks/soc-extra-v1/K6.json'))
    require(sw.get('case_sha256')==digest(path(root,'benchmarks/soc-extra-v1/K6.json').read_bytes()),'K6 case identity mismatch')
    energy=d_scf_quantities(sw,case)
    d=gamma_check(gw,energy,case,arithmetic)
    residual_max=d['explicit_residual_max_ha'];gram=d['gram_frobenius']
    vd,vq=d['values_ha'],q['values_ha'];raw=[x-y for x,y in zip(vd,vq)]
    shifted=[(x-vd[7])-(y-vq[7]) for x,y in zip(vd,vq)]
    delta=d['delta_so_ev']-q['delta_so_ev'];dr=d['delta_so_ev']-d4['delta_so_ev'];qr=q['delta_so_ev']-q4['delta_so_ev']
    comparison=dict(delta_D_minus_Q_ev=delta,delta_D_minus_Q_mev=1000*delta,
        D_K4_to_K6_ev=dr,Q_K4_to_K6_ev=qr,response_difference_ev=dr-qr,
        D_minus_Q_screen='PASS' if abs(delta)<=WINDOW_EV else 'REVIEW_REQUIRED',
        response_screen='PASS' if abs(dr-qr)<=WINDOW_EV else 'REVIEW_REQUIRED',screen_window_ev=WINDOW_EV,
        historical_K4_current_K6_scope='HISTORICAL_K4_LEGACY_TO_CURRENT_SOC_CORE_MIXED_VERSION_RESPONSE',
        implementation_scope='Historical K4 used legacy integration; current K6 uses the completed owned core plus declared extra adaptation. Static equivalence and B0 support do not replace a new-core K4 SCF.',
        raw_D_minus_Q_ha=raw,global_referenced_D_minus_Q_ha=shifted,
        raw_summary_ha=stats(raw),global_referenced_summary_ha=stats(shifted),
        reference=dict(rule='One Gamma state8 reference per program, for all24 states',D_ha=vd[7],Q_ha=vq[7]),
        D_explicit_residual_max_ha=residual_max,D_gram_frobenius=gram,
        QE_explicit_residuals='NOT_AVAILABLE',raw_internal_D_minus_Q_ha=energy['internal_ha']-qscf['energy']['internal_ha'],
        raw_free_D_minus_Q_ha=energy['free_ha']-qscf['energy']['free_ha'],
        total_energy_zero_difference_gate='NOT_DECLARED')
    result['K6']=dict(D=d,Q=q,D_energy=energy,comparison=comparison,
        comparison_status='PASS' if comparison['D_minus_Q_screen']==comparison['response_screen']=='PASS' else 'REVIEW_REQUIRED')
    return result



def equivalence_statistics(document):
    require(type(document) is dict and type(document.get('cases')) is dict,'Missing candidate equivalence record')
    cases=document['cases']
    if document.get('status')=='NOT_ATTEMPTED':
        require(not cases,'Unattempted candidate has numerical comparisons')
        return dict(status='NOT_ATTEMPTED',cases={})
    require(set(cases)<=set(('B0','K4')) and cases,'Invalid equivalence cases')
    results={};all_pass=set(cases)=={'B0','K4'}
    for label,case in cases.items():
        rows=case['rows'];require(type(rows) is list and rows,'No equivalence quantities')
        computed=[];labels=set()
        for row in rows:
            require(type(row.get('label')) is str and row['label'] not in labels,'Duplicate/missing equivalence label')
            labels.add(row['label'])
            if row['kind']=='array':
                require(type(row.get('shape')) is list and all(type(n) is int and n>0 for n in row['shape']),'Missing compared array shape')
                a,b,d=(number(row[k]) for k in ('reference_norm','candidate_norm','absolute_L2'))
                require(min(a,b,d)>=0 and row['limit']==1e-12,'Array norm/limit changed')
                value=d/max(a,b,1);limit=1e-12
                require(math.isclose(number(row['relative']),value,rel_tol=1e-13,abs_tol=1e-30),'Incorrect norm ratio')
            elif row['kind']=='scalar':
                value=number(row['candidate'])-number(row['reference'])
                limit=0 if row['label'].endswith('entropy_dimensionless') else 1e-10
                require(row['limit']==limit and math.isclose(number(row['difference']),value,rel_tol=1e-13,abs_tol=1e-30),'Scalar difference/limit changed')
            else: raise ValueError('Unknown equivalence quantity')
            status='PASS' if abs(value)<=limit else 'FAIL'
            require(row['status']==status,'Equivalence status contradicts arithmetic')
            computed.append(dict(label=row['label'],value=value,limit=limit,status=status))
        ok=all(r['status']=='PASS' for r in computed);all_pass=all_pass and ok
        results[label]=dict(status='PASS' if ok else 'FAIL',rows=computed)
    status='PASS' if all_pass else 'FAIL'
    require(document['status']==status,'Joint equivalence status contradicts rows')
    return dict(status=status,cases=results)


def performance_statistics(document):
    require(type(document) is dict and document.get('schema_version')==1 and type(document.get('records')) is list,'Invalid performance schema')
    computed={};original={}
    for record in document['records']:
        label,mode=record['case'],record['mode'];require(label in ('B0','K4') and mode in ('baseline','candidate'),'Unknown performance case/mode')
        key=mode+'/'+label;require(key not in computed,'Duplicate performance case/mode')
        exact_hash(record['execution_commit'],40);original[key]=record;measurements=record['measurements']
        require(record.get('base_commit')==BASE and type(record.get('input')) is dict and
                record.get('environment',{}).get('status')=='PASS' and
                record.get('parallelism')==dict(julia=1,blas=1,fft=1,mpi=1),'Performance input/environment/threads missing')
        exact_hash(record.get('raw_worker_sha256'))
        require(set(measurements)<=set(OPS),'Unplanned performance operation')
        ops={}
        for name,m in measurements.items():
            require(m.get('warmup_count')==1 and m.get('requested_samples')==5,'Changed warmup/sample contract')
            samples=m['samples'];require(type(samples) is list and len(samples)<=5,'Repeated/extra performance samples')
            require([s['index'] for s in samples]==list(range(1,len(samples)+1)),'Missing/reordered samples')
            good=[s for s in samples if s['status']=='PASS']
            if m.get('status')=='PASS':
                require(len(good)==5 and m.get('completed_samples')==5 and
                        type(m.get('warmup')) is dict and m['warmup'].get('status')=='PASS' and
                        m['warmup'].get('index')==0,'Partial performance result claims PASS')
            else: require(m.get('status') in ('FAIL','NOT_RUN','INCOMPLETE'),'Unknown performance operation state')
            fields=('time_seconds','allocated_bytes','gc_seconds','compile_seconds','recompile_seconds')
            values={f:[number(s[f]) for s in good] for f in fields}
            require(all(x>=0 for v in values.values() for x in v),'Negative performance metric')
            ops[name]=dict(status=m['status'],completed_samples=len(good),statistics={f:dict(median=statistics.median(v),min=min(v),max=max(v)) for f,v in values.items()} if good else {})
        computed[key]=ops
    ratios={};eligible=True
    for label in ('B0','K4'):
        if 'candidate/'+label not in computed or 'baseline/'+label not in computed:
            eligible=False;continue
        rb,rc=original['baseline/'+label],original['candidate/'+label]
        require(rb['input']==rc['input'],'Candidate input differs from its matched baseline')
        require(all(rb['environment'].get(k)==rc['environment'].get(k) and rb['environment'].get(k) for k in
                ('julia_version','manifest_sha256')),'Candidate loaded environment differs')
        for k in ('canonical_inputs','canonical_operators'):
            require(exact_hash(rb[k]['sha256'])==exact_hash(rc[k]['sha256']),'Candidate physical canonical data differ')
        before,after=computed['baseline/'+label],computed['candidate/'+label]
        require(set(before)==set(after)==set(OPS),'Joint candidate screen requires all four operations')
        ratios[label]={}
        for name in OPS:
            require(rb['measurements'][name].get('workload')==rc['measurements'][name].get('workload') and
                    rb['measurements'][name].get('workload'),'Candidate changed workload')
            if before[name]['status']!='PASS' or after[name]['status']!='PASS':eligible=False;continue
            a,b=before[name]['statistics'],after[name]['statistics']
            require(a['time_seconds']['median']>0 and a['allocated_bytes']['median']>0,'Undefined performance ratio')
            ratios[label][name]=dict(time_ratio=b['time_seconds']['median']/a['time_seconds']['median'],
                                    allocation_ratio=b['allocated_bytes']['median']/a['allocated_bytes']['median'])
        p=ratios[label].get('pipeline_with_validation')
        eligible=eligible and p is not None and p['time_ratio']<=.9 and p['allocation_ratio']<=1.1
    selection=document.get('selection',{});require(selection.get('adopted_core') in ('baseline','candidate'),'Final core selection required')
    equivalence=equivalence_statistics(document.get('equivalence',{}))
    if selection['adopted_core']=='candidate':
        require(eligible and equivalence['status']=='PASS','Candidate adopted without matched performance/equivalence')
    return dict(records=computed,ratios=ratios,performance_screen='ELIGIBLE_FOR_REVIEW' if eligible else 'RETAIN_BASELINE',
        adopted_core=selection['adopted_core'],equivalence=equivalence,equivalence_evidence_level='RUNNER_REPORTED_PRIVATE_ARRAY_COMPARISON',
        scope='All successful warmed samples, medians and ranges; profiler samples excluded; not statistical significance or SCF speedup')



def audit_artifacts(root,entries,slots):
    require(type(entries) is list,'Native log/trace manifest missing')
    seen={};paths=set()
    for entry in entries:
        raw=artifact(root,entry)
        require(entry['path'] not in paths,'Duplicate public artifact')
        paths.add(entry['path']);action=entry.get('action');kind=entry.get('kind')
        require(action in SLOTS and kind in ('native_stdout','native_stderr','compact_trace','lifecycle','resource_policy'),'Unrecognized slot artifact role')
        key=(action,kind);require(key not in seen,'Duplicate slot artifact role');seen[key]=raw
    for action,row in slots.items():
        if row['native_exit_code'] is not None:
            for kind in ('native_stdout','native_stderr'):
                require((action,kind) in seen,'Missing complete native stream: '+action+'/'+kind)
        accepted=row['status'] in ('PASS','PILOT_COMPLETED_NOT_SCF_CONVERGED')
        if accepted and (action.endswith('-SCF') or action=='X-K6-PILOT'):
            require((action,'compact_trace') in seen,'Missing all-map scientific trace: '+action)
            trace=[json.loads(line) for line in seen[action,'compact_trace'].decode().splitlines() if line.strip()]
            n=row['worker']['pilot']['completed_maps'] if action=='X-K6-PILOT' else row['worker']['final']['map_count']
            require([r.get('map_index') for r in trace]==list(range(1,n+1)),'Missing/duplicate/reordered completed scientific map')
            finite_public(trace)
            if action.endswith('-SCF'):
                require(trace[-1].get('map_role')=='closure' and trace[-1].get('status')=='PASS','Final trace lacks accepted closure')
            for record in trace:
                diag=record.get('diagnostics');require(type(diag) is dict,'Compact map omitted diagnostics')
                terms=diag.get('energy_terms_ha');require(type(terms) is dict and set(terms)==ENERGY_NAMES,'Compact map omitted seven energies')
                E,F,ts=(number(diag[k]) for k in ('internal_energy_ha','free_energy_ha','entropy_energy_ha'))
                require(abs(math.fsum(number(x) for x in terms.values())-E)<=1e-8 and abs(F-E-ts)<=1e-11,'Compact map energy arithmetic differs')
    return dict(artifacts_checked=len(entries),complete_accepted_map_traces=sum(k[1]=='compact_trace' and slots[k[0]]['status'] in ('PASS','PILOT_COMPLETED_NOT_SCF_CONVERGED') for k in seen))


def replay(root,manifest_path='results/soc-extra/evidence.json'):
    root=Path(root).resolve();manifest=read(path(root,manifest_path))
    require(manifest.get('schema_version')==1 and manifest.get('experiment')=='soc-extra-v1','Wrong evidence manifest')
    data=json.loads(artifact(root,manifest['data']));performance=json.loads(artifact(root,manifest['performance']))
    execution=exact_hash(data['execution_commit'],40)
    require(manifest['execution_commit']==execution,'Evidence/data execution mismatch')
    require(git(root,'merge-base','--is-ancestor',BASE,execution)==b'','Execution is outside accepted history')
    for row in data['slots'].values():
        worker=row.get('worker')
        if worker and row['status'] in ('PASS','PILOT_COMPLETED_NOT_SCF_CONVERGED'):
            sources=worker.get('executed_source_sha256');require(type(sources) is dict and sources,'Missing executed source identity')
            for relative,expected in sources.items():
                require(digest(git(root,'show',execution+':'+relative))==exact_hash(expected),'Executed source does not matchGit: '+relative)
    validate_slots(data)
    artifacts=audit_artifacts(root,manifest.get('artifacts'),data['slots'])
    result=evaluate(data,root);result['performance']=performance_statistics(performance)
    result['artifact_audit']=artifacts
    result.update(replay_status='PASS',recorded_execution_commit=execution,
                  scope=result['scope']+'; all declared compact/native artifact hashes checked')
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2])
    p.add_argument('--manifest',default='results/soc-extra/evidence.json');p.add_argument('--require-k6',action='store_true')
    a=p.parse_args(argv)
    try:
        result=replay(a.root,a.manifest)
        code=1 if a.require_k6 and result['K6']['comparison_status']!='PASS' else 0
        result['exit_code']=code;print(json.dumps(result,allow_nan=False,separators=(',',':')));return code
    except (Exception,KeyboardInterrupt) as error:
        print(json.dumps(dict(replay_status='FAIL',exit_code=2,reason=str(error)),allow_nan=False),file=sys.stderr);return 2


if __name__=='__main__':sys.exit(main())
