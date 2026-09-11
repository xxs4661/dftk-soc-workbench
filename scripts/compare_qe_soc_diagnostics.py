#!/usr/bin/env python3
"""Offline arithmetic for the bounded Phase 7B Mg solver/grid experiment.

No solver runs; no fabricated 7A case; historical inputs are read at their real
paths and checked against their immutable evidence. Payload hashes protect
against accidentally mixing stages; native reparse remains the authenticity check.
"""
import argparse
import copy
import csv
import hashlib
import json
import math
from pathlib import Path

from compare_qe_soc import (HARTREE_EV, close, energy_record, finite_number,
                           finite_tree, global_homo, historical_record,
                           load_historical, matched_points, require, validate_spectrum)

SLOTS=('I36','D36','C36','G40','D40','C40')
NUMERIC=('D36','C36','G40','D40','C40')
CROSS_TARGETS=('Q36','D36','C36','G40','D40','C40')
PAYLOAD_FIELDS=('case','phase','slot','calculation','kpoints','energy','fermi_energy_ha',
                'electrons','n_bands','occupation_capacity','tau_ha','smearing','xc',
                'pseudo_sha256','lattice_vectors_bohr','positions_fractional',
                'ecut_ha','ecutrho_ha','fft_grid','fft_smooth_grid','native_files_sha256')


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    obj=json.loads(Path(path).read_text());finite_tree(obj);return obj


def payload_sha256(record):
    payload={key:record.get(key) for key in PAYLOAD_FIELDS}
    finite_tree(payload)
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def delta(value):
    finite_number(value,'Difference')
    return {'signed_ha':value,'absolute_ha':abs(value),'signed_ev':value*HARTREE_EV,
            'absolute_ev':abs(value)*HARTREE_EV,'signed_mev':value*HARTREE_EV*1e3,
            'absolute_mev':abs(value)*HARTREE_EV*1e3,'signed_uev':value*HARTREE_EV*1e6,
            'absolute_uev':abs(value)*HARTREE_EV*1e6}


def statistic(rows,key):
    if not rows:return {'status':'EMPTY_GROUP','count':0,'maximum_location':None}
    values=[finite_number(row[key],key) for row in rows]
    maximum=max(abs(x) for x in values);rms=math.sqrt(sum(x*x for x in values)/len(values))
    where=rows[next(i for i,x in enumerate(values) if abs(x)==maximum)]
    return {'status':'REPORTED','count':len(values),'max_abs_ha':maximum,'rms_ha':rms,
            'max_abs_ev':maximum*HARTREE_EV,'rms_ev':rms*HARTREE_EV,
            'max_abs_mev':maximum*HARTREE_EV*1e3,'rms_mev':rms*HARTREE_EV*1e3,
            'max_abs_uev':maximum*HARTREE_EV*1e6,'rms_uev':rms*HARTREE_EV*1e6,
            'maximum_location':{k:where[k] for k in ('k_index','coordinate_fractional','band_index',
                'left_occupation','right_occupation','left_eigenvalue_ha','right_eigenvalue_ha')},
            'signed_at_maximum_ha':where[key],
            'definition':'Unweighted RMS across selected k/state rows; first maximum in the left record k/band order'}


def pair(left,right,left_name,right_name,*,align=False,mg_constant=None):
    """Same-density controls are raw only; cross-grid/engine may use one global HOMO."""
    validate_spectrum(left);validate_spectrum(right)
    other=matched_points(left,right)
    rows=[];lh=rh=None;supported=False
    if align:
        lh=global_homo(left);rh=global_homo(other)
        supported=lh['status']==rh['status']=='SUPPORTED'
    for ik,(p,q) in enumerate(zip(left,other),1):
        close(p['weight_spatial'],q['weight_spatial'],1e-10,'Matched spatial weight')
        for ib,(x,y,f,g) in enumerate(zip(p['eigenvalues_ha'],q['eigenvalues_ha'],p['occupations'],q['occupations']),1):
            raw=x-y
            row={'left':left_name,'right':right_name,'k_index':ik,'coordinate_fractional':p['coordinate_fractional'],
                 'band_index':ib,'left_eigenvalue_ha':x,'right_eigenvalue_ha':y,
                 'left_occupation':f,'right_occupation':g,'group':'occupied' if f>=.5 else 'empty',
                 'occupation_classification_matches':(f>=.5)==(g>=.5),
                 'raw_difference_ha':raw,'raw_difference_ev':raw*HARTREE_EV,
                 'raw_difference_mev':raw*HARTREE_EV*1e3,'raw_difference_uev':raw*HARTREE_EV*1e6}
            if align:
                referenced=(x-lh['homo_ha'])-(y-rh['homo_ha']) if supported else None
                row['global_reference_difference_ha']=referenced
                for unit,factor in [('ev',HARTREE_EV),('mev',HARTREE_EV*1e3),('uev',HARTREE_EV*1e6)]:
                    row['global_reference_difference_'+unit]=None if referenced is None else referenced*factor
            if mg_constant is not None:
                row['mg_C_diagnostic_ha']=raw+mg_constant
            rows.append(row)
    summary={}
    for bands in (16,24):
        summary[str(bands)]={}
        for group in ('all','occupied','empty'):
            selected=[row for row in rows if row['band_index']<=bands and (group=='all' or row['group']==group)]
            stats={'raw':statistic(selected,'raw_difference_ha')}
            if align:stats['global_reference']=statistic(selected,'global_reference_difference_ha') if supported else {'status':'UNSUPPORTED'}
            if mg_constant is not None:stats['mg_C_diagnostic']=statistic(selected,'mg_C_diagnostic_ha')
            summary[str(bands)][group]=stats
    return {'status':'REPORTED','left':left_name,'right':right_name,'reference_mode':'RAW_AND_SINGLE_GLOBAL_HOMO' if align else 'RAW_ONLY',
            'global_reference_status':('SUPPORTED' if supported else 'UNSUPPORTED') if align else 'NOT_APPLIED',
            'global_references':{left_name:lh,right_name:rh} if align else None,
            'group_definition':left_name+' f>=0.5; candidate classification agreement is recorded, not silently assumed',
            'mg_C_diagnostic':None if mg_constant is None else {'C_ha':mg_constant,'formula':'raw(left-QE) + C_Mg',
                'scope':'Non-fitted diagnostic only; raw spectra and total energies unchanged; QE internal G0 not extracted'},
            'rows':rows,'summary':summary}


def load_history(root,plan):
    root=Path(root);h=plan['historical_qe'];e_path=root/h['evidence']['path']
    require(h['commit']==plan['base_commit']=='9d49ca88bfe3c4add0e6c80c1376f006d065e306','Wrong reviewed base/history')
    require(digest(e_path)==h['evidence']['sha256'],'Historical QE evidence changed')
    evidence=read(e_path)
    for path,expected in evidence['public_sha256'].items():
        require(digest(root/path)==expected,'Historical public input/data changed: '+path)
    old_case=read(root/evidence['case_config']['path'])
    require(digest(root/evidence['case_config']['path'])==evidence['case_config']['sha256'],'Historical actual case changed')
    # The old loader and endpoint adapter see only their genuine immutable 7A case.
    a,b=load_historical(root,old_case)
    refs={label:historical_record(old_case,item,label) for label,item in [('A',a),('B',b)]}
    records={}
    for label,name,run_id in [('Q36','qe-result.json',evidence['run_id']),
                              ('old_bands','qe-refinement-result.json',evidence['refinement']['run_id'])]:
        path='results/mg-soc-qe-comparison/'+name
        records[label]=read(root/path)
        records[label]['run_id']=run_id
        records[label]['historical_reference']={'status':'HISTORICAL_REUSED','path':path,
            'sha256':evidence['public_sha256'][path],'commit':h['commit'],'run_id':run_id}
        from parse_qe_soc_diagnostics import native_warnings
        prefix='qe' if label=='Q36' else 'qe-refinement'
        records[label]['warning_diagnostics']=native_warnings(
            (root/'results/mg-soc-qe-comparison'/f'{prefix}.stdout').read_text(),
            (root/'results/mg-soc-qe-comparison'/f'{prefix}.stderr').read_text(),0)
    require(records['Q36']['run_id']==h['source_scf_run_id'] and records['old_bands']['run_id']==h['old_bands_run_id'],
            'Historical QE run identities changed')
    return old_case,refs,records,evidence


def validate_plan(plan,old):
    require(plan['case']=='mg-soc-qe-diagnostics-v1' and plan['phase']=='7B','Wrong new diagnostic case')
    for key in ('geometry','electrons','pseudo','xc','cutoffs','kpoints','parsing','comparison','historical','frozen_environment','qe'):
        require(plan[key]==old[key],'Frozen physical/comparison contract changed: '+key)
    require(tuple(plan['execution_order'])==SLOTS and set(plan['slots'])==set(SLOTS),'Unexpected slot matrix')
    require(plan['cross_solver_gate_ha']==1e-7,'Predeclared cross-solver threshold changed')
    for slot,spec in plan['slots'].items():
        grid=36 if slot.endswith('36') else 40
        bands=slot.startswith(('D','C'))
        require(spec['fft_grid']==[grid]*3 and spec['calculation']==('bands' if bands else 'scf'), 'Wrong slot grid/action')
        require(spec['solver']==('cg' if slot.startswith('C') else 'david'),'Wrong slot solver')
        require(spec['diago_thr_init_ry']==(1e-13 if bands else 1e-10),'Wrong prescribed threshold')
        require(spec['source_slot']==(('Q36' if grid==36 else 'G40') if bands else None),'Wrong slot source')
        require(spec['initialization_only']==(slot=='I36'),'Wrong dry-run slot')
        if slot.startswith('C'):require(spec['diago_cg_maxiter']==200,'Wrong CG maximum iterations')
        if slot.startswith('D'):require(spec['diago_david_ndim']==2,'Wrong Davidson workspace')
    require(plan['interpretation']['no_alignment_same_density'] is True
            and plan['interpretation']['no_total_energy_correction'] is True,'Comparison semantics changed')


def validate_record(plan,slot,r):
    finite_tree(r)
    require(r['slot']==slot,'Record assigned to wrong slot')
    if r['execution_status']!='PASS':
        require(r['execution_status'] in ('FAIL','BLOCKED','INCOMPLETE','NOT_RUN'),'Unknown failure status')
        require(bool(r.get('reason')),'Failure needs an explicit reason')
        return False
    require(r['input_contract_status']=='PASS','Input contract not established')
    require(isinstance(r['run_id'],str) and bool(r['run_id']),'Missing independent run identity')
    warning=r['warning_diagnostics']
    require(type(warning['eigenvalues_not_converged']) is bool and isinstance(warning['ieee_flags'],dict),
            'Missing native solver/IEEE warning receipt')
    for name in ('IEEE_INVALID_FLAG','IEEE_DIVIDE_BY_ZERO','IEEE_OVERFLOW_FLAG','IEEE_UNDERFLOW_FLAG','IEEE_INEXACT_FLAG'):
        require(type(warning['ieee_flags'][name]['reported']) is bool,'Missing native IEEE flag status')
    require(r['native_solver_warning_status']==('UNCONVERGED_WARNING' if warning['eigenvalues_not_converged'] else 'NO_UNCONVERGED_WARNING_REPORTED'),
            'Solver-warning status contradicts its native warning receipt')
    if slot=='I36':
        require(r['numerical_solve_status']=='NOT_RUN' and r['energy'] is None and r['scf'] is None and r['kpoints'] is None,
                'Initialization cannot masquerade as a numerical result')
        return True
    require(r['parsed_payload_sha256']==payload_sha256(r),'Canonical payload differs: possible mixed stage/grid/bands')
    require(type(r['exit_code']) is int and r['exit_code']==0,'Numerical process did not exit successfully')
    cfg=plan['slots'][slot]
    require(r['case']==plan['case'] and r['phase']=='7B','Wrong result case')
    require(r['calculation']==cfg['calculation'] and r['version']=='7.5','Wrong final action/version')
    require(r['fft_grid']==r['fft_smooth_grid']==cfg['fft_grid'],'Hard/smooth actual FFT differs from slot')
    require(r['actual_solver']['namelist']==cfg['solver']
            and r['actual_solver']['xml']=={'david':'davidson','cg':'cg'}[cfg['solver']]
            and bool(r['actual_solver']['stdout'])
            and all(s==cfg['solver'] for s in r['actual_solver']['stdout']),'Wrong recorded solver')
    require(r['diagnostic_parameters']['diago_thr_init_ry']==cfg['diago_thr_init_ry'],'Solver threshold/unit differs')
    require(r['electrons']==10 and r['n_bands']==24 and r['occupation_capacity']==1,'Wrong spinor count/capacity')
    require(r['tau_ha']==.001 and r['smearing']=='Fermi-Dirac','Wrong temperature/smearing')
    require(r['pseudo_sha256']==plan['pseudo']['sha256'] and r['z_valence']==10 and r['nlcc'] is False,'Wrong pseudo identity')
    require(r['xc']['functional']=='PBESOL' and r['xc']['indices'][:4]==[1,4,10,8] and not any(r['xc']['indices'][4:]),'Wrong XC')
    require(r['ecut_ha']==15 and r['ecutrho_ha']==60,'Wrong cutoff')
    for key,expected in [('noncolin',True),('spinorbit',True),('do_magnetization',False),('nosym',True),('noinv',True),('no_t_rev',True)]:
        require(r['input_model'][key] is expected,'Wrong actual spin/symmetry condition: '+key)
    require(r['lattice_vectors_bohr']==plan['geometry']['lattice_vectors_bohr'],'Wrong actual lattice')
    for x,y in zip(r['positions_fractional'][0],plan['geometry']['positions_fractional'][0]):close(x,y,1e-9,'Actual Mg position')
    validate_spectrum(r['kpoints'])
    for p,q,npw in zip(plan['kpoints'],matched_points(plan['kpoints'],r['kpoints']),(2777,2770,2770)):
        close(p['weight_spatial'],q['weight_spatial'],1e-10,'Actual spatial weight')
        require(q['npw']==npw,'Actual spatial plane-wave count differs')
    if cfg['calculation']=='bands':
        require(r['energy'] is None and r['scf'] is None and r['energy_semantics_status']=='NOT_APPLICABLE_SPECTRUM_ONLY',
                'Bands cannot supply SCF energies')
        bind=r['source_binding']
        require(bind['status']=='PASS' and bind['source_slot']==cfg['source_slot'] and bind['source_preservation_status']=='PASS',
                'Fixed-density source was not established/preserved')
        for key in ('source_snapshot_sha256','charge_before_sha256','charge_after_sha256'):
            require(isinstance(bind[key],str) and len(bind[key])==64,'Missing actual save hash: '+key)
        require(bind['charge_before_sha256']==bind['charge_after_sha256'],'Copied charge bytes changed')
        require(isinstance(bind['initial_wfc_sha256'],dict) and len(bind['initial_wfc_sha256'])>=3
                and all(isinstance(x,str) and len(x)==64 for x in bind['initial_wfc_sha256'].values()),
                'Missing independent initial wavefunction snapshot')
        start=r['read_start_evidence']
        require(start['status']=='PASS' and bool(start['potential_from_file']) and bool(start['wavefunctions_from_file'])
                and bool(start['band_structure_lines']) and not start['fallback_lines'] and not start['scf_iteration_lines'],
                'Bands did not establish the required file-start/no-SCF path')
    else:
        require(r['scf']['converged'] is True and r['energy_semantics_status']=='PASS','SCF not converged/energy unknown')
        qe_energy(r)
    return True


def qe_energy(r):
    require(r['calculation']=='scf' and r['energy'] is not None,'SCF energy required; bands energy never used')
    e=r['energy']
    for key in ('native_etot_ha','native_demet_ha'):finite_number(e[key],key)
    return energy_record(e['internal_ha'],e['free_ha'],e['entropy_ha'],source=e['sources'],
                         native_free=e['native_etot_ha'],native_entropy=e['native_demet_ha'])


def energy_pair(left,right):
    result={'energy':{key:delta(left['energy'][key+'_ha']-right['energy'][key+'_ha']) for key in ('internal','free','entropy')},
            'same_definition_terms':{key:delta(left['terms'][key]-right['terms'][key]) for key in ('Hartree','Xc','Ewald')},
            'scope':'Each engine own reported final density; only Hartree/XC/Ewald definitions mapped. No density-array validation.'}
    finite_tree(result);return result


def energies(refs,data):
    records={label:{'energy':r['energy'],'terms':r['energy_terms_ha'],'status':'HISTORICAL_REUSED'} for label,r in refs.items()}
    for label in ('Q36','G40'):
        if label not in data:continue
        r=data[label];native=r['energy']['native_components_ha']
        records[label]={'energy':qe_energy(r),'terms':{k:native[v] for k,v in [('Hartree','ehart'),('Xc','etxc'),('Ewald','ewald')]},
                        'native_stdout_tokens_precision':r['native_stdout'],'native_components_ha':native,
                        'status':'HISTORICAL_REUSED' if label=='Q36' else 'NEW_SCF_MEASUREMENT'}
    result={'records':records,'total_energy_correction_applied':False,'units':'Ha/cell; one atom per cell',
            'zero_entropy_scope':'Native displayed zero is preserved with printed precision, not claimed mathematically exact'}
    for label in ('A','B'):
        for q in ('Q36','G40'):
            result[label+'_minus_'+q]=energy_pair(records[label],records[q]) if q in records else {'status':'BLOCKED'}
    if 'G40' in records:
        result['G40_minus_Q36']=energy_pair(records['G40'],records['Q36'])
        algebra={}
        for label in ('A','B'):
            algebra[label]={}
            for key in ('internal','free'):
                residual=result[label+'_minus_G40']['energy'][key]['signed_ha']-result[label+'_minus_Q36']['energy'][key]['signed_ha']+result['G40_minus_Q36']['energy'][key]['signed_ha']
                close(residual,0,1e-10,'Grid/cross-code energy arithmetic')
                algebra[label][key+'_residual_ha']=residual
        result['grid_cross_difference_algebra']=algebra
    else:
        result['G40_minus_Q36']={'status':'BLOCKED'};result['grid_cross_difference_algebra']={'status':'BLOCKED'}
    return result


def source_pairs(records,data):
    for grid in ('36','40'):
        source='Q36' if grid=='36' else 'G40'
        names=['D'+grid,'C'+grid]
        for name in names:
            if name not in data:continue
            require(source in data,'Bands cannot outlive failed source SCF')
            require(data[name]['source_binding']['source_run_id']==data[source]['run_id'],'Bands source run differs')
        if not all(name in data for name in names):continue
        a,b=[records[n]['source_binding'] for n in names]
        for key in ('source_slot','source_run_id','source_snapshot_sha256','charge_before_sha256','initial_wfc_sha256'):
            require(a[key]==b[key],'D/C did not start from identical source '+key)


def blocked_pair(left,right):return {'status':'BLOCKED','left':left,'right':right,'reason':'Required valid numerical record unavailable'}


def analyze(root,plan,records):
    finite_tree([plan,records])
    old,refs,history,evidence=load_history(root,plan);validate_plan(plan,old)
    require(set(records)==set(SLOTS),'All six slots, including failures, must be explicitly recorded')
    valid={slot:validate_record(plan,slot,records[slot]) for slot in SLOTS}
    data=dict(history)
    for slot in NUMERIC:
        if valid[slot]:data[slot]=records[slot]
    ids=[r['run_id'] for r in data.values()]
    require(len(ids)==len(set(ids)),'New slot reused another run identity')
    source_pairs(records,data)
    tables={}
    controls=[('D36','Q36',False),('C36','Q36',False),('D36','C36',False),
              ('D36','old_bands',False),('C36','old_bands',False),('D40','G40',False),
              ('C40','G40',False),('D40','C40',False),('D40','D36',True),('C40','C36',True)]
    for left,right,align in controls:
        tables[left+'_minus_'+right]=pair(data[left]['kpoints'],data[right]['kpoints'],left,right,align=align) if left in data and right in data else blocked_pair(left,right)
    for label,r in refs.items():
        for slot in CROSS_TARGETS:
            tables[label+'_minus_'+slot]=pair(r['kpoints'],data[slot]['kpoints'],label,slot,align=True,
                mg_constant=r['energy_terms_ha']['PspCorrection']/10) if slot in data else blocked_pair(label,slot)
    stability={}
    for grid in ('36','40'):
        table=tables['D'+grid+'_minus_C'+grid]
        no_warning=all(name in data and not records[name]['warning_diagnostics']['eigenvalues_not_converged'] for name in ('D'+grid,'C'+grid))
        maximum=table['summary']['24']['all']['raw']['max_abs_ha'] if table['status']=='REPORTED' else None
        if maximum is not None:finite_number(maximum,'D/C maximum')
        observed=maximum is not None and maximum<=plan['cross_solver_gate_ha'] and no_warning
        stability[grid]={'status':'CROSS_SOLVER_STABILITY_OBSERVED' if observed else 'NOT_ESTABLISHED',
            'max_abs_ha':maximum,'gate_ha':plan['cross_solver_gate_ha'],'no_unconverged_warning':no_warning,
            'scope':'Same density/software/operator sensitivity only; not a per-state residual or independent physics certificate'}
    return {'schema_version':1,'case':plan['case'],'base_commit':plan['base_commit'],
            'comparison_execution_status':'COMPLETED' if all(valid.values()) else 'COMPLETED_WITH_UNAVAILABLE_SLOTS',
            'slots':{slot:{key:r.get(key) for key in ('execution_status','run_id','input_contract_status','reason','source_binding','native_solver_warning_status')}
                     for slot,r in records.items()},
            'spectra':tables,'energy':energies(refs,data),'cross_solver_stability':stability,
            'historical_references':{**{label:r['source'] for label,r in refs.items()},
                                     **{label:r['historical_reference'] for label,r in history.items()}},
            'numerical_agreement_status':'REVIEW_REQUIRED','physical_convergence_status':'NOT_ESTABLISHED',
            'warning_origin_status':'NOT_LOCALIZED','residual_attribution_status':'NOT_ESTABLISHED',
            'residual_certificate_status':'NOT_AVAILABLE',
            'warning_diagnostics':{slot:r.get('warning_diagnostics') for slot,r in {**history,**records}.items()},
            'array_dependent_claims':'Density/wavefunction byte binding is runner-reported and native-reparse checked separately; public arrays are not revalidated',
            'limitations':['D/C shares QE potentials/operators and cannot establish independent physical agreement',
                'G40-Q36 includes FFT change and self-consistent density response; no full convergence or isolated quadrature attribution',
                'Matching plane-wave counts does not establish G-vector order equality',
                'No best-spectrum assembly, energy shift or per-k reference fitting']}


def write_csv(path,result):
    rows=[{'pair':name,**row} for name,p in result['spectra'].items() for row in p.get('rows',[])]
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');writer.writeheader()
        for row in rows:
            row=dict(row,coordinate_fractional=json.dumps(row['coordinate_fractional'],separators=(',',':')))
            writer.writerow(row)


def summary(result):
    result=copy.deepcopy(result)
    for item in result['spectra'].values():item.pop('rows',None)
    return result


def write_differences_csv(path,result):
    write_csv(path,result)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--plan',type=Path,default=Path('benchmarks/mg-soc-qe-diagnostics-v1/plan.json'))
    parser.add_argument('--records',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--csv',type=Path)
    args=parser.parse_args()
    try:
        result=analyze(args.root,read(args.root/args.plan),read(args.records))
        if args.csv:write_csv(args.csv,result)
    except (ValueError,KeyError,TypeError,OSError) as error:
        result={'comparison_execution_status':'FAIL','numerical_agreement_status':'REVIEW_REQUIRED','reason':str(error)}
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    return 1 if result['comparison_execution_status']=='FAIL' else 0


if __name__=='__main__':raise SystemExit(main())
