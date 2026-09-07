# Bounded Phase 6B probes. No SCF, no dense full Hamiltonian, no parameter scan.
function build_integration_cases(root,settings)
    mg=load_bound_psp(root;mode=:real_fr)
    si=load_bound_psp(root;mode=:synthetic_scalar_limit)
    m=settings["mg"]
    mgctx=build_context([mg],Matrix{Float64}(I,3,3)*m["cell_side_bohr"],m["positions_fractional"],
        m["kpoints"],m["kweights"];Ecut=m["ecut_ha"],xc_identifiers=Symbol.(m["xc_identifiers"]),mode=:real_fr)
    case=JSON3.read(read(joinpath(root,"benchmarks/si-sr-lda/case.json"),String),Dict{String,Any})
    geo=case["geometry"]; lattice=reduce(hcat,Float64.(v) for v in geo["lattice_vectors_bohr"])
    positions=[Float64.(p) for p in geo["positions_fractional"]]
    coords=[Float64.(p["coordinate_fractional"]) for p in case["kpoints"]]
    weights=Float64[p["weight_spatial"] for p in case["kpoints"]]
    sictx=build_context(fill(si,length(positions)),lattice,positions,coords,weights;
        Ecut=case["cutoffs"]["dftk_ecut_ha"],xc_identifiers=Symbol.(case["xc"]["dftk_identifiers"]),mode=:synthetic_scalar_limit)
    nativepsp=DFTK.PspUpf(si.parsed;identifier="Original scalar Si reference",rcut=nothing)
    model=DFTK.model_DFT(lattice,[DFTK.ElementPsp(:Si,nativepsp) for _ in positions],positions;
        functionals=Symbol.(case["xc"]["dftk_identifiers"]),n_electrons=sictx.basis.model.n_electrons,
        spin_polarization=:none,temperature=0.0,symmetries=false)
    native_si_basis=DFTK.PlaneWaveBasis(model;Ecut=case["cutoffs"]["dftk_ecut_ha"],kgrid=DFTK.ExplicitKpoints(coords,weights))
    (;mg,si,mgctx,sictx,native_si_basis)
end

function fixed_reference_density(basis,settings)
    mg=settings["mg"]
    q=[cos(2π*dot(mg["reference_density_wavevector"],r)) for r in vec(DFTK.r_vectors(basis))]
    qbar=sum(q)/length(q)
    n=basis.model.n_electrons/basis.model.unit_cell_volume .* (1 .+ mg["reference_density_modulation"].*(q.-qbar))
    all(isfinite,n) && minimum(n)>0 || error("Reference density must be positive and finite")
    energy_valence_rho(basis,n)
    (;n,report=(;source="Prescribed analytic fixed density; no SCF and not PP_RHOATOM",qbar,
        minimum=minimum(n),maximum=maximum(n),electron_count=basis.dvol*sum(n),
        n_sha256=integration_density_hash(n),fft_grid=collect(basis.fft_size),volume_bohr3=basis.model.unit_cell_volume))
end

function diagnostic_fixture(ctx,seed;n_states=16)
    ne=Int(ctx.basis.model.n_electrons)
    n_states>ne || throw(ArgumentError("Fixture requires at least one empty state"))
    X=[Matrix(DFTK.ortho_qr(randn(MersenneTwister(seed+ik-1),ComplexF64,
        2length(DFTK.G_vectors(ctx.basis,k)),n_states))) for (ik,k) in enumerate(ctx.basis.kpoints)]
    f=[vcat(ones(ne),zeros(n_states-ne)) for _ in X]
    (;X,f,seed,scope="General complex whole-column QR operator/energy fixture; prescribed occupations; not a physical ground state")
end

function basis_summary(ctx)
    b=ctx.basis
    (;ecut_ha=b.Ecut,fft_grid=collect(b.fft_size),volume_bohr3=b.model.unit_cell_volume,
      n_electrons=b.model.n_electrons,lattice_bohr=collect(eachcol(b.model.lattice)),
      positions_fractional=b.model.positions,
      native_nonlocal_terms=count(t->t isa DFTK.TermAtomicNonlocal,b.terms),
      term_types=string.(typeof.(b.terms)),
      kpoints=[(;coordinate_fractional=collect(k.coordinate),weight_spatial=b.kweights[ik],
        ng=length(DFTK.G_vectors(b,k)),g_order_sha256=_source_snapshot(collect(DFTK.G_vectors(b,k)))) for (ik,k) in enumerate(b.kpoints)])
end

# Map actual fractional G+k vectors, then verify every numeric pair. No row-order assumption.
function time_reversal_map(basis,source_k,target_k)
    src=[collect(g+source_k.coordinate) for g in DFTK.G_vectors(basis,source_k)]
    dst=[collect(g+target_k.coordinate) for g in DFTK.G_vectors(basis,target_k)]
    length(src)==length(dst) || throw(ArgumentError("Time reversed G sets have different lengths"))
    # Prescribed dyadic k coordinates are exact in Float64. Canonicalize signed
    # zero because Julia Dict uses isequal, for which +0.0 and -0.0 differ.
    key(q)=Tuple(iszero(v) ? 0.0 : v for v in q)
    lookup=Dict(key(q)=>i for (i,q) in enumerate(dst))
    length(lookup)==length(dst) || throw(ArgumentError("Duplicate target G+k vector"))
    mapping=[get(lookup,key(-q),0) for q in src]
    all(>(0),mapping) && length(unique(mapping))==length(mapping) || throw(ArgumentError("G+k reversal is not bijective"))
    maximum(norm(src[i]+dst[mapping[i]]) for i in eachindex(src))<=1e-12 ||
        throw(ArgumentError("Time reversed G+k coordinates differ"))
    mapping
end

function time_reverse_spinor(X,mapping)
    size(X,1)==2length(mapping) || throw(DimensionMismatch("Time reversal G map differs from spinor rows"))
    length(unique(mapping))==length(mapping) && sort(mapping)==collect(eachindex(mapping)) ||
        throw(ArgumentError("Time reversal needs a bijection"))
    x=X isa AbstractVector ? reshape(X,:,1) : X
    y=similar(x)
    for (i,j) in enumerate(mapping)
        y[2j-1,:]=conj.(x[2i,:]);y[2j,:]=-conj.(x[2i-1,:])
    end
    X isa AbstractVector ? vec(y) : y
end

function full_hamiltonian_checks(ctx,ham,settings)
    t=settings["thresholds"]; seed=settings["seeds"]["symmetry_probe"]
    rows=NamedTuple[]
    for (ik,h) in enumerate(ham)
        rng=MersenneTwister(seed+ik-1)
        x=randn(rng,ComplexF64,size(h,1));x/=norm(x)
        y=randn(rng,ComplexF64,size(h,1));y/=norm(y)
        hx=h*x;hy=h*y
        herm=integration_error(dot(x,hy),dot(hx,y))
        c=SpinorPrototype.ComponentOperator(h.common.scalar,2)
        common=c*x; nl=ctx.fr_blocks[ik]*x
        decomposition=integration_error(hx,common+nl)
        down=zeros(ComplexF64,size(h,1));down[2:2:end]=randn(rng,ComplexF64,length(down)÷2);down/=norm(down)
        spin_full=(h*down)[1:2:end];spin_nl=(ctx.fr_blocks[ik]*down)[1:2:end]
        spin_common=(c*down)[1:2:end]
        signal=norm(spin_nl);absolute=norm(spin_full-spin_nl)
        relative=signal>0 ? absolute/signal : nothing
        spin_status=signal<t["spin_flip_min_signal"] ? "INCONCLUSIVE" :
            (relative<=t["spin_flip_relative"] && norm(spin_common)<=t["hamiltonian_decomposition_normalized"] ? "PASS" : "FAIL")
        push!(rows,(;k_index=ik,hermiticity_normalized=herm,decomposition_normalized=decomposition,
            spin_flip=(;status=spin_status,signal_norm=signal,absolute_error=absolute,signal_relative_error=relative,common_up_norm=norm(spin_common)),
            omitted_fr_effect_norm=norm(hx-common),duplicated_fr_effect_norm=norm((common+2nl)-hx),
            omitted_fr_effect_matches=integration_error(hx-common,nl),duplicated_fr_effect_matches=integration_error(common+2nl-hx,nl)))
    end
    trrows=NamedTuple[]
    for (is,it) in ((1,1),(2,3),(3,2))
        mapping=time_reversal_map(ctx.basis,ctx.basis.kpoints[is],ctx.basis.kpoints[it])
        x=randn(MersenneTwister(seed+10+is),ComplexF64,size(ham[is],1),2);x/=norm(x)
        lhs=ham[it]*time_reverse_spinor(x,mapping)
        rhs=time_reverse_spinor(ham[is]*x,mapping)
        push!(trrows,(;source=is,target=it,ng=length(mapping),bijection=true,
            reversal_map_sha256=_source_snapshot(mapping),normalized_error=integration_error(lhs,rhs),absolute_error=norm(lhs-rhs)))
    end
    good=all(r.hermiticity_normalized<=t["hermiticity_normalized"] && r.decomposition_normalized<=t["hamiltonian_decomposition_normalized"] &&
        r.omitted_fr_effect_norm>1e-12 && r.duplicated_fr_effect_norm>1e-12 for r in rows) &&
        all(r.normalized_error<=t["time_reversal_normalized"] for r in trrows)
    states=[r.spin_flip.status for r in rows]
    status=!good || "FAIL" in states ? "FAIL" : "INCONCLUSIVE" in states ? "INCONCLUSIVE" : "PASS"
    (;status,seed,blocks=rows,time_reversal=trrows,
      convention="i sigma_y K plus a verified bijection of actual G+k vectors; independent physical k blocks")
end

function assert_eigensolve_record(record,settings)
    t=settings["thresholds"]
    record.converged===true || error("Fixed-density eigensolver did not converge")
    all(isfinite,record.eigenvalues_ha) && all(isfinite,record.explicit_residuals_ha) &&
        isfinite(record.orthogonality_frobenius) || error("Nonfinite eigensolve result")
    maximum(record.explicit_residuals_ha)<=t["residual_ha"] || error("Explicit target eigenresidual failed")
    record.orthogonality_frobenius<=t["gram_norm"] || error("Target orthogonality failed")
    true
end

function solve_fixed_density(ctx,ham,settings;checkpoint=(record,X)->nothing)
    basis=ctx.basis; ne=Int(basis.model.n_electrons)
    target=2cld(max(16,ne+4),2); s=settings["solver"]; ncompute=target+s["n_auxiliary"]
    kinetic=only(filter(t->t isa DFTK.TermKinetic,basis.terms)).kinetic_energies
    records=NamedTuple[];orbitals=Matrix{ComplexF64}[];lambdas=Vector{Float64}[]
    for (ik,(k,h)) in enumerate(zip(basis.kpoints,ham))
        seed=settings["seeds"]["eigensolve_base"]+ik-1
        initial=Matrix(DFTK.ortho_qr(randn(MersenneTwister(seed),ComplexF64,size(h,1),ncompute)))
        saved=copy(initial)
        prec=SpinorPrototype.ComponentKineticPreconditioner(kinetic[ik],2;shift=s["preconditioner_shift_ha"])
        println(stderr,"Phase 6B fixed-density k=$ik/$(length(ham)), NG=$(size(h,1)÷2), targets=$target; no SCF")
        reset_full_counters!(h); started=time()
        d=DFTK.lobpcg_hyper(h,initial;prec,tol=s["tolerance_ha"],maxiter=s["maxiter"],miniter=1,n_conv_check=target)
        solve_counts=full_operator_stats(h)
        x=Matrix(d.X[:,1:target]);lambda=collect(d.λ[1:target]);hx=h*x
        residuals=[norm(hx[:,n]-lambda[n]*x[:,n]) for n in eachindex(lambda)]
        record=(;k_index=ik,coordinate_fractional=collect(k.coordinate),weight_spatial=basis.kweights[ik],
            ng=size(h,1)÷2,target_states=target,auxiliary_states=s["n_auxiliary"],seed,
            initial_source="Independent ComplexF64 Gaussian whole-spinor QR",initial_gram_norm=norm(saved'saved-I),
            initial_imaginary_norm=norm(imag.(saved)),initial_unchanged=initial==saved,
            iterations=d.n_iter,converged=d.converged,elapsed_seconds=time()-started,solver_n_matvec=d.n_matvec,
            operator_counts=solve_counts,counts_after_explicit_residual=full_operator_stats(h),
            eigenvalues_ha=lambda,auxiliary_eigenvalues_ha=collect(d.λ[target+1:end]),
            explicit_residuals_ha=residuals,solver_residuals_ha=collect(d.residual_norms),orthogonality_frobenius=norm(x'x-I))
        checkpoint(record,x) # Preserve measured failures before enforcing engineering thresholds.
        assert_eigensolve_record(record,settings)
        push!(records,record);push!(orbitals,x);push!(lambdas,lambda)
    end
    gamma=max((abs(lambdas[1][j]-lambdas[1][j+1]) for j in 1:2:target)...)
    pm=maximum(abs.(sort(lambdas[2])-sort(lambdas[3])))
    t=settings["thresholds"]
    spectrum=(;status=gamma<=t["kramers_ha"] && pm<=t["time_reversed_spectrum_ha"] ? "PASS" : "FAIL",
        gamma_kramers_max_ha=gamma,plus_minus_spectrum_max_ha=pm)
    f=[vcat(ones(ne),zeros(target-ne)) for _ in orbitals]
    (;X=orbitals,f,lambdas,records,spectrum)
end

function scalar_limit_action(ctx,native_basis,n,seed)
    pair=build_full_hamiltonian(ctx,n)
    native=DFTK.Hamiltonian(native_basis;ρ=energy_valence_rho(native_basis,n))
    rows=NamedTuple[]
    for (ik,h) in enumerate(pair.full)
        kc=ctx.basis.kpoints[ik];kn=native_basis.kpoints[ik]
        kc.coordinate==kn.coordinate && collect(DFTK.G_vectors(ctx.basis,kc))==collect(DFTK.G_vectors(native_basis,kn)) ||
            error("Scalar action reference has different G/k order")
        x=randn(MersenneTwister(seed+ik-1),ComplexF64,size(h,1),2);x/=norm(x)
        actual=h*x;expected=SpinorPrototype.ComponentOperator(native[ik],2)*x
        push!(rows,(;k_index=ik,ng=size(h,1)÷2,absolute_error=norm(actual-expected),normalized_error=integration_error(actual,expected)))
    end
    (;scope="Real scalar Si common data plus artificial complete degenerate FR channels vs native scalar H lifted to two components; no SCF",seed,
      max_error=maximum(r.normalized_error for r in rows),blocks=rows)
end
