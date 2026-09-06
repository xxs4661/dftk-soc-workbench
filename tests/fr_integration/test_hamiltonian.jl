# Explicit missing/double fixtures test numerical action, not a reported count.
# These operators are deliberately invalid and are never used by the runtime.
struct HamiltonianMultiplicityFault{C,F}
    common::C
    fr::F
    copies::Int
end
Base.:*(H::HamiltonianMultiplicityFault, X) = H.common * X + H.copies .* (H.fr * X)

function run_hamiltonian_tests(ctx_mg, ctx_si, settings)
    FI = FRIntegration
    tol = settings["thresholds"]["hamiltonian_decomposition_normalized"]
    rng = MersenneTwister(settings["seeds"]["symmetry_probe"])
    basis = ctx_mg.basis
    n = fill(basis.model.n_electrons / basis.model.unit_cell_volume, prod(basis.fft_size))
    built = FI.build_full_hamiltonian(ctx_mg, n)
    H = built.full[1]
    X = randn(rng, ComplexF64, size(H, 2), 3)
    X ./= norm(X)
    oldX = copy(X)
    expected = H.common * X + H.fr * X
    errors = Float64[]

    @testset "Six common terms plus one actual FR action" begin
        @test FI.validate_context(ctx_mg)
        @test length(basis.model.term_types) == 6
        @test count(t -> t isa DFTK.AtomicNonlocal, basis.model.term_types) == 0
        @test count(t -> t isa DFTK.TermAtomicNonlocal, basis.terms) == 0
        @test all(isnothing(block.nonlocal_op) for block in built.common.blocks if hasproperty(block, :nonlocal_op))
        @test size(H) == size(H.fr) == (2length(basis.kpoints[1].G_vectors), 2length(basis.kpoints[1].G_vectors))
        @test eltype(H) == ComplexF64
        @test X == oldX
        FI.reset_full_counters!(H)
        actual = H * X
        @test FI.integration_error(actual, expected) <= tol
        @test X == oldX
        # Same physical common operators through the alternative frozen block interface.
        generic_ops = copy(built.common[1].operators)
        generic = DFTK.GenericHamiltonianBlock(basis, basis.kpoints[1], generic_ops,
            DFTK.optimize_operators(generic_ops), nothing)
        generic_full = FI.FullHamiltonianBlock(ctx_mg, 1, generic, H.fr)
        @test FI.integration_error(generic_full * X, expected) <= tol
        generic_potential = only(filter(op -> op isa DFTK.RealSpaceMultiplication,
            generic.optimized_operators)).potential
        realstorage = vec(generic_potential)
        complexstorage = reinterpret(ComplexF64, @view realstorage[1:2*(length(realstorage)÷2)])
        @test length(complexstorage) >= size(H, 1)
        @test_throws ArgumentError mul!(@view(complexstorage[1:size(H,1)]), generic_full, X[:,1])
        stats = FI.full_operator_stats(H)
        @test (stats.full_mul_calls, stats.fr_mul_calls, stats.full_columns, stats.fr_columns) == (1, 1, 3, 3)
        @test stats.common.scalar_mul_calls == 2
        @test stats.common.scalar_columns == 6
        for ik in eachindex(built.full)
            block = built.full[ik]
            probe = randn(rng, ComplexF64, size(block, 2), 2)
            probe ./= norm(probe)
            check = FI.check_full_decomposition(block, block.common, block.fr, probe; atol=tol)
            push!(errors, check.normalized_error)
            @test check.normalized_error <= tol
            @test check.nonlocal_signal_norm > 100tol
            @test_throws ArgumentError FI.check_full_decomposition(
                HamiltonianMultiplicityFault(block.common, block.fr, 0), block.common, block.fr, probe; atol=tol)
            @test_throws ArgumentError FI.check_full_decomposition(
                HamiltonianMultiplicityFault(block.common, block.fr, 2), block.common, block.fr, probe; atol=tol)
        end
        v = copy(X[:, 1]); y = copy(X[:, 2])
        @test FI.integration_error(H*v, expected[:, 1]) <= tol
        @test FI.integration_error(dot(v, H*y), dot(H*v, y)) <= settings["thresholds"]["hermiticity_normalized"]
        down = copy(v); down[1:2:end] .= 0
        common = H.common * down
        full = H * down
        fr = H.fr * down
        @test all(iszero, common[1:2:end])
        signal = norm(fr[1:2:end])
        @test signal > settings["thresholds"]["spin_flip_min_signal"]
        @test norm(full[1:2:end]-fr[1:2:end])/signal <= settings["thresholds"]["spin_flip_relative"]
    end

    @testset "mul! publication, finite inputs and retained-storage aliases" begin
        Y = fill(ComplexF64(NaN), size(X))
        @test mul!(Y, H, X, 1, 0) === Y
        @test FI.integration_error(Y, expected) <= tol
        oldY = copy(Y)
        mul!(Y, H, X, 0.7 + 0.2im, -0.3im)
        @test FI.integration_error(Y, (0.7+0.2im).*expected .- 0.3im.*oldY) <= tol
        @test_throws ArgumentError mul!(X, H, X)
        @test X == oldX
        @test_throws ArgumentError mul!(@view(X[:, :]), H, X)
        @test_throws ArgumentError mul!(@view(H.fr.P[:, 1:3]), H, X)
        @test_throws DimensionMismatch mul!(zeros(ComplexF64, size(X,1)-1, 3), H, X)
        @test_throws DimensionMismatch H * zeros(ComplexF64, size(X,1), 0)
        @test_throws ArgumentError mul!(zeros(ComplexF32, size(X)), H, X)
        invalid = copy(X); invalid[1] = Inf
        Y .= 42; saved = copy(Y)
        @test_throws ArgumentError mul!(Y, H, invalid)
        @test Y == saved
        @test_throws ArgumentError mul!(Y, H, X, NaN, 0)
        @test_throws ArgumentError mul!(Y, H, X, big"1e1000", 0)
        @test Y == saved
        Y .= NaN
        @test_throws ArgumentError mul!(Y, H, X, 1, 1)
        # Protect the optimized common potential even through a differently typed view.
        scalar = H.common.scalar
        if hasproperty(scalar, :local_op)
            potential = scalar.local_op.potential
            realstorage = vec(potential)
            storage = reinterpret(ComplexF64, @view realstorage[1:2*(length(realstorage)÷2)])
            @test length(storage) >= size(H, 1)
            @test_throws ArgumentError mul!(@view(storage[1:size(H,1)]), H, X[:,1])
        end
    end

    @testset "Issued source, physical k and basis metadata cannot be interchanged" begin
        @test_throws ArgumentError FI.build_context(ctx_mg.bundles, basis.model.lattice,
            basis.model.positions, [k.coordinate for k in basis.kpoints], basis.kweights;
            Ecut=basis.Ecut, xc_identifiers=ctx_si.xc_identifiers, mode=:real_fr)
        @test_throws ArgumentError FI.build_context(ctx_si.bundles, ctx_si.basis.model.lattice,
            ctx_si.basis.model.positions, [k.coordinate for k in ctx_si.basis.kpoints], ctx_si.basis.kweights;
            Ecut=ctx_si.basis.Ecut, xc_identifiers=ctx_si.xc_identifiers, mode=:real_fr)
        forged = FI.FRHamiltonianContext(basis, ctx_mg.bundles, ctx_mg.fr_blocks,
                                        ctx_mg.mode, ctx_mg.xc_identifiers)
        @test_throws ArgumentError FI.validate_context(forged)
        @test size(built.full[2]) == size(built.full[3])
        swapped = copy(ctx_mg.fr_blocks); swapped[2], swapped[3] = swapped[3], swapped[2]
        @test_throws ArgumentError FI.compose_full_hamiltonian(ctx_mg, built.common; fr_blocks=swapped)
        @test_throws ArgumentError FI.FullHamiltonianBlock(ctx_mg, 2, built.common.blocks[3], ctx_mg.fr_blocks[2])
        @test_throws ArgumentError FI.compose_full_hamiltonian(ctx_mg, built.common; fr_blocks=ctx_mg.fr_blocks[1:2])
        @test_throws ArgumentError FI.compose_full_hamiltonian(ctx_mg, built.common; fr_blocks=vcat(ctx_mg.fr_blocks, ctx_mg.fr_blocks[1:1]))
        foreignbasis = DFTK.PlaneWaveBasis(basis.model; Ecut=basis.Ecut, kgrid=basis.kgrid)
        foreignham = DFTK.energy_hamiltonian(foreignbasis, nothing, nothing; ρ=built.rho).ham
        @test size(foreignham[1]) == size(built.common[1])
        @test_throws ArgumentError FI.compose_full_hamiltonian(ctx_mg, foreignham)
        kpt = basis.kpoints[1]
        oldG = copy(kpt.G_vectors)
        try
            kpt.G_vectors[1], kpt.G_vectors[2] = kpt.G_vectors[2], kpt.G_vectors[1]
            @test_throws ArgumentError FI.validate_context(ctx_mg)
            @test_throws ArgumentError H * X
        finally
            kpt.G_vectors .= oldG
        end
        oldmap = copy(kpt.mapping)
        try
            kpt.mapping[1], kpt.mapping[2] = kpt.mapping[2], kpt.mapping[1]
            @test_throws ArgumentError FI.validate_context(ctx_mg)
        finally
            kpt.mapping .= oldmap
        end
        oldpositions = copy(ctx_si.basis.model.positions)
        try
            reverse!(ctx_si.basis.model.positions)
            @test_throws ArgumentError FI.validate_context(ctx_si)
        finally
            ctx_si.basis.model.positions .= oldpositions
        end
        oldterms = copy(basis.model.term_types)
        try
            push!(basis.model.term_types, DFTK.AtomicNonlocal())
            @test_throws ArgumentError FI.validate_context(ctx_mg)
            @test_throws ArgumentError H * X
        finally
            empty!(basis.model.term_types); append!(basis.model.term_types, oldterms)
        end
        for xc in (only(filter(t -> t isa DFTK.Xc, basis.model.term_types)),
                   only(filter(t -> t isa DFTK.TermXc, basis.terms)))
            original = copy(xc.functionals)
            try
                xc.functionals[1] = DFTK.DispatchFunctional(:lda_x)
                @test_throws ArgumentError FI.validate_context(ctx_mg)
                @test_throws ArgumentError H * X
            finally
                xc.functionals .= original
            end
        end
        P = ctx_mg.fr_blocks[1].P; oldentry = P[1]
        try
            P[1] += 0.1
            @test_throws ArgumentError FI.compose_full_hamiltonian(ctx_mg, built.common)
        finally
            P[1] = oldentry
        end
        @test FI.validate_context(ctx_mg) && FI.validate_context(ctx_si)
    end

    @testset "Reference density remains valence-only and fixed" begin
        @test vec(built.rho) == n
        @test abs(sum(built.rho)*basis.dvol-basis.model.n_electrons) <= settings["thresholds"]["electron_count_abs"]
        @test_throws ArgumentError FI.build_full_hamiltonian(ctx_mg, n .* 2)
        @test_throws ArgumentError FI.build_full_hamiltonian(ctx_mg, n[1:end-1])
        invalid = copy(n); invalid[1] = NaN
        @test_throws ArgumentError FI.build_full_hamiltonian(ctx_mg, invalid)
        invalid = copy(n); invalid[1] = -1
        @test_throws ArgumentError FI.build_full_hamiltonian(ctx_mg, invalid)
        @test n == fill(basis.model.n_electrons / basis.model.unit_cell_volume, length(n))
    end
    (;scope="Fixed-density operator fixtures on original Mg and scalar Si; no diagonalization or SCF",
       max_full_decomposition_error=maximum(errors), actual_common_term_count=length(basis.model.term_types))
end
