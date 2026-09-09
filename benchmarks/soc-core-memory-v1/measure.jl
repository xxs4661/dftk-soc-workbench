#!/usr/bin/env julia
# Restricted fixed-endpoint measurements. No SCF, eigenvalue, or occupation solve.
using DFTK, PseudoPotentialIO, LinearAlgebra, Random, Serialization, SHA, JSON3, Dates
include("memory.jl")
const MEASUREMENT_PREPARATION = "e4f16a51a0304f5e70f5ae038563d6760409c2c4"
const MEASUREMENT_BASE = "c764311a5422b5c3cab5a7b78a02d420910c4e56"
const MEASUREMENT_DIR = "benchmarks/soc-core-memory-v1"
const MEASUREMENT_PLAN_FILES = ("README.md", "plan.json", "sources.json", "contract.json")

msha(path) = bytes2hex(sha256(read(path)))
mjson(path) = JSON3.read(read(path, String), Dict{String,Any})
mgit(root, args...) = read(`git -C $root $args`, String)
function mrequire(ok, why)
    ok || error(why)
    nothing
end
function msnapshot(x)
    io=IOBuffer(); serialize(io,x); bytes2hex(sha256(take!(io)))
end
function mpublic(x, root, reference)
    if x isa AbstractString
        replace(x, reference=>"<reference-root>", root=>"<workbench>", homedir()=>"<home>")
    elseif x isa NamedTuple || x isa AbstractDict
        Dict(string(k)=>mpublic(v,root,reference) for (k,v) in pairs(x))
    elseif x isa AbstractArray || x isa Tuple
        map(v->mpublic(v,root,reference),x)
    else
        x
    end
end
function mwrite(path, data;root,reference)
    bytes=JSON3.write(mpublic(data,root,reference))*"\n"
    JSON3.read(bytes); write(path*".tmp",bytes); mv(path*".tmp",path;force=true)
end
function checked_bytes(root, relative, spec)
    mrequire(!isabspath(relative) && !(".." in splitpath(relative)),"Unconfined source path")
    path=joinpath(root,relative)
    mrequire(isfile(path) && !islink(path),"Missing or symlinked source: $relative")
    bytes=read(path)
    mrequire(length(bytes)==spec["bytes"] && bytes2hex(sha256(bytes))==spec["sha256"],"Source bytes changed: $relative")
    bytes
end
function authenticate(root,reference,suite)
    mrequire(suite in ("REF-B0","REF-K4","CORE-B0","CORE-K4"),"Unknown static suite")
    for name in MEASUREMENT_PLAN_FILES
        relative=joinpath(MEASUREMENT_DIR,name)
        mrequire(read(joinpath(root,relative))==read(`git -C $root show $(MEASUREMENT_PREPARATION*":"*relative)`),"Prepared measurement contract changed")
    end
    sources=mjson(joinpath(root,MEASUREMENT_DIR,"sources.json"))
    mrequire(sources["base"]==MEASUREMENT_BASE,"Wrong reference source base")
    for (path,spec) in sources["frozen_inputs_and_history"]
        checked_bytes(root,path,spec)
    end
    mrequire(strip(mgit(reference,"rev-parse","HEAD"))==MEASUREMENT_BASE,"Reference checkout is not the accepted base")
    mrequire(isempty(strip(mgit(reference,"status","--porcelain","--untracked-files=all"))),"Reference checkout is dirty")
    for (path,spec) in sources["reference_implementation"]["files"]
        bytes=checked_bytes(reference,path,spec)
        mrequire(bytes==read(`git -C $reference show $(MEASUREMENT_BASE*":"*path)`),"Reference file differs from complete Git blob")
    end
    # There is intentionally no candidate alias or fallback before REF measurements.
    startswith(suite,"CORE-") && error("NOT_IMPLEMENTED: candidate measurement backend is not enabled")
    sources
end
function load_reference_modules(reference)
    entries=("scripts/workbench_environment.jl","scripts/upf_validation.jl","scripts/upf_runtime.jl",
        "prototypes/spinor/SpinorPrototype.jl","prototypes/relativistic/RelativisticProjectors.jl",
        "prototypes/fr_integration/FRIntegration.jl","prototypes/spinor/SpinorSCFPrototype.jl",
        "prototypes/soc_scf/SOCSCF.jl","prototypes/crystal_soc/SpinTrace.jl")
    for path in entries
        Base.include(Main,joinpath(reference,path))
    end
    collect(entries)
end

function original_endpoint(root,sources,label)
    spec=sources["historical_endpoints"][label]
    directory=joinpath(root,spec["directory"])
    resultpath=joinpath(directory,"result.json"); checkpoint=joinpath(directory,"final.bin")
    mrequire(isfile(resultpath) && !islink(resultpath) && msha(resultpath)==spec["raw_result_sha256"],"Original endpoint result is missing or changed")
    result=mjson(resultpath)
    mrequire(result["execution_status"]=="PASS" && result["exit_code"]===0 && result["execution_commit"]==spec["execution_commit"],"Historical endpoint was not a successful bound SCF")
    mrequire(isfile(checkpoint) && !islink(checkpoint) && filesize(checkpoint)==spec["checkpoint_bytes"] &&
        msha(checkpoint)==spec["checkpoint_sha256"]==result["checkpoint_sha256"],"Original checkpoint bytes are missing or changed")
    # The complete historical byte contract has passed before native deserialization.
    state=deserialize(checkpoint)
    mrequire(state isa NamedTuple && Set(keys(state))==Set((:n_in,:n_out,:X,:f,:eigenvalues,:mu,:final)),"Unexpected native final checkpoint container")
    mrequire(state.X isa Vector{Matrix{ComplexF64}} && state.f isa Vector{Vector{Float64}} &&
        state.eigenvalues isa Vector{Vector{Float64}},"Native orbital/occupation/level storage changed")
    mrequire(state.n_in isa Vector{Float64} && state.n_out isa Vector{Float64} && state.mu isa Float64 && isfinite(state.mu),"Native density/mu storage changed")
    nk=label=="B0" ? 8 : 64
    mrequire(length(state.X)==length(state.f)==length(state.eigenvalues)==nk,"Wrong original point count")
    mrequire(length(state.n_in)==length(state.n_out)==48^3 && all(isfinite,state.n_in) && all(isfinite,state.n_out),"Invalid original density")
    final=result["final"]
    for i in 1:nk
        x,f,e=state.X[i],state.f[i],state.eigenvalues[i]
        mrequire(size(x,2)==length(f)==length(e)==24 && all(isfinite,x) && all(isfinite,e) && all(v->isfinite(v)&&0<=v<=1,f),"Invalid original physical state")
        mrequire(isequal(f,Float64.(final["occupations"][i])) && isequal(e,Float64.(final["eigenvalues_ha"][i])),"Original f/e differ from bound endpoint")
    end
    FI=Main.FRIntegration
    mrequire(FI.integration_density_hash(state.n_in)==final["n_in_sha256"] && FI.integration_density_hash(state.n_out)==final["n_out_sha256"] && state.mu==final["mu_ha"],"Original n_in/n_out/mu identity mismatch")
    (;state,result,resultpath,checkpoint,spec)
end
physical_payload(state)=(;X=state.X,f=state.f,eigenvalues=state.eigenvalues,n_in=state.n_in,n_out=state.n_out,mu=state.mu)
function build_original_context(root,case,source)
    FI=Main.FRIntegration
    bundle=FI.load_bound_psp(root;source_spec=source)
    geometry=case["geometry"]
    lattice=reduce(hcat,Float64.(v) for v in geometry["lattice_vectors_bohr"])
    positions=[Float64.(v) for v in geometry["positions_fractional"]]
    points=[Float64.(v["coordinate_fractional"]) for v in case["kpoints"]]
    weights=Float64[v["weight_spatial"] for v in case["kpoints"]]
    ctx=FI.build_context(fill(bundle,length(positions)),lattice,positions,points,weights;
        Ecut=case["cutoffs"]["dftk_ecut_ha"],xc_identifiers=Symbol.(case["xc"]["dftk_identifiers"]),
        mode=:real_fr,temperature=case["electrons"]["temperature_ha"],smearing=DFTK.Smearing.FermiDirac(),fft_size=case["fft_size"])
    (;ctx,bundle)
end
function authenticate_basis(ctx,state,historical)
    FI=Main.FRIntegration;b=ctx.basis;old=historical["grid"]["basis"]
    actual=JSON3.read(JSON3.write(FI.basis_summary(ctx)),Dict{String,Any})
    mrequire(actual==old,"Reconstructed basis differs from historical full geometry/k/G-order receipt")
    mrequire(b.fft_size==(48,48,48) && b.model.n_electrons==8 && b.model.temperature==.001,"Fixed Si basis/temperature differs")
    for (i,k) in enumerate(b.kpoints)
        mrequire(size(state.X[i])==(2length(k.G_vectors),24),"Original orbital rows do not match the actual G order")
    end
    FI.check_energy_orbitals(b,state.X,state.f)
    mrequire(abs(b.dvol*sum(state.n_out)-8)<=1e-8,"Original density electron count differs")
    FI.validate_context(ctx)
end
function compact_consume(x)
    if x isa Number
        mrequire(isfinite(x),"Nonfinite consumed scalar")
        return (;real=Float64(real(x)),imaginary=Float64(imag(x)))
    elseif x isa AbstractArray{<:Number}
        mrequire(!isempty(x) && all(isfinite,x),"Empty/nonfinite consumed numerical output")
        return (;shape=Tuple(size(x)),sum_abs2=sum(abs2,x),first_real=Float64(real(first(x))),first_imaginary=Float64(imag(first(x))),last_real=Float64(real(last(x))),last_imaginary=Float64(imag(last(x))))
    elseif x isa NamedTuple || x isa AbstractDict
        return (;(Symbol(k)=>compact_consume(x[k]) for k in sort(collect(keys(x));by=string))...)
    elseif x isa AbstractArray || x isa Tuple
        return Tuple(map(compact_consume,x))
    end
    error("Unsupported numerical checksum payload")
end
function cold_report(t)
    Dict(string(k)=>getproperty(t,k) for k in propertynames(t) if k!=:value && getproperty(t,k) isa Number)
end
function save_payload(directory,name,value)
    path=joinpath(directory,name*".bin");mrequire(!ispath(path),"Refusing existing canonical payload")
    serialize(path,value)
    (;path=basename(path),sha256=msha(path),bytes=filesize(path),format="Julia 1.12.7 native Serialization; ignored private numerical outputs",source="Actual fixed-input measured operation, unshifted/unrenormalized")
end
function fixed_nonlocal(ctx,state)
    R=Main.RelativisticProjectors
    direct=R.nonlocal_energy(ctx.fr_blocks,state.X,ctx.basis.kweights,state.f)
    projected=R.projected_nonlocal_energy(ctx.fr_blocks,state.X,ctx.basis.kweights,state.f)
    mrequire(abs(direct-projected)/max(abs(direct),abs(projected),1)<=1e-11,"Independent projector contraction differs")
    (;direct_ha=direct,projected_ha=projected)
end
function energy_values(snapshot,state,basis)
    thermal=Main.SOCSCF.ensemble_free_energy(snapshot.total,state.f,basis.kweights,basis.model.temperature)
    (;terms_ha=snapshot.terms,internal_energy_ha=snapshot.total,free_energy_ha=thermal.free_energy_ha,
        entropy_energy_ha=thermal.entropy_energy_ha,entropy_dimensionless=thermal.entropy_dimensionless,
        R=snapshot.density.R,n=snapshot.density.n,m=snapshot.density.m,
        direct_kinetic_ha=snapshot.report.direct_kinetic_ha,nonlocal_ha=snapshot.nonlocal_decomposition.full_ha)
end
function fixed_energy(ctx,state)
    snapshot=Main.FRIntegration.energy_snapshot(ctx,state.X,state.f;expected_n=state.n_out,stream_k=true)
    Main.FRIntegration.assert_energy_consistency(snapshot)
    (;snapshot,values=energy_values(snapshot,state,ctx.basis))
end
function old_roots(;data=nothing,built=nothing,H=nothing,outputs=nothing,energy=nothing)
    FI=Main.FRIntegration
    (;data,built,H,outputs,energy,source_registry=FI._BOUND_PSP_SOURCES,context_registry=FI._FR_CONTEXT_CERTIFICATES)
end
function micro_rhs(state,contract)
    x=state.X[1]
    Dict(1=>copy(x[:,1]),24=>copy(x),30=>hcat(x,randn(MersenneTwister(contract["rhs_30_extra_columns"]["seed"]),ComplexF64,size(x,1),6)))
end
function micro_action!(Y,operator,X)
    mul!(Y,operator,X,1,0)
    Y
end
function reference_pipeline(root,case,source,state,rhs,historical)
    FI=Main.FRIntegration
    built=build_original_context(root,case,source);ctx=built.ctx
    authenticate_basis(ctx,state,historical)
    H=FI.build_full_hamiltonian(ctx,state.n_out)
    actions=Dict{String,Any}()
    for (label,operator) in (("FR",ctx.fr_blocks[1]),("component",H.full[1].common),("full_H",H.full[1]))
        for n in (1,24,30)
            Y=similar(rhs[n]);micro_action!(Y,operator,rhs[n]);actions["$(label)_$n"]=Y
        end
    end
    density=FI.orbital_density(ctx.basis,state.X,state.f;stream_k=true)
    nl=fixed_nonlocal(ctx,state);energy=fixed_energy(ctx,state)
    FI.validate_context(ctx);FI.assert_bound_sources(built.bundle)
    (;values=(;actions,density,nonlocal=nl,energy=energy.values),built,H,energy=energy.snapshot)
end

function run_loaded(root,reference,suite,outdir,result,sources)
    FI=Main.FRIntegration;WE=Main.WorkbenchEnvironment
    identity=WE.environment_identity(root,(DFTK,PseudoPotentialIO))
    result["environment"]=identity; mrequire(identity.status=="PASS","Frozen loaded environment mismatch")
    mrequire(VERSION==v"1.12.7","Native Serialization requires frozen Julia1.12.7")
    DFTK.disable_threading()
    result["parallelism"]=(;julia=Threads.nthreads(),blas=BLAS.get_num_threads(),fft=DFTK.FFTW.get_num_threads(),mpi=DFTK.mpi_nprocs(DFTK.MPI.COMM_WORLD))
    mrequire(all(==(1),values(result["parallelism"])),"Single Julia/BLAS/FFT/MPI execution required")
    label=split(suite,'-')[2];endpoint=original_endpoint(root,sources,label);state=endpoint.state
    casepath=label=="B0" ? "benchmarks/si-soc-splitting-v1/case.json" : "benchmarks/si-soc-sensitivity-v1/K4/case.json"
    case=mjson(joinpath(root,casepath));source=mjson(joinpath(root,"benchmarks/si-soc-splitting-v1/source.json"))
    contract=mjson(joinpath(root,MEASUREMENT_DIR,"contract.json"))
    Main.SOCSCF.validate_soc_settings(case["settings"];case_contract=label=="K4" ? case : nothing)
    payload=physical_payload(state);before=msnapshot(payload);rhs=micro_rhs(state,contract);rhs_before=msnapshot(rhs)
    result["input"]=(;historical_status="HISTORICAL_REUSED",historical_execution_commit=endpoint.spec["execution_commit"],
        checkpoint_sha256=endpoint.spec["checkpoint_sha256"],checkpoint_bytes=endpoint.spec["checkpoint_bytes"],raw_result_sha256=endpoint.spec["raw_result_sha256"],
        physical_payload_sha256=before,case_sha256=msha(joinpath(root,casepath)),native_type=string(typeof(state)),
        k_count=length(state.X),target_states=24,n_in_sha256=FI.integration_density_hash(state.n_in),n_out_sha256=FI.integration_density_hash(state.n_out),
        no_eigensolve=true,no_occupation_solve=true,no_scf=true)
    result["canonical_inputs"]=save_payload(outdir,"inputs",payload)
    result["measurements"]=Dict{String,Any}();result["outputs"]=Dict{String,Any}();result["live_memory"]=Dict{String,Any}()
    persist()=mwrite(joinpath(outdir,"worker-result.json"),result;root,reference)
    persist()
    cold=@timed build_original_context(root,case,source)
    built=cold.value;ctx=built.ctx
    result["cold_initialization"]=Dict("context_construction"=>cold_report(cold))
    authenticate_basis(ctx,state,endpoint.result)
    result["live_memory"]["context_ready"]=SOCCoreMemory.unique_memory(old_roots(data=payload,built=built))
    hcold=@timed FI.build_full_hamiltonian(ctx,state.n_out);H=hcold.value
    result["cold_initialization"]["H_construction"]=cold_report(hcold)
    result["live_memory"]["H_constructed"]=SOCCoreMemory.unique_memory(old_roots(data=payload,built=built,H=H))
    result["live_memory"]["one_static_solve_storage_proxy_no_eigensolve"]=SOCCoreMemory.unique_memory(old_roots(data=(;payload,rhs),built=built,H=H))
    result["live_memory_scope"]="Separate untimed observations of actual retained roots; static 30-column proxy is not an eigensolve; old registrations stay live until worker exit"
    function measure(name,f;consume=compact_consume,canonical=Base.identity)
        result["active_operation"]=name;persist()
        try
            measured=SOCCoreMemory.measure_operation(f;consume,name,warmup=1,samples=5)
            result["measurements"][name]=measured.report
            mrequire(Sys.maxrss()<8*1024^3,"RESOURCE_BLOCKED: Julia peak RSS reached8GiB")
            result["outputs"][name]=save_payload(outdir,name,canonical(measured.last_value))
            persist();measured.last_value
        catch err
            if hasproperty(err,:partial_report)
                result["measurements"][name]=getproperty(err,:partial_report);persist()
            end
            rethrow()
        end
    end
    for (name,op) in (("FR",ctx.fr_blocks[1]),("component",H.full[1].common),("full_H",H.full[1]))
        for n in (1,24,30)
            Y=similar(rhs[n]);fill!(Y,ComplexF64(NaN,NaN))
            before_counts=FI.full_operator_stats(H.full[1])
            measure("$(name)_$n",()->micro_action!(Y,op,rhs[n]))
            method=which(mul!,Tuple{typeof(Y),typeof(op),typeof(rhs[n]),Int,Int})
            result["measurements"]["$(name)_$n"]["dispatch"]=(;receiver_type=string(typeof(op)),module_name=string(method.module),source=string(method.file),line=method.line,
                call_count_including_warmup=6,columns_per_call=n,standalone_FR_counter="No native counter; direct six sampler calls",before_counts,after_counts=FI.full_operator_stats(H.full[1]))
        end
    end
    density=measure("density",()->FI.orbital_density(ctx.basis,state.X,state.f;stream_k=true))
    result["live_memory"]["density"]=SOCCoreMemory.unique_memory(old_roots(data=(;payload,rhs),built=built,H=H,outputs=density))
    measure("nonlocal",()->fixed_nonlocal(ctx,state))
    energy=measure("energy",()->fixed_energy(ctx,state);consume=x->compact_consume(x.values),canonical=x->x.values)
    result["live_memory"]["energy"]=SOCCoreMemory.unique_memory(old_roots(data=(;payload,rhs),built=built,H=H,outputs=density,energy=energy))
    FI.validate_context(ctx);FI.assert_bound_sources(built.bundle)
    result["live_memory"]["callback_or_save_boundary"]=SOCCoreMemory.unique_memory(old_roots(data=(;payload,rhs),built=built,H=H,outputs=density,energy=energy))
    pipeline=measure("pipeline",()->reference_pipeline(root,case,source,state,rhs,endpoint.result);consume=x->compact_consume(x.values),canonical=x->x.values)
    result["live_memory"]["next_map_boundary"]=SOCCoreMemory.unique_memory(old_roots(data=(;payload,rhs),built=built,H=H,outputs=(;density,pipeline),energy=energy))
    # Deliberately do not empty the historical registries or force GC.
    result["live_memory"]["session_closed"]=SOCCoreMemory.unique_memory(old_roots(data=(;payload,rhs),built=built,H=H,outputs=(;density,pipeline),energy=energy))
    result["legacy_lifetime"]=(;close_api="NONE",global_source_registrations=length(FI._BOUND_PSP_SOURCES),global_context_registrations=length(FI._FR_CONTEXT_CERTIFICATES),
        expected_contexts=7,registry_cleared=false,forced_gc=false,release_boundary="Julia process exit; session_closed observes legacy retained roots")
    mrequire(length(FI._FR_CONTEXT_CERTIFICATES)==7,"Unexpected legacy context lifetime count")
    result["input_unchanged"]=(;payload=msnapshot(payload)==before,rhs=msnapshot(rhs)==rhs_before,checkpoint=msha(endpoint.checkpoint)==endpoint.spec["checkpoint_sha256"],original_result=msha(endpoint.resultpath)==endpoint.spec["raw_result_sha256"])
    mrequire(all(values(result["input_unchanged"])),"Original input or operator-only probes changed")
    mrequire(length(result["measurements"])==13,"Incomplete static operation matrix")
    FI.validate_context(ctx);FI.assert_bound_sources(built.bundle)
    authenticate(root,reference,suite)
    mrequire(WE.environment_identity(root,(DFTK,PseudoPotentialIO)).status=="PASS","Loaded environment changed")
    result["active_operation"]=nothing
    mrequire(Sys.maxrss()<8*1024^3,"RESOURCE_BLOCKED: Julia peak RSS reached8GiB")
    result["measurement_status"]="COMPLETE";result["execution_status"]="PASS";result["overall_status"]="PASS";result["exit_code"]=0
    nothing
end

function measurement_main(args)
    args==["--help"] && (println("measure.jl --root ORIGINAL_ROOT --code-root DETACHED_REFERENCE_ROOT --suite REF-B0|REF-K4 --output NEW_OUTDIR; CORE labels fail NOT_IMPLEMENTED until enabled after REF");return 0)
    expected=Set(("--root","--code-root","--suite","--output"))
    if length(args)!=8 || Set(args[1:2:end])!=expected
        println(stderr,"Expected exactly --root, --code-root, --suite and --output");return 9
    end
    options=Dict(args[i]=>args[i+1] for i in 1:2:8)
    suite=options["--suite"];root=realpath(options["--root"]);reference=realpath(options["--code-root"]);outdir=normpath(abspath(options["--output"]))
    mrequire(startswith(outdir,joinpath(root,".work/phase9a")*"/"),"Measurements require a new ignored Phase9A directory")
    mrequire(!islink(outdir),"Measurement output cannot be a symlink")
    mkpath(outdir);mrequire(realpath(outdir)==outdir,"Measurement output cannot use a path alias")
    # The durable launcher owns result.json/preflight.json in this directory.
    # No existing worker result or prior canonical output is ever reused.
    outputs=vcat(["worker-result.json","worker-result.json.tmp","inputs.bin","density.bin","nonlocal.bin","energy.bin","pipeline.bin"],
        ["$(name)_$n.bin" for name in ("FR","component","full_H") for n in (1,24,30)])
    mrequire(all(!ispath(joinpath(outdir,name)) for name in outputs),"Existing measurement worker output is never reused")
    result=Dict{String,Any}("schema_version"=>1,"phase"=>"9A","suite"=>suite,"run_id"=>basename(outdir),"started_utc"=>string(now(UTC)),
        "base_commit"=>MEASUREMENT_BASE,"preparation_commit"=>MEASUREMENT_PREPARATION,"execution_status"=>"RUNNING","overall_status"=>"RUNNING","exit_code"=>9,
        "measurement_status"=>"NOT_RUN","backend"=>"LEGACY_REFERENCE","comparison_status"=>"NOT_RUN","evidence_level"=>"RUNNER_REPORTED_PRIVATE_ARRAY_EVALUATION")
    mwrite(joinpath(outdir,"worker-result.json"),result;root,reference)
    try
        execution=strip(mgit(root,"rev-parse","HEAD"));result["execution_commit"]=execution
        mrequire(isempty(strip(mgit(root,"status","--porcelain"))),"Measurement harness execution tree must be clean")
        for file in ("measure.jl","memory.jl")
            path=joinpath(MEASUREMENT_DIR,file)
            mrequire(read(joinpath(root,path))==read(`git -C $root show $(execution*":"*path)`),"Measurement harness not committed at execution HEAD")
        end
        result["harness_sources"]=Dict(file=>msha(joinpath(root,MEASUREMENT_DIR,file)) for file in ("measure.jl","memory.jl"))
        sources=authenticate(root,reference,suite)
        result["reference_source_sha256"]=sources["reference_implementation"]["files"]
        result["included_entry_modules"]=load_reference_modules(reference)
        Base.invokelatest(run_loaded,root,reference,suite,outdir,result,sources)
        mrequire(strip(mgit(root,"rev-parse","HEAD"))==execution,"Harness execution HEAD changed")
    catch err
        result["execution_status"]="FAIL";result["overall_status"]="FAIL";result["exit_code"]=9;result["reason"]=sprint(showerror,err)
        result["measurement_status"]="INCOMPLETE";showerror(stderr,err,catch_backtrace());println(stderr)
    end
    result["finished_utc"]=string(now(UTC));result["peak_rss_bytes"]=Sys.maxrss()
    try
        mwrite(joinpath(outdir,"worker-result.json"),result;root,reference)
    catch err
        println(stderr,"PERSISTENCE FAILURE: ",sprint(showerror,err));return 9
    end
    println(JSON3.write((;run_id=result["run_id"],suite,overall_status=result["overall_status"],execution_status=result["execution_status"],exit_code=result["exit_code"])))
    result["exit_code"]
end
function safe_measurement_main(args)
    try
        measurement_main(args)
    catch err
        println(stderr,"MEASUREMENT WRAPPER FAILURE: ",sprint(showerror,err));return 9
    end
end
abspath(PROGRAM_FILE)==(@__FILE__) && exit(safe_measurement_main(ARGS))
