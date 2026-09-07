#!/usr/bin/env julia
# Phase 7F: authenticated orbital transport, then a gated single nonlocal operator.
module OrbitalNonlocalExtraction
using LinearAlgebra, SHA, Serialization, JSON3, Dates
include("extract_soc_density.jl")
const SD=SOCDensityExtraction
const DFTK=SD.DFTK
const PseudoPotentialIO=SD.PseudoPotentialIO
include("upf_validation.jl")
include("upf_runtime.jl")
include("../prototypes/relativistic/RelativisticProjectors.jl")
const RP=RelativisticProjectors
const ROOT=SD.ROOT
const DTYPES=Dict(Float64=>"<f8",ComplexF64=>"<c16",Int64=>"<i8")
const GATE_CHECKS=("source_identity","miller_bijection","normalization","density_restoration","kinetic_restoration")

function check_plan_environment(plan,identity)
    expected=plan["identity"]
    expected["overall_status"]=="PASS" && expected["exit_code"]==0 || error("Preparation identity was not successful")
    VERSION==v"1.12.7" && string(VERSION)==expected["environment"]["julia_version"] || error("Frozen Julia Serialization version differs")
    for path in ("environment/workbench/Project.toml","environment/workbench/Manifest.toml",
                 "environment/workbench/checksums.toml","config/sources.lock")
        haskey(plan["source_sha256"],path) || error("Missing frozen environment source binding")
    end
    actual=JSON3.read(JSON3.write(SD.public_data(identity,ROOT)),Dict{String,Any})
    actual==expected["environment"] || error("Actually loaded environment differs from preparation identity")
    nothing
end

array_hash(x)=bytes2hex(sha256(reinterpret(UInt8,vec(x))))
function source_snapshot(x)
    io=IOBuffer();serialize(io,x);bytes2hex(sha256(take!(io)))
end

"""Primitive transport only. Shapes use Julia/F order, with no numerical conversion."""
function write_array(directory,name,x::Array)
    ENDIAN_BOM==0x04030201 || error("Only little-endian primitive transport is supported")
    haskey(DTYPES,eltype(x)) && all(isfinite,x) || error("Unsupported or nonfinite primitive array")
    occursin(r"^[A-Za-z0-9_-]+$",name) || error("Invalid primitive array name")
    path=joinpath(directory,name*".bin");bytes=collect(reinterpret(UInt8,vec(x)))
    write(path,bytes);read(path)==bytes || error("Primitive on-disk bitwise round trip failed")
    (;path=basename(path),dtype=DTYPES[eltype(x)],shape=collect(size(x)),order="F",
      sha256=SD.filehash(path),bytes=length(bytes),bitwise_roundtrip_status="PASS")
end

function read_array(directory,descriptor;tracked=nothing)
    ENDIAN_BOM==0x04030201 || error("Only little-endian primitive transport is supported")
    descriptor["order"]=="F" || error("Primitive array order must be F")
    name=descriptor["path"]
    name isa String && basename(name)==name && endswith(name,".bin") || error("Unsafe primitive path")
    shape=descriptor["shape"]
    shape isa Vector && 1<=length(shape)<=3 && all(x->x isa Integer && 0<x<=10^7,shape) || error("Invalid primitive shape")
    count=prod(big.(shape));count<=10^7 || error("Primitive array dimension limit exceeded")
    types=Dict(v=>k for (k,v) in DTYPES);haskey(types,descriptor["dtype"]) || error("Unsupported primitive dtype")
    T=types[descriptor["dtype"]];path=joinpath(directory,name)
    digest=SD.checked_file(path,descriptor["sha256"])
    filesize(path)==descriptor["bytes"]==count*sizeof(T) || error("Primitive byte count mismatch")
    bytes=read(path);x=reshape(copy(reinterpret(T,bytes)),Tuple(Int.(shape)))
    all(isfinite,x) || error("Nonfinite primitive array")
    collect(reinterpret(UInt8,vec(x)))==bytes || error("Primitive decoding changed bytes")
    SD.checked_file(path,digest);isnothing(tracked) || (tracked[path]=digest)
    x
end

"""Recover the exact frozen cutoff enumeration without Model, terms or FFT plans.

PlaneWaveBasis.jl:218 -> Kpoint.jl:58-64 -> Kpoint.jl:20-40. The
Serialization hash is the historical runtime_checks.jl/common_data.jl G-order
receipt, including the original Vector{Vec3{Int}} representation.
"""
function recover_kpoints(physical,historical_basis)
    lattice=hcat((Float64.(v) for v in physical["lattice_vectors_bohr"])...)
    size(lattice)==(3,3) && all(isfinite,lattice) && abs(det(lattice))>0 || error("Invalid lattice columns")
    reciprocal=DFTK.compute_recip_lattice(DFTK.Mat3{Float64}(lattice))
    maximum(abs,lattice'*reciprocal/(2pi)-I)<=1e-12 || error("Reciprocal duality failed")
    historical_lattice=hcat((Float64.(v) for v in historical_basis["lattice_bohr"])...)
    lattice==historical_lattice || error("Historical lattice columns differ")
    fft_size=Tuple(Int.(physical["fft_size"]));ecut=Float64(physical["ecut_ha"])
    historical_basis["fft_grid"]==collect(fft_size) && historical_basis["ecut_ha"]==ecut &&
        historical_basis["volume_bohr3"]==abs(det(lattice)) &&
        historical_basis["n_electrons"]==physical["expected_electrons"] || error("Historical fixed basis differs")
    length(physical["kpoints"])==length(physical["kweights"])==length(historical_basis["kpoints"]) || error("Historical k count differs")
    points=map(eachindex(physical["kpoints"])) do ik
        k=Float64.(physical["kpoints"][ik]);old=historical_basis["kpoints"][ik]
        k==Float64.(old["coordinate_fractional"]) && physical["kweights"][ik]==old["weight_spatial"] || error("Historical k identity differs")
        kp=DFTK.Kpoint(1,k,reciprocal,fft_size,ecut;variational=true,architecture=DFTK.CPU())
        g=collect(kp.G_vectors);digest=source_snapshot(g)
        length(g)==old["ng"] && digest==old["g_order_sha256"] || error("Historical G order hash differs; equal NG is insufficient")
        millers=reduce(hcat,g);cart=Vector{Float64}(reciprocal*k)
        maximum(sum(abs2,reciprocal*(m+k))/2 for m in g)<=ecut+1e-10 || error("Cutoff range failed")
        (;millers=Matrix{Int64}(millers),k_cart=cart,coordinate_fractional=k,
          weight=Float64(physical["kweights"][ik]),g_order_sha256=digest)
    end
    (;lattice=Matrix(lattice),reciprocal=Matrix(reciprocal),points)
end

function bound_orbitals(state,endpoint,points;target=24)
    state.X isa Vector && state.f isa Vector && state.eigenvalues isa Vector || error("Expected plain orbital vectors")
    length(state.X)==length(state.f)==length(state.eigenvalues)==length(points) || error("Orbital k count differs")
    state.final.target_states==endpoint["target_states"]==target || error("Auxiliary or missing physical bands")
    for ik in eachindex(points)
        x,f,e=state.X[ik],state.f[ik],state.eigenvalues[ik]
        x isa Matrix{ComplexF64} && size(x)==(2size(points[ik].millers,2),target) || error("Original interleaved orbital shape differs")
        f isa Vector{Float64} && e isa Vector{Float64} && length(f)==length(e)==target || error("Original f/e shape or dtype differs")
        all(isfinite,x) && all(isfinite,e) && all(v->isfinite(v)&&0<=v<=1,f) || error("Nonfinite orbitals or invalid capacity-one occupation")
        isequal(f,Float64.(endpoint["occupations"][ik])) && isequal(f,state.final.occupations[ik]) || error("Original occupations differ from bound endpoint")
        isequal(e,Float64.(endpoint["eigenvalues_ha"][ik])) && isequal(e,state.final.eigenvalues_ha[ik]) || error("Original eigenvalues differ from bound endpoint")
    end
    nothing
end

function extract_states!(result,request,plan,outdir,tracked)
    oldpath=SD.resolve_path(plan["historical_binding_plan"])
    tracked[oldpath]=SD.checked_file(oldpath,plan["source_sha256"][plan["historical_binding_plan"]])
    oldplan=SD.read_json(oldpath);physical=plan["physical"]
    physical["kpoints"]==[[0.,0.,0.],[.125,.0625,-.1875],[-.125,-.0625,.1875]] &&
        physical["fft_size"]==[40,40,40] && physical["ecut_ha"]==15 &&
        physical["expected_electrons"]==10 || error("Only the declared original Mg case is supported")
    states=Dict{String,Any}();result["states"]=states
    geometry=nothing
    for label in ("A","B")
        source=plan["sources"][label]
        source==oldplan["sources"][label] || error("Historical A/B source description changed")
        requested=get(get(request,"sources",Dict()),label,Dict())
        path=SD.resolve_path(get(requested,"checkpoint_path",source["checkpoint"]["path"]))
        get(requested,"checkpoint_sha256",source["checkpoint"]["sha256"])==source["checkpoint"]["sha256"] || error("Requested source hash changed")
        binding=SD.validate_historical_binding(oldplan,label,path);merge!(tracked,binding.tracked)
        evidence=SD.read_json(SD.resolve_path(source["historical_evidence_path"]))
        if isnothing(geometry)
            geometry=recover_kpoints(physical,evidence["basis"])
            result["static_kpoint_initializations"]=length(geometry.points)
        end
        state=SD.trusted_checkpoint(path,source["checkpoint"]["sha256"])
        bound=SD.bound_densities(state,binding.endpoint,Tuple(Int.(physical["fft_size"])),
            Float64(physical["volume_bohr3"])/prod(physical["fft_size"]),oldplan["thresholds"])
        bound.closure.status=="PASS" || error("Historical closure restoration failed")
        bound_orbitals(state,binding.endpoint,geometry.points)
        target=joinpath(outdir,label);mkpath(target)
        ks=map(enumerate(geometry.points)) do (ik,p)
            (;source_k_index=ik,millers=write_array(target,"k$(ik)-millers",p.millers),
              coefficients=write_array(target,"k$(ik)-coefficients",reshape(state.X[ik],2,size(p.millers,2),24)),
              occupations=write_array(target,"k$(ik)-occupations",state.f[ik]),
              eigenvalues=write_array(target,"k$(ik)-eigenvalues",state.eigenvalues[ik]),
              k_cart=write_array(target,"k$(ik)-cart",p.k_cart),coordinate_fractional=p.coordinate_fractional,
              weight=p.weight,g_order_sha256=p.g_order_sha256)
        end
        metadata=(;schema_version=1,phase="7F",execution_status="PASS",label,
            source_run_id=source["run_id"],source_checkpoint_sha256=source["checkpoint"]["sha256"],
            plan_sha256=result["plan_sha256"],coefficient_layout="component,G,state; interleaved components; F order",
            lattice_columns=write_array(target,"lattice-columns",geometry.lattice),
            reciprocal_columns=write_array(target,"reciprocal-columns",geometry.reciprocal),
            fft_size=physical["fft_size"],n_bands=24,occupation_capacity=1,kpoints=ks,
            n_out=write_array(target,"n-out",reshape(state.n_out,Tuple(Int.(physical["fft_size"])))),
            n_out_producer_sha256=binding.endpoint["n_out_sha256"],closure=bound.closure,
            historical_energy_terms_ha=binding.endpoint["diagnostics"]["energy_terms_ha"],
            source_binding_status="PASS",data_roundtrip_status="PASS",
            normalization_applied=false,orbital_rotation_applied=false)
        SD.write_json(joinpath(target,"metadata.json"),metadata)
        states[label]=(;metadata_path=label*"/metadata.json",sha256=SD.filehash(joinpath(target,"metadata.json")))
        println(stderr,"Completed unchanged historical orbital extraction ",label)
    end
end

function validate_gate(gate,plan_sha,metadata_shas)
    gate["schema_version"]==1 && gate["phase"]=="7F" && gate["execution_status"]=="PASS" || error("Nonlocal gate is not PASS")
    gate["plan_sha256"]==plan_sha || error("Gate plan differs")
    gate["orbital_metadata_sha256"]==metadata_shas || error("Gate is bound to different orbital data")
    Set(keys(metadata_shas))==Set(("A","B","Q")) || error("Only A/B/original Q states are supported")
    all(get(gate["checks"],key,nothing)=="PASS" for key in GATE_CHECKS) || error("A required pre-nonlocal gate failed")
    nothing
end

function load_state(path,sha,plan_sha,tracked)
    tracked[path]=SD.checked_file(path,sha);m=SD.read_json(path);directory=dirname(path)
    m["schema_version"]==1 && m["phase"]=="7F" && m["execution_status"]=="PASS" &&
        m["plan_sha256"]==plan_sha && m["n_bands"]==24 && m["occupation_capacity"]==1 || error("Unsupported state metadata")
    arr(key)=read_array(directory,m[key];tracked)
    ks=map(m["kpoints"]) do k
        getarray(key)=read_array(directory,k[key];tracked)
        g=getarray("millers");c=getarray("coefficients");f=getarray("occupations");e=getarray("eigenvalues");cart=getarray("k_cart")
        g isa Matrix{Int64} && size(g,1)==3 && c isa Array{ComplexF64,3} && size(c)==(2,size(g,2),24) || error("Invalid state G/component/band layout")
        f isa Vector{Float64} && e isa Vector{Float64} && length(f)==length(e)==24 &&
            all(x->0<=x<=1,f) && cart isa Vector{Float64} && length(cart)==3 || error("Invalid state occupations/eigenvalues/k")
        (;millers=g,X=reshape(c,2size(g,2),24),f,e,k_cart=cart,
          coordinate_fractional=Float64.(k["coordinate_fractional"]),weight=Float64(k["weight"]))
    end
    (;metadata=m,lattice=arr("lattice_columns"),reciprocal=arr("reciprocal_columns"),kpoints=ks)
end

"""Exact integer bijection. Only proven G row permutation; no projection or phase fit."""
function reorder_spinors(reference_millers,source_millers,X)
    reference_millers isa AbstractMatrix{<:Integer} && source_millers isa AbstractMatrix{<:Integer} || error("Miller entries must be exact integers")
    size(reference_millers,1)==size(source_millers,1)==3 &&
        size(reference_millers,2)==size(source_millers,2) && size(X,1)==2size(source_millers,2) || error("Miller / spinor sizes differ")
    src=Tuple.(eachcol(source_millers));dst=Tuple.(eachcol(reference_millers))
    length(unique(src))==length(src) && length(unique(dst))==length(dst) || error("Duplicate Miller vector")
    Set(src)==Set(dst) || error("G support differs; cropping, padding and reprojection forbidden")
    lookup=Dict(m=>i for (i,m) in enumerate(src));permutation=[lookup[m] for m in dst]
    rows=reduce(vcat,([2i-1,2i] for i in permutation));mapped=copy(X[rows,:])
    inverse=invperm(permutation);backrows=reduce(vcat,([2i-1,2i] for i in inverse))
    array_hash(mapped[backrows,:])==array_hash(X) || error("G permutation changed coefficient bytes")
    (;X=mapped,permutation)
end

"""Two single-operator contractions, preserving spin interference and full D."""
function nonlocal_contractions(op,X,f,w)
    X isa Matrix{ComplexF64} && size(X,1)==size(op,1) && length(f)==size(X,2) || error("Nonlocal state dimensions differ")
    all(isfinite,X) && all(x->isfinite(x)&&0<=x<=1,f) && isfinite(w) && w>=0 || error("Invalid nonlocal state")
    before=array_hash(X);vx=op*X
    up=op.P[1:2:end,:]'*X[1:2:end,:];down=op.P[2:2:end,:]'*X[2:2:end,:]
    y=op.P'*X;dy=op.D*y;dup=op.D*up;ddown=op.D*down
    rows=map(axes(X,2)) do n
        action=real(dot(view(X,:,n),view(vx,:,n)))
        projected=real(dot(view(y,:,n),view(dy,:,n)))
        uu=real(dot(view(up,:,n),view(dup,:,n)));dd=real(dot(view(down,:,n),view(ddown,:,n)))
        cross=dot(view(up,:,n),view(ddown,:,n));spin=uu+dd+2real(cross)
        (;band=n,occupation=f[n],weight_spatial=w,action_ha=action,projected_ha=projected,
          up_up_ha=uu,down_down_ha=dd,up_down_real_ha=real(cross),up_down_imag_ha=imag(cross),
          spin_cross_ha=2real(cross),spin_sum_ha=spin,weighted_action_ha=w*f[n]*action,
          weighted_projected_ha=w*f[n]*projected,weighted_spin_sum_ha=w*f[n]*spin)
    end
    all(r->all(isfinite,values(r)),rows) || error("Nonfinite nonlocal contraction")
    array_hash(X)==before || error("Nonlocal action mutated source spinors")
    (;rows,up,down,total_projected=sum(r.weighted_projected_ha for r in rows),
      total_action=sum(r.weighted_action_ha for r in rows),total_spin=sum(r.weighted_spin_sum_ha for r in rows),
      projection_split_max_abs=maximum(abs,y-up-down))
end

function evaluate_nonlocal!(result,request,plan,outdir,tracked)
    refs=request["states"];Set(keys(refs))==Set(("A","B","Q")) || error("Exactly A/B/Q required")
    shas=Dict(label=>refs[label]["sha256"] for label in ("A","B","Q"))
    gatepath=SD.resolve_path(request["gate_path"]);tracked[gatepath]=SD.checked_file(gatepath,request["gate_sha256"])
    validate_gate(SD.read_json(gatepath),result["plan_sha256"],shas)
    result["pre_nonlocal_gate_sha256"]=request["gate_sha256"]
    states=Dict(label=>load_state(SD.resolve_path(refs[label]["metadata_path"]),shas[label],result["plan_sha256"],tracked) for label in ("A","B","Q"))
    a=states["A"];physical=plan["physical"];thresholds=plan["thresholds"]
    A=hcat((Float64.(v) for v in physical["lattice_vectors_bohr"])...);B=Matrix(DFTK.compute_recip_lattice(DFTK.Mat3{Float64}(A)))
    expected_runs=Dict("A"=>plan["sources"]["A"]["run_id"],"B"=>plan["sources"]["B"]["run_id"],"Q"=>plan["sources"]["G40"]["run_id"])
    mapped=Dict{String,Any}();permutations=Dict{String,Any}()
    for label in ("A","B","Q")
        s=states[label];s.metadata["label"]==label && s.metadata["source_run_id"]==expected_runs[label] || error("State source is not original A/B/G40")
        size(s.lattice)==size(s.reciprocal)==(3,3) && maximum(abs,s.lattice-A)<=1e-12 && maximum(abs,s.reciprocal-B)<=1e-12 || error("State geometry differs")
        length(s.kpoints)==3 || error("Original three k points required")
        mapped[label]=Matrix{ComplexF64}[];permutations[label]=Any[]
        for ik in 1:3
            k=s.kpoints[ik];reference=a.kpoints[ik]
            k.coordinate_fractional==Float64.(physical["kpoints"][ik]) && k.weight==physical["kweights"][ik] &&
                maximum(abs,k.k_cart-B*k.coordinate_fractional)<=1e-12 || error("K source/order/units differs")
            r=reorder_spinors(reference.millers,k.millers,k.X)
            push!(mapped[label],r.X);push!(permutations[label],r.permutation)
        end
    end
    # Nothing above constructs any pseudopotential, P, D or physical operator.
    haskey(request,"pseudo_path") || error("An explicitly source-bound original Mg UPF path is required")
    ppath=SD.resolve_path(request["pseudo_path"]);pseudo_sha=physical["pseudopotential_sha256"]
    tracked[ppath]=SD.checked_file(ppath,pseudo_sha)
    parsed=UpfRuntime.parse_input(ppath);parsed.status=="PASS" || error("Mg UPF parsing failed")
    h=parsed.parsed.header
    (strip(h.element),h.z_valence,h.functional,h.relativistic,h.has_so,h.pseudo_type,h.core_correction)==
        ("Mg",10,"PBESOL","full",true,"NC",false) && isnothing(parsed.parsed.nlcc) || error("Bound Mg FR-NC/PBEsol/no-NLCC header differs")
    channels=RP.fr_channels(parsed.parsed;unit_convention=:dftk)
    positions=[A*Float64.(physical["position_fractional"])];volume=Float64(physical["volume_bohr3"])
    operators=map(a.kpoints) do k
        q=[B*Float64.(m)+k.k_cart for m in eachcol(k.millers)]
        RP.build_nonlocal_operator(channels,q,positions,volume)
    end
    all(op->size(op.P,2)==16 && op.D==operators[1].D && op.labels==operators[1].labels,operators) || error("Full 16-column common D/label contract differs")
    result["nonlocal_operator_constructions"]=3
    result["operators"]=(;D=write_array(outdir,"D",operators[1].D),labels=operators[1].labels,
        P=[write_array(outdir,"P-k$(ik)",op.P) for (ik,op) in enumerate(operators)],
        pseudo_sha256=pseudo_sha,channels=RP.channel_summary(channels),
        full_offdiagonal_D_retained=true,square_PW_operator_constructed=false)
    reports=Dict{String,Any}();result["states"]=reports
    for label in ("A","B","Q")
        s=states[label];blocks=[nonlocal_contractions(operators[ik],mapped[label][ik],s.kpoints[ik].f,s.kpoints[ik].weight) for ik in 1:3]
        action=sum(b.total_action for b in blocks);projected=sum(b.total_projected for b in blocks);spin=sum(b.total_spin for b in blocks)
        contractions_ok=abs(action-projected)<=thresholds["nonlocal_contraction_abs_ha"] && abs(action-spin)<=thresholds["nonlocal_contraction_abs_ha"]
        old=label=="Q" ? nothing : s.metadata["historical_energy_terms_ha"]["AtomicNonlocalFR"]
        difference=isnothing(old) ? nothing : action-old
        historical_ok=isnothing(difference) || abs(difference)<=thresholds["historical_nonlocal_abs_ha"]
        reports[label]=(;status=contractions_ok && historical_ok ? "PASS" : "FAIL",quantity=label=="Q" ? "DFTK_FROZEN_FR_NONLOCAL_EXPECTATION_ON_QE_G40_ORBITALS" : "DFTK_FROZEN_FR_NONLOCAL_EXPECTATION_ON_ORIGINAL_DFTK_ORBITALS",
            source_run_id=s.metadata["source_run_id"],orbital_metadata_sha256=shas[label],energy_action_ha=action,
            energy_projected_ha=projected,energy_spin_sum_ha=spin,historical_nonlocal_ha=old,historical_difference_ha=difference,
            kpoints=[(;rows=b.rows,up_amplitudes=write_array(outdir,"$(label)-k$(ik)-up",b.up),
                down_amplitudes=write_array(outdir,"$(label)-k$(ik)-down",b.down),
                projection_split_max_abs=b.projection_split_max_abs,source_row_permutation=permutations[label][ik]) for (ik,b) in enumerate(blocks)])
        println(stderr,"Completed frozen single-operator evaluation ",label)
        SD.write_json(joinpath(outdir,"progress.json"),result)
        contractions_ok || error("Nonlocal contraction paths differ; computed diagnostics retained")
        historical_ok || error("Original $label nonlocal energy not restored; Q interpretation blocked")
    end
end

function run_request(requestpath,outdir)
    outdir=abspath(outdir)
    ispath(outdir) && (println(stderr,"Existing output refused; no old PASS reused");return 2)
    startswith(outdir,joinpath(ROOT,".work")*"/") || (println(stderr,"Output must be a new ignored .work directory");return 2)
    result=Dict{String,Any}("schema_version"=>1,"phase"=>"7F","execution_status"=>"RUNNING",
        "started_utc"=>string(now(UTC)),"new_scf_status"=>"NOT_RUN","new_eigensolve_status"=>"NOT_RUN",
        "full_hamiltonian_status"=>"NOT_CONSTRUCTED","xc_hartree_local_evaluation_status"=>"NOT_RUN",
        "static_kpoint_initializations"=>0,"nonlocal_operator_constructions"=>0)
    tracked=Dict{String,String}();code=1
    try
        mkpath(outdir);request=SD.read_json(requestpath)
        request["schema_version"]==1 && request["stage"] in ("extract","nonlocal") || error("Unsupported request schema/stage")
        result["stage"]=request["stage"];result["plan_sha256"]=request["plan_sha256"]
        planpath=SD.resolve_path(request["plan_path"]);tracked[planpath]=SD.checked_file(planpath,request["plan_sha256"])
        plan=SD.read_json(planpath);plan["schema_version"]==1 || error("Unsupported plan schema")
        tracked[abspath(requestpath)]=SD.filehash(requestpath);tracked[@__FILE__]=SD.filehash(@__FILE__)
        result["executed_script_sha256"]=tracked[@__FILE__]
        for (path,sha) in plan["source_sha256"];tracked[SD.resolve_path(path)]=SD.checked_file(SD.resolve_path(path),sha);end
        identity=SD.environment_identity(ROOT,(DFTK,PseudoPotentialIO));result["environment"]=identity
        identity.status=="PASS" || error("Frozen environment identity failed")
        check_plan_environment(plan,identity)
        DFTK.disable_threading()
        request["stage"]=="extract" ? extract_states!(result,request,plan,outdir,tracked) : evaluate_nonlocal!(result,request,plan,outdir,tracked)
        for (path,sha) in tracked;SD.checked_file(path,sha);end
        SD.environment_identity(ROOT,(DFTK,PseudoPotentialIO))==identity || error("Loaded environment changed")
        result["source_preservation_status"]="PASS";result["environment_recheck_status"]="PASS"
        result["execution_status"]="PASS";code=0
    catch err
        result["execution_status"]=err isa SD.MissingSource ? "BLOCKED_MISSING_SOURCE" : "FAIL"
        result["failure_reason"]=sprint(showerror,err);showerror(stderr,err,catch_backtrace());println(stderr)
    end
    result["exit_code"]=code;result["finished_utc"]=string(now(UTC))
    try
        write(joinpath(outdir,"summary.txt"),"Phase7F $(get(result,"stage","unknown")): $(result["execution_status"]), exit=$code\n")
        SD.write_json(joinpath(outdir,"metadata.json"),result)
    catch err
        code=1;println(stderr,"Persistence failed: ",sprint(showerror,err))
        safe=Dict("schema_version"=>1,"phase"=>"7F","execution_status"=>"FAIL","exit_code"=>1,"failure_reason"=>"Persistence failed; see stderr")
        try SD.write_json(joinpath(outdir,"metadata.json"),safe) catch;println(stderr,"Could not persist safe failure record");end
    end
    code
end

function main(args)
    args==["--help"] && (println("Usage: extract_orbital_nonlocal.jl REQUEST.json NEW_IGNORED_OUTPUT_DIR\nStages: extract unchanged A/B; nonlocal only after an independently bound PASS gate. No electronic solve.");return 0)
    length(args)==2 || (println(stderr,"Expected request and new ignored output directory");return 2)
    run_request(args...)
end
end
abspath(PROGRAM_FILE)==(@__FILE__) && exit(OrbitalNonlocalExtraction.main(ARGS))
