#!/usr/bin/env julia
# Supplementary constructor-data export. No timing samples or solver operations.
using SHA, JSON3, Dates
const EXPORT_REF_EXECUTION="bbe9aa7755f052900e6e9c4618252a410e1cc8f0"
const EXPORT_REF_RECEIPTS=Dict(
    "B0"=>(;directory=".work/phase9a/static/REF-B0-20260909T103314263290Z-c672b973",
        outer="b7d520ec0cf0b6909a79107793896f6c0a50574035e3fe0b30e7cd12e96f253d",
        worker="efeb4eb4aa3fddbef721d2749fc4eeb5dbbfa4289c664dcfd6307b37048370f0"),
    "K4"=>(;directory=".work/phase9a/static/REF-K4-20260909T103452759115Z-43829d19",
        outer="33c9a7141bd165b65ce549d1a3a96a81400e71aeb861ddcd9ce4e7ef0497a09c",
        worker="71cd1fe94c95f83aeb2665e6dc2610a4dbb667a647e4f79c3dcc6c39ddb5e319"))

function export_ref_binding(root,sources,label)
    fixed=EXPORT_REF_RECEIPTS[label];directory=joinpath(root,fixed.directory)
    receipt=joinpath(directory,"result.json");workerpath=joinpath(directory,"worker-result.json")
    mrequire(isfile(receipt) && isfile(workerpath),"BLOCKED: completed original REF receipts are missing")
    mrequire(!islink(receipt) && !islink(workerpath) && msha(receipt)==fixed.outer && msha(workerpath)==fixed.worker,"Completed REF receipts changed")
    outer=mjson(receipt);worker=mjson(workerpath)
    mrequire(outer["overall_status"]==worker["overall_status"]=="PASS" && outer["exit_code"]===worker["exit_code"]===0 &&
        outer["execution_commit"]==worker["execution_commit"]==EXPORT_REF_EXECUTION && worker["suite"]=="REF-$label" &&
        outer["worker_result_sha256"]==fixed.worker,"Completed REF identity/status differs")
    source=sources["historical_endpoints"][label];original=joinpath(root,source["directory"])
    mrequire(isfile(joinpath(original,"result.json")) && isfile(joinpath(original,"final.bin")),"BLOCKED: original endpoint result/checkpoint is missing")
    mrequire(msha(joinpath(original,"result.json"))==source["raw_result_sha256"] &&
        filesize(joinpath(original,"final.bin"))==source["checkpoint_bytes"] &&
        msha(joinpath(original,"final.bin"))==source["checkpoint_sha256"],"Original checkpoint/result changed since REF")
    mrequire(worker["input"]["checkpoint_sha256"]==source["checkpoint_sha256"] &&
        worker["input"]["raw_result_sha256"]==source["raw_result_sha256"],"REF input does not belong to the declared original endpoint")
    transport=worker["canonical_inputs"];mrequire(transport["path"]=="inputs.bin","Unexpected original REF transport name")
    inputpath=joinpath(directory,transport["path"])
    mrequire(isfile(inputpath),"BLOCKED: completed REF canonical input bytes are missing")
    mrequire(!islink(inputpath) && filesize(inputpath)==transport["bytes"] && msha(inputpath)==transport["sha256"]==worker["input"]["physical_payload_sha256"],"Completed REF canonical input bytes changed")
    (;run_id=outer["run_id"],execution_commit=EXPORT_REF_EXECUTION,receipt_sha256=fixed.outer,worker_sha256=fixed.worker,
        checkpoint_sha256=source["checkpoint_sha256"],raw_result_sha256=source["raw_result_sha256"],
        canonical_inputs_sha256=transport["sha256"],canonical_inputs_bytes=transport["bytes"],
        input_deserialized=false,original_arrays_modified=false)
end

function export_reference_loaded(root,reference,label,outdir,result,sources)
    FI=Main.FRIntegration;WE=Main.WorkbenchEnvironment
    identity=WE.environment_identity(root,(Main.DFTK,Main.PseudoPotentialIO));result["environment"]=identity
    mrequire(identity.status=="PASS" && VERSION==v"1.12.7","Frozen actual loaded environment differs")
    Main.DFTK.disable_threading()
    result["parallelism"]=(;julia=Threads.nthreads(),blas=Main.BLAS.get_num_threads(),fft=Main.DFTK.FFTW.get_num_threads(),mpi=Main.DFTK.mpi_nprocs(Main.DFTK.MPI.COMM_WORLD))
    mrequire(all(==(1),values(result["parallelism"])),"Single-process/thread export required")
    result["reference_measurement"]=export_ref_binding(root,sources,label)
    fixed=EXPORT_REF_RECEIPTS[label]
    result["reference_suite_receipt"]=(;path=fixed.directory*"/result.json",sha256=fixed.outer)
    casepath=label=="B0" ? "benchmarks/si-soc-splitting-v1/case.json" : "benchmarks/si-soc-sensitivity-v1/K4/case.json"
    case=mjson(joinpath(root,casepath));source=mjson(joinpath(root,"benchmarks/si-soc-splitting-v1/source.json"))
    endpoint=mjson(joinpath(root,sources["historical_endpoints"][label]["directory"],"result.json"))
    built=build_original_context(root,case,source) # Exactly one old loader/context construction.
    ctx=built.ctx;FI.validate_context(ctx);FI.assert_bound_sources(built.bundle)
    actual=JSON3.read(JSON3.write(FI.basis_summary(ctx)),Dict{String,Any})
    mrequire(actual==endpoint["grid"]["basis"],"Actual source/case/G order differs from original endpoint")
    result["basis"]=actual;result["source"]=FI.common_data_summary(built.bundle)
    result["case_sha256"]=msha(joinpath(root,casepath))
    payload=operator_payload(ctx) # Same canonical schema as the CORE suite output.
    mrequire(length(payload)==(label=="B0" ? 8 : 64),"Wrong operator point count")
    rows=map(enumerate(payload)) do (i,entry)
        mrequire(size(entry.P)==(2length(entry.G),72) && size(entry.D)==(72,72) && length(entry.labels)==72 &&
            all(isfinite,entry.P) && all(isfinite,entry.D),"Invalid original rectangular operator data")
        (;k_index=i,coordinate=entry.coordinate,weight=entry.weight,ng=length(entry.G),P_shape=collect(size(entry.P)),D_shape=collect(size(entry.D)),
            P_sha256=msnapshot(entry.P),D_sha256=msnapshot(entry.D),labels_sha256=msnapshot(entry.labels),G_sha256=msnapshot(entry.G))
    end
    path=joinpath(outdir,"operators.bin");mrequire(!ispath(path),"Existing operator data is never reused")
    Main.Serialization.serialize(path,payload)
    result["operators"]=(;path="operators.bin",sha256=msha(path),bytes=filesize(path))
    result["transport_format"]="Julia1.12.7 native Serialization; per point coordinate/weight/G/P/D/labels; exact original old-constructor arrays"
    result["per_k"]=rows
    FI.validate_context(ctx);FI.assert_bound_sources(built.bundle)
    mrequire(all(msnapshot(entry.P)==rows[i].P_sha256 && msnapshot(entry.D)==rows[i].D_sha256 &&
        msnapshot(entry.labels)==rows[i].labels_sha256 && msnapshot(entry.G)==rows[i].G_sha256 for (i,entry) in enumerate(payload)),"Operator data changed during export")
    result["reference_measurement"]==export_ref_binding(root,sources,label) || error("Original REF input changed during export")
    authenticate(root,reference,"REF-$label")
    mrequire(WE.environment_identity(root,(Main.DFTK,Main.PseudoPotentialIO)).status=="PASS","Actual environment changed during export")
    mrequire(Sys.maxrss()<8*1024^3,"RESOURCE_BLOCKED: exporter peak reached8GiB")
    result["constructor_calls"]=1;result["legacy_contexts_retained"]=length(FI._FR_CONTEXT_CERTIFICATES)
    mrequire(result["legacy_contexts_retained"]==1,"Unexpected extra context construction")
    result["overall_status"]="PASS";result["exit_code"]=0
    nothing
end

function export_reference_prepare(root,reference,label,outdir,result)
    execution=strip(mgit(root,"rev-parse","HEAD"));result["execution_commit"]=execution
    mrequire(isempty(strip(mgit(root,"status","--porcelain","--untracked-files=all"))),"Export tooling execution tree must be clean")
    paths=["benchmarks/soc-core-memory-v1/$name" for name in ("export_reference_operators.jl","measure.jl","memory.jl")]
    for path in paths
        mrequire(read(joinpath(root,path))==read(`git -C $root show $(execution*":"*path)`),"Exporter helper is not the exact committed source")
    end
    result["tooling_sha256"]=Dict(path=>msha(joinpath(root,path)) for path in paths)
    sources=authenticate(root,reference,"REF-$label")
    result["reference_code_commit"]=MEASUREMENT_BASE
    result["reference_source_sha256"]=sources["reference_implementation"]["files"]
    result["included_entry_modules"]=load_reference_modules(reference)
    Base.invokelatest(export_reference_loaded,root,reference,label,outdir,result,sources)
    mrequire(strip(mgit(root,"rev-parse","HEAD"))==execution && isempty(strip(mgit(root,"status","--porcelain","--untracked-files=all"))),"Export tooling changed during execution")
end

function export_reference_main(args)
    args==["--help"] && (println("export_reference_operators.jl ORIGINAL_ROOT DETACHED_REFERENCE_ROOT B0|K4 NEW_OUTDIR");return 0)
    length(args)==4 || (println(stderr,"Expected ROOT CODE_ROOT B0|K4 NEW_OUTDIR");return 9)
    root,reference,label,outdir=args;root=realpath(root);reference=realpath(reference);outdir=normpath(abspath(outdir))
    label in ("B0","K4") || error("Only the two completed REF endpoint cases are supported")
    startswith(outdir,joinpath(root,".work/phase9a")*"/") || error("Export requires an ignored Phase9A child path")
    ispath(outdir) && error("Existing export directory is never reused");mkpath(outdir)
    realpath(outdir)==outdir || error("Export path alias is forbidden")
    result=Dict{String,Any}("schema_version"=>1,"phase"=>"9A","action"=>"EXPORT-REF-OPERATORS","label"=>label,"run_id"=>basename(outdir),
        "overall_status"=>"RUNNING","exit_code"=>9,"started_utc"=>string(now(UTC)),"performance_scope"=>"NOT_A_PERFORMANCE_SUITE",
        "performance_sample_count"=>0,"warmups"=>0,"scf"=>"NOT_RUN","eigensolve"=>"NOT_RUN","occupation_solve"=>"NOT_RUN",
        "reason_for_supplement"=>"Completed REF performance records did not export P/D/labels; provide old-constructor data for the required explicit candidate comparison without changing or rerunning those samples")
    output=joinpath(outdir,"operator-export.json")
    # Publish a current non-PASS before loading package-bearing helper definitions.
    write(output,JSON3.write(result)*"\n")
    try
        Base.include(Main,joinpath(root,"benchmarks/soc-core-memory-v1/measure.jl"))
        Base.invokelatest(export_reference_prepare,root,reference,label,outdir,result)
    catch err
        result["overall_status"]="FAIL";result["exit_code"]=9;result["reason"]=sprint(showerror,err)
        result["failure_status"]=occursin("BLOCKED:",result["reason"]) ? "BLOCKED" : "FAIL"
        showerror(stderr,err,catch_backtrace());println(stderr)
    end
    result["finished_utc"]=string(now(UTC));result["peak_rss_bytes"]=Sys.maxrss()
    try
        if isdefined(Main,:mwrite)
            Base.invokelatest(mwrite,output,result;root,reference)
        else
            write(output,JSON3.write(result)*"\n")
        end
    catch err
        println(stderr,"PERSISTENCE FAILURE: ",sprint(showerror,err));return 9
    end
    println(JSON3.write((;run_id=result["run_id"],label,overall_status=result["overall_status"],exit_code=result["exit_code"])))
    result["exit_code"]
end
function safe_export_reference(args)
    try
        export_reference_main(args)
    catch err
        println(stderr,"EXPORT WRAPPER FAILURE: ",sprint(showerror,err));return 9
    end
end
abspath(PROGRAM_FILE)==(@__FILE__) && exit(safe_export_reference(ARGS))
