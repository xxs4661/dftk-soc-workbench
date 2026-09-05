# Fresh process, frozen identity gate, new independent prototype tests only.
using Test
include(joinpath(@__DIR__,"..","..","scripts","run_relativistic_projectors.jl"))
include("test_channels_radial.jl")
include("test_angular.jl")
include("test_operator.jl")
include("test_recording.jl")

length(ARGS)==1 || error("Usage: runtests.jl NEW_IGNORED_EVIDENCE_DIRECTORY")
evidence_directory=abspath(only(ARGS))
startswith(evidence_directory,joinpath(PHASE6A_ROOT,".work")*"/") || error("Evidence belongs under ignored .work")
ispath(evidence_directory) && error("Refusing existing evidence directory")
mkpath(evidence_directory)
identity=environment_identity(PHASE6A_ROOT,(DFTK,PseudoPotentialIO))
phase6a_write(joinpath(evidence_directory,"identity.json"),identity)
identity.status=="PASS" || error("Frozen environment identity mismatch")
DFTK.disable_threading()
settings=TOML.parsefile(joinpath(PHASE6A_ROOT,"prototypes/relativistic/phase6a.toml"))
lock=TOML.parsefile(joinpath(PHASE6A_ROOT,"config/sources.lock"))
case=JSON3.read(read(joinpath(PHASE6A_ROOT,"benchmarks/si-sr-lda/case.json"),String),Dict{String,Any})
mgpath=joinpath(PHASE6A_ROOT,lock["pseudopotentials"]["local_path"])
sipath=joinpath(PHASE6A_ROOT,case["pseudo"]["local_path"])
filehash(mgpath)==lock["pseudopotentials"]["file_sha256"] || error("Mg checksum mismatch")
filehash(sipath)==case["pseudo"]["sha256"] || error("Si checksum mismatch")
mg=PseudoPotentialIO.load_psp_file(mgpath); si=PseudoPotentialIO.load_psp_file(sipath)
summary=Dict{String,Any}("schema_version"=>1,"scope"=>"Phase6A mathematical/metadata/operator regressions, explicitly synthetic fixtures; no SCF",
    "execution_status"=>"RUNNING","settings_sha256"=>filehash(joinpath(PHASE6A_ROOT,"prototypes/relativistic/phase6a.toml")))
sources=vcat(["scripts/run_relativistic_projectors.jl","scripts/workbench_environment.jl",
    "scripts/upf_validation.jl","scripts/upf_runtime.jl"],
    [joinpath(directory,f) for directory in ("prototypes/relativistic","tests/relativistic")
     for f in readdir(joinpath(PHASE6A_ROOT,directory)) if endswith(f,".jl") || endswith(f,".toml")])
summary["executed_source_sha256"]=Dict(f=>filehash(joinpath(PHASE6A_ROOT,f)) for f in sources)
summary["started_utc"]=string(now(UTC))
phase6a_write(joinpath(evidence_directory,"test-result.json"),summary)
try
    @testset "Phase 6A independent relativistic projector regressions" begin
        summary["channels_radial"]=run_channels_radial_tests(mg,si,settings)
        summary["angular"]=run_angular_tests(settings)
        summary["operator"]=run_operator_tests(settings)
        summary["recording"]=run_recording_tests(PHASE6A_ROOT,evidence_directory)
    end
    summary["execution_status"]="PASS"
    summary["exit_code"]=0
catch err
    summary["execution_status"]="FAIL"
    summary["exit_code"]=1
    summary["failure_reason"]=sprint(showerror,err)
    phase6a_write(joinpath(evidence_directory,"test-result.json"),summary)
    rethrow()
end
summary["finished_utc"]=string(now(UTC))
phase6a_write(joinpath(evidence_directory,"test-result.json"),summary)
