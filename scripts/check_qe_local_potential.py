#!/usr/bin/env python3
"""Bound public pp receipts, full NumPy field replay and unchanged predecessors.

No .work, private path, scientific executable or network is read by this check.
Git objects certify preparation/execution versions; they do not replace data.
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import subprocess
import sys

from check_energy_reference import check_frozen, NAV
from replay_qe_local_fields import replay

ROOT=Path(__file__).resolve().parents[1]
PLAN='benchmarks/mg-soc-qe-local-potential-v1/plan.json'
RESULTS='results/mg-soc-qe-local-potential'
G40='20260907T112107073262Z-G40-3f9731a6'
CASE='mg-soc-qe-local-potential-v1'
VERIFIERS={'scripts/check_qe_local_potential.py','scripts/replay_qe_local_fields.py',
           'scripts/compare_qe_local_potential.py','scripts/parse_qe_filplot.py'}
FIELD_SCRIPT='scripts/extract_saved_local_field.jl'


def require(condition,reason):
    if not condition:raise ValueError(reason)


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def public_path(root,relative):
    require(isinstance(relative,str),'Non-string public path')
    p=Path(relative)
    require(not p.is_absolute() and '..' not in p.parts and not any(part.startswith('.') for part in p.parts),
            'Private/absolute/traversal path is not a public source')
    target=root/p
    require(target.resolve().is_relative_to(root.resolve()) and not target.is_symlink(),'Public source escapes checkout')
    return target


def load(path):
    def bad(value):raise ValueError('Nonfinite JSON token '+value)
    return json.loads(Path(path).read_text(),parse_constant=bad)


def raw_bytes(path):
    payload=Path(path).read_bytes()
    if payload.startswith(b'\x1f\x8b'):
        with gzip.open(path,'rb') as stream:payload=stream.read(64_000_001)
    require(len(payload)<=64_000_000,'Oversize native filplot')
    return payload


def raw_digest(path):return hashlib.sha256(raw_bytes(path)).hexdigest()


def native_stream(parent,name):
    """One lossless representation only; native trailing whitespace is data."""
    candidates=[parent/name,parent/(name+'.gz')]
    found=[path for path in candidates if path.exists() or path.is_symlink()]
    require(len(found)==1,'Missing or ambiguous native stream representation '+name)
    path=found[0]
    require(path.is_file() and not path.is_symlink(),'Linked/nonregular native stream '+name)
    if path.suffix=='.gz':require(path.read_bytes().startswith(b'\x1f\x8b'),'Invalid gzip native stream container')
    return path,raw_bytes(path)


def equivalent(expected,actual,thresholds,path='result'):
    """Replay gates plus strict tiny print-width comparison, never rounded tables."""
    if isinstance(expected,bool) or isinstance(actual,bool):
        require(type(expected) is type(actual) and expected==actual,'Changed bool '+path);return
    if isinstance(expected,(int,float)) and isinstance(actual,(int,float)):
        require(math.isfinite(expected) and math.isfinite(actual),'Nonfinite '+path)
        if type(expected) is int and type(actual) is int:
            require(expected==actual,'Changed integer '+path);return
        width=any(x in path.lower() for x in ('halfwidth','quantization','allowance','print_bound','u_mean','u_l_','u_shape','u_g0'))
        if width:
            tol=max(32*math.ulp(float(expected)),32*math.ulp(float(actual)),
                    thresholds['fft_normalized']*max(abs(expected),abs(actual),1e-300))
        else:
            tol=min(thresholds['ledger_abs_ha'],thresholds['fft_normalized']*max(abs(expected),abs(actual),1))
        require(abs(expected-actual)<=tol,'Changed numeric value '+path);return
    require(type(expected) is type(actual),'Changed value type '+path)
    if isinstance(expected,dict):
        require(set(expected)==set(actual),'Changed fields '+path)
        for key in expected:equivalent(expected[key],actual[key],thresholds,path+'.'+key)
    elif isinstance(expected,list):
        require(len(expected)==len(actual),'Changed list count '+path)
        for i,(a,b) in enumerate(zip(expected,actual)):equivalent(a,b,thresholds,path+'['+str(i)+']')
    else:require(expected==actual,'Changed value '+path)


def validate_comparison(result):
    require(result['schema_version']==1 and result['source_field_adjustments_applied'] is False,'Invalid field replay')
    require(result['density_integral_source']=='PUBLIC_FINITE_SERIES_RECONSTRUCTION','Public result must identify reconstructed density arrays')
    require(result['p0_phase_status']=='PASS' and len(result['p0_phase_checks'])==17
            and all(x['status']=='PASS' for x in result['p0_phase_checks']),'Missing/failed P0 phase gate')
    c=result['comparison']
    require(c['P0_density_registration_status']=='PASS','Failed P0 registration cannot certify same density')
    require(c['local_energy_decomposition_status']=='PASS_ALGEBRA','Failed local energy decomposition')
    require(c['local_same_density_integration_status']=='MEASURED_WITH_P0_AND_PRINT_LIMITS','Wrong same-density evidence scope')
    require(c['Q_TNL_record_kind']=='DERIVED_LEDGER_REMAINDER_USING_PP_RECONSTRUCTED_LOCAL_INTEGRAL'
            and c['independent_QE_T_NL_status']=='NOT_AVAILABLE','Derived ledger remainder mislabelled as direct T/NL')
    require(c['native_E_F_modified'] is False and c['numerical_review_status']=='REVIEW_REQUIRED'
            and c['physical_convergence_status']=='NOT_ESTABLISHED','Unsupported energy correction/agreement claim')
    for key in ('qe_historical_in_memory_vloc_status','qe_internal_tab_vloc_status'):
        require(c[key]=='NOT_EXTRACTED','pp reconstruction mislabelled as historical memory/table extraction')
    for source in (result,c):
        for key in ('new_scf_status','new_eigensolve_status'):require(source[key]=='NOT_RUN','Unapproved new solver scope')
    require(c['output_precision_status'] in ('PASS','PRECISION_LIMITED'),'Invalid output precision status')
    require(c['G0_prediction_comparison_status'] in ('SUPPORTED_BY_PP_RECONSTRUCTED_MEAN','NOT_SUPPORTED_BY_PP_RECONSTRUCTED_MEAN'),
            'Invalid G0 scientific comparison status')


def validate_slot(root,slot,spec,receipt,plan,evidence):
    require(receipt.get('schema_version')==1 and set(receipt)>={'schema_version','state','preflight','preservation'},'Invalid public receipt envelope')
    state=receipt['state'];pre=receipt['preflight'];pres=receipt['preservation']
    run_id=spec['run_id']
    require(isinstance(run_id,str) and re.fullmatch(r'[A-Za-z0-9-]+',run_id) is not None,'Invalid public run ID')
    for item in (state,pre):
        require(item['run_id']==run_id and item['slot']==slot and item['source_run_id']==G40,'Stale slot or wrong historical source')
    for item in (state,spec):
        require(type(item['formal_call_count']) is int and item['formal_call_count']==1,'Slot must record exactly one formal pp call')
        require(type(item['process_exit_code']) is int and item['process_exit_code']==0,'Nonzero pp process cannot publish success')
        require(item['source_preservation_status']=='PASS','Source preservation failed')
    require(state['execution_status']=='PASS' and state['postprocessing_status']=='PASS' and state['parse_status']=='PASS'
            and state['exit_code']==0 and state['copied_files_preservation_status']=='PASS','Incomplete worker result')
    require(pres['status']=='PASS' and pres['source_run_id']==G40 and pres['source_changes']=={} and pres['copy_changes']=={},
            'Source/copy changes cannot be hidden behind PASS')
    require(pre['output_absent_before'] is True,'Output existed before this slot')
    require(pre['plan_sha256']==evidence['plan_sha256'] and pre['preparation_commit']==evidence['preparation_commit']
            and pre['execution_commit']==evidence['execution_commit'],'Wrong preparation/execution identity')
    require(pre['source_files']==plan['source_files'],'Working copy source hashes differ from G40 plan')
    expected_copies={name:item['sha256'] for name,item in plan['source_files'].items()}
    expected_copies['pseudo/Mg.upf']=plan['source_files']['scratch/mg_soc_qe_v1.save/Mg.upf']['sha256']
    require(pre['copy_sha256_before']==expected_copies,'Controlled copy hashes differ from bound source files')
    require(pre['qe_identity']==plan['qe_identity'],'Worker build receipt differs from committed pp/pw identity')
    require(pre['environment']==plan['qe_identity']['single_thread_environment'],'Worker thread environment changed')
    require(pre['field_provenance']==state['field_provenance']=='QE_PP_RECONSTRUCTION_BOUND_TO_HISTORICAL_G40','Wrong pp evidence label')
    for key in ('qe_historical_in_memory_vloc_status','qe_internal_tab_vloc_status'):require(state[key]=='NOT_EXTRACTED','Native table/memory overclaim')
    require(bool(pre['execution_source_sha256']),'Missing per-slot executed code receipt')
    for path,sha in pre['execution_source_sha256'].items():
        require(evidence['execution_source_sha256'].get(path)==sha,'Per-slot executed code differs from public execution version')
    inp=plan['slots'][slot]
    input_sha=digest(public_path(root,inp['input_path']))
    require(input_sha==inp['input_sha256']==spec['input_sha256']==state['input_sha256']==pre['input_sha256'],'Wrong fixed pp input')
    native=public_path(root,evidence[slot+'_path'])
    require(raw_digest(native)==state['filplot_sha256']==spec['filplot_raw_sha256'],'Native filplot detached from current slot')
    parent=public_path(root,spec['receipt_path']).parent
    streams={}
    for name,key in [('qe.stdout','stdout_sha256'),('qe.stderr','stderr_sha256')]:
        path,payload=native_stream(parent,name)
        require(hashlib.sha256(payload).hexdigest()==state[key],'Native stream detached from current slot '+name)
        require(str(path.relative_to(root)) in evidence['public_sha256'],'Native stream missing public binding')
        streams[name]=payload.decode('utf-8')
    stdout=streams['qe.stdout'];stderr=streams['qe.stderr']
    for name,text in [('stdout',stdout),('stderr',stderr)]:
        require(state['warnings'][name]['ieee_flags']==sorted(set(re.findall(r'IEEE_[A-Z_]+',text))),
                'Recorded IEEE flags differ from native stream')
    require(re.search(r'Program\s+POST-PROC\s+v\.7\.5\b',stdout) is not None and 'JOB DONE.' in stdout,'Missing native pp completion')
    require(not re.search(r'Error in routine|MPI_ABORT|SIGSEGV|Self-consistent Calculation|End of self-consistent calculation|iteration #',stdout+'\n'+stderr,re.I),
            'Native fatal/solver evidence conflicts with slot success')
    return {'run_id':run_id,'formal_call_count':1,'status':'PASS'}


def _git_bytes(root,commit,path):
    require(isinstance(commit,str) and re.fullmatch('[0-9a-f]{40}',commit) is not None,'Exact commit SHA required')
    return subprocess.check_output(['git','-C',str(root),'show',commit+':'+path],stderr=subprocess.PIPE)


def dftk_export_digest(path):
    """Restore exact first-five CSV column strings/order, not reformatted floats."""
    with gzip.open(path,'rb') as stream:raw=stream.read(64_000_001)
    require(len(raw)<=64_000_000 and b'\r' not in raw and raw.endswith(b'\n'),'Invalid canonical potential byte layout')
    lines=raw.decode('ascii').splitlines()
    require(lines and lines[0]=='m1,m2,m3,V_D_real,V_D_imag,V_Qpp_real,V_Qpp_imag','Wrong canonical potential header')
    # Numeric/support validation occurs in full replay. Here exact spelling,
    # signed zero and native row order must reconstruct the producer's export.
    out=['m1,m2,m3,V_D_real,V_D_imag']
    for line in lines[1:]:
        require(len(line.split(','))==7 and '"' not in line,'Unexpected canonical CSV token layout')
        out.append(','.join(line.split(',')[:5]))
    return hashlib.sha256(('\n'.join(out)+'\n').encode('ascii')).hexdigest()


def validate_field_binding(receipt,evidence,plan,prior,common,prior_sha,native_sha):
    """Bind the archived-field producer to public 7D receipts and full D CSV."""
    require(receipt['schema_version']==1 and receipt['execution_status']=='PASS' and receipt['exit_code']==0
            and receipt['source_preservation_status']=='PASS','Saved-field extraction did not pass')
    require(receipt['run_id']==evidence['field_run_id'] and receipt['execution_commit']==evidence['execution_commit']
            and receipt['plan_sha256']==evidence['plan_sha256'],'Saved-field production run/commit/plan mismatch')
    require(receipt['executed_script_sha256']==evidence['execution_source_sha256'][FIELD_SCRIPT],'Saved-field executed script mismatch')
    binding=receipt['source_binding']
    require(binding['source_evidence_path']=='results/mg-soc-energy-reference/evidence.json'
            and binding['source_evidence_sha256']==prior_sha,'Saved-field historical evidence mismatch')
    require(binding['source_run_id']==prior['run_id']==plan['dftk_source_run_id']
            and binding['source_execution_commit']==prior['execution_commit'],'Wrong historical DFTK field run')
    for field,path in [('arrays_sha256','common/arrays.bin'),('metadata_sha256','common/metadata.json'),('receipt_sha256','result.json')]:
        require(binding[field]==prior['execution_logs'][path],'Wrong historical '+path+' identity')
    require(binding['producer_script_sha256']==prior['execution_source_sha256']['scripts/evaluate_common_energy_terms.jl'],'Wrong historical field producer')
    require(binding['production_julia_version']==plan['julia_version']==common['environment']['julia_version'],'Wrong historical Julia version')
    require(receipt['environment']==common['environment'] and receipt['environment']['status']=='PASS','Saved-field loaded environment differs from historical receipt')
    require(binding['historical_archive']==prior['backup'],'Historical archive/restore receipt mismatch')
    require(receipt['constants']==common['constants'],'Changed historical field constants')
    require(native_sha==receipt['outputs_local_sha256']['native'],'Canonical D potential differs from whole native export')
    require(receipt['original_array_scope'].startswith('ORIGINAL_ARCHIVED_ARRAYS;'),'Original arrays relabelled')


def validate_saved_field(root,e,plan,replayed):
    path=e['saved_field_receipt_path'];require(path in e['public_sha256'],'Missing saved-field public binding')
    receipt=load(public_path(root,path))
    prior_path='results/mg-soc-energy-reference/evidence.json';prior=load(root/prior_path)
    common=load(root/'results/mg-soc-energy-reference/common-terms.json')
    ledger=load(root/'results/mg-soc-energy-reference/ledger.json')
    validate_field_binding(receipt,e,plan,prior,common,digest(root/prior_path),dftk_export_digest(root/e['potential_path']))
    t=plan['thresholds'];field=receipt['field_checks']
    require(field['status']=='PASS' and field['origin_fractional']==[0,0,0] and field['applied_mean_shift'] is False
            and field['applied_density_normalization'] is False,'Saved field origin/adjustment mismatch')
    require(field['fft_size']==plan['physical']['fft_size'] and field['physical_node_count']==math.prod(plan['physical']['fft_size']),
            'Saved field physical grid mismatch')
    require(field['local_fft']['status']=='PASS' and field['local_fft']['coefficient_count']==field['physical_node_count']
            and len(field['local_fft']['direct_checks'])==17,'Incomplete historical-field FFT/17-mode checks')
    require(field['local_fft']['complex_roundtrip_normalized']<=t['fft_normalized']
            and field['local_fft']['parseval_normalized']<=t['fft_normalized']
            and field['local_nbar_restoration_normalized']<=t['fft_normalized'],'Saved-field FFT gate failed')
    require([r['miller'] for r in field['local_fft']['direct_checks']]==plan['direct_fourier_miller_points'],'Saved-field Fourier probe set changed')
    require(all(r['normalized_error']<=t['fft_normalized'] for r in field['local_fft']['direct_checks']),'Saved-field phase check failed')
    for label,name in [('A','A_original_n_out'),('B','B_original_n_out'),('Q','Q_rep')]:
        s=receipt['saved_density_checks'][label];h=common['evaluations'][name]
        require(s['status']=='PASS' and s['source_evaluation']==name,'Wrong saved density label')
        require(s['n_sha256']==h['array_sha256']['n'] and s['potential_sha256']==h['array_sha256']['local_potential'],'Saved density/potential array source mismatch')
        require(abs(s['local_integral_ha']-h['local_integral_ha'])<=t['dftk_local_recovery_abs_ha']
                and abs(s['local_integral_ha']-s['local_fourier_integral_ha'])<=t['real_fourier_energy_abs_ha'],'Saved native integral does not recover history')
        original=receipt['original_pointwise_integrals_ha']['L_D_'+label]
        require(abs(original-h['local_integral_ha'])<=t['dftk_local_recovery_abs_ha'],'Original-point integral differs from history')
        require(abs(original-replayed['pointwise']['integrals_ha']['L_D_'+label])<=t['real_fourier_energy_abs_ha'],'Original/public reconstruction drift too large')
        diff=receipt['original_vs_public_reconstruction'][label]
        require(diff['status']=='PASS' and diff['normalized_l2']<=t['fft_normalized'],'Original density reconstruction failed')
    require(abs(receipt['original_potential_mean_ha']-common['evaluations']['Q_rep']['local_mean_ha'])<=t['dftk_mean_recovery_abs_ha'],'Original mean differs from history')
    require(abs(receipt['original_potential_mean_ha']-replayed['pointwise']['means_ha']['D'])<=t['dftk_mean_recovery_abs_ha'],'Original/public D mean mismatch')
    original=receipt['original_pointwise_integrals_ha'];pc=common['constants']['psp_correction_ha'];mean=receipt['original_potential_mean_ha']
    for key,value in original.items():
        require(abs(value-replayed['pointwise']['integrals_ha'][key])<=t['real_fourier_energy_abs_ha'],'Original/public local integral drift '+key)
    for label in ('A','B'):
        row=receipt['original_comparisons'][label+'_minus_G40'];hist=ledger['native_values'][label]['terms']
        rho=original['L_D_'+label]-original['L_D_Q'];g0=pc+receipt['saved_density_checks']['Q']['electron_count']*(mean-replayed['pointwise']['means_ha']['Qpp'])
        current=original['L_D_'+label]+pc-original['L_Qpp_Q']
        drift=original['L_D_'+label]+pc-hist['AtomicLocal']-hist['PspCorrection']
        historical=hist['AtomicLocal']+hist['PspCorrection']-original['L_Qpp_Q']
        remainder=ledger['comparisons'][label+'_minus_G40']['delta_ha']['O']-historical
        for key,value in [('rho_response_ha',rho),('g0_at_Q_ha',g0),('Delta_Lbar_current_ha',current),
                          ('same_source_local_plus_Pc_drift_ha',drift),('Delta_Lbar_historical_ha',historical),('R_after_local_ha',remainder)]:
            require(abs(row[key]-value)<=t['ledger_abs_ha'],'Original scalar decomposition mismatch '+key)
        require(abs(row['shape_at_Q_ha']-replayed['comparison']['comparisons'][label+'_minus_G40']['shape_at_Q_ha'])<=t['real_fourier_energy_abs_ha'],'Original/public same-Q shape drift')
        equivalent(row,replayed['comparison']['comparisons'][label+'_minus_G40'],t,'original comparison.'+label)
    return {'status':'PASS','field_run_id':receipt['run_id'],'full_D_native_export_sha256':receipt['outputs_local_sha256']['native'],
            'scope':'Whole D coefficient export and public arithmetic bound to original producer receipt; raw private arrays not reread'}


def check(root=ROOT):
    root=Path(root).resolve();plan=load(root/PLAN);e=load(root/RESULTS/'evidence.json')
    require(e['schema_version']==plan['schema_version']==1 and e['case']==plan['case']==CASE,'Wrong case/schema')
    require(e['base_commit']==plan['base_commit'] and e['plan_sha256']==digest(root/PLAN),'Wrong base/plan identity')
    require(set(e['slots'])=={'P2','P0'} and e['slots']['P2']['run_id']!=e['slots']['P0']['run_id'],'Distinct independent slots required')
    for field in ('DFTK_saved_local_field_status','pp_build_identity_status','historical_G40_binding_status'):
        require(e[field]=='PASS','Unaccepted source gate '+field)
    require(plan['source_run_id']==G40 and plan['execution_order']==['P2','P0'],'Wrong source or execution sequence plan')
    require(plan['qe_identity']['pp_build_identity_status']=='PASS' and plan['qe_identity']['historical_pw_verification_status']=='PASS','Same-build pp gate missing')
    require(digest(public_path(root,plan['identity_path']))==plan['identity_sha256'],'Changed public build identity file')
    require(load(root/plan['identity_path'])==plan['qe_identity'],'Identity object detached from plan')
    require(VERIFIERS<=set(e['verifier_sha256']),'Missing current verification code bindings')
    require(bool(e['execution_source_sha256']),'Missing executed source version')
    for mapping in (plan['source_sha256'],e['public_sha256'],e['verifier_sha256']):
        for path,sha in mapping.items():require(digest(public_path(root,path))==sha,'Changed bound public bytes: '+path)
    for key in ('comparison_path','potential_path','P2_path','P0_path'):
        require(e[key] in e['public_sha256'],'Missing canonical output binding '+key)
    for slot in ('P2','P0'):require(e['slots'][slot]['receipt_path'] in e['public_sha256'],'Missing slot receipt binding')
    require(hashlib.sha256(_git_bytes(root,e['preparation_commit'],PLAN)).hexdigest()==e['plan_sha256'],'Preparation Git plan bytes differ')
    for slot in ('P2','P0'):
        s=plan['slots'][slot]
        require(hashlib.sha256(_git_bytes(root,e['preparation_commit'],s['input_path'])).hexdigest()==s['input_sha256'],'Preparation Git input differs')
    for path,sha in e['execution_source_sha256'].items():
        public_path(root,path)
        require(hashlib.sha256(_git_bytes(root,e['execution_commit'],path)).hexdigest()==sha,'Executed Git source differs: '+path)
    for older,newer in ((e['base_commit'],e['preparation_commit']),(e['preparation_commit'],e['execution_commit'])):
        require(subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',older,newer],stdout=subprocess.PIPE,stderr=subprocess.PIPE).returncode==0,'Invalid preparation ancestry')
    slots={slot:validate_slot(root,slot,e['slots'][slot],load(root/e['slots'][slot]['receipt_path']),plan,e) for slot in ('P2','P0')}
    computed=replay(root,plan,e['potential_path'],e['P2_path'],e['P0_path'])
    saved=load(root/e['comparison_path']);validate_comparison(saved);validate_comparison(computed)
    equivalent(computed,saved,plan['thresholds'])
    saved_field=validate_saved_field(root,e,plan,computed)
    count=check_frozen(root,e['base_commit'])
    for doc in NAV:require('mg-soc-qe-local-potential' in (root/doc).read_text(),'Missing current navigation '+doc)
    return {'status':'PASS','slots':slots,'saved_field':saved_field,'frozen_predecessor_files':count,'backend':computed['backend'],
        'output_precision_status':computed['comparison']['output_precision_status'],
        'scope':'Full public fields/FFT/17 direct modes, all-node P0 and uncertainty, exact coefficient local integrals and signed ledger; not rerunning pp or measuring independent QE T/NL',
        'private_sources_read':False,'new_scf_status':'NOT_RUN','new_eigensolve_status':'NOT_RUN'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--all',action='store_true')
    parser.add_argument('--legacy-python',default='python3.9');parser.add_argument('--modern-python',default=sys.executable)
    args=parser.parse_args()
    try:
        if args.all:subprocess.run([args.modern_python,str(args.root/'scripts/check_energy_reference.py'),'--all',
            '--root',str(args.root),'--legacy-python',args.legacy_python,'--modern-python',args.modern_python],check=True,cwd=args.root)
        print(json.dumps(check(args.root),indent=2,allow_nan=False));return 0
    except (ValueError,KeyError,TypeError,OSError,subprocess.CalledProcessError) as error:
        print('FAIL: '+str(error),file=sys.stderr);return 1


if __name__=='__main__':sys.exit(main())
