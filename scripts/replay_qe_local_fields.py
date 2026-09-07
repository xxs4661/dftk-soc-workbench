#!/usr/bin/env python3
"""Complete public local-field replay using an explicitly existing NumPy FFT.

No scientific solver, XC/model evaluation or package installation is used.
The ordinary coefficient convention is forward FFT/N and inverse FFT*N; both
sign and Fortran node order have analytic synthetic checks. Direct selected
Fourier sums are independent of FFT and never fit a permutation or origin.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np

import compare_qe_local_potential as C
from compare_density_hartree import read_coefficients_gzip, reciprocal_geometry
from parse_qe_filplot import parse_qe_filplot

PUBLIC_SOURCES={
    'dftk_density':'results/mg-soc-density-hartree/dftk-nout.csv.gz',
    'qe_density':'results/mg-soc-density-hartree/qe-rho.csv.gz',
    'ledger':'results/mg-soc-energy-reference/ledger.json',
    'common':'results/mg-soc-energy-reference/common-terms.json',
    'radial':'results/mg-soc-energy-reference/local-g0.json',
}


def _error(a,b):
    x=np.asarray(a);y=np.asarray(b)
    if x.shape!=y.shape or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('Wrong field shape or nonfinite FFT data')
    delta=x-y
    return {'normalized_l2':float(np.linalg.norm(delta.ravel())/max(np.linalg.norm(x.ravel()),np.linalg.norm(y.ravel()),1)),
            'max_abs':float(np.max(np.abs(delta)))}


def _gate(error,tol,label):
    if error['normalized_l2']>tol:raise ValueError(label+' exceeds declared normalized FFT tolerance')
    return dict(error,status='PASS')


def coefficients_to_field(coefficients,size,*,complete,tolerance):
    """Embed this finite series, preserving separate original source support."""
    c=C._native(coefficients,size,complete=complete,conjugacy_tolerance=tolerance)
    workspace=np.zeros(tuple(size),dtype=np.complex128)
    for m,z in c.items():workspace[tuple(i%n for i,n in zip(m,size))]=z
    count=math.prod(size)
    complex_field=np.fft.ifftn(workspace)*count
    imaginary=_error(complex_field,complex_field.real)
    _gate(imaginary,tolerance,'Substantive imaginary reconstructed field')
    real_field=complex_field.real.copy()
    back=np.fft.fftn(real_field)/count
    roundtrip=_gate(_error(back,workspace),tolerance,'Coefficient IFFT/FFT roundtrip')
    return real_field.reshape(-1,order='F').tolist(),workspace,{
        'source_support_count':len(coefficients),'native_workspace_count':count,
        'imaginary':dict(imaginary,status='PASS'),'coefficient_roundtrip':roundtrip,
        'support_scope':'Zero workspace evaluates exactly the saved finite series; unsaved physical modes are not asserted zero'}


def field_to_coefficients(values,size):
    field=np.asarray(values,dtype=np.float64)
    if field.ndim!=1 or field.size!=math.prod(size) or not np.isfinite(field).all():
        raise ValueError('Expected complete finite first-index-fast real field')
    spectrum=np.fft.fftn(field.reshape(tuple(size),order='F'))/field.size
    ranges=[range(-(n//2),n-n//2) for n in size]
    return {(i,j,k):complex(spectrum[i%size[0],j%size[1],k%size[2]])
            for i in ranges[0] for j in ranges[1] for k in ranges[2]},spectrum


def direct_modes(values,size,millers):
    """Selected direct exp(-2*pi*i*m.s) sums, without an FFT or fitted shift."""
    field=np.asarray(values,dtype=np.float64)
    if field.shape!=(math.prod(size),) or not np.isfinite(field).all():raise ValueError('Invalid direct Fourier field')
    if len(millers)!=17 or len({tuple(m) for m in millers})!=17:
        raise ValueError('Exactly the 17 predeclared distinct Fourier probes are required')
    coordinates=np.indices(tuple(size),dtype=np.float64).reshape(3,-1,order='F')
    coordinates/=np.array(size,dtype=np.float64)[:,None]
    result={}
    for raw in millers:
        if len(raw)!=3 or any(type(m) is not int or abs(m)>n//2 for m,n in zip(raw,size)):
            raise ValueError('Invalid predeclared Fourier probe')
        m=tuple(raw);angle=2*math.pi*np.sum(np.array(m)[:,None]*coordinates,axis=0)
        # Trigonometry evaluates the documented ordinary Fourier definition.
        # math.fsum gives a reduction separate from NumPy's FFT algorithm.
        result[m]=complex(math.fsum((field*np.cos(angle)).tolist()),-math.fsum((field*np.sin(angle)).tolist()))/len(field)
    return result


def _read_original_fields(path,count):
    with Path(path).open(newline='') as stream:
        reader=csv.DictReader(stream)
        if reader.fieldnames!=['n_A','n_B','n_Q','V_D']:raise ValueError('Wrong original archived-field transfer header')
        fields={k:[] for k in reader.fieldnames}
        for i,row in enumerate(reader):
            if i>=count or None in row:raise ValueError('Oversize or ragged original field transfer')
            for key in fields:
                try:value=float(row[key])
                except (TypeError,ValueError) as exc:raise ValueError('Invalid original field token') from exc
                if not math.isfinite(value):raise ValueError('Nonfinite original field token')
                fields[key].append(value)
    if len(fields['n_A'])!=count:raise ValueError('Truncated original field transfer')
    return fields


def replay_fields(densities,potentials,p2,p0,*,physical,historical,probes,thresholds,original_fields=None):
    """Numerical replay entry for already parsed and externally bound sources."""
    t={key:thresholds[key] for key in C.DEFAULT_THRESHOLDS}
    C._thresholds(t)
    size=tuple(physical['fft_size']);volume=reciprocal_geometry(physical['lattice_vectors_bohr'])['volume_bohr3']
    if (p2['parse_status']!='PASS' or p0['parse_status']!='PASS' or p2['expected_validation_status']!='PASS'
            or p0['expected_validation_status']!='PASS' or p2['plot_num']!=2 or p0['plot_num']!=0
            or p2['unit']!='Ha' or p0['unit']!='electron/bohr^3'
            or p2['unit_scale']!=.5 or p0['unit_scale']!=1
            or tuple(p2['grid'])!=size or tuple(p0['grid'])!=size):
        raise ValueError('Unaccepted filplot layout, source geometry, action or units')
    if set(densities)!={'A','B','Q'} or set(potentials)!={'D','Qpp'}:raise ValueError('Incomplete field matrix')
    arrays={};workspaces={};checks={}
    for key,coeff in {**densities,'V_D':potentials['D'],'V_Qpp':potentials['Qpp']}.items():
        arrays[key],workspaces[key],checks[key]=coefficients_to_field(coeff,size,complete=key!='Q',tolerance=t['fft_normalized'])
    actual_q,actual_spectrum=field_to_coefficients(p2['values'],size)
    checks['P2_native_to_canonical']=_gate(_error(actual_spectrum,workspaces['V_Qpp']),t['fft_normalized'],'Native P2/canonical coefficient identity')
    checks['P2_native_to_reconstructed']=_gate(_error(p2['values'],arrays['V_Qpp']),t['fft_normalized'],'Native P2/canonical reconstructed field')
    native_q_support=set(C._native(densities['Q'],size,complete=False,conjugacy_tolerance=t['fft_normalized']))
    all_modes=set(actual_q);outside=sorted(all_modes-native_q_support)
    u_potential_mean=math.fsum(p2['halfwidths'])/math.prod(size)
    floating_margin=t['fft_normalized']*max(1,max(abs(z) for z in actual_q.values()))
    support_diagnostics={'qe_saved_G_count':len(native_q_support),'full_export_G_count':len(all_modes),
        'outside_qe_saved_G_count':len(outside),'all_native_modes_retained':True,
        'tagged_source_scope':'Standard vltot uses the actual QE G list; output FFT modes outside it may arise from decimal printing, not extra physical support',
        'u_uniform_coefficient_print_bound_ha':u_potential_mean,'floating_margin_ha':floating_margin}
    for name,coeff in [('P2',actual_q),('D',potentials['D'])]:
        normalized=C._native(coeff,size,complete=True,conjugacy_tolerance=t['fft_normalized'])
        z=[normalized[m] for m in outside]
        support_diagnostics[name]={'outside_max_abs_ha':max((abs(x) for x in z),default=0.),
            'outside_coefficient_l2_ha':math.sqrt(math.fsum(abs(x)**2 for x in z)),
            'outside_field_l2_ha_bohr_3_over_2':math.sqrt(volume*math.fsum(abs(x)**2 for x in z)),
            'scope':'Printed QE field; retained noise diagnostic' if name=='P2' else 'Separate DFTK support diagnostic; no QE support-zero assumption'}
    above=sum(abs(actual_q[m])>u_potential_mean+floating_margin for m in outside)
    support_diagnostics['P2'].update(count_above_uniform_print_plus_float_bound=above,
        status='COMPATIBLE_WITH_PRINT_NOISE_BOUND' if above==0 else 'EXCEEDS_PRINT_NOISE_BOUND')
    # The low-precision printed P0 is a registration witness, never substituted
    # for the high-precision Q finite-series reconstruction.
    selected={};phase=[];u_rho_mean=math.fsum(p0['halfwidths'])/math.prod(size)
    for key,field,spectrum in [('P2',p2['values'],actual_spectrum),('P0',p0['values'],None),('D',arrays['V_D'],workspaces['V_D'])]:
        direct=direct_modes(field,size,probes)
        if spectrum is None:_,spectrum=field_to_coefficients(field,size)
        rows=[]
        for m,z in direct.items():
            index=tuple(i%n for i,n in zip(m,size));fft=complex(spectrum[index])
            error=abs(z-fft);allow=t['fft_normalized']*max(abs(z),abs(fft),1)
            if error>allow:raise ValueError('Direct selected Fourier sum disagrees with FFT')
            rows.append({'miller':list(m),'direct':[z.real,z.imag],'fft':[fft.real,fft.imag],
                         'absolute_error':error,'normalized_error':error/max(abs(z),abs(fft),1),'status':'PASS'})
            if key=='P0':
                expected=complex(workspaces['Q'][index]);fp=t['fft_normalized']*max(abs(z),abs(expected),1)
                phase.append({'miller':list(m),'printed_density_direct':[z.real,z.imag],
                    'Q_rep_coefficient':[expected.real,expected.imag],'absolute_difference':abs(z-expected),
                    'token_halfwidth_allowance':u_rho_mean,'floating_allowance':fp,'total_allowance':u_rho_mean+fp,
                    'status':'PASS' if abs(z-expected)<=u_rho_mean+fp else 'FAIL'})
        selected[key]=rows
    primary={k:arrays[k] for k in ('A','B','Q')};vd=arrays['V_D'];original_check={}
    if original_fields is not None:
        original=_read_original_fields(original_fields,math.prod(size)) if isinstance(original_fields,(str,Path)) else original_fields
        if set(original)!={'n_A','n_B','n_Q','V_D'}:raise ValueError('Incomplete original archived fields')
        for key in ('A','B','Q'):
            original_check[key]=_gate(_error(original['n_'+key],arrays[key]),t['fft_normalized'],'Original/reconstructed density '+key)
            primary[key]=list(original['n_'+key])
        original_check['V_D']=_gate(_error(original['V_D'],vd),t['fft_normalized'],'Original/FFT archived D potential')
        vd=list(original['V_D'])
    point=C.pointwise_checks(primary['A'],primary['B'],primary['Q'],vd,p2['values'],p0['values'],
                             p2['halfwidths'],p0['halfwidths'],volume_bohr3=volume,thresholds=t)
    phase_status='PASS' if all(x['status']=='PASS' for x in phase) else 'FAIL'
    if phase_status=='PASS':
        comparison=C.compare_local_potential(densities,potentials,lattice_vectors_bohr=physical['lattice_vectors_bohr'],
            fft_size=size,historical=historical,pointwise=point,thresholds=t)
    else:
        comparison={'means_ha':point['means_ha'],'P0_density_registration_status':'FAIL_17_MODE_CHECK',
            'local_same_density_integration_status':'BLOCKED_P0_REGISTRATION',
            'local_energy_decomposition_status':'BLOCKED_P0_REGISTRATION','comparisons':{},
            'native_E_F_modified':False,'numerical_review_status':'REVIEW_REQUIRED'}
    return {'schema_version':1,'backend':{'numpy_version':np.__version__,'fft_backend':'numpy.fft CPU',
                'normalization':'forward fftn/N; inverse ifftn*N; order F physical nodes','dtype':'Float64/ComplexF64'},
        'fft_checks':checks,'direct_17_mode_checks':selected,'p0_phase_checks':phase,
        'support_diagnostics':support_diagnostics,
        'p0_phase_status':phase_status,'pointwise':point,'comparison':comparison,
        'density_integral_source':'ORIGINAL_ARCHIVED_ARRAYS' if original_fields is not None else 'PUBLIC_FINITE_SERIES_RECONSTRUCTION',
        'original_vs_public_reconstruction':original_check,
        'full_public_replay_scope':'Complete native P2/D coefficient transforms, all-node Q/P0 registration and token uncertainty, full Fourier/local signed arithmetic; not a new pp.x run',
        'source_field_adjustments_applied':False,'new_scf_status':'NOT_RUN','new_eigensolve_status':'NOT_RUN'}


def replay(root,plan,potential_path,p2_path,p0_path,*,original_fields=None):
    """Use only named public files unless an explicitly bound original CSV is supplied.

    The caller separately binds the new filplot/potential files to run receipts.
    Their hashes are returned. Frozen historical inputs must match the plan.
    """
    root=Path(root);bound={}
    potential_path,p2_path,p0_path=[Path(p) if Path(p).is_absolute() else root/p for p in (potential_path,p2_path,p0_path)]
    if isinstance(original_fields,(str,Path)) and not Path(original_fields).is_absolute():
        original_fields=root/original_fields
    for key,relative in PUBLIC_SOURCES.items():
        data=(root/relative).read_bytes();sha=hashlib.sha256(data).hexdigest()
        if sha!=plan['source_sha256'][relative]:raise ValueError('Changed frozen public source: '+relative)
        bound[key]=sha
    d=read_coefficients_gzip(root/PUBLIC_SOURCES['dftk_density']);q=read_coefficients_gzip(root/PUBLIC_SOURCES['qe_density'])
    if set(d)!={'A_out','B_out'} or set(q)!={'QE'}:raise ValueError('Wrong frozen density source columns')
    potentials=read_coefficients_gzip(potential_path)
    if set(potentials)!={'V_D','V_Qpp'}:raise ValueError('Wrong complete potential column contract')
    expected=plan['filplot_expected']
    p2=parse_qe_filplot(p2_path,expected_plot_num=2,expected=dict(expected,unit='Ha'))
    p0=parse_qe_filplot(p0_path,expected_plot_num=0,expected=dict(expected,unit='electron/bohr^3'))
    historical={key:json.loads((root/PUBLIC_SOURCES[key]).read_text()) for key in ('ledger','common','radial')}
    out=replay_fields({'A':d['A_out'],'B':d['B_out'],'Q':q['QE']},{'D':potentials['V_D'],'Qpp':potentials['V_Qpp']},p2,p0,
        physical=plan['physical'],historical=historical,probes=plan['direct_fourier_miller_points'],thresholds=plan['thresholds'],
        original_fields=original_fields)
    out['source_sha256']={PUBLIC_SOURCES[k]:v for k,v in bound.items()}
    out['new_source_sha256']={key:hashlib.sha256(Path(path).read_bytes()).hexdigest() for key,path in
        [('potential_coefficients',potential_path),('P2_filplot',p2_path),('P0_filplot',p0_path)]}
    out['native_filplot']={key:{name:p[name] for name in ('source_sha256','stored_sha256','physical_count','padding_count_excluded','grid','allocated_grid','unit','native_unit','unit_scale','parse_status','expected_validation_status')}
        for key,p in [('P2',p2),('P0',p0)]}
    return out
