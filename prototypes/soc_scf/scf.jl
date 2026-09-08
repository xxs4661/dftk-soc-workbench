# Reuse the small Phase 5B density-map controller, not its Si filling or energies.
function assert_current_hamiltonian(fresh,selected,probe;
    expected_potentials=[copy(DFTK.total_local_potential(h)) for h in fresh.common.blocks],expected_action=fresh.full[1]*probe)
    length(fresh.full)==length(selected.full) || error("Hamiltonian hook changed k blocks")
    for ik in eachindex(fresh.full)
        selected.full[ik].common.scalar === selected.common[ik] || error("Full-H and common-H k blocks were exchanged")
        selected.common[ik].basis === fresh.common[ik].basis && selected.common[ik].kpoint === fresh.common[ik].kpoint || error("Hamiltonian basis/k binding changed")
        p=expected_potentials[ik];q=DFTK.total_local_potential(selected.common[ik])
        size(p)==size(q) && p==q || error("Stale or altered H[n_in] local potential at k=$ik")
    end
    norm(expected_action-selected.full[1]*probe)<=1e-12 || error("Stale or altered full-H action")
    true
end

function rayleigh_occupation_diagnostic(ctx,rayleigh,formal_f,settings)
    # Rayleigh values can be unsorted within almost-degenerate subspaces. Sort
    # solely for the root solver, then restore the original orbital-column map.
    permutations=sortperm.(rayleigh)
    sorted=[r[p] for (r,p) in zip(rayleigh,permutations)]
    e=fermi_occupations(sorted,ctx.basis.kweights,ctx.basis.model.n_electrons,ctx.basis.model.temperature;
        electron_tol=settings["ensemble"]["root_electron_atol"],maxiter=settings["ensemble"]["root_maxiter"])
    restored=[f[invperm(p)] for (f,p) in zip(e.f,permutations)]
    error=maximum(maximum(abs.(a-b)) for (a,b) in zip(restored,formal_f))
    (;max_occupation_difference=error,occupations=restored,occupation_report=e.report,
        source="H[n_out] Rayleigh quotients, sorted only for global root then restored to original columns; not a new diagonalization")
end

function soc_map(ctx,n_in,settings,previous,target;seed,map_index,is_closure=false,
                 previous_potential=nothing,probe,hooks=NamedTuple(),progress=(r)->nothing)
    b=ctx.basis;t=settings["thresholds"]
    sin=Controller.density_summary(n_in,b.dvol;n_electrons=b.model.n_electrons,electron_tol=t["electron_count_abs"])
    fresh=FI.build_full_hamiltonian(ctx,n_in)
    selected=fresh
    if hasproperty(hooks,:ham)
        expected_potentials=[copy(DFTK.total_local_potential(h)) for h in fresh.common.blocks]
        expected_action=fresh.full[1]*probe
        selected=hooks.ham(fresh,copy(n_in),map_index)
        assert_current_hamiltonian(fresh,selected,probe;expected_potentials,expected_action)
    end
    potential=vec(DFTK.total_local_potential(selected.common));action=selected.full[1]*probe
    solve_hook=hasproperty(hooks,:solve) ? hooks.solve : nothing
    solved=solve_with_band_check(ctx,selected.full,previous,target,settings;seed,map_index,solve_hook,progress)
    X=solved.solved.X;f=solved.ensemble.f
    hasproperty(hooks,:occupations) && (f=hooks.occupations(deepcopy(f),map_index))
    # Hooks are fault injection only: preserve exact capacity-one global FD values.
    f==solved.ensemble.f || error("Occupation hook changed the global Fermi ensemble")
    stream_k=get(settings["solver"],"stream_k",false)
    orbital=FI.orbital_density(b,X,f;stream_k)
    chosen=hasproperty(hooks,:density) ? hooks.density(deepcopy(orbital),copy(n_in),map_index) : orbital
    FI.integration_density_hash(chosen.n)==FI.integration_density_hash(orbital.n) || error("Stale or exchanged n_out; density must belong to current X/f")
    energy=FI.energy_snapshot(ctx,X,f;expected_n=chosen.n,stream_k)
    FI.assert_energy_consistency(energy;energy_atol=t["energy_abs_ha"])
    thermal=ensemble_free_energy(energy.total,f,b.kweights,b.model.temperature)
    abs(thermal.arithmetic_error_ha)<=t["free_energy_arithmetic_relative"]*max(1,abs(thermal.free_energy_ha),abs(thermal.internal_energy_ha)) || error("Free-energy arithmetic failed")
    stationarity=occupation_stationarity(solved.solved.eigenvalues,f,solved.ensemble.mu,b.model.temperature;
        endpoint_margin=settings["ensemble"]["stationarity_endpoint_margin"])
    stationarity.max_abs_residual_ha<=settings["ensemble"]["stationarity_abs_ha"] || error("Finite-temperature occupation stationarity failed")
    self_old=Vector{Float64}[];self_rq=Vector{Float64}[];rayleigh=Vector{Float64}[]
    for (ik,(H,x)) in enumerate(zip(energy.ham,X))
        hx=H*x;rq=[real(dot(x[:,j],hx[:,j]))/sum(abs2,x[:,j]) for j in axes(x,2)]
        push!(self_old,[norm(hx[:,j]-solved.solved.eigenvalues[ik][j]*x[:,j]) for j in axes(x,2)])
        push!(self_rq,[norm(hx[:,j]-rq[j]*x[:,j]) for j in axes(x,2)])
        push!(rayleigh,rq)
    end
    feedback=rayleigh_occupation_diagnostic(ctx,rayleigh,f,settings)
    sout=Controller.density_summary(energy.density.n,b.dvol;n_electrons=b.model.n_electrons,electron_tol=t["electron_count_abs"])
    pauli=norm(energy.density.m)/norm(energy.density.n)
    all(isfinite,(pauli,feedback.max_occupation_difference)) || error("Nonfinite closure diagnostics")
    closure_ok=maximum(maximum,self_old)<=t["self_density_residual_ha"] && maximum(maximum,self_rq)<=t["self_density_residual_ha"] &&
        pauli<=t["pauli_density_relative"] && feedback.max_occupation_difference<=t["self_rayleigh_occupation_abs"]
    diag=(;consumed_input_sha256=sin.sha256,orbital_density_sha256=sout.sha256,
        target_states=solved.band.target,band_completeness=solved.band,band_attempts=solved.attempts,
        occupations=solved.ensemble.report,occupation_stationarity=stationarity,
        max_input_h_residual_ha=maximum(maximum(r.explicit_residuals_ha) for r in solved.solved.records),
        max_gram_norm=maximum(r.orthogonality_frobenius for r in solved.solved.records),
        potential_sha256=FI.integration_density_hash(potential),potential_norm=norm(potential),
        potential_change_norm=isnothing(previous_potential) ? nothing : norm(potential-previous_potential),
        probe_action_sha256=FI.integration_density_hash(action),probe_action_norm=norm(action),
        energy_terms_ha=energy.terms,internal_energy_ha=thermal.internal_energy_ha,
        entropy_dimensionless=thermal.entropy_dimensionless,entropy_energy_ha=thermal.entropy_energy_ha,
        free_energy_ha=thermal.free_energy_ha,free_energy_arithmetic_error_ha=thermal.arithmetic_error_ha,
        energy_checks=energy.report,nonlocal_decomposition=energy.nonlocal_decomposition,
        real_electron_count=sout.electron_count,orbital_electron_count=energy.report.electron_count_reciprocal,
        pauli_density_relative_l2=pauli,magnetization_integral=b.dvol.*vec(sum(energy.density.m;dims=2)),
        self_density_h_old_lambda_residuals_ha=self_old,self_density_h_rayleigh_residuals_ha=self_rq,
        self_density_h_rayleigh_values_ha=rayleigh,max_self_density_h_residual_ha=maximum(maximum,self_old),
        max_self_rayleigh_residual_ha=maximum(maximum,self_rq),rayleigh_occupations=feedback,
        formal_occupation_source="Global capacity-one Fermi root of the current map's solved H[n_in] eigenvalues",
        energy_density_source="Same physical X/f and n_out; seven-term E plus spinor entropy once; no n_next terms")
    raw=(;X,all_X=solved.solved.all_X,f,eigenvalues=solved.solved.eigenvalues,n_in=copy(n_in),n_out=copy(energy.density.n),
        density=energy.density,energy,thermal,ensemble=solved.ensemble,diag)
    (;n_out=energy.density.n,raw,diagnostics=diag,closure_ok,potential,target=solved.band.target)
end

function soc_scf(ctx,n0,settings;seed,callback=(r,raw)->nothing,progress=(r)->nothing,hooks=NamedTuple(),case_contract=nothing)
    validate_soc_settings(settings;case_contract);FI.validate_context(ctx)
    ctx.basis.model.temperature==settings["ensemble"]["tau_ha"] && ctx.basis.model.smearing isa DFTK.Smearing.FermiDirac || error("Actual model and ensemble settings disagree")
    previous=nothing;target=settings["solver"]["initial_target_states"];previous_potential=nothing
    probe=randn(MersenneTwister(settings["seeds"]["potential_probe"]),ComplexF64,2length(ctx.basis.kpoints[1].G_vectors),1);probe/=norm(probe)
    map=function(n_in,imap,closing)
        progress((;event="map_input_checkpoint",map_index=imap,is_closure=closing,n_in=copy(n_in)))
        mapped=soc_map(ctx,n_in,settings,previous,target;seed,map_index=imap,is_closure=closing,previous_potential,probe,hooks,progress)
        previous=mapped.raw.all_X;target=mapped.target;previous_potential=copy(mapped.potential)
        mapped
    end
    Controller.iterate_density_map(map,n0;dvol=ctx.basis.dvol,alpha=settings["scf"]["alpha"],max_maps=settings["scf"]["max_maps"],
        density_tol=settings["thresholds"]["density_fixedpoint_l2"],electron_tol=settings["thresholds"]["electron_count_abs"],
        n_electrons=ctx.basis.model.n_electrons,callback)
end

function endpoint_time_reversal(ctx,raw,settings)
    full=FI.full_hamiltonian_checks(ctx,raw.energy.ham,settings)
    e=raw.eigenvalues;f=raw.f;target=length(e[1]);t=settings["thresholds"]
    gamma=maximum(abs(e[1][i]-e[1][i+1]) for i in 1:2:target)
    pm=maximum(abs.(e[2]-e[3]))
    gf=maximum(abs(f[1][i]-f[1][i+1]) for i in 1:2:target)
    pf=maximum(abs.(f[2]-f[3]))
    status=full.status=="PASS" && gamma<=t["kramers_ha"] && pm<=t["time_reversed_spectrum_ha"] &&
        max(gf,pf)<=t["paired_occupation_abs"] ? "PASS" : "FAIL"
    (;status,full_h_at_n_out=full,gamma_kramers_max_ha=gamma,plus_minus_spectrum_max_ha=pm,
        gamma_occupation_max_difference=gf,plus_minus_occupation_max_difference=pf,
        eigenvalue_source="Actual closure solve H[n_in], where n_in is previous candidate's n_out; final H[n_out] action and Rayleigh residuals are separate")
end
