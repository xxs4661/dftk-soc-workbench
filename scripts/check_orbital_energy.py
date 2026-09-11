#!/usr/bin/env python3
"""Offline Phase7F replay: complete public Q orbitals and frozen FR contractions.

Never reads .work, uses UPF, starts Julia/QE, or constructs a new electronic state.
A/B source extraction and kinetic restoration remain explicitly runner-reported.
"""
import argparse,hashlib,json,math,pathlib,struct,subprocess,sys
import numpy as np
from orbital_evidence import load_package
from run_orbital_energy_audit import ROOT,PLAN,PUBLIC,EXECUTION_FILES,sha,read,checked,unpack_state,original_xml
from audit_orbital_kinetics import evaluate_orbitals,block_to_interleaved
from compare_density_hartree import read_coefficients_gzip
from compare_orbital_energy import evaluate_comparison

def require(value,message):
    if not value:raise ValueError(message)
def close(a,b,abs_tol=1e-11):
    if isinstance(a,dict):
        require(isinstance(b,dict) and a.keys()==b.keys(),'Report keys differ')
        for k in a:close(a[k],b[k],abs_tol)
    elif isinstance(a,list):
        require(isinstance(b,list) and len(a)==len(b),'Report lengths differ')
        for x,y in zip(a,b):close(x,y,abs_tol)
    elif type(a) in (int,float) and type(b) in (int,float):require(math.isfinite(a) and math.isfinite(b) and abs(a-b)<=abs_tol,'Numerical replay differs: '+str((a,b)))
    else:require(a==b,'Replay differs: '+str((a,b))[:200])

def verify_native_wfc_roundtrip(native,stored,expected_row,ik):
    """Rebuild original G40 record bytes in memory, without exporting a WFC.

    The immutable plan's whole-file hash is the authority. Header/payload
    hashes alone do not authenticate the assembled file or its original slot.
    This restricted replay supports the actually observed LE/M4/I4/L4 format.
    """
    require(type(ik) is int and 1<=ik<=3,'Invalid original G40 k slot')
    expected_path=('20260907T112107073262Z-G40-3f9731a6/'
                   f'scratch/mg_soc_qe_v1.save/wfc{ik}.dat')
    require(expected_row['path']==expected_path,'Wavefunction binding is not the original G40 slot')
    require(native['schema_version']==1 and native['qe_wfc_format_status']=='PASS','Native format record did not pass')
    h=native['metadata'];digest=expected_row['sha256']
    require(type(digest) is str and len(digest)==64 and all(x in '0123456789abcdef' for x in digest),
            'Invalid original whole-file hash')
    require(native['source_sha256']==h['source_sha256']==digest,'Native source hash differs from original G40 plan')
    require(h['format']==dict(endian='little',record_marker_bytes=4,integer_bytes=4,
            logical_bytes=4,real_bytes=8,complex_bytes=16),'Unsupported native replay byte format')
    require(type(h['candidate_count']) is int and h['candidate_count']==1,'Native format candidate is not unique')
    require(type(h['ik']) is int and h['ik']==ik and type(h['ngw']) is int and type(h['igwx']) is int
            and 1<=h['igwx']<=100000 and h['igwx']<=h['ngw']<=1000000,'Native dimensions or k slot differ')
    require(h['ispin']==1 and h['npol']==2 and h['nbnd']==24 and h['scalef']==1.
            and h['gamma_only'] is False and type(h['gamma_only_raw']) is int and h['gamma_only_raw']==0,
            'Unsupported native spin, scale or gamma convention')
    require(h['miller_values_status']=='PASS' and h['coefficient_values_status']=='PASS'
            and h['coefficient_bitwise_roundtrip_status']=='PASS','Native payload verification was incomplete')
    ng=h['igwx'];m=stored['millers'];c=stored['coefficients']
    require(isinstance(m,np.ndarray) and m.dtype.str=='<i8' and m.shape==(ng,3)
            and np.all((m>=-2147483648)&(m<=2147483647)), 'Native Miller values cannot be encoded exactly as Int32')
    require(len({tuple(row) for row in m})==ng,'Duplicate native Miller values')
    require(isinstance(c,np.ndarray) and c.dtype.str=='<c16' and c.shape==(2,ng,24)
            and np.isfinite(c).all() and native['shape']==[2,ng,24], 'Native spinor dtype, shape or values differ')
    k=np.asarray(h['k_cart_bohr_inv'],dtype='<f8');b=np.asarray(h['b_columns_bohr_inv'],dtype='<f8')
    require(k.shape==(3,) and b.shape==(3,3) and np.isfinite(k).all() and np.isfinite(b).all(),
            'Invalid native reciprocal geometry')
    require(np.array_equal(k,stored['k_cart']),'Native header and canonical Cartesian k differ')
    headers=[struct.pack('<i3diid',ik,*k.tolist(),h['ispin'],h['gamma_only_raw'],h['scalef']),
             struct.pack('<4i',h['ngw'],ng,h['npol'],h['nbnd']),
             b.tobytes(order='C')]
    miller=m.astype('<i4').tobytes(order='C')
    bands=[np.ascontiguousarray(c[:,:,band]).tobytes(order='C') for band in range(24)]
    require(hashlib.sha256(b''.join(headers)).hexdigest()==h['header_payload_sha256'],'Native header payload hash differs')
    require(hashlib.sha256(miller).hexdigest()==native['miller_payload_sha256'],'Native Miller payload hash differs')
    require(hashlib.sha256(b''.join(bands)).hexdigest()==native['coefficient_payload_sha256'],'Native coefficient payload hash differs')
    payloads=headers+[miller]+bands;records=[];offset=0;whole=hashlib.sha256()
    for payload in payloads:
        marker=struct.pack('<i',len(payload))
        records.append(dict(payload_offset=offset+4,payload_bytes=len(payload)))
        whole.update(marker);whole.update(payload);whole.update(marker);offset+=len(payload)+8
    require(records==h['records'] and [len(p) for p in payloads]==h['record_payload_bytes'],
            'Native record envelope metadata differs')
    require(type(expected_row['bytes']) is int and offset==expected_row['bytes']==h['file_bytes'],
            'Native whole-file byte count differs')
    require(whole.hexdigest()==digest,'Reconstructed whole WFC hash differs from original G40')
    return dict(status='PASS',sha256=whole.hexdigest(),bytes=offset,records=len(records),
                scope='IN_MEMORY_EXACT_NATIVE_FILE_BYTES; no WFC exported or numerical reevaluation')

def kinetic_scalar_replay(reports,thresholds=None):
    """Replay all published T rows; A/B original X is still not public here."""
    from audit_orbital_kinetics import DEFAULT_THRESHOLDS
    t=DEFAULT_THRESHOLDS if thresholds is None else thresholds
    require(set(reports)=={'A','B','Q'},'Exactly original A/B/Q kinetic tables required')
    summary={}
    for label,report in reports.items():
        require(report['label']==label and report['status']=='PASS' and report['all_required_gates_passed'] is True,
                'Kinetic source report failed')
        require(report['state_count']==24 and report['k_count']==3,'Original24 states at three k points required')
        points=report['per_k'];norm_reports=report['normalization_and_gram']
        require(len(points)==len(norm_reports)==3,'Missing original k table')
        weighted=[];gradient_weighted=[];electrons=[];norm_electrons=[];weights=[]
        for ik,(point,norms) in enumerate(zip(points,norm_reports)):
            require(point['k_index_zero_based']==norms['k_index_zero_based']==ik,'Kinetic k order changed')
            require(point['NG']==norms['NG'] and type(point['NG']) is int and point['NG']>0,'Kinetic/norm G count mismatch')
            require(len(point['states'])==len(norms['norms'])==24,'Incomplete kinetic or norm state table')
            require(norms['status']=='PASS','Original normalization/Gram failed')
            norm_error=max(abs(x-1) for x in norms['norms'])
            close(norm_error,norms['maximum_norm_error'],0.)
            require(math.isfinite(norms['gram_frobenius']) and 0<=norms['gram_frobenius']<=t['gram_frobenius']
                    and norm_error<=t['state_norm_abs'],'Original norm/Gram exceeds gate')
            w=point['weight_spatial'];require(type(w) is float and math.isfinite(w) and w>0,'Invalid original spatial weight')
            weights.append(w);kw=[];kg=[]
            for band,row in enumerate(point['states']):
                require(row['band_one_based']==band+1,'Original kinetic band order changed')
                for key in ('occupation','norm','eigenvalue_ha','kinetic_unweighted_ha','gradient_unweighted_ha',
                            'kinetic_weighted_ha','gradient_weighted_ha','signed_path_difference_ha'):
                    require(type(row[key]) in (int,float) and math.isfinite(row[key]),'Nonfinite kinetic row '+key)
                f=row['occupation'];require(0<=f<=1,'Kinetic occupation exceeds spinor capacity one')
                close(row['norm'],norms['norms'][band],0.)
                require(row['kinetic_unweighted_ha']>=0 and row['gradient_unweighted_ha']>=0,'Negative squared kinetic expectation')
                direct=w*f*row['kinetic_unweighted_ha'];grad=w*f*row['gradient_unweighted_ha']
                close(direct,row['kinetic_weighted_ha'],t['ledger_abs_ha'])
                close(grad,row['gradient_weighted_ha'],t['ledger_abs_ha'])
                close(row['kinetic_unweighted_ha']-row['gradient_unweighted_ha'],row['signed_path_difference_ha'],t['ledger_abs_ha'])
                kw.append(direct);kg.append(grad);electrons.append(w*f);norm_electrons.append(w*f*row['norm'])
            close(math.fsum(kw),point['kinetic_ha'],t['ledger_abs_ha'])
            close(math.fsum(kg),point['gradient_kinetic_ha'],t['ledger_abs_ha'])
            weighted.extend(kw);gradient_weighted.extend(kg)
        close(math.fsum(weights),1.,t['reciprocal_duality_abs'])
        ne=math.fsum(electrons);ne_norm=math.fsum(norm_electrons)
        close(ne,10.,t['electron_count_abs']);close(ne_norm,10.,t['electron_count_abs'])
        close(ne,report['electrons']['from_occupations'],t['electron_count_abs'])
        close(ne_norm,report['electrons']['from_actual_norms'],t['electron_count_abs'])
        direct=math.fsum(weighted);gradient=math.fsum(gradient_weighted);k=report['kinetic']
        close(direct,k['direct_ha'],t['ledger_abs_ha']);close(gradient,k['gradient_ha'],t['ledger_abs_ha'])
        close(direct-gradient,k['signed_difference_ha'],t['ledger_abs_ha'])
        require(k['status']=='PASS' and abs(direct-gradient)<=t['kinetic_paths_abs_ha'],'Kinetic paths gate failed')
        kind='DIRECT_REEVALUATION_OF_KINETIC_FROM_ORIGINAL_QE_WFC' if label=='Q' else 'DIRECT_REEVALUATION_OF_KINETIC_FROM_ORIGINAL_DFTK_X'
        require(k['evidence_kind']==kind,'Kinetic quantity mislabelled as a native printed field')
        if label!='Q':
            require(k['same_source_status']=='PASS','A/B historical T failed')
            close(direct,k['historical_ha'],t['kinetic_history_abs_ha'])
            close(direct-k['historical_ha'],k['historical_signed_difference_ha'],t['ledger_abs_ha'])
        summary[label]=dict(kinetic_ha=direct,gradient_kinetic_ha=gradient,electrons_from_table=ne,
            states_replayed=72,status='PASS_SCALAR_TABLE_REPLAY',
            evidence_tier='Published per-state table arithmetic; does not reconstruct original A/B X')
    return summary

def nonlocal_replay(arrays,state,reports,nl):
    d=arrays['D'];require(d.shape==(16,16) and np.max(abs(d-d.conj().T))<=1e-12,'Full Hermitian D16 required')
    totals={label:[] for label in ('A','B','Q')}
    for ik in range(1,4):
        p=arrays[f'k{ik}_P'];m=arrays[f'k{ik}_millers'];k=state['kpoints'][ik-1]
        require(p.shape==(2*len(m),16) and len({tuple(x) for x in m})==len(m),'Invalid original P basis')
        lookup={tuple(x):i for i,x in enumerate(k['millers'])}
        require(set(lookup)=={tuple(x) for x in m},'Q versus P Miller bijection differs')
        x=block_to_interleaved(k['coefficients'][:,[lookup[tuple(g)] for g in m],:])
        up=p[0::2].conj().T@x[0::2];down=p[1::2].conj().T@x[1::2]
        require(np.max(abs(up-arrays[f'Q_k{ik}_up']))<=1e-11 and np.max(abs(down-arrays[f'Q_k{ik}_down']))<=1e-11,'Public Q projection differs')
        vx=p@(d@(p.conj().T@x))
        for label in ('A','B','Q'):
            yu=arrays[f'{label}_k{ik}_up'];yd=arrays[f'{label}_k{ik}_down'];y=yu+yd
            require(y.shape==(16,24),'All original24 amplitudes required')
            rows=nl['states'][label]['kpoints'][ik-1]['rows'];original=reports[label]['per_k'][ik-1]
            require(len(rows)==24 and [r.get('band') for r in rows]==list(range(1,25)),'Nonlocal records must retain all24 originalbands')
            for band,row in enumerate(rows):
                f=original['states'][band]['occupation'];w=original['weight_spatial']
                require(f==row['occupation'] and w==row['weight_spatial'],'Original occupations/weights differ')
                proj=float(np.vdot(y[:,band],d@y[:,band]).real)
                uu=float(np.vdot(yu[:,band],d@yu[:,band]).real);dd=float(np.vdot(yd[:,band],d@yd[:,band]).real)
                cross=np.vdot(yu[:,band],d@yd[:,band])
                for key,value in dict(projected_ha=proj,up_up_ha=uu,down_down_ha=dd,up_down_real_ha=float(cross.real),up_down_imag_ha=float(cross.imag),spin_cross_ha=float(2*cross.real),spin_sum_ha=uu+dd+2*float(cross.real)).items():
                    close(value,row[key],1e-10)
                close(row['action_ha'],proj,1e-10)
                for field in ('action','projected','spin_sum'):close(row['weighted_'+field+'_ha'],w*f*row[field+'_ha'],1e-10)
                if label=='Q':close(float(np.vdot(x[:,band],vx[:,band]).real),row['action_ha'],1e-10)
                totals[label].append(w*f*proj)
    for label,values in totals.items():
        for name in ('action','projected','spin_sum'):close(math.fsum(values),nl['states'][label]['energy_'+name+'_ha'],1e-10)
    return {k:math.fsum(v) for k,v in totals.items()}

def replay(root=ROOT):
    out=root/PUBLIC;e=read(out/'evidence.json');plan=read(root/PLAN)
    for p,h in plan['source_sha256'].items():checked(root/p,h)
    expected={PUBLIC+'/'+name for name in ('qe-orbitals.npz','nonlocal-operator.npz','state-checks.json','nonlocal-checks.json','comparison.json','execution.json')}
    require(set(e['public_sha256'])==expected,'Canonical public file hash whitelist differs')
    for p,h in e['public_sha256'].items():checked(root/p,h)
    execution=read(out/'execution.json')
    require(execution['schema_version']==1 and execution['phase']=='7F' and execution['execution_status']=='PASS' and type(execution['exit_code']) is int and execution['exit_code']==0,'Execution receipt is not PASS')
    require(execution['run_id']==e['run_id'] and execution['plan_sha256']==e['plan_sha256'] and execution['execution_commit']==e['execution_commit'],'Execution identity differs')
    require(set(execution['code_sha256'])==set(EXECUTION_FILES),'Execution source whitelist differs')
    for p,h in execution['code_sha256'].items():checked(root/p,h)
    for key in ('original_qe_wfc_binding_status','qe_wfc_format_status','spinor_layout_and_basis_status','occupation_binding_status','same_source_orbital_density_status','kinetic_direct_evaluation_status','dftk_same_source_T_NL_status','dftk_nonlocal_on_qe_orbitals_status','local_state_integral_status','signed_combination_replay_status'):
        require(execution.get(key)=='PASS','Required execution stage not PASS: '+key)
    require(execution.get('independent_native_qe_nonlocal_status')=='NOT_MEASURED' and execution.get('qe_original_input_hamiltonian_residual_status')=='NOT_AVAILABLE','Unsupported native QE claim')
    require(e['plan_sha256']==sha(root/PLAN),'Plan binding differs')
    require(set(e.get('verifier_sha256',{}))=={'scripts/check_orbital_energy.py'},'Verifier identity whitelist differs')
    for name,digest in e['verifier_sha256'].items():checked(root/name,digest)
    reports=read(out/'state-checks.json');kinetic_tables=kinetic_scalar_replay(reports,plan['thresholds'])
    qmeta=e['Q_source_metadata'];packages=e['packages']
    qa=load_package(out/'qe-orbitals.npz',packages['qe-orbitals']);q=unpack_state(qa,qmeta)
    points,a,b,xml=original_xml(root,plan,root/'results/mg-soc-qe-diagnostics/G40/qe.xml')
    require(np.array_equal(a,q['lattice_columns']) and np.array_equal(b,q['reciprocal_columns']),'Public Q geometry differs')
    close(xml,qmeta['xml'])
    for ik,(point,stored) in enumerate(zip(points,q['kpoints'])):
        for name in ('occupations','eigenvalues','k_cart'):require(np.array_equal(point[name],stored[name]),'Public Q not original XML '+name)
        require(point['weight']==stored['weight'] and point['npw']==len(stored['millers']),'Public Q original npw/weight differs')
        native=qmeta['original_wfc'][ik];c=stored['coefficients']
        expected_row=plan['sources']['G40']['files'][f'scratch/mg_soc_qe_v1.save/wfc{ik+1}.dat']
        verify_native_wfc_roundtrip(native,stored,expected_row,ik+1)
        payload=b''.join(np.ascontiguousarray(c[:,:,n],dtype='<c16').tobytes() for n in range(24))
        require(hashlib.sha256(payload).hexdigest()==native['coefficient_payload_sha256'],'Native complex payload roundtrip differs')
        require(hashlib.sha256(stored['millers'].astype('<i4').tobytes()).hexdigest()==native['miller_payload_sha256'],'Native Miller payload differs')
    reference=dict(density_coefficients=read_coefficients_gzip(root/'results/mg-soc-density-hartree/qe-rho.csv.gz')['QE'],eband_ha=xml['eband_ha'],eband_print_halfwidth_ha=xml['eband_print_halfwidth_ha'])
    physical=dict(plan['physical'],direct_fourier_miller_points=plan['direct_fourier_miller_points'])
    evaluated=evaluate_orbitals(q,physical,plan['thresholds'],reference)
    require(evaluated['report']['all_required_gates_passed'],'Public Q first gates fail');close(evaluated['report'],reports['Q'])
    nl=read(out/'nonlocal-checks.json');op=load_package(out/'nonlocal-operator.npz',packages['nonlocal-operator'])
    totals=nonlocal_replay(op,q,reports,nl)
    comparison=evaluate_comparison(reports,nl,evaluated['density_real'],root=root)
    close(comparison,read(out/'comparison.json'))
    require(comparison['signed_combination_replay_status']=='PASS','Signed ledger failed')
    return dict(status='PASS',Q_full_coefficient_density_T_and_frozen_FR_replay='PASS',AB_projected_contractions_replay='PASS',AB_original_X_extraction_and_T='RUNNER_REPORTED',native_QE_NL='NOT_MEASURED',totals_ha=totals,kinetic_scalar_tables=kinetic_tables)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--all',action='store_true');p.add_argument('--legacy-python',default='python3.9');p.add_argument('--modern-python',default=sys.executable);args=p.parse_args(argv)
    try:
        result=replay()
        if args.all:
            completed=subprocess.run([sys.executable,str(ROOT/'scripts/check_qe_local_potential.py'),'--all','--legacy-python',args.legacy_python,'--modern-python',args.modern_python],cwd=ROOT,check=False)
            require(completed.returncode==0,'Prior public evidence chain failed')
        print(json.dumps(result,allow_nan=False));return 0
    except Exception as exc:print(json.dumps(dict(status='FAIL',reason=str(exc)),allow_nan=False));return 1
if __name__=='__main__':sys.exit(main())
