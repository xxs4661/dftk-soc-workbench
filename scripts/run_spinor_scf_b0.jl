#!/usr/bin/env julia
# Phase 5B orchestration only. SCF/energy live in the independent prototype.
using DFTK, PseudoPotentialIO, JSON3, TOML, LinearAlgebra, Dates, Serialization
include(joinpath(@__DIR__,"workbench_environment.jl"))
using .WorkbenchEnvironment
include(joinpath(@__DIR__,"..","prototypes","spinor","SpinorPrototype.jl"))
using .SpinorPrototype
include(joinpath(@__DIR__,"..","prototypes","spinor","SpinorSCFPrototype.jl"))
using .SpinorSCFPrototype

const PHASE5B_ROOT = realpath(joinpath(@__DIR__,".."))
const PHASE5B_BASE = "60140a4148a510f0b2eb36f7bf00d683f3105a9a"

function phase5b_finite(x)
    if x isa AbstractFloat
        isfinite(x) || error("Nonfinite public result")
    elseif x isa AbstractDict || x isa NamedTuple
        foreach(phase5b_finite,values(x))
    elseif x isa AbstractArray || x isa Tuple
        foreach(phase5b_finite,x)
    end
end

function phase5b_write(path,result)
    phase5b_finite(result)
    bytes=JSON3.write(public_data(result,PHASE5B_ROOT))*"\n"
    write(path*".tmp",bytes)
    mv(path*".tmp",path;force=true)
end

# A small driver-local failure boundary, also exercised by synthetic worker tests.
# It never reads an older result. Existing directories are refused, not overwritten.
function with_run_record(work,outdir)
    outdir=abspath(outdir)
    startswith(outdir,joinpath(PHASE5B_ROOT,".work")*"/") ||
        (println(stderr,"Raw runs must stay under ignored .work");return 2)
    ispath(outdir) && (println(stderr,"Refusing existing run directory");return 2)
    result=Dict{String,Any}("schema_version"=>1,"phase"=>"5B","run_id"=>basename(outdir),
        "base_commit"=>PHASE5B_BASE,"started_utc"=>string(now(UTC)),
        "execution_status"=>"RUNNING","spinor_scf_status"=>"NOT_RUN",
        "spinor_total_energy_status"=>"NOT_RUN","numerical_review_status"=>"REVIEW_REQUIRED",
        "soc_status"=>"NOT_IMPLEMENTED","noncollinear_lsda_status"=>"NOT_IMPLEMENTED",
        "upstream_native_spinor_support"=>"NOT_IMPLEMENTED_BY_THIS_PHASE")
    code=0
    try
        mkpath(outdir)
        phase5b_write(joinpath(outdir,"result.json"),result)
        work(result,outdir)
        result["execution_status"]="PASS"
    catch err
        code=1
        result["execution_status"]="FAIL"
        for stage in ("spinor_scf_status","spinor_total_energy_status")
            result[stage]=="RUNNING" && (result[stage]="FAIL")
        end
        result["failure_reason"]=sprint(showerror,err)
        showerror(stderr,err,catch_backtrace());println(stderr)
    end
    result["exit_code"]=code
    result["finished_utc"]=string(now(UTC))
    try
        phase5b_write(joinpath(outdir,"result.json"),result)
    catch err
        println(stderr,"Persistence failed: ",sprint(showerror,err))
        try
            phase5b_write(joinpath(outdir,"result.json"),Dict("schema_version"=>1,
                "run_id"=>basename(outdir),"execution_status"=>"FAIL","exit_code"=>1,
                "failure_reason"=>"Persistence failed; see stderr"))
        catch
            println(stderr,"Unable to persist a safe failure record")
        end
        return 1
    end
    println("Run $(basename(outdir)): $(result["execution_status"]), exit_code=$code")
    code
end

function run_phase5b!(result,outdir)
    settingsfile=joinpath(PHASE5B_ROOT,"prototypes/spinor/phase5b.toml")
    settings=TOML.parsefile(settingsfile)
    result["settings"]=settings
    files=vcat(["scripts/run_spinor_scf_b0.jl"],
        ["prototypes/spinor/"*n for n in readdir(joinpath(PHASE5B_ROOT,"prototypes/spinor"))
         if endswith(n,".jl") || n=="phase5b.toml"])
    result["executed_source_sha256"]=Dict(f=>filehash(joinpath(PHASE5B_ROOT,f)) for f in files)
    result["workbench_head_at_execution"]=strip(read(`git -C $PHASE5B_ROOT rev-parse HEAD`,String))
    prepared=build_b0(PHASE5B_ROOT)
    basis=prepared.basis
    result["provenance"]=prepared.provenance
    initial=initial_densities(basis,settings)
    result["initialization"]=initial.report
    serialize(joinpath(outdir,"initial-densities.bin"),(;a=initial.a,b=initial.b))
    result["run_order"]=String[]
    result["spinor_scf_status"]="RUNNING"
    result["spinor_total_energy_status"]="RUNNING"
    result["runs"]=Dict{String,Any}()
    phase5b_write(joinpath(outdir,"result.json"),result)
    function run_spinor(label,n0,seed)
        subdir=joinpath(outdir,label);mkpath(subdir)
        push!(result["run_order"],label)
        result["runs"][label]=Dict("status"=>"RUNNING","seed"=>seed,
            "initial_density_sha256"=>density_summary(n0,basis.dvol).sha256)
        phase5b_write(joinpath(outdir,"result.json"),result)
        callback=function(record,raw)
            phase5b_finite(record)
            open(joinpath(subdir,"maps.jsonl"),"a") do io
                println(io,JSON3.write(public_data(record,PHASE5B_ROOT)))
            end
            result["runs"][label]["last_map"]=record
            phase5b_write(joinpath(outdir,"result.json"),result)
            if record["status"]=="FAIL"
                println("$label map $(record["map_index"]): FAIL ",get(record,"failure_reason",""))
            else
                diag=record["diagnostics"]
                println("$label map $(record["map_index"]) $(record["map_role"]): residual=$(record["unmixed_residual_l2"]) energy=$(diag.energy_total_ha) status=$(record["status"])")
            end
            flush(stdout)
            if !isnothing(raw) && (record["map_index"]==1 || record["map_role"]=="closure" || record["status"]=="FAIL")
                serialize(joinpath(subdir,"map-$(record["map_index"])-state.bin"),
                    (;X=raw.X,f=raw.f,lambda=raw.lambda,n_in=raw.n_in,density=raw.density,
                      energy_terms=raw.energy.terms,total_energy=raw.energy.total))
            end
        end
        println("Starting $label from its independent guess and ComplexF64 seed $seed");flush(stdout)
        started=time()
        spin=spinor_scf(basis,n0,settings;seed,callback)
        result["runs"][label]=Dict("status"=>spin.status,"map_count"=>spin.map_count,
            "elapsed_seconds"=>time()-started,"seed"=>seed,"initial_density_sha256"=>density_summary(n0,basis.dvol).sha256,
            "final_map"=>last(spin.history),"total_energy_ha_cell"=>spin.energy.total,
            "energy_terms_ha_cell"=>spin.energy.terms,"energy_checks"=>spin.energy.report,
            "density"=>density_summary(spin.density.n,basis.dvol),
            "pauli_density_relative_l2"=>norm(spin.density.m)/norm(spin.density.n),
            "history_file"=>"$label/maps.jsonl")
        phase5b_write(joinpath(outdir,"result.json"),result)
        spin
    end
    a=run_spinor("A",initial.a,settings["initialization"]["seed_a"])
    b=run_spinor("B",initial.b,settings["initialization"]["seed_b"])
    result["spinor_scf_status"]="PASS"
    push!(result["run_order"],"C")
    result["runs"]["C"]=Dict("status"=>"RUNNING")
    phase5b_write(joinpath(outdir,"result.json"),result)
    println("A and B completed; starting independent native scalar reference C.");flush(stdout)
    c=scalar_reference(basis,settings)
    result["runs"]["C"]=c.report
    serialize(joinpath(outdir,"C-reference-state.bin"),c)
    comparison=compare_references(basis,a,b,c,settings)
    result["comparison"]=comparison
    println("Checking the fixed nonstationary orbital rotation and all three declared difference steps.");flush(stdout)
    fd=finite_difference_check(basis,a.X,a.f,settings)
    result["finite_difference"]=fd.report
    serialize(joinpath(outdir,"directional-center.bin"),(;X=fd.trial,f=a.f,density=fd.center_density))
    phase5b_write(joinpath(outdir,"result.json"),result)
    comparison.status=="PASS" || error("A/B/scalar comparison failed; thresholds retained")
    fd.report.status=="PASS" || error("Finite difference energy/Hamiltonian check failed; all steps retained")
    result["spinor_total_energy_status"]="PASS"
end

function phase5b_main(args)
    args in (["--help"],["-h"]) && (println("Usage: run_spinor_scf_b0.jl NEW_IGNORED_RUN_DIRECTORY");return 0)
    length(args)==1 || (println(stderr,"Expected one new ignored run directory");return 2)
    with_run_record(run_phase5b!,only(args))
end

if abspath(PROGRAM_FILE)==abspath(@__FILE__)
    exit(phase5b_main(ARGS))
end
