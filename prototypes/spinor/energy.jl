# Restricted charge-only B0 bridge. Spatial component columns are weighted
# density-matrix factors, not independent normalized scalar electronic states.

const SPINOR_ENERGY_TERM_NAMES = Set(["Kinetic", "AtomicLocal", "AtomicNonlocal",
    "Hartree", "Xc", "Ewald", "PspCorrection"])

"""Reject models outside the inspected seven-term, unpolarized LDA/NLCC bridge."""
function check_supported_basis(basis)
    model = basis.model
    eltype(basis) == Float64 && basis.architecture isa DFTK.CPU ||
        throw(ArgumentError("Energy bridge requires a Float64 CPU basis"))
    model.spin_polarization == :none && model.n_spin_components == 1 &&
        model.temperature == 0 && model.n_electrons == 8 && isnothing(model.εF) ||
        throw(ArgumentError("Energy bridge requires eight electrons, :none and zero temperature"))
    length(model.symmetries) == 1 && length(basis.kpoints) == 8 &&
        DFTK.mpi_nprocs(basis.comm_kpts) == 1 ||
        throw(ArgumentError("Energy bridge requires eight unreduced spatial k points in one process"))
    SpinorPrototype._density_checked_weights(basis.kweights, length(basis.kpoints))
    model_names = string.(nameof.(typeof.(model.term_types)))
    length(model_names) == 7 && Set(model_names) == SPINOR_ENERGY_TERM_NAMES &&
        length(basis.terms) == 7 || throw(ArgumentError("Unsupported or repeated energy term"))
    expected_types = Dict("Kinetic"=>DFTK.TermKinetic, "AtomicLocal"=>DFTK.TermAtomicLocal,
        "AtomicNonlocal"=>DFTK.TermAtomicNonlocal, "Hartree"=>DFTK.TermHartree,
        "Xc"=>DFTK.TermXc, "Ewald"=>DFTK.TermEwald, "PspCorrection"=>DFTK.TermPspCorrection)
    all(term isa expected_types[name] for (name,term) in zip(model_names,basis.terms)) ||
        throw(ArgumentError("Model and instantiated energy terms do not match"))
    mt(name) = model.term_types[only(findall(==(name),model_names))]
    bt(name) = basis.terms[only(findall(==(name),model_names))]
    kinetic, hartree, xc = bt("Kinetic"), bt("Hartree"), bt("Xc")
    mt("Kinetic").scaling_factor == 1 && mt("Kinetic").blowup isa DFTK.BlowupIdentity &&
        kinetic.scaling_factor == 1 && mt("Hartree").scaling_factor == 1 &&
        hartree.scaling_factor == 1 || throw(ArgumentError("Modified kinetic/Hartree parameters"))
    xcm = mt("Xc")
    xcm.scaling_factor == 1 && xc.scaling_factor == 1 &&
        xcm.potential_threshold == 0 && xc.potential_threshold == 0 &&
        xcm.use_nlcc && !xcm.nlcc_from_vw && !isnothing(xc.ρcore) && isnothing(xc.τcore) ||
        throw(ArgumentError("Only the default charge LDA with existing NLCC is supported"))
    ids = [:lda_x, :lda_c_pw]
    for functionals in (xcm.functionals, xc.functionals)
        length(functionals) == 2 && all(isequal(fun,DFTK.DispatchFunctional(id))
                for (fun,id) in zip(functionals,ids)) ||
            throw(ArgumentError("Only default lda_x + lda_c_pw functionals are supported"))
    end
    isnothing(mt("Ewald").η) && bt("Ewald").η == DFTK.default_η(model.lattice) ||
        throw(ArgumentError("Modified Ewald splitting is outside this bridge"))
    length(model.atoms) == 2 && all(atom -> atom isa DFTK.ElementPsp &&
        atom.psp isa DFTK.PspUpf && DFTK.has_core_density(atom), model.atoms) ||
        throw(ArgumentError("Energy bridge requires the two NC-UPF atoms with NLCC"))
    (; kinetic, atomic_local=bt("AtomicLocal"), atomic_nonlocal=bt("AtomicNonlocal"),
       hartree, xc, ewald=bt("Ewald"), psp_correction=bt("PspCorrection"))
end

function _check_energy_orbitals(basis, X, f)
    length(X) == length(f) == length(basis.kpoints) ||
        throw(DimensionMismatch("One spinor matrix and occupation vector are required per k point"))
    SpinorPrototype._density_checked_weights(basis.kweights, length(X))
    for (ik,(x,occ)) in enumerate(zip(X,f))
        x isa AbstractMatrix && eltype(x) == ComplexF64 &&
            size(x,1) == 2length(DFTK.G_vectors(basis,basis.kpoints[ik])) ||
            throw(DimensionMismatch("Orbitals must be ComplexF64 matrices with 2NG interleaved rows"))
        occ isa AbstractVector && length(occ) == size(x,2) && length(occ) >= 8 ||
            throw(DimensionMismatch("Spinor occupations must match all orbital columns"))
        all(isfinite,x) && all(v -> v isa Real && isfinite(v),occ) ||
            throw(ArgumentError("Nonfinite orbitals or occupations"))
        all(==(1),occ[1:8]) && all(iszero,occ[9:end]) ||
            throw(ArgumentError("Only eight occupied capacity-one spinors and empty auxiliaries are supported"))
    end
end

"""Return owned chi=[Xup Xdown], fchi=[f;f], without normalization or new occupations."""
function spinor_factors(basis, X, f)
    _check_energy_orbitals(basis,X,f)
    chi = [hcat(x[1:2:end,:],x[2:2:end,:]) for x in X]
    fchi = [vcat(occ,occ) for occ in f]
    (; chi, fchi)
end

"""Reconstruct R,n,m from actual spinor orbitals; zero-occupation columns are skipped."""
function density_from_orbitals(basis, X, f)
    _check_energy_orbitals(basis,X,f)
    occupied = [findall(!iszero,occ) for occ in f]
    u = [component_ifft(basis,k,unflatten_components(x[:,indices],2))
         for (k,x,indices) in zip(basis.kpoints,X,occupied)]
    density_from_real_states(u,basis.kweights,[occ[indices] for (occ,indices) in zip(f,occupied)])
end

"""Validate an eight-valence-electron flat density and copy it into DFTK's (Nx,Ny,Nz,1)."""
function valence_rho(basis, n)
    n isa AbstractVector && length(n) == prod(basis.fft_size) ||
        throw(DimensionMismatch("Valence density must be a flat real-grid vector"))
    all(v -> v isa Real && isfinite(v),n) || throw(ArgumentError("Nonfinite/nonreal valence density"))
    minimum(n) >= -64eps(Float64)*max(1,maximum(abs,n)) ||
        throw(ArgumentError("Negative valence density beyond roundoff; no clipping is permitted"))
    abs(basis.dvol*sum(n)-8) <= 1e-8 || throw(ArgumentError("Valence electron count drift"))
    reshape(Float64.(n),basis.fft_size...,1)
end

"""
    energy_snapshot(basis, X, f; expected_n=nothing)

Evaluate the seven-term total energy from the supplied spinor orbitals and their
own valence density. Exactly one energy_hamiltonian traversal evaluates XC and
the per-cell constants. Optional expected_n checks density provenance; it never
substitutes for orbital reconstruction. No core density is added outside DFTK.
"""
function energy_snapshot(basis, X, f; expected_n=nothing)
    supported = check_supported_basis(basis)
    factors = spinor_factors(basis,X,f)
    density = density_from_orbitals(basis,X,f)
    rho = valence_rho(basis,density.n)
    if !isnothing(expected_n)
        expected_n isa AbstractVector && length(expected_n) == length(density.n) &&
            all(v -> v isa Real && isfinite(v),expected_n) ||
            throw(ArgumentError("Expected density must be a finite real-grid vector"))
        norm(expected_n-density.n) <= 1e-12*max(norm(density.n),1) ||
            throw(ArgumentError("Energy density does not match the supplied orbital-density provenance"))
    end
    # A single inspected traversal: quadratic factors for T/nonlocal, explicit
    # valence rho for local/Hartree/XC, and each physical-cell constant once.
    eh = DFTK.energy_hamiltonian(basis,factors.chi,factors.fchi; ρ=rho)
    terms = Dict{String,Float64}(pairs(eh.energies))
    Set(keys(terms)) == SPINOR_ENERGY_TERM_NAMES || error("Unexpected evaluated energy terms")
    total = Float64(eh.energies.total)
    all(isfinite,values(terms)) && isfinite(total) || error("Nonfinite spinor total energy")

    direct_kinetic, direct_nonlocal, band_expectation, electrons_reciprocal = 0.0,0.0,0.0,0.0
    component_norms = Float64[]
    for (ik,x) in enumerate(X)
        weight, occ = basis.kweights[ik], f[ik]
        for state in axes(x,2)
            electrons_reciprocal += weight*occ[state]*sum(abs2,@view x[:,state])
        end
        indices = findall(!iszero,occ)
        occupied_x = x[:,indices]
        hx = ComponentOperator(eh.ham[ik],2)*occupied_x
        for (j,state) in enumerate(indices)
            band_expectation += weight*occ[state]*real(dot(occupied_x[:,j],hx[:,j]))
        end
        for component in 1:2
            block = x[component:2:end,indices]
            append!(component_norms,[sum(abs2,column) for column in eachcol(block)])
            kinetic_block = supported.kinetic.kinetic_energies[ik] .* block
            nonlocal_block = zeros(ComplexF64,size(block))
            DFTK.apply!((; fourier=nonlocal_block,real=nothing),supported.atomic_nonlocal.ops[ik],
                        (; fourier=block,real=nothing))
            for (j,state) in enumerate(indices)
                direct_kinetic += weight*occ[state]*real(dot(block[:,j],kinetic_block[:,j]))
                direct_nonlocal += weight*occ[state]*real(dot(block[:,j],nonlocal_block[:,j]))
            end
        end
    end
    abs(electrons_reciprocal-8) <= 1e-8 || error("Reciprocal-space valence electron count drift")
    atomic_local_potential = vec(supported.atomic_local.potential_values)
    local_potential = vec(DFTK.total_local_potential(eh.ham))
    # Existing Hartree linear kernel gives vH for this same valence rho. This is
    # a potential-only diagnostic, not a second energy/XC traversal.
    vH = vec(DFTK.apply_kernel(supported.hartree,basis,rho))
    vxc = local_potential-atomic_local_potential-vH
    local_integral = basis.dvol*dot(density.n,atomic_local_potential)
    hartree_half_integral = basis.dvol*dot(density.n,vH)/2
    integral_n_vxc = basis.dvol*dot(density.n,vxc)
    double_counting_total = band_expectation-terms["Hartree"]-integral_n_vxc+
        terms["Xc"]+terms["Ewald"]+terms["PspCorrection"]
    report = (; electron_count_real=basis.dvol*sum(density.n),
        electron_count_reciprocal=electrons_reciprocal,
        component_norm_min=minimum(component_norms),component_norm_max=maximum(component_norms),
        energy_term_sum_difference_ha=sum(values(terms))-total,
        direct_kinetic_ha=direct_kinetic,direct_nonlocal_ha=direct_nonlocal,
        direct_kinetic_difference_ha=direct_kinetic-terms["Kinetic"],
        direct_nonlocal_difference_ha=direct_nonlocal-terms["AtomicNonlocal"],
        local_integral_ha=local_integral,local_integral_difference_ha=local_integral-terms["AtomicLocal"],
        hartree_half_integral_ha=hartree_half_integral,
        hartree_half_integral_difference_ha=hartree_half_integral-terms["Hartree"],
        ewald_once_difference_ha=terms["Ewald"]-supported.ewald.energy,
        psp_correction_once_difference_ha=terms["PspCorrection"]-supported.psp_correction.energy,
        integral_n_vxc_ha=integral_n_vxc,band_expectation_ha=band_expectation,
        double_counting_total_ha=double_counting_total,
        double_counting_difference_ha=double_counting_total-total,
        energy_hamiltonian_calls=1,xc_evaluations=1,ewald_count=1,psp_correction_count=1,
        call_count_scope="One energy_hamiltonian traversal of the verified seven terms; not Libxc internal function-call counts",
        density_source="Reconstructed from these exact spinor orbitals and capacity-one occupations; valence only",
        nlcc_source="TermXc adds its existing core density internally; Hartree and n*vxc use valence n")
    all(v -> !(v isa Number) || isfinite(v),values(report)) || error("Nonfinite energy diagnostics")
    (; density,rho,ham=eh.ham,terms,total,report,local_potential,vH,vxc)
end
