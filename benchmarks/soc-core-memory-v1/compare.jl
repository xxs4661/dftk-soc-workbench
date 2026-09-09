#!/usr/bin/env julia
# Arithmetic over authenticated saved arrays only. No operator or solver call.
using DFTK, PseudoPotentialIO, LinearAlgebra, Serialization, SHA, JSON3
include("../../scripts/workbench_environment.jl")

digest(path)=bytes2hex(sha256(read(path)))
readjson(path)=JSON3.read(read(path,String),Dict{String,Any})
require_value(ok,reason)=ok || error(reason)
function arithmetic_source_identity(root,paths)
    require_value(isempty(strip(read(`git -C $root status --porcelain`,String))),"Arithmetic checkout must be clean")
    head=strip(read(`git -C $root rev-parse HEAD`,String))
    for path in paths
        require_value(read(joinpath(root,path))==read(`git -C $root show $(head*":"*path)`),"Arithmetic source not committed: $path")
    end
    for name in ("README.md","plan.json","sources.json","contract.json")
        path=joinpath("benchmarks/soc-core-memory-v1",name)
        require_value(read(joinpath(root,path))==read(`git -C $root show $("e4f16a51a0304f5e70f5ae038563d6760409c2c4:"*path)`),"Frozen arithmetic contract changed")
    end
    (;execution_commit=head,source_sha256=Dict(path=>digest(joinpath(root,path)) for path in paths))
end
function confined(root,relative)
    require_value(relative isa String && !isabspath(relative) && !(".." in splitpath(relative)),"Unconfined evidence path")
    path=joinpath(root,relative)
    require_value(isfile(path) && !islink(path) && realpath(path)==path,"Missing or aliased evidence file")
    path
end
function receipt(root,entry)
    path=confined(root,entry["path"])
    require_value(digest(path)==entry["sha256"],"Evidence receipt bytes differ")
    readjson(path),dirname(path)
end
function payload(directory,descriptor)
    require_value(basename(descriptor["path"])==descriptor["path"],"Unconfined canonical payload")
    path=joinpath(directory,descriptor["path"])
    require_value(!islink(path) && filesize(path)==descriptor["bytes"] && digest(path)==descriptor["sha256"],"Canonical array bytes differ")
    deserialize(path)  # Hash and byte count have passed before native reading.
end
function array_comparison(a,b,label,limit)
    require_value(a isa AbstractArray{<:Number} && b isa AbstractArray{<:Number},"Expected numeric arrays: $label")
    require_value(size(a)==size(b) && eltype(a)==eltype(b) && !isempty(a),"Array layout differs: $label")
    require_value(all(isfinite,a) && all(isfinite,b),"Nonfinite saved output: $label")
    na,nb=norm(a),norm(b);difference=a-b;absolute=norm(difference)
    relative=absolute/max(na,nb,1)
    require_value(all(isfinite,(na,nb,absolute,relative,maximum(abs,difference))),"Nonfinite derived comparison: $label")
    (;kind="array",label,shape=collect(size(a)),element_type=string(eltype(a)),
      reference_norm=na,candidate_norm=nb,absolute_L2=absolute,relative,
      max_abs=maximum(abs,difference),bitwise_equal=isequal(a,b),limit,
      status=relative<=limit ? "PASS" : "FAIL",evidence_level="RUNNER_REPORTED_PRIVATE_ARRAY_COMPARISON")
end
function compare_values!(rows,a,b,label,contract)
    if a isa AbstractArray{<:Number}
        key=last(split(label,'/')) in ("R","n","m") ? "density_R_n_m_relative" : "operator_relative"
        push!(rows,array_comparison(a,b,label,contract["accuracy"][key]))
    elseif a isa Real
        require_value(typeof(a)===typeof(b) && !(a isa Bool) && isfinite(a) && isfinite(b),"Invalid saved scalar: $label")
        delta=b-a
        require_value(isfinite(delta),"Nonfinite derived scalar: $label")
        dimensionless=endswith(label,"/entropy_dimensionless")
        # Identical immutable f/weights produce this deterministic derived scalar.
        # This exact diagnostic does not reinterpret the Ha energy contract.
        limit=dimensionless ? 0.0 : contract["accuracy"]["energy_each_and_total_abs_ha"]
        unit=dimensionless ? "dimensionless" : "Ha/cell"
        push!(rows,(;kind="scalar",label,reference=Float64(a),candidate=Float64(b),difference=Float64(delta),
            limit,unit,status=abs(delta)<=limit ? "PASS" : "FAIL",evidence_level="PUBLIC_ARITHMETIC"))
    elseif a isa NamedTuple || a isa AbstractDict
        require_value(typeof(a)===typeof(b) && Set(keys(a))==Set(keys(b)),"Numerical output fields differ: $label")
        for key in sort(collect(keys(a));by=string)
            compare_values!(rows,a[key],b[key],label*"/"*string(key),contract)
        end
    else
        error("Unsupported saved numerical value: $label")
    end
end
function density_integrals(a,b,label,dvol,contract)
    na=dvol*sum(a.n);nb=dvol*sum(b.n)
    require_value(all(isfinite,(na,nb,dvol)),"Nonfinite density integral")
    limit=contract["accuracy"]["valence_electron_abs"]
    (;label,reference_electrons=na,candidate_electrons=nb,reference_error=na-8,candidate_error=nb-8,
      reference_m=dvol.*vec(sum(a.m;dims=2)),candidate_m=dvol.*vec(sum(b.m;dims=2)),
      electron_limit=limit,status=max(abs(na-8),abs(nb-8))<=limit ? "PASS" : "FAIL",
      evidence_level="RUNNER_REPORTED_PRIVATE_DENSITY_INTEGRAL")
end

function compare_pair(root,label,pair,execution,contract)
    reference,refdir=receipt(root,pair["reference"])
    candidate,coredir=receipt(root,pair["candidate"])
    for (record,suite) in ((reference,"REF-"*label),(candidate,"CORE-"*label))
        require_value(record["suite"]==suite && record["overall_status"]=="PASS" && record["process_exit_code"]==record["exit_code"]==0,"Static suite did not pass")
    end
    require_value(reference["execution_commit"]=="bbe9aa7755f052900e6e9c4618252a410e1cc8f0" && candidate["execution_commit"]==execution,"Static execution commit mismatch")
    workers=map(((reference,refdir),(candidate,coredir))) do (record,dir)
        path=joinpath(dir,"worker-result.json")
        require_value(digest(path)==record["worker_result_sha256"],"Static worker bytes changed")
        worker=readjson(path)
        require_value(worker["overall_status"]=="PASS" && worker["measurement_status"]=="COMPLETE" && worker["exit_code"]==0,"Incomplete static worker")
        worker
    end
    old,new=workers
    for field in ("checkpoint_sha256","physical_payload_sha256","case_sha256","n_in_sha256","n_out_sha256","target_states","k_count")
        require_value(old["input"][field]==new["input"][field],"Corresponding inputs differ: $field")
    end
    require_value(old["canonical_inputs"]["sha256"]==new["canonical_inputs"]["sha256"],"Canonical input bytes differ")
    # Verify actual files as well as the reported common hash.
    payload(refdir,old["canonical_inputs"]);payload(coredir,new["canonical_inputs"])
    expected=Set(vcat(["$(op)_$n" for op in ("FR","component","full_H") for n in (1,24,30)],
        ["density","nonlocal","energy","pipeline"]))
    require_value(Set(keys(old["outputs"]))==Set(keys(new["outputs"]))==expected,"Missing comparison operation")
    case=readjson(joinpath(root,label=="B0" ? "benchmarks/si-soc-splitting-v1/case.json" : "benchmarks/si-soc-sensitivity-v1/K4/case.json"))
    lattice=reduce(hcat,Float64.(v) for v in case["geometry"]["lattice_vectors_bohr"])
    volume=abs(det(lattice));dvol=volume/prod(case["fft_size"])
    rows=Any[];integrals=Any[]
    for operation in sort(collect(expected))
        a=payload(refdir,old["outputs"][operation]);b=payload(coredir,new["outputs"][operation])
        compare_values!(rows,a,b,operation,contract)
        operation=="density" && push!(integrals,density_integrals(a,b,operation,dvol,contract))
        operation=="energy" && push!(integrals,density_integrals(a,b,operation,dvol,contract))
        operation=="pipeline" && push!(integrals,density_integrals(a.density,b.density,operation,dvol,contract))
    end
    exported,exportdir=receipt(root,pair["reference_operators"])
    require_value(exported["label"]==label && exported["overall_status"]=="PASS" && exported["exit_code"]==0 && exported["reference_code_commit"]==contract["base"],"Unbound old projector source")
    require_value(exported["performance_sample_count"]==0,"Supplement must not replace the five measured samples")
    require_value(exported["reference_suite_receipt"]==pair["reference"],"Supplement belongs to another reference suite")
    a=payload(exportdir,exported["operators"]);b=payload(coredir,new["canonical_operators"])
    nk=label=="B0" ? 8 : 64
    require_value(length(a)==length(b)==nk,"Projector k count differs")
    for i in 1:nk
        for key in (:coordinate,:weight,:G,:labels)
            require_value(isequal(a[i][key],b[i][key]),"Projector k/G/atom/channel label differs at k=$i field=$key")
        end
        for key in (:P,:D)
            push!(rows,array_comparison(a[i][key],b[i][key],"operators/$i/$key",contract["accuracy"]["operator_relative"]))
        end
    end
    status=all(row.status=="PASS" for row in rows) && all(row.status=="PASS" for row in integrals) ? "PASS" : "FAIL"
    (;label,status,reference=pair["reference"],candidate=pair["candidate"],reference_operators=pair["reference_operators"],
      input_identity=old["input"]["physical_payload_sha256"],checkpoint_sha256=old["input"]["checkpoint_sha256"],
      volume_bohr3=volume,dvol,rows,density_integrals=integrals,
      input_binding="Exact canonical input bytes; supplemental old-projector construction is not a performance rerun")
end

function main(args)
    length(args)==3 || error("compare.jl ROOT REQUEST_JSON NEW_OUTPUT_JSON")
    root=realpath(args[1]);request=readjson(args[2]);output=abspath(args[3])
    require_value(!ispath(output),"Comparison output exists")
    execution=strip(read(`git -C $root rev-parse HEAD`,String))
    result=Dict{String,Any}("schema_version"=>1,"phase"=>"9A","execution_commit"=>execution,
        "overall_status"=>"FAIL","exit_code"=>9,"pairs"=>Any[],"scope"=>"Saved-array arithmetic only; no operator, SCF, eigenvalue or occupation evaluation")
    try
        paths=["benchmarks/soc-core-memory-v1/compare.jl","scripts/workbench_environment.jl"]
        identity=arithmetic_source_identity(root,paths)
        result["arithmetic_sources"]=identity
        environment=WorkbenchEnvironment.environment_identity(root,(DFTK,PseudoPotentialIO))
        result["environment"]=WorkbenchEnvironment.public_data(environment,root)
        require_value(environment.status=="PASS","Arithmetic environment mismatch")
        require_value(request["execution_commit"]==execution && Set(keys(request["pairs"]))==Set(("B0","K4")),"Wrong comparison request")
        contract=readjson(joinpath(root,"benchmarks/soc-core-memory-v1/contract.json"))
        contract["base"]="c764311a5422b5c3cab5a7b78a02d420910c4e56" # Local binding only; frozen file never written.
        for label in ("B0","K4")
            push!(result["pairs"],compare_pair(root,label,request["pairs"][label],execution,contract))
        end
        require_value(arithmetic_source_identity(root,paths)==identity,"Arithmetic source changed")
        passed=all(pair.status=="PASS" for pair in result["pairs"])
        result["overall_status"]=passed ? "PASS" : "FAIL";result["exit_code"]=passed ? 0 : 9
    catch error
        result["reason"]=sprint(showerror,error)
        showerror(stderr,error,catch_backtrace());println(stderr)
    end
    mkpath(dirname(output));write(output*".tmp",JSON3.write(result)*"\n");mv(output*".tmp",output)
    println(JSON3.write((;overall_status=result["overall_status"],exit_code=result["exit_code"])))
    result["exit_code"]
end
abspath(PROGRAM_FILE)==(@__FILE__) && exit(main(ARGS))
