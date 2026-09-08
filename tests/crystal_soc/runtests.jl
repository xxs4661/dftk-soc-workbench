#!/usr/bin/env julia
# This entry runs synthetic spin-trace tests only. Actual Si action checks belong
# to the case's authorized static/final-density task, never an extra SCF/solve.
using Test
include("../../scripts/run_soc_scf.jl")
include("../../prototypes/crystal_soc/SpinTrace.jl")
include("test_spin_trace.jl")

length(ARGS) == 1 || error("Usage: runtests.jl NEW_IGNORED_EVIDENCE_DIRECTORY")
outdir = abspath(only(ARGS))
startswith(outdir, joinpath(PHASE6B_ROOT, ".work")*"/") || error("Evidence must be ignored under .work")
ispath(outdir) && error("Refusing existing test evidence directory")
mkpath(outdir)
result = Dict{String,Any}("schema_version"=>1, "run_id"=>basename(outdir),
    "execution_status"=>"RUNNING", "scope"=>"Synthetic spin-trace tests; no real source, SCF or eigensolve",
    "started_utc"=>string(now(UTC)),
    "source_sha256"=>Dict(f=>filehash(joinpath(PHASE6B_ROOT, f)) for f in
        ("prototypes/crystal_soc/SpinTrace.jl", "tests/crystal_soc/test_spin_trace.jl", "tests/crystal_soc/runtests.jl")))
phase6b_write(joinpath(outdir, "test-result.json"), result)
try
    identity = environment_identity(PHASE6B_ROOT, (DFTK, PseudoPotentialIO))
    result["environment"] = identity
    identity.status == "PASS" || error("Frozen environment identity mismatch")
    DFTK.disable_threading()
    suite = @testset "Phase 8A spin-trace diagnostic" begin
        result["synthetic"] = run_spin_trace_tests()
    end
    counts = Test.get_test_counts(suite)
    result["test_counts"] = (; passes=counts.passes+counts.cumulative_passes,
        fails=counts.fails+counts.cumulative_fails, errors=counts.errors+counts.cumulative_errors,
        broken=counts.broken+counts.cumulative_broken)
    result["execution_status"] = "PASS"; result["exit_code"] = 0
catch err
    result["execution_status"] = "FAIL"; result["exit_code"] = 1
    result["failure_reason"] = sprint(showerror, err)
    result["finished_utc"] = string(now(UTC))
    phase6b_write(joinpath(outdir, "test-result.json"), result)
    rethrow()
end
result["finished_utc"] = string(now(UTC))
phase6b_write(joinpath(outdir, "test-result.json"), result)
