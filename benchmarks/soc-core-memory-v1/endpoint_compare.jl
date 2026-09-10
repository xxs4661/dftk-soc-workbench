#!/usr/bin/env julia
# Only authenticated endpoint-array arithmetic; no numerical operator/solver.
include("compare.jl")
function endpoint_resume_authorization(root,authorization,scf_outer,gamma_outer,execution)
    python=get(ENV,"SOC_CORE_PYTHON","")
    require_value(!isempty(python) && isabspath(python) && isfile(python),"Explicit SOC_CORE_PYTHON interpreter required")
    path=abspath(authorization)
    require_value(!islink(path) && realpath(path)==path,"Aliased continuation authorization")
    before=digest(path)
    command=Cmd([python,joinpath(root,"benchmarks/soc-core-memory-v1/resume/control.py"),"verify-endpoints",
        "--root",root,"--authorization",path,"--execution-commit",execution,
        "--scf",abspath(scf_outer),"--gamma",abspath(gamma_outer)])
    verified=JSON3.read(read(command,String),Dict{String,Any})
    require_value(verified["status"]=="PASS" && verified["endpoint_execution_commit"]==execution &&
        verified["authorization_sha256"]==before && digest(path)==before,"Continuation endpoint authentication differs")
    verified
end
function endpoint_worker(root,outerpath,action,execution)
    path=realpath(outerpath)
    require_value(startswith(path,joinpath(root,".work/phase9a/endpoints")*"/"),"Endpoint outside this phase")
    outer=readjson(path)
    require_value(outer["action"]==action && outer["execution_commit"]==execution && outer["execution_status"]=="PASS" && outer["exit_code"]==0,"Endpoint did not pass")
    require_value(outer["run_id"]==basename(dirname(path)) && outer["worker_directory"]==outer["run_id"]*"-dftk","Endpoint directory identity differs")
    resource=readjson(joinpath(dirname(path),"resource.json"));native=readjson(joinpath(dirname(path),"process-exit.json"))
    require_value(resource==outer["resource"] && resource["status"]==resource["owned_process_cleanup_status"]=="PASS" &&
        native["exit_code"]==resource["native_exit_code"]==outer["worker_exit_code"]==0 && native["interrupted"]==false &&
        0<resource["peak_aggregate_rss_bytes"]<8*1024^3 && resource["nonempty_samples"]>0,"Endpoint process/resource failed")
    workerpath=joinpath(dirname(path),outer["worker_directory"],"result.json")
    require_value(realpath(workerpath)==workerpath && !islink(workerpath),"Aliased endpoint worker")
    require_value(digest(workerpath)==outer["worker_result_sha256"],"Endpoint worker bytes changed")
    worker=readjson(workerpath)
    require_value(worker["action"]==action && worker["backend"]=="soc-core" && worker["execution_commit"]==execution && worker["execution_status"]=="PASS" && worker["exit_code"]==0,"Wrong endpoint worker")
    require_value(worker["runtime_closed"] && worker["runtime_dispatch_status"]=="PASS","Missing actual core dispatch/close")
    worker,workerpath
end
function endpoint_main(args)
    length(args) in (4,5) || error("endpoint_compare.jl ROOT SCF_OUTER_JSON GAMMA_OUTER_JSON NEW_OUTPUT_JSON [AUTHORIZATION_JSON]")
    root=realpath(args[1]);output=abspath(args[4]);require_value(!ispath(output),"Endpoint comparison exists")
    execution=strip(read(`git -C $root rev-parse HEAD`,String))
    result=Dict{String,Any}("schema_version"=>1,"phase"=>"9A","execution_commit"=>execution,"overall_status"=>"FAIL","exit_code"=>9)
    try
        paths=["benchmarks/soc-core-memory-v1/endpoint_compare.jl","benchmarks/soc-core-memory-v1/compare.jl","scripts/workbench_environment.jl"]
        if length(args)==5
            append!(paths,["benchmarks/soc-core-memory-v1/resume/control.py","benchmarks/soc-core-memory-v1/resume/plan.json"])
        end
        identity=arithmetic_source_identity(root,paths);result["arithmetic_sources"]=identity
        if length(args)==5
            result["resume_authentication"]=endpoint_resume_authorization(root,args[5],args[2],args[3],execution)
        end
        environment=WorkbenchEnvironment.environment_identity(root,(DFTK,PseudoPotentialIO))
        require_value(environment.status=="PASS","Endpoint arithmetic environment mismatch")
        result["environment"]=WorkbenchEnvironment.public_data(environment,root)
        scf,scfpath=endpoint_worker(root,args[2],"OPT-B0-SCF",execution)
        gamma,gammapath=endpoint_worker(root,args[3],"OPT-B0-GAMMA",execution)
        require_value(gamma["source_scf_run_id"]==scf["run_id"] && gamma["parent_result_sha256"]==digest(scfpath),"Gamma parent mismatch")
        sources=readjson(joinpath(root,"benchmarks/soc-core-memory-v1/sources.json"))
        oldspec=sources["historical_endpoints"]["B0"]
        oldpath=joinpath(root,oldspec["directory"],"final.bin")
        oldresultpath=joinpath(root,oldspec["directory"],"result.json")
        newpath=joinpath(dirname(scfpath),"final.bin")
        require_value(digest(oldpath)==oldspec["checkpoint_sha256"] && filesize(oldpath)==oldspec["checkpoint_bytes"] && digest(oldresultpath)==oldspec["raw_result_sha256"],"Historical endpoint changed")
        require_value(digest(newpath)==scf["checkpoint_sha256"]==gamma["parent_checkpoint_sha256"],"New checkpoint changed")
        old=deserialize(oldpath);new=deserialize(newpath)
        for (data,record) in ((old,readjson(oldresultpath)),(new,scf))
            require_value(data.n_out isa Vector{Float64} && length(data.n_out)==48^3 && all(isfinite,data.n_out),"Invalid endpoint density")
            require_value(bytes2hex(sha256(reinterpret(UInt8,data.n_out)))==record["final"]["n_out_sha256"],"Density hash mismatch")
        end
        accuracy=readjson(joinpath(root,"benchmarks/soc-core-memory-v1/contract.json"))["endpoint"]
        delta=norm(new.n_out-old.n_out);relative=delta/max(norm(new.n_out),norm(old.n_out),1)
        require_value(all(isfinite,(delta,relative)),"Nonfinite endpoint difference")
        result["n_out"]=(;reference_norm=norm(old.n_out),candidate_norm=norm(new.n_out),absolute_L2=delta,relative,
            reference_sha256=readjson(oldresultpath)["final"]["n_out_sha256"],candidate_sha256=scf["final"]["n_out_sha256"],
            limit=accuracy["n_out_relative_L2"],status=relative<=accuracy["n_out_relative_L2"] ? "PASS" : "FAIL",
            evidence_level="RUNNER_REPORTED_PRIVATE_ENDPOINT_ARRAY_COMPARISON")
        result["sources"]=(;historical_checkpoint_sha256=oldspec["checkpoint_sha256"],historical_status="HISTORICAL_REUSED",historical_execution_commit=oldspec["execution_commit"],
            new_checkpoint_sha256=scf["checkpoint_sha256"],new_scf_run_id=scf["run_id"],new_gamma_run_id=gamma["run_id"],
            scf_result_sha256=digest(scfpath),gamma_result_sha256=digest(gammapath))
        require_value(arithmetic_source_identity(root,paths)==identity,"Endpoint arithmetic source changed")
        if length(args)==5
            require_value(digest(abspath(args[5]))==result["resume_authentication"]["authorization_sha256"],"Continuation authorization changed during arithmetic")
        end
        passed=result["n_out"].status=="PASS"
        result["overall_status"]=passed ? "PASS" : "FAIL";result["exit_code"]=passed ? 0 : 9
    catch err
        result["reason"]=sprint(showerror,err);showerror(stderr,err,catch_backtrace());println(stderr)
    end
    mkpath(dirname(output));write(output*".tmp",JSON3.write(result)*"\n");mv(output*".tmp",output)
    println(JSON3.write((;overall_status=result["overall_status"],exit_code=result["exit_code"])))
    result["exit_code"]
end
abspath(PROGRAM_FILE)==(@__FILE__) && exit(endpoint_main(ARGS))
