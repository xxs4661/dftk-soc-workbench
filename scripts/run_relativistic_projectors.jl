#!/usr/bin/env julia
# Restricted Phase 6A probe. Does not load a SCF driver or change DFTK methods.
using DFTK, PseudoPotentialIO, LinearAlgebra, Random, SHA, TOML, JSON3, Dates, Serialization
include(joinpath(@__DIR__, "workbench_environment.jl"))
include(joinpath(@__DIR__, "upf_validation.jl"))
include(joinpath(@__DIR__, "upf_runtime.jl"))
using .WorkbenchEnvironment, .UpfValidation, .UpfRuntime
include(joinpath(@__DIR__, "..", "prototypes", "relativistic", "RelativisticProjectors.jl"))
using .RelativisticProjectors
include(joinpath(@__DIR__, "..", "tests", "relativistic", "angular_reference.jl"))
include(joinpath(@__DIR__, "..", "prototypes", "relativistic", "probe_checks.jl"))

const PHASE6A_ROOT = realpath(joinpath(@__DIR__, ".."))
const PHASE6A_BASE = "c235481e0a3eb149759d12293cbf005916ab09fb"
const PHASE6A_STAGES = ("metadata_status", "angular_validation_status", "radial_validation_status",
    "independent_operator_validation_status", "scalar_limit_validation_status", "real_fr_runtime_status")

function phase6a_finite(x)
    if x isa Number
        x isa Real && isfinite(x) || error("Public evidence must contain finite real numbers")
    elseif x isa AbstractDict || x isa NamedTuple
        foreach(phase6a_finite, values(x))
    elseif x isa AbstractArray || x isa Tuple
        foreach(phase6a_finite, x)
    end
end

function phase6a_write(path, result)
    phase6a_finite(result)
    bytes = JSON3.write(public_data(result, PHASE6A_ROOT))*"\n"
    JSON3.read(bytes)  # Complete encoding/validation before publication.
    write(path*".tmp", bytes)
    mv(path*".tmp", path; force=true)
end

# Driver-local boundary only; no general recorder or prior result is consulted.
function with_phase6a_record(work, outdir)
    outdir = abspath(outdir)
    startswith(outdir, joinpath(PHASE6A_ROOT, ".work")*"/") ||
        (println(stderr,"Raw run must be under ignored .work"); return 2)
    ispath(outdir) && (println(stderr,"Refusing existing run directory"); return 2)
    result = Dict{String,Any}("schema_version"=>1, "phase"=>"6A", "run_id"=>basename(outdir),
        "base_commit"=>PHASE6A_BASE, "started_utc"=>string(now(UTC)), "execution_status"=>"RUNNING",
        "numerical_review_status"=>"REVIEW_REQUIRED", "soc_scf_status"=>"NOT_IMPLEMENTED",
        "qe_soc_benchmark_status"=>"NOT_RUN", "upstream_native_support"=>"NOT_IMPLEMENTED_BY_THIS_PHASE")
    foreach(stage -> result[stage]="NOT_RUN", PHASE6A_STAGES)
    code = 0
    try
        mkpath(outdir)
        phase6a_write(joinpath(outdir,"result.json"), result)
        work(result, outdir)
        all(result[stage]=="PASS" for stage in PHASE6A_STAGES) || error("Required Phase 6A stage did not pass")
        result["execution_status"]="PASS"
    catch err
        code=1
        result["execution_status"]="FAIL"
        foreach(stage -> result[stage]=="RUNNING" && (result[stage]="FAIL"), PHASE6A_STAGES)
        result["failure_reason"]=sprint(showerror,err)
        showerror(stderr,err,catch_backtrace()); println(stderr)
    end
    result["exit_code"]=code
    result["finished_utc"]=string(now(UTC))
    try
        phase6a_write(joinpath(outdir,"result.json"),result)
    catch err
        println(stderr,"Persistence failure: ",sprint(showerror,err))
        try
            phase6a_write(joinpath(outdir,"result.json"),Dict("schema_version"=>1,
                "run_id"=>basename(outdir),"execution_status"=>"FAIL","exit_code"=>1,
                "failure_reason"=>"Could not persist full result; see stderr"))
        catch
            println(stderr,"Unable to persist safe failure record")
        end
        return 1
    end
    println(stderr,"Phase 6A $(basename(outdir)): $(result["execution_status"]), exit_code=$code")
    code
end

function run_phase6a!(result,outdir)
    settingsfile=joinpath(PHASE6A_ROOT,"prototypes/relativistic/phase6a.toml")
    settings=TOML.parsefile(settingsfile)
    result["settings"]=settings
    files=vcat(["scripts/run_relativistic_projectors.jl", "scripts/workbench_environment.jl",
        "scripts/upf_validation.jl", "scripts/upf_runtime.jl", "tests/relativistic/angular_reference.jl"],
        ["prototypes/relativistic/"*f for f in readdir(joinpath(PHASE6A_ROOT,"prototypes/relativistic"))
         if endswith(f,".jl") || endswith(f,".toml")])
    result["executed_source_sha256"]=Dict(f=>filehash(joinpath(PHASE6A_ROOT,f)) for f in files)
    result["workbench_head_at_execution"]=strip(read(`git -C $PHASE6A_ROOT rev-parse HEAD`,String))
    identity=environment_identity(PHASE6A_ROOT,(DFTK,PseudoPotentialIO))
    result["environment"]=identity
    identity.status=="PASS" || error("Frozen environment identity mismatch")
    DFTK.disable_threading()
    Threads.nthreads()==1 && BLAS.get_num_threads()==1 && DFTK.mpi_nprocs(DFTK.MPI.COMM_WORLD)==1 ||
        error("Phase 6A probe requires serial CPU execution")
    phase6a_write(joinpath(outdir,"result.json"),result)
    run_probe_checks!(result,outdir,settings,PHASE6A_ROOT)
end

function phase6a_main(args)
    args in (["--help"],["-h"]) &&
        (println("Usage: run_relativistic_projectors.jl NEW_IGNORED_RUN_DIRECTORY (no SCF)");return 0)
    length(args)==1 || (println(stderr,"Expected a new ignored run directory");return 2)
    with_phase6a_record(run_phase6a!,only(args))
end

if abspath(PROGRAM_FILE)==abspath(@__FILE__)
    exit(phase6a_main(ARGS))
end
