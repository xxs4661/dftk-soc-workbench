"""Integer lifetime accounting only; no context, arrays, solver or resource waiver."""

def known_terms(geometry):
    if (geometry['nk'],geometry['ng_max'],geometry['sum_ng'],geometry['fft_size'],geometry['projectors_per_k'],geometry['target_states'],geometry['solver_columns'])!=(216,2138,457287,[48,48,48],72,24,30):
        raise ValueError('Only the frozen K6 geometry accounting is supported')
    n,g,S,R,p,b=216,2138,457287,48**3,72,30
    return dict(
        one_retained_P_set=32*p*S,
        one_retained_D_per_k=16*p*p*n,
        kinetic_vectors=8*S,
        live_padded_G_and_mapping=32*(R//8)*n,
        copied_G_mapping_device_snapshots=40*S,
        both_inverse_mapping_tables=2*17*4096*n,
        prior_current_X24_allX30_and_energy_factors=32*S*(24+30+24+30+24),
        one_k_solver_allowance_unchanged=32*g*30*60,
        three_common_H_local_potential_sets=3*8*R*n,
        core_nonlocal_workspace=16*(2*p*b+2*g*b),
        core_component_workspace=16*4*g*b,
        core_full_H_staging=16*4*g*b,
        core_density_FFT_workspace=16*g+144*R,
        frozen_broad_FFT_allowance_retained=32*R*24*8,
        frozen_broad_field_allowance_retained=8*R*100,
        runtime_library_margin_unchanged=2*1024**3)


def replay(data):
    terms=known_terms(data['geometry'])
    if set(terms)!=set(data['accounting_terms']):raise ValueError('Accounting term omitted/added')
    for key,value in terms.items():
        if type(data['accounting_terms'][key]['bytes']) is not int or data['accounting_terms'][key]['bytes']!=value:
            raise ValueError('Accounting arithmetic differs: '+key)
    subtotal=sum(terms.values())
    if subtotal!=data['known_terms_plus_retained_allowances_subtotal_bytes']:raise ValueError('Subtotal changed')
    if data['hard_limit_bytes']!=8*1024**3 or data['margin_bytes']!=2*1024**3:raise ValueError('Budget/margin changed')
    if data['original_legacy_estimate']['total_bytes']!=12614633984:raise ValueError('Historical estimate changed')
    if (data['status']!='INSUFFICIENT_EVIDENCE' or data['new_estimated_peak_bytes'] is not None
        or data['subtotal_is_upper_bound'] is not False or not data['unpriced_or_unbounded']
        or data['DFTK_K6_SCF']!='NOT_RUN' or data['DFTK_K6_context_created'] is not False):
        raise ValueError('Incomplete accounting cannot authorize or certify a K6 run')
    return dict(status='INSUFFICIENT_EVIDENCE',arithmetic_status='PASS',subtotal_bytes=subtotal,
                DFTK_K6_SCF='NOT_RUN',scope='Incomplete integer accounting; no estimated peak bound')
