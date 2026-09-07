using Test, Random, LinearAlgebra
import DFTK

# Synthetic coefficients on a real DFTK plane-wave basis; no pseudopotential or
# physical SCF is involved. Relative Frobenius/Euclidean errors use the reference
# norm; for reference norm < 1e-12, use absolute error. Threshold is 1e-11.
function fft_test_error(actual, expected)
    scale = norm(expected)
    norm(actual - expected) / (scale < 1e-12 ? 1.0 : scale)
end

function run_fft_tests(basis)
    @testset "Component FFT on periodic Bloch functions (synthetic coefficients)" begin
        rng = MersenneTwister(50317)
        @test length(basis.kpoints) >= 2
        @test any(kpt -> norm(kpt.coordinate) > 0, basis.kpoints)
        @test length(unique(length(DFTK.G_vectors(basis, kpt)) for kpt in basis.kpoints)) > 1
        r_vectors = vec(DFTK.r_vectors(basis))
        nr = prod(basis.fft_size)
        volume = abs(det(basis.model.lattice))
        @test isapprox(basis.dvol * nr, volume; rtol=1e-14)

        for kpt in basis.kpoints, ncomp in (1, 2, 3)
            ng = length(DFTK.G_vectors(basis, kpt))
            nstates = 3
            Psi = randn(rng, ComplexF64, ncomp, ng, nstates)
            Phi = randn(rng, ComplexF64, ncomp, ng, nstates)
            saved = copy(Psi)
            u = SpinorPrototype.component_ifft(basis, kpt, Psi)
            v = SpinorPrototype.component_ifft(basis, kpt, Phi)
            saved_u = copy(u)
            back = SpinorPrototype.component_fft(basis, kpt, u)
            @test size(u) == (ncomp, nr, nstates)
            @test size(back) == size(Psi)
            @test Psi == saved
            @test u == saved_u
            @test fft_test_error(back, Psi) <= 1e-11
            @test fft_test_error(basis.dvol * sum(abs2, u), sum(abs2, Psi)) <= 1e-11
            @test fft_test_error(basis.dvol * dot(u, v), dot(Psi, Phi)) <= 1e-11

            # Noncontiguous views must also retain their backing arrays.
            backing = randn(rng, ComplexF64, 2ncomp, ng, 2nstates)
            view_Psi = @view backing[1:2:2ncomp, :, 1:2:2nstates]
            saved_backing = copy(backing)
            view_u = SpinorPrototype.component_ifft(basis, kpt, view_Psi)
            @test fft_test_error(SpinorPrototype.component_fft(basis, kpt, view_u), view_Psi) <= 1e-11
            @test backing == saved_backing
            real_backing = zeros(ComplexF64, 2ncomp, nr, 2nstates)
            real_view = @view real_backing[1:2:2ncomp, :, 1:2:2nstates]
            real_view .= u
            saved_real_backing = copy(real_backing)
            @test fft_test_error(SpinorPrototype.component_fft(basis, kpt, real_view), Psi) <= 1e-11
            @test real_backing == saved_real_backing

            # QR acts on the total component+G norm, not one norm per component.
            Q = Matrix(qr(reshape(copy(Psi), ncomp * ng, nstates)).Q)[:, 1:nstates]
            orthogonal = reshape(Q, ncomp, ng, nstates)
            orthogonal_u = SpinorPrototype.component_ifft(basis, kpt, orthogonal)
            Qr = reshape(orthogonal_u, ncomp * nr, nstates)
            @test norm(Q'Q - I) <= 1e-11
            @test norm(basis.dvol * Qr'Qr - I) <= 1e-11
            for state in 1:nstates
                @test abs(sum(abs2, orthogonal[:, :, state]) - 1) <= 1e-11
                @test abs(basis.dvol * sum(abs2, orthogonal_u[:, :, state]) - 1) <= 1e-11
            end
        end

        # Independent Fourier-series oracle (no call to either transform):
        # distinct components/states have distinct complex amplitudes and Gs.
        # This tests the 1/sqrt(Ω) scale and phase sign separately from roundtrip.
        for kpt in basis.kpoints
            Gs = DFTK.G_vectors(basis, kpt)
            ng = length(Gs)
            nonzero = findfirst(G -> any(x -> !iszero(x), G), Gs)
            @test !isnothing(nonzero)
            chosen = [1, nonzero, ng]
            amplitudes = ComplexF64[1+2im -2+0.5im; -0.7+im 3-2im; 0.4-0.3im -im]
            Psi = zeros(ComplexF64, 3, ng, 2)
            reference = zeros(ComplexF64, 3, nr, 2)
            for state in 1:2, component in 1:3
                ig = chosen[component]
                Psi[component, ig, state] = amplitudes[component, state]
                for (ir, r) in enumerate(r_vectors)
                    reference[component, ir, state] = amplitudes[component, state] *
                        cis(2π * dot(Gs[ig], r)) / sqrt(volume)
                end
            end
            @test fft_test_error(SpinorPrototype.component_ifft(basis, kpt, Psi), reference) <= 1e-11
            @test fft_test_error(SpinorPrototype.component_fft(basis, kpt, reference), Psi) <= 1e-11
            @test fft_test_error(basis.dvol * sum(abs2, reference), sum(abs2, amplitudes)) <= 1e-11

            # G=0 must be constant even at nonzero k: these are periodic u,
            # not the full Bloch orbital exp(ik⋅r)u. Total spinor norm is one.
            zero_G = findfirst(G -> all(iszero, G), Gs)
            @test !isnothing(zero_G)
            constant = zeros(ComplexF64, 2, ng, 1)
            constant[:, zero_G, 1] = ComplexF64[1, 2im] / sqrt(5)
            constant_u = SpinorPrototype.component_ifft(basis, kpt, constant)
            @test fft_test_error(constant_u[1, :, 1], fill(1 / sqrt(5volume), nr)) <= 1e-11
            @test fft_test_error(constant_u[2, :, 1], fill(2im / sqrt(5volume), nr)) <= 1e-11
            @test abs(basis.dvol * sum(abs2, constant_u) - 1) <= 1e-11
            @test abs(basis.dvol * sum(abs2, constant_u[1, :, 1]) - 0.2) <= 1e-11
            @test abs(basis.dvol * sum(abs2, constant_u[2, :, 1]) - 0.8) <= 1e-11
        end

        kpt = first(basis.kpoints)
        ng = length(DFTK.G_vectors(basis, kpt))
        @test_throws DimensionMismatch SpinorPrototype.component_ifft(basis, kpt, zeros(ComplexF64, 2, ng + 1, 1))
        @test_throws DimensionMismatch SpinorPrototype.component_ifft(basis, kpt, zeros(ComplexF64, 2, ng))
        @test_throws DimensionMismatch SpinorPrototype.component_fft(basis, kpt, zeros(ComplexF64, 2, nr - 1, 1))
        @test_throws DimensionMismatch SpinorPrototype.component_fft(basis, kpt, zeros(ComplexF64, 2, nr))
        @test_throws ArgumentError SpinorPrototype.component_ifft(basis, kpt, zeros(ComplexF64, 0, ng, 1))
        @test_throws ArgumentError SpinorPrototype.component_fft(basis, kpt, zeros(ComplexF64, 2, nr, 0))
        @test_throws ArgumentError SpinorPrototype.component_ifft(basis, kpt, zeros(Float64, 2, ng, 1))
        @test_throws ArgumentError SpinorPrototype.component_fft(basis, kpt, zeros(Float64, 2, nr, 1))
    end
end
