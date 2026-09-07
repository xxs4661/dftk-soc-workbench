# Shared only by the new Phase 5B driver/tests. Historical B0/5A files are unchanged.
function build_b0(root)
    base = "60140a4148a510f0b2eb36f7bf00d683f3105a9a"
    casefile = "benchmarks/si-sr-lda/case.json"
    identity = environment_identity(root, (DFTK, PseudoPotentialIO))
    identity.status == "PASS" || error("Frozen environment identity mismatch")
    DFTK.disable_threading()
    Threads.nthreads()==1 && BLAS.get_num_threads()==1 &&
        DFTK.mpi_nprocs(DFTK.MPI.COMM_WORLD)==1 || error("B0 requires serial CPU execution")
    read(joinpath(root,casefile)) == read(`git -C $root show $base\:$casefile`) ||
        error("Historical B0 case changed")
    case = JSON3.read(read(joinpath(root,casefile),String),Dict{String,Any})
    psppath = joinpath(root,case["pseudo"]["local_path"])
    filehash(psppath)==case["pseudo"]["sha256"] || error("B0 Si UPF checksum mismatch")
    upf = PseudoPotentialIO.load_psp_file(psppath)
    upf isa PseudoPotentialIO.UpfFile || error("Expected UpfFile")
    h = upf.header
    h.element=="Si" && h.pseudo_type=="NC" && h.relativistic=="scalar" && !h.has_so &&
        h.z_valence==4 && h.core_correction || error("Wrong Si scalar NC/NLCC metadata")
    split(h.functional)==split(case["xc"]["upf_functional"]) || error("Wrong UPF functional")
    psp = DFTK.PspUpf(upf;identifier=basename(psppath),rcut=case["pseudo"]["dftk_rcut_bohr"])
    geometry = case["geometry"]
    lattice = reduce(hcat,[Float64.(v) for v in geometry["lattice_vectors_bohr"]])
    positions = [Float64.(v) for v in geometry["positions_fractional"]]
    atoms = [DFTK.ElementPsp(:Si,psp) for _ in geometry["species"]]
    model = DFTK.model_DFT(lattice,atoms,positions;
        functionals=Symbol.(case["xc"]["dftk_identifiers"]), n_electrons=8,
        spin_polarization=:none,temperature=0.0,symmetries=false)
    coords = [Float64.(p["coordinate_fractional"]) for p in case["kpoints"]]
    weights = Float64[p["weight_spatial"] for p in case["kpoints"]]
    basis = DFTK.PlaneWaveBasis(model;Ecut=case["cutoffs"]["dftk_ecut_ha"],
        kgrid=DFTK.ExplicitKpoints(coords,weights))
    length(basis.kpoints)==8 && length(model.symmetries)==1 || error("B0 k/symmetry mismatch")
    used = Int[]
    for (ik,kpt) in enumerate(basis.kpoints)
        matches = findall(coords) do coord
            delta = collect(kpt.coordinate)-coord
            maximum(abs.(delta-round.(delta)))<1e-12
        end
        length(matches)==1 || error("Ambiguous k-point association")
        idx = only(matches)
        idx in used && error("Duplicate k point")
        push!(used,idx)
        abs(basis.kweights[ik]-weights[idx])<1e-12 || error("Wrong spatial weight")
    end
    check_supported_basis(basis)
    provenance = (; environment=identity,base_commit=base,
        case_sha256=filehash(joinpath(root,casefile)),pseudo_sha256=filehash(psppath),
        geometry=case["geometry"],ecut_ha=basis.Ecut,fft_grid=collect(basis.fft_size),
        dvol_bohr3=basis.dvol,volume_bohr3=model.unit_cell_volume,
        n_electrons=8,xc=case["xc"]["dftk_identifiers"],nlcc=true,
        parallelism=(;julia=Threads.nthreads(),dftk=DFTK.get_DFTK_threads(),
                     blas=BLAS.get_num_threads(),fft=DFTK.FFTW.get_num_threads(),mpi=1),
        kpoints=[(;coordinate_fractional=collect(k.coordinate),weight_spatial=basis.kweights[ik],
            ng=length(DFTK.G_vectors(basis,k))) for (ik,k) in enumerate(basis.kpoints)])
    (;basis,case,provenance)
end

function initial_densities(basis, settings)
    original = vec(DFTK.total_density(DFTK.guess_density(basis)))
    all(isfinite,original) && minimum(original)>=0 || error("Invalid guess density")
    count_before = basis.dvol*sum(original)
    count_before>0 || error("Empty initial density")
    scale = 8/count_before
    n0 = original .* scale  # This is the only normalization in A/B initialization.
    init = settings["initialization"]
    q = [cos(2π*dot(init["perturbation_reciprocal_vector"],r)) for r in vec(DFTK.r_vectors(basis))]
    qbar = dot(n0,q)/sum(n0)
    perturbed = n0 .* (1 .+ init["perturbation_amplitude"].*(q.-qbar))
    norm(perturbed-n0)>0 && minimum(perturbed)>=0 || error("Perturbation invalid or zero")
    abs(basis.dvol*sum(perturbed)-8)<=settings["acceptance"]["electron_count_abs"] ||
        error("Perturbation changed valence electron count")
    digest(n)=bytes2hex(sha256(reinterpret(UInt8,vec(n))))
    report=(;source="DFTK.guess_density before any scalar SCF",count_before,
        scale_applied_once=scale,count_after=basis.dvol*sum(n0),original_sha256=digest(original),
        a_sha256=digest(n0),b_sha256=digest(perturbed),qbar,
        a_minimum=minimum(n0),b_minimum=minimum(perturbed),
        b_electron_count=basis.dvol*sum(perturbed),
        perturbation_l2=sqrt(basis.dvol)*norm(perturbed-n0),
        formula="n0*(1+0.01*(cos(2pi*(x+2y+3z))-qbar)); fractional real-grid coordinates",
        seed_a=init["seed_a"],seed_b=init["seed_b"])
    (;a=n0,b=perturbed,report)
end
