# Actual Mg operator/energy integration with deliberately synthetic spectra and
# complex trial orbitals. No eigensolve, physical occupation claim, or SCF here.
function run_soc_integration_tests(ctx_hot, settings)
    FI = FRIntegration
    SC = SOCSCF
    basis = ctx_hot.basis
    tau = basis.model.temperature
    ne = basis.model.n_electrons
    weights = basis.kweights
    nstates = settings["solver"]["initial_target_states"]
    tol = settings["thresholds"]

    # Known fractional FD fixture: the three k points have unequal electron
    # shares (10.1,9.9,10), but the weighted total is the actual Mg header's 10.
    # These finite energies are analytic fixtures, not computed Mg eigenvalues;
    # their intentionally occupied upper levels are not a band-completeness test.
    target_f = [vcat(fill(.8,8), fill(.6,4), fill(.1,12)) for _ in weights]
    target_f[1][1:2] .+= .05
    target_f[2][1:2] .-= .05
    foreach(o -> sort!(o; rev=true), target_f)
    levels = [[tau*log((1-o)/o) for o in fk] for fk in target_f]
    ensemble = SC.fermi_occupations(levels, weights, ne, tau;
        electron_tol=settings["ensemble"]["root_electron_atol"],
        maxiter=settings["ensemble"]["root_maxiter"])
    f = ensemble.f
    X = [SC.solver_initial(nothing, 2length(k.G_vectors), nstates,
                          settings["seeds"]["symmetry_probe"]+ik-1)
         for (ik,k) in enumerate(basis.kpoints)]
    savedX, savedf = deepcopy(X), deepcopy(f)
    snapshot = FI.energy_snapshot(ctx_hot, X, f)
    thermal = SC.ensemble_free_energy(snapshot.total, f, weights, tau)
    # Independent direct binary-entropy expression is safe here because every
    # fixture occupation is strictly inside (0,1), with no endpoint conventions.
    entropy_direct = -sum(weights[k]*sum(o*log(o)+(1-o)*log(1-o) for o in f[k])
                          for k in eachindex(weights))

    @testset "Finite-temperature physical-spinor factors retain seven-term E and one entropy" begin
        @test FI.validate_context(ctx_hot)
        @test tau == settings["ensemble"]["tau_ha"] == 0.001
        @test basis.model.smearing isa DFTK.Smearing.FermiDirac
        @test ne == sum(b.common.z_valence for b in ctx_hot.bundles) == 10
        @test length(basis.model.term_types) == length(basis.terms) == 6
        @test !any(t -> t isa DFTK.Entropy, basis.model.term_types)
        @test !any(t -> t isa DFTK.TermEntropy, basis.terms)
        @test all(size(x,2)==nstates && norm(x'x-I)<=tol["gram_norm"] for x in X)
        @test all(norm(imag.(x))>0 && norm(x[1:2:end,:])>0 && norm(x[2:2:end,:])>0 for x in X)
        @test all(all(o -> 0<o<1, fk) for fk in f)
        @test maximum(maximum(abs.(a-b)) for (a,b) in zip(f,target_f)) <= 1e-11
        @test maximum(sum.(f))-minimum(sum.(f)) > .1
        @test abs(sum(weights.*sum.(f))-ne) <= settings["ensemble"]["root_electron_atol"]
        @test Set(keys(snapshot.terms)) == FI.FR_ENERGY_NAMES
        @test FI.assert_energy_consistency(snapshot; energy_atol=tol["energy_abs_ha"])
        @test abs(sum(values(snapshot.terms))-snapshot.total) <= tol["energy_abs_ha"]
        @test abs(snapshot.report.electron_count_real-ne) <= tol["electron_count_abs"]
        @test abs(snapshot.report.electron_count_reciprocal-ne) <= tol["electron_count_abs"]
        @test snapshot.report.native_nonlocal_terms == 0
        @test !snapshot.report.nlcc_present
        @test abs(snapshot.nonlocal_decomposition.cross_ha) > 1e-12
        @test abs(snapshot.nonlocal_decomposition.decomposition_difference_ha) <= 1e-11
        @test abs(thermal.entropy_dimensionless-entropy_direct) <= 1e-12
        @test thermal.entropy_dimensionless > 0 && thermal.entropy_energy_ha < 0
        @test thermal.internal_energy_ha == snapshot.total
        @test abs(thermal.free_energy_ha-snapshot.total+tau*entropy_direct) <=
              1e-12*max(1,abs(thermal.free_energy_ha),abs(snapshot.total))
        doubled = SC.ensemble_free_energy(snapshot.total, [vcat(fk,fk) for fk in f], weights, tau)
        @test abs(doubled.entropy_dimensionless-2thermal.entropy_dimensionless) <= 1e-12
        @test abs(doubled.free_energy_ha-thermal.free_energy_ha) > 1e-6
        @test X == savedX && f == savedf
    end

    angle, phase = .37, .29
    U = ComplexF64[cos(angle) cis(phase)*sin(angle); -cis(-phase)*sin(angle) cos(angle)]
    equalX = deepcopy(X)
    equalX[1][:,[1,2]] = X[1][:,[1,2]]*U
    equal = FI.energy_snapshot(ctx_hot, equalX, f)
    unequalX = deepcopy(X)
    unequalX[1][:,[1,9]] = X[1][:,[1,9]]*U
    unequal = FI.orbital_density(basis, unequalX, f)
    equal_density_error = FI.integration_error(snapshot.density.n, equal.density.n)
    unequal_density_change = sqrt(basis.dvol)*norm(snapshot.density.n-unequal.n)
    @testset "Orbital unitary invariance applies to equal occupations only" begin
        @test norm(U'U-I) <= 1e-12
        @test f[1][1] == f[1][2]
        @test abs(f[1][1]-f[1][9]) > .1
        @test FI.integration_error(snapshot.density.R, equal.density.R) <= 1e-10
        @test equal_density_error <= 1e-10
        @test FI.integration_error(snapshot.density.m, equal.density.m) <= 1e-10
        @test abs(snapshot.total-equal.total) <= tol["energy_abs_ha"]
        @test maximum(abs(snapshot.terms[k]-equal.terms[k]) for k in keys(snapshot.terms)) <= tol["energy_abs_ha"]
        @test unequal_density_change > 1e-8
        @test abs(sum(unequal.n)*basis.dvol-ne) <= tol["electron_count_abs"]
        @test_throws ArgumentError FI.energy_snapshot(ctx_hot, unequalX, f; expected_n=snapshot.density.n)
        @test X == savedX && f == savedf
    end

    initialA = SC.soc_initial_density(ctx_hot,"A",settings)
    initialB = SC.soc_initial_density(ctx_hot,"B",settings)
    pairA = FI.build_full_hamiltonian(ctx_hot, initialA.n)
    pairB = FI.build_full_hamiltonian(ctx_hot, initialB.n)
    probe = copy(X[1][:,1:1])
    potential_change = norm(DFTK.total_local_potential(pairA.common)-DFTK.total_local_potential(pairB.common))
    action_change = norm(pairA.full[1]*probe-pairB.full[1]*probe)
    hartree = only(filter(t -> t isa DFTK.TermHartree, basis.terms))
    atomic_local = vec(only(filter(t -> t isa DFTK.TermAtomicLocal, basis.terms)).potential_values)
    vH_A = vec(DFTK.apply_kernel(hartree, basis, FI.energy_valence_rho(basis, initialA.n)))
    vH_B = vec(DFTK.apply_kernel(hartree, basis, FI.energy_valence_rho(basis, initialB.n)))
    # Keep the complete native PBEsol variational potential, including its GGA
    # gradient/divergence terms, exactly as in the existing energy adapter.
    vxc_A = vec(DFTK.total_local_potential(pairA.common)) - atomic_local - vH_A
    vxc_B = vec(DFTK.total_local_potential(pairB.common)) - atomic_local - vH_B
    hartree_change = norm(vH_A-vH_B)
    xc_change = norm(vxc_A-vxc_B)
    @testset "New n changes Hartree/XC and full H; stale and mixed-k pairs are rejected" begin
        @test potential_change > 1e-8
        @test action_change > 1e-8
        @test hartree_change > 1e-8
        @test xc_change > 1e-8
        @test SC.assert_current_hamiltonian(pairB,pairB,probe)
        @test_throws ErrorException SC.assert_current_hamiltonian(pairB,pairA,probe)
        mixedblocks = copy(pairB.full)
        mixedblocks[2] = pairA.full[2]
        mixed = merge(pairB,(;full=mixedblocks))
        @test_throws ErrorException SC.assert_current_hamiltonian(pairB,mixed,probe)
        potentials = [DFTK.total_local_potential(h) for h in pairB.common.blocks]
        saved_potentials = copy.(potentials)
        saved_action = pairB.full[1]*probe
        try
            potentials[2] .+= .01 # Explicit in-place corruption of a test H, never source data.
            @test_throws ErrorException SC.assert_current_hamiltonian(pairB,pairB,probe;
                expected_potentials=saved_potentials,expected_action=saved_action)
        finally
            foreach(pair->copyto!(pair[1],pair[2]),zip(potentials,saved_potentials))
        end
        @test SC.assert_current_hamiltonian(pairB,pairB,probe)
        @test pairA.full[1].fr === pairB.full[1].fr # Only the density-independent FR data are cached.
        @test_throws ArgumentError FI.build_full_hamiltonian(ctx_hot, initialA.n .* .8)
        invalidn = copy(initialA.n); invalidn[1] = NaN
        @test_throws ArgumentError FI.build_full_hamiltonian(ctx_hot, invalidn)
    end

    @testset "Malformed spinors, wrong ensemble and old eight-electron assumptions fail" begin
        invalidX=deepcopy(X); invalidX[1][1]=NaN
        @test_throws ArgumentError FI.energy_snapshot(ctx_hot,invalidX,f)
        invalidf=deepcopy(f); invalidf[1][1]=NaN
        @test_throws ArgumentError FI.energy_snapshot(ctx_hot,X,invalidf)
        @test_throws SC.EnsembleError SC.ensemble_free_energy(snapshot.total,invalidf,weights,tau)
        invalidf=deepcopy(f); invalidf[1][1]=1.01
        @test_throws ArgumentError FI.energy_snapshot(ctx_hot,X,invalidf)
        invalidf=deepcopy(f); invalidf[1][1]+=.01
        @test_throws ArgumentError FI.energy_snapshot(ctx_hot,X,invalidf)
        invalidf=deepcopy(f); pop!(invalidf[1])
        @test_throws DimensionMismatch FI.energy_snapshot(ctx_hot,X,invalidf)
        @test_throws ArgumentError SC.Controller.density_summary(initialA.n,basis.dvol;n_electrons=8)
        @test X == savedX && f == savedf
    end

    @testset "Controlled solver failure fixtures cannot publish converged target states" begin
        # Each hook bypasses LOBPCG. Only random QR and, for the last fixture,
        # a direct matrix-free residual evaluation are performed.
        failed=(H,initial,prec,ik,imap)->(;converged=false,n_iter=0)
        @test_throws ErrorException SC.solve_soc_targets(ctx_hot,pairA.full,nothing,nstates,settings;
            seed=settings["seeds"]["A"],map_index=1,solve_hook=failed)
        zero_iter=(H,initial,prec,ik,imap)->(;converged=true,n_iter=0)
        @test_throws ErrorException SC.solve_soc_targets(ctx_hot,pairA.full,nothing,nstates,settings;
            seed=settings["seeds"]["A"],map_index=1,solve_hook=zero_iter)
        wrongshape=(H,initial,prec,ik,imap)->(;converged=true,n_iter=1,
            X=zeros(ComplexF64,size(initial,1),1),λ=[0.0])
        @test_throws ErrorException SC.solve_soc_targets(ctx_hot,pairA.full,nothing,nstates,settings;
            seed=settings["seeds"]["A"],map_index=1,solve_hook=wrongshape)
        nonfinite=(H,initial,prec,ik,imap)->(;converged=true,n_iter=1,
            X=fill(ComplexF64(NaN),size(initial)),λ=zeros(size(initial,2)))
        @test_throws ErrorException SC.solve_soc_targets(ctx_hot,pairA.full,nothing,nstates,settings;
            seed=settings["seeds"]["A"],map_index=1,solve_hook=nonfinite)
        false_residual=(H,initial,prec,ik,imap)->(;converged=true,n_iter=1,
            X=copy(initial),λ=zeros(size(initial,2)),n_matvec=0)
        recorded=Any[]
        @test_throws ErrorException SC.solve_soc_targets(ctx_hot,pairA.full,nothing,nstates,settings;
            seed=settings["seeds"]["A"],map_index=1,solve_hook=false_residual,
            progress=r->push!(recorded,r))
        residual_records=[r.record for r in recorded if hasproperty(r,:event) && r.event=="target_solve"]
        @test length(residual_records)==1
        @test length(only(residual_records).explicit_residuals_ha)==nstates
        @test maximum(only(residual_records).explicit_residuals_ha)>tol["residual_ha"]
    end

    ncolumns=nstates+settings["solver"]["auxiliary_states"]
    xa=SC.solver_initial(nothing,size(X[1],1),ncolumns,settings["seeds"]["A"])
    xb=SC.solver_initial(nothing,size(X[1],1),ncolumns,settings["seeds"]["B"])
    @testset "A/B start independently from positive ten-electron densities and new complex QR" begin
        @test initialA.report.seed != initialB.report.seed
        @test initialA.n !== initialB.n && initialA.n != initialB.n
        @test maximum(initialA.n) == minimum(initialA.n)
        @test norm(initialB.n-initialA.n) > 1e-8
        for initial in (initialA,initialB)
            @test minimum(initial.n)>0 && all(isfinite,initial.n)
            @test abs(basis.dvol*sum(initial.n)-ne) <= tol["electron_count_abs"]
            @test !initial.report.normalization_applied && !initial.report.prior_run_orbitals_used
        end
        @test xa != xb && !Base.mightalias(xa,xb)
        @test norm(xa'xa-I) <= tol["gram_norm"] && norm(xb'xb-I) <= tol["gram_norm"]
        @test norm(imag.(xa))>0 && norm(imag.(xb))>0
        @test xa == SC.solver_initial(nothing,size(X[1],1),ncolumns,settings["seeds"]["A"])
        oldxa=copy(xa)
        warm=SC.solver_initial(xa,size(xa,1),ncolumns,settings["seeds"]["B"])
        @test warm==xa && !Base.mightalias(warm,xa)
        extended=SC.solver_initial(xa,size(xa,1),ncolumns+8,settings["seeds"]["A"]+settings["seeds"]["extension_stride"])
        @test norm(extended'extended-I) <= tol["gram_norm"]
        @test norm(xa-extended*(extended'*xa)) <= tol["gram_norm"]
        @test xa == oldxa
        @test_throws ArgumentError SC.soc_initial_density(ctx_hot,"C",settings)
    end
    (;scope="Real Mg fractional-occupation operator/energy fixtures with synthetic spectra; no eigensolve or SCF",
      occupation_electron_residual=ensemble.report.electron_residual,
      per_k_unweighted_electrons=ensemble.report.electrons_per_k_unweighted,
      internal_energy_ha=snapshot.total,entropy_energy_ha=thermal.entropy_energy_ha,free_energy_ha=thermal.free_energy_ha,
      double_counting_difference_ha=snapshot.report.double_counting_difference_ha,
      equal_occupation_density_error=equal_density_error,unequal_occupation_density_change_l2=unequal_density_change,
      changed_input_potential_norm=potential_change,changed_input_h_action_norm=action_change,
      changed_input_hartree_potential_norm=hartree_change,changed_input_xc_potential_norm=xc_change)
end
