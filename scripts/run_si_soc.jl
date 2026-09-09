#!/usr/bin/env julia
# One prescribed Si case; reuse the frozen ensemble, map controller and target solver.
include("run_soc_scf.jl")
include("../prototypes/crystal_soc/SpinTrace.jl")
const SI_CASE_DIR=joinpath(PHASE6C_ROOT,"benchmarks/si-soc-splitting-v1")
const SI_CORE_BASE="c764311a5422b5c3cab5a7b78a02d420910c4e56"
const SI_CORE_PREPARATION="e4f16a51a0304f5e70f5ae038563d6760409c2c4"
const SI_BASE="9342a5ea21a76acd0d74d228d4a2081394f702d0"
const SI_SENSITIVITY_BASE="bc68aaf655d96dfd4335f6fa1a8e5ee76477c2a3"
const SI_SENSITIVITY_PREPARATION="4a58286183e4625ad7ae69b44eb80097e8ad6c7d"
const SI_SENSITIVITY_DIR="benchmarks/si-soc-sensitivity-v1"
si_json(path)=JSON3.read(read(path,String),Dict{String,Any})
function si_profile(profile)
    profile isa AbstractString && profile in ("E40","T05","K4") || error("Unregistered Si sensitivity profile")
    String(profile)
end
si_case_path(profile)=isnothing(profile) ? "benchmarks/si-soc-splitting-v1/case.json" : "$SI_SENSITIVITY_DIR/$(si_profile(profile))/case.json"
function si_prepared_bytes(path)
    file=joinpath(PHASE6C_ROOT,path)
    islink(file) && error("Prepared input cannot be a symlink")
    bytes=read(file);ref="$SI_SENSITIVITY_PREPARATION:$path"
    bytes==read(`git -C $PHASE6C_ROOT show $ref`) || error("Prepared Si input changed: $path")
    bytes
end
function si_case(profile=nothing)
    isnothing(profile) && return si_json(joinpath(SI_CASE_DIR,"case.json"))
    case=JSON3.read(String(si_prepared_bytes(si_case_path(profile))),Dict{String,Any})
    SOC.validate_soc_settings(case["settings"];case_contract=case)
    case
end
function si_sources(profile=nothing;backend=nothing)
    files=collect(keys(phase6c_sources()))
    append!(files,["prototypes/crystal_soc/SpinTrace.jl","scripts/run_si_soc.jl"])
    append!(files,["benchmarks/si-soc-splitting-v1/"*f for f in ("case.json","source.json","plan.json","qe-scf.in","qe-spectrum.in")])
    if !isnothing(profile)
        profile=si_profile(profile)
        prepared=["$SI_SENSITIVITY_DIR/$f" for f in ("plan.json","allowed-differences.json","replay-contract.json")]
        append!(prepared,["$SI_SENSITIVITY_DIR/$profile/$f" for f in ("case.json","qe-scf.in","qe-gamma.in")])
        push!(prepared,"benchmarks/si-soc-splitting-v1/source.json")
        foreach(si_prepared_bytes,prepared)
        append!(files,prepared)
    end
    if !isnothing(backend)
        backend=="soc-core" && isnothing(profile) || error("Unregistered core source/backend combination")
        append!(files,["src/SOCKernels.jl","prototypes/fr_integration/runtime.jl","scripts/run_si_dftk.py","benchmarks/soc-core-memory-v1/run.py"])
        for (directory,_,names) in walkdir(joinpath(PHASE6C_ROOT,"src/soc_kernels"))
            append!(files,[relpath(joinpath(directory,f),PHASE6C_ROOT) for f in names if endswith(f,".jl")])
        end
        for file in ("README.md","plan.json","sources.json","contract.json")
            path="benchmarks/soc-core-memory-v1/$file"
            read(joinpath(PHASE6C_ROOT,path))==read(`git -C $PHASE6C_ROOT show $(SI_CORE_PREPARATION*":"*path)`) || error("Core preparation changed")
            push!(files,path)
        end
    end
    Dict(f=>filehash(joinpath(PHASE6C_ROOT,f)) for f in unique(files))
end
function si_core_gate(path,execution)
    isnothing(path) && error("Core static gate is required")
    python=get(ENV,"SOC_CORE_PYTHON","");isfile(python) || error("Explicit recorder Python required for static gate authentication")
    record=JSON3.read(read(`$python -B $(joinpath(PHASE6C_ROOT,"scripts/run_si_dftk.py")) --verify-core-gate $PHASE6C_ROOT $path $execution`,String),Dict{String,Any})
    record["sha256"]==filehash(path) || error("Core gate changed during verification")
    record["sha256"]
end
function si_context(case,kind;backend=nothing)
    if haskey(case,"sensitivity_profile")
        SOC.validate_soc_settings(case["settings"];case_contract=case)
        kind in ("scf","spectrum") || error("Sensitivity cases allow only SCF or Gamma contexts")
    end
    spec=si_json(joinpath(SI_CASE_DIR,"source.json"))
    bundle=FI.load_bound_psp(PHASE6C_ROOT;source_spec=spec)
    g=case["geometry"];lat=reduce(hcat,Float64.(v) for v in g["lattice_vectors_bohr"])
    pos=[Float64.(p) for p in g["positions_fractional"]]
    if kind=="scf"
        k=[Float64.(p["coordinate_fractional"]) for p in case["kpoints"]]
        w=Float64[p["weight_spatial"] for p in case["kpoints"]]
    elseif kind=="spectrum"
        k=[Float64.(p) for p in case["probe_kpoints"]];w=Float64.(case["probe_weights"])
    elseif kind=="null" || (kind=="core_gamma" && backend=="soc-core")
        k=[[0.,0.,0.]];w=[1.]
    else;error("Unknown fixed Si grid");end
    ctx=FI.build_context(fill(bundle,length(pos)),lat,pos,k,w;Ecut=case["cutoffs"]["dftk_ecut_ha"],
        xc_identifiers=Symbol.(case["xc"]["dftk_identifiers"]),mode=:real_fr,
        temperature=case["electrons"]["temperature_ha"],smearing=DFTK.Smearing.FermiDirac(),fft_size=case["fft_size"])
    ctx.basis.model.n_electrons==8 && length(ctx.bundles)==2 && ctx.basis.fft_size==(48,48,48) || error("Wrong Si case dimensions")
    derived_columns=length(RelativisticProjectors.projector_labels(bundle.channels,2))
    all(op->size(op.P,2)==derived_columns,ctx.fr_blocks) && derived_columns==72 || error("Actual parsed Si projector columns differ")
    (;ctx,bundle)
end

"""Diagnostic FD function only; the Gamma probe never solves an electron constraint."""
si_probe_occupations(levels,mu,tau)=[SOC.fermi_logistic((e-mu)/tau) for e in levels]

"""Use the existing physical-q and spinor maps only for the single Gamma block."""
function si_gamma_time_reversal(ctx,ham,settings)
    length(ham)==length(ctx.basis.kpoints)==1 && all(iszero,ctx.basis.kpoints[1].coordinate) || error("Expected only Gamma")
    k=only(ctx.basis.kpoints);mapping=FI.time_reversal_map(ctx.basis,k,k)
    seed=settings["seeds"]["symmetry_probe"]+11
    x=randn(MersenneTwister(seed),ComplexF64,size(only(ham),1),2);x/=norm(x)
    lhs=only(ham)*FI.time_reverse_spinor(x,mapping)
    rhs=FI.time_reverse_spinor(only(ham)*x,mapping)
    err=FI.integration_error(lhs,rhs)
    (;status=err<=settings["thresholds"]["time_reversal_normalized"] ? "PASS" : "FAIL",seed,
        time_reversal=[(;source=1,target=1,ng=length(mapping),bijection=true,
            reversal_map_sha256=FI._source_snapshot(mapping),normalized_error=err,absolute_error=norm(lhs-rhs))],
        scope="RUNNER_REPORTED Gamma physical-q operator check; off-Gamma TR NOT_RUN")
end
function si_grid(ctx)
    b=ctx.basis
    rows=map(b.kpoints) do k
        G=collect(DFTK.G_vectors(b,k));q=collect(DFTK.Gplusk_vectors_cart(b,k))
        widths=[maximum(g[i] for g in G)-minimum(g[i] for g in G) for i in 1:3]
        all(2widths[i]<b.fft_size[i] for i in 1:3) || error("BLOCKED_GRID: product reaches Nyquist")
        maxkin=maximum(dot(v,v)/2 for v in q)
        maxkin<=b.Ecut+1e-12 || error("Wavefunction cutoff violated")
        (;coordinate_fractional=collect(k.coordinate),ng=length(G),max_product_component=widths,
          max_kinetic_ha=maxkin,g_sha256=FI._source_snapshot(G))
    end
    # Deliberately overcount retained old/new/auxiliary orbitals, trial vectors,
    # source certificates, FFT temporaries, and native-library/runtime headroom.
    ngmax=maximum(r.ng for r in rows);nk=length(rows);nr=prod(b.fft_size)
    estimates=Dict("retained_orbitals_and_solver"=>16*2*ngmax*30*(12nk+60),
        "projectors_and_snapshots"=>16*2*ngmax*72*nk*4,
        "bounded_fft_workspaces"=>16*2*nr*24*8,
        "density_core_local_fields"=>8*nr*100,"runtime_library_margin"=>2*1024^3)
    peak=sum(values(estimates));peak<8*1024^3 || error("RESOURCE_BLOCKED: conservative bound exceeds8GiB")
    (;status="PASS",basis=FI.basis_summary(ctx),rows,nyquist="All actual same-k component difference extrema strictly below24; sufficient for every G-Gprime",memory_estimate_bytes=estimates,conservative_peak_bytes=peak)
end

"""Finite geometric support prediction; native QE output must confirm actual grids."""
function si_qe_grid_support(ctx,case)
    lattice=Matrix(ctx.basis.model.lattice)
    reciprocal=2π*inv(lattice)'
    density_cutoff=case["cutoffs"]["qe_ecutrho_ry"]/2
    case["cutoffs"]["qe_ecutrho_ry"]==4case["cutoffs"]["qe_ecutwfc_ry"] || error("NC density/smooth cutoff ratio changed")
    # g_i = a_i dot q / 2pi. Cauchy-Schwarz bounds the entire sphere,
    # including integer modes outside the enumerated finite FFT box.
    component_bounds=[sqrt(2density_cutoff)*norm(lattice[:,i])/(2π) for i in 1:3]
    all(x->isfinite(x) && x<24,component_bounds) || error("BLOCKED_GRID: QE density sphere can reach the 48-cubed boundary; bounds=$component_bounds")
    support=NTuple{3,Int}[]
    for i in -24:23,j in -24:23,k in -24:23
        q=reciprocal*[i,j,k]
        dot(q,q)/2<=density_cutoff && push!(support,(i,j,k))
    end
    minima=[minimum(g[i] for g in support) for i in 1:3]
    maxima=[maximum(g[i] for g in support) for i in 1:3]
    all(-24<minima[i]<=maxima[i]<24 for i in 1:3) || error("BLOCKED_GRID: QE density support reaches FFT boundary")
    (;status="PASS",evidence_level="GEOMETRIC_PREDICTION_REQUIRES_NATIVE_QE_OUTPUT",
        density_cutoff_ha=density_cutoff,smooth_cutoff_ha=density_cutoff,
        fft_grid=[48,48,48],enumerated_box_modes=48^3,sphere_mode_count=length(support),
        allowed_g_min=minima,allowed_g_max=maxima,analytic_abs_component_bounds=component_bounds,
        allowed_g_sha256=FI._source_snapshot(support),
        formula="|g_i| <= sqrt(2 E_rho_Ha) norm(a_i)/(2pi) < 24; enumerate q=2pi inv(lattice)'g in [-24,23]^3",
        native_scope="NC fixed ecutrho/ecutwfc=4 gives the same requested density/smooth sphere; actual QE hard/smooth grids are checked after execution")
end
"""Fourier coefficients of real(ifft(raw)); a reference, never a density mutation."""
function si_real_fourier_coefficients(raw::AbstractArray{<:Complex,3})
    represented=similar(raw)
    for I in CartesianIndices(raw)
        J=CartesianIndex(ntuple(d->mod1(2-I[d],size(raw,d)),3))
        represented[I]=(raw[I]+conj(raw[J]))/2
    end
    represented
end

function si_static_nlcc(ctx,case;progress=(report)->nothing)
    b=ctx.basis;c=first(ctx.bundles).common
    report=Dict{String,Any}("status"=>"RUNNING","scope"=>"RUNNER_REPORTED: prescribed static valence densities; no SCF",
        "allowed_density_evaluations"=>5,"completed_density_evaluations"=>0,"evaluations"=>Any[],"samples"=>Any[])
    publish()=progress(deepcopy(report))
    publish()
    xc=only(filter(t->t isa DFTK.TermXc,b.terms));modelxc=only(filter(t->t isa DFTK.Xc,b.model.term_types))
    modelxc.use_nlcc && !isnothing(xc.ρcore) && norm(xc.ρcore)>0 || error("Actual NLCC not enabled")
    core_before=FI.integration_density_hash(vec(xc.ρcore))
    actual=DFTK.fft(b,xc.ρcore[:,:,:,1]);g=collect(DFTK.G_vectors(b));gcart=collect(DFTK.G_vectors_cart(b))
    raw_atomic=map(zip(g,gcart)) do (gg,q)
        DFTK.eval_psp_core_density_fourier(c,norm(q))*sum(cis(-2π*dot(gg,p)) for p in b.model.positions)/sqrt(b.model.unit_cell_volume)
    end
    raw_atomic=reshape(raw_atomic,b.fft_size)
    # Frozen atomic_total_density ends with irfft = real(ifft). On an even,
    # nonorthogonal grid its cyclic Nyquist partners can have different |G|.
    # Compare the actual core to that identical representation: this formula
    # predicts the real projection; it never alters xc.ρcore or drops modes.
    represented=si_real_fourier_coefficients(raw_atomic)
    boundary=[any(abs(gg[i])==b.fft_size[i]÷2 for i in 1:3) for gg in vec(g)]
    normalize(a,b)=norm(a-b)/max(norm(a),norm(b),1)
    core_err=normalize(actual,represented)
    raw_delta=normalize(raw_atomic,represented)
    interior_error=normalize(vec(actual)[.!boundary],vec(raw_atomic)[.!boundary])
    single_g0=DFTK.eval_psp_core_density_fourier(c,0.)
    core_electrons=b.dvol*sum(xc.ρcore)
    g0_error=abs(core_electrons-2single_g0)
    merge!(report,Dict("core_hash"=>core_before,"upf_nlcc_hash"=>FI.integration_density_hash(c.nlcc_raw),
        "core_fourier_error"=>core_err,"raw_atomic_to_native_real_projection_delta"=>raw_delta,
        "raw_atomic_interior_error"=>interior_error,"nyquist_coefficient_count"=>count(boundary),
        "core_electrons"=>core_electrons,"single_atom_core_g0"=>single_g0,
        "core_g0_additive_expected"=>2single_g0,"core_g0_additivity_error"=>g0_error,
        "raw_atomic_g0"=>real(raw_atomic[1])*sqrt(b.model.unit_cell_volume),
        "xc_use_nlcc"=>modelxc.use_nlcc,"core_not_in_Ne"=>b.model.n_electrons==8,
        "fourier_convention"=>"Source radial factor times both atom phases / sqrt(Omega); separately predict the frozen real(ifft) Hermitian projection, retaining every grid coefficient",
        "core_values_modified"=>false))
    publish()
    max(core_err,interior_error)<=1e-11 && g0_error<=1e-11 || error("Two-atom core Fourier/phase/G0 mismatch")
    rs=vec(DFTK.r_vectors(b));nb=8/b.model.unit_cell_volume
    wave=[cos(2π*dot([1,2,3],r)) for r in rs]
    n0=nb.*(1 .+ 0.02 .* wave);direction=nb.*(wave.-sum(wave)/length(wave))
    abs(b.dvol*sum(direction))<=1e-12 || error("Static direction has nonzero integral")
    function start_evaluation(label,n)
        report["evaluation_in_progress"]=(;label,density_sha256=FI.integration_density_hash(n))
        publish()
    end
    function retain_evaluation(label,n,energy)
        push!(report["evaluations"],(;label,xc_energy_ha=energy,density_sha256=FI.integration_density_hash(n),
            valence_electrons=b.dvol*sum(n),minimum_valence_density=minimum(n)))
        report["completed_density_evaluations"]=length(report["evaluations"])
        delete!(report,"evaluation_in_progress")
        publish()
    end
    function evaluate(label,n)
        minimum(n)>0 || error("Static density is not positive")
        rho=FI.context_valence_rho(ctx,n)
        # Full frozen GGA derivative, including divergence, and its own energy.
        start_evaluation(label,n)
        v=DFTK.xc_potential_real(xc,b,nothing,nothing;ρ=rho)
        retain_evaluation(label,n,v.E)
        (;energy=v.E,potential=vec(v.potential),density_sha256=FI.integration_density_hash(n))
    end
    # One center common evaluation + four XC-only perturbations = exactly five.
    minimum(n0)>0 || error("Static center density is not positive")
    start_evaluation("center",n0)
    common=DFTK.energy_hamiltonian(b,nothing,nothing;ρ=FI.context_valence_rho(ctx,n0))
    retain_evaluation("center",n0,common.energies["Xc"])
    localterm=only(filter(t->t isa DFTK.TermAtomicLocal,b.terms))
    hartree=only(filter(t->t isa DFTK.TermHartree,b.terms))
    potential=vec(DFTK.total_local_potential(common.ham))-vec(localterm.potential_values)-
        vec(DFTK.apply_kernel(hartree,b,FI.context_valence_rho(ctx,n0)))
    analytic=b.dvol*dot(direction,potential)
    merge!(report,Dict("analytic_ha"=>analytic,"center_xc_ha"=>common.energies["Xc"],
        "center_density_sha256"=>FI.integration_density_hash(n0),"direction_sha256"=>FI.integration_density_hash(direction),
        "valence_electrons"=>b.dvol*sum(n0)))
    publish()
    for h in (1e-4,1e-5)
        plus=evaluate("plus_h=$(h)",n0+h*direction);minus=evaluate("minus_h=$(h)",n0-h*direction)
        numeric=(plus.energy-minus.energy)/(2h)
        push!(report["samples"],(;h,plus_xc_ha=plus.energy,minus_xc_ha=minus.energy,numeric_ha=numeric,
            plus_density_sha256=plus.density_sha256,minus_density_sha256=minus.density_sha256,
            normalized_error=abs(numeric-analytic)/max(1,abs(analytic))))
        publish()
    end
    report["core_unchanged"]=core_before==FI.integration_density_hash(vec(xc.ρcore))
    report["convention"]="Frozen Xc evaluates valence+core once; Hartree/FD and integral n*vxc use valence only; no core compensation constant"
    publish()
    report["core_unchanged"] || error("Core changed during variation")
    report["completed_density_evaluations"]==5 || error("Static XC evaluation count differs from plan")
    last(report["samples"]).normalized_error<=1e-6 || error("Static full-GGA directional derivative failed")
    report["status"]=abs(analytic)>=1e-10 ? "PASS" : "INCONCLUSIVE"
    publish()
    (;report,full=FI.compose_full_hamiltonian(ctx,common.ham))
end
function si_append(path,x)
    phase6b_finite(x);open(path,"a") do io;write(io,JSON3.write(x)*"\n");flush(io);end
end
"""Check a new Si D-SCF receipt before admitting its final density as a parent."""
function si_validate_parent_receipt(receipt,case,sources,execution_commit;backend=nothing,core_gate_sha256=nothing)
    receipt isa AbstractDict || error("Parent must be a result object")
    profile=get(case,"sensitivity_profile",nothing)
    expected_case=isnothing(profile) ? "si-soc-splitting-v1" : case["case"]
    expected_base=backend=="soc-core" ? SI_CORE_BASE : isnothing(profile) ? SI_BASE : SI_SENSITIVITY_BASE
    if !isnothing(backend)
        backend=="soc-core" && isnothing(profile) || error("Wrong parent backend/profile")
        get(receipt,"backend",nothing)==backend && get(receipt,"core_gate_sha256",nothing)==core_gate_sha256 &&
            get(receipt,"runtime_closed",nothing)===true && get(receipt,"runtime_dispatch_status",nothing)=="PASS" || error("BLOCKED_PARENT: parent did not complete the current owned backend")
    end
    if !isnothing(profile)
        SOC.validate_soc_settings(case["settings"];case_contract=case)
        get(receipt,"sensitivity_profile",nothing)==profile &&
            get(receipt,"case_sha256",nothing)==filehash(joinpath(PHASE6C_ROOT,si_case_path(profile))) &&
            get(receipt,"temperature_ha",nothing)==case["electrons"]["temperature_ha"] || error("Parent sensitivity case/temperature binding differs")
    end
    get(receipt,"schema_version",nothing) === 1 && get(receipt,"case",nothing)==expected_case &&
        get(receipt,"base_commit",nothing)==expected_base || error("Wrong parent schema/case/base")
    get(receipt,"action",nothing)==(backend=="soc-core" ? "OPT-B0-SCF" : "D-SCF") && get(receipt,"execution_status",nothing)=="PASS" &&
        get(receipt,"exit_code",nothing) === 0 || error("Parent SCF is not successful")
    get(receipt,"execution_commit",nothing)==execution_commit &&
        get(receipt,"executed_source_sha256",nothing)==sources || error("Parent code/input execution binding differs")
    input=get(receipt,"input",nothing)
    input isa AbstractDict && get(input,"sha256",nothing)==case["pseudo"]["sha256"] &&
        get(input,"element",nothing)=="Si" && get(input,"z_valence",nothing)==4 &&
        get(input,"functional",nothing)=="PBE" && get(input,"mode",nothing)=="real_fr" &&
        get(input,"has_so",nothing)===true && get(input,"nlcc_present",nothing)===true &&
        get(input,"xc_identifiers",nothing)==case["xc"]["dftk_identifiers"] || error("Parent source/XC/NLCC mismatch")
    grid=get(receipt,"grid",nothing)
    grid isa AbstractDict && get(grid,"status",nothing)=="PASS" || error("Parent grid was not accepted")
    b=get(grid,"basis",nothing)
    b isa AbstractDict && get(b,"fft_grid",nothing)==case["fft_size"] &&
        get(b,"n_electrons",nothing)==8 && get(b,"ecut_ha",nothing)==case["cutoffs"]["dftk_ecut_ha"] &&
        get(b,"lattice_bohr",nothing)==case["geometry"]["lattice_vectors_bohr"] &&
        get(b,"positions_fractional",nothing)==case["geometry"]["positions_fractional"] || error("Parent geometry/FFT/electron count mismatch")
    points=get(b,"kpoints",nothing)
    points isa AbstractVector && length(points)==length(case["kpoints"]) || error("Parent SCF k-count mismatch")
    all(p isa AbstractDict && get(p,"coordinate_fractional",nothing)==q["coordinate_fractional"] &&
        get(p,"weight_spatial",nothing)==q["weight_spatial"] for (p,q) in zip(points,case["kpoints"])) || error("Parent SCF k/weight mismatch")
    final=get(receipt,"final",nothing)
    final isa AbstractDict && get(final,"diagnostics",nothing) isa AbstractDict || error("Missing parent final diagnostics")
    get(final["diagnostics"],"target_states",nothing)==24 || error("Parent did not use24 physical targets")
    receipt
end

function si_arity_valid(action,n;profile=nothing)
    !isnothing(profile) && return profile in ("E40","T05","K4") &&
        (action in ("prepare","D-SCF") ? n==2 : action=="D-GAMMA" ? n==3 : false)
    action in ("prepare","static","D-SCF") ? n==2 :
        action in ("D-SPECTRUM","D-NULL-GAMMA") ? n==3 : false
end

function si_spin_trace_report(full,settings)
    report=SpinTrace.spin_trace_diagnostics(full;seed=settings["seeds"]["symmetry_probe"])
    threshold=settings["thresholds"]["spin_flip_min_signal"]
    signal=report.spin_dependent_action_norm>threshold
    merge(report,(;status=signal ? report.status : "FAIL",spin_dependent_signal_status=signal ? "PASS" : "FAIL",
        spin_dependent_signal_threshold=threshold))
end

function si_run(action,outdir,parent=nothing;profile=nothing,backend=nothing,core_gate=nothing)
    owned=backend=="soc-core"
    isnothing(backend) || owned || error("Unknown explicit backend")
    owned && !isnothing(profile) && error("Core backend cannot impersonate an old profile")
    !owned && !isnothing(core_gate) && error("Core gate requires explicit backend")
    !isnothing(profile) && si_profile(profile)
    work_action=owned ? action=="OPT-B0-SCF" ? "D-SCF" : action=="OPT-B0-GAMMA" ? "D-GAMMA" : "INVALID" : action
    allowed=owned ? ("OPT-B0-SCF","OPT-B0-GAMMA") :isnothing(profile) ? ("prepare","static","D-SCF","D-SPECTRUM","D-NULL-GAMMA") : ("prepare","D-SCF","D-GAMMA")
    action in allowed || error("Unknown Si action")
    area=owned ? ".work/phase9a/endpoints" : isnothing(profile) ? ".work/phase8a" : ".work/phase8b/$profile"
    caseid=isnothing(profile) ? "si-soc-splitting-v1" : "si-soc-sensitivity-v1/$profile"
    outdir=abspath(outdir)
    startswith(outdir,joinpath(PHASE6C_ROOT,area)*"/") || error("Si runs require ignored $area path")
    ispath(outdir) && error("Refusing existing run directory; no prior PASS reused")
    mkpath(outdir)
    result=Dict{String,Any}("schema_version"=>1,"case"=>caseid,"run_id"=>basename(outdir),
        "action"=>action,"base_commit"=>(owned ? SI_CORE_BASE : isnothing(profile) ? SI_BASE : SI_SENSITIVITY_BASE),"execution_status"=>"RUNNING","exit_code"=>1,
        "started_utc"=>string(now(UTC)),"numerical_review_status"=>"REVIEW_REQUIRED")
    owned && merge!(result,Dict("phase"=>"9A","backend"=>"soc-core","preparation_commit"=>SI_CORE_PREPARATION,"runtime_closed"=>false))
    phase6b_write(joinpath(outdir,"result.json"),result)
    runtime=nothing
    try
        result["executed_source_sha256"]=si_sources(profile;backend)
        result["execution_commit"]=strip(read(`git -C $PHASE6C_ROOT rev-parse HEAD`,String))
        if owned
            result["core_gate_sha256"]=si_core_gate(core_gate,result["execution_commit"])
            isempty(strip(read(`git -C $PHASE6C_ROOT status --porcelain`,String))) || error("Core endpoint needs a clean execution tree")
            result["case_sha256"]=filehash(joinpath(PHASE6C_ROOT,"benchmarks/si-soc-splitting-v1/case.json"))
        end
        identity=environment_identity(PHASE6C_ROOT,(DFTK,PseudoPotentialIO));result["environment"]=identity
        phase6b_write(joinpath(outdir,"identity.raw.json"),identity;redact=false)
        identity.status=="PASS" || error("Frozen environment mismatch")
        DFTK.disable_threading();Threads.nthreads()==BLAS.get_num_threads()==1 || error("Single CPU thread required")
        DFTK.mpi_nprocs(DFTK.MPI.COMM_WORLD)==1 || error("Single MPI process required")
        case=si_case(profile);settings=case["settings"]
        if !isnothing(profile)
            result["sensitivity_profile"]=profile
            result["case_sha256"]=filehash(joinpath(PHASE6C_ROOT,si_case_path(profile)))
            result["temperature_ha"]=case["electrons"]["temperature_ha"]
        end
        kind=work_action in ("prepare","D-SCF") ? "scf" : owned ? "core_gamma" : work_action=="D-NULL-GAMMA" ? "null" : "spectrum"
        built=si_context(case,kind;backend);ctx=built.ctx;b=ctx.basis
        b.model.temperature==settings["ensemble"]["tau_ha"] || error("Actual Si context/ensemble temperature mismatch")
        result["input"]=FI.common_data_summary(built.bundle);result["grid"]=si_grid(ctx)
        if owned
            runtime=FI.owned_runtime(ctx;max_rhs=30);ctx=runtime;built=(;ctx,bundle=built.bundle)
            FI.runtime_boundary!(runtime,:driver_entry)
        end
        checkpoint=function(path,value)
            owned && FI.runtime_boundary!(runtime,:before_serialization)
            phase6c_checkpoint(path,value)
            owned && FI.runtime_boundary!(runtime,:after_serialization)
        end
        result["parallelism"]=(;julia=Threads.nthreads(),blas=BLAS.get_num_threads(),fft=DFTK.FFTW.get_num_threads(),mpi=1)
        phase6b_write(joinpath(outdir,"result.json"),result)
        if work_action=="prepare" && !isnothing(profile)
            gamma=si_context(case,"spectrum")
            result["gamma_grid"]=si_grid(gamma.ctx)
            qe_support=si_qe_grid_support(ctx,case)
            inversions=map(enumerate(b.kpoints)) do (i,k)
                targets=findall(q->all(isinteger,k.coordinate+q.coordinate),b.kpoints)
                length(targets)==1 || error("SCF inversion partner is missing or ambiguous")
                j=only(targets);mapping=FI.time_reversal_map(b,k,b.kpoints[j])
                (;source=i,target=j,ng=length(mapping),bijection=true,reversal_map_sha256=FI._source_snapshot(mapping))
            end
            xc=only(filter(t->t isa DFTK.TermXc,b.terms))
            gxc=only(filter(t->t isa DFTK.TermXc,gamma.ctx.basis.terms))
            !isnothing(xc.ρcore) && !isnothing(gxc.ρcore) && norm(xc.ρcore)>0 && xc.ρcore==gxc.ρcore || error("SCF/Gamma core binding differs")
            result["preflight"]=(;status="PASS",scf_k_count=length(b.kpoints),gamma_k_count=1,
                actual_temperature_ha=b.model.temperature,gamma_temperature_ha=gamma.ctx.basis.model.temperature,
                scf_weight_sum=sum(b.kweights),gamma_weight=only(gamma.ctx.basis.kweights),inversion_partners=inversions,
                source_sha256=built.bundle.sha256,gamma_source_sha256=gamma.bundle.sha256,
                core_sha256=FI.integration_density_hash(vec(xc.ρcore)),nlcc_nonzero=true,
                columns_per_atom=length(RelativisticProjectors.projector_labels(built.bundle.channels,1)),
                total_columns=size(first(ctx.fr_blocks).P,2),qe_density_smooth_support=qe_support,
                context_source_binding="Both contexts use independently issued identical frozen Si source bytes",
                scope="Source/context/basis/static FR only; no XC evaluation, eigensolve or density feedback")
            FI.validate_context(gamma.ctx);FI.assert_bound_sources(gamma.bundle)
        elseif work_action=="static"
            progress=report->begin
                result["nlcc"]=report
                phase6b_write(joinpath(outdir,"result.json"),result)
            end
            static=si_static_nlcc(ctx,case;progress);result["nlcc"]=static.report
            result["spin_trace"]=si_spin_trace_report(first(static.full),settings)
            result["spin_trace"].status=="PASS" || error("Spin-dependent action is not identifiable")
            result["time_reversal"]=FI.full_hamiltonian_checks(ctx,static.full,settings)
            result["nlcc"]["status"]=="PASS" || error("INCONCLUSIVE static XC direction")
            result["time_reversal"].status=="PASS" || error("Static TR check failed")
        elseif work_action=="D-SCF"
            n=fill(8/b.model.unit_cell_volume,prod(b.fft_size))
            checkpoint(joinpath(outdir,"initial.bin"),(;n,seed=81001))
            progress=function(event)
                if hasproperty(event,:event) && event.event=="map_input_checkpoint"
                    checkpoint(joinpath(outdir,"current-map-input.bin"),event)
                elseif hasproperty(event,:event) && event.event in ("target_solve","failed_target_solve")
                    if event.event=="target_solve"
                        checkpoint(joinpath(outdir,"latest-k$(event.record.k_index).bin"),event.state)
                        si_append(joinpath(outdir,"solver.jsonl"),event.record)
                    else
                        checkpoint(joinpath(outdir,"failed-solve.bin"),event)
                    end
                else
                    si_append(joinpath(outdir,"events.jsonl"),event)
                end
            end
            callback=function(record,raw)
                owned && FI.runtime_boundary!(runtime,:callback_entry)
                si_append(joinpath(outdir,"maps.jsonl"),record)
                result["completed_maps"]=record["map_index"];result["latest_map"]=record
                if !isnothing(raw)
                    state=(;X=raw.X,all_X=raw.all_X,f=raw.f,eigenvalues=raw.eigenvalues,n_in=raw.n_in,n_out=raw.n_out,
                        diagnostics=raw.diag,mu=raw.ensemble.mu,record)
                    checkpoint(joinpath(outdir,"latest.bin"),state)
                    if record["map_index"]==1 || get(record,"density_candidate",false) || record["map_role"]=="closure" || record["status"]=="FAIL"
                        checkpoint(joinpath(outdir,"map-$(lpad(record["map_index"],3,'0')).bin"),state)
                    end
                    println(stderr,"Si map=$(record["map_index"]) $(record["map_role"]) $(record["status"]) residual=$(get(record,"unmixed_residual_l2",nothing)) E=$(raw.thermal.internal_energy_ha)")
                end
                Sys.maxrss()<8*1024^3 || error("RESOURCE_BLOCKED: measured peak exceeds8GiB")
                phase6b_write(joinpath(outdir,"result.json"),result)
                owned && FI.runtime_boundary!(runtime,:callback_return)
            end
            solved=SOC.soc_scf(ctx,n,settings;seed=81001,callback,progress,case_contract=isnothing(profile) ? nothing : case);raw=solved.raw
            result["final"]=(;map_count=solved.map_count,n_in_sha256=FI.integration_density_hash(raw.n_in),
                n_out_sha256=FI.integration_density_hash(raw.n_out),mu_ha=raw.ensemble.mu,
                eigenvalues_ha=raw.eigenvalues,occupations=raw.f,diagnostics=raw.diag,
                unmixed_residual_l2=last(solved.history)["unmixed_residual_l2"])
            checkpoint(joinpath(outdir,"final.bin"),(;n_in=raw.n_in,n_out=raw.n_out,X=raw.X,f=raw.f,
                eigenvalues=raw.eigenvalues,mu=raw.ensemble.mu,final=result["final"]))
            result["checkpoint_sha256"]=filehash(joinpath(outdir,"final.bin"))
        elseif work_action in ("D-SPECTRUM","D-NULL-GAMMA","D-GAMMA")
            isnothing(parent) && error("Missing successful D-SCF parent")
            parent=abspath(parent);receipt=si_json(joinpath(parent,"result.json"))
            startswith(realpath(parent),realpath(joinpath(PHASE6C_ROOT,area))*"/") || error("Parent must belong to the same Si run area")
            si_validate_parent_receipt(receipt,case,result["executed_source_sha256"],result["execution_commit"];backend,core_gate_sha256=owned ? result["core_gate_sha256"] : nothing)
            get(receipt,"run_id",nothing)==basename(parent) || error("Parent run ID differs from its directory")
            cp=joinpath(parent,"final.bin");filehash(cp)==receipt["checkpoint_sha256"] || error("Parent checkpoint hash mismatch")
            raw=deserialize(cp);FI.integration_density_hash(raw.n_out)==receipt["final"]["n_out_sha256"] || error("Wrong parent final density")
            H=FI.build_full_hamiltonian(ctx,raw.n_out)
            null=work_action=="D-NULL-GAMMA";ham=null ? SpinTrace.spin_trace_hamiltonian.(H.full) : H.full
            result["source_scf_run_id"]=receipt["run_id"];result["density_source_sha256"]=receipt["final"]["n_out_sha256"]
            result["parent_checkpoint_sha256"]=receipt["checkpoint_sha256"]
            result["parent_result_sha256"]=filehash(joinpath(parent,"result.json"))
            if !null
                result["time_reversal"]=work_action=="D-GAMMA" ? si_gamma_time_reversal(ctx,H.full,settings) : FI.full_hamiltonian_checks(ctx,H.full,settings)
                result["time_reversal"].status=="PASS" || error("Final-density full-H time reversal failed")
            else
                result["spin_trace"]=si_spin_trace_report(first(H.full),settings)
                result["spin_trace"].status=="PASS" || error("Spin-dependent action is not identifiable")
            end
            progress=function(event)
                if event.event=="target_solve"
                    si_append(joinpath(outdir,"solver.jsonl"),event.record)
                    checkpoint(joinpath(outdir,"k$(event.record.k_index).bin"),event.state)
                else
                    checkpoint(joinpath(outdir,"failed-solve.bin"),event)
                end
            end
            sol=SOC.solve_soc_targets(ctx,ham,nothing,24,settings;seed=null ? 81301 : 81201,map_index=1,progress)
            points=[(;coordinate_fractional=collect(k.coordinate),eigenvalues_ha=sol.eigenvalues[i],
                residuals_ha=sol.records[i].explicit_residuals_ha,gram_frobenius=sol.records[i].orthogonality_frobenius,
                occupations=si_probe_occupations(sol.eigenvalues[i],raw.mu,case["electrons"]["temperature_ha"])) for (i,k) in enumerate(b.kpoints)]
            if !isnothing(profile) || owned
                points=[merge(point,(;weight_spatial=b.kweights[i])) for (i,point) in enumerate(points)]
            end
            spectrum=(;schema_version=1,case=caseid,kind=null ? "null" : "spectrum",code="DFTK",
                run_id=result["run_id"],execution_status="PASS",process_exit_code=0,
                source_scf_run_id=receipt["run_id"],density_source_sha256=result["density_source_sha256"],
                pseudo_sha256=built.bundle.sha256,physical_operator=null ? "spin_trace_null" : "full_soc",
                n_electrons=8,n_bands=24,occupation_capacity=1,fermi_energy_ha=raw.mu,kpoints=points)
            if !isnothing(profile)
                spectrum=merge(spectrum,(;sensitivity_profile=profile,case_sha256=result["case_sha256"],
                    temperature_ha=b.model.temperature,occupations_use="DIAGNOSTIC_ONLY_NOT_DENSITY_FEEDBACK"))
            end
            if owned
                spectrum=merge(spectrum,(;backend="soc-core",temperature_ha=b.model.temperature,occupations_use="DIAGNOSTIC_ONLY_NOT_DENSITY_FEEDBACK"))
                filehash(cp)==result["parent_checkpoint_sha256"] && filehash(joinpath(parent,"result.json"))==result["parent_result_sha256"] || error("Parent changed during Gamma evaluation")
            end
            # Only the final outer result is authoritative. Do not publish a
            # standalone PASS spectrum before all source/environment/I/O gates.
            result["spectrum"]=spectrum
        end
        Sys.maxrss()<8*1024^3 || error("RESOURCE_BLOCKED: measured peak exceeds8GiB")
        if owned
            FI.runtime_boundary!(runtime,:final)
            result["runtime"]=FI.runtime_summary(runtime)
            counts=result["runtime"].counters
            all(getproperty(counts,k)>0 for k in (:fr_mul_calls,:component_mul_calls,:full_mul_calls)) || error("Owned core dispatch counters were not exercised")
            result["runtime_dispatch_status"]="PASS"
            si_core_gate(core_gate,result["execution_commit"])==result["core_gate_sha256"] || error("Core static gate changed")
        else
            FI.validate_context(ctx);FI.assert_bound_sources(built.bundle)
        end
        si_sources(profile;backend)==result["executed_source_sha256"] || error("Execution source/config changed")
        environment_identity(PHASE6C_ROOT,(DFTK,PseudoPotentialIO)).status=="PASS" || error("Environment changed")
        result["execution_status"]="PASS";result["exit_code"]=0
    catch err
        result["execution_status"]="FAIL";result["exit_code"]=1;result["reason"]=sprint(showerror,err)
        if haskey(result,"nlcc") && result["nlcc"] isa AbstractDict && result["nlcc"]["status"]=="RUNNING"
            result["nlcc"]["status"]="FAIL"
        end
        haskey(result,"spectrum") && (result["spectrum"]=merge(result["spectrum"],(;execution_status="FAIL",process_exit_code=1)))
        showerror(stderr,err,catch_backtrace());println(stderr)
    finally
        if owned && !isnothing(runtime)
            try
                haskey(result,"runtime") || (result["runtime"]=FI.runtime_summary(runtime))
                FI.close_runtime!(runtime)
                result["runtime_after_close"]=FI.runtime_summary(runtime)
                result["runtime_closed"]=result["runtime_after_close"].closed
                result["runtime_closed"] || error("Owned runtime did not close")
            catch err
                result["execution_status"]="FAIL";result["exit_code"]=1;result["cleanup_reason"]=sprint(showerror,err)
                get!(result,"reason","Owned runtime cleanup failed")
                haskey(result,"spectrum") && (result["spectrum"]=merge(result["spectrum"],(;execution_status="FAIL",process_exit_code=1)))
                println(stderr,"Runtime cleanup failed: ",sprint(showerror,err))
            end
        end
    end
    result["finished_utc"]=string(now(UTC));result["peak_rss_bytes"]=Sys.maxrss()
    try
        phase6b_finite(result)
        write(joinpath(outdir,"summary.txt"),"$(result["run_id"]): $(result["execution_status"]) exit=$(result["exit_code"])\n")
        phase6b_write(joinpath(outdir,"result.json"),result)
    catch err
        result=Dict("schema_version"=>1,"case"=>caseid,"action"=>action,"run_id"=>basename(outdir),
            "execution_status"=>"FAIL","exit_code"=>1,"reason"=>"Persistence failure; see stderr")
        println(stderr,"Persistence failure: ",sprint(showerror,err))
        try phase6b_write(joinpath(outdir,"result.json"),result) catch;println(stderr,"Unable to persist failure");end
    end
    result["exit_code"]
end
function si_main(args)
    args==["--help"] && (println("run_si_soc.jl ACTION NEW_RUN_DIR [PARENT_D_SCF_DIR] [--profile E40|T05|K4]; profile actions: prepare|D-SCF|D-GAMMA; legacy: prepare|static|D-SCF|D-SPECTRUM|D-NULL-GAMMA");return 0)
    if "--backend" in args || "--core-gate" in args
        length(args) in (6,7) && args[end-3]=="--backend" && args[end-2]=="soc-core" && args[end-1]=="--core-gate" || return 2
        positional=args[1:end-4]
        length(positional)==(first(positional)=="OPT-B0-SCF" ? 2 : first(positional)=="OPT-B0-GAMMA" ? 3 : 0) || return 2
        return si_run(positional[1],positional[2],length(positional)==3 ? positional[3] : nothing;backend="soc-core",core_gate=args[end])
    end
    profile=nothing;positional=args
    if "--profile" in args
        length(args)>=2 && args[end-1]=="--profile" && count(==("--profile"),args)==1 || return 2
        profile=args[end];positional=args[1:end-2]
    end
    !isempty(positional) && si_arity_valid(positional[1],length(positional);profile) || return 2
    si_run(positional[1],positional[2],length(positional)==3 ? positional[3] : nothing;profile)
end
abspath(PROGRAM_FILE)==(@__FILE__) && exit(si_main(ARGS))
