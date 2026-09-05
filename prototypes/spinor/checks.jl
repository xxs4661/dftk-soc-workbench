# Finite B0 diagnostics. No extra SCF or k/cutoff scan is hidden in these functions.
function rotate_pair(X, ik, a, b, theta)
    a != b || throw(ArgumentError("Rotation needs two distinct states"))
    out = copy.(X)
    up, down = copy(X[ik][:,a]), copy(X[ik][:,b])
    out[ik][:,a] = cos(theta).*up + sin(theta).*down
    out[ik][:,b] = -sin(theta).*up + cos(theta).*down
    out
end

function finite_difference_check(basis, X, f, settings)
    cfg = settings["finite_difference"]
    ik,a,b = cfg["kpoint_index"],cfg["occupied_state"],cfg["empty_state"]
    f[ik][a]==1 && f[ik][b]==0 || error("Direction requires occupied and empty spinor states")
    trial = rotate_pair(X,ik,a,b,cfg["center_angle_rad"])
    center = energy_snapshot(basis,trial,f)
    h = ComponentOperator(center.ham[ik],2)
    derivative = 2basis.kweights[ik]*(f[ik][a]-f[ik][b]) *
        real(dot(trial[ik][:,b],h*trial[ik][:,a]))
    abs(derivative)>cfg["minimum_nonstationary_derivative_ha_per_rad"] ||
        error("Direction center is too close to stationary for the declared diagnostic")
    records = []
    for step in cfg["steps_rad"]
        plus = energy_snapshot(basis,rotate_pair(trial,ik,a,b,step),f)
        minus = energy_snapshot(basis,rotate_pair(trial,ik,a,b,-step),f)
        numeric = (plus.total-minus.total)/(2step)
        normalized_error = abs(numeric-derivative)/max(1,abs(derivative))
        digest(n)=bytes2hex(sha256(reinterpret(UInt8,vec(n))))
        push!(records,(;step_rad=step,energy_plus_ha_cell=plus.total,energy_minus_ha_cell=minus.total,
            numeric_ha_per_rad=numeric,analytic_ha_per_rad=derivative,normalized_error,
            plus_density_sha256=digest(plus.density.n),minus_density_sha256=digest(minus.density.n)))
    end
    last(records).step_rad==1e-4 || error("Expected all three declared difference steps")
    report = (;status=last(records).normalized_error<=settings["acceptance"]["directional_derivative_normalized"] ? "PASS" : "FAIL",
        kpoint_index=ik,occupied_state=a,empty_state=b,center_angle_rad=cfg["center_angle_rad"],
        center_energy_ha_cell=center.total,center_orthogonality_frobenius=norm(trial[ik]'trial[ik]-I),
        analytic_ha_per_rad=derivative,center_energy_checks=center.report,steps=records,
        definition="Each plus/minus recomputes orbital density and full Hartree/XC energy; analytic derivative applies H at center orbital density")
    (;report,trial,center_density=center.density)
end

function scalar_reference(basis,settings)
    cfg = settings["scalar"]
    dtol = cfg["diagonalization_tolerance_ha"]
    initial_rho = DFTK.guess_density(basis)
    initial_sha256 = bytes2hex(sha256(reinterpret(UInt8,vec(initial_rho))))
    diagtolalg = DFTK.AdaptiveDiagtol(;diagtol_first=dtol,diagtol_min=dtol,diagtol_max=dtol)
    started = time()
    scf = DFTK.self_consistent_field(basis;ρ=initial_rho,tol=cfg["density_tolerance"],
        maxiter=cfg["maxiter"],seed=cfg["seed"],diagtolalg,
        nbandsalg=DFTK.FixedBands(;n_bands_converge=cfg["target_states"],
            n_bands_compute=cfg["target_states"]+cfg["auxiliary_states"]))
    scf.converged && all(d.converged for d in scf.diagonalization) || error("Native scalar reference did not converge")
    d = DFTK.diagonalize_all_kblocks(DFTK.lobpcg_hyper,scf.ham,
        cfg["target_states"]+cfg["auxiliary_states"];ψguess=scf.ψ,tol=dtol,
        n_conv_check=cfg["target_states"],maxiter=cfg["maxiter"])
    d.converged || error("Final scalar reference diagonalization failed")
    residuals = [[norm(scf.ham[ik]*d.X[ik][:,j]-d.λ[ik][j]*d.X[ik][:,j])
                   for j in 1:8] for ik in eachindex(basis.kpoints)]
    maximum(maximum,residuals)<=settings["acceptance"]["explicit_residual_ha"] || error("Scalar explicit residual failed")
    occ = fixed_gapped_occupations(d.λ,basis.kweights;representation=:scalar)
    rho_reconstructed = DFTK.compute_density(basis,d.X,occ.occupations)
    density = vec(DFTK.total_density(scf.ρ))
    reconstructed = vec(DFTK.total_density(rho_reconstructed))
    report = (;status="PASS",source="Independent native scalar SCF executed after A and B",
        initial_source="Fresh DFTK.guess_density, no spinor orbitals or density supplied",initial_sha256,
        iterations=scf.n_iter,elapsed_seconds=time()-started,seed=cfg["seed"],settings=cfg,
        density_residual_history=scf.history_Δρ,energy_history_ha=scf.history_Etot,
        energy_terms_ha_cell=Dict(pairs(scf.energies)),total_energy_ha_cell=scf.energies.total,
        eigenvalues_ha=[e[1:8] for e in d.λ],explicit_residuals_ha=residuals,
        final_diagonalization_iterations=d.n_iter,occupations=occ,
        density_sha256=bytes2hex(sha256(reinterpret(UInt8,density))),
        reconstructed_density_sha256=bytes2hex(sha256(reinterpret(UInt8,reconstructed))),
        density_electron_count=basis.dvol*sum(density),
        reconstructed_vs_scf_relative_l2=norm(reconstructed-density)/norm(density))
    (;report,X=d.X,f=occ.occupations,lambda=d.λ,density,reconstructed,scf_rho=scf.ρ)
end

function compare_references(basis, a, b, c, settings)
    gates = Dict{String,Any}()
    function gate(name,value,threshold)
        gates[name] = (;measured=value,threshold,status=isfinite(value)&&value<=threshold ? "PASS" : "FAIL")
    end
    thresholds = settings["acceptance"]
    comparisons = Dict{String,Any}()
    for (name,spin) in (("A",a),("B",b))
        diff = spin.energy.total-c.report.total_energy_ha_cell
        termdiff = Dict(k=>v-c.report.energy_terms_ha_cell[k] for (k,v) in spin.energy.terms)
        densitydiff = norm(spin.density.n-c.density)/norm(c.density)
        # The same explicit basis object was shared; coordinates/weights were verified
        # at construction. Retain raw differences without any energy alignment.
        spectrum = [spin.lambda[ik][1:16]-sort(repeat(c.lambda[ik][1:8];inner=2))
                    for ik in eachindex(basis.kpoints)]
        comparisons[name] = (;total_energy_difference_ha_cell=diff,energy_component_differences_ha_cell=termdiff,
            density_vs_native_scalar_relative_l2=densitydiff,
            density_vs_scalar_reconstructed_relative_l2=norm(spin.density.n-c.reconstructed)/norm(c.reconstructed),
            raw_spectrum_differences_ha=spectrum,
            reference="Current independent scalar C; no fitted or reference energy shift")
        gate(name*"_total_energy_vs_scalar",abs(diff),thresholds["total_energy_vs_scalar_abs_ha_cell"])
        gate(name*"_energy_components_vs_scalar",maximum(abs,values(termdiff)),thresholds["energy_component_abs_ha_cell"])
        gate(name*"_density_vs_scalar",densitydiff,thresholds["density_vs_scalar_relative_l2"])
        gate(name*"_raw_spectrum_vs_scalar",maximum(maximum(abs,d) for d in spectrum),thresholds["spectrum_max_abs_ha"])
    end
    ab = a.energy.total-b.energy.total
    gate("A_vs_B_total_energy",abs(ab),thresholds["a_vs_b_energy_abs_ha_cell"])
    (;status=all(g.status=="PASS" for g in values(gates)) ? "PASS" : "FAIL",gates,comparisons,
        a_minus_b_energy_ha_cell=ab,a_vs_b_density_relative_l2=norm(a.density.n-b.density.n)/norm(b.density.n))
end
