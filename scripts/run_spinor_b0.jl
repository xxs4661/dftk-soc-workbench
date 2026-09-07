#!/usr/bin/env julia
# One fresh scalar SCF, followed by actual matrix-free component eigenproblems.
using DFTK, PseudoPotentialIO, JSON3, TOML, LinearAlgebra, Random, Serialization, Dates
include(joinpath(@__DIR__, "workbench_environment.jl"))
using .WorkbenchEnvironment
include(joinpath(@__DIR__, "..", "prototypes", "spinor", "SpinorPrototype.jl"))
using .SpinorPrototype

const ROOT = realpath(joinpath(@__DIR__, ".."))
const BASE = "47159d7b28f01a86f26425183803ee31cb2d2f70"
const CASE = "benchmarks/si-sr-lda/case.json"
const TOLERANCES = "prototypes/spinor/tolerances.toml"

function finite_data(x)
    if x isa AbstractFloat
        isfinite(x) || error("Nonfinite public result")
    elseif x isa AbstractDict || x isa NamedTuple
        foreach(finite_data, values(x))
    elseif x isa AbstractArray || x isa Tuple
        foreach(finite_data, x)
    end
end

function save_result(outdir, result)
    finite_data(result)
    data = JSON3.write(public_data(result, ROOT)) * "\n"
    path = joinpath(outdir, "result.json")
    write(path * ".tmp", data)
    mv(path * ".tmp", path; force=true)
end

function prepare!(result)
    identity = environment_identity(ROOT, (DFTK, PseudoPotentialIO))
    result["environment"] = identity
    identity.status == "PASS" || error("Loaded workbench environment mismatch")
    DFTK.disable_threading()
    DFTK.mpi_nprocs(DFTK.MPI.COMM_WORLD) == 1 || error("Requires one MPI process")
    Threads.nthreads() == 1 && BLAS.get_num_threads() == 1 || error("Requires serial CPU settings")
    result["parallelism"] = (; julia_threads=Threads.nthreads(),
        dftk_threads=DFTK.get_DFTK_threads(), blas_threads=BLAS.get_num_threads(),
        fft_threads=DFTK.FFTW.get_num_threads(), mpi_processes=1)
    result["workbench_head_at_execution"] = strip(read(`git -C $ROOT rev-parse HEAD`, String))
    files = vcat(["scripts/run_spinor_b0.jl", TOLERANCES],
        ["prototypes/spinor/" * name for name in readdir(joinpath(ROOT, "prototypes", "spinor"))
         if endswith(name, ".jl")])
    result["executed_source_sha256"] = Dict(p => filehash(joinpath(ROOT, p)) for p in files)
    casepath = joinpath(ROOT, CASE)
    # The accepted bytes, including all original B0 settings, must remain identical.
    read(casepath) == read(`git -C $ROOT show $BASE\:$CASE`) || error("B0 differs from accepted commit")
    case = JSON3.read(read(casepath, String), Dict{String,Any})
    result["case"] = (; path=CASE, sha256=filehash(casepath), historical_base=BASE)
    psppath = joinpath(ROOT, case["pseudo"]["local_path"])
    filehash(psppath) == case["pseudo"]["sha256"] || error("B0 UPF checksum mismatch")
    parsed = PseudoPotentialIO.load_psp_file(psppath)
    parsed isa PseudoPotentialIO.UpfFile || error("Not an UpfFile")
    h = parsed.header
    h.element == "Si" && h.pseudo_type == "NC" && h.relativistic == "scalar" &&
        !h.has_so && h.z_valence == 4 && h.core_correction || error("Wrong Si scalar NC metadata")
    split(h.functional) == split(case["xc"]["upf_functional"]) || error("Wrong UPF functional")
    psp = DFTK.PspUpf(parsed; identifier=basename(psppath), rcut=case["pseudo"]["dftk_rcut_bohr"])
    DFTK.has_core_density(psp) || error("NLCC missing")
    result["pseudo"] = (; sha256=filehash(psppath), filename=basename(psppath),
        pseudo_type=h.pseudo_type, relativistic=h.relativistic, has_so=h.has_so,
        z_valence=h.z_valence, nlcc=true, rcut_actual_bohr=psp.rcut)
    geometry = case["geometry"]
    lattice = reduce(hcat, [Float64.(v) for v in geometry["lattice_vectors_bohr"]])
    positions = [Float64.(v) for v in geometry["positions_fractional"]]
    atoms = [ElementPsp(:Si, psp) for _ in geometry["species"]]
    model = model_DFT(lattice, atoms, positions;
        functionals=Symbol.(case["xc"]["dftk_identifiers"]), n_electrons=8,
        spin_polarization=:none, temperature=0.0, symmetries=false)
    coords = [Float64.(p["coordinate_fractional"]) for p in case["kpoints"]]
    weights = Float64[p["weight_spatial"] for p in case["kpoints"]]
    basis = PlaneWaveBasis(model; Ecut=case["cutoffs"]["dftk_ecut_ha"],
        kgrid=ExplicitKpoints(coords, weights))
    length(basis.kpoints) == 8 || error("B0 needs eight spatial k points")
    used = Int[]
    for (ik, k) in enumerate(basis.kpoints)
        matches = findall(coords) do c
            delta = collect(k.coordinate) - c
            maximum(abs.(delta-round.(delta))) < 1e-12
        end
        length(matches) == 1 || error("Ambiguous k-point association")
        index = only(matches)
        index in used && error("Duplicate k point")
        push!(used, index)
        abs(basis.kweights[ik] - weights[index]) < 1e-12 || error("Spatial weight mismatch")
    end
    length(model.symmetries) == 1 || error("Spatial symmetry reduction enabled")
    xc = only(filter(t -> t isa DFTK.Xc, model.term_types))
    xcterm = only(filter(t -> t isa DFTK.TermXc, basis.terms))
    string.(DFTK.identifier.(xc.functionals)) == case["xc"]["dftk_identifiers"] || error("Wrong XC")
    xc.use_nlcc && !isnothing(xcterm.ρcore) || error("Actual XC lacks NLCC")
    result["basis"] = (; ecut_ha=basis.Ecut, fft_grid=collect(basis.fft_size),
        volume_bohr3=model.unit_cell_volume, dvol_bohr3=basis.dvol, n_electrons=8,
        spin_polarization="none", temperature_ha=0.0, symmetry_operations=length(model.symmetries),
        xc=case["xc"]["dftk_identifiers"], nlcc=true,
        kpoints=[(; coordinate_fractional=collect(k.coordinate),
            weight_spatial=basis.kweights[ik], ng=length(DFTK.G_vectors(basis, k)))
            for (ik, k) in enumerate(basis.kpoints)])
    kinetic = only(filter(t -> t isa DFTK.TermKinetic, basis.terms)).kinetic_energies
    case, basis, kinetic
end

function interface_preflight!(result, basis, kinetic, outdir)
    # Builds an initial-density Hamiltonian and applies it; executes no SCF/eigensolve.
    rho = DFTK.guess_density(basis)
    ham = DFTK.energy_hamiltonian(basis, nothing, nothing; ρ=rho).ham
    diagnostics = []
    for ik in eachindex(basis.kpoints)
        ng = length(kinetic[ik])
        x = DFTK.ortho_qr(randn(MersenneTwister(53000+ik), ComplexF64, 2ng, 3))
        a = ComponentOperator(ham[ik], 2)
        hx = a * x
        p = ComponentKineticPreconditioner(kinetic[ik], 2)
        all(isfinite, p \ hx) || error("Preconditioner output nonfinite")
        u = component_ifft(basis, basis.kpoints[ik], unflatten_components(x, 2))
        roundtrip = flatten_components(component_fft(basis, basis.kpoints[ik], u))
        err = norm(roundtrip-x) / norm(x)
        err <= 1e-11 || error("Actual B0 component FFT preflight failed")
        push!(diagnostics, (; ng, roundtrip_relative=err, lifted_size=collect(size(a))))
    end
    serialize(joinpath(outdir, "serialization-probe.bin"), (; rho_shape=size(rho), diagnostics))
    result["interface_preflight"] = diagnostics
    result["scalar_scf_status"] = "NOT_RUN"
end

function calculate!(result, case, basis, kinetic, settings, outdir)
    solver = settings["solver"]
    starget = solver["scalar_target_states"]
    scompute = starget + solver["scalar_auxiliary_states"]
    target = solver["spinor_target_states"]
    ncompute = target + solver["spinor_auxiliary_states"]
    scfsettings = case["scf"]
    dtol = scfsettings["diagonalization_tol_ha"]
    result["scalar_scf_status"] = "RUNNING"
    save_result(outdir, result)
    println("Starting the sole fresh scalar B0 SCF."); flush(stdout)
    started = time()
    diagtolalg = DFTK.AdaptiveDiagtol(; diagtol_first=dtol, diagtol_min=dtol, diagtol_max=dtol)
    scf = self_consistent_field(basis; tol=scfsettings["dftk_tol"],
        maxiter=scfsettings["maxiter"], nbandsalg=FixedBands(;
            n_bands_converge=starget, n_bands_compute=scompute), diagtolalg, seed=0)
    result["scalar_scf"] = (; converged=scf.converged, iterations=scf.n_iter,
        elapsed_seconds=time()-started, seed=scf.seed, tol=scfsettings["dftk_tol"],
        diagonalization_tol_ha=dtol, target_states=starget, auxiliary_states=scompute-starget,
        density_residual_history=scf.history_Δρ, energy_history_ha=scf.history_Etot,
        native_total_energy_ha_cell=scf.energies.total, energy_components_ha=Dict(pairs(scf.energies)),
        energy_note="Native scalar DFT SCF total energy; not a spinor result or band-energy sum",
        final_diagonalization_converged=all(d.converged for d in scf.diagonalization))
    serialize(joinpath(outdir, "scalar-scf-orbitals.bin"),
        (; psi=scf.ψ, rho=scf.ρ, eigenvalues=scf.eigenvalues, occupations=scf.occupation))
    result["scalar_scf_status"] = scf.converged ? "PASS" : "FAIL"
    save_result(outdir, result)
    scf.converged && all(d.converged for d in scf.diagonalization) || error("Scalar SCF did not converge")
    println("Scalar SCF complete; obtaining scalar references on exactly scf.ham."); flush(stdout)
    diagonal = DFTK.diagonalize_all_kblocks(DFTK.lobpcg_hyper, scf.ham, scompute;
        ψguess=scf.ψ, tol=solver["scalar_tolerance_ha"], n_conv_check=starget,
        maxiter=solver["scalar_maxiter"])
    scalar_x = [x[:, 1:starget] for x in diagonal.X]
    scalar_hx = [scf.ham[ik] * x for (ik,x) in enumerate(scalar_x)]
    scalar_res = [[norm(scalar_hx[ik][:,n]-diagonal.λ[ik][n]*x[:,n]) for n in 1:starget]
                  for (ik,x) in enumerate(scalar_x)]
    result["scalar_reference"] = (; converged=diagonal.converged, target_states=starget,
        auxiliary_states=scompute-starget, tolerance_ha=solver["scalar_tolerance_ha"],
        iterations_per_kpoint=diagonal.n_iter, n_matvec=diagonal.n_matvec,
        eigenvalues_with_auxiliary_ha=diagonal.λ, explicit_residuals_ha=scalar_res,
        orthogonality_frobenius=[norm(x'x-I) for x in scalar_x],
        source="Final scf.ham; no density or Hamiltonian update after this point")
    save_result(outdir, result)
    spinor_x = Matrix{ComplexF64}[]
    spinor_hx = Matrix{ComplexF64}[]
    spinor_lambda = Vector{Float64}[]
    records = Any[]
    result["spinor_kpoints"] = records
    for (ik, k) in enumerate(basis.kpoints)
        ng = length(kinetic[ik])
        seed = solver["initial_seed_base"] + ik - 1
        initial = DFTK.ortho_qr(randn(MersenneTwister(seed), ComplexF64, 2ng, ncompute))
        initial_component_norms = [sum(abs2, initial[c:2:end,:]) for c in 1:2]
        initial_gram = norm(initial'initial-I)
        initial_imaginary_norm = norm(imag.(initial))
        initial_gram <= settings["acceptance"]["algebra_normalized"] || error("Initial QR orthogonality failed")
        all(>(0), initial_component_norms) && initial_imaginary_norm > 0 || error("Initial subspace is not complex two-component")
        initial_saved = copy(initial)
        a = ComponentOperator(scf.ham[ik], 2)
        p = ComponentKineticPreconditioner(kinetic[ik], 2; shift=solver["preconditioner_shift_ha"])
        println("Solving spinor k=$ik/8: NG=$ng, dimension=$(2ng), targets=$target, auxiliary=$(ncompute-target)."); flush(stdout)
        started = time()
        reset_counters!(a)
        d = DFTK.lobpcg_hyper(a, initial; prec=p, tol=solver["spinor_tolerance_ha"],
            maxiter=solver["spinor_maxiter"], miniter=solver["spinor_miniter"], n_conv_check=target)
        solver_stats = operator_stats(a)
        elapsed = time()-started
        x = d.X[:, 1:target]
        hx = a * x
        residuals = [norm(hx[:,n] - d.λ[n]*x[:,n]) for n in 1:target]
        oracle = sort(repeat(diagonal.λ[ik][1:starget]; inner=2))
        # Post-solve occupied-subspace oracle only; never used as the initial subspace.
        q = zeros(ComplexF64, 2ng, 8)
        for n in 1:4, c in 1:2
            q[c:2:end, 2(n-1)+c] = scalar_x[ik][:,n]
        end
        occupied = x[:,1:8]
        record = (; index=ik, coordinate_fractional=collect(k.coordinate),
            weight_spatial=basis.kweights[ik], ng, dimension=2ng, components=2,
            target_states=target, auxiliary_states=ncompute-target, seed,
            initial_source="Independent ComplexF64 Gaussian random subspace followed by thin QR",
            initial_orthogonality_frobenius=initial_gram, initial_component_norms,
            initial_imaginary_norm, initial_array_unchanged_by_solver=initial==initial_saved,
            target_component_norms=[[sum(abs2,x[c:2:end,n]) for c in 1:2] for n in 1:target],
            iterations=d.n_iter,
            elapsed_seconds=elapsed, converged=d.converged, solver_n_matvec=d.n_matvec,
            solver_operator_counters=solver_stats, counters_after_explicit_residual=operator_stats(a),
            eigenvalues_ha=d.λ[1:target], auxiliary_eigenvalues_ha=d.λ[target+1:end],
            scalar_repeated_oracle_ha=oracle, spectrum_difference_ha=d.λ[1:target]-oracle,
            explicit_residuals_ha=residuals, solver_reported_residuals_ha=d.residual_norms,
            orthogonality_frobenius=norm(x'x-I),
            occupied_subspace_leakage_frobenius=norm(occupied-q*(q'occupied)),
            occupied_overlap_singular_values=svdvals(q'occupied))
        push!(records, record)
        push!(spinor_x, x); push!(spinor_hx, hx); push!(spinor_lambda, collect(d.λ))
        serialize(joinpath(outdir, "spinor-k$ik-orbitals.bin"), (; x=d.X, eigenvalues=d.λ))
        save_result(outdir, result)
    end
    weights = basis.kweights
    scalar_occ = fixed_gapped_occupations(diagonal.λ, weights; representation=:scalar)
    spinor_occ = fixed_gapped_occupations(spinor_lambda, weights; representation=:spinor)
    result["scalar_occupations"] = scalar_occ
    result["spinor_occupations"] = spinor_occ
    # Reconstruct independently from actually solved occupied orbitals. Empty targets
    # and auxiliaries contribute exactly zero; no scalar density is copied to spinors.
    scalar_u = [component_ifft(basis, k, unflatten_components(scalar_x[ik][:,1:4], 1))
                for (ik,k) in enumerate(basis.kpoints)]
    spinor_u = [component_ifft(basis, k, unflatten_components(spinor_x[ik][:,1:8], 2))
                for (ik,k) in enumerate(basis.kpoints)]
    scalar_density = density_from_real_states(scalar_u, weights, [f[1:4] for f in scalar_occ.occupations])
    spinor_density = density_from_real_states(spinor_u, weights, [f[1:8] for f in spinor_occ.occupations])
    scalar_scf_rho = vec(DFTK.total_density(scf.ρ))
    scalar_dftk_rho = vec(DFTK.total_density(DFTK.compute_density(basis,
        [x[:,1:4] for x in scalar_x], [f[1:4] for f in scalar_occ.occupations])))
    l2(x) = sqrt(basis.dvol)*norm(x)
    reference_norm = l2(scalar_density.n)
    reference_norm > 0 || error("Zero reference density norm")
    nspin = basis.dvol*sum(spinor_density.n)
    nscalar = basis.dvol*sum(scalar_density.n)
    result["density"] = (; scalar_electron_count=nscalar, spinor_electron_count=nspin,
        scalar_final_h_l2=reference_norm,
        spinor_vs_scalar_final_h_relative_l2=l2(spinor_density.n-scalar_density.n)/reference_norm,
        scalar_adapter_vs_dftk_relative_l2=l2(scalar_density.n-scalar_dftk_rho)/reference_norm,
        scalar_final_h_vs_saved_scf_relative_l2=l2(scalar_density.n-scalar_scf_rho)/reference_norm,
        spinor_vs_saved_scf_relative_l2=l2(spinor_density.n-scalar_scf_rho)/reference_norm,
        pauli_density_l2=l2(spinor_density.m), charge_density_l2=l2(spinor_density.n),
        pauli_relative_l2=l2(spinor_density.m)/l2(spinor_density.n),
        integrated_pauli_components=basis.dvol*vec(sum(spinor_density.m; dims=2)),
        minimum_n_minus_m=minimum(spinor_density.n-vec(sqrt.(sum(abs2, spinor_density.m; dims=1)))),
        density_matrix_hermiticity_max=maximum(norm(spinor_density.R[:,:,r]-spinor_density.R[:,:,r]') for r in axes(spinor_density.R,3)),
        definition="R_ab=sum(w*f*u_a*conj(u_b)); my=-2imag(R12); m is Pauli density, not magnetic moment")
    expectation(xs,hxs,occs,nocc) = sum(weights[ik]*sum(occs[ik][n]*real(dot(x[:,n],hxs[ik][:,n]))
        for n in 1:nocc) for (ik,x) in enumerate(xs))
    eigenvalue_sum(values,occs) = sum(weights .* [dot(f, e) for (f,e) in zip(occs,values)])
    escalar = expectation(scalar_x,scalar_hx,scalar_occ.occupations,4)
    espin = expectation(spinor_x,spinor_hx,spinor_occ.occupations,8)
    sumscalar = eigenvalue_sum(diagonal.λ,scalar_occ.occupations)
    sumspin = eigenvalue_sum(spinor_lambda,spinor_occ.occupations)
    result["fixed_h_band_energy"] = (; scalar_expectation_ha_cell=escalar,
        spinor_expectation_ha_cell=espin, difference_ha_cell=espin-escalar,
        scalar_occupied_eigenvalue_sum_ha_cell=sumscalar, spinor_occupied_eigenvalue_sum_ha_cell=sumspin,
        scalar_expectation_minus_sum_ha_cell=escalar-sumscalar,
        spinor_expectation_minus_sum_ha_cell=espin-sumspin,
        definition="Occupied expectation of the same fixed scalar SCF Hamiltonian; NOT a DFT total energy")
    serialize(joinpath(outdir, "final-reference-and-density.bin"),
        (; scalar_x, scalar_eigenvalues=diagonal.λ, scalar_density, spinor_density, scalar_scf_rho))
    gates = Dict{String,Any}()
    function gate(name, value, threshold)
        gates[name] = (; measured=value, threshold, status=isfinite(value) && value<=threshold ? "PASS" : "FAIL")
    end
    a = settings["acceptance"]
    gate("scalar_explicit_residual_ha", maximum(maximum,scalar_res), a["explicit_residual_ha"])
    gate("scalar_orthogonality_frobenius", maximum(norm(x'x-I) for x in scalar_x), a["orthogonality_frobenius"])
    gate("spinor_explicit_residual_ha", maximum(maximum(r.explicit_residuals_ha) for r in records), a["explicit_residual_ha"])
    gate("spinor_orthogonality_frobenius", maximum(r.orthogonality_frobenius for r in records), a["orthogonality_frobenius"])
    gate("spectrum_max_abs_ha", maximum(maximum(abs,r.spectrum_difference_ha) for r in records), a["spectrum_max_abs_ha"])
    gate("electron_count_abs", max(abs(nspin-8),abs(nscalar-8)), a["electron_count_abs"])
    gate("density_relative_l2", result["density"].spinor_vs_scalar_final_h_relative_l2, a["density_relative_l2"])
    gate("pauli_density_relative_l2", result["density"].pauli_relative_l2, a["pauli_density_relative_l2"])
    gate("fixed_h_expectation_abs_ha_cell", abs(espin-escalar), a["fixed_h_expectation_abs_ha_cell"])
    gate("scalar_expectation_vs_sum_abs_ha_cell", abs(escalar-sumscalar), a["fixed_h_expectation_abs_ha_cell"])
    gate("spinor_expectation_vs_sum_abs_ha_cell", abs(espin-sumspin), a["fixed_h_expectation_abs_ha_cell"])
    result["acceptance"] = gates
    result["solver_execution_status"] = diagonal.converged && all(r.converged && r.iterations>0 for r in records) ? "PASS" : "FAIL"
    result["engineering_acceptance_status"] = all(g.status=="PASS" for g in values(gates)) ? "PASS" : "FAIL"
    save_result(outdir, result)
    result["solver_execution_status"] == "PASS" || error("A final-H solver did not converge through real iterations")
    result["engineering_acceptance_status"] == "PASS" || error("A predeclared engineering gate failed; retain results for review")
end

function main(args)
    if args in (["--help"], ["-h"])
        println("Usage: run_spinor_b0.jl [--preflight] NEW_IGNORED_RUN_DIRECTORY")
        return 0
    end
    preflight = length(args)==2 && first(args)=="--preflight"
    (length(args)==1 || preflight) || (println(stderr,"Invalid arguments"); return 2)
    outdir = abspath(last(args))
    ignoredroot = joinpath(ROOT,".work") * "/"
    startswith(outdir,ignoredroot) || (println(stderr,"Raw orbitals must stay in .work"); return 2)
    ispath(outdir) && (println(stderr,"Refusing to reuse a run directory"); return 2)
    result = Dict{String,Any}("schema_version"=>1, "phase"=>"5A", "base_commit"=>BASE,
        "run_id"=>basename(outdir), "started_utc"=>string(now(UTC)),
        "execution_status"=>"RUNNING", "engineering_acceptance_status"=>"NOT_RUN",
        "numerical_review_status"=>"REVIEW_REQUIRED", "spinor_scf_status"=>"NOT_IMPLEMENTED",
        "spinor_total_energy_status"=>"NOT_IMPLEMENTED", "scalar_scf_status"=>"NOT_RUN",
        "mode"=>preflight ? "interface_preflight_no_scf" : "real_b0_fixed_h",
        "layout"=>"Psi[component,G,state]; row=component+ncomp*(G-1); kron(Hscalar,Icomp)")
    code = 0
    try
        mkpath(outdir)
        save_result(outdir,result)
        settings = TOML.parsefile(joinpath(ROOT,TOLERANCES))
        result["predeclared_settings"] = settings
        case,basis,kinetic = prepare!(result)
        save_result(outdir,result)
        if preflight
            interface_preflight!(result,basis,kinetic,outdir)
        else
            calculate!(result,case,basis,kinetic,settings,outdir)
        end
        result["execution_status"] = "PASS"
    catch err
        code = 1
        result["execution_status"] = "FAIL"
        result["scalar_scf_status"] == "RUNNING" && (result["scalar_scf_status"] = "FAIL")
        result["failure_reason"] = sprint(showerror,err)
        showerror(stderr,err,catch_backtrace()); println(stderr)
    end
    result["exit_code"] = code
    result["finished_utc"] = string(now(UTC))
    try
        save_result(outdir,result)
    catch err
        println(stderr,"Persistence failed: ",sprint(showerror,err))
        try
            save_result(outdir,Dict("schema_version"=>1,"run_id"=>basename(outdir),
                "execution_status"=>"FAIL","exit_code"=>1,"failure_reason"=>"Persistence failed; see log"))
        catch
            println(stderr,"Unable to persist even a safe failure record")
        end
        return 1
    end
    println("Run $(basename(outdir)): $(result["execution_status"]), exit_code=$code"); flush(stdout)
    code
end

exit(main(ARGS))
