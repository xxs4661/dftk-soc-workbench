# Current-orbital, charge-only LDA/GGA energy. No fixed-density eigenvalues or
# scalar nonlocal energy enter this adapter; no density is fed to an eigensolve.
const FR_ENERGY_NAMES = Set(["Kinetic", "AtomicLocal", "AtomicNonlocalFR",
    "Hartree", "Xc", "Ewald", "PspCorrection"])
const COMMON_ENERGY_NAMES = setdiff(FR_ENERGY_NAMES, Set(["AtomicNonlocalFR"]))

integration_error(a,b) = norm(a-b)/max(norm(a),norm(b),1)

function check_energy_orbitals(basis,X,f)
    length(X)==length(f)==length(basis.kpoints)>0 ||
        throw(DimensionMismatch("One spinor matrix and occupation vector per k point required"))
    weights=SpinorPrototype._density_checked_weights(basis.kweights,length(X))
    count=0.0
    for (ik,(x,occ)) in enumerate(zip(X,f))
        x isa AbstractMatrix && eltype(x)==ComplexF64 && size(x,2)>0 &&
            size(x,1)==2length(DFTK.G_vectors(basis,basis.kpoints[ik])) ||
            throw(DimensionMismatch("Energy orbitals need ComplexF64 interleaved 2NG-by-state matrices"))
        occ isa AbstractVector && length(occ)==size(x,2) ||
            throw(DimensionMismatch("Occupation and orbital columns differ"))
        all(isfinite,x) && all(v->v isa Real && isfinite(v) && 0<=v<=1,occ) ||
            throw(ArgumentError("Finite orbitals and explicit capacity-one occupations required"))
        for state in eachindex(occ)
            count+=weights[ik]*occ[state]*sum(abs2,@view x[:,state])
        end
    end
    ne=basis.model.n_electrons
    ne isa Real && isfinite(ne) && ne>0 || throw(ArgumentError("Invalid model valence electron count"))
    abs(sum(weights.*sum.(f))-ne)<=1e-8 || throw(ArgumentError("Occupation count differs from model valence count"))
    abs(count-ne)<=1e-8 || throw(ArgumentError("Orbital norms/occupations change the valence electron count"))
    count
end

"""Owned spatial factors preserve spinor components; no component QR or capacity-two refill."""
function energy_factors(basis,X,f)
    check_energy_orbitals(basis,X,f)
    (;chi=[hcat(x[1:2:end,:],x[2:2:end,:]) for x in X],
      fchi=[vcat(occ,occ) for occ in f])
end

"""One reusable k tensor feeding the unchanged density accumulator in its original order.
Views returned by this internal adapter are transient. No consumer may retain a k
tensor across iteration; density_from_real_states only consumes it synchronously.
"""
mutable struct _StreamingRealStates{B,S} <: AbstractVector{Array{ComplexF64,3}}
    basis::B
    X::S
    cached_k::Int
    workspace::Union{Nothing,Array{ComplexF64,3}}
    evaluations::Int
end
_StreamingRealStates(basis,X)=_StreamingRealStates(basis,X,0,nothing,0)
Base.size(states::_StreamingRealStates)=(length(states.X),)
Base.IndexStyle(::Type{<:_StreamingRealStates})=IndexLinear()
function Base.getindex(states::_StreamingRealStates,ik::Int)
    checkbounds(states,ik)
    if ik!=states.cached_k
        transformed=SpinorPrototype.component_ifft(states.basis,states.basis.kpoints[ik],
            SpinorPrototype.unflatten_components(states.X[ik],2))
        if isnothing(states.workspace) || size(states.workspace)!=size(transformed)
            states.workspace=transformed
        else
            copyto!(states.workspace,transformed)
        end
        states.cached_k=ik;states.evaluations+=1
    end
    states.workspace::Array{ComplexF64,3}
end

function orbital_density(basis,X,f;stream_k=false)
    stream_k isa Bool || throw(ArgumentError("stream_k must be boolean"))
    check_energy_orbitals(basis,X,f)
    # Empty columns are retained so even an entirely empty k point has a valid
    # array shape. The frozen density accumulator skips its zero occupations.
    states=stream_k ? _StreamingRealStates(basis,X) : [SpinorPrototype.component_ifft(basis,k,
        SpinorPrototype.unflatten_components(x,2)) for (k,x) in zip(basis.kpoints,X)]
    SpinorPrototype.density_from_real_states(states,basis.kweights,f)
end

function energy_valence_rho(basis,n)
    n isa AbstractVector && length(n)==prod(basis.fft_size) ||
        throw(DimensionMismatch("Valence density needs the basis real-grid length"))
    all(v->v isa Real && isfinite(v),n) || throw(ArgumentError("Nonfinite/nonreal valence density"))
    minimum(n)>=-64eps(Float64)*max(1,maximum(abs,n)) || throw(ArgumentError("Negative valence density; no clipping"))
    abs(basis.dvol*sum(n)-basis.model.n_electrons)<=1e-8 ||
        throw(ArgumentError("Valence density count differs from model electron count"))
    reshape(Float64.(n),basis.fft_size...,1)
end

"""Independent P_up/P_down contraction, retaining the interference term [Ha/cell]."""
function nonlocal_spin_decomposition(operators,X,weights,f)
    full=RelativisticProjectors.nonlocal_energy(operators,X,weights,f)
    up,down,cross,projected=0.0,0.0,0.0,0.0
    for (op,x,w,occ) in zip(operators,X,weights,f)
        cu=op.P[1:2:end,:]'*x[1:2:end,:]
        cd=op.P[2:2:end,:]'*x[2:2:end,:]
        du,dd=op.D*cu,op.D*cd
        for state in eachindex(occ)
            factor=w*occ[state]
            up+=factor*real(dot(cu[:,state],du[:,state]))
            down+=factor*real(dot(cd[:,state],dd[:,state]))
            cross+=factor*real(dot(cu[:,state],dd[:,state])+dot(cd[:,state],du[:,state]))
            projected+=factor*real(dot(cu[:,state]+cd[:,state],du[:,state]+dd[:,state]))
        end
    end
    result=(;full_ha=full,up_ha=up,down_ha=down,diagonal_ha=up+down,cross_ha=cross,
        projected_full_ha=projected,decomposition_difference_ha=full-up-down-cross,
        projected_normalized_error=integration_error(full,projected))
    all(isfinite,values(result)) || throw(ArgumentError("Nonfinite nonlocal spin decomposition"))
    result
end

"""Actual occupied expectation of supplied blocks, never an old eigenvalue sum."""
function occupied_expectation(blocks,X,weights,f)
    length(blocks)==length(X)==length(weights)==length(f) || throw(DimensionMismatch("Expectation k-point count mismatch"))
    value=0.0
    for (h,x,w,occ) in zip(blocks,X,weights,f)
        hx=h*x
        for n in eachindex(occ)
            value+=w*occ[n]*real(dot(x[:,n],hx[:,n]))
        end
    end
    isfinite(value) || throw(ArgumentError("Nonfinite Hamiltonian expectation"))
    value
end

"""
Current X -> R,n,m -> six common terms and H_common[n_X] -> one spinor FR term.
TermXc internally adds its immutable core density once and retains its complete
GGA divergence contribution. Hartree, electron counts and n*vxc use valence n.
"""
function energy_snapshot(ctx,X,f;expected_n=nothing,stream_k=false)
    validate_context(ctx)
    basis=ctx.basis
    factors=energy_factors(basis,X,f)
    density=orbital_density(basis,X,f;stream_k)
    rho=energy_valence_rho(basis,density.n)
    if !isnothing(expected_n)
        expected_n isa AbstractVector && length(expected_n)==length(density.n) &&
            all(v->v isa Real && isfinite(v),expected_n) || throw(ArgumentError("Invalid expected density"))
        norm(expected_n-density.n)<=1e-12*max(norm(density.n),1) ||
            throw(ArgumentError("Supplied density is not generated by these orbitals"))
    end
    common=DFTK.energy_hamiltonian(basis,factors.chi,factors.fchi;ρ=rho)
    terms=Dict{String,Float64}(pairs(common.energies))
    Set(keys(terms))==COMMON_ENERGY_NAMES || throw(ArgumentError("Common energy must contain exactly six terms without native nonlocal"))
    ham=compose_full_hamiltonian(ctx,common.ham)
    nl=nonlocal_spin_decomposition(ctx.fr_blocks,X,basis.kweights,f)
    terms["AtomicNonlocalFR"]=nl.full_ha
    total=Float64(common.energies.total)+nl.full_ha
    all(isfinite,values(terms)) && isfinite(total) || throw(ArgumentError("Nonfinite full energy"))

    term(T)=only(filter(t->t isa T,basis.terms))
    kinetic,localterm,hartree,xc=term(DFTK.TermKinetic),term(DFTK.TermAtomicLocal),term(DFTK.TermHartree),term(DFTK.TermXc)
    atomic_local=vec(localterm.potential_values)
    local_potential=vec(DFTK.total_local_potential(common.ham))
    vH=vec(DFTK.apply_kernel(hartree,basis,rho))
    vxc=local_potential-atomic_local-vH # Full DFTK GGA potential, not only ∂e/∂n.
    integral_n_vxc=basis.dvol*dot(density.n,vxc)
    band=occupied_expectation(ham,X,basis.kweights,f)
    dc=band-terms["Hartree"]-integral_n_vxc+terms["Xc"]+terms["Ewald"]+terms["PspCorrection"]
    direct_kinetic=sum(basis.kweights[ik]*occ[n]*real(dot(x[:,n],
        repeat(kinetic.kinetic_energies[ik];inner=2).*x[:,n]))
        for (ik,(x,occ)) in enumerate(zip(X,f)) for n in eachindex(occ))
    component_norms=[sum(abs2,@view x[s:2:end,n]) for (x,occ) in zip(X,f)
        for n in eachindex(occ) if occ[n]>0 for s in 1:2]
    report=(;electron_count_real=basis.dvol*sum(density.n),
        electron_count_reciprocal=check_energy_orbitals(basis,X,f),
        expected_valence_electrons=basis.model.n_electrons,
        component_norm_min=minimum(component_norms),component_norm_max=maximum(component_norms),
        native_nonlocal_terms=count(t->t isa DFTK.TermAtomicNonlocal,basis.terms),
        direct_kinetic_ha=direct_kinetic,direct_kinetic_difference_ha=direct_kinetic-terms["Kinetic"],
        local_integral_difference_ha=basis.dvol*dot(density.n,atomic_local)-terms["AtomicLocal"],
        hartree_half_integral_difference_ha=basis.dvol*dot(density.n,vH)/2-terms["Hartree"],
        ewald_reference_ha=term(DFTK.TermEwald).energy,
        psp_correction_reference_ha=term(DFTK.TermPspCorrection).energy,
        ewald_once_difference_ha=terms["Ewald"]-term(DFTK.TermEwald).energy,
        psp_correction_once_difference_ha=terms["PspCorrection"]-term(DFTK.TermPspCorrection).energy,
        integral_n_vxc_ha=integral_n_vxc,band_expectation_ha=band,
        double_counting_total_ha=dc,double_counting_difference_ha=dc-total,
        energy_term_sum_difference_ha=sum(values(terms))-total,
        core_electron_integral=isnothing(xc.ρcore) ? 0.0 : basis.dvol*sum(xc.ρcore),
        nlcc_present=!isnothing(xc.ρcore),
        density_source="These spinors and capacity-one occupations; n_X, not n_ref",
        xc_scope="One six-term energy_hamiltonian traversal; full frozen charge-only LDA/GGA potential, core added internally")
    all(v->!(v isa Number) || isfinite(v),values(report)) || throw(ArgumentError("Nonfinite energy diagnostics"))
    snapshot=(;density,rho,ham,common_ham=common.ham,terms,total,report,
        nonlocal_decomposition=nl,local_potential,vH,vxc)
    assert_energy_consistency(snapshot)
    snapshot
end

"""Numerical consistency gate, also usable with explicitly corrupted test records."""
function assert_energy_consistency(snapshot;energy_atol=1e-8,nonlocal_tol=1e-11)
    Set(keys(snapshot.terms))==FR_ENERGY_NAMES || throw(ArgumentError("Full energy term identities changed"))
    all(isfinite,values(snapshot.terms)) && isfinite(snapshot.total) || throw(ArgumentError("Nonfinite energy record"))
    abs(sum(values(snapshot.terms))-snapshot.total)<=energy_atol || throw(ArgumentError("Full energy differs from its seven terms"))
    report=snapshot.report
    for key in (:direct_kinetic_difference_ha,:local_integral_difference_ha,
                :hartree_half_integral_difference_ha,:ewald_once_difference_ha,
                :psp_correction_once_difference_ha,:double_counting_difference_ha)
        value=getproperty(report,key)
        isfinite(value) && abs(value)<=energy_atol || throw(ArgumentError("Energy consistency failed: $key"))
    end
    report.native_nonlocal_terms==0 || throw(ArgumentError("Native nonlocal term duplicated in common model"))
    abs(snapshot.terms["Ewald"]-report.ewald_reference_ha)<=energy_atol &&
        abs(snapshot.terms["PspCorrection"]-report.psp_correction_reference_ha)<=energy_atol ||
        throw(ArgumentError("Per-cell Ewald/PspCorrection must each enter once"))
    nl=snapshot.nonlocal_decomposition
    integration_error(snapshot.terms["AtomicNonlocalFR"],nl.full_ha)<=nonlocal_tol &&
        nl.projected_normalized_error<=nonlocal_tol &&
        abs(nl.decomposition_difference_ha)<=nonlocal_tol || throw(ArgumentError("Full spinor nonlocal energy/decomposition differs"))
    # Recompute the double-counting expression against the reported total. This
    # catches corrupt totals even if a stale precomputed difference was retained.
    abs(report.band_expectation_ha-snapshot.terms["Hartree"]-report.integral_n_vxc_ha+
        snapshot.terms["Xc"]+snapshot.terms["Ewald"]+snapshot.terms["PspCorrection"]-
        snapshot.total)<=energy_atol || throw(ArgumentError("Actual H[n_X] expectation is inconsistent with energy"))
    true
end

"""Real scalar Si's synthetic full-spinor limit versus native seven-term factors."""
function compare_native_scalar_energy(ctx,X,f,native_basis)
    snapshot=energy_snapshot(ctx,X,f)
    native_basis.model.n_electrons==ctx.basis.model.n_electrons &&
        native_basis.fft_size==ctx.basis.fft_size &&
        native_basis.model.lattice==ctx.basis.model.lattice &&
        native_basis.model.positions==ctx.basis.model.positions &&
        native_basis.kweights==ctx.basis.kweights || throw(ArgumentError("Native scalar comparison basis differs"))
    length(native_basis.kpoints)==length(ctx.basis.kpoints) || throw(DimensionMismatch("Native comparison k-point count"))
    for (kn,kc) in zip(native_basis.kpoints,ctx.basis.kpoints)
        kn.coordinate==kc.coordinate && collect(DFTK.G_vectors(native_basis,kn))==collect(DFTK.G_vectors(ctx.basis,kc)) ||
            throw(ArgumentError("Native scalar comparison G/k ordering differs"))
    end
    factors=energy_factors(native_basis,X,f)
    native=DFTK.energy_hamiltonian(native_basis,factors.chi,factors.fchi;ρ=snapshot.rho)
    native_terms=Dict{String,Float64}(pairs(native.energies))
    native_terms["AtomicNonlocalFR"]=pop!(native_terms,"AtomicNonlocal")
    Set(keys(native_terms))==FR_ENERGY_NAMES || throw(ArgumentError("Native reference must have seven terms"))
    differences=Dict(name=>snapshot.terms[name]-native_terms[name] for name in keys(native_terms))
    (;snapshot,native_terms,term_differences_ha=differences,total_difference_ha=snapshot.total-native.energies.total,
      max_term_difference_ha=maximum(abs,values(differences)),
      scope="Real scalar Si, synthetic complete spin-degenerate channels; no Si SOC/SCF")
end
