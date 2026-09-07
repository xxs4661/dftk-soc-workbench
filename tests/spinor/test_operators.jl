# All matrices here are synthetic algebra fixtures, not physical Hamiltonians.
# Algebra error = norm(actual-reference)/max(norm(reference),1), with 1e-11
# tolerance. The separate iterative-solver test recomputes Euclidean residuals.
operator_test_error(actual, expected) = norm(actual - expected) / max(norm(expected), 1)

function run_operator_tests()
    rng = MersenneTwister(50319)
    @testset "Component-interleaved scalar lift (synthetic matrices)" begin
        ng = 5
        raw = randn(rng, ComplexF64, ng, ng)
        H = Hermitian(raw + raw')
        saved_H = copy(H)
        for ncomp in (1, 2, 3)
            A = ComponentOperator(H, ncomp)
            reference = kron(Matrix(H), Matrix{ComplexF64}(I, ncomp, ncomp))
            @test size(A) == size(reference)
            @test size(A, 1) == size(A, 2) == ncomp * ng
            @test size(A, 3) == 1
            @test eltype(A) == eltype(typeof(A)) == ComplexF64
            @test_throws ArgumentError size(A, 0)

            X = randn(rng, ComplexF64, ncomp * ng, 3)
            saved_X = copy(X)
            x = randn(rng, ComplexF64, ncomp * ng)
            y = randn(rng, ComplexF64, ncomp * ng)
            @test operator_test_error(A * X, reference * X) <= 1e-11
            @test operator_test_error(A * x, reference * x) <= 1e-11
            @test operator_test_error(dot(x, A * y), dot(A * x, y)) <= 1e-11

            Y = fill(ComplexF64(NaN, NaN), size(X))
            @test mul!(Y, A, X) === Y
            @test operator_test_error(Y, reference * X) <= 1e-11
            alpha, beta = 0.3 + 0.2im, -0.4 + 0.7im
            Y0 = randn(rng, ComplexF64, size(X))
            Y .= Y0
            @test mul!(Y, A, X, alpha, beta) === Y
            @test operator_test_error(Y, alpha * reference * X + beta * Y0) <= 1e-11
            @test X == saved_X
            @test H == saved_H

            # Noncontiguous input and output views retain unrelated storage.
            input_backing = randn(rng, ComplexF64, 2ncomp * ng, 6)
            Xview = @view input_backing[1:2:end, 1:2:end]
            saved_backing = copy(input_backing)
            output_backing = zeros(ComplexF64, 2ncomp * ng, 6)
            Yview = @view output_backing[1:2:end, 1:2:end]
            mul!(Yview, A, Xview)
            @test operator_test_error(Yview, reference * Xview) <= 1e-11
            @test input_backing == saved_backing
            @test all(iszero, output_backing[2:2:end, :])
            @test all(iszero, output_backing[:, 2:2:end])

            reset_counters!(A)
            mul!(Y, A, X)
            A * x
            @test operator_stats(A) == (; operator_mul_calls=2, operator_columns=4,
                                       scalar_mul_calls=2ncomp, scalar_columns=4ncomp)
            reset_counters!(A)
            @test all(iszero, values(operator_stats(A)))

            # Alias rejection happens before modifying the caller's input.
            @test_throws ArgumentError mul!(X, A, X)
            @test X == saved_X
            overlapping = randn(rng, ComplexF64, ncomp * ng + 1, 3)
            before_overlap = copy(overlapping)
            @test_throws ArgumentError mul!(@view(overlapping[2:end, :]), A,
                                           @view(overlapping[1:end-1, :]))
            @test overlapping == before_overlap
            @test_throws DimensionMismatch A * zeros(ComplexF64, ncomp * ng + 1)
            @test_throws DimensionMismatch mul!(zeros(ComplexF64, ncomp * ng, 2), A, X)
            @test_throws DimensionMismatch mul!(zeros(ComplexF64, ncomp * ng, 1), A, x)
        end
        @test_throws ArgumentError ComponentOperator(H, 0)
        @test_throws ArgumentError ComponentOperator(H, -1)
        @test_throws ArgumentError ComponentOperator(H, true)
        @test_throws ArgumentError ComponentOperator(zeros(0, 0), 2)
        @test_throws DimensionMismatch ComponentOperator(zeros(2, 3), 2)

        # A single global SU(2) rotation acts on components, independently of G.
        theta, phi = 0.37, 0.29
        U = ComplexF64[cos(theta) cis(phi)*sin(theta);
                      -cis(-phi)*sin(theta) cos(theta)]
        @test norm(U'U - I) <= 1e-11
        @test abs(det(U) - 1) <= 1e-11
        S = kron(Matrix{ComplexF64}(I, ng, ng), U)
        A = ComponentOperator(H, 2)
        X = randn(rng, ComplexF64, 2ng, 3)
        @test operator_test_error(A * (S * X), S * (A * X)) <= 1e-11
    end

    @testset "Positive component kinetic preconditioner" begin
        kinetic = [0.0, 0.5, 2.0, 5.0]
        for ncomp in (1, 2, 3)
            P = ComponentKineticPreconditioner(kinetic, ncomp; shift=1.0)
            diagonal = repeat(kinetic .+ 1.0; inner=ncomp)
            reference = Diagonal(diagonal)
            @test P.diagonal == diagonal
            @test all(>(0), P.diagonal)
            @test size(P) == size(reference)
            @test size(P, 1) == size(P, 2) == length(diagonal)
            @test size(P, 3) == 1
            @test eltype(P) == eltype(typeof(P)) == Float64
            @test_throws ArgumentError size(P, 0)
            for R in (randn(rng, ComplexF64, length(diagonal)),
                      randn(rng, ComplexF64, length(diagonal), 3))
                saved_R = copy(R)
                @test operator_test_error(P * R, reference * R) <= 1e-11
                @test operator_test_error(P \ R, reference \ R) <= 1e-11
                Y = similar(R)
                @test ldiv!(Y, P, R) === Y
                @test operator_test_error(Y, reference \ R) <= 1e-11
                @test R == saved_R
                inplace = copy(R)
                @test ldiv!(P, inplace) === inplace
                @test operator_test_error(inplace, reference \ R) <= 1e-11
                @test mul!(inplace, P, inplace) === inplace
                @test operator_test_error(inplace, R) <= 1e-11
            end
            overlapping = randn(rng, ComplexF64, length(diagonal) + 1, 2)
            saved_overlap = copy(overlapping)
            @test_throws ArgumentError ldiv!(@view(overlapping[2:end, :]), P,
                                             @view(overlapping[1:end-1, :]))
            @test overlapping == saved_overlap
            @test_throws DimensionMismatch P \ zeros(length(diagonal) + 1)
        end
        @test_throws ArgumentError ComponentKineticPreconditioner(kinetic, 0)
        @test_throws ArgumentError ComponentKineticPreconditioner(kinetic, true)
        @test_throws ArgumentError ComponentKineticPreconditioner(Float64[], 2)
        @test_throws ArgumentError ComponentKineticPreconditioner([-1.0, 2.0], 2)
        @test_throws ArgumentError ComponentKineticPreconditioner([NaN, 2.0], 2)
        @test_throws ArgumentError ComponentKineticPreconditioner(kinetic, 2; shift=0)
        @test_throws ArgumentError ComponentKineticPreconditioner(kinetic, 2; shift=Inf)
    end

    @testset "Frozen LOBPCG interface on a synthetic component operator" begin
        ng, ncomp, ntarget, ntrial = 40, 2, 6, 8
        Q = Matrix(qr(randn(rng, ComplexF64, ng, ng)).Q)
        H = Hermitian(Q * Diagonal(collect(range(0.5, 10.0; length=ng))) * Q')
        saved_H = copy(H)
        A = ComponentOperator(H, ncomp)
        X0 = Matrix(qr(randn(rng, ComplexF64, ncomp * ng, ntrial)).Q)[:, 1:ntrial]
        saved_X0 = copy(X0)
        @test norm(X0'X0 - I) <= 1e-11
        @test all(norm(X0[c:ncomp:end, state]) > 0 for c in 1:ncomp, state in 1:ntrial)
        P = ComponentKineticPreconditioner(zeros(ng), ncomp; shift=1.0)
        result = SpinorPrototype.DFTK.lobpcg_hyper(A, X0; prec=P, tol=1e-10,
                    maxiter=300, miniter=1, n_conv_check=ntarget)
        @test result.converged
        @test result.n_iter > 0
        calls_after_solver = operator_stats(A)
        @test calls_after_solver.operator_mul_calls > 0
        @test calls_after_solver.scalar_mul_calls == ncomp * calls_after_solver.operator_mul_calls
        @test calls_after_solver.scalar_columns == ncomp * calls_after_solver.operator_columns
        @test X0 == saved_X0
        @test H == saved_H
        target_X = result.X[:, 1:ntarget]
        target_values = result.λ[1:ntarget]
        residual = A * target_X - target_X .* transpose(target_values)
        residual_norms = [norm(column) for column in eachcol(residual)]
        @test all(isfinite, residual_norms)
        @test maximum(residual_norms) <= 1e-9
        @test norm(target_X'target_X - I) <= 1e-9
        # Dense scalar eigenvalues are an independent tiny-matrix oracle only.
        expected = repeat(eigvals(H)[1:(ntarget ÷ ncomp)]; inner=ncomp)
        @test maximum(abs.(target_values - expected)) <= 1e-9
    end
end
