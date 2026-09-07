#!/usr/bin/env python3
"""Independent spinor Fourier density and kinetic arithmetic on fixed states.

Uses existing NumPy FFTs, ordinary mathematical reciprocal geometry, and a
separate integer-support correlation sum. No QR, normalization, occupation
solve, Hamiltonian, potential or projector evaluation is performed. Inputs are
never modified. All bands, including original zero occupations, are retained.
"""
from __future__ import annotations

import hashlib
import math
import numpy as np

DEFAULT_THRESHOLDS={
    'reciprocal_duality_abs':1e-12,'k_cart_abs_bohr_inv':1e-12,'cutoff_slack_ha':1e-10,
    'state_norm_abs':1e-9,'gram_frobenius':1e-9,'electron_count_abs':1e-8,
    'kinetic_paths_abs_ha':1e-9,'kinetic_history_abs_ha':1e-9,
    'q_density_coefficient_max_abs':1e-10,'q_density_nonzero_relative_l2':1e-9,
    'ab_density_relative_l2':1e-9,'ab_density_node_max_abs':1e-10,
    'direct_correlation_abs':1e-11,'analytic_normalized':1e-12,'ledger_abs_ha':1e-10,
}


class OrbitalAuditError(ValueError):
    def __init__(self,reason,status='FAIL'):
        super().__init__(reason);self.status=status;self.reason=reason


def _require(condition,reason,status='FAIL'):
    if not condition:raise OrbitalAuditError(reason,status)


def _array(value,dtype,shape,label):
    _require(isinstance(value,np.ndarray) and value.dtype==np.dtype(dtype),'Wrong exact dtype for '+label)
    _require(value.shape==tuple(shape),'Wrong shape for '+label)
    _require(np.isfinite(value).all(),'Nonfinite '+label)
    return value


def _fsum(value):return math.fsum(np.asarray(value).reshape(-1).tolist())


def _abs2(value):return value.real*value.real+value.imag*value.imag


def _fingerprint(state):
    out={}
    for name in ('lattice_columns','reciprocal_columns'):
        a=state[name];out[name]={'shape':list(a.shape),'dtype':a.dtype.str,'sha256':hashlib.sha256(a.tobytes(order='C')).hexdigest()}
    for ik,point in enumerate(state['kpoints']):
        for name in ('millers','coefficients','occupations','eigenvalues','k_cart','weight'):
            a=np.asarray(point[name]);out[str(ik)+'/'+name]={'shape':list(a.shape),'dtype':a.dtype.str,
                'sha256':hashlib.sha256(a.tobytes(order='C')).hexdigest()}
    return out


def block_to_interleaved(coefficients):
    _require(isinstance(coefficients,np.ndarray) and coefficients.dtype==np.dtype('complex128')
             and coefficients.ndim==3 and coefficients.shape[0]==2,'Expected two block components')
    # Explicit G,spin,band order. No conjugation or relative spin phase change.
    return coefficients.transpose(1,0,2).reshape(2*coefficients.shape[1],coefficients.shape[2]).copy()


def _geometry(state,physical,t):
    a=_array(state['lattice_columns'],'float64',(3,3),'lattice')
    b=_array(state['reciprocal_columns'],'float64',(3,3),'reciprocal lattice')
    expected_a=np.asarray(physical['lattice_vectors_bohr'],dtype=np.float64).T
    _require(np.array_equal(a,expected_a),'Lattice differs from fixed column-vector geometry')
    volume=float(np.linalg.det(a));_require(math.isfinite(volume) and volume>0,'Nonpositive cell volume')
    error=float(np.max(np.abs(a.T@b/(2*math.pi)-np.eye(3))))
    _require(error<=t['reciprocal_duality_abs'],'Reciprocal columns fail A^T B/(2pi)=I')
    return a,b,volume,error


def _support_and_q(point,ik,b,physical,t):
    m=point['millers'];_require(isinstance(m,np.ndarray) and m.dtype==np.dtype('int64') and m.ndim==2
                               and m.shape[1]==3 and 1<=len(m)<=100_000,'Invalid integer Miller matrix')
    # Two comparisons also reject typemin(int64), whose abs would overflow.
    _require(np.all((-1_000_000<m)&(m<1_000_000)),'Unbounded Miller index')
    _require(len({tuple(x) for x in m.tolist()})==len(m),'Duplicate wavefunction Miller vector')
    k=_array(point['k_cart'],'float64',(3,),'k Cartesian')
    expected_k=b@np.asarray(physical['kpoints'][ik],dtype=np.float64)
    k_error=float(np.max(np.abs(k-expected_k)))
    _require(k_error<=t['k_cart_abs_bohr_inv'],'k Cartesian does not match this original k slot')
    q=m@b.T+k[None,:]
    kinetic=np.array([.5*math.fsum(float(x*x) for x in row) for row in q],dtype=np.float64)
    _require(float(kinetic.max())<=physical['ecut_ha']+t['cutoff_slack_ha'],'Actual G+k exceeds original kinetic cutoff')
    return m,q,kinetic,k_error


def product_support(miller_sets,fft_size):
    """Direct integer G-G certificate, independent of coefficient values/FFT.

    For even grids, a possible pair +/-Nyquist is ambiguous and rejected;
    neither endpoint is silently identified with its opposite physical mode.
    """
    size=np.asarray(fft_size,dtype=np.int64)
    _require(size.shape==(3,) and np.all(size>=2) and math.prod(size.tolist())<=1_000_000,'Unsupported FFT grid')
    count=math.prod(size.tolist());present=np.zeros(count,dtype=bool);ranges=[]
    for m in miller_sets:
        extent=m.max(axis=0)-m.min(axis=0)
        _require(np.all(2*extent<size),'Orbital products cannot be represented without Nyquist/alias ambiguity','UNSUPPORTED_PRODUCT_GRID')
        ranges.append(extent.tolist())
        for start in range(0,len(m),64):
            difference=m[start:start+64,None,:]-m[None,:,:]
            bins=difference%size
            code=bins[:,:,0]+size[0]*(bins[:,:,1]+size[1]*bins[:,:,2])
            present[code.reshape(-1)]=True
    codes=np.flatnonzero(present)
    bins=np.column_stack((codes%size[0],(codes//size[0])%size[1],codes//(size[0]*size[1])))
    millers=(bins+size//2)%size-size//2
    return millers.astype(np.int64),{'status':'PASS','same_k_difference_extents':ranges,
        'possible_product_count':len(millers),'nyquist_ambiguous_products':0,
        'method':'All same-k integer G-G pairs, blocked direct enumeration; strict unique finite-grid representatives'}


def correlation_modes(state,millers,volume):
    """Independent non-modular reciprocal correlation; no FFT/reconstruction."""
    result={}
    _require(len(millers)==17 and len({tuple(m) for m in millers})==17,'Exactly 17 distinct declared density probes required')
    for raw in millers:
        _require(len(raw)==3 and all(type(i) is int for i in raw),'Noninteger correlation probe')
        g=tuple(raw);real_terms=[];imag_terms=[]
        for point in state['kpoints']:
            mapping={tuple(m):i for i,m in enumerate(point['millers'].tolist())};left=[];right=[]
            for m,i in mapping.items():
                target=tuple(a+b for a,b in zip(m,g))
                if target in mapping:left.append(mapping[target]);right.append(i)
            if not left:continue
            c=point['coefficients'];products=c[:,left,:]*c[:,right,:].conjugate()
            weights=float(point['weight'])*point['occupations']
            weighted=products*weights[None,None,:]
            real_terms.append(_fsum(weighted.real));imag_terms.append(_fsum(weighted.imag))
        result[g]=complex(math.fsum(real_terms),math.fsum(imag_terms))/volume
    return result


def _density_coefficients(density,size):
    spectrum=np.fft.fftn(density.reshape(tuple(size),order='F'))/len(density)
    ranges=[range(-(n//2),n-n//2) for n in size]
    return {(i,j,k):complex(spectrum[i%size[0],j%size[1],k%size[2]]) for i in ranges[0] for j in ranges[1] for k in ranges[2]}


def _reference_density(label,actual,n,reference,products,t):
    source=reference['density_coefficients']
    _require(isinstance(source,dict) and (0,0,0) in source and len(source)>1,'Missing bound reference density coefficients')
    _require(all(isinstance(m,tuple) and len(m)==3 and all(type(x) is int for x in m) for m in source),'Reference Miller indices must be exact integer tuples')
    _require(set(source)<=set(actual),'Reference density has an unsupported grid representative')
    _require(all(math.isfinite(complex(z).real) and math.isfinite(complex(z).imag) for z in source.values()),'Nonfinite reference density')
    modes=sorted(source);nz=[m for m in modes if m!=(0,0,0)]
    errors=[actual[m]-source[m] for m in modes]
    numerator=math.sqrt(math.fsum(abs(actual[m]-source[m])**2 for m in nz))
    denominator=math.sqrt(math.fsum(abs(source[m])**2 for m in nz))
    relative=numerator/denominator if denominator>0 else (0.0 if numerator==0 else None)
    max_error=max(abs(z) for z in errors)
    product_set={tuple(m) for m in products.tolist()};outside_products=product_set-set(source)
    outside=[m for m in actual if m not in source]
    report={'coefficient_max_abs':max_error,'common_coefficient_count':len(source),
        'common_nonzero_difference_l2':numerator,'reference_nonzero_l2':denominator,
        'common_nonzero_relative_l2':relative,'zero_reference_denominator':denominator==0,
        'zero_reference_rule':'When reference fluctuations are exactly zero, apply the declared absolute coefficient maximum only; relative L2 is not defined unless the difference is also exactly zero',
        'outside_saved_coefficient_l2':math.sqrt(math.fsum(abs(actual[m])**2 for m in outside)),
        'outside_saved_coefficient_max_abs':max((abs(actual[m]) for m in outside),default=0.),
        'outside_saved_mode_count':len(outside),'possible_products_outside_saved_count':len(outside_products),
        'scope':'FULL_FINITE_PRODUCT_SUPPORT_WITHIN_SAVED_G' if not outside_products else 'PROJECTED_ON_SAVED_DENSITY_G',
        'unknown_physical_modes_assumed_zero':False}
    if label=='Q':
        passed=max_error<=t['q_density_coefficient_max_abs'] and (denominator==0 or (relative is not None and relative<=t['q_density_nonzero_relative_l2']))
    else:
        _require(len(source)==len(actual),'A/B require full original native density coefficient support')
        original=_array(reference['density_real'],'float64',(len(n),),'original n_out')
        diff=n-original;dn=math.sqrt(_fsum(diff*diff));norm=math.sqrt(_fsum(original*original))
        rel=dn/norm if norm else (0. if dn==0 else None)
        maximum=float(np.max(np.abs(diff)))
        report.update(original_node_relative_l2=rel,original_node_max_abs=maximum,
            original_n_out_sha256=hashlib.sha256(original.tobytes(order='C')).hexdigest())
        passed=(rel is not None and rel<=t['ab_density_relative_l2'] and maximum<=t['ab_density_node_max_abs']
                and max_error<=t['ab_density_node_max_abs'])
    report['status']='PASS' if passed else 'FAIL'
    return report


def evaluate_orbitals(state,physical,thresholds,reference):
    """Fixed source state -> small measured report and private derived arrays.

    Required state arrays use true matrix columns for lattice/reciprocal,
    millers(NG,3), complex coefficients(2,NG,n_states). physical kpoints are
    fractional; the stored source k_cart remains untouched. Reference binding
    to raw-file identities is the recorder's responsibility, not a norm test.
    """
    t={key:thresholds[key] for key in DEFAULT_THRESHOLDS}
    _require(all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in t.values()),'Invalid thresholds')
    label=state['label'];_require(label in ('A','B','Q'),'Unknown original state label')
    size=tuple(physical['fft_size']);nb=physical['n_states'];count=math.prod(size)
    _require(type(nb) is int and nb>0 and nb<=1000,'Invalid declared state count')
    _require(type(physical['expected_electrons']) in (int,float) and math.isfinite(physical['expected_electrons'])
             and physical['expected_electrons']>0,'Invalid expected electron count')
    _require(len(state['kpoints'])==len(physical['kpoints'])==len(physical['kweights'])>0,'k slot count mismatch')
    a,b,volume,dual_error=_geometry(state,physical,t)
    source_before=_fingerprint(state);prepared=[];norm_reports=[];weights=[]
    for ik,point in enumerate(state['kpoints']):
        m,q,kin,k_error=_support_and_q(point,ik,b,physical,t)
        c=_array(point['coefficients'],'complex128',(2,len(m),nb),'block spinor coefficients')
        f=_array(point['occupations'],'float64',(nb,),'original occupations')
        eig=_array(point['eigenvalues'],'float64',(nb,),'original eigenvalues')
        w=np.asarray(point['weight']);_require(w.shape==() and w.dtype==np.dtype('float64') and np.isfinite(w),'Invalid scalar spatial weight')
        weight=float(w);_require(weight>0 and weight==physical['kweights'][ik],'Original spatial weight/order mismatch')
        _require(np.all((f>=0)&(f<=1)),'Explicit spinor capacity is one; invalid original occupation')
        weights.append(weight);flat=c.reshape(2*len(m),nb)
        norms=[_fsum(_abs2(c[:,:,band])) for band in range(nb)]
        gram=float(np.linalg.norm(flat.conjugate().T@flat-np.eye(nb),ord='fro'))
        _require(all(math.isfinite(x) for x in norms) and math.isfinite(gram),'Nonfinite derived norm or Gram matrix')
        norm_error=max(abs(x-1) for x in norms)
        norm_reports.append({'k_index_zero_based':ik,'NG':len(m),'norms':norms,'maximum_norm_error':norm_error,
            'gram_frobenius':gram,'k_cart_max_abs_error':k_error,'cutoff_max_ha':float(kin.max()),
            'status':'PASS' if norm_error<=t['state_norm_abs'] and gram<=t['gram_frobenius'] else 'FAIL'})
        prepared.append((point,m,q,kin,c,f,eig,weight,norms))
    _require(abs(math.fsum(weights)-1)<=t['reciprocal_duality_abs'],'Spatial weights must sum to one exactly within declared tolerance')
    products,product_report=product_support([x[1] for x in prepared],size)
    r11=np.zeros(count);r22=np.zeros(count);r12=np.zeros(count,dtype=np.complex128)
    per_k=[];density_k_electrons=[];factor=count/math.sqrt(volume);dvol=volume/count
    for ik,(point,m,q,kin,c,f,eig,weight,norms) in enumerate(prepared):
        bins=m%np.array(size);grid=np.zeros((2,*size,nb),dtype=np.complex128)
        grid[:,bins[:,0],bins[:,1],bins[:,2],:]=c
        u=np.fft.ifftn(grid,axes=(1,2,3))*factor
        flat_u=u.reshape((2,count,nb),order='F');wf=weight*f
        r11+=np.sum(_abs2(flat_u[0])*wf[None,:],axis=1)
        r22+=np.sum(_abs2(flat_u[1])*wf[None,:],axis=1)
        r12+=np.sum(flat_u[0]*flat_u[1].conjugate()*wf[None,:],axis=1)
        density_k_electrons.append(dvol*_fsum((_abs2(flat_u[0])+_abs2(flat_u[1]))*wf[None,:]))
        direct=[_fsum(_abs2(c[:,:,band])*kin[None,:]) for band in range(nb)]
        gradient=[0.0]*nb
        for alpha in range(3):
            derivative_grid=np.zeros_like(grid)
            derivative_grid[:,bins[:,0],bins[:,1],bins[:,2],:]=1j*q[:,alpha][None,:,None]*c
            derivative=np.fft.ifftn(derivative_grid,axes=(1,2,3))*factor
            for band in range(nb):gradient[band]+=.5*dvol*_fsum(_abs2(derivative[...,band]))
        rows=[{'band_one_based':band+1,'occupation':float(f[band]),'eigenvalue_ha':float(eig[band]),
            'norm':norms[band],'kinetic_unweighted_ha':direct[band],'gradient_unweighted_ha':gradient[band],
            'kinetic_weighted_ha':weight*float(f[band])*direct[band],
            'gradient_weighted_ha':weight*float(f[band])*gradient[band],
            'signed_path_difference_ha':direct[band]-gradient[band]} for band in range(nb)]
        per_k.append({'k_index_zero_based':ik,'weight_spatial':weight,'k_cart_bohr_inv':point['k_cart'].tolist(),
            'NG':len(m),'states':rows,'kinetic_ha':math.fsum(r['kinetic_weighted_ha'] for r in rows),
            'gradient_kinetic_ha':math.fsum(r['gradient_weighted_ha'] for r in rows)})
    density=r11+r22;pauli=np.vstack((2*r12.real,-2*r12.imag,r11-r22))
    _require(np.isfinite(density).all() and np.isfinite(pauli).all(),'Nonfinite reconstructed density')
    coefficients=_density_coefficients(density,size)
    direct17=correlation_modes(state,physical['direct_fourier_miller_points'],volume);correlation=[]
    for m,z in direct17.items():
        _require(m in coefficients,'Declared direct probe outside native density grid')
        fft=coefficients[m];error=abs(z-fft)
        correlation.append({'miller':list(m),'correlation':[z.real,z.imag],'FFT':[fft.real,fft.imag],
                            'absolute_difference':error,'status':'PASS' if error<=t['direct_correlation_abs'] else 'FAIL'})
    ne_f=math.fsum(w*float(fn) for _,_,_,_,_,f,_,w,_ in prepared for fn in f)
    ne_norm=math.fsum(w*float(fn)*norm for _,_,_,_,_,f,_,w,norms in prepared for fn,norm in zip(f,norms))
    ne_real=dvol*_fsum(density);ne_expected=physical['expected_electrons']
    electron_errors={'occupations_minus_expected':ne_f-ne_expected,'norm_weighted_minus_expected':ne_norm-ne_expected,
        'real_density_minus_expected':ne_real-ne_expected,'real_minus_norm_weighted':ne_real-ne_norm}
    electron_status='PASS' if max(abs(x) for x in electron_errors.values())<=t['electron_count_abs'] else 'FAIL'
    kinetic=math.fsum(k['kinetic_ha'] for k in per_k);gradient=math.fsum(k['gradient_kinetic_ha'] for k in per_k)
    _require(all(math.isfinite(r[key]) for k in per_k for r in k['states']
                 for key in ('kinetic_unweighted_ha','gradient_unweighted_ha','kinetic_weighted_ha','gradient_weighted_ha'))
             and math.isfinite(kinetic) and math.isfinite(gradient),'Nonfinite derived kinetic arithmetic')
    kinetic_report={'direct_ha':kinetic,'gradient_ha':gradient,'signed_difference_ha':kinetic-gradient,
        'status':'PASS' if abs(kinetic-gradient)<=t['kinetic_paths_abs_ha'] else 'FAIL',
        'evidence_kind':'DIRECT_REEVALUATION_OF_KINETIC_FROM_ORIGINAL_QE_WFC' if label=='Q' else 'DIRECT_REEVALUATION_OF_KINETIC_FROM_ORIGINAL_DFTK_X',
        'summation':'Direct: stable coefficient-probability sum with physical G+k. Independent: three covariant-derivative IFFTs and real-space squared integrals.'}
    if label!='Q':
        historical=float(reference['kinetic_ha']);_require(math.isfinite(historical),'Nonfinite historical kinetic reference')
        kinetic_report.update(historical_ha=historical,historical_signed_difference_ha=kinetic-historical,
            same_source_status='PASS' if abs(kinetic-historical)<=t['kinetic_history_abs_ha'] else 'FAIL')
    else:kinetic_report['same_source_status']='NO_INDEPENDENT_NATIVE_QE_T_FIELD'
    density_report=_reference_density(label,coefficients,density,reference,products,t)
    eband=math.fsum(w*float(fn)*float(en) for _,_,_,_,_,f,eig,w,_ in prepared for fn,en in zip(f,eig))
    band_report={'sum_w_f_epsilon_ha':eband,'status':'NOT_REQUESTED',
        'scope':'Original XML/checkpoint occupation-energy bookkeeping only; not a Hamiltonian residual or kinetic identity'}
    if 'eband_ha' in reference:
        halfwidth=float(reference['eband_print_halfwidth_ha']);_require(math.isfinite(halfwidth) and halfwidth>=0,'Invalid native eband print interval')
        _require(math.isfinite(float(reference['eband_ha'])),'Nonfinite native eband reference')
        diff=eband-float(reference['eband_ha']);allowed=t['ledger_abs_ha']+halfwidth
        band_report.update(native_eband_ha=float(reference['eband_ha']),signed_difference_ha=diff,allowed_ha=allowed,
            print_halfwidth_ha=halfwidth,status='PASS' if abs(diff)<=allowed else 'FAIL')
    source_after=_fingerprint(state);_require(source_after==source_before,'Original input array bytes changed')
    gates=[all(x['status']=='PASS' for x in norm_reports),electron_status=='PASS',kinetic_report['status']=='PASS',
        density_report['status']=='PASS',all(x['status']=='PASS' for x in correlation),band_report['status']!='FAIL']
    if label!='Q':gates.append(kinetic_report['same_source_status']=='PASS')
    report={'schema_version':1,'label':label,'status':'PASS' if all(gates) else 'FAIL','all_required_gates_passed':all(gates),
        'spinor_layout':'coefficients[spin,G,band], block components; capacity one','state_count':nb,'k_count':len(prepared),
        'volume_bohr3':volume,'reciprocal_duality_max_abs':dual_error,'fft_size':list(size),
        'normalization_and_gram':norm_reports,'electrons':{'from_occupations':ne_f,'from_actual_norms':ne_norm,
            'from_real_density':ne_real,'per_k_real_contributions':density_k_electrons,'errors':electron_errors,'status':electron_status},
        'product_support':product_report,'same_source_orbital_density':density_report,'direct_correlation_checks':correlation,
        'kinetic':kinetic_report,'per_k':per_k,'eband_bookkeeping':band_report,
        'pauli_diagnostic':{'n_min':float(density.min()),'m_max_norm':float(np.max(np.sqrt(np.sum(pauli*pauli,axis=0)))),
            'sigma_y_convention':'m_y=-2 Im(sum wf u_up conj(u_down))',
            'scope':'New orbital Pauli diagnostic, not magnetization read from G40 charge and not evidence of noncollinear XC'},
        'input_array_fingerprints':source_before,'input_bytes_unchanged':True,'normalization_or_QR_applied':False,
        'new_scf_status':'NOT_RUN','new_eigensolve_status':'NOT_RUN','new_occupation_solve_status':'NOT_RUN',
        'new_xc_evaluation_status':'NOT_RUN','new_qe_pp_execution_status':'NOT_RUN',
        'physical_convergence_status':'NOT_ESTABLISHED','numerical_review_status':'REVIEW_REQUIRED',
        'independent_native_qe_nonlocal_status':'NOT_MEASURED','qe_original_input_hamiltonian_residual_status':'NOT_AVAILABLE',
        'backend':{'numpy_version':np.__version__,'complex_dtype':'complex128','real_dtype':'float64'},
        'FFT_convention':'ifftn(c_grid)*Ngrid/sqrt(volume); physical first-index-fast order; same-k density sum then spatial weights once'}
    return {'report':report,'density_real':density,'pauli_density':pauli,'density_coefficients':coefficients,'product_millers':products}
