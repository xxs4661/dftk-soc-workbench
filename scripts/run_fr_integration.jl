#!/usr/bin/env julia
# Phase 6B only: fixed-density eigensolves and current-orbital energy; no SCF driver.
using DFTK, PseudoPotentialIO, LinearAlgebra, Random, SHA, TOML, JSON3, Dates, Serialization
include("workbench_environment.jl")
include("upf_validation.jl")
include("upf_runtime.jl")
using .WorkbenchEnvironment, .UpfValidation, .UpfRuntime
include("../prototypes/spinor/SpinorPrototype.jl")
include("../prototypes/relativistic/RelativisticProjectors.jl")
include("../prototypes/fr_integration/FRIntegration.jl")
const FI=FRIntegration
const PHASE6B_ROOT=realpath(joinpath(@__DIR__,".."))
const PHASE6B_STAGES=("common_psp_data_status","same_source_consistency_status","full_hamiltonian_status",
    "fixed_density_eigensolve_status","fr_total_energy_functional_status","variational_consistency_status",
    "scalar_limit_integration_status")

function phase6b_finite(x)
    if x isa Number
        x isa Real && isfinite(x) || error("Public evidence requires finite real numbers")
    elseif x isa AbstractDict || x isa NamedTuple
        foreach(phase6b_finite,values(x))
    elseif x isa AbstractArray || x isa Tuple
        foreach(phase6b_finite,x)
    end
    nothing
end
function phase6b_write(path,result;redact=true)
    phase6b_finite(result)
    data=redact ? public_data(result,PHASE6B_ROOT) : result
    bytes=JSON3.write(data)*"\n"; JSON3.read(bytes)
    write(path*".tmp",bytes)
    mv(path*".tmp",path;force=true)
end

# Single-phase publication boundary: no old result is consulted; existing run is refused.
function with_phase6b_record(work,outdir)
    outdir=abspath(outdir)
    startswith(outdir,joinpath(PHASE6B_ROOT,".work")*"/") || (println(stderr,"Run directory must be under ignored .work");return 2)
    ispath(outdir) && (println(stderr,"Refusing existing run directory");return 2)
    result=Dict{String,Any}("schema_version"=>1,"phase"=>"6B","run_id"=>basename(outdir),
        "base_commit"=>"1db8b61e7d962c7476b301e8a5be0be3725fbe6f","started_utc"=>string(now(UTC)),
        "execution_status"=>"RUNNING","numerical_review_status"=>"REVIEW_REQUIRED",
        "soc_scf_status"=>"NOT_IMPLEMENTED","qe_soc_benchmark_status"=>"NOT_RUN",
        "noncollinear_xc_status"=>"NOT_IMPLEMENTED","upstream_native_support"=>"NOT_IMPLEMENTED_BY_THIS_PHASE")
    foreach(k->result[k]="NOT_RUN",PHASE6B_STAGES)
    code=0
    try
        mkpath(outdir)
        phase6b_write(joinpath(outdir,"result.json"),result)
        work(result,outdir)
        all(result[k]=="PASS" for k in PHASE6B_STAGES) || error("Required Phase 6B integration stage did not pass")
        result["execution_status"]="PASS"
    catch err
        code=1; result["execution_status"]="FAIL"
        foreach(k->result[k]=="RUNNING" && (result[k]="FAIL"),PHASE6B_STAGES)
        result["failure_reason"]=sprint(showerror,err)
        showerror(stderr,err,catch_backtrace());println(stderr)
    end
    result["exit_code"]=code;result["finished_utc"]=string(now(UTC))
    try
        phase6b_write(joinpath(outdir,"result.json"),result)
    catch err
        println(stderr,"Persistence failure: ",sprint(showerror,err))
        safe=Dict{String,Any}("schema_version"=>1,"phase"=>"6B","run_id"=>basename(outdir),
            "execution_status"=>"FAIL","exit_code"=>1,"failure_reason"=>"Full result persistence failed; see stderr")
        foreach(k->safe[k]="NOT_RUN",PHASE6B_STAGES)
        try
            phase6b_write(joinpath(outdir,"result.json"),safe)
        catch
            println(stderr,"Unable to persist even safe failure record")
        end
        return 1
    end
    println(stderr,"Phase 6B $(basename(outdir)): $(result["execution_status"]), exit=$code")
    code
end

function phase6b_source_hashes(;tests=false)
    files=["scripts/run_fr_integration.jl","scripts/workbench_environment.jl","scripts/upf_validation.jl","scripts/upf_runtime.jl"]
    append!(files,["prototypes/spinor/"*f for f in ("SpinorPrototype.jl","operators.jl","fft.jl","density.jl")])
    append!(files,["prototypes/relativistic/"*f for f in ("RelativisticProjectors.jl","channels.jl","radial.jl","angular.jl","operator.jl")])
    append!(files,["prototypes/fr_integration/"*f for f in readdir(joinpath(PHASE6B_ROOT,"prototypes/fr_integration")) if endswith(f,".jl")])
    if tests
        append!(files,["tests/fr_integration/"*f for f in readdir(joinpath(PHASE6B_ROOT,"tests/fr_integration")) if endswith(f,".jl")])
    end
    Dict(f=>filehash(joinpath(PHASE6B_ROOT,f)) for f in files)
end
function phase6b_stage!(result,outdir,key,status)
    result[key]=status
    phase6b_write(joinpath(outdir,"result.json"),result)
    status=="PASS" || error("$key = $status; retaining evidence for review")
end
function compact_energy(snapshot)
    (;terms_ha=snapshot.terms,total_ha=snapshot.total,checks=snapshot.report,
      nonlocal=snapshot.nonlocal_decomposition,density_sha256=FI.integration_density_hash(snapshot.density.n))
end

function run_phase6b!(result,outdir)
    settingsfile=joinpath(PHASE6B_ROOT,"prototypes/fr_integration/phase6b.toml")
    settings=TOML.parsefile(settingsfile);result["settings"]=settings
    result["settings_sha256"]=filehash(settingsfile)
    result["executed_source_sha256"]=phase6b_source_hashes()
    result["workbench_head_at_execution"]=strip(read(`git -C $PHASE6B_ROOT rev-parse HEAD`,String))
    identity=environment_identity(PHASE6B_ROOT,(DFTK,PseudoPotentialIO));result["environment"]=identity
    phase6b_write(joinpath(outdir,"identity.raw.json"),identity;redact=false)
    identity.status=="PASS" || error("Frozen environment identity mismatch")
    DFTK.disable_threading()
    Threads.nthreads()==1 && BLAS.get_num_threads()==1 && DFTK.mpi_nprocs(DFTK.MPI.COMM_WORLD)==1 || error("Serial CPU required")
    result["parallelism"]=(;julia=Threads.nthreads(),blas=BLAS.get_num_threads(),fft=DFTK.FFTW.get_num_threads(),mpi=1)
    result["common_psp_data_status"]="RUNNING"
    cases=FI.build_integration_cases(PHASE6B_ROOT,settings)
    result["input"]=(;mg=FI.common_data_summary(cases.mg),si=FI.common_data_summary(cases.si))
    result["basis"]=(;mg=FI.basis_summary(cases.mgctx),si=FI.basis_summary(cases.sictx))
    common=FI.compare_native_common_si(cases.si,settings["common_fourier_probes_bohr_inverse"])
    result["si_common"]=common
    phase6b_stage!(result,outdir,"common_psp_data_status",common.max_error<=settings["thresholds"]["common_data_normalized"] ? "PASS" : "FAIL")
    FI.assert_bound_sources(cases.mg);FI.assert_bound_sources(cases.si)
    phase6b_stage!(result,outdir,"same_source_consistency_status","PASS")

    result["scalar_limit_integration_status"]="RUNNING"
    println(stderr,"Real scalar Si: common, full-H action and seven-term synthetic-limit energy, no SCF")
    si_reference=FI.fixed_reference_density(cases.sictx.basis,settings)
    action=FI.scalar_limit_action(cases.sictx,cases.native_si_basis,si_reference.n,settings["seeds"]["si_energy_fixture"])
    sifixture=FI.diagnostic_fixture(cases.sictx,settings["seeds"]["si_energy_fixture"])
    si_energy=FI.compare_native_scalar_energy(cases.sictx,sifixture.X,sifixture.f,cases.native_si_basis)
    result["si_scalar_limit"]=(;reference_density=si_reference.report,action,
        energy=compact_energy(si_energy.snapshot),native_terms_ha=si_energy.native_terms,
        term_differences_ha=si_energy.term_differences_ha,total_difference_ha=si_energy.total_difference_ha,
        fixture_seed=sifixture.seed,scope=sifixture.scope)
    serialize(joinpath(outdir,"si-fixture-density.bin"),(;X=sifixture.X,f=sifixture.f,n=si_energy.snapshot.density.n))
    si_ok=action.max_error<=settings["thresholds"]["scalar_hamiltonian_normalized"] &&
        max(abs(si_energy.total_difference_ha),si_energy.max_term_difference_ha)<=settings["thresholds"]["scalar_energy_abs_ha"]
    phase6b_stage!(result,outdir,"scalar_limit_integration_status",si_ok ? "PASS" : "FAIL")

    result["full_hamiltonian_status"]="RUNNING"
    ctx=cases.mgctx; reference=FI.fixed_reference_density(ctx.basis,settings)
    pair=FI.build_full_hamiltonian(ctx,reference.n)
    result["mg_reference_density"]=reference.report
    symmetry=FI.full_hamiltonian_checks(ctx,pair.full,settings);result["full_hamiltonian"]=symmetry
    phase6b_stage!(result,outdir,"full_hamiltonian_status",symmetry.status)
    result["fixed_density_eigensolve_status"]="RUNNING";result["eigensolves"]=Any[]
    checkpoint=function(record,X)
        push!(result["eigensolves"],record)
        serialize(joinpath(outdir,"mg-k$(record.k_index)-orbitals.bin"),(;X,eigenvalues=record.eigenvalues_ha,n_ref=reference.n))
        phase6b_write(joinpath(outdir,"result.json"),result)
    end
    solved=FI.solve_fixed_density(ctx,pair.full,settings;checkpoint)
    result["spectrum_symmetry"]=solved.spectrum
    phase6b_stage!(result,outdir,"fixed_density_eigensolve_status",solved.spectrum.status)

    result["fr_total_energy_functional_status"]="RUNNING"
    println(stderr,"Mg current-orbital energy and prescribed variational diagnostics; no density feedback")
    actual=FI.energy_snapshot(ctx,solved.X,solved.f)
    fixture=FI.diagnostic_fixture(ctx,settings["seeds"]["mg_energy_fixture"])
    trial=FI.energy_snapshot(ctx,fixture.X,fixture.f)
    band_ref=sum(ctx.basis.kweights.*[dot(f,e) for (f,e) in zip(solved.f,solved.lambdas)])
    result["mg_energy"]=(;from_solved_fixed_density_orbitals=compact_energy(actual),general_complex_fixture=compact_energy(trial),
        fixture_seed=fixture.seed,fixture_scope=fixture.scope,diagnostic_occupations=solved.f,
        n_X_minus_n_ref_l2=sqrt(ctx.basis.dvol)*norm(actual.density.n-reference.n),
        fixed_reference_eigenvalue_sum_ha=band_ref,
        current_H_expectation_minus_old_eigenvalue_sum_ha=actual.report.band_expectation_ha-band_ref,
        scope="E[X,f] at n_X; prescribed occupied first N_e states per k; not a self-consistent or equilibrium energy")
    serialize(joinpath(outdir,"mg-energy-densities.bin"),(;X=solved.X,f=solved.f,n_ref=reference.n,n_X=actual.density.n,
        fixture_X=fixture.X,fixture_n=trial.density.n))
    cross=abs(trial.nonlocal_decomposition.cross_ha)
    phase6b_stage!(result,outdir,"fr_total_energy_functional_status",cross>=settings["thresholds"]["cross_energy_min_abs_ha"] ? "PASS" : "INCONCLUSIVE")
    result["variational_consistency_status"]="RUNNING"
    cfg=settings["spin_rotation"];axis=Float64.(cfg["axis"]);axis/=norm(axis)
    sigma=axis[1]*ComplexF64[0 1;1 0]+axis[2]*ComplexF64[0 -im;im 0]+axis[3]*ComplexF64[1 0;0 -1]
    U=cos(cfg["angle_rad"]/2)*Matrix{ComplexF64}(I,2,2)-im*sin(cfg["angle_rad"]/2)*sigma
    spin=FI.spin_rotation_diagnostic(ctx,fixture.X,fixture.f,U)
    result["spin_rotation"]=spin
    fd=settings["finite_difference"]
    variational=FI.variational_checks(ctx,solved.X,solved.f;k_index=fd["kpoint_index"],occupied_state=fd["occupied_index"],
        empty_state=Int(ctx.basis.model.n_electrons)+1,center_angle=fd["center_angle_rad"],steps=fd["steps_rad"],
        total_derivative_min_abs=fd["total_derivative_min_abs"],nl_derivative_min_abs=fd["nl_derivative_min_abs"],
        total_derivative_tol=fd["total_error_normalized"],nl_derivative_atol=fd["nl_error_abs_floor"],nl_derivative_rtol=fd["nl_error_relative"])
    result["variational"]=variational
    states=(spin.status,variational.status)
    status="FAIL" in states ? "FAIL" : "INCONCLUSIVE" in states ? "INCONCLUSIVE" : "PASS"
    phase6b_stage!(result,outdir,"variational_consistency_status",status)
    result["raw_artifacts_sha256"]=Dict(f=>filehash(joinpath(outdir,f)) for f in readdir(outdir) if endswith(f,".bin"))
end
function phase6b_main(args)
    args==["--help"] && (println("Usage: run_fr_integration.jl NEW_IGNORED_RUN_DIRECTORY\nPhase 6B fixed-density and orbital-energy checks; no SCF/QE.");return 0)
    length(args)==1 || (println(stderr,"One new ignored run directory is required; --help for usage");return 2)
    with_phase6b_record(run_phase6b!,only(args))
end
abspath(PROGRAM_FILE)==(@__FILE__) && exit(phase6b_main(ARGS))
