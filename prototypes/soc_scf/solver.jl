# Matrix-free target-state solves. Auxiliary states never enter occupations.
function validate_soc_settings(settings;case_contract=nothing)
    e,s,c=settings["ensemble"],settings["solver"],settings["scf"]
    tau=0.001
    if !isnothing(case_contract) && haskey(case_contract,"extra_profile")
        profile=case_contract["extra_profile"]
        profile in ("B0","K6") || error("Unregistered extra settings profile")
        case_contract["case"]=="soc-extra-v1/"*profile || error("Extra case/profile mismatch")
        settings===case_contract["settings"] || error("Settings must belong to their extra case")
        root=normpath(joinpath(@__DIR__,"../.."))
        path="benchmarks/soc-extra-v1/$profile.json"
        expected=JSON3.read(read(`git -C $root show $("HEAD:"*path)`,String),Dict{String,Any})
        isequal(case_contract,expected) || error("Extra case differs from clean execution bytes")
        historical=profile=="B0" ? "benchmarks/si-soc-splitting-v1/case.json" : "benchmarks/si-soc-k-reference-v1/K6/case.json"
        original=JSON3.read(read(`git -C $root show $("7630172808773a3d4ac2da825c27fe43a8705fb8:"*historical)`,String),Dict{String,Any})
        for key in ("pseudo","geometry","electrons","xc","cutoffs","fft_size","kpoints","symmetries","settings")
            isequal(case_contract[key],original[key]) || error("Extra physical input changed: $key")
        end
        tau=0.001
    elseif !isnothing(case_contract)
        case_contract isa AbstractDict || error("Expected an authenticated Si sensitivity case")
        profile=get(case_contract,"sensitivity_profile",nothing)
        profile in ("E40","T05","K4") || error("Unregistered SOC settings profile")
        get(case_contract,"case",nothing)=="si-soc-sensitivity-v1/"*profile || error("SOC case/profile mismatch")
        settings===case_contract["settings"] || error("Settings must belong to the authenticated case")
        root=normpath(joinpath(@__DIR__,"../.."))
        ref="4a58286183e4625ad7ae69b44eb80097e8ad6c7d:benchmarks/si-soc-sensitivity-v1/$profile/case.json"
        expected=JSON3.read(read(`git -C $root show $ref`,String),Dict{String,Any})
        exact(a,b)=typeof(a)===typeof(b) && (a isa AbstractDict ? keys(a)==keys(b) && all(exact(a[k],b[k]) for k in keys(a)) :
            a isa AbstractVector ? length(a)==length(b) && all(exact(x,y) for (x,y) in zip(a,b)) : isequal(a,b))
        exact(case_contract,expected) || error("SOC case differs from its fixed preparation")
        tau=profile=="T05" ? 0.0005 : 0.001
        case_contract["electrons"]["temperature_ha"]==tau || error("Case temperature differs from its registered profile")
    end
    e["tau_ha"]==tau && e["smearing"]=="FermiDirac" && e["capacity_per_spinor_state"]==1 || error("Fixed Phase 6C ensemble changed")
    e["root_maxiter"]==256 && e["root_electron_atol"]==1e-12 || error("Global occupation root settings changed")
    (s["initial_target_states"],s["auxiliary_states"],s["target_increment"],s["max_target_states"])==(24,6,8,48) || error("Target-band chain changed")
    s["tolerance_ha"]==1e-10 && s["maxiter"]==300 || error("Eigensolver settings changed")
    c["alpha"]==0.1 && c["max_maps"]==400 || error("Fixed mixing or map budget changed")
    true
end

function build_soc_context(root,settings)
    validate_soc_settings(settings)
    previous=TOML.parsefile(joinpath(root,"prototypes/fr_integration/phase6b.toml"))["mg"]
    m=settings["mg"]
    for k in ("cell_side_bohr","positions_fractional","ecut_ha","kpoints","kweights","xc_identifiers","symmetries",
              "reference_density_modulation","reference_density_wavevector")
        m[k]==previous[k] || error("Phase 6B physical input changed: $k")
    end
    bundle=FI.load_bound_psp(root;mode=:real_fr);c=bundle.common
    (c.element,c.z_valence,c.functional,c.relativistic,c.has_so,c.has_nlcc)==(:Mg,10,"PBESOL","full",true,false) || error("Actual Mg header mismatch")
    ctx=FI.build_context([bundle],Matrix{Float64}(I,3,3)*m["cell_side_bohr"],m["positions_fractional"],m["kpoints"],m["kweights"];
        Ecut=m["ecut_ha"],xc_identifiers=Symbol.(m["xc_identifiers"]),mode=:real_fr,
        temperature=settings["ensemble"]["tau_ha"],smearing=DFTK.Smearing.FermiDirac())
    (;ctx,bundle)
end

function soc_initial_density(ctx,label,settings)
    label in ("A","B") || throw(ArgumentError("Only independent A and B initial states are supported"))
    b=ctx.basis;n=fill(b.model.n_electrons/b.model.unit_cell_volume,prod(b.fft_size))
    qbar=nothing
    if label=="B"
        q=[cos(2π*dot(settings["mg"]["reference_density_wavevector"],r)) for r in vec(DFTK.r_vectors(b))]
        qbar=sum(q)/length(q)
        n .*= 1 .+ settings["mg"]["reference_density_modulation"].*(q.-qbar)
    end
    summary=Controller.density_summary(n,b.dvol;n_electrons=b.model.n_electrons)
    minimum(n)>0 || error("Initial density is not strictly positive")
    (;n,report=(;label,seed=settings["seeds"][label],summary,qbar,
        source=label=="A" ? settings["scf"]["initial_A"] : settings["scf"]["initial_B"],
        normalization_applied=false,prior_run_orbitals_used=false))
end

"""Warm starts belong to this run. New columns are independent projected random directions."""
function solver_initial(previous,nrows,ncolumns,seed)
    rng=MersenneTwister(seed)
    if isnothing(previous)
        return Matrix(DFTK.ortho_qr(randn(rng,ComplexF64,nrows,ncolumns)))
    end
    previous isa Matrix{ComplexF64} && size(previous,1)==nrows && all(isfinite,previous) || error("Invalid run-local warm start")
    size(previous,2)<=ncolumns || error("Warm-start state count exceeds requested states")
    if size(previous,2)==ncolumns
        return copy(previous)
    end
    old=Matrix(DFTK.ortho_qr(previous))
    new=randn(rng,ComplexF64,nrows,ncolumns-size(old,2))
    new-=old*(old'*new)
    new-=old*(old'*new) # Reorthogonalize new directions against the retained subspace.
    Matrix(DFTK.ortho_qr(hcat(old,new)))
end

function solve_soc_targets(ctx,ham,previous,target,settings;seed,map_index,extension_index=0,
                           solve_hook=nothing,progress=(record)->nothing)
    settings_stamp=_runtime_settings_stamp(ctx,settings)
    s,t=settings["solver"],settings["thresholds"]
    ncolumns=target+s["auxiliary_states"]
    kinetic=only(filter(x->x isa DFTK.TermKinetic,ctx.basis.terms)).kinetic_energies
    orbitals=Matrix{ComplexF64}[];all_X=Matrix{ComplexF64}[];eigenvalues=Vector{Float64}[];records=NamedTuple[]
    for (ik,H) in enumerate(ham)
        old=isnothing(previous) ? nothing : previous[ik]
        derived_seed=seed+ik-1+(extension_index==0 ? 0 : settings["seeds"]["extension_stride"]*extension_index+1000map_index)
        initial=solver_initial(old,size(H,1),ncolumns,derived_seed);saved=copy(initial)
        initial_gram=norm(initial'initial-I)
        initial_gram<=t["gram_norm"] || error("Initial whole-spinor QR Gram check failed")
        prec=ComponentKineticPreconditioner(kinetic[ik],2;shift=s["preconditioner_shift_ha"])
        FI.reset_full_counters!(H);started=time()
        eig=_runtime_call(ctx,:eigensolve;ham=(H,),settings,stamp=settings_stamp) do
            isnothing(solve_hook) ? DFTK.lobpcg_hyper(H,initial;prec,tol=s["tolerance_ha"],maxiter=s["maxiter"],miniter=1,n_conv_check=target) :
                solve_hook(H,initial,prec,ik,map_index)
        end
        counts=FI.full_operator_stats(H)
        if eig.converged!==true || eig.n_iter<=0
            state=hasproperty(eig,:X) && hasproperty(eig,:λ) ? (;X=eig.X,eigenvalues_ha=eig.λ) : nothing
            _runtime_call(()->progress((;event="failed_target_solve",map_index,k_index=ik,converged=eig.converged,iterations=eig.n_iter,state)),ctx,:progress_callback;
                ham=(H,),settings,stamp=settings_stamp,payload=state)
            error("SOC diagonalization failed or used zero iterations")
        end
        initial==saved || error("Eigensolver changed its input subspace")
        size(eig.X)==(size(H,1),ncolumns) && length(eig.λ)==ncolumns || error("Eigensolver returned wrong state counts")
        all(isfinite,eig.X) && all(isfinite,eig.λ) || error("Nonfinite SOC eigenresult")
        x=Matrix(eig.X[:,1:target]);lambda=Float64.(eig.λ[1:target]);hx=H*x
        residuals=[norm(hx[:,j]-lambda[j]*x[:,j]) for j in 1:target]
        record=(;map_index,k_index=ik,target_states=target,auxiliary_states=s["auxiliary_states"],ng=size(H,1)÷2,
            initial_source=isnothing(old) ? "Independent ComplexF64 Gaussian whole-column QR" :
                size(old,2)<ncolumns ? "Same-run subspace plus independently seeded orthogonal new directions" : "Previous map from this run only",
            initial_seed=derived_seed,initial_gram_norm=initial_gram,initial_imaginary_norm=norm(imag.(saved)),
            initial_sha256=FI.integration_density_hash(saved),initial_unchanged=true,
            converged=eig.converged,iterations=eig.n_iter,elapsed_seconds=time()-started,
            solver_n_matvec=eig.n_matvec,operator_counts=counts,counts_after_explicit_residual=FI.full_operator_stats(H),
            eigenvalues_ha=lambda,explicit_residuals_ha=residuals,orthogonality_frobenius=norm(x'x-I))
        # Raw arrays stay in ignored checkpoints; callback mutation cannot cross
        # the owned runtime's source/potential/settings boundary unnoticed.
        _runtime_call(()->progress((;event="target_solve",record,state=(;X=x,all_X=Matrix(eig.X),eigenvalues_ha=lambda))),ctx,:progress_callback;
            ham=(H,),settings,stamp=settings_stamp,payload=(;x,all_X=eig.X,lambda,record))
        FI.assert_eigensolve_record(record,settings)
        push!(orbitals,x);push!(all_X,Matrix(eig.X));push!(eigenvalues,lambda);push!(records,record)
    end
    (;X=orbitals,all_X,eigenvalues,records,target)
end

function solve_with_band_check(ctx,ham,previous,target,settings;seed,map_index,solve_hook=nothing,progress=(record)->nothing)
    settings_stamp=_runtime_settings_stamp(ctx,settings)
    allow_expansion=get(settings["solver"],"allow_band_expansion",true)
    allow_expansion isa Bool || throw(ArgumentError("allow_band_expansion must be boolean"))
    attempts=NamedTuple[];warm=previous;expansion=0
    while true
        solved=solve_soc_targets(ctx,ham,warm,target,settings;seed,map_index,extension_index=expansion,solve_hook,progress)
        ensemble=fermi_occupations(solved.eigenvalues,ctx.basis.kweights,ctx.basis.model.n_electrons,ctx.basis.model.temperature;
            electron_tol=settings["ensemble"]["root_electron_atol"],maxiter=settings["ensemble"]["root_maxiter"])
        band=band_completeness(ensemble.f;threshold=settings["ensemble"]["boundary_occupation_max"])
        push!(attempts,(;target,band,occupation=ensemble.report,per_k=solved.records))
        _runtime_call(()->progress((;map_index,event="band_completeness",attempt=last(attempts))),ctx,:progress_callback;
            ham,settings,stamp=settings_stamp,payload=last(attempts))
        band.status=="PASS" && return (;solved,ensemble,band,attempts)
        allow_expansion || throw(EnsembleError("INSUFFICIENT_BANDS",
            "At $target targets, highest two occupations exceed the declared threshold; this case forbids band expansion"))
        band.status=="INSUFFICIENT_BANDS" && throw(EnsembleError("INSUFFICIENT_BANDS","At 48 targets, highest two occupations exceed the declared threshold"))
        warm=solved.all_X;target=band.next_target;expansion+=1
    end
end
