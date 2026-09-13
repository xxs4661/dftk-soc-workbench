#!/usr/bin/env julia
# Three explicitly bound short diagnostics. All numerical maps are shared SOC code.
const TIMING_ADAPTER_ROOT=normpath(joinpath(@__DIR__,"../.."))
const TIMING_BOOTSTRAP_NS=time_ns()
include(joinpath(TIMING_ADAPTER_ROOT,"prototypes/diagnostics.jl"))
const TD=WorkbenchDiagnostics
include(joinpath(@__DIR__,"control.jl"))
const TC=SocTimingControl

function timing_main(args)
    isempty(args) && return 2
    check=last(args)=="--check-entry"
    a=check ? args[1:end-1] : args
    length(a)==3 || return 2
    task,outdir,routepath=a;outdir=abspath(outdir)
    task in ("T-B0-REF","T-B0-TIMED","T-K4-TIMED") || return 2
    timed=task!="T-B0-REF";runid=basename(dirname(outdir))
    control=Ref{Any}(nothing);bridge=Ref{Any}(nothing);limit_stop=Ref{Any}(nothing)
    runtime=Ref{Any}(nothing);timingio=Ref{Any}(nothing)
    result=Dict{String,Any}("schema_version"=>1,"run_id"=>runid,"worker_id"=>basename(outdir),
        "task_id"=>task,"execution_status"=>"FAIL","exit_code"=>1,"completed_maps"=>0,
        "partial_map_index"=>nothing,"current_k"=>nothing,"runtime_closed"=>false,
        "workspace_released"=>false,"last_complete_file"=>nothing,"errors"=>String[],
        "scientific_convergence_status"=>"NOT_ASSESSED","check_only"=>check,"context_constructed"=>false,
        "map_checks_passed"=>false,"runtime_dispatch_status"=>"NOT_ASSESSED",
        "runtime_state"=>"NOT_CONSTRUCTED","owned_runtime_constructed"=>false,
        "map_summaries_sha256"=>Dict{String,String}())
    function boundary(event,map_index=0,k_index=0;propagate=true)
        isnothing(control[]) && return
        map_index>result["completed_maps"] && (result["partial_map_index"]=map_index)
        k_index>0 && map_index>result["completed_maps"] && (result["current_k"]=k_index)
        try
            TC.boundary!(control[],event,map_index,k_index;propagate)
        catch err
            if task=="T-B0-REF" && err isa TD.ControlledStop && isdefined(Main,:SOC)
                sentinel=SOC.Controller.DensityMapFailure(sprint(showerror,err),Any[])
                bridge[]=(;sentinel,original=err)
                throw(sentinel)
            end
            rethrow()
        end
    end
    session=TD.Session(runid;enabled=timed,boundary_hook=(e,m,k)->boundary(e,m,k),max_rows=20000)
    result["bootstrap_before_session_seconds"]=timed ? (time_ns()-TIMING_BOOTSTRAP_NS)/1e9 : nothing
    function emit_timing()
        isnothing(timingio[]) && return
        TD.flush!(session,rows->foreach(r->println(timingio[],JSON3.write(r)),rows))
        flush(timingio[])
    end
    function record_failure(err)
        original=!isnothing(bridge[]) && err===bridge[].sentinel ? bridge[].original : err
        if original isa TD.ControlledStop && isempty(result["errors"])
            reason=original.reason
            result["execution_status"]=reason;result["stop_reason"]=reason
            result["exit_code"]=reason=="USER_CANCELLED" ? 130 : reason=="TIME_BUDGET_EXCEEDED" ? 124 : 17
        else
            push!(result["errors"],sprint(showerror,err));result["execution_status"]="FAIL";result["exit_code"]=1
        end
    end
    try
    TD.with_span(session,:worker_total) do
    local python, route
    try
        TD.with_span(session,:module_environment_load) do
            Core.eval(Main,:(using JSON3, SHA, Serialization, LinearAlgebra, Dates))
        end
        python=get(ENV,"SOC_TIMING_PYTHON","");isfile(python) || error("Explicit recorder Python required")
        route=TD.with_span(session,:route_authentication) do
            Base.invokelatest() do
                JSON3.read(read(`$python -B $(joinpath(@__DIR__,"route.py")) verify $routepath $task $outdir`,String),Dict{String,Any})
            end
        end
        for key in ("execution_commit","source_commit","case_sha256","source_sha256","adapter_sha256","route_sha256","timing_enabled")
            result[key]=route[key]
        end
        result["numerical_root"]=route["numerical_root"]
        result["adapter_root"]=route["adapter_root"]
        if !check
            !ispath(outdir) || error("Existing worker output is never overwritten")
            mkpath(outdir)
            timingio[]=open(joinpath(outdir,"timing.jsonl"),"w")
            control[]=TC.load_control(dirname(outdir);expected_run_id=runid,
                expected_execution_commit=route["execution_commit"],expected_source_commit=route["source_commit"],
                expected_task_id=task,expected_case_sha256=route["case_sha256"])
            result["control"]=TC.summary(control[])
            result["control_sha256"]=result["control"]["control_sha256"]
            boundary("module_loading_before")
        end
        TD.with_span(session,:numerical_definitions_load) do
            include(joinpath(route["numerical_root"],"scripts/run_si_soc.jl"))
        end
        check || boundary("module_loading_after")
        # Loading an independent E0/E1 module tree introduces new Julia methods.
        # Cross this one entry barrier; never change environments in a loaded session.
        Base.invokelatest() do
        case=si_json(joinpath(route["numerical_root"],route["case_path"]));settings=case["settings"]
        locations=Dict{String,Any}()
        for (name,f,relative) in (("soc_scf",SOC.soc_scf,"prototypes/soc_scf/scf.jl"),
                                  ("solve_soc_targets",SOC.solve_soc_targets,"prototypes/soc_scf/solver.jl"),
                                  ("controller",SOC.Controller.iterate_density_map,"prototypes/spinor/scf.jl"))
            paths=unique(realpath(String(Base.functionloc(m)[1])) for m in methods(f))
            paths==[realpath(joinpath(route["numerical_root"],relative))] || error("Loaded method belongs to another source tree: $name")
            locations[name]=(;relative_path=relative,source_sha256=route["source_sha256"][relative])
        end
        result["actual_method_sources"]=locations
        contract=route["profile"]=="K4" ? case : nothing
        SOC.validate_soc_settings(settings;case_contract=contract)
        result["environment"]=environment_identity(route["numerical_root"],(DFTK,PseudoPotentialIO))
        result["environment"].status=="PASS" || error("Frozen environment identity mismatch")
        DFTK.disable_threading()
        Threads.nthreads()==BLAS.get_num_threads()==DFTK.FFTW.get_num_threads()==1 || error("Serial CPU threads required")
        DFTK.mpi_nprocs(DFTK.MPI.COMM_WORLD)==1 || error("Single MPI process required")
        if check
            length(FI._FR_CONTEXT_CERTIFICATES)==length(FI._BOUND_PSP_SOURCES)==0 || error("Entry built a physical context")
            result["execution_status"]="CHECK_ONLY_PASS";result["exit_code"]=0
            result["numerical_execution_status"]="NOT_RUN";result["formal_slot_reserved"]=false
            return nothing
        end
        phase6b_write(joinpath(outdir,"result.json"),result)
        boundary("initialization_before")
        built=TD.with_span(session,:context_construction) do
            si_context(case,"scf";backend="soc-core")
        end
        result["context_constructed"]=true
        result["input"]=FI.common_data_summary(built.bundle)
        result["grid"]=si_grid(built.ctx)
        runtime[]=TD.with_span(session,:owned_runtime_construction) do
            FI.owned_runtime(built.ctx;max_rhs=30)
        end
        built=(;ctx=runtime[],bundle=built.bundle) # Same retained-context ownership as the existing driver.
        result["owned_runtime_constructed"]=true;result["runtime_state"]="OPEN"
        ctx=runtime[];b=ctx.basis;FI.runtime_boundary!(ctx,:driver_entry)
        result["parallelism"]=(;julia=Threads.nthreads(),blas=BLAS.get_num_threads(),fft=DFTK.FFTW.get_num_threads(),mpi=1)
        boundary("initialization_after")
        checkpoint=function(path,value)
            boundary("checkpoint_before",something(result["partial_map_index"],0),something(result["current_k"],0))
            TD.with_span(session,:checkpoint;map_index=something(result["partial_map_index"],0),k_index=something(result["current_k"],0)) do
                TD.with_span(session,:checkpoint_validation_before) do
                    FI.runtime_boundary!(ctx,:before_serialization)
                end
                TD.with_span(session,:checkpoint_serialization_and_file_write) do
                    phase6c_checkpoint(path,value)
                end
                result["last_complete_file"]=basename(path)
                TD.with_span(session,:checkpoint_validation_after) do
                    FI.runtime_boundary!(ctx,:after_serialization)
                end
            end
            boundary("checkpoint_after",something(result["partial_map_index"],0),something(result["current_k"],0))
        end
        n=fill(8/b.model.unit_cell_volume,prod(b.fft_size))
        checkpoint(joinpath(outdir,"initial.bin"),(;n,seed=81001))
        progress=function(event)
            m=hasproperty(event,:map_index) ? event.map_index : hasproperty(event,:record) ? event.record.map_index : 0
            k=hasproperty(event,:k_index) ? event.k_index : hasproperty(event,:record) ? event.record.k_index : 0
            boundary("progress_before",m,k)
            if event.event=="map_input_checkpoint"
                checkpoint(joinpath(outdir,"current-map-input.bin"),event)
            elseif event.event=="target_solve"
                checkpoint(joinpath(outdir,"latest-k$(event.record.k_index).bin"),event.state)
                si_append(joinpath(outdir,"solver.jsonl"),event.record)
            elseif event.event=="failed_target_solve"
                checkpoint(joinpath(outdir,"failed-solve.bin"),event)
            else
                si_append(joinpath(outdir,"events.jsonl"),event)
            end
            boundary("progress_after",m,k)
        end
        callback=function(record,raw)
            m=record["map_index"];boundary("map_callback_before",m)
            FI.runtime_boundary!(ctx,:callback_entry)
            si_append(joinpath(outdir,"maps.jsonl"),record)
            if !isnothing(raw)
                state=(;X=raw.X,all_X=raw.all_X,f=raw.f,eigenvalues=raw.eigenvalues,n_in=raw.n_in,n_out=raw.n_out,
                    diagnostics=raw.diag,mu=raw.ensemble.mu,record)
                checkpoint(joinpath(outdir,"latest.bin"),state)
                if m==1 || get(record,"density_candidate",false) || record["map_role"]=="closure" || record["status"]=="FAIL"
                    checkpoint(joinpath(outdir,"map-$(lpad(m,3,'0')).bin"),state)
                end
                result["latest_map"]=si_extra_compact_map(record)
                println(stderr,"Si diagnostic map=$m $(record["status"]) residual=$(get(record,"unmixed_residual_l2",nothing)) E=$(raw.thermal.internal_energy_ha)")
            end
            phase6b_write(joinpath(outdir,"result.json"),result)
            FI.runtime_boundary!(ctx,:callback_return)
            boundary("map_callback_complete",m)
            if !isnothing(raw) && record["status"] in ("CONTINUE","CANDIDATE","PASS")
                length(raw.eigenvalues)==length(case["kpoints"]) && all(length(e)==24 for e in raw.eigenvalues) || error("Incomplete diagnostic map")
                raw.diag.target_states==24 && raw.diag.band_completeness.status=="PASS" || error("Diagnostic physical-band check failed")
                raw.diag.max_input_h_residual_ha<=settings["thresholds"]["residual_ha"] &&
                    raw.diag.max_gram_norm<=settings["thresholds"]["gram_norm"] || error("Diagnostic solve check failed")
                abs(raw.diag.real_electron_count-8)<=settings["thresholds"]["electron_count_abs"] &&
                    abs(raw.diag.orbital_electron_count-8)<=settings["thresholds"]["electron_count_abs"] || error("Diagnostic electron count failed")
                Base.ENDIAN_BOM==0x04030201 || error("Density export requires authenticated little-endian Float64")
                density_path="map-$(lpad(m,3,'0'))-density.f64"
                write(joinpath(outdir,density_path),reinterpret(UInt8,vec(raw.n_out)))
                summary=(;map_index=m,run_id=runid,task_id=task,case_sha256=route["case_sha256"],
                    execution_commit=route["execution_commit"],source_commit=route["source_commit"],
                    internal_energy_ha=raw.thermal.internal_energy_ha,free_energy_ha=raw.thermal.free_energy_ha,
                    unmixed_residual_l2=record["unmixed_residual_l2"],eigenvalues_ha=raw.eigenvalues,occupations=raw.f,
                    kpoints=[collect(k.coordinate) for k in b.kpoints],n_out_sha256=FI.integration_density_hash(raw.n_out),n_out_norm=norm(raw.n_out),
                    density_file=density_path,density_file_sha256=filehash(joinpath(outdir,density_path)),density_encoding="little-endian Float64",
                    density_count=length(raw.n_out),diagnostics=si_extra_compact_map(record)["diagnostics"],
                    band_completeness_status=raw.diag.band_completeness.status,energy_checks=raw.diag.energy_checks)
                summary_name="map-$(lpad(m,3,'0'))-summary.json"
                phase6b_write(joinpath(outdir,summary_name),summary)
                result["map_summaries_sha256"][summary_name]=filehash(joinpath(outdir,summary_name))
                result["completed_maps"]=m;result["partial_map_index"]=nothing;result["current_k"]=nothing
                result["map_checks_passed"]=m==2
                result["last_complete_file"]="map-$(lpad(m,3,'0'))-summary.json"
                TD.with_span(session,:timing_batch_output;map_index=m) do
                    emit_timing()
                end
            end
            if m==2 && result["completed_maps"]==2
                sentinel=timed ? TD.ControlledStop("DIAGNOSTIC_MAP_LIMIT";boundary="map_callback_complete",map_index=2) :
                    SOC.Controller.DensityMapFailure("DIAGNOSTIC_MAP_LIMIT",Any[])
                limit_stop[]=sentinel;throw(sentinel)
            end
        end
        solve_hook=function(H,initial,prec,ik,map_index)
            boundary("k_solve_before",map_index,ik)
            value=TD.with_span(session,:lobpcg_body;map_index,k_index=ik) do
                DFTK.lobpcg_hyper(H,initial;prec,tol=settings["solver"]["tolerance_ha"],
                    maxiter=settings["solver"]["maxiter"],miniter=1,n_conv_check=24)
            end
            boundary("k_solve_after",map_index,ik);value
        end
        TD.with_span(session,:diagnostic_maps) do
            keywords=(;seed=81001,callback,progress,case_contract=contract,hooks=(;solve=solve_hook))
            timed ? SOC.soc_scf(ctx,n,settings;keywords...,diagnostics=session) : SOC.soc_scf(ctx,n,settings;keywords...)
        end
        error("Shared controller returned without the declared two-map stop")
        end # independent numerical method world
    catch err
        if !isnothing(limit_stop[]) && err===limit_stop[] && result["completed_maps"]==2
            result["execution_status"]="DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED";result["exit_code"]=0
            result["stop_reason"]="DIAGNOSTIC_MAP_LIMIT"
            result["diagnostic_stop"]=(;reason="DIAGNOSTIC_MAP_LIMIT",boundary="map_callback_complete",
                completed_maps=2,external_request=false,acknowledged=true)
            try
                boundary("diagnostic_completed",2)
                Base.invokelatest() do
                    TD.with_span(session,:final_authentication) do
                        current=JSON3.read(read(`$python -B $(joinpath(@__DIR__,"route.py")) verify $routepath $task $outdir`,String),Dict{String,Any})
                        current==route || error("Source/adapter route changed during diagnostic")
                        environment_identity(route["numerical_root"],(DFTK,PseudoPotentialIO)).status=="PASS" || error("Environment changed during diagnostic")
                    end
                end
            catch final_error
                record_failure(final_error)
            end
        else
            record_failure(err)
            showerror(stderr,err,catch_backtrace());println(stderr)
        end
    finally
        if !isnothing(runtime[])
            try
                Base.invokelatest() do
                TD.with_span(session,:runtime_close) do
                    result["runtime_before_close"]=FI.runtime_summary(runtime[])
                    counts=result["runtime_before_close"].counters
                    result["runtime_dispatch_status"]=all(getproperty(counts,k)>0 for k in
                        (:fr_mul_calls,:component_mul_calls,:full_mul_calls)) ? "PASS" : "NOT_EXERCISED"
                    FI.close_runtime!(runtime[])
                    closed=FI.runtime_summary(runtime[])
                    result["runtime_after_close"]=closed;result["runtime_closed"]=closed.closed
                    result["workspace_released"]=closed.workspace_released && closed.owned_source_entries==0
                    result["runtime_closed"] && result["workspace_released"] || error("Owned runtime release unconfirmed")
                    result["runtime_state"]="CLOSED"
                end
                end
            catch err
                push!(result["errors"],sprint(showerror,err));result["execution_status"]="FAIL";result["exit_code"]=1
            end
        end
        if !isnothing(control[])
            try boundary("after_close";propagate=false) catch err
                push!(result["errors"],sprint(showerror,err));result["execution_status"]="FAIL";result["exit_code"]=1
            end
            result["control"]=TC.summary(control[])
            result["control_sha256"]=result["control"]["control_sha256"]
        end
    end
    if result["exit_code"]==0 && !check
        try boundary("before_result_publication") catch err;record_failure(err);end
        result["control"]=TC.summary(control[])
    end
    end # worker_total, including runtime close
    catch err
        push!(result["errors"],sprint(showerror,err));result["execution_status"]="FAIL";result["exit_code"]=1
    end
    output_started=timed ? time_ns() : nothing
    try TD.finish!(session);Base.invokelatest(emit_timing) catch err
        push!(result["errors"],sprint(showerror,err));result["execution_status"]="FAIL";result["exit_code"]=1
    end
    result["timing_output_duration_ns"]=timed ? Int(time_ns()-output_started) : nothing
    result["timing_output_duration_scope"]="Final finish/flush only, outside worker_total; per-map flush is timing_batch_output"
    result["final_result_write_timing_status"]="NOT_RECORDED_OUTSIDE_WORKER_TOTAL"
    try
        isnothing(timingio[]) || close(timingio[])
    catch err
        push!(result["errors"],sprint(showerror,err));result["execution_status"]="FAIL";result["exit_code"]=1
    end
    failure_reason!() = result["exit_code"]==0 ? nothing :
        (result["reason"]=isempty(result["errors"]) ? get(result,"stop_reason","Diagnostic entry failed") : join(result["errors"],"; "))
    if !check && isdir(outdir)
        if result["exit_code"]==0
            result["completed_maps"]==2 && result["runtime_closed"] && result["workspace_released"] &&
                result["map_checks_passed"] && result["runtime_dispatch_status"]=="PASS" &&
                !isfile(joinpath(outdir,"final.bin")) || (result["execution_status"]="FAIL";result["exit_code"]=1;push!(result["errors"],"Diagnostic completion contract failed"))
        end
        failure_reason!()
        try
            if isdefined(Main,:phase6b_write)
                Base.invokelatest(phase6b_write,joinpath(outdir,"result.json"),result)
            else
                path=joinpath(outdir,"result.json");temporary=path*".tmp"
                write(temporary,Base.invokelatest(JSON3.write,result));mv(temporary,path;force=true)
            end
        catch err
            result["execution_status"]="FAIL";result["exit_code"]=1;push!(result["errors"],sprint(showerror,err))
            println(stderr,"Diagnostic persistence failed: ",sprint(showerror,err))
        end
    end
    failure_reason!()
    isdefined(Main,:JSON3) && println(Base.invokelatest(JSON3.write,result))
    result["exit_code"]
end

isempty(ARGS) ? exit(2) : exit(timing_main(ARGS))
