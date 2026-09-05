using Test, Random, LinearAlgebra, TOML, JSON3
import DFTK, PseudoPotentialIO

const WORKBENCH_ROOT = normpath(joinpath(@__DIR__, "..", ".."))
length(ARGS) <= 1 || error("Usage: runtests.jl [evidence_directory]")
evidence_directory = isempty(ARGS) ? joinpath(WORKBENCH_ROOT, ".work", "phase5a-preflight") :
                                   abspath(only(ARGS))
mkpath(evidence_directory)

# Run this script in a fresh Julia process with the saved workbench project.
# Identity is checked before prototype code or any test fixture is loaded.
include(joinpath(WORKBENCH_ROOT, "scripts", "workbench_environment.jl"))
identity = WorkbenchEnvironment.environment_identity(WORKBENCH_ROOT, (DFTK, PseudoPotentialIO))
open(joinpath(evidence_directory, "unit-test-identity.json"), "w") do io
    JSON3.write(io, WorkbenchEnvironment.public_data(identity, WORKBENCH_ROOT))
    println(io)
end
identity.status == "PASS" || error("Frozen workbench identity check failed: " * join(identity.reasons, "; "))
println("Frozen workbench identity: ", identity.status)
println("Manifest SHA256: ", identity.manifest_sha256)

tolerances = TOML.parsefile(joinpath(WORKBENCH_ROOT, "prototypes", "spinor", "tolerances.toml"))
tolerances["acceptance"]["algebra_normalized"] == 1e-11 ||
    error("Synthetic test thresholds require the declared 1e-11 algebra acceptance gate")
println("Synthetic algebra threshold: 1e-11 (norm and near-zero definitions in each test)")
println("Scope: synthetic matrices/coefficients and a small kinetic-only DFTK basis; no SCF")

include(joinpath(WORKBENCH_ROOT, "prototypes", "spinor", "SpinorPrototype.jl"))
using .SpinorPrototype
include("test_operators.jl")
include("test_fft.jl")
include("test_density.jl")

@testset "Phase 5A independent spinor prototype unit tests" begin
    @testset "Single component-interleaved layout and complex orthogonality" begin
        rng = MersenneTwister(50311)
        for ncomp in (1, 2, 3)
            ng, nstates = 5, 3
            Psi = randn(rng, ComplexF64, ncomp, ng, nstates)
            Phi = randn(rng, ComplexF64, size(Psi))
            X = flatten_components(Psi)
            @test size(X) == (ncomp * ng, nstates)
            @test Base.mightalias(Psi, X)
            for state in 1:nstates, g in 1:ng, component in 1:ncomp
                @test X[component + ncomp * (g - 1), state] == Psi[component, g, state]
            end
            restored = unflatten_components(X, ncomp)
            @test size(restored) == size(Psi)
            @test restored == Psi
            @test Base.mightalias(restored, X)
            independent_inner = sum(conj(Psi[c, g, s]) * Phi[c, g, s]
                                    for s in 1:nstates, g in 1:ng, c in 1:ncomp)
            @test abs(dot(X, flatten_components(Phi)) - independent_inner) /
                  max(abs(independent_inner), 1) <= 1e-11

            # QR orthogonalizes columns in the full component+G inner product.
            Q = Matrix(qr(copy(X)).Q)[:, 1:nstates]
            orthogonal = unflatten_components(Q, ncomp)
            @test norm(Q'Q - I) <= 1e-11
            @test flatten_components(orthogonal) == Q
            @test all(abs(sum(abs2, orthogonal[:, :, s]) - 1) <= 1e-11 for s in 1:nstates)
        end
        @test_throws DimensionMismatch flatten_components(zeros(ComplexF64, 0, 5, 3))
        @test_throws DimensionMismatch flatten_components(zeros(ComplexF64, 2, 5, 0))
        @test_throws DimensionMismatch unflatten_components(zeros(ComplexF64, 5, 3), 2)
        @test_throws DimensionMismatch unflatten_components(zeros(ComplexF64, 6, 3), 0)
        @test_throws DimensionMismatch unflatten_components(zeros(ComplexF64, 0, 3), 2)
    end

    run_operator_tests()

    # This small no-pseudopotential basis has unequal NG at Gamma/nonzero k.
    model = DFTK.Model(Matrix(Diagonal([6.0, 7.0, 8.0]));
                       n_electrons=2, terms=[DFTK.Kinetic()], symmetries=false)
    basis = DFTK.PlaneWaveBasis(model; Ecut=3.0,
        kgrid=DFTK.ExplicitKpoints([[0.0, 0.0, 0.0], [0.19, 0.07, -0.13]]))
    println("Synthetic FFT basis: NG=", [length(DFTK.G_vectors(basis, k)) for k in basis.kpoints],
            ", fft_size=", basis.fft_size)
    run_fft_tests(basis)
    run_density_tests()
end
