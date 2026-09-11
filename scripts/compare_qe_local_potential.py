#!/usr/bin/env python3
"""Finite-grid local-potential arithmetic; no FFT, solver or physical model.

The main direct integrals use the original archived A/B density arrays and
certified Q_rep. Complete ordinary Fourier coefficients provide a separate
Parseval check. Sparse saved Q coefficients define a finite series, with no
assertion about unsaved physical modes. All arithmetic keeps G=0 and Nyquist.
"""
from __future__ import annotations

import math
from compare_density_hartree import reciprocal_geometry, validate_coefficients

ZERO=(0,0,0)
DEFAULT_THRESHOLDS={
    'p0_pointwise_fp_relative':1e-12, 'electron_count_abs':1e-8,
    'fft_normalized':1e-11, 'dftk_local_recovery_abs_ha':1e-8,
    'dftk_mean_recovery_abs_ha':1e-11, 'real_fourier_energy_abs_ha':1e-9,
    'ledger_abs_ha':1e-10, 'g0_prediction_abs_ha':1e-9,
    'local_print_bound_target_ha':1e-7, 'mean_print_bound_target_ha':1e-8,
}


def _finite(x,label):
    if type(x) not in (int,float) or not math.isfinite(x):
        raise ValueError('Invalid finite numeric '+label)
    return float(x)


def _thresholds(values):
    out=dict(DEFAULT_THRESHOLDS if values is None else values)
    if set(out)!=set(DEFAULT_THRESHOLDS):
        raise ValueError('Missing or unknown declared local-potential thresholds')
    for key,value in out.items():
        if _finite(value,key)<=0:raise ValueError('Nonpositive threshold '+key)
    return out


def _close(a,b,tol,label):
    difference=_finite(a,label)-_finite(b,label)
    if abs(difference)>tol:raise ValueError(label+' differs beyond declared tolerance')
    return difference


def _norm(values):
    return math.sqrt(math.fsum(abs(z)**2 for z in values))


def _sum_product(a,b):
    if len(a)!=len(b):raise ValueError('Product arrays differ in size')
    value=math.fsum(x*y for x,y in zip(a,b))
    return _finite(value,'sum product')


def pointwise_checks(n_A,n_B,n_Q,V_D,V_Qpp,n_P0,uV,un,*,volume_bohr3,thresholds=None):
    """Full physical nodes, all potential samples in Ha, density in e/bohr^3.

    uV/un are actual decimal-token halfwidths already converted by the parser.
    These bounds assume ordinary nearest decimal rounding; they are not bounds
    on the underlying calculation. No input is renormalized, clipped or shifted.
    """
    t=_thresholds(thresholds);volume=_finite(volume_bohr3,'volume')
    if volume<=0:raise ValueError('Nonpositive volume')
    inputs=(n_A,n_B,n_Q,V_D,V_Qpp,n_P0,uV,un)
    count=len(n_Q)
    if not 2<=count<=1_000_000 or any(len(a)!=count for a in inputs):
        raise ValueError('Physical node count mismatch, padding or repeated endpoints')
    arrays=[[ _finite(x,'physical field') for x in a] for a in inputs]
    a,b,q,vd,vq,p0,uv,ur=arrays
    if min(uv+ur)<0:raise ValueError('Negative quantization halfwidth')
    dvol=volume/count
    means={'D':math.fsum(vd)/count,'Qpp':math.fsum(vq)/count}
    electrons={name:dvol*math.fsum(n) for name,n in [('A',a),('B',b),('Q',q),('P0',p0)]}
    p0_errors=[x-y for x,y in zip(p0,q)]
    allowances=[u+t['p0_pointwise_fp_relative']*max(1,abs(n)) for u,n in zip(ur,q)]
    excess=[abs(e)-u for e,u in zip(p0_errors,allowances)]
    failures=sum(e>0 for e in excess)
    u_ne=dvol*math.fsum(ur)
    electron_error=electrons['P0']-electrons['Q']
    p0_pass=failures==0 and abs(electron_error)<=u_ne+t['electron_count_abs']
    integrals={'L_D_A':dvol*_sum_product(a,vd),'L_D_B':dvol*_sum_product(b,vd),
               'L_D_Q':dvol*_sum_product(q,vd),'L_Qpp_Q':dvol*_sum_product(q,vq),
               'L_Qpp_printed_P0':dvol*_sum_product(p0,vq)}
    rho={name:dvol*_sum_product([x-y for x,y in zip(n,q)],vd) for name,n in [('A',a),('B',b)]}
    shape=dvol*math.fsum(n*((v-means['D'])-(w-means['Qpp'])) for n,v,w in zip(q,vd,vq))
    u_mean=math.fsum(uv)/count
    u_lq=dvol*math.fsum(abs(n)*u for n,u in zip(q,uv))
    u_printed=dvol*math.fsum(abs(n)*u+abs(v)*un_i+un_i*u for n,v,u,un_i in zip(p0,vq,uv,ur))
    # Same printed V enters zero-mean shape and G0: propagate the combined
    # coefficient -n_Q once, not two unrelated random errors.
    u_shape=dvol*math.fsum(abs(n-electrons['Q']/volume)*u for n,u in zip(q,uv))
    u_g0=abs(electrons['Q'])*u_mean
    raw=[v-w for v,w in zip(vd,vq)]
    centered=[x-(means['D']-means['Qpp']) for x in raw]
    raw_norm=math.sqrt(dvol)*_norm(raw);shape_norm=math.sqrt(dvol)*_norm(centered)
    precision='PASS' if u_lq<=t['local_print_bound_target_ha'] and u_mean<=t['mean_print_bound_target_ha'] else 'PRECISION_LIMITED'
    return {'schema_version':1,'point_count':count,'volume_bohr3':volume,'dvol_bohr3':dvol,
        'units':{'potential':'Ha','density':'electron/bohr^3','integrals':'Ha/cell'},
        'means_ha':means,'electrons':electrons,'integrals_ha':integrals,
        'rho_response_ha':rho,'shape_at_Q_ha':shape,
        'P0_density_registration_status':'PASS' if p0_pass else 'FAIL',
        'P0':{'failing_points':failures,'maximum_point_error':max(abs(e) for e in p0_errors),
              'maximum_excess_over_allowance':max(excess),'maximum_error_flat_index_zero_based':max(range(count),key=lambda i:abs(p0_errors[i])),
              'density_l2_e_bohr_minus_3_over_2':math.sqrt(dvol)*_norm(p0_errors),
              'density_normalized_l2':_norm(p0_errors)/max(_norm(p0),_norm(q),1),
              'electron_difference':electron_error,'electron_token_halfwidth':u_ne,
              'electron_allowance':u_ne+t['electron_count_abs'],
              'pointwise_rule':'u_n + declared_fp*max(1,abs(Q_rep)); no registration fit'},
        'potential_field_difference':{'raw_l2_ha_bohr_3_over_2':raw_norm,
              'zero_mean_l2_ha_bohr_3_over_2':shape_norm,'raw_max_abs_ha':max(abs(x) for x in raw),
              'zero_mean_max_abs_ha':max(abs(x) for x in centered),
              'raw_normalized_l2':_norm(raw)/max(_norm(vd),_norm(vq),1),
              'normalization':'Euclidean norm of node values, denominator max(norm(D),norm(Qpp),1 Ha)'},
        'quantization':{'u_meanV_ha':u_mean,'u_L_Q_ha':u_lq,'u_L_using_printed_rho_ha':u_printed,
              'u_shape_at_Q_ha':u_shape,'u_g0_at_Q_ha':u_g0,'u_shape_plus_g0_ha':u_lq,
              'u_L_Q_from_registered_P0_lower_ha':dvol*math.fsum(max(0,abs(n)-a_i)*u for n,a_i,u in zip(p0,allowances,uv)),
              'u_L_Q_from_registered_P0_upper_ha':dvol*math.fsum((abs(n)+a_i)*u for n,a_i,u in zip(p0,allowances,uv)),
              'correlation_rule':'Shape + G0 first combines to -n_Q*deltaV; no independent-noise assumption',
              'scope':'Decimal print halfwidth propagation, not full numerical error bounds'},
        'output_precision_status':precision,'input_adjustments_applied':False,
        'node_order':'First index fastest, physical nodes only, zero fractional origin'}


def _native(coefficients,size,*,complete,conjugacy_tolerance=DEFAULT_THRESHOLDS['fft_normalized']):
    if len(size)!=3 or any(type(n) is not int or not 2<=n<=4096 for n in size) or math.prod(size)>1_000_000:
        raise ValueError('Unsupported finite grid size')
    source=validate_coefficients(coefficients);out={}
    for m,z in source.items():
        if any(abs(i)>n//2 for i,n in zip(m,size)):
            raise ValueError('Coefficient outside finite grid; no alias folding of external modes')
        representative=tuple((i+n//2)%n-n//2 for i,n in zip(m,size))
        if representative in out:raise ValueError('Ambiguous Nyquist or duplicate modular representative')
        out[representative]=z
    if complete and len(out)!=math.prod(size):raise ValueError('Complete native field coefficients required')
    # Reality uses the actual discrete grid's modular conjugate at Nyquist.
    error=_norm(z-out.get(tuple((-i+n//2)%n-n//2 for i,n in zip(m,size)),0j).conjugate() for m,z in out.items())
    if error/max(_norm(out.values()),1)>conjugacy_tolerance:
        raise ValueError('Fourier series is not real under discrete modular conjugacy')
    return out


def fourier_integral(density,potential,volume_bohr3):
    """Ordinary nbar/Vbar inner product, never +/-G doubling."""
    if ZERO not in density or not set(density)<=potential.keys():
        raise ValueError('Missing integration support/G0')
    value=volume_bohr3*math.fsum((density[m].conjugate()*potential[m]).real for m in sorted(density))
    return _finite(value,'Fourier integral')


def _history(historical):
    ledger=historical['ledger'];common=historical['common'];radial=historical['radial']
    if ledger['historical_energy_ledger_status']!='PASS' or common['execution_status']!='PASS':
        raise ValueError('Unaccepted historical energy source')
    if radial['qe_tagged_prediction']['status']!='PREDICTED_QE_7_5_TAGGED_CONVENTION':
        raise ValueError('Historical tagged G0 prediction unavailable')
    widths={x['id']:_finite(x['quantization_half_width_ha'],'historical token width') for x in ledger['field_dictionary'] if 'quantization_half_width_ha' in x}
    u_o=math.fsum(widths['G40.'+x] for x in ('etot','demet','ehart','etxc','ewald'))
    return ledger,common,radial,u_o


def compare_local_potential(density_coefficients,potential_coefficients,*,lattice_vectors_bohr,
                            fft_size,historical,pointwise,thresholds=None):
    """Public full-coefficient checks and signed historical ledger continuation.

    pointwise is the independently recorded physical-node result above; its
    real-field integrals must match this complete Fourier replay. The caller
    binds original files/run IDs/hashes, parser units, and direct 17-mode checks.
    This function never claims to reconstruct Q nodes or execute an FFT.
    """
    t=_thresholds(thresholds);size=tuple(fft_size);volume=reciprocal_geometry(lattice_vectors_bohr)['volume_bohr3']
    if set(density_coefficients)!={'A','B','Q'} or set(potential_coefficients)!={'D','Qpp'}:
        raise ValueError('Missing density or potential dataset')
    densities={k:_native(c,size,complete=k!='Q',conjugacy_tolerance=t['fft_normalized']) for k,c in density_coefficients.items()}
    potentials={k:_native(c,size,complete=True,conjugacy_tolerance=t['fft_normalized']) for k,c in potential_coefficients.items()}
    if type(pointwise.get('point_count')) is not int or pointwise['point_count']!=math.prod(size):
        raise ValueError('Pointwise physical count does not match Fourier grid')
    if pointwise['input_adjustments_applied'] is not False:raise ValueError('Adjusted original field')
    _close(pointwise['volume_bohr3'],volume,1e-11,'Pointwise/Fourier volume')
    if pointwise['units']!={'potential':'Ha','density':'electron/bohr^3','integrals':'Ha/cell'}:
        raise ValueError('Pointwise field units mismatch')
    p0=pointwise['P0']
    if type(p0['failing_points']) is not int or not 0<=p0['failing_points']<=math.prod(size):
        raise ValueError('Invalid P0 point-failure count')
    p0_pass=(p0['failing_points']==0 and _finite(p0['maximum_excess_over_allowance'],'P0 excess')<=0
             and abs(_finite(p0['electron_difference'],'P0 electron difference'))<=_finite(p0['electron_allowance'],'P0 electron allowance'))
    if pointwise['P0_density_registration_status']!=('PASS' if p0_pass else 'FAIL'):
        raise ValueError('P0 registration status contradicts its measured diagnostics')
    ledger,common,radial,u_o=_history(historical)
    const=common['constants'];pc=_finite(const['psp_correction_ha'],'native Pc');model_ne=_finite(const['model_ne'],'model Ne')
    _close(const['volume_bohr3'],volume,1e-11,'Historical volume')
    _close(pc,const['alpha_from_common_native']*const['natoms']*const['n_electrons_from_atoms_actual']/volume,t['ledger_abs_ha'],'Native Pc factors (one copy)')
    if const['model_ne']!=const['n_electrons_from_atoms_actual']:raise ValueError('Nonneutral correction model unsupported')
    means={k:potentials[k][ZERO].real for k in ('D','Qpp')}
    ne={k:volume*c[ZERO].real for k,c in densities.items()}
    for k in means:_close(means[k],pointwise['means_ha'][k],t['dftk_mean_recovery_abs_ha'],'Direct/Fourier mean '+k)
    _close(means['D'],common['evaluations']['Q_rep']['local_mean_ha'],t['dftk_mean_recovery_abs_ha'],'Historical D mean (no shift)')
    for k in ne:
        _close(ne[k],pointwise['electrons'][k],t['electron_count_abs'],'Direct/Fourier electrons '+k)
        _close(ne[k],model_ne,t['electron_count_abs'],'Model electrons '+k)
    ints={'L_D_'+k:fourier_integral(d,potentials['D'],volume) for k,d in densities.items()}
    ints['L_Qpp_Q']=fourier_integral(densities['Q'],potentials['Qpp'],volume)
    parseval={k:_close(v,pointwise['integrals_ha'][k],t['real_fourier_energy_abs_ha'],'Direct/Fourier '+k) for k,v in ints.items()}
    same_source={}
    for k,name in [('A','A_original_n_out'),('B','B_original_n_out'),('Q','Q_rep')]:
        same_source[k]=_close(pointwise['integrals_ha']['L_D_'+k],common['evaluations'][name]['local_integral_ha'],t['dftk_local_recovery_abs_ha'],'Historical D local '+k)
    modes=sorted(potentials['D']);delta={m:potentials['D'][m]-potentials['Qpp'][m] for m in modes}
    nonzero=[m for m in modes if m!=ZERO]
    raw_l2=math.sqrt(volume)*_norm(delta.values());shape_l2=math.sqrt(volume)*_norm(delta[m] for m in nonzero)
    _close(raw_l2,pointwise['potential_field_difference']['raw_l2_ha_bohr_3_over_2'],t['fft_normalized']*max(raw_l2,1),'Field raw L2 Parseval')
    _close(shape_l2,pointwise['potential_field_difference']['zero_mean_l2_ha_bohr_3_over_2'],t['fft_normalized']*max(shape_l2,1),'Field shape L2 Parseval')
    quant=pointwise['quantization'];u_mean=_finite(quant['u_meanV_ha'],'mean print width');u_lq=_finite(quant['u_L_Q_ha'],'local print width')
    if min(u_mean,u_lq)<0:raise ValueError('Negative print bounds')
    _close(quant['u_g0_at_Q_ha'],abs(pointwise['electrons']['Q'])*u_mean,1e-18,'G0 token propagation')
    _close(quant['u_shape_plus_g0_ha'],u_lq,1e-18,'Correlated shape+G0 token propagation')
    if p0_pass and not quant['u_L_Q_from_registered_P0_lower_ha']-1e-18<=u_lq<=quant['u_L_Q_from_registered_P0_upper_ha']+1e-18:
        raise ValueError('Local print width outside independently registered-density interval')
    expected_precision='PASS' if u_mean<=t['mean_print_bound_target_ha'] and u_lq<=t['local_print_bound_target_ha'] else 'PRECISION_LIMITED'
    if expected_precision!=pointwise['output_precision_status']:raise ValueError('False precision status')
    g0_difference=means['Qpp']-radial['qe_tagged_prediction']['C_ha']
    result={'schema_version':1,'field_provenance':'QE_PP_RECONSTRUCTION_BOUND_TO_HISTORICAL_G40',
        'means_ha':{**means,'C_D_book':pc/model_ne,'C_Q_tagged':radial['qe_tagged_prediction']['C_ha']},
        'G0_prediction':{'signed_difference_ha':g0_difference,'absolute_difference_ha':abs(g0_difference),
            'token_bound_ha':u_mean,'allowed_ha':u_mean+t['g0_prediction_abs_ha']},
        'G0_prediction_comparison_status':'SUPPORTED_BY_PP_RECONSTRUCTED_MEAN' if abs(g0_difference)<=u_mean+t['g0_prediction_abs_ha'] else 'NOT_SUPPORTED_BY_PP_RECONSTRUCTED_MEAN',
        'nonzero_G_shape':{'coefficient_max_abs_difference_ha':max(abs(delta[m]) for m in nonzero),
            'maximum_coefficient_miller':list(max(nonzero,key=lambda m:abs(delta[m]))),
            'raw_l2_ha_bohr_3_over_2':raw_l2,'zero_mean_l2_ha_bohr_3_over_2':shape_l2,
            'raw_normalized_l2':_norm(delta.values())/max(_norm(potentials['D'].values()),_norm(potentials['Qpp'].values()),1),
            'normalization':'Ordinary Fourier coefficient norm; denominator max(norm(D),norm(Qpp),1 Ha)',
            'native_coefficient_count':len(modes),'zero_and_Nyquist_retained':True,
            'export_tail_scope':'All printed-field discrete modes retained; small output tails are not assigned physical support'},
        'source_support_count':{k:len(c) for k,c in density_coefficients.items()},
        'finite_series_scope':'Missing saved Q modes only absent from this declared finite series; no unsaved physical-zero assertion',
        'integrals_fourier_ha':ints,'integrals_direct_ha':pointwise['integrals_ha'],
        'parseval_signed_errors_ha':parseval,'same_source_D_recovery_errors_ha':same_source,
        'electrons_fourier':ne,'quantization':quant,'output_precision_status':expected_precision,
        'P0_density_registration_status':pointwise['P0_density_registration_status'],
        'qe_historical_in_memory_vloc_status':'NOT_EXTRACTED','qe_internal_tab_vloc_status':'NOT_EXTRACTED',
        'numerical_review_status':'REVIEW_REQUIRED','physical_convergence_status':'NOT_ESTABLISHED',
        'ieee_warning_origin_status':'NOT_LOCALIZED','new_scf_status':'NOT_RUN','new_eigensolve_status':'NOT_RUN',
        'independent_QE_T_NL_status':'NOT_AVAILABLE','native_E_F_modified':False,
        'replay_scope':'All complete-coefficient inner products and scalar algebra; original node registration/quantization requires explicit node reconstruction backend'}
    if pointwise['P0_density_registration_status']!='PASS':
        result.update(local_same_density_integration_status='BLOCKED_P0_REGISTRATION',
            local_energy_decomposition_status='BLOCKED_P0_REGISTRATION',derived_remaining_combination_status='BLOCKED_P0_REGISTRATION',comparisons={})
        return result
    # Main path retains original A/B direct arrays. Fourier copies and drifts
    # above remain distinct; no historical record is rewritten.
    direct=pointwise['integrals_ha'];nq=pointwise['electrons']['Q'];md=pointwise['means_ha']['D'];mq=pointwise['means_ha']['Qpp']
    shape=pointwise['shape_at_Q_ha'];g0=pc+nq*(md-mq)
    shape_fourier=volume*math.fsum((densities['Q'].get(m,0j).conjugate()*delta[m]).real for m in nonzero)
    _close(shape,shape_fourier,t['real_fourier_energy_abs_ha'],'Nonzero G shape integral')
    comparisons={}
    for label in ('A','B'):
        hist=ledger['native_values'][label]['terms'];old=ledger['comparisons'][label+'_minus_G40']
        _close(pc,hist['PspCorrection'],t['ledger_abs_ha'],'Native/historical Pc one copy')
        response=pointwise['rho_response_ha'][label]
        _close(response,direct['L_D_'+label]-direct['L_D_Q'],t['ledger_abs_ha'],'Density response identity')
        local_combo=direct['L_D_'+label]+pc-direct['L_Qpp_Q']
        drift=(direct['L_D_'+label]+pc)-(hist['AtomicLocal']+hist['PspCorrection'])
        historical_combo=hist['AtomicLocal']+hist['PspCorrection']-direct['L_Qpp_Q']
        remainder=old['delta_ha']['O']-historical_combo
        closure=_close(local_combo,response+shape+g0,t['ledger_abs_ha'],'Local rho+shape+G0 decomposition')
        _close(historical_combo,response+shape+g0-drift,t['ledger_abs_ha'],'Historical local decomposition with drift')
        total=math.fsum([old['delta_ha'][x] for x in ('H','XC','Ew')]+[historical_combo,remainder])
        total_error=_close(old['delta_ha']['E'],total,t['ledger_abs_ha'],'Signed total ledger without double-counting subterms')
        comparisons[label+'_minus_G40']={'historical_delta_ha':old['delta_ha'],
            'rho_response_ha':response,'shape_at_Q_ha':shape,'g0_at_Q_ha':g0,
            'Delta_Lbar_current_ha':local_combo,'same_source_local_plus_Pc_drift_ha':drift,
            'Delta_Lbar_historical_ha':historical_combo,'R_after_local_ha':remainder,
            'g0_simplified_auxiliary_ha':model_ne*(pc/model_ne-mq),
            'g0_exact_minus_simplified_ha':nq*md+(model_ne-nq)*mq,
            'local_recombination_error_ha':closure,'total_ledger_error_ha':total_error,
            'uncertainty':{'u_local_combination_print_ha':u_lq,'u_R_after_local_print_ha':u_lq+u_o,
                'u_historical_O_Q_print_ha':u_o,'correlation_rule':'rho+shape+G0 is one local term; shape and G0 rounding combined before propagation'},
            'subterm_rule':'rho_response, shape and G0 partition local only; subtract drift for historical ledger, never add both parent and children'}
    result.update(comparisons=comparisons,Q_TNL_ledger_post_ha=ledger['native_values']['G40']['O']-direct['L_Qpp_Q'],
        Q_TNL_record_kind='DERIVED_LEDGER_REMAINDER_USING_PP_RECONSTRUCTED_LOCAL_INTEGRAL',
        Q_TNL_print_halfwidth_ha=u_o+u_lq,local_same_density_integration_status='MEASURED_WITH_P0_AND_PRINT_LIMITS',
        nonzero_G_shape_comparison_status='MEASURED_COMPLETE_NATIVE_GRID',local_energy_decomposition_status='PASS_ALGEBRA',
        derived_remaining_combination_status='DERIVED_NOT_INDEPENDENT_T_NL',residual_attribution_status='PARTIALLY_QUANTIFIED')
    return result
