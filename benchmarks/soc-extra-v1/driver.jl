# Explicit experiment glue only. The shared Si path owns all numerical execution.
const SI_EXTRA_BASE="7630172808773a3d4ac2da825c27fe43a8705fb8"
const SI_EXTRA_DIR=joinpath(PHASE6C_ROOT,"benchmarks/soc-extra-v1")
function si_extra_authorization(path,profile;action=nothing,outdir=nothing)
    isnothing(path) && error("Extra execution contract required")
    python=get(ENV,"SOC_CORE_PYTHON","");isfile(python) || error("Explicit recorder Python required")
    execution=strip(read(`git -C $PHASE6C_ROOT rev-parse HEAD`,String))
    args=[python,"-B",joinpath(SI_EXTRA_DIR,"control.py"),"verify",PHASE6C_ROOT,path,execution,profile]
    isnothing(action) || push!(args,action)
    auth=JSON3.read(read(Cmd(args),String),Dict{String,Any})
    auth["contract_sha256"]==filehash(path) || error("Extra contract changed during read")
    if !isnothing(action)
        get(ENV,"SOC_EXTRA_WORKER_DIRECTORY","")==basename(outdir) || error("Extra worker directory differs from recorder")
        get(ENV,"SOC_EXTRA_RUN_ID","")==basename(dirname(outdir)) || error("Extra worker run identity differs")
    end
    auth
end
function si_extra_case(profile)
    profile in ("B0","K6") || error("Unregistered extra case")
    case=si_json(joinpath(SI_EXTRA_DIR,profile*".json"))
    SOC.validate_soc_settings(case["settings"];case_contract=case)
    case
end
function si_extra_check_sources(auth)
    all(filehash(joinpath(PHASE6C_ROOT,p))==h for (p,h) in auth["executed_source_sha256"]) || error("Extra source changed")
    true
end
function si_extra_result_binding!(result,auth,profile)
    result["contract_sha256"]=auth["contract_sha256"]
    result["case_sha256"]=auth["case_sha256"]
    result["executed_source_sha256"]=auth["executed_source_sha256"]
    result["temperature_ha"]=0.001
    result["core_selection"]=auth["core_selection"]
    result["original_9A_status"]="COMPLETED_UNCHANGED"
end
function si_extra_grid(ctx,case;gamma=false)
    geo=si_geometry(ctx);b=ctx.basis;profile=case["extra_profile"]
    expected_points=gamma ? [Dict("coordinate_fractional"=>[0.,0.,0.],"weight_spatial"=>1.)] : case["kpoints"]
    length(geo.rows)==length(expected_points) || error("Extra k count mismatch")
    for (row,w,expected) in zip(geo.rows,b.kweights,expected_points)
        all(abs.(row.coordinate_fractional.-expected["coordinate_fractional"]).<=1e-14) && w==expected["weight_spatial"] || error("Extra actual k/weight mismatch")
    end
    if profile=="K6" && length(geo.rows)>1
        length(geo.rows)==216 && sum(r.ng for r in geo.rows)==457287 && maximum(r.ng for r in geo.rows)==2138 || error("Extra K6 actual geometry differs from independent prediction")
    end
    (;status="PASS",geo...,nyquist="Original component-extrema and kinetic-cutoff checks unchanged",
      resource_policy="Explicit extra engineering admission and sampled7/8GiB monitor; old si_grid budget remains unchanged")
end
function si_extra_safe_boundary(outdir,event)
    Sys.maxrss()<8*1024^3 || error("RESOURCE_LIMIT: native sampled high-water RSS reached8GiB")
    path=get(ENV,"SOC_EXTRA_STOP_FILE","")
    !isempty(path) && isfile(path) && error("RESOURCE_LIMIT: recorder requested stop at $event")
    nothing
end
function si_extra_parent(receipt,case,auth,parent)
    profile=case["extra_profile"]
    receipt["schema_version"]===1 && receipt["phase"]=="9A-extra" && receipt["extra_profile"]==profile &&
        receipt["case"]==case["case"] && receipt["action"]=="X-$profile-SCF" || error("BLOCKED_PARENT: extra SCF identity differs")
    receipt["execution_status"]=="PASS" && receipt["exit_code"]===0 && receipt["runtime_closed"]===true &&
        receipt["runtime_dispatch_status"]=="PASS" || error("BLOCKED_PARENT: extra SCF did not finish")
    for key in ("execution_commit","case_sha256","contract_sha256","executed_source_sha256")
        receipt[key]==auth[key] || error("BLOCKED_PARENT: extra $key differs")
    end
    receipt["run_id"]==basename(parent) && receipt["input"]["sha256"]==case["pseudo"]["sha256"] || error("BLOCKED_PARENT: input/run differs")
    receipt["final"]["closure_status"]=="PASS" && receipt["final"]["diagnostics"]["target_states"]==24 || error("BLOCKED_PARENT: missing closure or24 targets")
    b=receipt["grid"]["basis"]
    b["n_electrons"]==8 && b["fft_grid"]==case["fft_size"] && b["ecut_ha"]==30 || error("BLOCKED_PARENT: geometry differs")
    length(b["kpoints"])==length(case["kpoints"]) || error("BLOCKED_PARENT: k count differs")
    all(p["coordinate_fractional"]==q["coordinate_fractional"] && p["weight_spatial"]==q["weight_spatial"] for (p,q) in zip(b["kpoints"],case["kpoints"])) || error("BLOCKED_PARENT: k mapping differs")
    receipt
end

# Serialize to a counting sink without retaining bytes. This observes exact wire
# length; it neither replaces nor bypasses the active callback fingerprint.
mutable struct ExtraCountingIO <: IO
    bytes::Int
end
Base.isopen(::ExtraCountingIO)=true
Base.iswritable(::ExtraCountingIO)=true
Base.position(io::ExtraCountingIO)=io.bytes
Base.write(io::ExtraCountingIO,x::UInt8)=(io.bytes+=1;1)
Base.unsafe_write(io::ExtraCountingIO,p::Ptr{UInt8},n::UInt)=(io.bytes+=Int(n);n)
const SI_EXTRA_BUFFER_SOURCES=Dict(
    "base/iobuffer.jl"=>"730edfc92371ac494a39bb27c91f07227bf43bd21006a327ecaadf6f4ea5976b",
    "base/array.jl"=>"156389c374e625ae52bee0bb53057f61728716ed34d7b63680486316ea171dca")
function si_extra_buffer_sources()
    VERSION==v"1.12.7" || error("Extra buffer inference requires the frozen Julia version")
    base=dirname(dirname(Base.find_source_file("array.jl")))
    actual=Dict(p=>filehash(joinpath(base,p)) for p in keys(SI_EXTRA_BUFFER_SOURCES))
    actual==SI_EXTRA_BUFFER_SOURCES || error("Extra buffer growth implementation changed")
    actual
end
function si_extra_serialized_length(x)
    io=ExtraCountingIO(0);serialize(io,x);io.bytes
end
function si_extra_observer(outdir,result,ctx)
    observed=Dict{String,Any}("records"=>Any[],"history_bytes"=>0,"history_map_count"=>0,
        "max_record_bytes"=>0,"serialization_payload_bytes"=>0,"serialization_buffer_capacity_bytes"=>0)
    si_append(joinpath(outdir,"lifecycle.jsonl"),(;event="owned_runtime_ready",peak_rss_bytes=Sys.maxrss(),
        runtime_summary=FI.runtime_summary(ctx),runtime_graph_bytes=Base.summarysize(ctx)))
    observed["outdir"]=outdir;observed["serialization_capacity_source_sha256"]=si_extra_buffer_sources();observed
end
function si_extra_compact_map(record)
    result=Dict(k=>v for (k,v) in record if k!="diagnostics")
    if haskey(record,"diagnostics")
        diag=record["diagnostics"]
        keep=(:target_states,:internal_energy_ha,:free_energy_ha,:entropy_energy_ha,:entropy_dimensionless,
            :energy_terms_ha,:real_electron_count,:orbital_electron_count,:pauli_density_relative_l2,
            :max_input_h_residual_ha,:max_gram_norm,:max_self_density_h_residual_ha,:max_self_rayleigh_residual_ha,
            :free_energy_arithmetic_error_ha,:potential_change_norm)
        result["diagnostics"]=(; (k=>getproperty(diag,k) for k in keep if hasproperty(diag,k))...)
    end
    result
end
function si_extra_observe_map!(o,record,raw,ctx)
    isnothing(raw) && return
    records=o["records"]
    (isempty(records) || last(records)!==record) && push!(records,record)
    o["max_record_bytes"]=max(o["max_record_bytes"],Base.summarysize(record))
    if length(records)<=2 || record["map_role"]=="closure"
        o["history_bytes"]=Base.summarysize(records);o["history_map_count"]=length(records)
        payload=SOC._runtime_callback_payload(record,raw)
        wire=si_extra_serialized_length(payload)
        # Frozen Julia1.12.7 Base.overallocation, monotone for append-only IOBuffer.
        capacity=max(32,Base.overallocation(wire))
        o["serialization_payload_bytes"]=max(o["serialization_payload_bytes"],wire)
        o["serialization_buffer_capacity_bytes"]=max(o["serialization_buffer_capacity_bytes"],capacity)
        si_append(joinpath(o["outdir"],"lifecycle.jsonl"),(;event="complete_map",map_index=record["map_index"],
            peak_rss_bytes=Sys.maxrss(),history_bytes=o["history_bytes"],history_map_count=o["history_map_count"],
            max_record_bytes=o["max_record_bytes"],serialization_payload_bytes=wire,
            serialization_buffer_capacity_bytes=capacity,capacity_evidence="INFERRED_FROM_FROZEN_BUFFER_GROWTH",
            runtime_and_current_raw_graph_bytes=Base.summarysize((ctx,raw,records))))
    end
    si_extra_safe_boundary(o["outdir"],"complete_map")
end
function si_extra_pilot_report(o,solved,ctx)
    columns=[size(op.P,2) for op in ctx.fr_blocks]
    all(==(72),columns) || error("Actual extra projectors differ")
    (;status="PILOT_COMPLETED_NOT_SCF_CONVERGED",completed_maps=solved.map_count,
      diagnostic_converged=get(solved,:diagnostic_converged,false),formal_scf=false,
      geometry=(;nk=length(ctx.basis.kpoints),sum_ng=sum(length(k.G_vectors) for k in ctx.basis.kpoints),
        max_ng=maximum(length(k.G_vectors) for k in ctx.basis.kpoints),projectors_per_k=only(unique(columns)),fft_size=collect(ctx.basis.fft_size)),
      lifecycle=(;history_bytes=o["history_bytes"],history_map_count=o["history_map_count"],max_record_bytes=o["max_record_bytes"],
        serialization_payload_bytes=o["serialization_payload_bytes"],serialization_buffer_capacity_bytes=o["serialization_buffer_capacity_bytes"],
        serialization_capacity_evidence="INFERRED_FROM_FROZEN_BUFFER_GROWTH",
        serialization_capacity_source_sha256=o["serialization_capacity_source_sha256"],julia_version=string(VERSION)))
end
function si_extra_spectral_pairs(b,raw,settings)
    records=map(enumerate(b.kpoints)) do (i,k)
        js=findall(q->all(abs.(k.coordinate.+q.coordinate.-round.(k.coordinate.+q.coordinate)).<=1e-12),b.kpoints)
        length(js)==1 || error("Extra k inversion is missing or ambiguous")
        j=only(js)
        (;source=i,target=j,coordinate_fractional=collect(k.coordinate),
          eigenvalue_max_ha=maximum(abs.(raw.eigenvalues[i].-raw.eigenvalues[j])),
          occupation_max=maximum(abs.(raw.f[i].-raw.f[j])))
    end
    em=maximum(r.eigenvalue_max_ha for r in records);fm=maximum(r.occupation_max for r in records)
    (;status=em<=settings["thresholds"]["time_reversed_spectrum_ha"] && fm<=settings["thresholds"]["paired_occupation_abs"] ? "PASS" : "REVIEW_REQUIRED",
      records,max_eigenvalue_difference_ha=em,max_occupation_difference=fm,
      scope="Actual same-grid solved spectrum/occupation pairing modulo reciprocal integers; no extra eigensolve; full-grid operator TR NOT_RUN")
end
function si_extra_check_entry(action,outdir,parent,profile,path)
    outdir=abspath(outdir);ispath(outdir) && error("Entry output already exists")
    startswith(outdir,joinpath(PHASE6C_ROOT,".work/phase9a-extra/runs")*"/") || error("Wrong extra entry area")
    mkpath(outdir)
    result=Dict{String,Any}("schema_version"=>1,"phase"=>"9A-extra","base_commit"=>SI_EXTRA_BASE,
        "case"=>"soc-extra-v1/$profile","extra_profile"=>profile,"backend"=>"soc-core","action"=>action,
        "run_id"=>basename(outdir),"execution_commit"=>strip(read(`git -C $PHASE6C_ROOT rev-parse HEAD`,String)),
        "execution_status"=>"FAIL","exit_code"=>1,"check_only"=>true,"numerical_execution_status"=>"NOT_RUN",
        "context_constructed"=>false,"formal_slot_reserved"=>false)
    try
        auth=si_extra_authorization(path,profile);si_extra_result_binding!(result,auth,profile)
        case=si_extra_case(profile)
        result["environment"]=environment_identity(PHASE6C_ROOT,(DFTK,PseudoPotentialIO))
        result["environment"].status=="PASS" || error("Frozen environment mismatch")
        DFTK.disable_threading();Threads.nthreads()==BLAS.get_num_threads()==1 || error("Single thread required")
        if endswith(action,"GAMMA")
            isnothing(parent) && error("BLOCKED_PARENT: own SCF required")
            receipt=si_json(joinpath(parent,"result.json"));si_extra_parent(receipt,case,auth,parent)
            filehash(joinpath(parent,"final.bin"))==receipt["checkpoint_sha256"] || error("Parent checkpoint changed")
        end
        length(FI._FR_CONTEXT_CERTIFICATES)==length(FI._BOUND_PSP_SOURCES)==0 || error("Entry built a numerical context/source")
        result["context_registrations"]=0;result["source_registrations"]=0
        si_extra_check_sources(auth)
        result["execution_status"]="CHECK_ONLY_PASS";result["check_status"]="PASS";result["exit_code"]=0
    catch err
        result["reason"]=sprint(showerror,err);showerror(stderr,err,catch_backtrace());println(stderr)
    end
    phase6b_write(joinpath(outdir,"result.json"),result);result["exit_code"]
end
function si_extra_main(args)
    check=!isempty(args) && last(args)=="--check-entry";a=check ? args[1:end-1] : args
    length(a) in (6,7) && a[end-3]=="--extra-profile" && a[end-1]=="--extra-contract" || return 2
    positional=a[1:end-4];profile=a[end-2];contract=a[end]
    allowed=profile=="B0" ? ("X-B0-SCF","X-B0-GAMMA") : profile=="K6" ? ("X-K6-PILOT","X-K6-SCF","X-K6-GAMMA") : ()
    isempty(positional) && return 2
    action=first(positional);action in allowed || return 2
    length(positional)==(endswith(action,"GAMMA") ? 3 : 2) || return 2
    parent=length(positional)==3 ? positional[3] : nothing
    check && return si_extra_check_entry(action,positional[2],parent,profile,contract)
    si_run(action,positional[2],parent;backend="soc-core",extra_profile=profile,extra_contract=contract)
end
