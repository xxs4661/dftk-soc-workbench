#!/usr/bin/env julia
# Phase 7C: trusted historical arrays -> native Fourier coefficients. No electronic solve.
module SOCDensityExtraction
using DFTK, PseudoPotentialIO, LinearAlgebra, SHA, JSON3, Serialization, Dates
include("workbench_environment.jl")
using .WorkbenchEnvironment

const ROOT = realpath(joinpath(@__DIR__, ".."))
const CHECKPOINT_FIELDS = (:X, :f, :eigenvalues, :n_in, :n_out, :R, :m, :final)
struct MissingSource <: Exception
    reason::String
end
Base.showerror(io::IO, e::MissingSource) = print(io, e.reason)

density_hash(n::Array{Float64}) = bytes2hex(sha256(reinterpret(UInt8, vec(n))))
resolve_path(path) = isabspath(path) ? path : joinpath(ROOT, path)
read_json(path) = JSON3.read(read(path, String), Dict{String,Any})

function checked_file(path, expected_sha)
    expected_sha isa String && occursin(r"^[0-9a-f]{64}$", expected_sha) ||
        error("A complete SHA-256 binding is required")
    isfile(path) || throw(MissingSource("Required source file is missing: $(basename(path))"))
    actual = filehash(path)
    actual == expected_sha || error("Source SHA-256 mismatch: $(basename(path))")
    actual
end

"""Allow only the producer's plain data graph; never recover a serialized context.

This is a post-read type check, not a sandbox for Serialization. The original
historical SHA must be authenticated before deserialize is invoked at all.
"""
function require_plain(x)
    if x === nothing || x isa Union{String,Symbol,Bool,Int64,Int32,UInt64,UInt32,UInt8,Float64,ComplexF64}
        x isa Number && !isfinite(x) && error("Nonfinite checkpoint value")
    elseif x isa NamedTuple || x isa Tuple
        foreach(require_plain, x)
    elseif x isa Array
        if eltype(x) in (Float64, ComplexF64, Int64, Int32, Bool)
            all(isfinite, x) || error("Nonfinite checkpoint array")
        else
            foreach(require_plain, x)
        end
    elseif x isa Dict
        all(k -> k isa Union{String,Symbol}, keys(x)) || error("Non-plain metadata key")
        foreach(require_plain, values(x))
    else
        error("Unsupported checkpoint object type: $(typeof(x))")
    end
    nothing
end

function trusted_checkpoint(path, expected_sha; reader=Serialization.deserialize)
    before = checked_file(path, expected_sha)  # mandatory before reader, also in negative tests
    state = open(path, "r") do io
        value = reader(io)
        eof(io) || error("Trailing data after the single checkpoint object")
        value
    end
    checked_file(path, before)
    state isa NamedTuple && keys(state) == CHECKPOINT_FIELDS ||
        error("Expected exactly the Phase 6C final.bin plain NamedTuple fields")
    require_plain(state)
    state
end

function bound_densities(state, endpoint, fft_size, dvol, thresholds)
    length(fft_size) == 3 && all(x -> x isa Integer && x > 0, fft_size) || error("Invalid FFT shape")
    for name in (:n_in, :n_out)
        n = getproperty(state, name)
        n isa Vector{Float64} && length(n) == prod(fft_size) ||
            error("$name must be the unchanged flat Float64 producer array on this grid")
        all(isfinite, n) || error("Nonfinite $name")
        key = string(name) * "_sha256"
        density_hash(n) == endpoint[key] == getproperty(state.final, Symbol(key)) ||
            error("$name density hash differs from its bound endpoint (state swap is forbidden)")
    end
    state.final.map_count == endpoint["map_count"] || error("Checkpoint map_count mismatch")
    state.final.target_states == endpoint["target_states"] || error("Checkpoint target-state count mismatch")
    state.final.unmixed_residual_l2 == endpoint["unmixed_residual_l2"] ||
        error("Checkpoint and endpoint closure records differ")
    # Same norm and same unchanged arrays as prototypes/spinor/scf.jl:72.
    closure = sqrt(dvol) * norm(state.n_out - state.n_in)
    difference = abs(closure - endpoint["unmixed_residual_l2"])
    (; n_in=state.n_in, n_out=state.n_out,
       closure=(; status=difference <= thresholds["closure_l2_abs"] ? "PASS" : "FAIL",
           recomputed_l2=closure, historical_l2=endpoint["unmixed_residual_l2"],
           absolute_difference=difference, units="electron/bohr^(3/2)",
           formula="sqrt(Omega/Ngrid) * norm(n_out - n_in)",
           map_count=endpoint["map_count"], public_replay="NOT_AVAILABLE_WITHOUT_N_IN_ARRAY"))
end

# A separate pointwise DFT with compensated real/imaginary accumulation. It does
# not call FFTGrid.r_vectors, FFTW, the production FFT, or an inverse transform.
function direct_coefficient(n::Vector{Float64}, fft_size::NTuple{3,Int}, m::NTuple{3,Int})
    length(n) == prod(fft_size) || error("Direct-sum shape mismatch")
    sr = 0.0; si = 0.0; cr = 0.0; ci = 0.0
    for k in 0:fft_size[3]-1, j in 0:fft_size[2]-1, i in 0:fft_size[1]-1
        index = 1 + i + fft_size[1] * (j + fft_size[2] * k)
        phase = -2pi * (m[1]*i/fft_size[1] + m[2]*j/fft_size[2] + m[3]*k/fft_size[3])
        value = n[index] * cis(phase)
        yr = real(value) - cr; tr = sr + yr; cr = (tr - sr) - yr; sr = tr
        yi = imag(value) - ci; ti = si + yi; ci = (ti - si) - yi; si = ti
    end
    complex(sr, si) / length(n)
end

function density_fourier(n::Vector{Float64}, lattice::Matrix{Float64}, fft_size::NTuple{3,Int},
                         points, expected_electrons, thresholds)
    size(lattice) == (3,3) && all(isfinite, lattice) || error("Finite column-vector lattice required")
    all(x -> x > 0, fft_size) && length(n) == prod(fft_size) || error("FFT shape mismatch")
    all(isfinite, n) || error("Nonfinite density")
    volume = abs(det(lattice)); isfinite(volume) && volume > 0 || error("Singular cell")
    reciprocal = 2pi * inv(transpose(lattice))
    duality = maximum(abs, transpose(lattice)*reciprocal/(2pi) - I)
    grid = DFTK.FFTGrid(fft_size, volume, DFTK.CPU())
    c = vec(DFTK.fft(grid, reshape(n, fft_size)))
    coefficients = c ./ sqrt(volume)
    all(isfinite, coefficients) || error("Nonfinite Fourier coefficient")
    millers = [Tuple(g) for g in vec(DFTK.G_vectors(grid))]
    length(unique(millers)) == prod(fft_size) || error("Duplicate native Miller vector")
    lookup = Dict(m => i for (i,m) in enumerate(millers))
    zero_index = only(findall(==((0,0,0)), millers))
    length(points) >= 15 && length(unique(Tuple.(points))) == length(points) ||
        error("At least 15 distinct predeclared direct-sum points are required")
    checks = map(points) do raw_m
        length(raw_m) == 3 && all(x -> x isa Integer, raw_m) || error("Integer direct-sum Miller vector required")
        m = Tuple(Int.(raw_m)); haskey(lookup, m) || error("Direct-sum point not in native grid")
        reference = direct_coefficient(n, fft_size, m)
        actual = coefficients[lookup[m]]
        err = abs(actual-reference)
        bound = thresholds["fft_direct_abs"] + thresholds["fft_direct_relative"]*abs(reference)
        (; miller=collect(m), reference=[real(reference),imag(reference)],
           fft=[real(actual),imag(actual)], absolute_error=err, bound,
           status=err <= bound ? "PASS" : "FAIL")
    end
    dvol = volume / length(n)
    real_norm2 = dvol * sum(abs2, n)
    fourier_norm2 = volume * sum(abs2, coefficients)
    parseval_relative = abs(real_norm2-fourier_norm2)/max(real_norm2, fourier_norm2, floatmin(Float64))
    # Modulo-grid conjugacy includes self-paired Nyquist points. Strict -m need
    # not exist for even-grid boundary representatives; neither table is expanded.
    modulo_lookup = Dict(ntuple(j -> mod(m[j],fft_size[j]),3) => i for (i,m) in enumerate(millers))
    conjugacy_errors = [coefficients[i] - conj(coefficients[modulo_lookup[ntuple(j -> mod(-m[j],fft_size[j]),3)]])
                       for (i,m) in enumerate(millers)]
    conjugacy_l2 = norm(conjugacy_errors)/max(norm(coefficients), floatmin(Float64))
    count_real = dvol * sum(n)
    count_fourier = volume * real(coefficients[zero_index])
    imaginary_electrons = volume * abs(imag(coefficients[zero_index]))
    count_ok = abs(count_real-expected_electrons) <= thresholds["electron_count_abs"] &&
               abs(count_fourier-expected_electrons) <= thresholds["electron_count_abs"] &&
               imaginary_electrons <= thresholds["zero_imag_electrons_abs"]
    fourier_ok = all(x -> x.status=="PASS", checks) && parseval_relative <= thresholds["parseval_relative"] &&
                 conjugacy_l2 <= thresholds["discrete_conjugacy_relative_l2"]
    support_ok = duality <= thresholds["reciprocal_duality_abs"]
    ok = count_ok && fourier_ok && support_ok
    diagnostics = (; status=ok ? "PASS" : "FAIL", density_sha256=density_hash(n),
        fourier_convention_status=fourier_ok ? "PASS" : "FAIL",
        electron_count_status=count_ok ? "PASS" : "FAIL",
        reciprocal_support_status=support_ok ? "PASS" : "FAIL",
        density_eltype="Float64", density_shape=collect(size(n)), fft_shape=collect(fft_size),
        ngrid=length(n), native_g_count=length(millers), volume_bohr3=volume, dvol_bohr3=dvol,
        reciprocal_lattice_matrix_bohr_inverse=[collect(row) for row in eachrow(reciprocal)],
        reciprocal_duality_max_abs=duality, electron_count_real=count_real,
        electron_count_fourier=count_fourier, zero_imag_electrons=imaginary_electrons,
        real_norm_squared=real_norm2, fourier_norm_squared=fourier_norm2, parseval_relative,
        discrete_conjugacy_relative_l2=conjugacy_l2,
        discrete_conjugacy_max_abs=maximum(abs,conjugacy_errors),
        strict_negative_missing_count=count(m -> !haskey(lookup, ntuple(j -> -m[j],3)), millers),
        minimum_density=minimum(n), maximum_density=maximum(n), direct_sum_checks=checks,
        convention="nbar=DFTK.fft(FFTGrid,reshape(n,fft_size))/sqrt(Omega); no spin or k factor",
        real_grid_order="Julia column-major, fractional (i/N1,j/N2,k/N3), indices start at zero",
        native_order="vec(DFTK.G_vectors(FFTGrid)); even-grid axis includes -N/2, excludes +N/2")
    (; millers, coefficients, orthonormal_coefficients=c, diagnostics)
end

function write_native_csv(path, input, output)
    input.millers == output.millers || error("Input/output native G order mismatch")
    open(path, "w") do io
        write(io, "m1,m2,m3,n_in_real,n_in_imag,n_out_real,n_out_imag\n")
        for (m,a,b) in zip(input.millers,input.coefficients,output.coefficients)
            values = (real(a),imag(a),real(b),imag(b))
            tokens = repr.(values)
            all(isequal.(parse.(Float64,tokens),values)) || error("Float64 CSV round-trip failed")
            write(io, join((string.(m)...,tokens...),",")*"\n")
        end
    end
    # Verify the actual on-disk bytes, not only formatting before a write.
    open(path,"r") do io
        readline(io)=="m1,m2,m3,n_in_real,n_in_imag,n_out_real,n_out_imag" || error("CSV header mismatch")
        for (m,a,b) in zip(input.millers,input.coefficients,output.coefficients)
            fields=split(readline(io),','); length(fields)==7 || error("CSV field count mismatch")
            Tuple(parse.(Int,fields[1:3]))==m || error("CSV Miller round-trip failed")
            expected=(real(a),imag(a),real(b),imag(b))
            all(isequal.(parse.(Float64,fields[4:7]),expected)) || error("On-disk CSV Float64 round-trip failed")
        end
        eof(io) || error("Unexpected trailing CSV rows")
    end
    nothing
end

function write_json(path, object)
    bytes = JSON3.write(public_data(object,ROOT))*"\n"
    JSON3.read(bytes)
    write(path*".tmp",bytes)
    mv(path*".tmp",path;force=true)
end

function validate_historical_binding(plan,label,source_path)
    label in ("A","B") || error("Only historical A/B sources are supported")
    source=plan["sources"][label]
    evidence_path=resolve_path(source["historical_evidence_path"])
    evidence_sha=plan["source_evidence_sha256"][source["historical_evidence_path"]]
    checked_file(evidence_path,evidence_sha)
    evidence=read_json(evidence_path); run=evidence["runs"][label]
    run["run_id"]==source["run_id"] && run["label"]==label && run["execution_status"]=="PASS" ||
        error("Historical run identity/status mismatch")
    run["checkpoint_sha256"]==source["checkpoint"]["sha256"] || error("Historical checkpoint SHA binding mismatch")
    tracked=Dict(evidence_path=>evidence_sha)
    for key in ("endpoint","receipt","maps")
        ref=source[key]; path=resolve_path(ref["path"])
        tracked[path]=checked_file(path,ref["sha256"])
        haskey(ref,"bytes") && filesize(path)!=ref["bytes"] && error("Bound $key byte count mismatch")
    end
    endpoint=read_json(resolve_path(source["endpoint"]["path"]))
    receipt=read_json(resolve_path(source["receipt"]["path"]))
    receipt["run_id"]==source["run_id"] && receipt["label"]==label && receipt["execution_status"]=="PASS" &&
        receipt["checkpoint_sha256"]==run["checkpoint_sha256"] || error("Original run receipt does not match source")
    for key in ("map_count","n_in_sha256","n_out_sha256","unmixed_residual_l2","target_states")
        receipt["final"][key]==endpoint[key] || error("Original receipt / public endpoint mismatch: $key")
    end
    maps=map(line -> JSON3.read(line,Dict{String,Any}),readlines(resolve_path(source["maps"]["path"])))
    length(maps)==endpoint["map_count"] && [r["map_index"] for r in maps]==collect(1:length(maps)) || error("Historical map count/order mismatch")
    last_map=last(maps)
    last_map["map_role"]=="closure" && last_map["status"]=="PASS" || error("Endpoint is not a successful closure map")
    last_map["n_in"]["sha256"]==endpoint["n_in_sha256"] && last_map["n_out"]["sha256"]==endpoint["n_out_sha256"] &&
        last_map["unmixed_residual_l2"]==endpoint["unmixed_residual_l2"] || error("Closure map does not bind endpoint densities")
    evidence["basis"]["fft_grid"]==plan["fft_size"] || error("Historical FFT grid mismatch")
    lattice=hcat((Float64.(v) for v in plan["lattice_vectors_bohr"])...)
    historical=reduce(vcat,permutedims.(Float64.(v) for v in evidence["basis"]["lattice_bohr"]))
    maximum(abs,lattice-historical)<=plan["thresholds"]["direct_lattice_abs_bohr"] || error("Historical lattice mismatch")
    evidence["basis"]["n_electrons"]==plan["expected_electrons"] || error("Historical electron count mismatch")
    tracked[source_path]=checked_file(source_path,run["checkpoint_sha256"])
    filesize(source_path)==source["checkpoint"]["bytes"] || error("Checkpoint byte count mismatch")
    (; source,endpoint,lattice,tracked)
end

function extract_request(request_path,outdir; csv_writer=write_native_csv)
    outdir=abspath(outdir)
    ispath(outdir) && (println(stderr,"Refusing existing output directory; no stale PASS reused");return 2)
    startswith(outdir,joinpath(ROOT,".work")*"/") || (println(stderr,"Output must be in a new ignored .work directory");return 2)
    result=Dict{String,Any}("schema_version"=>1,"phase"=>"7C","execution_status"=>"RUNNING",
        "extraction_run_id"=>basename(outdir),"started_utc"=>string(now(UTC)),
        "data_status"=>"NEW_EXTRACTION_FROM_HISTORICAL_ARRAYS","scf_status"=>"HISTORICAL_REUSED",
        "new_scf_status"=>"NOT_RUN","new_eigensolve_status"=>"NOT_RUN")
    code=1; tracked=Dict{String,String}()
    try
        mkpath(outdir)
        request=read_json(request_path); request["schema_version"]==1 || error("Unsupported request schema")
        tracked[abspath(request_path)]=filehash(request_path)
        plan_path=resolve_path(request["plan_path"])
        tracked[plan_path]=checked_file(plan_path,request["plan_sha256"])
        plan=read_json(plan_path); plan["schema_version"]==1 || error("Unsupported plan schema")
        result["plan_sha256"]=request["plan_sha256"];result["label"]=request["label"]
        result["executed_script_sha256"]=filehash(@__FILE__)
        tracked[@__FILE__]=result["executed_script_sha256"]
        tracked[joinpath(@__DIR__,"workbench_environment.jl")]=filehash(joinpath(@__DIR__,"workbench_environment.jl"))
        string(VERSION)==plan["julia_version"]=="1.12.7" || error("Julia version differs from original Serialization environment")
        identity=environment_identity(ROOT,(DFTK,PseudoPotentialIO));result["environment"]=identity
        identity.status=="PASS" || error("Frozen environment identity mismatch")
        for (path,sha) in plan["frozen_environment_sha256"]
            tracked[resolve_path(path)]=checked_file(resolve_path(path),sha)
        end
        DFTK.disable_threading()
        source_path=resolve_path(get(request,"source_path",plan["sources"][request["label"]]["checkpoint"]["path"]))
        binding=validate_historical_binding(plan,request["label"],source_path)
        merge!(tracked,binding.tracked)
        result["source_run_id"]=binding.source["run_id"]
        result["raw_source_binding_status"]="PASS"
        result["source_sha256_before"]=tracked[source_path]
        state=trusted_checkpoint(source_path,tracked[source_path])
        result["binary_parse_status"]="PASS"
        result["checkpoint_fields"]=string.(keys(state))
        fft_size=Tuple(Int.(plan["fft_size"]));volume=abs(det(binding.lattice))
        volume==plan["volume_bohr3"] || error("Plan volume differs from lattice")
        bound=bound_densities(state,binding.endpoint,fft_size,volume/prod(fft_size),plan["thresholds"])
        result["density_state_binding_status"]="PASS";result["closure"]=bound.closure
        input=density_fourier(bound.n_in,binding.lattice,fft_size,plan["direct_fourier_miller_points"],plan["expected_electrons"],plan["thresholds"])
        output=density_fourier(bound.n_out,binding.lattice,fft_size,plan["direct_fourier_miller_points"],plan["expected_electrons"],plan["thresholds"])
        result["n_in"]=input.diagnostics;result["n_out"]=output.diagnostics
        all(x=="PASS" for x in (bound.closure.status,input.diagnostics.status,output.diagnostics.status)) ||
            error("Closure or native Fourier consistency check failed; original diagnostics retained")
        csv_writer(joinpath(outdir,"native.csv"),input,output)
        result["coefficients"]=(;path="native.csv",sha256=filehash(joinpath(outdir,"native.csv")),
            row_count=length(output.millers),float64_round_trip_status="PASS",units="electron/bohr^3")
        for (path,sha) in tracked;checked_file(path,sha);end
        result["source_sha256_after"]=filehash(source_path)
        result["source_unchanged_status"]="PASS"
        final_identity=environment_identity(ROOT,(DFTK,PseudoPotentialIO))
        final_identity==identity || error("Runtime environment identity changed")
        result["environment_recheck_status"]="PASS"
        result["execution_status"]="PASS";code=0
    catch err
        result["execution_status"]=err isa MissingSource ? "BLOCKED" : "FAIL"
        result["failure_reason"]=sprint(showerror,err)
        showerror(stderr,err,catch_backtrace());println(stderr)
    end
    result["exit_code"]=code;result["finished_utc"]=string(now(UTC))
    try
        # metadata.json is the final success publication, after CSV round-trip,
        # source rechecks and complete summary construction/writing.
        summary="$(result["extraction_run_id"]): $(result["execution_status"]), exit=$code\n"
        write(joinpath(outdir,"summary.txt"),summary)
        write_json(joinpath(outdir,"metadata.json"),result)
    catch err
        println(stderr,"Persistence failed: ",sprint(showerror,err));code=1
        safe=Dict("schema_version"=>1,"phase"=>"7C","execution_status"=>"FAIL","exit_code"=>1,
            "failure_reason"=>"Persistence failure; see stderr","new_scf_status"=>"NOT_RUN","new_eigensolve_status"=>"NOT_RUN")
        try write_json(joinpath(outdir,"metadata.json"),safe) catch
            println(stderr,"Unable to persist safe failure record")
        end
    end
    code
end

function main(args)
    args==["--help"] && (println("Usage: extract_soc_density.jl REQUEST.json NEW_IGNORED_OUTPUT_DIR\nRead only SHA-bound Phase 6C densities; no electronic structure solve.");return 0)
    length(args)==2 || (println(stderr,"Expected REQUEST.json NEW_IGNORED_OUTPUT_DIR");return 2)
    extract_request(args[1],args[2])
end
end
abspath(PROGRAM_FILE)==(@__FILE__) && exit(SOCDensityExtraction.main(ARGS))
