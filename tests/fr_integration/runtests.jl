using Test
include("../../scripts/run_fr_integration.jl")
using .FRIntegration
include("test_common_data.jl")
include("test_hamiltonian.jl")
include("test_energy.jl")
include("test_runtime.jl")
length(ARGS)==1 || error("Usage: runtests.jl NEW_IGNORED_EVIDENCE_DIRECTORY")
outdir=abspath(only(ARGS))
startswith(outdir,joinpath(PHASE6B_ROOT,".work")*"/") || error("Evidence must be under ignored .work")
ispath(outdir) && error("Refusing existing test evidence directory")
mkpath(outdir)
identity=environment_identity(PHASE6B_ROOT,(DFTK,PseudoPotentialIO))
phase6b_write(joinpath(outdir,"identity.json"),identity)
identity.status=="PASS" || error("Frozen environment mismatch")
DFTK.disable_threading()
settings=TOML.parsefile(joinpath(PHASE6B_ROOT,"prototypes/fr_integration/phase6b.toml"))
result=Dict{String,Any}("schema_version"=>1,"run_id"=>basename(outdir),"execution_status"=>"RUNNING",
    "scope"=>"Workbench Phase 6B tests; synthetic faults/operator fixtures on actual Mg/Si; no SCF/eigensolve",
    "started_utc"=>string(now(UTC)),"settings_sha256"=>filehash(joinpath(PHASE6B_ROOT,"prototypes/fr_integration/phase6b.toml")),
    "executed_source_sha256"=>phase6b_source_hashes(;tests=true))
phase6b_write(joinpath(outdir,"test-result.json"),result)
try
    suite=@testset "Phase 6B Hamiltonian and energy integration" begin
        result["common"]=run_common_data_tests(PHASE6B_ROOT,settings)
        cases=FI.build_integration_cases(PHASE6B_ROOT,settings)
        result["hamiltonian"]=run_hamiltonian_tests(cases.mgctx,cases.sictx,settings)
        result["energy"]=run_energy_tests(cases.mgctx,cases.sictx,cases.native_si_basis,settings)
        result["runtime"]=run_integration_runtime_tests(cases.mgctx,settings,outdir)
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
