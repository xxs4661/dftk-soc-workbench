using Test
include("../../scripts/run_soc_scf.jl")
include("test_interfaces.jl")
length(ARGS)==1 || error("Usage: runtests_interfaces.jl NEW_IGNORED_OUTPUT_DIRECTORY")
outdir=abspath(only(ARGS))
startswith(outdir,joinpath(PHASE6C_ROOT,".work")*"/") || error("Use an ignored output directory")
ispath(outdir) && error("Refusing to reuse interface-test results")
mkpath(outdir)
result=Dict{String,Any}("schema_version"=>1,"phase"=>"8A","run_id"=>basename(outdir),
    "execution_status"=>"RUNNING","started_utc"=>string(now(UTC)),
    "scope"=>"Source/grid constructors, synthetic band-budget solver hooks, and static Mg streaming-energy regression; no physical eigensolve or SCF",
    "executed_source_sha256"=>phase6c_sources(),
    "test_source_sha256"=>Dict(f=>filehash(joinpath(@__DIR__,f)) for f in ("test_interfaces.jl","runtests_interfaces.jl")))
phase6b_write(joinpath(outdir,"test-result.json"),result)
try
    identity=environment_identity(PHASE6C_ROOT,(DFTK,PseudoPotentialIO))
    result["environment"]=identity
    phase6b_write(joinpath(outdir,"identity.raw.json"),identity;redact=false)
    identity.status=="PASS" || error("Frozen environment mismatch")
    DFTK.disable_threading()
    settings=TOML.parsefile(PHASE6C_CONFIG)
    suite=@testset "Phase 8A shared interface regression" begin
        result["interfaces"]=run_si_interface_tests(PHASE6C_ROOT,settings)
    end
    counts=Test.get_test_counts(suite)
    result["test_counts"]=(;passes=counts.passes+counts.cumulative_passes,fails=counts.fails+counts.cumulative_fails,
        errors=counts.errors+counts.cumulative_errors,broken=counts.broken+counts.cumulative_broken)
    result["execution_status"]="PASS";result["exit_code"]=0
catch err
    result["execution_status"]="FAIL";result["exit_code"]=1;result["failure_reason"]=sprint(showerror,err)
    phase6b_write(joinpath(outdir,"test-result.json"),result)
    rethrow()
end
result["finished_utc"]=string(now(UTC))
phase6b_write(joinpath(outdir,"test-result.json"),result)
