# All matrices here are synthetic protocol/math fixtures, not pseudopotentials.
using Test, LinearAlgebra, Random

function run_spin_trace_tests()
    ST = SpinTrace
    RP = RelativisticProjectors
    rng = MersenneTwister(810062)
    tol = 1e-11
    spatial = 7
    raw = randn(rng, ComplexF64, 2spatial, 2spatial)
    V = (raw + raw') / 2
    fr = RP.FRNonlocalOperator(Matrix{ComplexF64}(I, 2spatial, 2spatial), V)
    N = ST.SpinTraceNonlocal(fr)
    u, d = 1:2:2spatial, 2:2:2spatial
    W = (V[u, u] + V[d, d]) / 2
    dense_null = kron(W, Matrix{ComplexF64}(I, 2, 2))
    X = randn(rng, ComplexF64, 2spatial, 3)
    oldX, oldP, oldD = copy(X), copy(fr.P), copy(fr.D)
    err(a, b) = norm(a-b) / max(norm(a), norm(b), 1)
    math_errors = Float64[]

    @testset "Synthetic complex block trace and independent Pauli twirl" begin
        @test size(N) == (2spatial, 2spatial)
        @test size(N, 3) == 1
        @test eltype(N) === ComplexF64
        @test_throws ArgumentError size(N, 0)
        @test err(N*X, dense_null*X) <= tol
        @test err(N*X[:, 1], dense_null*X[:, 1]) <= tol
        @test err(N*Matrix{Float64}(I, 2spatial, 2spatial), dense_null) <= tol
        twirl = copy(V)
        for sigma in (ComplexF64[0 1; 1 0], ComplexF64[0 -im; im 0], ComplexF64[1 0; 0 -1])
            # Dense Kronecker action is intentionally independent of spin_apply.
            S = kron(Matrix{Float64}(I, spatial, spatial), sigma)
            twirl += S * V * S
            @test err(ST.spin_apply(sigma, X), S*X) <= tol
        end
        twirl /= 4
        @test err(twirl, dense_null) <= tol
        @test err(ST.pauli_twirl_action(fr, X), twirl*X) <= tol
        @test err(V, V') <= tol
        @test err(dense_null, dense_null') <= tol
        @test err(tr(V), tr(dense_null)) <= tol
        @test err(dense_null[u, u]+dense_null[d, d], V[u, u]+V[d, d]) <= tol
        @test err(N*X, fr*X) > 100tol # A spin-dependent fixture, not the scalar limit.
        for (theta, phi) in ((.371, .293), (.882, -.651), (-.245, 1.197))
            U = ComplexF64[cos(theta) cis(phi)*sin(theta); -cis(-phi)*sin(theta) cos(theta)]
            S = kron(Matrix{Float64}(I, spatial, spatial), U)
            @test err(U'*U, Matrix{ComplexF64}(I, 2, 2)) <= tol
            @test err(N*(S*X), S*(N*X)) <= tol
        end
        # A genuinely spin-independent synthetic operator remains unchanged.
        scalar = randn(rng, ComplexF64, spatial, spatial)
        scalar = (scalar+scalar')/2
        V0 = kron(scalar, Matrix{ComplexF64}(I, 2, 2))
        fr0 = RP.FRNonlocalOperator(Matrix{ComplexF64}(I, 2spatial, 2spatial), V0)
        @test err(ST.SpinTraceNonlocal(fr0)*X, V0*X) <= tol
        push!(math_errors, err(N*X, dense_null*X), err(twirl, dense_null))
    end

    @testset "Synthetic rectangular complex P, radial D, and prohibited null faults" begin
        P = randn(rng, ComplexF64, 2spatial, 5)
        rawD = randn(rng, ComplexF64, 5, 5)
        D = (rawD+rawD')/2
        rectangular = RP.FRNonlocalOperator(P, D)
        null = ST.SpinTraceNonlocal(rectangular)
        full = P*D*P'
        Wu = full[u, u]; Wd = full[d, d]
        expected = kron((Wu+Wd)/2, Matrix{ComplexF64}(I, 2, 2))
        @test err(null*X, expected*X) <= tol
        @test err(null*X, ST.pauli_twirl_action(rectangular, X)) <= tol
        @test err(tr(expected), tr(full)) <= tol
        offdiag_only = zeros(ComplexF64, size(full))
        offdiag_only[u, u] = Wu; offdiag_only[d, d] = Wd
        omitted_half = 2expected
        Pu, Pd = P[u, :], P[d, :]
        omitted_conjugate = kron((Pu*D*transpose(Pu)+Pd*D*transpose(Pd))/2,
                                 Matrix{ComplexF64}(I, 2, 2))
        dropped_all = zero(expected)
        @test err(offdiag_only*X, expected*X) > 100tol
        @test err(omitted_half*X, expected*X) > 100tol
        @test err(omitted_conjugate*X, expected*X) > 100tol
        @test err(dropped_all*X, expected*X) > 100tol
        @test err(offdiag_only[u, u], offdiag_only[d, d]) > 100tol
        @test err(omitted_conjugate, omitted_conjugate') > 100tol
        @test_throws DimensionMismatch ST.SpinTraceNonlocal(RP.FRNonlocalOperator(ones(ComplexF64, 3, 1), ones(1, 1)))
        push!(math_errors, err(null*X, expected*X))
    end

    @testset "Output publication and read-only operator/input storage" begin
        Y = fill(ComplexF64(NaN), size(X))
        @test mul!(Y, N, X, 1, 0) === Y
        @test err(Y, dense_null*X) <= tol
        oldY = copy(Y)
        @test mul!(Y, N, X, .7+.2im, -.3im) === Y
        @test err(Y, (.7+.2im).*(dense_null*X) .- .3im.*oldY) <= tol
        @test_throws ArgumentError mul!(X, N, X)
        @test_throws ArgumentError mul!(@view(X[:, :]), N, X)
        @test_throws ArgumentError mul!(@view(fr.P[:, 1:3]), N, X)
        @test_throws ArgumentError mul!(@view(fr.D[:, 1:3]), N, X)
        @test_throws DimensionMismatch mul!(zeros(ComplexF64, 2spatial-1, 3), N, X)
        @test_throws DimensionMismatch N*zeros(ComplexF64, 2spatial, 0)
        @test_throws ArgumentError mul!(zeros(ComplexF32, size(X)), N, X)
        @test_throws ArgumentError N*ComplexF32.(X)
        @test_throws ArgumentError mul!(Y, N, X, NaN, 0)
        @test_throws ArgumentError mul!(Y, N, X, big"1e1000", 0)
        bad = copy(X); bad[1] = Inf
        before = copy(Y)
        @test_throws ArgumentError mul!(Y, N, bad)
        @test Y == before
        Y .= NaN
        @test_throws ArgumentError mul!(Y, N, X, 1, 1)
        @test X == oldX && fr.P == oldP && fr.D == oldD
        @test N.original === fr
    end
    (; scope="Synthetic complex matrix tests only; no UPF, model, SCF or eigensolve",
       seed=810062, threshold=tol, maximum_math_error=maximum(math_errors))
end

"""Invoke only from the authorized new-Si static/final-density task; no extra solve."""
function run_real_si_spin_trace_tests(full; seed)
    FI = FRIntegration
    ctx = full.context
    @test ctx.mode == :real_fr
    @test length(ctx.bundles) == 2
    @test all(b -> b.common.element == :Si && b.common.has_nlcc, ctx.bundles)
    @test ctx.basis.model.n_electrons == 8
    @test iszero(norm(ctx.basis.kpoints[full.ik].coordinate))
    @test Set(l.l for l in full.fr.labels) == Set((0, 1, 2))
    old = FI.full_operator_stats(full)
    N = SpinTrace.spin_trace_hamiltonian(full)
    X = randn(MersenneTwister(seed), ComplexF64, size(full, 1), 3)
    P, D = copy(full.fr.P), copy(full.fr.D)
    FI.reset_full_counters!(N)
    N*X
    @test FI.full_operator_stats(full) == old
    @test FI.full_operator_stats(N).full_mul_calls == 1
    @test FI.full_operator_stats(N).fr_mul_calls == 1
    @test FI.full_operator_stats(N).common.scalar_mul_calls == 2
    @test N.common.scalar === full.scalar_binding
    @test N.fr.original === ctx.fr_blocks[full.ik]
    @test N.common !== full.common
    @test full.fr.P == P && full.fr.D == D
    @test_throws ArgumentError mul!(@view(full.fr.P[:, 1:3]), N, X)
    report = SpinTrace.spin_trace_diagnostics(full; seed)
    @test report.status == "PASS"
    @test report.spin_dependent_action_norm > report.threshold
    @test report.nonlocal_action_norm > report.threshold
    @test FI.validate_context(ctx)
    report
end
