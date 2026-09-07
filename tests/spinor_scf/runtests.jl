# Run in a fresh Julia process. The unchanged Phase 5A entry point performs the
# frozen environment gate before loading prototype code and reruns all 544 tests.
const PHASE5B_ROOT = normpath(joinpath(@__DIR__, "..", ".."))
length(ARGS) <= 1 || error("Usage: runtests.jl [evidence_directory]")
isempty(ARGS) && push!(ARGS, joinpath(PHASE5B_ROOT, ".work", "phase5b-preflight"))
include(joinpath(@__DIR__, "..", "spinor", "runtests.jl"))

include(joinpath(PHASE5B_ROOT, "prototypes", "spinor", "SpinorSCFPrototype.jl"))
using .SpinorSCFPrototype
include("test_energy.jl")
include("test_scf.jl")

DFTK.disable_threading()
settings = TOML.parsefile(joinpath(PHASE5B_ROOT, "prototypes", "spinor", "phase5b.toml"))
context = build_b0(PHASE5B_ROOT)
println("Phase 5B new tests: synthetic orbitals on verified B0 and synthetic density maps; no SCF")
@testset "Phase 5B energy and density-feedback regressions" begin
    energy_fixture = run_energy_tests(context.basis, settings)
    controller_evidence = run_scf_tests(context.basis, settings, energy_fixture,
                                      PHASE5B_ROOT, evidence_directory)
    open(joinpath(evidence_directory, "new-test-evidence.json"), "w") do io
        JSON3.write(io, (; scope="Synthetic orbital/energy snapshots and injected density maps; no real SCF",
                         energy=energy_fixture.summary, controller=controller_evidence))
        println(io)
    end
end
