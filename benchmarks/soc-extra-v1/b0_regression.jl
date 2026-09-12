#!/usr/bin/env julia
# Authenticated saved endpoint arithmetic only; no context, operator or solver.
# Reuse the established array comparison and historical receipt reader.
include("../soc-core-memory-v1/endpoint_compare.jl")
const EXTRA_B0_BASE="7630172808773a3d4ac2da825c27fe43a8705fb8"
const EXTRA_B0_REFERENCE_E="281c53525a70cf21c36973956d5303d3201a73eb"

function extra_b0_frozen(root,relative)
    path=confined(root,relative)
    require_value(read(path)==read(`git -C $root show $(EXTRA_B0_BASE*":"*relative)`),"Frozen completed B0 evidence changed: $relative")
    readjson(path)
end
function extra_b0_public(root,entry)
    value=extra_b0_frozen(root,entry["path"])
    path=confined(root,entry["path"])
    require_value(digest(path)==entry["sha256"] && filesize(path)==entry["bytes"],"Completed public projection differs")
    value
end
function extra_b0_history(root)
    manifest=extra_b0_frozen(root,"results/soc-core-memory/completion/endpoints.json")
    require_value(manifest["endpoint_execution_commit"]==EXTRA_B0_REFERENCE_E,"Wrong completed B0 execution")
    workers=Dict{String,Any}();paths=Dict{String,String}();raw_bindings=Dict{String,String}()
    for action in ("OPT-B0-SCF","OPT-B0-GAMMA")
        slot=manifest["slots"][action]
        require_value(slot["status"]=="PASS" && slot["native_exit_code"]==slot["recorder_exit_code"]==0 && slot["native_process_started"],"Historical completed slot failed")
        published=extra_b0_public(root,slot["worker"])
        extra_b0_public(root,slot["outer"])
        outerpath=joinpath(root,".work/phase9a/endpoints",slot["run_id"],"receipt.json")
        require_value(digest(outerpath)==slot["outer"]["raw_sha256"] && filesize(outerpath)==slot["outer"]["raw_bytes"],"Historical raw outer differs from its frozen public binding")
        worker,workerpath=endpoint_worker(root,outerpath,action,EXTRA_B0_REFERENCE_E)
        require_value(digest(workerpath)==slot["worker"]["raw_sha256"] && filesize(workerpath)==slot["worker"]["raw_bytes"],"Historical raw worker differs from its frozen public binding")
        for key in ("final","spectrum")
            haskey(worker,key) && require_value(worker[key]==published[key],"Historical numerical projection changed: $key")
        end
        for (name,entry) in slot["process"]
            extra_b0_public(root,entry)
            path=joinpath(dirname(outerpath),name)
            require_value(digest(path)==entry["raw_sha256"] && filesize(path)==entry["raw_bytes"],"Historical native/resource raw bytes differ")
            raw_bindings[relpath(path,root)]=digest(path)
        end
        workers[action]=worker;paths[action]=workerpath
        raw_bindings[relpath(outerpath,root)]=digest(outerpath);raw_bindings[relpath(workerpath,root)]=digest(workerpath)
    end
    scf=workers["OPT-B0-SCF"];gamma=workers["OPT-B0-GAMMA"]
    cp=joinpath(dirname(paths["OPT-B0-SCF"]),"final.bin")
    density=extra_b0_frozen(root,"results/soc-core-memory/completion/density-comparison.json")
    cpentry=density["resume_authentication"]["endpoint_bindings"]["OPT-B0-SCF"]["checkpoint"]
    require_value(confined(root,cpentry["path"])==cp && filesize(cp)==cpentry["bytes"] && digest(cp)==cpentry["sha256"]==scf["checkpoint_sha256"],"Completed private checkpoint differs from authenticated continuation receipt")
    require_value(gamma["source_scf_run_id"]==scf["run_id"] && gamma["parent_result_sha256"]==digest(paths["OPT-B0-SCF"]) && gamma["parent_checkpoint_sha256"]==digest(cp),"Historical own-density Gamma binding differs")
    raw_bindings[relpath(cp,root)]=digest(cp)
    (;scf,gamma,checkpoint=cp,raw_bindings,manifest_sha256=digest(joinpath(root,"results/soc-core-memory/completion/endpoints.json")))
end
function extra_b0_new(root,scf_outer,gamma_outer,execution,python)
    # No action launch: the current extra recorder's complete saved-run verifier
    # checks contracts, native/resource exits, closure, dispatch and checkpoint.
    code="""
import importlib.util,json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
spec=importlib.util.spec_from_file_location('extra_saved_verifier',root/'benchmarks/soc-extra-v1/run.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
values={}
for action,argument in [('X-B0-SCF',sys.argv[2]),('X-B0-GAMMA',sys.argv[3])]:
    path=Path(argument).resolve()
    if path.name!='result.json':raise ValueError('Expected current outer result.json')
    rec,worker,d=m.checked_run(root,path.parent,action,sys.argv[4])
    values[action]={'outer_sha256':m.sha(path),'worker_path':str(d/'result.json'),'worker_sha256':m.sha(d/'result.json')}
print(json.dumps(values,allow_nan=False))
"""
    verified=JSON3.read(read(Cmd([python,"-B","-c",code,root,abspath(scf_outer),abspath(gamma_outer),execution]),String),Dict{String,Any})
    s=verified["X-B0-SCF"];g=verified["X-B0-GAMMA"]
    scf=readjson(s["worker_path"]);gamma=readjson(g["worker_path"])
    cp=joinpath(dirname(s["worker_path"]),"final.bin")
    require_value(scf["extra_profile"]==gamma["extra_profile"]=="B0" && scf["contract_sha256"]==gamma["contract_sha256"],"New B0 contracts differ")
    require_value(gamma["source_scf_run_id"]==scf["run_id"] && gamma["parent_result_sha256"]==s["worker_sha256"] &&
        gamma["parent_checkpoint_sha256"]==digest(cp)==scf["checkpoint_sha256"] && gamma["density_source_sha256"]==scf["final"]["n_out_sha256"],"New Gamma not bound to its own final density")
    bindings=Dict(relpath(abspath(scf_outer),root)=>s["outer_sha256"],relpath(abspath(gamma_outer),root)=>g["outer_sha256"],
        relpath(s["worker_path"],root)=>s["worker_sha256"],relpath(g["worker_path"],root)=>g["worker_sha256"],relpath(cp,root)=>digest(cp))
    (;scf,gamma,checkpoint=cp,verified,raw_bindings=bindings)
end
function extra_b0_gamma(root,old,new,python)
    code="""
import json,sys
sys.path.insert(0,sys.argv[1]+'/scripts')
from si_soc_comparison import analyze_gamma
values=json.load(sys.stdin)
print(json.dumps([analyze_gamma(v) for v in values],allow_nan=False))
"""
    raw=JSON3.write([old,new])
    JSON3.read(read(pipeline(Cmd([python,"-B","-c",code,root]);stdin=IOBuffer(raw)),String),Vector{Any})
end
function extra_b0_metrics(old,new,old_n,new_n,old_gamma,new_gamma,contract)
    limit=contract["comparison"]
    density=merge(array_comparison(old_n,new_n,"completed9A/n_out",limit["B0_density_norm_ratio"]),
        (;reference_source_sha256=old["checkpoint_sha256"],reference_n_out_sha256=old["final"]["n_out_sha256"],
          candidate_n_out_sha256=new["final"]["n_out_sha256"]))
    od,nd=old["final"]["diagnostics"],new["final"]["diagnostics"]
    energy=map(("internal_energy_ha","free_energy_ha","entropy_energy_ha")) do key
        a,b=od[key],nd[key];require_value(a isa Real && b isa Real && all(isfinite,(a,b)),"Invalid saved energy")
        lim=key=="entropy_energy_ha" ? nothing : limit["B0_E_F_abs_ha"]
        (;field=key,reference=a,candidate=b,difference=b-a,unit="Ha/cell",limit=lim,
          status=isnothing(lim) ? "DIAGNOSTIC_ONLY" : abs(b-a)<=lim ? "PASS" : "FAIL")
    end
    ot,nt=od["energy_terms_ha"],nd["energy_terms_ha"]
    require_value(Set(keys(ot))==Set(keys(nt)) && length(ot)==7,"Seven native terms required")
    require_value(all(v->v isa Real && !(v isa Bool) && isfinite(v),vcat(collect(values(ot)),collect(values(nt)))),"Seven terms must be finite")
    terms=[(;term=k,reference=ot[k],candidate=nt[k],difference=nt[k]-ot[k],unit="Ha/cell") for k in sort(collect(keys(ot)))]
    a,b=Float64.(old_gamma["values_ha"]),Float64.(new_gamma["values_ha"])
    require_value(length(a)==length(b)==24 && all(isfinite,a) && all(isfinite,b),"All24 finite raw Gamma eigenvalues required")
    differences=b-a;split=new_gamma["delta_so_ev"]-old_gamma["delta_so_ev"]
    gamma=(;reference_split_ev=old_gamma["delta_so_ev"],candidate_split_ev=new_gamma["delta_so_ev"],difference_ev=split,
        split_limit_ev=limit["B0_split_abs_ev"],raw_differences_ha=differences,raw_max_abs_ha=maximum(abs,differences),
        raw_rms_ha=norm(differences)/sqrt(24),raw_limit_ha=limit["B0_gamma24_raw_max_ha"],
        status=abs(split)<=limit["B0_split_abs_ev"] && maximum(abs,differences)<=limit["B0_gamma24_raw_max_ha"] ? "PASS" : "FAIL")
    status=density.status==gamma.status=="PASS" && all(r.status in ("PASS","DIAGNOSTIC_ONLY") for r in energy) ? "PASS" : "FAIL"
    (;status,n_out=density,energy,energy_terms=terms,gamma)
end
function extra_b0_main(args)
    length(args)==4 || error("b0_regression.jl ROOT NEW_SCF_OUTER_RESULT NEW_GAMMA_OUTER_RESULT NEW_OUTPUT")
    root=realpath(args[1]);output=abspath(args[4]);require_value(!ispath(output),"Existing B0 regression record is never overwritten")
    require_value(startswith(output,joinpath(root,".work/phase9a-extra")*"/"),"B0 regression output must be a new extra record")
    execution=strip(read(`git -C $root rev-parse HEAD`,String))
    result=Dict{String,Any}("schema_version"=>1,"execution_commit"=>execution,"status"=>"FAIL","exit_code"=>9,
        "scf_receipt_sha256"=>nothing,"gamma_receipt_sha256"=>nothing,"scope"=>"Saved B0 endpoint arithmetic; no new electronic-structure task")
    try
        python=get(ENV,"SOC_CORE_PYTHON","");require_value(isabspath(python) && isfile(python),"Explicit existing SOC_CORE_PYTHON required")
        source_paths=["benchmarks/soc-extra-v1/b0_regression.jl","benchmarks/soc-extra-v1/run.py","benchmarks/soc-extra-v1/control.py",
            "benchmarks/soc-extra-v1/plan.json","benchmarks/soc-extra-v1/sources.json","benchmarks/soc-extra-v1/B0.json",
            "benchmarks/soc-core-memory-v1/endpoint_compare.jl","benchmarks/soc-core-memory-v1/compare.jl",
            "scripts/si_soc_comparison.py","scripts/parse_qe_soc.py","scripts/workbench_environment.jl"]
        identity=arithmetic_source_identity(root,source_paths);result["arithmetic_sources"]=identity
        env=WorkbenchEnvironment.environment_identity(root,(DFTK,PseudoPotentialIO));require_value(env.status=="PASS","Frozen arithmetic environment mismatch")
        result["environment"]=WorkbenchEnvironment.public_data(env,root)
        old=extra_b0_history(root);new=extra_b0_new(root,args[2],args[3],execution,python)
        original=deserialize(old.checkpoint);candidate=deserialize(new.checkpoint)
        for (value,worker) in ((original,old.scf),(candidate,new.scf))
            require_value(value.n_out isa Vector{Float64} && length(value.n_out)==48^3 && all(isfinite,value.n_out),"Invalid saved n_out")
            require_value(bytes2hex(sha256(reinterpret(UInt8,value.n_out)))==worker["final"]["n_out_sha256"],"Saved density and result identity differ")
        end
        oldpoint=only(old.gamma["spectrum"]["kpoints"]);newpoint=only(new.gamma["spectrum"]["kpoints"])
        require_value(oldpoint["coordinate_fractional"]==newpoint["coordinate_fractional"]==[0.,0.,0.],"Only same-location Gamma comparison allowed")
        gammas=extra_b0_gamma(root,oldpoint["eigenvalues_ha"],newpoint["eigenvalues_ha"],python)
        metrics=extra_b0_metrics(old.scf,new.scf,original.n_out,candidate.n_out,gammas[1],gammas[2],readjson(joinpath(root,"benchmarks/soc-extra-v1/plan.json")))
        result["metrics"]=metrics
        result["closure_status"]=new.scf["final"]["closure_status"]
        result["dispatch_status"]=Dict("scf"=>new.scf["runtime_dispatch_status"],"gamma"=>new.gamma["runtime_dispatch_status"])
        result["runtime_closed"]=Dict("scf"=>new.scf["runtime_closed"],"gamma"=>new.gamma["runtime_closed"])
        occupations=Float64.(newpoint["occupations"])
        require_value(length(occupations)==24 && all(f->isfinite(f)&&0<=f<=1,occupations),"Invalid Gamma occupation diagnostics")
        result["occupation_diagnostic"]=(;minimum_window=min(occupations[3:8]...),threshold=0.99999999,
            status=minimum(occupations[3:8])>=0.99999999 ? "PASS" : "REVIEW_REQUIRED")
        result["manifold_assignment_status"]="MANIFOLD_ASSIGNMENT_REVIEW_REQUIRED";result["physical_convergence"]="NOT_ESTABLISHED"
        result["historical_reference"]=(;status="HISTORICAL_REUSED",execution_commit=EXTRA_B0_REFERENCE_E,
            snapshot_commit=EXTRA_B0_BASE,manifest_sha256=old.manifest_sha256,scf_run_id=old.scf["run_id"],gamma_run_id=old.gamma["run_id"])
        result["source_hashes"]=merge(old.raw_bindings,new.raw_bindings)
        for (p,h) in result["source_hashes"];require_value(digest(confined(root,p))==h,"Endpoint changed during arithmetic: $p");end
        require_value(arithmetic_source_identity(root,source_paths)==identity,"Arithmetic source changed")
        result["scf_receipt_sha256"]=new.verified["X-B0-SCF"]["outer_sha256"]
        result["gamma_receipt_sha256"]=new.verified["X-B0-GAMMA"]["outer_sha256"]
        result["status"]=metrics.status;result["exit_code"]=metrics.status=="PASS" ? 0 : 9
    catch error
        result["status"]="FAIL";result["exit_code"]=9;result["reason"]=sprint(showerror,error)
        showerror(stderr,error,catch_backtrace());println(stderr)
    end
    try
        bytes=JSON3.write(result)*"\n";JSON3.read(bytes)
        mkpath(dirname(output));write(output*".tmp",bytes);mv(output*".tmp",output)
    catch error
        println(stderr,"B0 regression persistence failed; gate is not PASS: ",sprint(showerror,error));return 9
    end
    println(JSON3.write((;status=result["status"],exit_code=result["exit_code"])));result["exit_code"]
end
abspath(PROGRAM_FILE)==(@__FILE__) && exit(extra_b0_main(ARGS))
