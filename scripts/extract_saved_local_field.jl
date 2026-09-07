#!/usr/bin/env julia
# Only trusted saved arrays and FFT arithmetic. No model, potential or XC evaluation.
module SavedLocalFieldExtraction
using DFTK, PseudoPotentialIO, LinearAlgebra, SHA, JSON3, Serialization
include("extract_soc_density.jl")
const SD = SOCDensityExtraction
const ROOT = SD.ROOT
const EVIDENCE = "results/mg-soc-energy-reference/evidence.json"
const COMMON = "results/mg-soc-energy-reference/common-terms.json"
const OLD_PLAN = "benchmarks/mg-soc-energy-reference-v1/plan.json"
const SOURCE_RUN = "20260907T144446657126Z-8fa3b4d2"
const SOURCE_FIELDS = (:evaluations, :reconstructed_complex, :native_millers, :local_nbar)
const EVALUATIONS = ("A_original_n_out", "B_original_n_out", "Q_rep", "A_reconstructed", "B_reconstructed")
const ARRAY_FIELDS = (:n, :vxc, :local_potential, :gradient, :sigma)
array_hash(x::Array) = bytes2hex(sha256(reinterpret(UInt8, vec(x))))
normalized(a,b) = norm(a-b)/max(norm(a),norm(b),1.0)
asdict(x) = JSON3.read(JSON3.write(x), Dict{String,Any})

"""Hash authentication precedes Julia deserialization, which is not a sandbox.

The frozen producer serialized one plain array container. Julia necessarily
materializes its other arrays; this reader never evaluates or uses vxc/gradients.
"""
function trusted_arrays(path, expected_sha; reader=Serialization.deserialize)
    before=SD.checked_file(path,expected_sha)
    raw=open(path,"r") do io
        value=reader(io)
        eof(io) || error("Trailing data after saved array container")
        value
    end
    SD.checked_file(path,before)
    raw isa NamedTuple && keys(raw)==SOURCE_FIELDS || error("Wrong Phase 7D array container")
    SD.require_plain(raw)
    raw.evaluations isa Dict && Set(keys(raw.evaluations))==Set(EVALUATIONS) || error("Incomplete saved evaluation set")
    for fields in values(raw.evaluations)
        fields isa NamedTuple && keys(fields)==ARRAY_FIELDS || error("Wrong saved field layout")
    end
    raw
end

"""Ordinary Fourier coefficients: FFT(field)/N, with no weights or factors.

DFTK src/fft.jl:24-29 defines the native Miller ordering; lines 71-77
normalize its forward FFT by sqrt(Omega)/N, hence division by sqrt(Omega).
The independent direct sums use first-index-fast physical nodes, no FFT helper.
"""
function field_fourier(field, shape, volume, points, tolerance)
    shape isa NTuple{3,Int} && all(>(0),shape) || error("Positive integer grid required")
    field isa Vector{Float64} && length(field)==prod(shape) && all(isfinite,field) || error("Finite flat Float64 field required")
    volume isa Real && !(volume isa Bool) && isfinite(volume) && volume>0 || error("Positive finite volume required")
    omega=Float64(volume);grid=DFTK.FFTGrid(shape,omega,DFTK.CPU())
    millers=[Tuple(g) for g in vec(DFTK.G_vectors(grid))]
    coeff=vec(DFTK.fft(grid,reshape(field,shape)))/sqrt(omega)
    back=vec(DFTK.ifft(grid,reshape(sqrt(omega)*coeff,shape)))
    all(isfinite,coeff) && all(isfinite,back) || error("Nonfinite FFT result")
    lookup=Dict(m=>i for (i,m) in enumerate(millers))
    length(points)>=15 && length(unique(Tuple.(points)))==length(points) || error("At least 15 distinct predeclared Fourier probes required")
    checks=map(points) do p
        length(p)==3 && all(x->x isa Integer && !(x isa Bool),p) || error("Integer Miller probe required")
        m=Tuple(Int.(p));haskey(lookup,m) || error("Non-native Fourier probe")
        direct=SD.direct_coefficient(field,shape,m);fft=coeff[lookup[m]]
        (;miller=collect(m),direct=[real(direct),imag(direct)],fft=[real(fft),imag(fft)],
          absolute_error=abs(direct-fft),normalized_error=normalized(direct,fft))
    end
    realnorm=omega/length(field)*sum(abs2,field);fouriernorm=omega*sum(abs2,coeff)
    report=(;status="PASS",coefficient_count=length(coeff),mean=sum(field)/length(field),
        g0=[real(coeff[1]),imag(coeff[1])],real_l2_squared=realnorm,fourier_l2_squared=fouriernorm,
        parseval_normalized=normalized(realnorm,fouriernorm),
        complex_roundtrip_normalized=normalized(back,field),roundtrip_imaginary_max=maximum(abs,imag.(back)),
        direct_checks=checks,normalization="ordinary Fourier series: DFTK.fft(field)/sqrt(Omega) = FFT(field)/Ngrid",
        convention="Original zero-origin nodes; first index fastest; all native bins including G=0 and Nyquist")
    report.parseval_normalized<=tolerance && report.complex_roundtrip_normalized<=tolerance &&
        all(x->x.normalized_error<=tolerance,checks) || error("Field FFT/direct/Parseval check failed")
    (;millers,coefficients=coeff,report)
end

function saved_fields(raw, metadata, physical, thresholds, points)
    shape=Tuple(Int.(physical["fft_size"]));volume=Float64(physical["volume_bohr3"])
    ngrid=prod(shape);dvol=volume/ngrid;wanted=("A_original_n_out","B_original_n_out","Q_rep")
    metadata["basis"]["fft_size"]==collect(shape) && metadata["basis"]["volume_bohr3"]==volume || error("Saved physical grid mismatch")
    fields=Dict{String,Vector{Float64}}();checks=Dict{String,Any}();spectra=Dict{String,Any}()
    localpotential=nothing
    for (label,name) in zip(("A","B","Q"),wanted)
        saved=raw.evaluations[name];old=metadata["evaluations"][name]
        old["status"]=="PASS" || error("Historical evaluation not successful")
        for key in (:n,:local_potential)
            a=getproperty(saved,key)
            a isa Vector{Float64} && length(a)==ngrid && all(isfinite,a) || error("Invalid saved $key array")
            array_hash(a)==old["array_sha256"][string(key)] || error("Saved $key source hash mismatch")
        end
        if isnothing(localpotential)
            localpotential=saved.local_potential
        else
            saved.local_potential==localpotential || error("Different saved local potentials across densities")
        end
        old["density"]["sha256"]==array_hash(saved.n) || error("Saved density receipt mismatch")
        spectrum=field_fourier(saved.n,shape,volume,points,thresholds["fft_normalized"])
        spectra[label]=spectrum;fields["n_"*label]=saved.n
        ne=dvol*sum(saved.n);energy=dvol*dot(saved.n,saved.local_potential)
        abs(ne-physical["expected_electrons"])<=thresholds["electron_count_abs"] || error("Saved electron count mismatch")
        abs(energy-old["atomic_local_ha"])<=thresholds["saved_local_energy_abs_ha"] || error("Historical local energy not restored")
        mean=sum(saved.local_potential)/ngrid
        abs(mean-old["local_mean_ha"])<=thresholds["saved_local_mean_abs_ha"] || error("Historical local mean not restored")
        checks[label]=(;status="PASS",source_evaluation=name,n_sha256=array_hash(saved.n),
            potential_sha256=array_hash(saved.local_potential),electron_count=ne,
            local_integral_ha=energy,historical_atomic_local_ha=old["atomic_local_ha"],
            integral_minus_historical_ha=energy-old["atomic_local_ha"],mean_ha=mean,
            historical_mean_ha=old["local_mean_ha"],density_fft=spectrum.report)
    end
    fields["V_D"]=localpotential
    vf=field_fourier(localpotential,shape,volume,points,thresholds["fft_normalized"])
    raw.native_millers==vf.millers || error("Saved native Miller order/grid mismatch")
    raw.local_nbar isa Vector{ComplexF64} && length(raw.local_nbar)==ngrid && all(isfinite,raw.local_nbar) || error("Wrong saved local Fourier array")
    err=normalized(raw.local_nbar,vf.coefficients)
    err<=thresholds["fft_normalized"] || error("Saved ordinary local coefficients not restored")
    for label in ("A","B","Q")
        fourier_energy=volume*real(dot(spectra[label].coefficients,vf.coefficients))
        difference=fourier_energy-checks[label].local_integral_ha
        abs(difference)<=thresholds["local_parseval_abs_ha"] || error("Real/Fourier local integral mismatch")
        checks[label]=merge(checks[label],(;local_fourier_integral_ha=fourier_energy,real_fourier_difference_ha=-difference))
    end
    (;fields,millers=vf.millers,coefficients=vf.coefficients,
      report=(;status="PASS",fft_size=collect(shape),volume_bohr3=volume,origin_fractional=[0,0,0],
        physical_node_count=ngrid,local_fft=vf.report,local_nbar_restoration_normalized=err,
        saved_local_nbar_sha256=array_hash(raw.local_nbar),saved_density_checks=checks,
        units=(;density="electron/bohr^3",potential="Ha",potential_coefficients="Ha",energy="Ha/cell",
            density_l2_squared="electron^2/bohr^3",potential_l2_squared="Ha^2 bohr^3"),
        applied_mean_shift=false,applied_density_normalization=false,
        unused_fields="Serialized vxc, gradient and sigma materialized by the plain container reader but not used in any evaluation"))
end

function bind_source(plan, directory, identity)
    tracked=Dict{String,String}()
    for path in (EVIDENCE,COMMON,OLD_PLAN)
        haskey(plan["source_sha256"],path) || error("Required public source not predeclared")
    end
    for (path,hash) in plan["source_sha256"]
        full=SD.resolve_path(path);tracked[full]=SD.checked_file(full,hash)
        filesize(full)==plan["source_bytes"][path] || error("Public source byte count mismatch")
    end
    evidence=SD.read_json(joinpath(ROOT,EVIDENCE));public=SD.read_json(joinpath(ROOT,COMMON))
    oldplan=SD.read_json(joinpath(ROOT,OLD_PLAN))
    evidence["run_id"]==SOURCE_RUN && evidence["execution_status"]=="PASS" &&
        evidence["julia_exit_code"]==evidence["runner_exit_code"]==0 || error("Wrong historical successful run")
    for name in ("result.json","common/metadata.json","common/arrays.bin")
        full=joinpath(directory,name);tracked[full]=SD.checked_file(full,evidence["execution_logs"][name])
    end
    receipt=SD.read_json(joinpath(directory,"result.json"));metadata=SD.read_json(joinpath(directory,"common/metadata.json"))
    receipt["run_id"]==metadata["run_id"]==public["run_id"]==SOURCE_RUN || error("Mixed historical run receipts")
    receipt["execution_status"]==metadata["execution_status"]==public["execution_status"]=="PASS" || error("Failed historical field source")
    receipt["exit_code"]==receipt["julia_exit_code"]==metadata["exit_code"]==0 || error("Historical process failure")
    receipt["source_preservation_status"]==metadata["source_unchanged_status"]=="PASS" || error("Historical sources were changed")
    receipt["execution_commit"]==evidence["execution_commit"] || error("Wrong historical execution commit")
    receipt["plan_sha256"]==metadata["plan_sha256"]==evidence["plan_sha256"]==SD.filehash(joinpath(ROOT,OLD_PLAN)) || error("Wrong historical plan")
    for name in ("common/metadata.json","common/arrays.bin")
        receipt["outputs_sha256"][name]==evidence["execution_logs"][name] || error("Receipt output hash mismatch")
    end
    metadata["local_arrays"]["sha256"]==evidence["execution_logs"]["common/arrays.bin"] || error("Array/metadata identity mismatch")
    key="scripts/evaluate_common_energy_terms.jl"
    metadata["executed_script_sha256"]==receipt["execution_source_sha256"][key]==evidence["execution_source_sha256"][key] || error("Producer code identity mismatch")
    code=read(`git -C $ROOT show $(evidence["execution_commit"]*":"*key)`)
    bytes2hex(sha256(code))==metadata["executed_script_sha256"] || error("Producer code differs from recorded Git object")
    isequal(plan["physical"],oldplan["physical"]) || error("Physical case changed")
    historical_env=metadata["environment"]
    historical_env["julia_version"]==string(VERSION)=="1.12.7" || error("Wrong serialization Julia version")
    asdict(SD.WorkbenchEnvironment.public_data(identity,ROOT))==historical_env || error("Loaded frozen environment differs from producer")
    metadata["environment_recheck_status"]=="PASS" || error("Producer environment changed")
    for key in ("basis","constants","evaluations","original_sources","local_arrays")
        metadata[key]==public[key] || error("Public/raw common receipt differs: $key")
    end
    (;metadata,evidence,tracked,arrays_path=joinpath(directory,"common/arrays.bin"),
      provenance=(;source_run_id=SOURCE_RUN,source_execution_commit=evidence["execution_commit"],
        source_evidence_path=EVIDENCE,source_evidence_sha256=plan["source_sha256"][EVIDENCE],
        arrays_sha256=evidence["execution_logs"]["common/arrays.bin"],
        metadata_sha256=evidence["execution_logs"]["common/metadata.json"],
        receipt_sha256=evidence["execution_logs"]["result.json"],
        historical_archive=evidence["backup"],production_julia_version=historical_env["julia_version"],
        producer_script_sha256=metadata["executed_script_sha256"]))
end

function write_outputs(outdir,data)
    native=joinpath(outdir,"native.csv")
    open(native,"w") do io
        println(io,"m1,m2,m3,V_D_real,V_D_imag")
        for (m,z) in zip(data.millers,data.coefficients)
            println(io,join((m...,repr(real(z)),repr(imag(z))),','))
        end
    end
    fields=joinpath(outdir,"fields.csv")
    open(fields,"w") do io
        println(io,"n_A,n_B,n_Q,V_D")
        for i in eachindex(data.fields["V_D"])
            println(io,join((repr(data.fields[k][i]) for k in ("n_A","n_B","n_Q","V_D")),','))
        end
    end
    # Verify actual persisted bytes against every source value, including signed
    # zeros. The public coefficient table must not be a partial mode selection.
    open(native,"r") do io
        readline(io)=="m1,m2,m3,V_D_real,V_D_imag" || error("Native CSV header changed")
        for (m,z) in zip(data.millers,data.coefficients)
            row=split(readline(io),',');length(row)==5 || error("Native CSV row width changed")
            Tuple(parse.(Int,row[1:3]))==m || error("Native Miller round-trip failed")
            isequal(complex(parse(Float64,row[4]),parse(Float64,row[5])),z) || error("Native coefficient round-trip failed")
        end
        eof(io) || error("Extra native CSV rows")
    end
    open(fields,"r") do io
        readline(io)=="n_A,n_B,n_Q,V_D" || error("Field CSV header changed")
        for i in eachindex(data.fields["V_D"])
            row=split(readline(io),',');length(row)==4 || error("Field CSV row width changed")
            for (j,k) in enumerate(("n_A","n_B","n_Q","V_D"))
                isequal(parse(Float64,row[j]),data.fields[k][i]) || error("Saved field round-trip failed")
            end
        end
        eof(io) || error("Extra field CSV rows")
    end
    (;native=(;path="native.csv",sha256=SD.filehash(native),rows=length(data.millers)),
      fields=(;path="fields.csv",sha256=SD.filehash(fields),rows=length(data.millers),scope="LOCAL_ONLY; original point arrays for companion checks"))
end

function extract_request!(result,request,outdir)
    request["schema_version"]==1 || error("Unsupported request schema")
    planpath=SD.resolve_path(request["plan_path"]);SD.checked_file(planpath,request["plan_sha256"])
    plan=SD.read_json(planpath);result["plan_sha256"]=request["plan_sha256"]
    identity=SD.environment_identity(ROOT,(DFTK,PseudoPotentialIO));identity.status=="PASS" || error("Frozen environment mismatch")
    result["environment"]=identity;result["executed_script_sha256"]=SD.filehash(@__FILE__)
    DFTK.disable_threading()
    Threads.nthreads()==BLAS.get_num_threads()==DFTK.mpi_nprocs(DFTK.MPI.COMM_WORLD)==1 || error("One process and thread required")
    directory=SD.resolve_path(get(request,"source_run_directory",joinpath(".work","phase7d",SOURCE_RUN)))
    binding=bind_source(plan,directory,identity);result["source_binding"]=binding.provenance
    raw=trusted_arrays(binding.arrays_path,binding.provenance.arrays_sha256)
    data=saved_fields(raw,binding.metadata,plan["physical"],plan["thresholds"],plan["direct_fourier_miller_points"])
    result["field_checks"]=data.report;result["constants"]=binding.metadata["constants"]
    result["outputs"]=write_outputs(outdir,data)
    for (path,hash) in binding.tracked;SD.checked_file(path,hash);end
    SD.checked_file(planpath,request["plan_sha256"])
    SD.environment_identity(ROOT,(DFTK,PseudoPotentialIO))==identity || error("Environment changed during extraction")
    result["source_preservation_status"]="PASS";result["DFTK_saved_local_field_status"]="PASS"
    result["execution_status"]="PASS"
    nothing
end

function main(args)
    args==["--help"] && (println("Usage: extract_saved_local_field.jl REQUEST.json NEW_IGNORED_DIR\nTrusted saved fields and FFT only; no model, XC, SCF or eigensolve.");return 0)
    length(args)==2 || (println(stderr,"Expected REQUEST.json NEW_IGNORED_DIR");return 2)
    outdir=abspath(args[2])
    (!ispath(outdir) && startswith(outdir,joinpath(ROOT,".work")*"/")) || (println(stderr,"Use a new ignored .work directory");return 2)
    result=Dict{String,Any}("schema_version"=>1,"phase"=>"7E","execution_status"=>"RUNNING",
        "data_status"=>"NEW_EXTRACTION_FROM_HISTORICAL_SAVED_FIELDS","new_scf_status"=>"NOT_RUN",
        "new_eigensolve_status"=>"NOT_RUN","new_xc_evaluation_status"=>"NOT_RUN","new_potential_evaluation_status"=>"NOT_RUN")
    code=1
    try
        mkpath(outdir);request=SD.read_json(args[1]);result["run_id"]=request["run_id"]
        extract_request!(result,request,outdir);code=0
    catch err
        result["execution_status"]=err isa SD.MissingSource ? "BLOCKED_MISSING_SOURCE" : "FAIL"
        result["failure_reason"]=sprint(showerror,err);showerror(stderr,err,catch_backtrace());println(stderr)
    end
    result["exit_code"]=code
    try
        write(joinpath(outdir,"summary.txt"),"$(get(result,"run_id",basename(outdir))): $(result["execution_status"]), exit=$code\n")
        SD.write_json(joinpath(outdir,"metadata.json"),result)
    catch err
        code=1;println(stderr,"Persistence failure: ",sprint(showerror,err))
        try SD.write_json(joinpath(outdir,"metadata.json"),Dict("schema_version"=>1,"phase"=>"7E","execution_status"=>"FAIL","exit_code"=>1,"failure_reason"=>"Persistence failure")) catch
            println(stderr,"Unable to persist safe failure record")
        end
    end
    code
end
end
abspath(PROGRAM_FILE)==(@__FILE__) && exit(SavedLocalFieldExtraction.main(ARGS))
