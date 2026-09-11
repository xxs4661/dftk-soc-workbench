#!/usr/bin/env python3
"""Signed fixed-orbital ledger continuation; no energy operator is built here.

P2 is the already recorded pp reconstruction. Its token-specific intervals are
propagated after combining shared coefficients. Old E/F and O are immutable.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
PLAN='benchmarks/mg-soc-wavefunction-energy-v1/plan.json'
SOURCES={
    'ledger':'results/mg-soc-energy-reference/ledger.json',
    'previous':'results/mg-soc-qe-local-potential/saved-field-receipt.json',
    'density':'results/mg-soc-density-hartree/qe-rho.csv.gz',
    'P2':'results/mg-soc-qe-local-potential/P2/local-ionic.pp.gz',
    'local_plan':'benchmarks/mg-soc-qe-local-potential-v1/plan.json',
}
Q_NL_KIND='DFTK_FROZEN_FR_NONLOCAL_EXPECTATION_ON_QE_G40_ORBITALS'
AB_NL_KIND='DFTK_FROZEN_FR_NONLOCAL_EXPECTATION_ON_ORIGINAL_DFTK_ORBITALS'
LEDGER_NL_KIND='DERIVED_NL_SHAPED_REMAINDER_NOT_DIRECT_QE_NL'


def require(condition,reason):
    if not condition:raise ValueError(reason)


def finite(value,label):
    require(type(value) in (int,float) and math.isfinite(value),'Nonfinite or invalid '+label)
    return float(value)


def close(a,b,tolerance,label):
    difference=finite(a,label)-finite(b,label)
    require(abs(difference)<=tolerance,label+' exceeds declared tolerance')
    return difference


def _fsum(values):return math.fsum(np.asarray(values).reshape(-1).tolist())


def _field(value,count,label):
    require(isinstance(value,np.ndarray) and value.dtype==np.dtype('float64')
            and value.shape==(count,) and np.isfinite(value).all(),'Invalid '+label+' physical node array')
    return value


def correlated_print_bound(coefficients,uV,dvol,*,O_coefficient=0.,O_halfwidth=0.):
    """Shared P2/O coefficients must be combined before calling this function."""
    require(np.shape(coefficients)==np.shape(uV),'Print-bound field shape mismatch')
    require(np.isfinite(coefficients).all() and np.isfinite(uV).all() and np.all(uV>=0),'Invalid P2 print interval')
    require(math.isfinite(dvol) and dvol>0 and math.isfinite(O_coefficient)
            and math.isfinite(O_halfwidth) and O_halfwidth>=0,'Invalid print-bound units or O interval')
    return dvol*_fsum(np.abs(coefficients)*uV)+abs(O_coefficient)*O_halfwidth


def _gate_inputs(reports,nonlocal_result,thresholds):
    require(set(reports)=={'A','B','Q'},'Exactly original A, B and Q reports are required')
    require(nonlocal_result['execution_status']=='PASS','Frozen nonlocal execution did not pass')
    require(set(nonlocal_result['states'])=={'A','B','Q'},'Wrong nonlocal state set')
    for label,r in reports.items():
        require(r['label']==label and r['status']=='PASS' and r['all_required_gates_passed'] is True,
                'Orbital source gate failed for '+label)
        require(r['same_source_orbital_density']['status']=='PASS' and r['electrons']['status']=='PASS'
                and r['kinetic']['status']=='PASS','Density/electron/kinetic gate failed for '+label)
        require(r['input_bytes_unchanged'] is True and r['normalization_or_QR_applied'] is False,'Altered original orbitals')
        require(len(r['normalization_and_gram'])>0 and len(r['direct_correlation_checks'])==17
                and all(k['status']=='PASS' for k in r['normalization_and_gram'])
                and all(k['status']=='PASS' for k in r['direct_correlation_checks']),'Incomplete original-state gate')
        expected='DIRECT_REEVALUATION_OF_KINETIC_FROM_ORIGINAL_QE_WFC' if label=='Q' else 'DIRECT_REEVALUATION_OF_KINETIC_FROM_ORIGINAL_DFTK_X'
        require(r['kinetic']['evidence_kind']==expected,'Direct T has an unsupported provenance label')
        n=nonlocal_result['states'][label]
        require(n['status']=='PASS' and n['quantity']==(Q_NL_KIND if label=='Q' else AB_NL_KIND),'Wrong nonlocal source or quantity label')
        tol=thresholds['nonlocal_contraction_abs_ha']
        close(n['energy_action_ha'],n['energy_projected_ha'],tol,'NL action/projection '+label)
        close(n['energy_action_ha'],n['energy_spin_sum_ha'],tol,'NL full spin contraction '+label)
        if label!='Q':require(r['kinetic']['same_source_status']=='PASS','Historical T recovery failed')


def compare_arrays(reports,nonlocal_result,n_wfc,n_saved,potential,uV,*,volume_bohr3,
                   expected_electrons,ledger,previous,thresholds):
    """Small pure synthetic-testable core; caller certifies original file hashes."""
    _gate_inputs(reports,nonlocal_result,thresholds)
    require(ledger['historical_energy_ledger_status']=='PASS' and ledger['source_binding_status']=='PASS','Unaccepted old energy ledger')
    require(previous['execution_status']=='PASS' and previous['source_preservation_status']=='PASS','Unaccepted old P2 field receipt')
    before=json.dumps([ledger,previous],sort_keys=True,allow_nan=False)
    count=len(n_wfc);require(count>0,'Empty local grid')
    nw=_field(n_wfc,count,'Q orbital density');ns=_field(n_saved,count,'Q saved finite density')
    v=_field(potential,count,'already Ha P2 potential');uv=_field(uV,count,'Ha token halfwidth')
    require(np.all(uv>=0),'Negative P2 print halfwidth')
    volume=finite(volume_bohr3,'volume');require(volume>0,'Nonpositive volume')
    dvol=volume/count;tol=thresholds['ledger_abs_ha']
    fingerprints={key:hashlib.sha256(a.tobytes()).hexdigest() for key,a in [('n_wfc',nw),('n_saved',ns),('V_Qpp',v),('uV',uv)]}
    ne_w=dvol*_fsum(nw);ne_s=dvol*_fsum(ns)
    close(ne_w,expected_electrons,thresholds['electron_count_abs'],'Q orbital local-integral electrons')
    close(ne_s,expected_electrons,thresholds['electron_count_abs'],'Saved Q local-integral electrons')
    close(ne_w,reports['Q']['electrons']['from_real_density'],thresholds['electron_count_abs'],'Q report/node density ownership')
    Lw=dvol*_fsum(nw*v);Ls=dvol*_fsum(ns*v)
    # Evaluate the difference directly on the shared potential, retaining its
    # smaller correlated print coefficient instead of adding two error bars.
    delta_L=dvol*_fsum((ns-nw)*v)
    delta_subtraction_drift=close(delta_L,Ls-Lw,tol,'Shared-potential local state difference')
    Lold=finite(previous['original_pointwise_integrals_ha']['L_Qpp_Q'],'historical L_saved')
    replay_drift=Ls-Lold
    close(Ls,Lold,tol,'Frozen P2/saved-density local integral replay')
    q=ledger['native_values']['G40'];Oq=finite(q['O'],'historical O_Q')
    O_fsum=math.fsum([q['E'],-q['H'],-q['XC'],-q['Ew']])
    O_source_grouping_drift=close(Oq,O_fsum,tol,'Retained historical O source grouping')
    widths={r['id']:finite(r['quantization_half_width_ha'],'token halfwidth') for r in ledger['field_dictionary']
            if 'quantization_half_width_ha' in r}
    token_ids=['G40.'+key for key in ('etot','demet','ehart','etxc','ewald')]
    require(all(widths[key]>=0 for key in token_ids),'Negative historical O token interval')
    uO=math.fsum(widths[key] for key in token_ids)
    bounds={
        'L_wfc':correlated_print_bound(nw,uv,dvol),
        'L_saved':correlated_print_bound(ns,uv,dvol),
        'delta_L_state':correlated_print_bound(ns-nw,uv,dvol),
        'J_Q':correlated_print_bound(nw,uv,dvol,O_coefficient=-1.,O_halfwidth=uO),
        'NL_Q_ledger':correlated_print_bound(-nw,uv,dvol,O_coefficient=1.,O_halfwidth=uO),
        'J_plus_delta_L':correlated_print_bound(ns,uv,dvol,O_coefficient=-1.,O_halfwidth=uO),
        'recomposed_R':correlated_print_bound(ns,uv,dvol,O_coefficient=-1.,O_halfwidth=uO),
        'J_plus_NL_Q_ledger':correlated_print_bound(np.zeros(count),uv,dvol),
    }
    Tq=finite(reports['Q']['kinetic']['direct_ha'],'Q direct T')
    Nq=finite(nonlocal_result['states']['Q']['energy_action_ha'],'workbench NL on Q')
    Kq=math.fsum([Tq,Nq]);J=math.fsum([Kq,Lw,-Oq])
    NLledger=math.fsum([Oq,-Lw,-Tq])
    complementary=close(J+NLledger,Nq,tol,'J plus NL-shaped ledger remainder')
    rows={}
    for label in ('A','B'):
        terms=ledger['native_values'][label]['terms'];Ts=finite(reports[label]['kinetic']['direct_ha'],label+' direct T')
        Ns=finite(nonlocal_result['states'][label]['energy_action_ha'],label+' direct NL')
        histT=finite(terms['Kinetic'],label+' historical T');histN=finite(terms['AtomicNonlocalFR'],label+' historical NL')
        dT=close(Ts,histT,thresholds['kinetic_history_abs_ha'],label+' same-source T')
        dN=close(Ns,histN,thresholds['historical_nonlocal_abs_ha'],label+' same-source NL')
        Khist=math.fsum([histT,histN]);Knew=math.fsum([Ts,Ns]);drift=Knew-Khist
        response=Knew-Kq
        old=previous['original_comparisons'][label+'_minus_G40'];Rold=finite(old['R_after_local_ha'],'exact old R')
        # Old O_D was grouped differently from K_hist+L_hist+Pc. This explicit
        # machine-arithmetic difference is preserved, never assigned to NL.
        hist_formula=math.fsum([Khist,-Oq,Lold]);old_O_grouping=Rold-hist_formula
        close(old_O_grouping,0.,tol,'Historical O-combination grouping '+label)
        recomposed=math.fsum([response,J,delta_L,-drift,old_O_grouping,-replay_drift])
        closure=close(recomposed,Rold,tol,'Signed historical remainder closure '+label)
        old_from_7D=ledger['comparisons'][label+'_minus_G40']['delta_ha']['O']-(terms['AtomicLocal']+terms['PspCorrection']-Lold)
        close(Rold,old_from_7D,tol,'Old 7D/7E definition '+label)
        old_u=old['uncertainty']['u_R_after_local_print_ha']
        close(old_u,bounds['recomposed_R'],tol,'Old R correlated print interval replay '+label)
        rows[label]={
            'reference_role':'primary' if label=='A' else 'auxiliary',
            'T_direct_ha':Ts,'N_D_ha':Ns,'T_historical_ha':histT,'N_D_historical_ha':histN,
            'T_same_source_signed_difference_ha':dT,'N_D_same_source_signed_difference_ha':dN,
            'Delta_T_S_minus_Q_ha':Ts-Tq,'Delta_N_D_S_minus_Q_ha':Ns-Nq,
            'K_hist_ha':Khist,'K_new_ha':Knew,'K_Q_in_D_ha':Kq,
            'S_response_ha':response,'J_Q_ha':J,'delta_L_state_ha':delta_L,'drift_S_ha':drift,
            'R_old_ha':Rold,'historical_K_minus_O_plus_L_ha':hist_formula,
            'historical_O_combination_drift_ha':old_O_grouping,'saved_local_replay_drift_ha':replay_drift,
            'recomposed_R_ha':recomposed,'signed_closure_error_ha':closure,
            'original_R_print_halfwidth_ha':old_u,'recomposed_R_print_halfwidth_ha':bounds['recomposed_R'],
            'status':'PASS_ALGEBRA','response_scope':'Same T plus workbench FR operator on different original orbitals AND occupations',
            'causal_attribution_status':'NOT_ESTABLISHED',
        }
    require(json.dumps([ledger,previous],sort_keys=True,allow_nan=False)==before,'Historical E/F or source ledger mutated')
    require(fingerprints=={key:hashlib.sha256(a.tobytes()).hexdigest() for key,a in [('n_wfc',nw),('n_saved',ns),('V_Qpp',v),('uV',uv)]},'Local-integral input arrays mutated')
    result={
        'schema_version':1,'case':'mg-soc-wavefunction-energy-v1','status':'PASS_LIMITED_STATIC_AUDIT',
        'local_state_integral_status':'PASS','signed_combination_replay_status':'PASS',
        'signed_combination_evidence_tier':'ALGEBRA_WITH_EXPLICIT_SOURCE_AND_PRINT_LIMITATIONS',
        'units':'Ha/cell; node density electron/bohr^3; volume bohr^3','volume_bohr3':volume,'node_count':count,'dvol_bohr3':dvol,
        'local_state':{'L_saved_historical_ha':Lold,'L_saved_replayed_ha':Ls,'L_wfc_ha':Lw,'delta_L_state_ha':delta_L,
            'delta_L_direct_minus_subtraction_ha':delta_subtraction_drift,'saved_local_replay_drift_ha':replay_drift,
            'N_saved':ne_s,'N_wfc':ne_w,'potential_unit':'Ha','potential_rescaled':False,
            'density_scope':'Full finite orbital density versus the explicitly saved finite Q charge series; unsaved physical modes are not assumed zero',
            'field_fingerprints':fingerprints},
        'Q':{'T_direct_ha':Tq,'T_quantity':'DIRECT_REEVALUATION_OF_KINETIC_FROM_ORIGINAL_QE_WFC',
            'N_D_ha':Nq,'N_D_quantity':Q_NL_KIND,'K_Q_in_D_ha':Kq,
            'O_historical_ha':Oq,'O_reduction_grouping_drift_ha':O_source_grouping_drift,
            'NL_Q_ledger_ha':NLledger,'NL_Q_ledger_quantity':LEDGER_NL_KIND,'J_Q_ha':J,
            'J_plus_NL_ledger_minus_N_D_ha':complementary,
            'J_scope':'Cross-source diagnostic sum, not a mixed Hamiltonian ground-state energy or localization of a SOC error'},
        'comparisons':rows,
        'printing':{'bound_kind':'TOKEN_QUANTIZATION_ONLY_NOT_PHYSICAL_ERROR_OR_STATISTICAL_SIGNIFICANCE',
            'O_token_halfwidths_ha':{key:widths[key] for key in token_ids},'O_halfwidth_ha':uO,'halfwidths_ha':bounds,
            'shared_coefficients':{'L_wfc':'n_wfc','L_saved':'n_saved','delta_L_state':'n_saved - n_wfc',
                'J_Q':'P2: n_wfc; O: -1','NL_Q_ledger':'P2: -n_wfc; O: +1',
                'J_plus_delta_L':'P2: n_saved; O: -1','J_plus_NL_Q_ledger':'P2: 0; O: 0',
                'recomposed_R':'P2: n_saved; O: -1; stored replay/grouping drifts remain explicit'},
            'formula':'dvol * sum(abs(combined node coefficient) * per-token uV) + abs(combined O coefficient) * uO',
            'binary_orbital_record_precision':'Exact recorded Float64 values; no invented binary quantization/physical-error interval',
            'unmodelled_errors':['original SCF/eigensolver','P2 reconstruction','workbench versus QE nonlocal implementation','unknown original H[n_in] residual']},
        'recomposition_formula':'R_old = S_response + J_Q + delta_L_state - drift_S + historical_O_combination_drift - saved_local_replay_drift',
        'native_E_F_modified':False,'energy_correction_applied':False,
        'historical_E_F_ha':{label:{name:ledger['native_values'][label][name] for name in ('E','F')} for label in ('A','B','G40')},
        'independent_native_qe_nonlocal_status':'NOT_MEASURED','qe_original_input_hamiltonian_residual_status':'NOT_AVAILABLE',
        'new_scf_status':'NOT_RUN','new_eigensolve_status':'NOT_RUN','new_occupation_solve_status':'NOT_RUN',
        'new_qe_pp_execution_status':'NOT_RUN','new_xc_evaluation_status':'NOT_RUN',
        'physical_convergence_status':'NOT_ESTABLISHED','ieee_warning_origin_status':'NOT_LOCALIZED','numerical_review_status':'REVIEW_REQUIRED',
    }
    validate_result(result,thresholds)
    return result


def validate_result(result,thresholds):
    """Public protocol and small scalar identities; field integrals need replay."""
    require(result['status']=='PASS_LIMITED_STATIC_AUDIT' and result['local_state_integral_status']=='PASS'
            and result['signed_combination_replay_status']=='PASS'
            and result['signed_combination_evidence_tier']=='ALGEBRA_WITH_EXPLICIT_SOURCE_AND_PRINT_LIMITATIONS','Incomplete comparison stages')
    require(result['Q']['N_D_quantity']==Q_NL_KIND and result['Q']['NL_Q_ledger_quantity']==LEDGER_NL_KIND,'Nonlocal measurement provenance was overstated')
    require(result['Q']['T_quantity']=='DIRECT_REEVALUATION_OF_KINETIC_FROM_ORIGINAL_QE_WFC','Q T is not a native printed field')
    for key,value in {'independent_native_qe_nonlocal_status':'NOT_MEASURED',
        'qe_original_input_hamiltonian_residual_status':'NOT_AVAILABLE','physical_convergence_status':'NOT_ESTABLISHED',
        'numerical_review_status':'REVIEW_REQUIRED','ieee_warning_origin_status':'NOT_LOCALIZED'}.items():
        require(result[key]==value,'Unsupported claim for '+key)
    require(result['native_E_F_modified'] is False and result['energy_correction_applied'] is False,'Historical energy correction forbidden')
    for key in ('new_scf_status','new_eigensolve_status','new_occupation_solve_status','new_qe_pp_execution_status','new_xc_evaluation_status'):
        require(result[key]=='NOT_RUN','Unpermitted new physics claim '+key)
    tol=thresholds['ledger_abs_ha']
    q=result['Q'];local=result['local_state']
    close(q['K_Q_in_D_ha'],q['T_direct_ha']+q['N_D_ha'],tol,'Q common evaluator sum')
    close(q['J_Q_ha'],math.fsum([q['K_Q_in_D_ha'],local['L_wfc_ha'],-q['O_historical_ha']]),tol,'J cross-source formula')
    close(q['NL_Q_ledger_ha'],math.fsum([q['O_historical_ha'],-local['L_wfc_ha'],-q['T_direct_ha']]),tol,'Derived NL-shaped formula')
    for row in result['comparisons'].values():
        close(row['K_new_ha'],row['T_direct_ha']+row['N_D_ha'],tol,'Reference evaluator sum')
        close(row['K_hist_ha'],row['T_historical_ha']+row['N_D_historical_ha'],tol,'Reference historical sum')
        close(row['S_response_ha'],row['K_new_ha']-q['K_Q_in_D_ha'],tol,'Common-evaluator response')
        close(row['drift_S_ha'],row['K_new_ha']-row['K_hist_ha'],tol,'Same-source drift')
        close(row['J_Q_ha'],q['J_Q_ha'],tol,'Shared J ownership')
        close(row['delta_L_state_ha'],local['delta_L_state_ha'],tol,'Shared local state ownership')
        recomposed=math.fsum([row['S_response_ha'],row['J_Q_ha'],row['delta_L_state_ha'],-row['drift_S_ha'],
                             row['historical_O_combination_drift_ha'],-row['saved_local_replay_drift_ha']])
        close(recomposed,row['R_old_ha'],tol,'Public signed remainder closure')
        close(row['recomposed_R_ha'],recomposed,tol,'Reported recomposition')
    return True


def evaluate_comparison(reports,nonlocal_result,n_wfc,root=ROOT):
    """Bound public history + new gate-approved orbitals; no new physics call."""
    from compare_density_hartree import read_coefficients_gzip
    from replay_qe_local_fields import coefficients_to_field
    from parse_qe_filplot import parse_qe_filplot
    root=Path(root);plan=json.loads((root/PLAN).read_text());bound={}
    for name,path in SOURCES.items():
        digest=hashlib.sha256((root/path).read_bytes()).hexdigest()
        require(digest==plan['source_sha256'][path],'Frozen comparison source hash mismatch: '+path)
        bound[path]=digest
    ledger=json.loads((root/SOURCES['ledger']).read_text());previous=json.loads((root/SOURCES['previous']).read_text())
    local_plan=json.loads((root/SOURCES['local_plan']).read_text())
    q=read_coefficients_gzip(root/SOURCES['density']);require(set(q)=={'QE'},'Wrong original saved Q density columns')
    saved,_,fft_report=coefficients_to_field(q['QE'],plan['physical']['fft_size'],complete=False,tolerance=local_plan['thresholds']['fft_normalized'])
    parsed=parse_qe_filplot(root/SOURCES['P2'],expected_plot_num=2,expected=dict(local_plan['filplot_expected'],unit='Ha'))
    require(parsed['parse_status']=='PASS' and parsed['expected_validation_status']=='PASS' and parsed['unit']=='Ha','Unaccepted frozen P2')
    require(parsed['grid']==plan['physical']['fft_size'],'P2 grid mismatch')
    result=compare_arrays(reports,nonlocal_result,n_wfc,np.asarray(saved,np.float64),np.asarray(parsed['values'],np.float64),
        np.asarray(parsed['halfwidths'],np.float64),volume_bohr3=plan['physical']['volume_bohr3'],
        expected_electrons=plan['physical']['expected_electrons'],ledger=ledger,previous=previous,thresholds=plan['thresholds'])
    result['source_sha256']=bound;result['saved_density_reconstruction']=fft_report
    result['P2_source']={key:parsed[key] for key in ('source_sha256','stored_sha256','unit','native_unit','unit_scale','physical_count','parse_status','expected_validation_status')}
    return result
