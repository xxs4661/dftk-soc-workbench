#!/usr/bin/env julia
# Phase 4B only: scalar Si SCF, followed by eight converged bands at the final SCF potential.
# API evidence: DFTK 2f51b91213e26726fb9c6a17e5fae235a1412d01:
# src/bzmesh.jl:102; src/scf/nbands_algorithm.jl:19;
# src/scf/self_consistent_field.jl:239,270; src/eigen/diag.jl:10.
using JSON3, SHA, LinearAlgebra
using DFTK, PseudoPotentialIO
include(joinpath(@__DIR__, "workbench_environment.jl"))
using .WorkbenchEnvironment

const ROOT = realpath(joinpath(@__DIR__, ".."))

function finite_data(value)
    if value isa AbstractFloat
        isfinite(value) || error("Nonfinite number in DFTK result")
    elseif value isa AbstractDict || value isa NamedTuple
        foreach(finite_data, values(value))
    elseif value isa AbstractArray || value isa Tuple
        foreach(finite_data, value)
    end
    nothing
end

function write_result(path, result)
    finite_data(result)
    data = JSON3.write(public_data(result, ROOT)) * "\n"
    open(path * ".tmp", "w") do io
        write(io, data)
    end
    mv(path * ".tmp", path; force=true)
end

# Coordinates may differ by an integer reciprocal-lattice vector, never by energy matching.
function check_kpoints(basis, requested)
    length(basis.kpoints) == length(requested) || error("Actual k-point count mismatch")
    used = Int[]
    for (ik, kpt) in enumerate(basis.kpoints)
        matches = findall(requested) do point
            delta = collect(kpt.coordinate) - Float64.(point["coordinate_fractional"])
            maximum(abs.(delta - round.(delta))) < 1e-12
        end
        length(matches) == 1 || error("Missing or ambiguous requested k-point")
        index = only(matches)
        index in used && error("Duplicate actual k-point")
        push!(used, index)
        abs(basis.kweights[ik] - requested[index]["weight_spatial"]) < 1e-12 ||
            error("Actual spatial k-point weight mismatch")
    end
end

function check_occupations(occupation, weights, settings)
    length(occupation) == length(weights) || error("Occupation/k-point count mismatch")
    nocc = settings["n_occupied"]
    capacity = settings["spin_degeneracy"]
    for occ in occupation
        length(occ) >= settings["n_bands"] || error("Insufficient occupation entries")
        all(occ[1:nocc] .== capacity) && all(iszero, occ[nocc+1:end]) ||
            error("Fixed nonmagnetic occupations were not attained at every k-point")
    end
    nelec = sum(weights .* sum.(occupation))
    abs(nelec - settings["n_electrons"]) < 1e-10 || error("Integrated electron count mismatch")
    nelec
end

function run_baseline!(result, casepath, psppath, outputpath)
    case = JSON3.read(read(casepath, String), Dict{String,Any})
    case["schema_version"] == 1 || error("Unsupported scalar case schema")
    result["case_sha256"] = case["source_case_sha256"]
    result["input_sha256"] = filehash(casepath)
    result["pseudo_sha256"] = filehash(psppath)
    result["pseudo_sha256"] == case["pseudo"]["sha256"] || error("Si UPF checksum mismatch")

    # This compares real loaded paths before any public-data path redaction.
    identity = environment_identity(ROOT, (DFTK, PseudoPotentialIO))
    result["environment"] = identity
    identity.status == "PASS" || error("Workbench environment identity mismatch")
    DFTK.disable_threading()
    DFTK.mpi_nprocs(DFTK.MPI.COMM_WORLD) == 1 || error("This baseline requires one MPI process")
    result["parallelism"] = Dict("julia_threads" => Threads.nthreads(),
        "dftk_threads" => DFTK.get_DFTK_threads(), "blas_threads" => BLAS.get_num_threads(),
        "fft_threads" => DFTK.FFTW.get_num_threads(), "mpi_processes" => 1)

    parsed = PseudoPotentialIO.load_psp_file(psppath)
    parsed isa PseudoPotentialIO.UpfFile || error("Input was not parsed as UpfFile")
    header = parsed.header
    header.element == "Si" && header.pseudo_type == "NC" &&
        header.relativistic == "scalar" && !header.has_so && header.z_valence == 4 ||
        error("Input is not the required scalar-relativistic Si NC UPF")
    split(header.functional) == split(case["xc"]["upf_functional"]) ||
        error("UPF functional differs from the case")
    header.core_correction == case["pseudo"]["nlcc"] || error("UPF NLCC header mismatch")
    rcut = case["pseudo"]["dftk_rcut_bohr"]
    psp = DFTK.PspUpf(parsed; identifier=basename(psppath), rcut)
    DFTK.has_core_density(psp) == case["pseudo"]["nlcc"] || error("Loaded NLCC density mismatch")
    result["pseudo"] = Dict("filename" => basename(psppath), "sha256" => result["pseudo_sha256"],
        "upf_version" => parsed.version, "pseudo_type" => header.pseudo_type,
        "element" => header.element, "relativistic" => header.relativistic,
        "has_so" => header.has_so, "z_valence" => header.z_valence,
        "functional_raw" => header.functional, "nlcc" => DFTK.has_core_density(psp),
        "rcut_requested_bohr" => rcut, "rcut_actual_bohr" => psp.rcut,
        "radial_grid_last_bohr" => last(psp.rgrid), "radial_cutoff_index" => psp.ircut,
        "radial_grid_points" => length(psp.rgrid))

    geometry = case["geometry"]
    electrons = case["electrons"]
    electrons["spin_polarization"] == "none" && electrons["temperature_ha"] == 0 &&
        electrons["occupations"] == "fixed" && electrons["spin_degeneracy"] == 2 ||
        error("Unsupported spin, temperature, or occupation model")
    all(==("Si"), geometry["species"]) || error("This worker only supports the Si case")
    # Read the generated matrix explicitly; its columns are the configuration's vectors.
    # Also check against those source vectors so a generator transpose error cannot hide.
    lattice = reduce(vcat, [permutedims(Float64.(row)) for row in case["lattice_matrix_bohr"]])
    lattice == reduce(hcat, [Float64.(v) for v in geometry["lattice_vectors_bohr"]]) ||
        error("Generated DFTK lattice matrix does not contain the requested column vectors")
    positions = [Float64.(v) for v in geometry["positions_fractional"]]
    atoms = [ElementPsp(:Si, psp) for _ in geometry["species"]]
    functionals = Symbol.(case["xc"]["dftk_identifiers"])
    model = model_DFT(lattice, atoms, positions; functionals,
        n_electrons=electrons["n_electrons"], spin_polarization=:none,
        temperature=0.0, symmetries=false)
    coords = [Float64.(p["coordinate_fractional"]) for p in case["kpoints"]]
    weights = Float64[p["weight_spatial"] for p in case["kpoints"]]
    basis = PlaneWaveBasis(model; Ecut=case["cutoffs"]["dftk_ecut_ha"],
        kgrid=ExplicitKpoints(coords, weights))
    check_kpoints(basis, case["kpoints"])
    length(model.symmetries) == 1 || error("Spatial symmetry reduction was not disabled")
    xc = only(filter(term -> term isa DFTK.Xc, model.term_types))
    xc_term = only(filter(term -> term isa DFTK.TermXc, basis.terms))
    actual_identifiers = string.(DFTK.identifier.(xc.functionals))
    actual_identifiers == case["xc"]["dftk_identifiers"] || error("Loaded XC identifier mismatch")
    xc.use_nlcc && (isnothing(xc_term.ρcore) == !case["pseudo"]["nlcc"]) ||
        error("Actual XC NLCC treatment mismatch")
    result["lattice_vectors_bohr"] = [collect(v) for v in eachcol(model.lattice)]
    result["positions_fractional"] = [collect(v) for v in model.positions]
    result["atom_symbols"] = string.(DFTK.element_symbol.(model.atoms))
    result["n_atoms"] = length(model.atoms)
    result["volume_bohr3"] = model.unit_cell_volume
    result["n_electrons"] = model.n_electrons
    result["fft_grid"] = collect(basis.fft_size)
    result["ecut_ha"] = basis.Ecut
    result["xc_raw"] = actual_identifiers
    result["xc_backend"] = Dict("dispatch" => string.(typeof.(xc.functionals)),
        "libxc_version" => string(DFTK.Libxc.libxc_version),
        "libxc_julia_version" => string(pkgversion(DFTK.Libxc)), "use_nlcc" => xc.use_nlcc,
        "core_density_present" => !isnothing(xc_term.ρcore))
    result["input_settings"] = Dict("spin_polarization" => string(model.spin_polarization),
        "temperature_ha" => model.temperature, "occupation_function" => string(typeof(model.smearing)),
        "symmetry_operations" => length(model.symmetries),
        "weight_convention" => "spatial weights sum to 1; raw occupations include spin degeneracy 2")
    result["reasons"] = ["Inputs and current loaded environment verified; SCF not completed"]
    write_result(outputpath, result)
    println("Scalar Si inputs and current loaded environment verified. Starting SCF.")

    settings = case["scf"]
    nbands = electrons["n_bands"]
    ncompute = nbands + settings["extra_bands"]
    dtol = settings["diagonalization_tol_ha"]
    # FixedBands explicitly checks all eight target bands, including empty bands.
    # Equal AdaptiveDiagtol bounds give a known residual tolerance at every SCF step.
    diagtolalg = DFTK.AdaptiveDiagtol(; diagtol_first=dtol, diagtol_min=dtol, diagtol_max=dtol)
    scf = self_consistent_field(basis; tol=settings["dftk_tol"], maxiter=settings["maxiter"],
        nbandsalg=FixedBands(; n_bands_converge=nbands, n_bands_compute=ncompute),
        diagtolalg, seed=0)
    result["converged"] = scf.converged
    result["n_bands"] = nbands
    result["n_bands_computed"] = length(first(scf.eigenvalues))
    all(length(e) == ncompute for e in scf.eigenvalues) || error("Computed SCF band count mismatch")
    result["energy_ha"] = scf.energies.total
    result["energy_raw"] = Dict("value" => scf.energies.total, "unit" => "Ha/cell",
        "source" => "self_consistent_field final scfres.energies.total; not eigenvalue sum")
    result["energy_components_ha"] = Dict(pairs(scf.energies))
    result["scf"] = Dict("converged" => scf.converged, "iterations" => scf.n_iter,
        "timedout" => scf.timedout, "tol" => settings["dftk_tol"],
        "criterion" => "L2 density change: norm(rho_out-rho_in)*sqrt(basis.dvol) < tol",
        "density_residual_history" => scf.history_Δρ, "energy_history_ha" => scf.history_Etot,
        "diagonalization_tolerance_ha" => dtol,
        "last_diagonalization_converged" => all(d.converged for d in scf.diagonalization),
        "last_diagonalization_iterations" => [d.n_iter for d in scf.diagonalization],
        "last_diagonalization_residuals_ha" => [d.residual_norms for d in scf.diagonalization],
        "eigenvalues_ha" => scf.eigenvalues, "occupations_raw" => scf.occupation,
        "fermi_energy_ha" => scf.εF, "seed" => scf.seed)
    write_result(outputpath, result)
    scf.converged || error("DFTK SCF did not converge")
    all(d.converged for d in scf.diagonalization) || error("Final SCF diagonalization did not converge")
    check_occupations(scf.occupation, basis.kweights, electrons)

    # DFTK rebuilds scf.ham from final rho after the last SCF diagonalization.
    # Diagonalize that same final Hamiltonian once, retaining the original SCF total energy.
    println("SCF converged; diagonalizing its final Hamiltonian for eight target bands.")
    diagonal = DFTK.diagonalize_all_kblocks(DFTK.lobpcg_hyper, scf.ham, ncompute;
        ψguess=scf.ψ, tol=dtol, n_conv_check=nbands, maxiter=settings["maxiter"])
    result["diagonalization"] = Dict("source" => "same final scfres.ham, no density update",
        "converged" => diagonal.converged, "tol_ha" => dtol, "maxiter" => settings["maxiter"],
        "n_bands_converge" => nbands, "n_bands_compute" => ncompute,
        "iterations_per_kpoint" => diagonal.n_iter,
        "residuals_ha" => diagonal.residual_norms, "all_eigenvalues_ha" => diagonal.λ)
    diagonal.converged || error("Final-potential diagonalization did not converge")
    all(maximum(res[1:nbands]) < dtol for res in diagonal.residual_norms) ||
        error("Target empty/occupied band residual exceeds the requested tolerance")
    occupation, fermi = DFTK.compute_occupation(basis, diagonal.λ)
    result["diagonalization"]["all_occupations_raw"] = occupation
    result["integrated_n_electrons"] = check_occupations(occupation, basis.kweights, electrons)
    result["fermi_energy_ha"] = fermi
    result["fermi_definition"] = "Zero-temperature DFTK midpoint of global HOMO and LUMO"
    result["kpoints"] = [Dict("coordinate_fractional" => collect(k.coordinate),
        "weight_raw" => basis.kweights[ik], "weight_spatial" => basis.kweights[ik],
        "occupations_raw" => occupation[ik][1:nbands], "occupations" => occupation[ik][1:nbands],
        "eigenvalues_ha" => diagonal.λ[ik][1:nbands],
        "npw" => length(DFTK.G_vectors(basis, k))) for (ik, k) in enumerate(basis.kpoints)]
    result["execution_status"] = "PASS"
    result["reasons"] = String[]
    finite_data(result)
    println("DFTK SCF and final-potential target-band diagonalization converged.")
end

function main(args)
    if args in (["--help"], ["-h"])
        println("Usage: run_dftk_baseline.jl CASE_JSON UPF_PATH OUTPUT_JSON")
        return 0
    end
    length(args) == 3 || (println(stderr, "Expected CASE_JSON UPF_PATH OUTPUT_JSON"); return 2)
    casepath, psppath, outputpath = args
    ispath(outputpath) && (println(stderr, "Refusing to reuse an existing result path"); return 2)
    result = Dict{String,Any}("schema_version" => 1, "code" => "DFTK",
        "execution_status" => "BLOCKED", "converged" => false, "reasons" => String[])
    code = 0
    try
        run_baseline!(result, casepath, psppath, outputpath)
    catch error
        code = 1
        result["execution_status"] = "FAIL"
        result["reasons"] = [sprint(showerror, error)]
        showerror(stderr, error, catch_backtrace())
        println(stderr)
    end
    result["exit_code"] = code
    try
        write_result(outputpath, result)
    catch error
        println(stderr, "DFTK result persistence failed: ", sprint(showerror, error))
        # Replace a possibly incomplete record with fresh finite failure data when writable.
        try
            write_result(outputpath, Dict("schema_version" => 1, "code" => "DFTK",
                "execution_status" => "FAIL", "converged" => false, "exit_code" => 1,
                "reasons" => ["Result serialization or persistence failed; see stderr"]))
        catch
        end
        return 1
    end
    code
end

exit(main(ARGS))
