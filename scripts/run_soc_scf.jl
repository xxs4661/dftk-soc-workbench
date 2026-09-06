#!/usr/bin/env julia
# Phase 6C: one fresh independent SOC SCF; no QE process or historical orbitals.
include("run_fr_integration.jl")
include("../prototypes/spinor/SpinorSCFPrototype.jl")
include("../prototypes/soc_scf/SOCSCF.jl")
const SOC=SOCSCF
const PHASE6C_ROOT=PHASE6B_ROOT
const PHASE6C_CONFIG=joinpath(PHASE6C_ROOT,"prototypes/soc_scf/phase6c.toml")
const SOC_STAGES=("soc_scf_execution_status","global_occupation_status","band_completeness_diagnostic_status",
    "density_closure_status","energy_and_free_energy_status","time_reversal_status")

function phase6c_sources()
    files=collect(keys(phase6b_source_hashes()))
    append!(files,["prototypes/spinor/"*f for f in ("SpinorSCFPrototype.jl","scf.jl","energy.jl","b0_support.jl","checks.jl")])
    append!(files,["prototypes/soc_scf/"*f for f in readdir(joinpath(PHASE6C_ROOT,"prototypes/soc_scf")) if endswith(f,".jl") || endswith(f,".toml")])
    push!(files,"scripts/run_soc_scf.jl")
    Dict(f=>filehash(joinpath(PHASE6C_ROOT,f)) for f in unique(files))
end

function phase6c_record(work,label,outdir)
    label in ("A","B") || (println(stderr,"Only A and B are physical run labels");return 2)
    outdir=abspath(outdir)
    startswith(outdir,joinpath(PHASE6C_ROOT,".work")*"/") || (println(stderr,"Evidence must be under ignored .work");return 2)
    ispath(outdir) && (println(stderr,"Refusing existing run directory; no stale result is reused");return 2)
    result=Dict{String,Any}("schema_version"=>1,"phase"=>"6C","label"=>label,"run_id"=>basename(outdir),
        "base_commit"=>"9ec5ef155ad6c078ad6379a6b32f23b7f27da7eb","started_utc"=>string(now(UTC)),
        "execution_status"=>"RUNNING","numerical_review_status"=>"REVIEW_REQUIRED",
        "two_initial_states_comparison_status"=>"NOT_RUN","qe_soc_input_status"=>"BLOCKED",
        "qe_soc_benchmark_status"=>"NOT_RUN","noncollinear_xc_status"=>"NOT_IMPLEMENTED",
        "upstream_native_support"=>"NOT_IMPLEMENTED_BY_THIS_PHASE")
    foreach(k->result[k]="NOT_RUN",SOC_STAGES)
    code=0
    try
        mkpath(outdir);phase6b_write(joinpath(outdir,"result.json"),result)
        work(result,outdir)
        all(result[k]=="PASS" for k in SOC_STAGES) || error("Required SOC stage did not pass")
        result["execution_status"]="PASS"
    catch err
        code=1;result["execution_status"]="FAIL"
        foreach(k->result[k]=="RUNNING" && (result[k]="FAIL"),SOC_STAGES)
        result["failure_reason"]=sprint(showerror,err)
        showerror(stderr,err,catch_backtrace());println(stderr)
    end
    result["exit_code"]=code;result["finished_utc"]=string(now(UTC))
    try
        # Construct/validate all mandatory output before publishing final PASS.
        phase6b_finite(result)
        summary="$(result["run_id"]): $(result["execution_status"]), exit=$code\n"
        write(joinpath(outdir,"summary.txt.tmp"),summary)
        mv(joinpath(outdir,"summary.txt.tmp"),joinpath(outdir,"summary.txt");force=true)
        phase6b_write(joinpath(outdir,"result.json"),result)
    catch err
        println(stderr,"Persistence failure: ",sprint(showerror,err))
        safe=Dict("schema_version"=>1,"phase"=>"6C","label"=>label,"run_id"=>basename(outdir),
            "execution_status"=>"FAIL","exit_code"=>1,"failure_reason"=>"Persistence failed; see stderr")
        try phase6b_write(joinpath(outdir,"result.json"),safe) catch
            println(stderr,"Unable to persist even the safe failure record")
        end
        return 1
    end
    println(stderr,"Phase 6C $(basename(outdir)): $(result["execution_status"]), exit=$code")
    code
end

function phase6c_checkpoint(path,state)
    # Only arrays and plain metadata: never serialize context/H/process-local tokens.
    serialize(path*".tmp",state);mv(path*".tmp",path;force=true)
end

function run_soc!(result,outdir)
    settings=TOML.parsefile(PHASE6C_CONFIG);label=result["label"]
    result["settings"]=settings;result["config_sha256"]=filehash(PHASE6C_CONFIG)
    result["executed_source_sha256"]=phase6c_sources()
    result["workbench_head_at_execution"]=strip(read(`git -C $PHASE6C_ROOT rev-parse HEAD`,String))
    identity=environment_identity(PHASE6C_ROOT,(DFTK,PseudoPotentialIO));result["environment"]=identity
    phase6b_write(joinpath(outdir,"identity.raw.json"),identity;redact=false)
    identity.status=="PASS" || error("Frozen environment identity mismatch")
    DFTK.disable_threading()
    Threads.nthreads()==1 && BLAS.get_num_threads()==1 && DFTK.mpi_nprocs(DFTK.MPI.COMM_WORLD)==1 || error("Serial CPU required")
    result["parallelism"]=(;julia=Threads.nthreads(),blas=BLAS.get_num_threads(),fft=DFTK.FFTW.get_num_threads(),mpi=1)
    case=SOC.build_soc_context(PHASE6C_ROOT,settings);ctx=case.ctx
    result["input"]=FI.common_data_summary(case.bundle);result["basis"]=FI.basis_summary(ctx)
    result["temperature_ha"]=ctx.basis.model.temperature;result["smearing"]="FermiDirac"
    initial=SOC.soc_initial_density(ctx,label,settings);result["initial"]=initial.report
    phase6c_checkpoint(joinpath(outdir,"initial.bin"),(;n=initial.n,report=initial.report))
    foreach(k->result[k]="RUNNING",SOC_STAGES)
    phase6b_write(joinpath(outdir,"result.json"),result)
    append_record=function(path,record)
        phase6b_finite(record)
        open(path,"a") do io;write(io,JSON3.write(record)*"\n");flush(io);end
    end
    progress=function(event)
        if hasproperty(event,:event) && event.event=="map_input_checkpoint"
            phase6c_checkpoint(joinpath(outdir,"current-map-input.bin"),event)
        elseif hasproperty(event,:event) && event.event=="failed_target_solve"
            phase6c_checkpoint(joinpath(outdir,"failed-k$(event.k_index).bin"),event.state)
            append_record(joinpath(outdir,"solver-events.jsonl"),(;event=event.event,map_index=event.map_index,
                k_index=event.k_index,converged=event.converged,iterations=event.iterations))
        elseif hasproperty(event,:event) && event.event=="target_solve"
            r=event.record
            phase6c_checkpoint(joinpath(outdir,"latest-k$(r.k_index).bin"),event.state)
            append_record(joinpath(outdir,"solver-events.jsonl"),(;event="target_solve",record=r))
        else
            append_record(joinpath(outdir,"solver-events.jsonl"),event)
        end
    end
    checkpoint=function(record,raw)
        append_record(joinpath(outdir,"maps.jsonl"),record)
        result["completed_maps"]=record["map_index"];result["latest_map"]=record
        if !isnothing(raw)
            FI.validate_context(ctx);FI.assert_bound_sources(case.bundle)
            nnext=!haskey(record,"next_density_source") ? nothing : record["next_density_source"]=="linear_mixing" ?
                (1-settings["scf"]["alpha"]).*raw.n_in.+settings["scf"]["alpha"].*raw.n_out : copy(raw.n_out)
            state=(;X=raw.X,all_X=raw.all_X,f=raw.f,eigenvalues=raw.eigenvalues,n_in=raw.n_in,n_out=raw.n_out,
                n_next=nnext,R=raw.density.R,m=raw.density.m,record,
                config_sha256=result["config_sha256"],source_sha256=result["executed_source_sha256"])
            phase6c_checkpoint(joinpath(outdir,"latest.bin"),state)
            if record["map_index"]==1 || get(record,"density_candidate",false) || record["map_role"]=="closure" || record["status"]=="FAIL"
                phase6c_checkpoint(joinpath(outdir,"map-$(lpad(record["map_index"],3,'0')).bin"),state)
            end
            println(stderr,"$label map=$(record["map_index"]) $(record["map_role"]) $(record["status"]) residual=$(get(record,"unmixed_residual_l2",nothing)) E=$(raw.thermal.internal_energy_ha) F=$(raw.thermal.free_energy_ha)")
        end
        phase6b_write(joinpath(outdir,"result.json"),result)
    end
    solved=SOC.soc_scf(ctx,initial.n,settings;seed=settings["seeds"][label],callback=checkpoint,progress)
    raw=solved.raw
    result["final"]=(;target_states=length(raw.f[1]),map_count=solved.map_count,
        n_in_sha256=FI.integration_density_hash(raw.n_in),n_out_sha256=FI.integration_density_hash(raw.n_out),
        eigenvalues_ha=raw.eigenvalues,occupations=raw.f,mu_ha=raw.ensemble.mu,
        diagnostics=raw.diag,unmixed_residual_l2=last(solved.history)["unmixed_residual_l2"])
    phase6c_checkpoint(joinpath(outdir,"final.bin"),(;X=raw.X,f=raw.f,eigenvalues=raw.eigenvalues,
        n_in=raw.n_in,n_out=raw.n_out,R=raw.density.R,m=raw.density.m,final=result["final"]))
    for k in SOC_STAGES[1:5];result[k]="PASS";end
    result["time_reversal"]=SOC.endpoint_time_reversal(ctx,raw,settings)
    result["time_reversal_status"]=result["time_reversal"].status
    result["time_reversal_status"]=="PASS" || error("Endpoint time-reversal/spectrum/occupation check failed")
    final_identity=environment_identity(PHASE6C_ROOT,(DFTK,PseudoPotentialIO))
    final_identity.status=="PASS" || error("Frozen identity changed during run")
    FI.validate_context(ctx);FI.assert_bound_sources(case.bundle)
    phase6c_sources()==result["executed_source_sha256"] || error("Executed source changed during physical run")
    filehash(PHASE6C_CONFIG)==result["config_sha256"] || error("Settings changed during physical run")
    result["final_environment"]=final_identity
    result["checkpoint_sha256"]=filehash(joinpath(outdir,"final.bin"))
end

function phase6c_main(args)
    args==["--help"] && (println("Usage: run_soc_scf.jl A|B NEW_IGNORED_RUN_DIRECTORY");return 0)
    length(args)==2 || (println(stderr,"Usage: run_soc_scf.jl A|B NEW_IGNORED_RUN_DIRECTORY");return 2)
    phase6c_record(run_soc!,args[1],args[2])
end
abspath(PROGRAM_FILE)==(@__FILE__) && exit(phase6c_main(ARGS))
