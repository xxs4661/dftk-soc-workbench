#!/usr/bin/env julia
# Read-only comparison of the two Phase 6C endpoints; never invokes SCF or QE.
isdefined(@__MODULE__, :phase6c_main) || include("run_soc_scf.jl")

soc_compare_require(ok,message) = ok || throw(ArgumentError(message))
soc_compare_plain(x) = JSON3.read(JSON3.write(x),Dict{String,Any})

function soc_kpoint_mapping(ka,kb;atol=1e-13)
    length(ka)==length(kb)>0 || throw(ArgumentError("Different k-point counts"))
    coords(points) = [begin
        q=point["coordinate_fractional"]
        soc_compare_require(q isa AbstractVector && length(q)==3 && all(x->x isa Real && isfinite(x),q),"Invalid fractional k coordinate")
        Float64.(q)
    end for point in points]
    a,b=coords(ka),coords(kb)
    equivalent(x,y)=norm((x-y).-round.(x-y),Inf)<=atol
    for points in (a,b),i in eachindex(points),j in 1:i-1
        soc_compare_require(!equivalent(points[i],points[j]),"Duplicate k coordinate modulo reciprocal integers")
    end
    mapping=Int[]
    for q in a
        matched=findall(p->equivalent(q,p),b)
        soc_compare_require(length(matched)==1,"Missing or ambiguous k-coordinate match")
        push!(mapping,only(matched))
    end
    soc_compare_require(length(unique(mapping))==length(mapping),"k-coordinate mapping is not bijective")
    mapping
end

function soc_validate_endpoint(run,state,label,settings,config_hash,checkpoint_hash)
    phase6b_finite(run)
    soc_compare_require(get(run,"schema_version",nothing)===1 && get(run,"phase",nothing)=="6C" &&
        get(run,"label",nothing)==label,"Wrong result schema, phase or label")
    soc_compare_require(get(run,"execution_status",nothing)=="PASS" && get(run,"exit_code",nothing)===0 &&
        all(get(run,key,nothing)=="PASS" for key in SOC_STAGES),"$label: not every execution/stage passed")
    soc_compare_require(get(run,"run_id",nothing) isa AbstractString && !isempty(run["run_id"]),"Missing run ID")
    soc_compare_require(run["config_sha256"]==config_hash && run["settings"]==settings,"$label: actual configuration differs")
    soc_compare_require(run["checkpoint_sha256"]==checkpoint_hash,"$label: final checkpoint SHA-256 differs")
    soc_compare_require(run["environment"]["status"]=="PASS" && run["final_environment"]["status"]=="PASS" &&
        run["environment"]==run["final_environment"],"$label: environment did not remain valid")
    soc_compare_require(run["temperature_ha"]==settings["ensemble"]["tau_ha"] && run["smearing"]=="FermiDirac",
        "$label: temperature/smearing differs")
    soc_compare_require(state isa NamedTuple && Set(keys(state))==Set((:X,:f,:eigenvalues,:n_in,:n_out,:R,:m,:final)),
        "$label: expected arrays and final metadata, not a serialized context")
    final=run["final"];target=final["target_states"]
    s=settings["solver"]
    soc_compare_require(target isa Int && target in s["initial_target_states"]:s["target_increment"]:s["max_target_states"],
        "$label: invalid target count")
    soc_compare_require(soc_compare_plain(state.final)==final,"$label: checkpoint final metadata differs from result JSON")
    basis=run["basis"];mg=settings["mg"];input=run["input"];side=mg["cell_side_bohr"]
    soc_compare_require(input["element"]=="Mg" && input["functional"]=="PBESOL" && input["has_so"]===true &&
        input["nlcc_present"]===false && input["relativistic"]=="full" &&
        input["z_valence"]==mg["expected_header_valence"] && input["xc_identifiers"]==mg["xc_identifiers"],
        "$label: input header differs from requested Mg")
    soc_compare_require(basis["lattice_bohr"]==[[side,0.,0.],[0.,side,0.],[0.,0.,side]] &&
        basis["volume_bohr3"]==side^3 && basis["positions_fractional"]==mg["positions_fractional"] &&
        basis["ecut_ha"]==mg["ecut_ha"] && basis["n_electrons"]==input["z_valence"]*length(mg["positions_fractional"]) &&
        basis["native_nonlocal_terms"]==0,"$label: actual basis differs from requested model")
    requested=[Dict("coordinate_fractional"=>q) for q in mg["kpoints"]]
    request_mapping=soc_kpoint_mapping(requested,basis["kpoints"])
    for (i,j) in enumerate(request_mapping)
        soc_compare_require(basis["kpoints"][j]["weight_spatial"]==mg["kweights"][i],"$label: requested k weight differs")
    end
    soc_compare_require(basis["fft_grid"] isa AbstractVector && length(basis["fft_grid"])==3 &&
        all(x->x isa Int && x>0,basis["fft_grid"]),"Invalid FFT grid")
    nk=length(basis["kpoints"]);nr=prod(basis["fft_grid"])
    for (name,n) in (("n_in",state.n_in),("n_out",state.n_out))
        soc_compare_require(n isa Vector{Float64} && length(n)==nr && all(isfinite,n),"$label: invalid $name array")
        soc_compare_require(FI.integration_density_hash(n)==final[name*"_sha256"],"$label: $name array hash differs")
    end
    soc_compare_require(minimum(state.n_out)>=-64eps(Float64)*max(1,maximum(abs,state.n_out)),"Negative output density")
    electron_count=basis["volume_bohr3"]/nr*sum(state.n_out)
    soc_compare_require(abs(electron_count-basis["n_electrons"])<=settings["thresholds"]["electron_count_abs"],"Output-density electron count differs")
    soc_compare_require(size(state.m)==(3,nr) && all(isfinite,state.m),"Invalid Pauli-density array")
    soc_compare_require(size(state.R)==(2,2,nr) && all(isfinite,state.R),"Invalid spin-density matrix array")
    soc_compare_require(length(state.X)==length(state.eigenvalues)==length(state.f)==nk,"Checkpoint k-point count differs")
    soc_compare_require(state.eigenvalues==final["eigenvalues_ha"] && state.f==final["occupations"],
        "$label: checkpoint spectra/occupations differ from result JSON")
    for ik in 1:nk
        e,f,x=state.eigenvalues[ik],state.f[ik],state.X[ik]
        soc_compare_require(e isa Vector{Float64} && length(e)==target && all(isfinite,e) && issorted(e),"Invalid ordered target eigenvalues")
        soc_compare_require(f isa Vector{Float64} && length(f)==target && all(v->isfinite(v) && 0<=v<=1,f),"Invalid occupations")
        soc_compare_require(x isa Matrix{ComplexF64} && size(x)==(2basis["kpoints"][ik]["ng"],target) && all(isfinite,x),
            "Invalid target-orbital array")
    end
    diag=final["diagnostics"]
    for key in ("internal_energy_ha","free_energy_ha","entropy_energy_ha","entropy_dimensionless")
        soc_compare_require(diag[key] isa Real && isfinite(diag[key]),"Invalid final energy/entropy")
    end
    soc_compare_require(final["mu_ha"] isa Real && isfinite(final["mu_ha"]),"Invalid chemical potential")
    (;target,electron_count)
end

"""Compare actual endpoint arrays; synthetic tests are protocol/numerical fixtures only."""
function compare_soc_results(a,b,state_a,state_b,settings;config_sha256,run_hashes,checkpoint_hashes)
    ea=soc_validate_endpoint(a,state_a,"A",settings,config_sha256,checkpoint_hashes["A"])
    eb=soc_validate_endpoint(b,state_b,"B",settings,config_sha256,checkpoint_hashes["B"])
    soc_compare_require(a["run_id"]!=b["run_id"],"A and B must have independent run IDs")
    soc_compare_require(a["input"]==b["input"],"A/B input metadata or identity differs")
    soc_compare_require(a["environment"]==b["environment"] && a["executed_source_sha256"]==b["executed_source_sha256"],
        "A/B environment or executed source differs")
    ba,bb=a["basis"],b["basis"]
    soc_compare_require(Set(keys(ba))==Set(keys(bb)),"A/B basis fields differ")
    for key in keys(ba)
        key=="kpoints" && continue
        soc_compare_require(ba[key]==bb[key],"A/B basis differs: $key")
    end
    mapping=soc_kpoint_mapping(ba["kpoints"],bb["kpoints"])
    for (ia,ib) in enumerate(mapping)
        ka,kb=ba["kpoints"][ia],bb["kpoints"][ib]
        soc_compare_require(Set(keys(ka))==Set(keys(kb)),"A/B k-point metadata fields differ")
        for key in keys(ka)
            key=="coordinate_fractional" && continue
            soc_compare_require(ka[key]==kb[key],"A/B corresponding k-point basis differs: $key")
        end
    end
    # Same physical real-space grid: dvol cancels in the relative L2 ratio.
    na,nb=state_a.n_out,state_b.n_out
    density_relative=norm(na-nb)/max(norm(na),norm(nb))
    density_abs=sqrt(ba["volume_bohr3"]/length(na))*norm(na-nb)
    threshold=settings["thresholds"];nlow=threshold["comparison_lowest_states"]
    soc_compare_require(min(ea.target,eb.target)>=nlow,"Too few target states for requested spectral comparison")
    spectral=[(;a_index=ia,b_index=ib,coordinate_fractional=ba["kpoints"][ia]["coordinate_fractional"],
        max_abs_difference_ha=maximum(abs.(state_a.eigenvalues[ia][1:nlow]-state_b.eigenvalues[ib][1:nlow])))
        for (ia,ib) in enumerate(mapping)]
    max_spectrum=maximum(row.max_abs_difference_ha for row in spectral)
    da,db=a["final"]["diagnostics"],b["final"]["diagnostics"]
    energy_difference=abs(da["internal_energy_ha"]-db["internal_energy_ha"])
    free_difference=abs(da["free_energy_ha"]-db["free_energy_ha"])
    numerical_pass=density_relative<=threshold["ab_density_relative"] && max_spectrum<=threshold["ab_spectrum_abs_ha"] &&
        max(energy_difference,free_difference)<=threshold["ab_energy_abs_ha"]
    common_target=ea.target==eb.target ? ea.target : nothing
    status=!numerical_pass ? "DIFFERENT_SOLUTIONS" : isnothing(common_target) ? "REVIEW_REQUIRED" : "PASS"
    nshared=min(ea.target,eb.target)
    occupation_difference=maximum(maximum(abs.(state_a.f[ia][1:nshared]-state_b.f[ib][1:nshared])) for (ia,ib) in enumerate(mapping))
    result=Dict{String,Any}(
        "schema_version"=>1,"phase"=>"6C","execution_status"=>"PASS","exit_code"=>(status=="PASS" ? 0 : 1),
        "two_initial_states_comparison_status"=>status,"numerical_review_status"=>"REVIEW_REQUIRED",
        "common_target_states"=>common_target,"target_states"=>Dict("A"=>ea.target,"B"=>eb.target),
        "config_sha256"=>config_sha256,
        "runs"=>Dict(label=>Dict("run_id"=>run["run_id"],"result_sha256"=>run_hashes[label],
            "checkpoint_sha256"=>checkpoint_hashes[label]) for (label,run) in (("A",a),("B",b))),
        "input_sha256"=>a["input"]["sha256"],"kpoint_mapping_b_for_a"=>mapping,
        "density_relative_l2"=>density_relative,"density_absolute_l2"=>density_abs,
        "internal_energy_abs_difference_ha"=>energy_difference,"free_energy_abs_difference_ha"=>free_difference,
        "lowest_states_compared"=>nlow,"max_raw_eigenvalue_difference_ha"=>max_spectrum,"spectra_by_k"=>spectral,
        "diagnostic_only"=>Dict("shared_state_occupation_max_difference"=>occupation_difference,
            "shared_states_compared"=>nshared,"entropy_abs_difference_dimensionless"=>abs(da["entropy_dimensionless"]-db["entropy_dimensionless"]),
            "mu_abs_difference_ha"=>abs(a["final"]["mu_ha"]-b["final"]["mu_ha"]),
            "note"=>"f/S/mu are diagnostics; no chemical-potential equality gate in a numerically saturated gap"),
        "comparison_definition"=>"Raw lowest 16 levels at uniquely matched fractional k modulo reciprocal integers; no spectral matching, energy shift or fit",
        "qe_soc_input_status"=>"BLOCKED","qe_soc_benchmark_status"=>"NOT_RUN")
    phase6b_finite(result)
    result
end

function compare_soc_main(args)
    usage="Usage: compare_soc_scf.jl RAW_A_RESULT RAW_B_RESULT NEW_COMPARISON_JSON (no SCF; non-PASS exits 1)"
    args==["--help"] && (println(usage);return 0)
    length(args)==3 || (println(stderr,usage);return 2)
    ap,bp,out=abspath.(args)
    ispath(out) && (println(stderr,"Refusing existing comparison output");return 2)
    startswith(out,joinpath(PHASE6C_ROOT,".work")*"/") || (println(stderr,"Comparison evidence must be under ignored .work");return 2)
    result=Dict{String,Any}("schema_version"=>1,"phase"=>"6C","execution_status"=>"FAIL","exit_code"=>1,
        "two_initial_states_comparison_status"=>"FAIL","qe_soc_input_status"=>"BLOCKED","qe_soc_benchmark_status"=>"NOT_RUN")
    try
        abytes,bbytes=read(ap),read(bp)
        ah,bh=bytes2hex(sha256(abytes)),bytes2hex(sha256(bbytes))
        a,b=[JSON3.read(bytes,Dict{String,Any}) for bytes in (abytes,bbytes)]
        ac,bc=[joinpath(dirname(p),"final.bin") for p in (ap,bp)]
        ach,bch=filehash(ac),filehash(bc)
        soc_compare_require(a["checkpoint_sha256"]==ach && b["checkpoint_sha256"]==bch,"Actual final checkpoint SHA-256 differs")
        identity=environment_identity(PHASE6C_ROOT,(DFTK,PseudoPotentialIO))
        soc_compare_require(identity.status=="PASS","Comparison environment identity failed")
        soc_compare_require(a["environment"]==soc_compare_plain(public_data(identity,PHASE6C_ROOT)),"Actual comparison environment differs from A/B")
        soc_compare_require(a["executed_source_sha256"]==b["executed_source_sha256"]==phase6c_sources(),"Actual executed source identity differs")
        pseudo=TOML.parsefile(joinpath(PHASE6C_ROOT,"config/sources.lock"))["pseudopotentials"]
        soc_compare_require(a["input"]["sha256"]==pseudo["file_sha256"]==filehash(joinpath(PHASE6C_ROOT,pseudo["local_path"])),
            "Actual locked Mg bytes differ from A/B input identity")
        settings=TOML.parsefile(PHASE6C_CONFIG)
        result=compare_soc_results(a,b,deserialize(ac),deserialize(bc),settings;
            config_sha256=filehash(PHASE6C_CONFIG),run_hashes=Dict("A"=>ah,"B"=>bh),checkpoint_hashes=Dict("A"=>ach,"B"=>bch))
        result["comparison_environment"]=identity
        soc_compare_require(filehash(ap)==ah && filehash(bp)==bh && filehash(ac)==ach && filehash(bc)==bch,
            "Input evidence changed during comparison")
    catch err
        result=Dict{String,Any}("schema_version"=>1,"phase"=>"6C","execution_status"=>"FAIL","exit_code"=>1,
            "two_initial_states_comparison_status"=>"FAIL","qe_soc_input_status"=>"BLOCKED","qe_soc_benchmark_status"=>"NOT_RUN",
            "failure_reason"=>sprint(showerror,err))
        println(stderr,result["failure_reason"])
    end
    result["finished_utc"]=string(now(UTC))
    try
        ispath(out) && (println(stderr,"Comparison output appeared during execution; refusing replacement");return 2)
        mkpath(dirname(out));phase6b_write(out,result)
    catch err
        println(stderr,"Comparison persistence failure: ",sprint(showerror,err));return 1
    end
    println(stderr,"A/B comparison: ",result["two_initial_states_comparison_status"])
    result["exit_code"]
end

abspath(PROGRAM_FILE)==(@__FILE__) && exit(compare_soc_main(ARGS))
