#!/usr/bin/env julia
# Static K4 construction and local validation only. No SCF/map/solve entry is called.
using JSON3, SHA, LinearAlgebra, TOML
const LOCAL_ROOT=normpath(joinpath(@__DIR__,"../.."))
include(joinpath(LOCAL_ROOT,"prototypes/diagnostics.jl"))
include(joinpath(LOCAL_ROOT,"benchmarks/soc-timing-v1/control.jl"))
const LC=SocTimingControl
const LD=WorkbenchDiagnostics

function local_write(path,value)
    raw=JSON3.write(value);JSON3.read(raw)
    tmp=path*".tmp";write(tmp,raw*"\n");mv(tmp,path;force=true)
end
local_hash(path)=bytes2hex(sha256(read(path)))
function timed_record(f)
    t=@timed f()
    fields=Dict{String,Any}("seconds"=>t.time,"allocation_bytes"=>t.bytes,"gc_seconds"=>t.gctime)
    for k in (:compile_time,:recompile_time)
        fields[string(k)]=hasproperty(t,k) ? getproperty(t,k) : nothing
    end
    (t.value,fields)
end

# Keep ownership visible to finally before any cooperative post-construction check.
# This helper is also tested with nonphysical constructors; it does not choose inputs.
function construct_static!(context_ref,runtime_ref,result,boundary,make_context,make_runtime)
    boundary("context_setup_before")
    context_ref[],t=timed_record(make_context)
    result["stages"]["context_setup"]=t;result["context_constructed"]=true
    boundary("context_setup_after")
    boundary("runtime_setup_before")
    runtime_ref[],t=timed_record(()->make_runtime(context_ref[]))
    result["stages"]["runtime_setup"]=t
    result["runtime_state"]="OPEN";result["owned_runtime_constructed"]=true
    boundary("runtime_setup_after")
    nothing
end

# Equal outer integrity checks, not charged to the measured function. Hash unique
# arrays once in this snapshot only; keep original DFTK wrappers and storage order.
function local_snapshot(rt,H)
    arrays=Any[]
    for (i,op) in enumerate(rt.fr_blocks)
        push!(arrays,("P/$i",op.P));push!(arrays,("D/$i",op.D))
    end
    append!(arrays,[("derived/"*x[1],x[2]) for x in FI._runtime_term_arrays(rt)])
    append!(arrays,[("current/"*x[1],x[2]) for x in FI._ham_storage(rt._current)])
    ids=IdDict{Any,Int}();hashes=IdDict{Any,String}();rows=Any[]
    id(a)=get!(()->length(ids)+1,ids,a)
    for (label,a) in arrays
        oid=id(a);p=parent(a);pid=id(p)
        digest=get!(()->FI._fr_array_hash(a),hashes,a)
        stride=try collect(strides(a)) catch; nothing end
        push!(rows,(;label,object_group=oid,parent_group=pid,parent_type=string(typeof(p)),
            type=string(typeof(a)),eltype=string(eltype(a)),shape=collect(size(a)),strides=stride,sha256=digest))
    end
    b=rt.basis
    ks=[(;coordinate=collect(k.coordinate),weight=b.kweights[i],ng=length(k.G_vectors),
           G_sha256=FI._source_snapshot(k.G_vectors),mapping_sha256=FI._source_snapshot(k.mapping),
           mapping_inv_sha256=FI._source_snapshot(k.mapping_inv),mapping_device_sha256=FI._source_snapshot(k.mapping_device))
        for (i,k) in enumerate(b.kpoints)]
    (;generation=rt._generation,fft_size=collect(b.fft_size),lattice=collect.(eachcol(b.model.lattice)),
      electron_count=b.model.n_electrons,temperature=b.model.temperature,Ecut=b.Ecut,
      arrays=rows,kpoints=ks,full_hamiltonian_count=length(H.full),
      source_snapshots=[(;common=FI._source_snapshot(s.common),channels=FI._source_snapshot(s.channels),
                          parsed=FI._source_snapshot(s.parsed)) for s in rt.bundles])
end
function storage_call(rt,role,selection=nothing)
    arrays=FI._ham_storage(rt._current);certificate=rt._current_storage
    if !isnothing(selection)
        arrays=arrays[selection];certificate=certificate[selection]
    end
    if role=="S"
        FI._check_storage(certificate,arrays)
    else
        FI._with_validation(rt) do memo
            FI._check_storage(certificate,arrays,memo)
        end
    end
end
function measured_operation(rt,H,role,name,selection)
    name=="boundary" ? FI.runtime_boundary!(rt,:local_probe;ham=H.full) :
        storage_call(rt,role,selection)
end
function local_work(route,outdir,result,control,check)
    role=route["role"];source=route["numerical_root"]
    boundary(event;propagate=true)=isnothing(control) ? nothing : LC.boundary!(control,event;propagate)
    rt=nothing;observer=nothing;observer_module=nothing
    context_ref=Ref{Any}(nothing);runtime_ref=Ref{Any}(nothing)
    stage(name,f)=begin
        boundary(name*"_before")
        value,t=timed_record(f);result["stages"][name]=t
        boundary(name*"_after");value
    end
    # Julia do syntax puts f first.
    stag(f,name)=stage(name,f)
    try
        case=si_case("K4")
        result["environment"]=environment_identity(source,(DFTK,PseudoPotentialIO))
        result["environment"].status=="PASS" || error("Frozen loaded environment mismatch")
        DFTK.disable_threading()
        Threads.nthreads()==BLAS.get_num_threads()==DFTK.FFTW.get_num_threads()==1 || error("Serial execution required")
        DFTK.mpi_nprocs(DFTK.MPI.COMM_WORLD)==1 || error("Single MPI process required")
        result["parallelism"]=(;julia=Threads.nthreads(),blas=BLAS.get_num_threads(),fft=DFTK.FFTW.get_num_threads(),mpi=1)
        result["methods"]=Dict{String,Any}()
        for (name,f,types) in (("runtime_boundary",FI.runtime_boundary!,Tuple{FI.OwnedRuntime,Symbol}),
                              ("validate_context",FI.validate_context,Tuple{FI.OwnedRuntime}),
                              ("storage",FI._check_storage,Tuple{Vector,Vector}),
                              ("build_full_hamiltonian",FI.build_full_hamiltonian,Tuple{FI.OwnedRuntime,Array{Float64,3}}))
            m=which(f,types);path,line=Base.functionloc(m);real=realpath(String(path))
            startswith(real,realpath(source)*"/") || error("Loaded source mismatch: "*name)
            result["methods"][name]=(;relative_path=relpath(real,source),line,source_sha256=local_hash(real))
        end
        result["actual_method_sources"]=result["methods"]
        fixture=JSON3.read(read(route["fixture_path"],String),Dict{String,Any})
        dens=fixture["density"];densitypath=route["density_path"]
        local_hash(densitypath)==dens["sha256"] && filesize(densitypath)==dens["bytes"] || error("Density bytes changed")
        ENDIAN_BOM==0x04030201 || error("Explicit little-endian density requires little-endian host")
        if check
            isempty(FI._FR_CONTEXT_CERTIFICATES) && isempty(FI._BOUND_PSP_SOURCES) || error("Precheck constructed state")
            result["execution_status"]="CHECK_ONLY_PASS";result["exit_code"]=0
            result["formal_slot_reserved"]=false;result["numerical_execution_status"]="NOT_RUN";return
        end
        n=reshape(copy(reinterpret(Float64,read(densitypath))),Tuple(Int.(dens["fft_shape"])))
        all(isfinite,n) || error("Nonfinite fixed density")
        result["density_sha256"]=local_hash(densitypath)
        construct_static!(context_ref,runtime_ref,result,boundary,
            ()->si_context(case,"scf";backend="soc-core"),
            built->role=="S" ? FI.owned_runtime(built.ctx;max_rhs=30) :
                FI.owned_runtime(built.ctx;max_rhs=30,validation_policy=Symbol(route["validation_policy"])))
        rt=runtime_ref[]
        result["density_electrons"]=sum(n)*rt.basis.dvol
        abs(result["density_electrons"]-8)<=1e-8 || error("Fixed density electron count differs")
        H=stag("fixed_density_hamiltonian_setup") do
            FI.build_full_hamiltonian(rt,n)
        end
        result["setup_status"]="STATIC_CONTEXT_SETUP_NOT_SCF"
        result["static_context_setup_status"]=result["setup_status"]
        before=stag("outer_integrity_before") do
            local_snapshot(rt,H)
        end
        local_write(joinpath(outdir,"fixture-observed.json"),before)
        result["fixture_observed_sha256"]=local_hash(joinpath(outdir,"fixture-observed.json"))
        result["runtime_before"]=FI.runtime_summary(rt)
        if startswith(result["task_id"],"DIAG-")
            include(joinpath(@__DIR__,"observe.jl"))
            observer_module=getfield(@__MODULE__,:ValidationLocalObserver)
            observer=Base.invokelatest(observer_module.install_observer!,FI,role,source)
            # Observer definitions introduce a fresh world; only diagnostics use it.
            Base.invokelatest() do
                traces=Any[]
                for name in ("boundary","storage")
                    boundary("trace_"*name*"_before")
                    observer_module.start_trace!(observer,name)
                    returned,t=timed_record(()->measured_operation(rt,H,role,name,nothing))
                    trace=observer_module.finish_trace!(observer)
                    push!(traces,(;operation=name,returned,timing=t,trace))
                    boundary("trace_"*name*"_after")
                end
                local_write(joinpath(outdir,"trace.json"),traces)
                local_write(joinpath(outdir,"observer.json"),observer_module.observer_manifest(observer))
                result["trace_sha256"]=local_hash(joinpath(outdir,"trace.json"))
                result["observer_sha256"]=local_hash(joinpath(outdir,"observer.json"))
            end
        else
            # Selection is fixed from the diagnosis and committed before E_new.
            selected=JSON3.read(read(joinpath(LOCAL_ROOT,"benchmarks/soc-validation-local-v1/selection.json"),String),Dict{String,Any})
            operations=Any[(;name="boundary",indices=nothing),(;name="storage",indices=nothing)]
            for spec in selected["sequences"]
                push!(operations,(;name=spec["name"],indices=Int.(spec["indices"])))
            end
            length(operations)<=5 || error("Too many representative sequences")
            samples=Any[]
            for op in operations
                for i in 1:7
                    boundary("sample_"*op.name*"_"*string(i)*"_before")
                    value,t=timed_record(()->measured_operation(rt,H,role,op.name,op.indices))
                    value===true || error("Validation returned unexpected result")
                    row=merge(Dict("operation"=>op.name,"sample_index"=>i,"kind"=>(i<=2 ? "warmup" : "measurement")),t)
                    push!(samples,row);local_write(joinpath(outdir,"samples.json"),samples)
                    boundary("sample_"*op.name*"_"*string(i)*"_after")
                end
            end
            result["samples_sha256"]=local_hash(joinpath(outdir,"samples.json"))
            result["sample_contract"]=(;warmups=2,samples=5,trace_enabled=false,operations=length(operations))
        end
        after=stag("outer_integrity_after") do
            local_snapshot(rt,H)
        end
        # Serialized NamedTuple field order is stable and independent of process IDs.
        JSON3.write(before)==JSON3.write(after) || error("Protected state changed during static probe")
        result["outer_integrity_status"]="PASS"
        bytes2hex(sha256(reinterpret(UInt8,vec(n))))==dens["sha256"] || error("Fixed input density changed")
        local_hash(densitypath)==dens["sha256"] || error("Density source file changed")
        result["validation_operations_status"]="PASS"
        result["runtime_after_operations"]=Base.invokelatest(FI.runtime_summary,rt)
        all(iszero,values(result["runtime_after_operations"].counters)) || error("Forbidden numerical operator action occurred")
        result["execution_status"]="STATIC_VALIDATION_COMPLETED_NOT_SCF";result["exit_code"]=0
    catch err
        if err isa LD.ControlledStop
            result["execution_status"]=err.reason;result["stop_reason"]=err.reason
            result["exit_code"]=err.reason=="USER_CANCELLED" ? 130 : err.reason=="TIME_BUDGET_EXCEEDED" ? 124 : 17
        else
            result["execution_status"]="FAIL";result["exit_code"]=1;push!(result["errors"],sprint(showerror,err))
            showerror(stderr,err,catch_backtrace());println(stderr)
        end
    finally
        isnothing(rt) && (rt=runtime_ref[])
        if !isnothing(observer)
            try Base.invokelatest(observer_module.clear_observer!,observer) catch err
                push!(result["errors"],sprint(showerror,err));result["exit_code"]=1;result["execution_status"]="FAIL"
            end
        end
        if !isnothing(rt)
            try
                result["runtime_before_close"]=Base.invokelatest(FI.runtime_summary,rt)
                _,t=timed_record(()->Base.invokelatest(FI.close_runtime!,rt));result["stages"]["close"]=t
                closed=Base.invokelatest(FI.runtime_summary,rt)
                result["runtime_after_close"]=closed;result["runtime_closed"]=closed.closed
                result["workspace_released"]=closed.workspace_released && closed.owned_source_entries==0
                result["runtime_state"]="CLOSED"
                result["runtime_closed"] && result["workspace_released"] || error("Runtime release not confirmed")
            catch err
                push!(result["errors"],sprint(showerror,err));result["exit_code"]=1;result["execution_status"]="FAIL"
            end
        end
        if !isnothing(control)
            try boundary("after_close";propagate=false) catch err
                push!(result["errors"],sprint(showerror,err));result["exit_code"]=1;result["execution_status"]="FAIL"
            end
            result["control"]=LC.summary(control);result["control_sha256"]=control.control_sha256
        end
    end
end
function local_main(args)
    check=last(args)=="--check-entry";a=check ? args[1:end-1] : args
    length(a)==3 || return 2
    task,outdir,routepath=a;outdir=abspath(outdir)
    result=Dict{String,Any}("schema_version"=>1,"task_id"=>task,"run_id"=>basename(dirname(outdir)),
        "worker_id"=>"worker","execution_status"=>"FAIL","exit_code"=>1,"errors"=>String[],
        "context_constructed"=>false,"owned_runtime_constructed"=>false,"runtime_state"=>"NOT_CONSTRUCTED",
        "runtime_closed"=>false,"workspace_released"=>false,"stages"=>Dict{String,Any}(),
        "setup_status"=>"NOT_RUN","check_only"=>check,"scf_status"=>"NOT_RUN","eigensolve_status"=>"NOT_RUN",
        "maps_executed"=>0,"scientific_convergence_status"=>"NOT_ASSESSED")
    control=nothing
    try
        python=ENV["SOC_LOCAL_PYTHON"]
        route=JSON3.read(read(`$python -B $(joinpath(@__DIR__,"supervisor.py")) verify $routepath $task $outdir`,String),Dict{String,Any})
        for key in ("experiment","execution_commit","source_commit","case_sha256","role","validation_policy",
                    "strategy","fixture_sha256","density_sha256","mode")
            result[key]=route[key]
        end
        route["check_only"]===check || error("Entry mode differs from authenticated route")
        if !check
            ispath(outdir) && error("Existing worker output rejected");mkpath(outdir)
            raw=LC.safe_read(joinpath(dirname(outdir),"control.toml"));conf=TOML.parse(String(copy(raw)))
            bytes2hex(sha256(raw))==route["control_sha256"] || error("Authenticated control changed")
            control=LC.State(dirname(outdir),conf,raw,route["control_sha256"],nothing,nothing,nothing,"",0)
            result["control_sha256"]=control.control_sha256
            LC.boundary!(control,"before_module_load")
        end
        include(joinpath(route["numerical_root"],"scripts/run_si_soc.jl"))
        Base.invokelatest(local_work,route,outdir,result,control,check)
        JSON3.read(read(`$python -B $(joinpath(@__DIR__,"supervisor.py")) verify $routepath $task $outdir`,String))
        !check && result["exit_code"]==0 && LC.boundary!(control,"before_result_publication")
    catch err
        if err isa LD.ControlledStop && isempty(result["errors"])
            result["execution_status"]=err.reason;result["stop_reason"]=err.reason
            result["exit_code"]=err.reason=="USER_CANCELLED" ? 130 : err.reason=="TIME_BUDGET_EXCEEDED" ? 124 : 17
        else
            result["execution_status"]="FAIL";result["exit_code"]=1;push!(result["errors"],sprint(showerror,err))
        end
        showerror(stderr,err,catch_backtrace());println(stderr)
    end
    if !isnothing(control)
        result["control"]=LC.summary(control);result["control_sha256"]=control.control_sha256
    end
    result["exit_code"]!=0 && (result["reason"]=isempty(result["errors"]) ? get(result,"stop_reason","Static entry failed") : join(result["errors"],"; "))
    if !check && isdir(outdir)
        try local_write(joinpath(outdir,"result.json"),result) catch err
            result["exit_code"]=9;result["execution_status"]="FAIL";println(stderr,"Persistence failure: ",sprint(showerror,err))
        end
    end
    println(JSON3.write(result));result["exit_code"]
end
abspath(PROGRAM_FILE)==(@__FILE__) && exit(isempty(ARGS) ? 2 : local_main(ARGS))
