#!/usr/bin/env python3
"""One case, original orbitals only. No electronic solver or potential evaluation."""
from __future__ import annotations
import argparse, datetime, decimal, hashlib, json, math, os, pathlib, subprocess, sys, uuid
import xml.etree.ElementTree as ET
import numpy as np
from parse_qe_wavefunction import parse_wfc
from audit_orbital_kinetics import evaluate_orbitals
from compare_density_hartree import read_coefficients_gzip
from orbital_evidence import (load_state_metadata, write_state_metadata, save_package,
                              read_primitive, recorded_run)
ROOT=pathlib.Path(__file__).resolve().parents[1]
PLAN='benchmarks/mg-soc-wavefunction-energy-v1/plan.json'
PUBLIC='results/mg-soc-wavefunction-energy'
EXECUTION_FILES=['scripts/run_orbital_energy_audit.py','scripts/parse_qe_wavefunction.py',
 'scripts/audit_orbital_kinetics.py','scripts/orbital_evidence.py',
 'scripts/extract_orbital_nonlocal.jl','scripts/compare_orbital_energy.py']
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(pathlib.Path(p).read_text())
def write(p,x):pathlib.Path(p).write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def checked(p,digest):
    p=pathlib.Path(p)
    if not p.is_file():raise FileNotFoundError('Required bound original source missing: '+str(p))
    if sha(p)!=digest:raise ValueError('Required source SHA256 differs: '+str(p))
    return p

def validate_sources(root,plan):
    for name,digest in plan['source_sha256'].items():checked(root/name,digest)
    for row in plan['original_binding']['files']:
        p=checked(root/row['current'],row['sha256'])
        if p.stat().st_size!=row['bytes']:raise ValueError('Original byte count differs')
    source=plan['sources']['G40']; receipt=read(root/'.work/phase7b'/source['run_id']/'result.json')
    if any(receipt[k]!=v for k,v in dict(slot='G40',run_id=source['run_id'],execution_status='PASS',exit_code=0,process_exit_code=0).items()):
        raise ValueError('Not the bound original G40 SCF')
    return True

def halfwidth(token):return float(decimal.Decimal(5).scaleb(decimal.Decimal(token).as_tuple().exponent-1))
def original_xml(root,plan,xml_path=None):
    s=plan['sources']['G40'];row=s['files']['scratch/mg_soc_qe_v1.save/data-file-schema.xml']
    p=checked(xml_path if xml_path is not None else root/'.work/phase7b'/row['path'],row['sha256']);tree=ET.parse(p)
    output=tree.getroot().find('output');bs=output.find('band_structure')
    def req(name,value):
        if bs.findtext(name).strip()!=value:raise ValueError('Original XML '+name+' differs')
    req('nbnd','24');req('nks','3');req('nelec','1.000000000000000E+001')
    a=np.array(plan['physical']['lattice_vectors_bohr'],dtype=np.float64).T
    b=2*math.pi*np.linalg.inv(a).T
    alat=float(output.find('atomic_structure').attrib['alat']);points=[];tokens=[]
    for ik,entry in enumerate(bs.findall('ks_energies')):
        node=entry.find('k_point');kt=node.text.split();wt=node.attrib['weight'];ft=entry.findtext('occupations').split();et=entry.findtext('eigenvalues').split()
        kcart=np.array(list(map(float,kt)),dtype=np.float64)*(2*math.pi/alat)
        f=np.array(list(map(float,ft)),dtype=np.float64);e=np.array(list(map(float,et)),dtype=np.float64)
        if f.shape!=(24,) or e.shape!=(24,) or not np.isfinite(f).all() or not np.isfinite(e).all() or np.any((f<0)|(f>1)):raise ValueError('Original XML invalid bands/occupations')
        if float(wt)!=plan['physical']['kweights'][ik] or np.max(abs(kcart-b@plan['physical']['kpoints'][ik]))>1e-12:raise ValueError('Original XML k/weight differs')
        points.append(dict(k_cart=kcart,weight=float(wt),occupations=f,eigenvalues=e,npw=int(entry.findtext('npw'))))
        tokens.append(dict(k=kt,weight=wt,occupations=ft,eigenvalues_ha=et))
    if len(points)!=3:raise ValueError('Original XML must contain exactly three ks_energies records')
    eband_token=output.findtext('total_energy/eband').strip()
    # Sum product print intervals conservatively, without treating them as independent noise.
    D=decimal.Decimal
    def u(token):return D(5).scaleb(D(token).as_tuple().exponent-1)
    with decimal.localcontext() as ctx:
        ctx.prec=80
        width=u(eband_token)
        for t in tokens:
            w=abs(D(t['weight']));uw=u(t['weight'])
            for ft,et in zip(t['occupations'],t['eigenvalues_ha']):
                f,e=abs(D(ft)),abs(D(et));uf,ue=u(ft),u(et)
                width+=(w+uw)*(f+uf)*(e+ue)-w*f*e
    width=math.nextafter(float(width),math.inf)
    return points,a,b,dict(source_xml_sha256=row['sha256'],native_tokens=tokens,
        eband_token_ha=eband_token,eband_ha=float(eband_token),eband_print_halfwidth_ha=width,
        occupations='original XML wg/wk, preserved; no new occupation solve',capacity=1)

def q_state(root,plan):
    points,a,b,xml=original_xml(root,plan);s=plan['sources']['G40'];headers=[]
    for ik,p in enumerate(points,1):
        row=s['files'][f'scratch/mg_soc_qe_v1.save/wfc{ik}.dat']
        parsed=parse_wfc(root/'.work/phase7b'/row['path'],dict(source_sha256=row['sha256'],ik=ik,
          k_cart_bohr_inv=p['k_cart'].tolist(),b_columns_bohr_inv=b.T.tolist(),npw=p.pop('npw'),nbnd=24))
        p['millers']=np.array(parsed.pop('miller'),dtype=np.int64)
        p['coefficients']=np.array(parsed.pop('coefficients'),dtype=np.complex128)
        p['coordinate_fractional']=plan['physical']['kpoints'][ik-1]
        p['source_k_index']=ik;headers.append(parsed)
    state=dict(label='Q',fft_size=plan['physical']['fft_size'],lattice_columns=a,reciprocal_columns=b,kpoints=points,
      raw_metadata=dict(schema_version=1,phase='7F',execution_status='PASS',label='Q',
       source_run_id=s['run_id'],plan_sha256=sha(root/PLAN),n_bands=24,occupation_capacity=1,
       fft_size=plan['physical']['fft_size'],source_binding_status='PASS',data_roundtrip_status='PASS',
       normalization_applied=False,orbital_rotation_applied=False,xml=xml,original_wfc=headers))
    return state

def package_state(state):
    arrays={key:state[key] for key in ('lattice_columns','reciprocal_columns')}
    for ik,k in enumerate(state['kpoints'],1):
        for name in ('millers','coefficients','occupations','eigenvalues','k_cart'):
            arrays[f'k{ik}_{name}']=k[name]
        arrays[f'k{ik}_weight']=np.array([k['weight']],dtype=np.float64)
    return arrays

def unpack_state(arrays,metadata):
    points=[]
    for ik in range(1,4):
        k={name:arrays[f'k{ik}_{name}'] for name in ('millers','coefficients','occupations','eigenvalues','k_cart')}
        k['weight']=float(arrays[f'k{ik}_weight'][0]);points.append(k)
    return dict(label='Q',kpoints=points,lattice_columns=arrays['lattice_columns'],reciprocal_columns=arrays['reciprocal_columns'],raw_metadata=metadata)

def references(root,states):
    coeff=read_coefficients_gzip(root/'results/mg-soc-density-hartree/dftk-nout.csv.gz')
    qcoeff=read_coefficients_gzip(root/'results/mg-soc-density-hartree/qe-rho.csv.gz')['QE']
    ledger=read(root/'results/mg-soc-energy-reference/ledger.json')
    out={label:dict(density_coefficients=coeff[label+'_out'],density_real=states[label]['n_out'].reshape(-1,order='F'),kinetic_ha=ledger['native_values'][label]['terms']['Kinetic']) for label in ('A','B')}
    xml=states['Q']['raw_metadata']['xml'];out['Q']=dict(density_coefficients=qcoeff,eband_ha=xml['eband_ha'],eband_print_halfwidth_ha=xml['eband_print_halfwidth_ha'])
    return out

def julia_stage(args,directory,stage,extra):
    request=dict(schema_version=1,stage=stage,plan_path=PLAN,plan_sha256=sha(ROOT/PLAN),**extra)
    req=directory/(stage+'-request.json');write(req,request);out=directory/stage
    cmd=[args.julia,'--startup-file=no','--color=no','--project=environment/workbench','scripts/extract_orbital_nonlocal.jl',str(req),str(out)]
    with (directory/(stage+'.stdout')).open('wb') as stdout,(directory/(stage+'.stderr')).open('wb') as stderr:
        result=subprocess.run(cmd,cwd=ROOT,stdout=stdout,stderr=stderr,check=False)
    write(directory/(stage+'-process.json'),dict(command=['julia']+cmd[1:],exit_code=result.returncode))
    if result.returncode:raise RuntimeError(stage+' failed, see retained child metadata/stderr; exit '+str(result.returncode))
    child=read(out/'metadata.json')
    expected=dict(schema_version=1,phase='7F',stage=stage,execution_status='PASS',exit_code=0,plan_sha256=request['plan_sha256'],source_preservation_status='PASS',environment_recheck_status='PASS')
    if any(child.get(k)!=v for k,v in expected.items()) or type(child.get('exit_code')) is not int or type(child.get('schema_version')) is not int:
        raise ValueError('Contradictory or unbound Julia child metadata')
    if child.get('environment')!=read(ROOT/PLAN)['identity']['environment'] or child.get('executed_script_sha256')!=sha(ROOT/'scripts/extract_orbital_nonlocal.jl'):
        raise ValueError('Julia child actual loaded identity or execution source differs')
    return child

def execute(args,directory,run_id):
    plan=read(ROOT/PLAN);validate_sources(ROOT,plan)
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    dirty=subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT,text=True)
    if dirty:raise ValueError('Tracked working tree must be committed before formal extraction')
    for name in EXECUTION_FILES:
        committed=subprocess.check_output(['git','show','HEAD:'+name],cwd=ROOT)
        if committed!=(ROOT/name).read_bytes():raise ValueError('Execution file not committed: '+name)
    codehash={p:sha(ROOT/p) for p in EXECUTION_FILES};write(directory/'execution.json',dict(run_id=run_id,commit=revision,source_sha256=codehash,plan_sha256=sha(ROOT/PLAN)))
    extracted=julia_stage(args,directory,'extract',{})
    states={label:load_state_metadata(directory/'extract'/ref['metadata_path'],expected_sha256=ref['sha256']) for label,ref in extracted['states'].items()}
    states['Q']=q_state(ROOT,plan)
    qmeta=write_state_metadata(states['Q'],directory/'Q');states['Q']=load_state_metadata(qmeta,expected_sha256=sha(qmeta))
    write(directory/'q-source.json',states['Q']['raw_metadata'])
    package=save_package(directory/'qe-orbitals.npz',package_state(states['Q']))
    write(directory/'qe-orbitals-manifest.json',package)
    refs=references(ROOT,states);physical=dict(plan['physical'],direct_fourier_miller_points=plan['direct_fourier_miller_points'])
    reports={};evaluated={}
    for label in ('A','B','Q'):
        print('Static original-orbital density/kinetic audit '+label,file=sys.stderr,flush=True)
        evaluated[label]=evaluate_orbitals(states[label],physical,plan['thresholds'],refs[label]);reports[label]=evaluated[label]['report']
        write(directory/'state-checks.json',reports)
        np.save(directory/(label+'-density.npy'),evaluated[label]['density_real'],allow_pickle=False)
    if not all(r['all_required_gates_passed'] for r in reports.values()):
        raise ValueError('First numerical gate failed; nonlocal construction and dependent ledger NOT_RUN')
    for ik in range(3):
        reference={tuple(m) for m in states['A']['kpoints'][ik]['millers']}
        if any({tuple(m) for m in states[s]['kpoints'][ik]['millers']}!=reference for s in ('B','Q')):
            raise ValueError('Original wavefunction Miller bijection failed; no cropping/padding')
    paths={label:directory/'extract'/label/'metadata.json' for label in ('A','B')};paths['Q']=pathlib.Path(qmeta)
    shas={k:sha(v) for k,v in paths.items()}
    gate=dict(schema_version=1,phase='7F',execution_status='PASS',plan_sha256=sha(ROOT/PLAN),orbital_metadata_sha256=shas,
       checks={key:'PASS' for key in ['source_identity','miller_bijection','normalization','density_restoration','kinetic_restoration']},state_checks_sha256=sha(directory/'state-checks.json'))
    write(directory/'gate.json',gate)
    g40=plan['sources']['G40']['run_id'];pseudo=ROOT/'.work/phase7b'/g40/'scratch/mg_soc_qe_v1.save/Mg.upf'
    nl=julia_stage(args,directory,'nonlocal',dict(gate_path=str(directory/'gate.json'),gate_sha256=sha(directory/'gate.json'),states={k:dict(metadata_path=str(v),sha256=shas[k]) for k,v in paths.items()},pseudo_path=str(pseudo)))
    # Canonical P/D and A/B/Q amplitudes. P rows use the authenticated A enumeration.
    arrays={'D':read_primitive(directory/'nonlocal',nl['operators']['D'])}
    for ik,descriptor in enumerate(nl['operators']['P'],1):
        arrays[f'k{ik}_P']=read_primitive(directory/'nonlocal',descriptor)
        arrays[f'k{ik}_millers']=states['A']['kpoints'][ik-1]['millers']
    for label,report in nl['states'].items():
        for ik,k in enumerate(report['kpoints'],1):
            for spin in ('up','down'):arrays[f'{label}_k{ik}_{spin}']=read_primitive(directory/'nonlocal',k[spin+'_amplitudes'])
    nlp=save_package(directory/'nonlocal-operator.npz',arrays);write(directory/'nonlocal-operator-manifest.json',nlp)
    from compare_orbital_energy import evaluate_comparison
    comparison=evaluate_comparison(reports,nl,evaluated['Q']['density_real'],root=ROOT);write(directory/'comparison.json',comparison)
    if any(comparison[key]!='PASS' for key in ('local_state_integral_status','signed_combination_replay_status')):
        raise ValueError('Dependent comparison gate failed; measured diagnostics retained')
    validate_sources(ROOT,plan)
    if codehash!={p:sha(ROOT/p) for p in EXECUTION_FILES}:raise ValueError('Execution code changed during audit')
    return dict(schema_version=1,phase='7F',run_id=run_id,execution_status='PASS',exit_code=0,execution_commit=revision,
       source_preservation_status='PASS',plan_sha256=sha(ROOT/PLAN),code_sha256=codehash,
       original_qe_wfc_binding_status='PASS',qe_wfc_format_status='PASS',spinor_layout_and_basis_status='PASS',
       occupation_binding_status='PASS',same_source_orbital_density_status='PASS',kinetic_direct_evaluation_status='PASS',
       dftk_same_source_T_NL_status='PASS',dftk_nonlocal_on_qe_orbitals_status='PASS',
       local_state_integral_status=comparison['local_state_integral_status'],signed_combination_replay_status=comparison['signed_combination_replay_status'],
       independent_native_qe_nonlocal_status='NOT_MEASURED',qe_original_input_hamiltonian_residual_status='NOT_AVAILABLE',
       new_scf_status='NOT_RUN',new_eigensolve_status='NOT_RUN',new_occupation_solve_status='NOT_RUN',
       new_qe_pp_execution_status='NOT_RUN',new_xc_evaluation_status='NOT_RUN',physical_convergence_status='NOT_ESTABLISHED',
       ieee_warning_origin_status='NOT_LOCALIZED',numerical_review_status='REVIEW_REQUIRED')

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--julia',default='julia');args=p.parse_args(argv)
    run_id=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+uuid.uuid4().hex[:8]
    directory=ROOT/'.work/phase7f'/run_id
    print('Phase7F run_id='+run_id,file=sys.stderr,flush=True)
    return recorded_run(directory,lambda out:execute(args,out,run_id),run_id=run_id)
if __name__=='__main__':sys.exit(main())
