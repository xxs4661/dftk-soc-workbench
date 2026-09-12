#!/usr/bin/env julia
"""Bounded extra baseline diagnostics. Including this file loads stdlibs only.
The executable path loads the existing measurement helpers after byte checks;
no SCF, eigenvalue or occupation solve is available through this entry.
"""
module SOCExtraProfile
using Dates, LinearAlgebra, Profile, Serialization, SHA
include("../soc-core-memory-v1/memory.jl")

const BASE = "7630172808773a3d4ac2da825c27fe43a8705fb8"
const PREPARATION = "360f586aefd593347d9acd3753ae51d6b78b9b1b"
const OPERATIONS = ("FR_1", "FR_24", "full_H_24", "pipeline_with_validation")
const PROFILE_CALLS = Dict("FR_1"=>100,"FR_24"=>50,"full_H_24"=>3,"pipeline_with_validation"=>1)
const PROFILE_DELAY = 0.002
const ALLOCATION_SAMPLE_RATE = 0.001
const LIMIT_BYTES = 8 * 1024^3
const CANDIDATE_FILE = "prototypes/fr_integration/hamiltonian.jl"
require(ok,reason) = ok || throw(ArgumentError(reason))
sha(path)=bytes2hex(sha256(read(path)))
git(root,args...)=strip(read(`git -C $root $args`,String))

function parse_options(args)
    args==["--help"] && return nothing
    require(count(==("--check-only"),args)<=1,"Duplicate --check-only flag")
    check_only="--check-only" in args
    args=filter(!=("--check-only"),args)
    require(iseven(length(args)) && length(args) in (8,10),"Four required option pairs; candidate additionally requires --baseline-result")
    opts=Dict(args[i]=>args[i+1] for i in 1:2:length(args))
    names=Set(("--root","--case","--mode","--output"))
    mode=get(opts,"--mode","")
    mode=="candidate" && push!(names,"--baseline-result")
    require(Set(keys(opts))==names && length(opts)==length(args)÷2,"Unknown, duplicate or missing profile options")
    require(opts["--case"] in ("B0","K4"),"Only authenticated B0/K4 performance inputs are allowed")
    require(mode in ("baseline","candidate"),"Only baseline or the single planned hash-copy candidate is supported")
    opts["--check-only"]=string(check_only)
    opts
end

function prepare_output(root,requested)
    root=realpath(root);out=normpath(abspath(requested))
    area=joinpath(root,".work","phase9a-extra","performance")
    require(startswith(out,area*"/") && out!=area,"Output must be a new extra performance run directory")
    require(!ispath(out),"Existing diagnostic output is never reused")
    # Resolve existing ancestors before making any directory, rejecting aliases.
    ancestor=dirname(out)
    while !ispath(ancestor)
        ancestor=dirname(ancestor)
    end
    require(isdir(ancestor) && realpath(ancestor)==ancestor,"Output parent is aliased")
    mkpath(out)
    require(realpath(out)==out,"Output directory is aliased")
    out
end

function checked_file(root,path;commit=nothing,expected_sha=nothing,bytes=nothing)
    require(path isa AbstractString && !isabspath(path) && !(".." in splitpath(path)),"Unconfined source path")
    full=joinpath(root,path)
    require(isfile(full) && !islink(full) && realpath(full)==full,"Missing or aliased source: $path")
    data=read(full)
    isnothing(commit) || require(data==read(`git -C $root show $(commit*":"*path)`),"Source differs from committed bytes: $path")
    isnothing(expected_sha) || require(bytes2hex(sha256(data))==expected_sha,"Source hash changed: $path")
    isnothing(bytes) || require(length(data)==bytes,"Source size changed: $path")
    (;sha256=bytes2hex(sha256(data)),bytes=length(data))
end

function baseline_path(path)
    startswith(path,"src/") || startswith(path,"prototypes/fr_integration/") ||
    startswith(path,"prototypes/relativistic/") || startswith(path,"prototypes/spinor/") ||
    startswith(path,"prototypes/crystal_soc/") || path in
    ("prototypes/soc_scf/SOCSCF.jl","prototypes/soc_scf/ensemble.jl",
     "scripts/workbench_environment.jl","scripts/upf_runtime.jl","scripts/upf_validation.jl")
end

function authenticate(root,execution,mode="baseline")
    require(isempty(git(root,"status","--porcelain","--untracked-files=all")),"Diagnostic execution checkout must be clean")
    require(git(root,"rev-parse","HEAD")==execution,"Execution HEAD changed")
    require(success(`git -C $root merge-base --is-ancestor $BASE $execution`),"Execution does not descend from accepted base")
    for name in ("plan.json","sources.json","B0.json","K6.json")
        checked_file(root,"benchmarks/soc-extra-v1/"*name;commit=PREPARATION)
    end
    sources=Main.mjson(joinpath(root,"benchmarks/soc-extra-v1/sources.json"))
    require(sources["base"]==BASE,"Wrong extra baseline identity")
    for (path,spec) in sources["historical"]
        checked_file(root,path;expected_sha=spec["sha256"],bytes=spec["bytes"])
    end
    # The old input manifest is reused as immutable data, never as an old gate.
    old=Main.mjson(joinpath(root,sources["original_static_endpoint_manifest"]))
    for (path,spec) in old["frozen_inputs_and_history"]
        checked_file(root,path;expected_sha=spec["sha256"],bytes=spec["bytes"])
    end
    actual=Dict{String,Any}();changed_adapter=Dict{String,Any}()
    paths=split(git(root,"ls-files","src","prototypes","scripts/workbench_environment.jl",
        "scripts/upf_runtime.jl","scripts/upf_validation.jl"),'\n')
    for path in paths
        endswith(path,".jl") || continue
        row=checked_file(root,path;commit=execution)
        if baseline_path(path)
            require(haskey(sources["baseline_source_sha256"],path),"Unexpected baseline numerical source: $path")
            if !(mode=="candidate" && path==CANDIDATE_FILE)
                require(row.sha256==sources["baseline_source_sha256"][path],"Baseline numerical core changed: $path")
            end
        elseif path in ("prototypes/soc_scf/scf.jl","prototypes/soc_scf/solver.jl")
            # These loaded definitions are recorded at E; this static path
            # never invokes a density map, eigenvalue or occupation solver.
            changed_adapter[path]=(;row...,baseline_sha256=sources["baseline_source_sha256"][path],
                same_as_baseline=row.sha256==sources["baseline_source_sha256"][path])
        end
        actual[path]=row
    end
    for path in ("benchmarks/soc-core-memory-v1/measure.jl","benchmarks/soc-core-memory-v1/memory.jl")
        checked_file(root,path;commit=BASE)
        actual[path]=checked_file(root,path;commit=execution)
    end
    for path in ("benchmarks/soc-extra-v1/profile.jl",)
        actual[path]=checked_file(root,path;commit=execution)
    end
    if mode=="candidate"
        require(actual[CANDIDATE_FILE].sha256!=sources["baseline_source_sha256"][CANDIDATE_FILE],"Candidate has no change in the only planned file")
    end
    (;old,actual,changed_adapter)
end

"""The same operation and output consumption as timed work; no extra warmup.
Profiler invocation counts are fixed separately and do not become timing samples.
"""
function profile_work(f,consume,count)
    require(count isa Integer && !(count isa Bool) && count>0,"Positive fixed profile repetition count required")
    for _ in 1:count
        consume(f())
    end
    nothing
end

function descriptor(path)
    (;path=basename(path),bytes=filesize(path),sha256=sha(path))
end

function diagnose(f,consume,name,out,root)
    require(name in OPERATIONS,"Unknown diagnostic operation")
    count=PROFILE_CALLS[name]
    Profile.clear()
    Profile.init(n=4_000_000,delay=PROFILE_DELAY)
    Profile.@profile profile_work(f,consume,count)
    time_data=Profile.retrieve()
    raw=joinpath(out,name*"-time-profile.bin")
    serialize(raw,time_data)
    textpath=joinpath(out,name*"-time-profile.txt")
    open(textpath,"w") do io
        Profile.print(io,time_data...;format=:flat,C=true,sortedby=:count)
    end
    raw_entries=length(first(time_data));time_data=nothing;Profile.clear()
    Profile.Allocs.clear()
    try
        Profile.Allocs.@profile sample_rate=ALLOCATION_SAMPLE_RATE profile_work(f,consume,count)
        allocations=Profile.Allocs.fetch()
        allocpath=joinpath(out,name*"-allocations.jsonl")
        # All recorded allocation events, without address/task-pointer fields.
        open(allocpath,"w") do io
            for a in allocations.allocs
                frames=[(;function_name=string(f.func),file=string(f.file),line=f.line,from_c=f.from_c) for f in a.stacktrace]
                println(io,Main.JSON3.write((;type=string(a.type),bytes=a.size,frames)))
            end
        end
        return (;status="RECORDED",calls_per_profiler=count,
            time_sampling_delay_seconds=PROFILE_DELAY,time_backtrace_entries_including_metadata=raw_entries,
            allocation_sample_rate=ALLOCATION_SAMPLE_RATE,allocation_events=length(allocations.allocs),
            sampled_allocation_bytes=sum((a.size for a in allocations.allocs);init=0),
            time_raw=descriptor(raw),time_flat=descriptor(textpath),allocations=descriptor(allocpath),
            scope="Separate diagnostic calls, excluded from five warmed timing samples; sampled allocation bytes are neither total allocations nor live memory; raw profiles stay private")
    finally
        Profile.Allocs.clear()
    end
end

# old_roots has no positional arguments. Keep the actual keyword-only call in
# one small helper so its two inventory boundaries share the tested signature.
profile_roots(payload,rhs,built,H)=Main.old_roots(;data=(;payload,rhs),built,H)

function loaded_run(root,label,out,result,identity)
    FI=Main.FRIntegration;WE=Main.WorkbenchEnvironment
    environment=WE.environment_identity(root,(Main.DFTK,Main.PseudoPotentialIO))
    result["environment"]=environment
    require(environment.status=="PASS" && VERSION==v"1.12.7","Frozen loaded Julia/package environment mismatch")
    Main.DFTK.disable_threading()
    parallelism=(;julia=Threads.nthreads(),blas=BLAS.get_num_threads(),
        fft=Main.DFTK.FFTW.get_num_threads(),mpi=Main.DFTK.mpi_nprocs(Main.DFTK.MPI.COMM_WORLD))
    result["parallelism"]=parallelism
    result["profiler_identity"]=(;julia_version=string(VERSION),
        time_source=(;path=pathof(Profile),sha256=sha(pathof(Profile))),
        allocation_source=(;path=joinpath(dirname(pathof(Profile)),"Allocs.jl"),
            sha256=sha(joinpath(dirname(pathof(Profile)),"Allocs.jl"))),
        api="Profile.@profile/clear/retrieve/print and Profile.Allocs.@profile/fetch/clear from this Julia stdlib")
    require(all(==(1),values(parallelism)),"Single Julia/BLAS/FFT/MPI execution required")
    endpoint=Main.original_endpoint(root,identity.old,label);state=endpoint.state
    casepath=label=="B0" ? "benchmarks/si-soc-splitting-v1/case.json" : "benchmarks/si-soc-sensitivity-v1/K4/case.json"
    case=Main.mjson(joinpath(root,casepath));source=Main.mjson(joinpath(root,"benchmarks/si-soc-splitting-v1/source.json"))
    contract=Main.mjson(joinpath(root,"benchmarks/soc-core-memory-v1/contract.json"))
    Main.SOCSCF.validate_soc_settings(case["settings"];case_contract=label=="K4" ? case : nothing)
    payload=Main.physical_payload(state);before=Main.msnapshot(payload)
    rhs=Main.micro_rhs(state,contract);rhs_before=Main.msnapshot(rhs)
    result["input"]=(;historical_status="HISTORICAL_REUSED",case_sha256=sha(joinpath(root,casepath)),
        checkpoint_sha256=endpoint.spec["checkpoint_sha256"],checkpoint_bytes=endpoint.spec["checkpoint_bytes"],
        raw_result_sha256=endpoint.spec["raw_result_sha256"],historical_execution_commit=endpoint.spec["execution_commit"],
        physical_payload_sha256=before,k_count=length(state.X),target_states=24,
        n_in_sha256=FI.integration_density_hash(state.n_in),n_out_sha256=FI.integration_density_hash(state.n_out))
    result["canonical_inputs"]=Main.save_payload(out,"inputs",payload)
    if result["mode"]=="candidate"
        binding=result["baseline_binding"]
        require(before==binding.physical_payload_sha256 && result["canonical_inputs"].sha256==binding.canonical_inputs_sha256,
            "Candidate physical arrays differ before context construction")
    end
    persist()=Main.mwrite(joinpath(out,"worker-result.json"),result;root,reference=root)
    persist()
    cold=@timed Main.build_static_context(root,case,source,true)
    built=cold.value;rt=built.ctx
    result["cold_initialization"]["context_construction"]=Main.cold_report(cold)
    try
        Main.authenticate_basis(rt,state,endpoint.result)
        result["canonical_operators"]=Main.save_payload(out,"operators",Main.operator_payload(rt))
        result["mode"]=="candidate" && require(result["canonical_operators"].sha256==result["baseline_binding"].canonical_operators_sha256,
            "Candidate P/D/geometry arrays differ before measurements")
        hcold=@timed FI.build_full_hamiltonian(rt,state.n_out);H=hcold.value
        result["cold_initialization"]["H_construction"]=Main.cold_report(hcold)
        result["live_memory"]["prepared"]=SOCCoreMemory.unique_memory(profile_roots(payload,rhs,built,H))
        for name in OPERATIONS
            result["active_operation"]=name;persist()
            pipeline=name=="pipeline_with_validation"
            n=name=="FR_1" ? 1 : 24
            op=name=="full_H_24" ? H.full[1] : Main.static_operators(rt)[1]
            Y=similar(rhs[n]);fill!(Y,ComplexF64(NaN,NaN))
            f=pipeline ? ()->Main.reference_pipeline(root,case,source,state,rhs,endpoint.result;core=true) : ()->Main.micro_action!(Y,op,rhs[n])
            consume=pipeline ? x->Main.compact_consume(x.values) : Main.compact_consume
            canonical=pipeline ? x->x.values : Base.identity
            function on_sample(report)
                row=isempty(report["samples"]) ? report["warmup"] : last(report["samples"])
                open(joinpath(out,"measurement-progress.jsonl"),"a") do io
                    println(io,Main.JSON3.write((;operation=name,sample=row)))
                end
                result["measurements"][name]=report;persist()
            end
            measurement=SOCCoreMemory.measure_operation(f;consume,name,on_sample)
            result["outputs"][name]=Main.save_payload(out,name,canonical(measurement.last_value))
            result["measurements"][name]=measurement.report
            result["measurements"][name]["workload"]=(;first_k_only=!pipeline,physical_states=24,
                rhs=pipeline ? [1,24,30] : [n],includes_output_consumption=true,
                pipeline_scope=pipeline ? "Original complete static pipeline including all validation, density and energy, construction and close" : nothing)
            if !pipeline
                method=which(mul!,Tuple{typeof(Y),typeof(op),typeof(rhs[n]),Int,Int})
                result["measurements"][name]["dispatch"]=(;receiver_type=string(typeof(op)),module_name=string(method.module),file=string(method.file),line=method.line)
            end
            measurement=nothing
            require(Sys.maxrss()<LIMIT_BYTES,"RESOURCE_LIMIT: observed native high-water RSS reached8GiB")
            persist()
            result["active_operation"]=name*"/profiler";persist()
            result["profiles"][name]=diagnose(f,consume,name,out,root)
            persist()
        end
        Main.static_boundary(built,:extra_profile_final;ham=H)
        result["live_memory"]["final_before_close"]=SOCCoreMemory.unique_memory(profile_roots(payload,rhs,built,H))
        result["runtime_before_close"]=FI.runtime_summary(rt)
    finally
        FI.close_runtime!(rt)
        result["runtime_after_close"]=FI.runtime_summary(rt)
        persist()
    end
    result["input_unchanged"]=(;payload=Main.msnapshot(payload)==before,rhs=Main.msnapshot(rhs)==rhs_before,
        checkpoint=sha(endpoint.checkpoint)==endpoint.spec["checkpoint_sha256"],
        result=sha(endpoint.resultpath)==endpoint.spec["raw_result_sha256"])
    require(all(values(result["input_unchanged"])) && isempty(FI._FR_CONTEXT_CERTIFICATES) && isempty(FI._BOUND_PSP_SOURCES),"Input mutation or retained context/source registration")
    require(length(result["measurements"])==length(result["outputs"])==length(result["profiles"])==4,"Incomplete four-operation diagnostic")
    require(WE.environment_identity(root,(Main.DFTK,Main.PseudoPotentialIO)).status=="PASS","Environment changed during diagnostic")
    require(Sys.maxrss()<LIMIT_BYTES,"RESOURCE_LIMIT: observed native high-water RSS reached8GiB")
    authenticate(root,result["execution_commit"],result["mode"])
    result["active_operation"]=nothing
    nothing
end

function compare_values!(rows,a,b,label)
    require(typeof(a)===typeof(b),"Canonical value type differs: $label")
    if a isa AbstractArray{<:Number}
        require(size(a)==size(b) && !isempty(a) && all(isfinite,a) && all(isfinite,b),"Invalid canonical array: $label")
        na,nb=norm(a),norm(b);difference=norm(b-a);ratio=difference/max(na,nb,1)
        require(all(isfinite,(na,nb,difference,ratio)),"Nonfinite canonical comparison: $label")
        push!(rows,(;label,kind="array",shape=collect(size(a)),reference_norm=na,candidate_norm=nb,
            absolute_L2=difference,relative=ratio,limit=1e-12,status=ratio<=1e-12 ? "PASS" : "FAIL"))
    elseif a isa Real && !(a isa Bool)
        require(isfinite(a) && isfinite(b),"Nonfinite canonical scalar: $label")
        delta=b-a;limit=endswith(label,"/entropy_dimensionless") ? 0.0 : 1e-10
        push!(rows,(;label,kind="scalar",reference=a,candidate=b,difference=delta,
            limit,status=abs(delta)<=limit ? "PASS" : "FAIL"))
    elseif a isa NamedTuple || a isa AbstractDict
        require(Set(keys(a))==Set(keys(b)),"Canonical fields differ: $label")
        for key in sort(collect(keys(a));by=string)
            compare_values!(rows,a[key],b[key],label*"/"*string(key))
        end
    elseif a===nothing
        nothing
    else
        throw(ArgumentError("Unsupported canonical comparison: $label"))
    end
    rows
end

function canonical_payload(directory,record)
    require(record["path"]==basename(record["path"]),"Unconfined canonical payload")
    checked_file(directory,record["path"];expected_sha=record["sha256"],bytes=record["bytes"])
    deserialize(joinpath(directory,record["path"]))
end

function candidate_screen(result,baseline_file,out)
    require(isfile(baseline_file) && !islink(baseline_file) && realpath(baseline_file)==baseline_file,"Missing or aliased baseline result")
    baseline=Main.mjson(baseline_file);directory=dirname(baseline_file)
    require(baseline["overall_status"]=="PASS" && baseline["exit_code"]===0 && baseline["mode"]=="baseline" &&
        baseline["kind"]=="FINITE_PERFORMANCE_DIAGNOSTIC" && baseline["case"]==result["case"],"Wrong or incomplete baseline result")
    require(baseline["input"]==Main.JSON3.read(Main.JSON3.write(result["input"]),Dict{String,Any}),"Matched historical input identity differs")
    require(baseline["environment"]["status"]=="PASS" && baseline["environment"]["manifest_sha256"]==result["environment"].manifest_sha256 &&
        baseline["environment"]["julia_version"]==result["environment"].julia_version,"Baseline/candidate environment identity differs")
    require(baseline["parallelism"]==Main.JSON3.read(Main.JSON3.write(result["parallelism"]),Dict{String,Any}),"Baseline/candidate threading differs")
    for key in ("canonical_inputs","canonical_operators")
        require(baseline[key]["sha256"]==getproperty(result[key],:sha256),"Canonical input or P/D bytes differ")
        canonical_payload(directory,baseline[key])
    end
    current=Main.JSON3.read(Main.JSON3.write(result["actual_source_files"]),Dict{String,Any})
    old=baseline["actual_source_files"]
    require(Set(keys(old))==Set(keys(current)),"Candidate source closure differs")
    for path in keys(old)
        path==CANDIDATE_FILE || require(old[path]==current[path],"Candidate changed another included or measurement source: $path")
    end
    require(old[CANDIDATE_FILE]!=current[CANDIDATE_FILE],"Candidate source is identical to baseline")
    rows=Any[];ratios=Dict{String,Any}()
    require(Set(keys(baseline["measurements"]))==Set(OPERATIONS),"Baseline lacks the fixed operation set")
    for name in OPERATIONS
        before=baseline["measurements"][name];after=result["measurements"][name]
        for measurement in (before,after)
            require(measurement["status"]=="PASS" && measurement["warmup_count"]==1 && measurement["requested_samples"]==measurement["completed_samples"]==5 &&
                length(measurement["samples"])==5,"Baseline/candidate lacks all five successful samples")
        end
        require(before["workload"]==Main.JSON3.read(Main.JSON3.write(after["workload"]),Dict{String,Any}),"Candidate workload changed")
        bp=baseline["profiles"][name];cp=result["profiles"][name]
        for field in ("calls_per_profiler","time_sampling_delay_seconds","allocation_sample_rate")
            require(bp[field]==getproperty(cp,Symbol(field)),"Candidate profiler setting changed")
        end
        original=canonical_payload(directory,baseline["outputs"][name])
        candidate=canonical_payload(out,Main.JSON3.read(Main.JSON3.write(result["outputs"][name]),Dict{String,Any}))
        compare_values!(rows,original,candidate,name)
        time_ratio=after["statistics"]["time_seconds"]["median"]/before["statistics"]["time_seconds"]["median"]
        alloc_ratio=after["statistics"]["allocated_bytes"]["median"]/before["statistics"]["allocated_bytes"]["median"]
        ratios[name]=(;time_median_ratio=time_ratio,allocation_median_ratio=alloc_ratio)
    end
    pipeline=ratios["pipeline_with_validation"]
    equivalent=all(row.status=="PASS" for row in rows)
    performance=pipeline.time_median_ratio<=0.9 && pipeline.time_median_ratio<=1.1 && pipeline.allocation_median_ratio<=1.1
    (;status=equivalent && performance ? "ELIGIBLE_FOR_JOINT_B0_K4_REVIEW" : "REJECTED",
        equivalence_status=equivalent ? "PASS" : "FAIL",performance_status=performance ? "PASS" : "RETAIN_BASELINE",
        baseline_result_sha256=sha(baseline_file),baseline_execution_commit=baseline["execution_commit"],
        changed_file=CANDIDATE_FILE,rows,ratios,
        scope="Per-case screen only; both B0/K4 screens and affected tests must pass before joint candidate adoption")
end

function baseline_binding(path,label,actual)
    require(path isa AbstractString && isfile(path) && !islink(path),"Missing baseline result")
    path=realpath(path);baseline=Main.mjson(path)
    require(baseline["overall_status"]=="PASS" && baseline["exit_code"]===0 && baseline["mode"]=="baseline" &&
        baseline["kind"]=="FINITE_PERFORMANCE_DIAGNOSTIC" && baseline["case"]==label,"Wrong or incomplete baseline result")
    current=Main.JSON3.read(Main.JSON3.write(actual),Dict{String,Any});old=baseline["actual_source_files"]
    require(Set(keys(old))==Set(keys(current)),"Candidate source closure differs")
    for file in keys(old)
        file==CANDIDATE_FILE || require(old[file]==current[file],"Candidate changed another included or measurement source: $file")
    end
    require(old[CANDIDATE_FILE]!=current[CANDIDATE_FILE],"Candidate source identical to baseline")
    for name in OPERATIONS
        row=baseline["measurements"][name]
        require(row["status"]=="PASS" && row["warmup_count"]==1 && row["completed_samples"]==5,"Incomplete baseline samples")
        canonical_payload(dirname(path),baseline["outputs"][name])
    end
    for field in ("canonical_inputs","canonical_operators")
        canonical_payload(dirname(path),baseline[field])
    end
    (;path,result_sha256=sha(path),execution_commit=baseline["execution_commit"],
        run_id=baseline["run_id"],physical_payload_sha256=baseline["input"]["physical_payload_sha256"],
        canonical_inputs_sha256=baseline["canonical_inputs"]["sha256"],
        canonical_operators_sha256=baseline["canonical_operators"]["sha256"])
end

function check_loaded(root,label,result)
    WE=Main.WorkbenchEnvironment;FI=Main.FRIntegration
    environment=WE.environment_identity(root,(Main.DFTK,Main.PseudoPotentialIO))
    result["environment"]=environment
    require(environment.status=="PASS" && VERSION==v"1.12.7","Frozen loaded environment mismatch")
    path=label=="B0" ? "benchmarks/si-soc-splitting-v1/case.json" : "benchmarks/si-soc-sensitivity-v1/K4/case.json"
    case=Main.mjson(joinpath(root,path))
    Main.SOCSCF.validate_soc_settings(case["settings"];case_contract=label=="K4" ? case : nothing)
    require(isempty(FI._FR_CONTEXT_CERTIFICATES) && isempty(FI._BOUND_PSP_SOURCES),"Entry check constructed or registered a context/source")
    result["entry_check"]=(;status="CHECK_ONLY_PASS",context_count=0,registered_sources=0,
        measured_samples=0,profile_calls=0,scope="Actual definitions, source and environment checks only; no context or numerical workload")
    nothing
end

function main_loaded(root,label,mode,out,execution,loading,baseline_file,check_only)
    result=Dict{String,Any}("schema_version"=>1,"experiment"=>"soc-extra-v1","kind"=>"FINITE_PERFORMANCE_DIAGNOSTIC",
        "run_id"=>basename(out),"case"=>label,"mode"=>mode,"backend"=>"soc-core","check_only"=>check_only,
        "base_commit"=>BASE,"preparation_commit"=>PREPARATION,"execution_commit"=>execution,
        "started_utc"=>string(now(UTC)),"overall_status"=>"INCOMPLETE","exit_code"=>9,
        "evidence_level"=>"RUNNER_REPORTED_PRIVATE_ARRAY_DIAGNOSTIC","no_scf"=>true,"no_eigensolve"=>true,"no_occupation_solve"=>true,
        "measurements"=>Dict{String,Any}(),"outputs"=>Dict{String,Any}(),"profiles"=>Dict{String,Any}(),
        "live_memory"=>Dict{String,Any}(),"cold_initialization"=>Dict("dependency_helper_load"=>Main.cold_report(loading)))
    persist()=Main.mwrite(joinpath(out,"worker-result.json"),result;root,reference=root)
    persist()
    try
        identity=authenticate(root,execution,mode)
        result["actual_source_files"]=identity.actual
        result["loaded_unexercised_scf_adapter_sources"]=identity.changed_adapter
        mode=="candidate" && (result["baseline_binding"]=baseline_binding(baseline_file,label,identity.actual))
        loading=@timed Main.load_reference_modules(root)
        result["included_entry_modules"]=loading.value
        result["cold_initialization"]["numerical_module_load"]=Main.cold_report(loading)
        persist()
        if check_only
            result["kind"]="DEFINITION_ENVIRONMENT_ENTRY_CHECK"
            Base.invokelatest(check_loaded,root,label,result)
        else
            Base.invokelatest(loaded_run,root,label,out,result,identity)
        end
        if mode=="candidate" && !check_only
            require(sha(result["baseline_binding"].path)==result["baseline_binding"].result_sha256,"Bound baseline result changed")
            result["candidate_screen"]=candidate_screen(result,result["baseline_binding"].path,out)
            require(result["candidate_screen"].equivalence_status=="PASS","Candidate failed fixed numerical equivalence; dependent work must stop")
        end
        result["overall_status"]=check_only ? "CHECK_ONLY_PASS" : "PASS";result["exit_code"]=0
    catch error
        result["overall_status"]="FAIL";result["exit_code"]=9
        result["error_type"]=string(typeof(error));result["reason"]=sprint(showerror,error)
        showerror(stderr,error,catch_backtrace());println(stderr)
    end
    result["finished_utc"]=string(now(UTC));result["peak_rss_bytes"]=Sys.maxrss()
    persist()
    println(Main.JSON3.write((;run_id=result["run_id"],overall_status=result["overall_status"],exit_code=result["exit_code"])))
    result["exit_code"]
end

function main(args)
    options=parse_options(args)
    if isnothing(options)
        println("profile.jl --root ROOT --case B0|K4 --mode baseline|candidate --output NEW_DIRECTORY [--baseline-result BASELINE_WORKER_JSON] [--check-only]; use an external process-group RSS observer (8GiB stop); no SCF or eigensolve")
        return 0
    end
    root=realpath(options["--root"])
    require(root==realpath(joinpath(@__DIR__,"../..")),"Root must be the actual source checkout")
    out=prepare_output(root,options["--output"])
    execution=git(root,"rev-parse","HEAD")
    checked_file(root,"benchmarks/soc-core-memory-v1/measure.jl";commit=BASE)
    checked_file(root,"benchmarks/soc-core-memory-v1/memory.jl";commit=BASE)
    loading=@timed Base.include(Main,joinpath(root,"benchmarks/soc-core-memory-v1/measure.jl"))
    Base.invokelatest(main_loaded,root,options["--case"],options["--mode"],out,execution,loading,get(options,"--baseline-result",nothing),options["--check-only"]=="true")
end
function safe_main(args)
    try
        main(args)
    catch error
        println(stderr,"EXTRA PROFILE FAILURE: ",sprint(showerror,error));return 9
    end
end
end
abspath(PROGRAM_FILE)==(@__FILE__) && exit(SOCExtraProfile.safe_main(ARGS))
