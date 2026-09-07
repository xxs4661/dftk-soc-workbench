# Model-interface tests only: no eigensolve, occupations, entropy calculation,
# density feedback or SCF. The existing zero-temperature context is supplied by
# the runner; a second context is built at the predeclared electronic tau [Ha].
function run_temperature_tests(ctx_zero, settings)
    FI = FRIntegration
    tau = settings["ensemble"]["tau_ha"]
    cold = ctx_zero.basis
    build(; kwargs...) = FI.build_context(ctx_zero.bundles, cold.model.lattice,
        cold.model.positions, [k.coordinate for k in cold.kpoints], cold.kweights;
        Ecut=cold.Ecut, xc_identifiers=ctx_zero.xc_identifiers, mode=ctx_zero.mode, kwargs...)
    hot = build(; temperature=tau, smearing=DFTK.Smearing.FermiDirac())
    @testset "Explicit electronic temperature with exactly six common internal-energy terms" begin
        @test tau == 0.001
        @test FI.validate_context(ctx_zero)
        @test cold.model.temperature === 0.0
        @test cold.model.smearing isa DFTK.Smearing.None
        @test cold.model.model_name == "Phase 6B common-only integration"
        @test FI.validate_context(hot)
        @test hot.basis.model.temperature === Float64(tau)
        @test hot.basis.model.smearing isa DFTK.Smearing.FermiDirac
        @test hot.basis.model.n_electrons == cold.model.n_electrons
        @test hot.basis.kweights == cold.kweights
        @test hot.basis.model.positions == cold.model.positions
        @test hot.basis.model.lattice == cold.model.lattice
        for ctx in (ctx_zero, hot)
            model, basis = ctx.basis.model, ctx.basis
            @test length(model.term_types) == 6
            @test length(basis.terms) == 6
            @test count(t -> t isa DFTK.Entropy, model.term_types) == 0
            @test count(t -> t isa DFTK.TermEntropy, basis.terms) == 0
            @test count(t -> t isa DFTK.AtomicNonlocal, model.term_types) == 0
            @test count(t -> t isa DFTK.TermAtomicNonlocal, basis.terms) == 0
        end
        @test typeof.(cold.model.term_types) == typeof.(hot.basis.model.term_types)
        @test_throws ArgumentError build(; temperature=tau) # No hidden smearing default change.
        @test_throws ArgumentError build(; temperature=0.0, smearing=DFTK.Smearing.FermiDirac())
        @test_throws ArgumentError build(; temperature=tau, smearing=DFTK.Smearing.Gaussian())
        for invalid in (-0.001, Inf, NaN, big"1e1000", true)
            @test_throws ArgumentError build(; temperature=invalid, smearing=DFTK.Smearing.FermiDirac())
        end
    end

    n = fill(cold.model.n_electrons / cold.model.unit_cell_volume, prod(cold.fft_size))
    cold_h = FI.build_full_hamiltonian(ctx_zero, n)
    hot_h = FI.build_full_hamiltonian(hot, n)
    rng = MersenneTwister(settings["seeds"]["symmetry_probe"])
    probe = randn(rng, ComplexF64, size(cold_h.full[1], 1), 2)
    probe ./= norm(probe)
    action_error = FI.integration_error(cold_h.full[1]*probe, hot_h.full[1]*probe)
    @testset "Temperature changes ensemble metadata, not the fixed-density internal-energy operator" begin
        @test action_error <= settings["thresholds"]["hamiltonian_decomposition_normalized"]
        @test FI.integration_error(DFTK.total_local_potential(cold_h.common),
                                  DFTK.total_local_potential(hot_h.common)) <= 1e-10
        @test all(cold_h.full[i].fr.P == hot_h.full[i].fr.P &&
                  cold_h.full[i].fr.D == hot_h.full[i].fr.D for i in eachindex(cold_h.full))
        @test FI._FR_CONTEXT_CERTIFICATES[ctx_zero].snapshot.temperature === 0.0
        @test FI._FR_CONTEXT_CERTIFICATES[hot].snapshot.temperature === Float64(tau)
        @test FI._FR_CONTEXT_CERTIFICATES[hot].snapshot.smearing isa DFTK.Smearing.FermiDirac
    end

    @testset "Changed temperature/smearing cannot retain an old context's identity" begin
        # The upstream Model is immutable. These explicit fault fixtures corrupt
        # only the expected settings in the EXISTING certificate, then restore
        # them; no unsafe Model mutation or new identity mechanism is introduced.
        cert = FI._FR_CONTEXT_CERTIFICATES[hot]
        for mismatch in ((;temperature=2tau), (;smearing=DFTK.Smearing.None()))
            try
                FI._FR_CONTEXT_CERTIFICATES[hot] = merge(cert, (;snapshot=merge(cert.snapshot, mismatch)))
                @test_throws ArgumentError FI.validate_context(hot)
                @test_throws ArgumentError hot_h.full[1] * probe
            finally
                FI._FR_CONTEXT_CERTIFICATES[hot] = cert
            end
        end
        @test FI.validate_context(hot)
        oldterms = copy(hot.basis.model.term_types)
        try
            push!(hot.basis.model.term_types, DFTK.Entropy())
            @test_throws ArgumentError FI.validate_context(hot)
            @test_throws ArgumentError hot_h.full[1] * probe
        finally
            empty!(hot.basis.model.term_types)
            append!(hot.basis.model.term_types, oldterms)
        end
        @test FI.validate_context(hot) && FI.validate_context(ctx_zero)
    end
    (;scope="Fixed model and Hamiltonian interface only; no occupations/eigensolve/SCF",
      zero_temperature_ha=cold.model.temperature, finite_temperature_ha=hot.basis.model.temperature,
      finite_smearing=string(typeof(hot.basis.model.smearing)), common_term_count=length(hot.basis.terms),
      native_entropy_term_count=count(t -> t isa DFTK.TermEntropy, hot.basis.terms),
      same_density_hamiltonian_normalized_error=action_error)
end
