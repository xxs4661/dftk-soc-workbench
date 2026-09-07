# Synthetic algebra/density fixtures only; no Si SCF or physical magnetic field.
# The root test runner supplies Test, Random, LinearAlgebra, and SpinorPrototype.
function run_density_tests()
    @testset "Explicit gapped capacities and electron counting" begin
        scalar = [-3.0, -2, -1, -0.4, 0.4, 1, 2, 3]
        spinor = vcat(repeat(scalar; inner=2), [4.0, 5, 6, 7])
        weights = [0.25, 0.75]
        so = SpinorPrototype.fixed_gapped_occupations([scalar, scalar .+ 0.1], weights;
                                                      representation=:scalar)
        sp = SpinorPrototype.fixed_gapped_occupations([spinor, spinor .+ 0.1], weights;
                                                      representation=:spinor)
        @test (so.capacity, so.n_occupied, so.n_target) == (2, 4, 8)
        @test (sp.capacity, sp.n_occupied, sp.n_target) == (1, 8, 16)
        @test so.n_electrons == sp.n_electrons == 8
        @test so.occupations[1] == [2, 2, 2, 2, 0, 0, 0, 0]
        @test sp.occupations[1] == vcat(ones(8), zeros(12))
        @test so.gap ≈ 0.7 atol=1e-14
        @test sp.gap == so.gap
        @test_throws ArgumentError SpinorPrototype.fixed_gapped_occupations(
            [scalar, scalar .+ 1], weights; representation=:scalar)
        touch = copy(scalar); touch[5] = touch[4]
        @test_throws ArgumentError SpinorPrototype.fixed_gapped_occupations([touch], [1.0]; representation=:scalar)
        @test_throws ArgumentError SpinorPrototype.fixed_gapped_occupations([scalar], [2.0]; representation=:scalar)
        @test_throws ArgumentError SpinorPrototype.fixed_gapped_occupations([scalar, scalar], [-0.1, 1.1]; representation=:scalar)
        @test_throws ArgumentError SpinorPrototype.fixed_gapped_occupations([scalar], [1.0]; representation=:spinor, n_electrons=16)
        @test_throws DimensionMismatch SpinorPrototype.fixed_gapped_occupations([scalar], [1.0]; representation=:spinor)
        @test_throws ArgumentError SpinorPrototype.fixed_gapped_occupations([reverse(scalar)], [1.0]; representation=:scalar)
        bad = copy(spinor); bad[end] = NaN
        @test_throws ArgumentError SpinorPrototype.fixed_gapped_occupations([bad], [1.0]; representation=:spinor)
        @test_throws ArgumentError SpinorPrototype.fixed_gapped_occupations([scalar], [1.0]; representation=:none)
    end

    @testset "Pauli pure states and sigma-y sign" begin
        pure_states = [ComplexF64[1, 0], ComplexF64[0, 1],
                       ComplexF64[1, 1]/sqrt(2), ComplexF64[1, im]/sqrt(2)]
        expected = [[0, 0, 1], [0, 0, -1], [1, 0, 0], [0, 1, 0]]
        for (psi, spin) in zip(pure_states, expected)
            state = reshape(psi, 2, 1, 1)
            result = SpinorPrototype.density_from_real_states([state], [1.0], [[1.0]])
            @test result.n ≈ [1] atol=1e-11 rtol=0
            @test vec(result.m) ≈ spin atol=1e-11 rtol=0
            @test result.R[:, :, 1] ≈ psi*psi' atol=1e-11 rtol=0
        end
        # Independent nonuniform-weight oracle also exercises f separately from w.
        up = reshape(ComplexF64[1, 0], 2, 1, 1)
        down = reshape(ComplexF64[0, 1], 2, 1, 1)
        weighted = SpinorPrototype.density_from_real_states([up, down], [0.25, 0.75], [[0.5], [1.0]])
        @test weighted.R[:, :, 1] == ComplexF64[0.125 0; 0 0.75]
        @test weighted.n == [0.875]
        @test vec(weighted.m) == [0, 0, -0.625]
    end

    @testset "Density Hermiticity, positivity, covariance and subspace invariance" begin
        rng = MersenneTwister(20260503)
        states = [randn(rng, ComplexF64, 2, 7, 3), randn(rng, ComplexF64, 2, 7, 3)]
        weights, occupations = [0.3, 0.7], [[1.0, 1, 0], [1.0, 1, 0]]
        saved = deepcopy(states)
        result = SpinorPrototype.density_from_real_states(states, weights, occupations)
        @test states == saved
        for r in 1:7
            local_R = result.R[:, :, r]
            @test norm(local_R-local_R') <= 1e-11
            @test minimum(eigvals(Hermitian(local_R))) >= -1e-11
            @test result.n[r] + 1e-11 >= norm(result.m[:, r])
        end
        sigma_x = ComplexF64[0 1; 1 0]
        sigma_y = ComplexF64[0 -im; im 0]
        sigma_z = ComplexF64[1 0; 0 -1]
        axis = [1.0, -2, 3]/sqrt(14)
        generator = axis[1]*sigma_x+axis[2]*sigma_y+axis[3]*sigma_z
        U = cos(0.71)*Matrix{ComplexF64}(I, 2, 2)-im*sin(0.71)*generator
        @test norm(U'U-I) <= 1e-11
        @test abs(det(U)-1) <= 1e-11
        rotated = [reshape(U*reshape(psi, 2, :), size(psi)) for psi in states]
        transformed = SpinorPrototype.density_from_real_states(rotated, weights, occupations)
        @test norm(transformed.n-result.n)/norm(result.n) <= 1e-11
        for r in 1:7
            @test norm(transformed.R[:, :, r]-U*result.R[:, :, r]*U') <= 1e-11
        end
        orbital_U = Matrix(qr(randn(rng, ComplexF64, 2, 2)).Q)
        mixed = deepcopy(states)
        for psi in mixed
            psi[:, :, 1:2] .= reshape(reshape(psi[:, :, 1:2], 14, 2)*orbital_U, 2, 7, 2)
            psi[:, :, 3] .*= 1000  # An unoccupied auxiliary orbital contributes nothing.
        end
        invariant = SpinorPrototype.density_from_real_states(mixed, weights, occupations)
        @test norm(invariant.R-result.R)/norm(result.R) <= 1e-11
        @test norm(invariant.n-result.n)/norm(result.n) <= 1e-11
        @test norm(invariant.m-result.m)/norm(result.m) <= 1e-11
        scalar = reshape(ComplexF64[1, im], 1, 2, 1)
        sd = SpinorPrototype.density_from_real_states([scalar], [1.0], [[2.0]])
        @test sd.n == [2, 2]
        @test sd.m === nothing
        @test_throws ArgumentError SpinorPrototype.density_from_real_states(states, weights, [[2.0, 0, 0], [1.0, 1, 0]])
        @test_throws ArgumentError SpinorPrototype.density_from_real_states(states, weights, [[-1.0, 0, 0], [1.0, 1, 0]])
        @test_throws DimensionMismatch SpinorPrototype.density_from_real_states(states, weights, [[1.0], [1.0]])
        bad_states = deepcopy(states); bad_states[2] = zeros(ComplexF64, 2, 8, 3)
        @test_throws DimensionMismatch SpinorPrototype.density_from_real_states(bad_states, weights, occupations)
        nonfinite = deepcopy(states); nonfinite[1][1, 1, 1] = NaN
        @test_throws ArgumentError SpinorPrototype.density_from_real_states(nonfinite, weights, occupations)
        @test_throws ArgumentError SpinorPrototype.density_from_real_states(states, [0.3, 0.8], occupations)
    end

    @testset "Synthetic local Pauli matrix action" begin
        rng = MersenneTwister(20260504)
        psi = randn(rng, ComplexF64, 2, 5, 3)
        saved = copy(psi)
        scalar = randn(rng, 5)
        field = randn(rng, 3, 5)
        sigma = [ComplexF64[0 1; 1 0], ComplexF64[0 -im; im 0], ComplexF64[1 0; 0 -1]]
        actual = SpinorPrototype.apply_local_pauli(psi, scalar, field)
        @test psi == saved
        oracle = similar(actual)
        for r in 1:5
            local_V = scalar[r]*Matrix{ComplexF64}(I, 2, 2) + sum(field[a, r]*sigma[a] for a in 1:3)
            oracle[:, r, :] = local_V*psi[:, r, :]
        end
        @test norm(actual-oracle)/norm(oracle) <= 1e-11
        @test SpinorPrototype.apply_local_pauli(reshape(ComplexF64[1, im], 2, 1, 1),
                                               0.0, [0.0, 1, 0]) ≈ reshape(ComplexF64[1, im], 2, 1, 1) atol=1e-11
        constant_v, constant_B = 0.37, [0.2, -0.9, 0.4]
        identity_columns = reshape(Matrix{ComplexF64}(I, 2, 2), 2, 1, 2)
        local_matrix = reshape(SpinorPrototype.apply_local_pauli(identity_columns, constant_v, constant_B), 2, 2)
        @test norm(local_matrix-local_matrix') <= 1e-11
        @test eigvals(Hermitian(local_matrix)) ≈ [constant_v-norm(constant_B), constant_v+norm(constant_B)] atol=1e-11
        other = randn(rng, ComplexF64, size(psi))
        Hother = SpinorPrototype.apply_local_pauli(other, scalar, field)
        @test abs(dot(psi, Hother)-dot(actual, other)) <= 1e-11
        @test_throws DimensionMismatch SpinorPrototype.apply_local_pauli(zeros(ComplexF64, 3, 5, 2), scalar, field)
        @test_throws ArgumentError SpinorPrototype.apply_local_pauli(psi, scalar, complex.(field, 0.1))
        @test_throws DimensionMismatch SpinorPrototype.apply_local_pauli(psi, scalar, zeros(2, 5))
    end
end
