using Test
include("../../scripts/run_soc_scf.jl")
using .SOCSCF
include("test_ensemble.jl")
include("test_temperature.jl")
include("test_controller.jl")
include("test_integration.jl")
include("test_recording.jl")
include("test_comparison.jl")
length(ARGS)==1 || error("Usage: runtests.jl NEW_IGNORED_EVIDENCE_DIRECTORY")
outdir=abspath(only(ARGS))
startswith(outdir,joinpath(PHASE6C_ROOT,".work")*"/") || error("Use ignored evidence directory")
ispath(outdir) && error("Refusing existing test evidence directory")
mkpath(outdir)
settings=TOML.parsefile(PHASE6C_CONFIG)
result=Dict{String,Any}("schema_version"=>1,"phase"=>"6C","run_id"=>basename(outdir),
    "execution_status"=>"RUNNING","scope"=>"Synthetic spectra, maps and faults; real-Mg operator/energy fixtures, no physical eigensolve or SCF",
    "started_utc"=>string(now(UTC)),"config_sha256"=>filehash(PHASE6C_CONFIG),
    "executed_source_sha256"=>phase6c_sources(),
    "test_source_sha256"=>Dict(f=>filehash(joinpath(@__DIR__,f)) for f in readdir(@__DIR__) if endswith(f,".jl")))
try
    identity=environment_identity(PHASE6C_ROOT,(DFTK,PseudoPotentialIO));result["environment"]=identity
    phase6b_write(joinpath(outdir,"identity.raw.json"),identity;redact=false)
    identity.status=="PASS" || error("Frozen identity mismatch")
    DFTK.disable_threading()
    case=SOC.build_soc_context(PHASE6C_ROOT,settings);b=case.ctx.basis;m=settings["mg"]
    cold=FI.build_context([case.bundle],Matrix{Float64}(I,3,3)*m["cell_side_bohr"],m["positions_fractional"],m["kpoints"],m["kweights"];
        Ecut=m["ecut_ha"],xc_identifiers=Symbol.(m["xc_identifiers"]),mode=:real_fr)
    suite=@testset "Phase 6C ensemble, controller and interface tests" begin
        result["ensemble"]=run_ensemble_tests(settings)
        result["temperature"]=run_temperature_tests(cold,settings)
        result["controller"]=run_soc_controller_tests()
        result["integration"]=run_soc_integration_tests(case.ctx,settings)
        result["recording"]=run_soc_recording_tests(outdir)
        result["comparison"]=run_soc_comparison_tests()
    end
    counts=Test.get_test_counts(suite)
    result["test_counts"]=(;passes=counts.passes+counts.cumulative_passes,fails=counts.fails+counts.cumulative_fails,
        errors=counts.errors+counts.cumulative_errors,broken=counts.broken+counts.cumulative_broken)
    result["execution_status"]="PASS";result["exit_code"]=0
catch err
    result["execution_status"]="FAIL";result["exit_code"]=1;result["failure_reason"]=sprint(showerror,err)
    phase6b_write(joinpath(outdir,"test-result.json"),result);rethrow()
end
result["finished_utc"]=string(now(UTC))
phase6b_write(joinpath(outdir,"test-result.json"),result)
