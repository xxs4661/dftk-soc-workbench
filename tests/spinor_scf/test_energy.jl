# Synthetic orbital factors on the actual B0 discretization. None of these
# orbitals comes from scalar/spinor SCF or represents a converged physical state.
function energy_test_rotate(X, ik, a, b, angle)
    result = copy.(X)
    old_a, old_b = copy(X[ik][:, a]), copy(X[ik][:, b])
    result[ik][:, a] = cos(angle)*old_a + sin(angle)*old_b
    result[ik][:, b] = -sin(angle)*old_a + cos(angle)*old_b
    result
end

function run_energy_tests(basis, settings)
    rng = MersenneTwister(56021)
    X = map(basis.kpoints) do kpt
        ng = length(DFTK.G_vectors(basis, kpt))
        trial = randn(rng, ComplexF64, 2ng, 16)
        trial[1:2:end, :] .*= 0.5  # Unequal component norms; only full columns are QR'd.
        Matrix(qr(trial).Q)[:, 1:16]
    end
    f = [vcat(ones(8), zeros(8)) for _ in basis.kpoints]
    saved_X, saved_f = copy.(X), copy.(f)
    snapshot = energy_snapshot(basis, X, f)
    supported = check_supported_basis(basis)
    factors = spinor_factors(basis, X, f)
    tol = settings["acceptance"]["energy_identity_abs_ha_cell"]
    checks = (:energy_term_sum_difference_ha, :direct_kinetic_difference_ha,
        :direct_nonlocal_difference_ha, :local_integral_difference_ha,
        :hartree_half_integral_difference_ha, :double_counting_difference_ha,
        :ewald_once_difference_ha, :psp_correction_once_difference_ha)
    summary = Dict{String,Any}("fixture"=>"Unconverged deterministic general complex QR spinors",
        "seed"=>56021, "energy_ha"=>snapshot.total, "identity_threshold_ha"=>tol,
        "identity_errors_ha"=>Dict(string(k)=>getproperty(snapshot.report,k) for k in checks))

    @testset "General complex component factors and seven-term energy" begin
        @test length(X) == 8
        @test X == saved_X && f == saved_f
        @test Set(keys(snapshot.terms)) == Set(["Kinetic", "AtomicLocal", "AtomicNonlocal",
                                               "Hartree", "Xc", "Ewald", "PspCorrection"])
        @test isfinite(snapshot.total)
        @test all(abs(getproperty(snapshot.report,k)) <= tol for k in checks)
        @test norm(snapshot.density.m) > 0  # Diagnostic spin density is not forcibly zeroed.
        @test size(snapshot.rho) == (basis.fft_size..., 1)
        @test vec(snapshot.rho) == snapshot.density.n
        @test abs(basis.dvol*sum(snapshot.density.n)-8) <= 1e-8
        @test abs(snapshot.report.electron_count_reciprocal-8) <= 1e-8
        @test 0 < snapshot.report.component_norm_min < 0.4
        @test 0.6 < snapshot.report.component_norm_max < 1
        for ik in eachindex(X)
            @test norm(X[ik]'X[ik]-I) <= 1e-11
            @test factors.chi[ik] == hcat(X[ik][1:2:end,:], X[ik][2:2:end,:])
            @test factors.fchi[ik] == vcat(f[ik],f[ik])
            @test sum(factors.fchi[ik]) == 16  # Factors are not 16 normalized electrons.
            counted = sum(factors.fchi[ik][j]*sum(abs2,factors.chi[ik][:,j])
                          for j in axes(factors.chi[ik],2))
            @test abs(counted-8) <= 1e-11
            @test all(abs(sum(abs2,v)-1)>0.1 for v in eachcol(factors.chi[ik]))
        end
        scalar_factor_density = DFTK.compute_density(basis, factors.chi, factors.fchi)
        @test norm(vec(scalar_factor_density)-snapshot.density.n)/norm(snapshot.density.n) <= 1e-11
        @test abs(snapshot.terms["Ewald"]-supported.ewald.energy) <= tol
        @test abs(snapshot.terms["PspCorrection"]-supported.psp_correction.energy) <= tol
        @test snapshot.report.energy_hamiltonian_calls == 1
        @test snapshot.report.xc_evaluations == snapshot.report.ewald_count == snapshot.report.psp_correction_count == 1
        @test abs(snapshot.report.hartree_half_integral_ha-snapshot.terms["Hartree"]) <= tol
        @test abs(sum(values(snapshot.terms))-snapshot.total) <= tol
        @test abs(snapshot.report.double_counting_total_ha-snapshot.total) <= tol

        # Independent direct XC term calls are test oracles, outside the main
        # single energy traversal. Passing external core would cause double NLCC.
        @test !isnothing(supported.xc.ρcore)
        @test norm(supported.xc.ρcore) > 0
        correct_xc = DFTK.ene_ops(supported.xc,basis,factors.chi,factors.fchi; ρ=snapshot.rho).E
        double_core_xc = DFTK.ene_ops(supported.xc,basis,factors.chi,factors.fchi;
                                    ρ=snapshot.rho+supported.xc.ρcore).E
        @test abs(snapshot.terms["Xc"]-correct_xc) <= tol
        @test abs(double_core_xc-correct_xc) > 1e-6
        @test abs(basis.dvol*sum(snapshot.rho+supported.xc.ρcore)-8) > 1e-6
        @test_throws ArgumentError SpinorSCFPrototype.valence_rho(basis,vec(snapshot.rho+supported.xc.ρcore))
        summary["double_core_xc_minus_correct_ha"] = double_core_xc-correct_xc

        matched = energy_snapshot(basis,X,f; expected_n=copy(snapshot.density.n))
        @test matched.total == snapshot.total
        wrong_density = copy(snapshot.density.n)
        wrong_density[1] += 1e-3
        wrong_density[2] -= 1e-3
        @test_throws ArgumentError energy_snapshot(basis,X,f; expected_n=wrong_density)
        @test_throws ArgumentError energy_snapshot(basis,X,f; expected_n=fill(NaN,length(wrong_density)))
        @test_throws ArgumentError energy_snapshot(basis,X,f; expected_n=snapshot.rho)
        bad_f = copy.(f); bad_f[1][1] = 2
        @test_throws ArgumentError energy_snapshot(basis,X,bad_f)
        bad_f[1][1] = NaN
        @test_throws ArgumentError energy_snapshot(basis,X,bad_f)
        bad_X = copy.(X); bad_X[1][1,1] = NaN
        @test_throws ArgumentError energy_snapshot(basis,bad_X,f)
        drifted = [x .* 1.001 for x in X]
        @test_throws ArgumentError energy_snapshot(basis,drifted,f)
        extra_model = DFTK.Model(basis.model; terms=vcat(basis.model.term_types,[DFTK.Entropy()]))
        extra_basis = DFTK.PlaneWaveBasis(basis; model=extra_model)
        @test_throws ArgumentError check_supported_basis(extra_basis)
        @test length(basis.terms) == length(basis.model.term_types) == 7
    end

    @testset "Charge-only energy invariance and density-dependent Hamiltonian" begin
        Uocc = Matrix(qr(randn(rng,ComplexF64,8,8)).Q)
        mixed = copy.(X)
        for x in mixed
            x[:,1:8] = x[:,1:8]*Uocc
        end
        smixed = energy_snapshot(basis,mixed,f)
        @test norm(smixed.density.n-snapshot.density.n)/norm(snapshot.density.n) <= 1e-11
        @test abs(smixed.total-snapshot.total) <= tol
        theta, phi = 0.41, 0.29
        U = ComplexF64[cos(theta) cis(phi)*sin(theta); -cis(-phi)*sin(theta) cos(theta)]
        @test norm(U'U-I) <= 1e-11 && abs(det(U)-1) <= 1e-11
        rotated = [reshape(U*reshape(x,2,:),size(x)) for x in X]
        srot = energy_snapshot(basis,rotated,f)
        @test norm(srot.density.n-snapshot.density.n)/norm(snapshot.density.n) <= 1e-11
        @test abs(srot.total-snapshot.total) <= tol
        @test norm(srot.density.m-snapshot.density.m) > 1e-6
        summary["equal_occupation_energy_difference_ha"] = smixed.total-snapshot.total
        summary["global_SU2_energy_difference_ha"] = srot.total-snapshot.total

        trial = energy_test_rotate(X,1,1,9,0.13)
        center = energy_snapshot(basis,trial,f)
        @test norm(center.density.n-snapshot.density.n) > 1e-6
        @test norm(center.vH-snapshot.vH) > 1e-6
        @test norm(center.vxc-snapshot.vxc) > 1e-6
        @test norm(center.local_potential-snapshot.local_potential) > 1e-6
        probe = randn(MersenneTwister(56022),ComplexF64,size(X[1],1),1)
        probe ./= norm(probe)
        effect = ComponentOperator(center.ham[1],2)*probe - ComponentOperator(snapshot.ham[1],2)*probe
        @test norm(effect) > 1e-7
        @test_throws ArgumentError energy_snapshot(basis,trial,f; expected_n=snapshot.density.n)
        summary["changed_density_h_probe_norm"] = norm(effect)

        # Independent analytic expectation versus three full nonlinear energy
        # differences: each ±h rebuilds its own density/Hartree/XC. No SCF.
        a, b = trial[1][:,1], trial[1][:,9]
        analytic = 2basis.kweights[1]*(f[1][1]-f[1][9]) *
                   real(dot(b,ComponentOperator(center.ham[1],2)*a))
        @test abs(analytic) > 1e-5
        fd = map((1e-3,3e-4,1e-4)) do h
            plus = energy_snapshot(basis,energy_test_rotate(trial,1,1,9,h),f)
            minus = energy_snapshot(basis,energy_test_rotate(trial,1,1,9,-h),f)
            numeric = (plus.total-minus.total)/(2h)
            @test norm(plus.density.n-minus.density.n) > 0
            @test norm(plus.vH-minus.vH) > 0 && norm(plus.vxc-minus.vxc) > 0
            (; h_rad=h, numeric_ha_per_rad=numeric,
               normalized_error=abs(numeric-analytic)/max(1,abs(analytic)))
        end
        @test last(fd).normalized_error <= settings["acceptance"]["directional_derivative_normalized"]
        summary["nonstationary_analytic_derivative_ha_per_rad"] = analytic
        summary["directional_differences"] = fd
    end
    (; X,f,snapshot,summary)
end
