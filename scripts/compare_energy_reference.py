#!/usr/bin/env python3
"""Replay saved scalar tables/algebra; does not independently execute XC/field integrals."""
import math
from run_density_hartree_audit import require


def close(a,b,tol,reason):
    require(type(a) in (int,float) and type(b) in (int,float) and math.isfinite(a) and math.isfinite(b), 'Nonfinite '+reason)
    require(abs(a-b)<=tol,reason)
    return a-b


def split_response(a,q,historical,first_order=None):
    response=a-q;residual=q-historical;total=a-historical
    record=dict(historical_difference_ha=total,density_response_in_D_ha=response,
                evaluation_residual_at_Q_rep_ha=residual,recombination_error_ha=total-response-residual)
    if first_order is not None:
        record.update(first_order_at_Q_ha=first_order,curvature_remainder_ha=response-first_order)
    return record


def compare_saved(ledger,common,radial,plan):
    t=plan['thresholds'];tol=t['ledger_abs_ha']
    require(ledger['source_binding_status']=='PASS' and ledger['historical_energy_ledger_status']=='PASS','Unaccepted historical ledger')
    require(set(common['reconstruction'])=={'A','B','Q'} and set(common['original_sources'])=={'A','B'},'Missing representation/original checks')
    require(set(common['same_source'])=={'A_original_n_out','B_original_n_out','A_reconstructed','B_reconstructed'},'Missing same-source checks')
    require(set(common['responses'])=={'A','B'},'Missing density responses')
    require(common['execution_status']=='PASS' and common['exit_code']==0 and common['xc_calls_completed']==5,'Incomplete fixed-density matrix')
    require(common['environment']['status']=='PASS' and common['environment_recheck_status']=='PASS','Environment identity not accepted')
    require(common['source_binding_status']=='PASS' and common['source_unchanged_status']=='PASS','Source binding/preservation failed')
    expected={'A_original_n_out','B_original_n_out','Q_rep','A_reconstructed','B_reconstructed'}
    require(set(common['evaluations'])==expected,'Wrong density evaluation matrix')
    for name,rep in common['reconstruction'].items():
        require(rep['status']=='PASS' and rep['source_support_preserved'] and rep['unsaved_physical_modes']=='NOT_ESTABLISHED_ZERO','Unsupported or mislabelled representation')
        require(rep['source_support_count']==(22119 if name=='Q' else 64000) and rep['native_workspace_count']==64000,'Changed source support')
        close(rep['imaginary_max'],0,t['density_imaginary_abs'],'Substantive imaginary reconstruction')
        close(rep['fourier_roundtrip_relative_l2'],0,t['fourier_roundtrip_relative_l2'],'Fourier roundtrip')
        require(len(rep['directional_checks'])==17 and len({tuple(p['miller']) for p in rep['directional_checks']})==17,'Missing directional checks')
        for point in rep['directional_checks']:
            close(point['absolute_error'],0,t['fourier_directional_abs'],'Directional Fourier phase check')
    for name,source in common['original_sources'].items():
        d=source['same_source_reconstruction']
        require(source['status']=='PASS' and d['status']=='PASS','Missing original array binding')
        close(d['relative_l2'],0,t['density_reconstruction_relative_l2'],'Original density L2 reconstruction')
        close(d['max_abs'],0,t['density_reconstruction_max_abs'],'Original density max reconstruction')
    for name,ev in common['evaluations'].items():
        require(ev['status']=='PASS' and ev['xc_call_count']==1,'Incomplete evaluation')
        d=ev['density']; require(d['status']=='PASS' and not d['clipping_applied'] and not d['normalization_applied'],'Altered input density')
        close(d['electron_count'],10,t['electron_count_abs'],'Electron count')
        require(d['minimum']>=-d['negative_roundoff_bound'],'Unsupported negative density')
        require(ev['backend']['full_gga_potential'] and not ev['backend']['generic_dftfunctionals_evaluation_used'],'Wrong full GGA backend')
        require([x['identifier'] for x in ev['backend']['functionals']]==plan['physical']['functionals'],'Wrong functional')
        require(all(x['backend']=='Libxc Float64 CPU' for x in ev['backend']['functionals']),'Wrong actual dispatch report')
        close(ev['local_integral_ha'],ev['atomic_local_ha'],t['local_parseval_abs_ha'],'Local integral/energy disagreement')
    for name,check in common['same_source'].items():
        require(check['status']=='PASS','Failed same-source terms')
        require(len(check['rows'])==5 and {row['field'] for row in check['rows']}=={'atomic_local_ha','xc_ha','integral_n_vxc_ha','psp_correction_ha','ewald_ha'},'Incomplete same-source terms')
        for row in check['rows']:
            field=row['field'];label=name[0];hist=ledger['native_values'][label]
            actual=common['constants'][field] if field in ('psp_correction_ha','ewald_ha') else common['evaluations'][name][field]
            historical=hist['Ixc'] if field=='integral_n_vxc_ha' else hist['terms'][{'atomic_local_ha':'AtomicLocal','xc_ha':'Xc','psp_correction_ha':'PspCorrection','ewald_ha':'Ewald'}[field]]
            require(row['actual']==actual and row['historical']==historical,'Same-source row detached from evaluation/history')
            threshold=t['same_source_constants_abs_ha'] if row['field'] in ('psp_correction_ha','ewald_ha') else t['same_source_common_abs_ha']
            close(row['actual'],row['historical'],threshold,'Same-source '+name+'/'+row['field'])
            close(row['actual']-row['historical'],row['signed_difference_ha'],tol,'Same-source signed subtraction')
    const=common['constants']
    require(const['model_ne']==const['n_electrons_from_atoms_actual']==10 and const['natoms']==1 and const['volume_bohr3']==1000,'Changed correction model')
    close(const['psp_correction_ha'],const['alpha_from_common_native']*const['natoms']*const['model_ne']/const['volume_bohr3'],t['same_source_constants_abs_ha'],'Pc atom/electron/volume factors')
    close(const['psp_local_fourier_G0'],0,t['synthetic_normalized'],'Native local G0')
    q=common['evaluations']['Q_rep'];comparisons={}
    for label in ('A','B'):
        a=common['evaluations'][label+'_original_n_out'];h=ledger['native_values']['G40'];response=common['responses'][label]
        require(response['status']=='PASS','Failed density response identity')
        xc=split_response(a['xc_ha'],q['xc_ha'],h['XC'],response['xc_first_order_at_Q_ha'])
        ixc=split_response(a['integral_n_vxc_ha'],q['integral_n_vxc_ha'],h['Ixc'])
        for row,key,historical_A in ((xc,'xc_ha',ledger['native_values'][label]['terms']['Xc']),(ixc,'integral_n_vxc_ha',ledger['native_values'][label]['Ixc'])):
            row['reevaluated_A_minus_historical_Q_ha']=row.pop('historical_difference_ha')
            row['same_source_A_drift_ha']=a[key]-historical_A
            row['historical_difference_ha']=historical_A-(h['XC'] if key=='xc_ha' else h['Ixc'])
            row['historical_recombination_error_ha']=row['historical_difference_ha']-(row['density_response_in_D_ha']+row['evaluation_residual_at_Q_rep_ha']-row['same_source_A_drift_ha'])
            close(row['historical_recombination_error_ha'],0,tol,'Historical split with explicit same-source drift')
        close(xc['density_response_in_D_ha'],response['xc_density_response_ha'],tol,'XC response')
        close(ixc['density_response_in_D_ha'],response['ixc_density_response_ha'],tol,'Ixc response')
        close(xc['historical_difference_ha'],ledger['comparisons'][label+'_minus_G40']['delta_ha']['XC'],t['same_source_common_abs_ha'],'Historical/self XC')
        close(response['local_density_response_real_ha'],response['local_density_response_fourier_ha'],t['local_parseval_abs_ha'],'Local Fourier identity')
        close(a['atomic_local_ha']-q['atomic_local_ha'],response['local_density_response_real_ha'],t['local_parseval_abs_ha'],'Local energy response')
        close(xc['recombination_error_ha'],0,tol,'XC recombination')
        close(ixc['recombination_error_ha'],0,tol,'Ixc recombination')
        reconstruction=common['evaluations'][label+'_reconstructed']
        comparisons[label+'_minus_G40']=dict(xc=xc,ixc=ixc,
            ixc_evidence_tier='Corresponding final-density full-GGA n*vxc by qe-7.5 tagged convention; installed source commit unknown',
            local_density_response_ha=response['local_density_response_real_ha'],
            local_fourier_identity_error_ha=response['local_real_minus_fourier_ha'],
            local_field_integral_evidence='RUNNER_REPORTED; required new potential arrays remain local',
            delta_electrons=response['delta_electrons'],
            original_L_plus_Pc_ha=a['atomic_local_ha']+const['psp_correction_ha'],
            reconstructed_minus_original_ha={key:reconstruction[key]-a[key] for key in ('atomic_local_ha','xc_ha','integral_n_vxc_ha')})
    require(radial['dftk_bookkeeping']['status']=='PASS','Native local correction bookkeeping failed')
    require(radial['applied_energy_correction'] is False,'Historical total energy must not be corrected')
    return dict(schema_version=1,case=plan['case'],new_data_status='NEW_POSTPROCESSING_OF_HISTORICAL_STATES',
        comparisons=comparisons,Q_rep_L_plus_Pc_ha=q['atomic_local_ha']+const['psp_correction_ha'],
        source_binding_status='PASS',energy_field_semantics_status=ledger['energy_field_semantics_status'],
        historical_energy_ledger_status='PASS',density_representation_status='PASS',same_source_common_terms_status='PASS',
        xc_density_response_status='MEASURED_IN_FROZEN_DFTK',xc_same_represented_density_residual_status='MEASURED_WITH_REPRESENTATION_AND_TAGGED_SOURCE_LIMITS',
        local_gauge_bookkeeping_status='PASS_DFTK_ONE_PC_QE_TAGGED_CONVENTION',g0_integral_diagnostic_status=radial['g0_integral_diagnostic_status'],
        qe_native_local_potential_status='NOT_EXTRACTED',qe_separate_kinetic_nonlocal_status='NOT_AVAILABLE',
        numerical_review_status='REVIEW_REQUIRED',numerical_agreement_status='REVIEW_REQUIRED',physical_convergence_status='NOT_ESTABLISHED',
        residual_attribution_status='PARTIALLY_QUANTIFIED_COMBINATIONS_NOT_FULLY_ATTRIBUTED',ieee_warning_origin_status='NOT_LOCALIZED',
        new_scf_status='NOT_RUN',new_eigensolve_status='NOT_RUN',new_qe_numerical_status='NOT_RUN',
        python_replay_scope='Bound saved scalar tables and algebra only, not independent XC/radial/full-field evaluation',
        Q_rep_scope='Complete saved finite Fourier series on original zero-origin40^3 nodes; no proof of unsaved physical modes or independently extracted QE real-space array',
        residual_scope='Q_rep residual contains evaluator, finite representation, gradients, thresholds and unconfirmed installed-source details; not an identified bug or SOC attribution',
        native_E_F_modified=False)
