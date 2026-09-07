#!/usr/bin/env julia
# Fixed historical densities only. No orbitals, Hamiltonian, T/NL, or electronic solve.
module CommonEnergyEvaluation
using DFTK, PseudoPotentialIO, LinearAlgebra, SHA, JSON3, TOML, Serialization
include("extract_soc_density.jl")
const SD = SOCDensityExtraction
include("upf_validation.jl")
include("upf_runtime.jl")
include("../prototypes/relativistic/RelativisticProjectors.jl")
module CommonData
using DFTK, PseudoPotentialIO, SHA, TOML, JSON3, LinearAlgebra
using ..RelativisticProjectors
# Reuse the frozen adapter without including the full-H/energy/SCF modules.
include("../prototypes/fr_integration/common_data.jl")
end

const ROOT = SD.ROOT
const IDS = [:gga_x_pbe_sol, :gga_c_pbe_sol]
array_hash(x::Array) = bytes2hex(sha256(reinterpret(UInt8,vec(x))))
finite_number(x) = x isa Real && !(x isa Bool) && isfinite(x)

function read_coefficient_csv(path, names)
    text=read(path,String);occursin('\r',text) && error("Coefficient CSV must retain LF encoding")
    lines=split(chomp(text),'\n')
    expected=vcat(["m1","m2","m3"],reduce(vcat,[[name*"_real",name*"_imag"] for name in names]))
    split(first(lines),',')==expected || error("Unexpected coefficient columns")
    millers=NTuple{3,Int}[];data=Dict(name=>ComplexF64[] for name in names)
    for line in lines[2:end]
        row=split(line,',');length(row)==length(expected) || error("Coefficient row shape mismatch")
        ints=parse.(Int,row[1:3]);string.(ints)==row[1:3] || error("Noncanonical integer Miller token")
        push!(millers,Tuple(ints))
        for (i,name) in enumerate(names)
            z=complex(parse(Float64,row[2i+2]),parse(Float64,row[2i+3]))
            isfinite(z) || error("Nonfinite Fourier data")
            push!(data[name],z)
        end
    end
    !isempty(millers) && length(unique(millers))==length(millers) || error("Empty/duplicate Miller table")
    count(==((0,0,0)),millers)==1 || error("Exactly one source G=0 is required")
    (;millers,data)
end

function density_diagnostics(n,volume,thresholds;expected_electrons=10)
    n isa Vector{Float64} && !isempty(n) && all(isfinite,n) || error("Finite flat Float64 density required")
    finite_number(volume) && volume>0 || error("Positive cell volume required")
    dvol=volume/length(n);ne=dvol*sum(n)
    bound=64eps(Float64)*max(1,maximum(abs,n)) # frozen energy_valence_rho rule
    good=abs(ne-expected_electrons)<=thresholds["electron_count_abs"] && minimum(n)>=-bound
    (;status=good ? "PASS" : "UNSUPPORTED_REPRESENTATION",sha256=array_hash(n),
      electron_count=ne,electron_error=ne-expected_electrons,minimum=minimum(n),maximum=maximum(n),
      negative_count=count(<(0),n),negative_roundoff_bound=bound,
      l2=sqrt(dvol)*norm(n),normalization_applied=false,clipping_applied=false)
end

"""Evaluate the unchanged saved finite Fourier series on its original nodes.

The zero-initialized workspace is not a statement about unsaved physical modes.
Integer support is retained separately; aliases and non-native representatives fail.
"""
function reconstruct_density(millers,coefficients,grid,volume,thresholds;points)
    length(millers)==length(coefficients)>0 || error("Miller/coefficient lengths differ")
    all(z->z isa ComplexF64 && isfinite(z),coefficients) || error("ComplexF64 coefficients required")
    all(m->length(m)==3 && all(x->x isa Int,m),millers) || error("Integer Miller triples required")
    length(unique(millers))==length(millers) || error("Duplicate source Miller vector")
    native=[Tuple(g) for g in vec(DFTK.G_vectors(grid))]
    index=Dict(g=>i for (i,g) in enumerate(native))
    all(haskey(index,m) for m in millers) || error("Out-of-grid or aliased/non-native Miller representative")
    count(==((0,0,0)),millers)==1 || error("Missing/duplicate G=0")
    work=zeros(ComplexF64,grid.fft_size)
    for (m,z) in zip(millers,coefficients);work[index[m]]=sqrt(volume)*z;end
    complex_n=vec(DFTK.ifft(grid,work)) # retain imaginary output before considering real()
    all(isfinite,complex_n) || error("Nonfinite complex reconstruction")
    imaginary_max=maximum(abs,imag.(complex_n))
    imaginary_l2=norm(imag.(complex_n))/max(norm(complex_n),floatmin(Float64))
    imaginary_max<=thresholds["density_imaginary_abs"] || error("Reconstruction has substantive imaginary density; no real-part projection allowed")
    n=real.(complex_n)
    check=density_diagnostics(n,volume,thresholds)
    back=vec(DFTK.fft(grid,reshape(complex_n,grid.fft_size)))/sqrt(volume)
    target=vec(work)/sqrt(volume)
    roundtrip=norm(back-target)/max(norm(target),floatmin(Float64))
    # This path is an independent pointwise forward sum, not another FFT call.
    directional=map(points) do point
        m=Tuple(Int.(point));haskey(index,m) || error("Directional test outside native grid")
        ref=SD.direct_coefficient(n,grid.fft_size,m)
        expected=target[index[m]]
        (;miller=collect(m),source_present=m in millers,expected=[real(expected),imag(expected)],
          direct=[real(ref),imag(ref)],absolute_error=abs(ref-expected))
    end
    good=check.status=="PASS" && roundtrip<=thresholds["fourier_roundtrip_relative_l2"] &&
         maximum(r.absolute_error for r in directional)<=thresholds["fourier_directional_abs"]
    report=(;status=good ? "PASS" : "UNSUPPORTED_REPRESENTATION",density=check,
        source_support_count=length(millers),native_workspace_count=length(native),
        missing_workspace_bins=length(native)-length(millers),source_support_preserved=true,
        unsaved_physical_modes="NOT_ESTABLISHED_ZERO",imaginary_max,imaginary_relative_l2=imaginary_l2,
        fourier_roundtrip_relative_l2=roundtrip,directional_checks=directional,
        representation="Saved finite Fourier series on original zero-origin nodes, nbar -> sqrt(Omega)*nbar -> complex IFFT",
        original_QE_realspace_array="NOT_INDEPENDENTLY_EXTRACTED",
        density_hash_scope="Reconstructed Float64 array; not the original checkpoint byte identity")
    (;n,complex_n,native_millers=native,native_nbar=target,source_millers=copy(millers),report)
end

function reconstruction_difference(original,reconstruction,thresholds)
    original isa Vector{Float64} && length(original)==length(reconstruction) || error("Original/reconstruction shape differs")
    relative=norm(reconstruction-original)/max(norm(original),floatmin(Float64))
    absolute=maximum(abs,reconstruction-original)
    (;status=relative<=thresholds["density_reconstruction_relative_l2"] &&
        absolute<=thresholds["density_reconstruction_max_abs"] ? "PASS" : "FAIL",
      relative_l2=relative,max_abs=absolute,original_sha256=array_hash(original),
      reconstructed_sha256=array_hash(reconstruction),hash_equality_required=false)
end

function static_basis(bundle,physics)
    CommonData.assert_bound_sources(bundle)
    c=bundle.common
    (c.element,c.z_valence,c.functional,c.has_so,c.has_nlcc)==(:Mg,10,"PBESOL",true,false) || error("Fixed Mg common source mismatch")
    bundle.xc_identifiers==IDS || error("PBEsol common source required")
    lattice=hcat((Float64.(v) for v in physics["lattice_vectors_bohr"])...)
    lattice==10Matrix{Float64}(I,3,3) && physics["position_fractional"]==[.17,.23,.31] || error("Frozen Mg geometry changed")
    physics["fft_size"]==[40,40,40] && physics["ecut_ha"]==15 && physics["tau_ha"]==.001 &&
        physics["expected_electrons"]==10 && Symbol.(physics["functionals"])==IDS &&
        physics["nlcc"]===false && physics["atoms"]==1 && physics["element"]=="Mg" && physics["charge_spin_components"]==1 || error("Frozen static settings changed")
    terms=[DFTK.AtomicLocal(),DFTK.Xc(IDS),DFTK.Ewald(),DFTK.PspCorrection()]
    model=DFTK.Model(lattice,[DFTK.ElementPsp(:Mg,c)],[Float64.(physics["position_fractional"])];
        model_name="Static common-term audit of historical density",terms,n_electrons=10,
        spin_polarization=:none,temperature=.001,smearing=DFTK.Smearing.FermiDirac(),symmetries=false)
    basis=DFTK.PlaneWaveBasis(model;Ecut=15.,fft_size=(40,40,40),
        kgrid=DFTK.ExplicitKpoints([Float64.(k) for k in physics["kpoints"]],Float64.(physics["kweights"])))
    [collect(k.coordinate) for k in basis.kpoints]==physics["kpoints"] && basis.kweights==physics["kweights"] || error("Static k-point contract changed")
    localterm=only(filter(t->t isa DFTK.TermAtomicLocal,basis.terms))
    xcterm=only(filter(t->t isa DFTK.TermXc,basis.terms))
    isnothing(xcterm.ρcore) && isnothing(xcterm.τcore) && xcterm.potential_threshold==0 && xcterm.scaling_factor==1 || error("Frozen no-NLCC unscaled XC path changed")
    DFTK.identifier.(xcterm.functionals)==IDS && all(f->DFTK.family(f)==:gga,xcterm.functionals) || error("Full PBEsol GGA required")
    ewald=only(filter(t->t isa DFTK.TermEwald,basis.terms));pc=only(filter(t->t isa DFTK.TermPspCorrection,basis.terms))
    constants=(;ewald_ha=ewald.energy,psp_correction_ha=pc.energy,
        alpha_from_common_native=DFTK.eval_psp_energy_correction(Float64,c),
        psp_local_fourier_G0=DFTK.eval_psp_local_fourier(c,0.0),
        n_electrons_from_atoms_actual=DFTK.n_electrons_from_atoms(model.atoms),model_ne=model.n_electrons,
        volume_bohr3=model.unit_cell_volume,natoms=length(model.atoms),ewald_eta=ewald.η,
        source_sha256=bundle.sha256,nlcc=false,
        psp_correction_scope="One native per-cell constant; not added to density response or historical totals")
    (;basis,localterm,xcterm,constants,bundle)
end

function xc_backend_report(term,density)
    rho=DFTK._matify(density.ρ_real);sigma=DFTK._matify(density.σ_real)
    rho isa Matrix{Float64} && sigma isa Matrix{Float64} || error("This audit requires the frozen CPU Float64 XC dispatch")
    rows=map(term.functionals) do fun
        fun isa DFTK.DispatchFunctional && fun.inner isa DFTK.LibxcFunctional{:gga} || error("Unexpected XC backend object")
        # xc.jl:525 forwards both absent tau/lapl arguments; preserve the actual
        # five-argument signature rather than probing an unused abbreviated call.
        dispatch=which(DFTK.potential_terms,Tuple{typeof(fun),typeof(rho),typeof(sigma),Nothing,Nothing})
        inner=which(DFTK.potential_terms,Tuple{typeof(fun.inner),typeof(rho),typeof(sigma)})
        native=DFTK.Libxc.Functional(DFTK.identifier(fun);n_spin=1)
        info=DFTK.Libxc.xc_func_get_info(native.pointer_)
        nparams=DFTK.Libxc.xc_func_info_get_n_ext_params(info)
        params=[(;name=unsafe_string(DFTK.Libxc.xc_func_info_get_ext_params_name(info,i)),
            default=DFTK.Libxc.xc_func_info_get_ext_params_default_value(info,i),
            actual_default_object=DFTK.Libxc.xc_func_get_ext_params_value(native.pointer_,i)) for i in 0:nparams-1]
        (;identifier=string(DFTK.identifier(fun)),functional_type=string(typeof(fun)),inner_type=string(typeof(fun.inner)),
          backend="Libxc Float64 CPU",density_type=string(typeof(rho)),sigma_type=string(typeof(sigma)),
          dispatch_file=string(dispatch.file),dispatch_line=dispatch.line,inner_file=string(inner.file),inner_line=inner.line,
          native_number=DFTK.Libxc.xc_functional_get_number(string(DFTK.identifier(fun))),
          native_name=native.name,native_family=string(native.family),parameters=params,
          density_threshold=native.density_threshold,sigma_threshold=native.sigma_threshold,
          tau_threshold=native.tau_threshold,zeta_threshold=native.zeta_threshold,
          below_density_threshold=count(x->x<native.density_threshold,rho),
          below_sigma_threshold=count(x->x<native.sigma_threshold,sigma),
          parameter_scope="Fresh default Libxc object with the same identifier/n_spin as the selected frozen method; no setter or parameter override")
    end
    libpath=string(DFTK.Libxc.libxc)
    (;functionals=rows,libxc_wrapper_version=string(pkgversion(DFTK.Libxc)),
      libxc_wrapper_uuid=string(Base.PkgId(DFTK.Libxc).uuid),
      libxc_runtime_version=unsafe_string(DFTK.Libxc.xc_version_string()),
      libxc_library_path=libpath,libxc_library_sha256=SD.filehash(libpath),
      dftfunctionals_version=string(pkgversion(DFTK.DftFunctionals)),
      dftfunctionals_uuid=string(Base.PkgId(DFTK.DftFunctionals).uuid),
      functional_dispatch_source_sha256=SD.filehash(joinpath(dirname(pathof(DFTK)),"DispatchFunctional.jl")),
      xc_source_sha256=SD.filehash(joinpath(dirname(pathof(DFTK)),"terms/xc.jl")),
      potential_threshold=term.potential_threshold,full_gga_potential=true,
      gradient_convention="Full native cubic FFT support; iG times orthonormal rho coefficients, then real(ifft); Nyquist real-part convention unchanged",
      divergence_convention="Native divergence_real: FFT each vector component, multiply iG, sum, real(ifft)",
      generic_dftfunctionals_evaluation_used=false)
end

function evaluate_density(static,n,source,thresholds)
    basis=static.basis;check=density_diagnostics(n,basis.model.unit_cell_volume,thresholds)
    check.status=="PASS" || return (;summary=(;status=check.status,source,density=check,xc_call_count=0),arrays=nothing)
    original_hash=array_hash(n);rho=reshape(n,basis.fft_size...,1)
    # One full native GGA call per prescribed density. No orbital argument is used.
    xc=DFTK.xc_potential_real(static.xcterm,basis,nothing,nothing;ρ=rho)
    isnothing(xc.Vτ) || error("Unexpected meta-GGA potential")
    localenergy=DFTK.ene_ops(static.localterm,basis,nothing,nothing;ρ=rho).E
    vxc=vec(xc.potential);localpotential=vec(static.localterm.potential_values)
    all(isfinite,vxc) && all(isfinite,localpotential) && isfinite(xc.E) && isfinite(localenergy) || error("Nonfinite common-term evaluation")
    # This second density container computes only gradients for retained diagnostics;
    # it does not evaluate an XC functional or call a solver.
    density=DFTK.LibxcDensities(basis,1,rho,nothing)
    backend=xc_backend_report(static.xcterm,density)
    arrays=(;n=copy(n),vxc=copy(vxc),local_potential=copy(localpotential),
        gradient=copy(density.∇ρ_real),sigma=copy(density.σ_real))
    local_nbar=vec(DFTK.fft(basis,reshape(localpotential,basis.fft_size)))/sqrt(basis.model.unit_cell_volume)
    array_hash(n)==original_hash || error("Static evaluation mutated the density")
    summary=(;status="PASS",source,density=check,
        atomic_local_ha=localenergy,xc_ha=xc.E,integral_n_vxc_ha=basis.dvol*dot(n,vxc),
        local_integral_ha=basis.dvol*dot(n,localpotential),
        local_integral_minus_native_energy_ha=basis.dvol*dot(n,localpotential)-localenergy,
        vxc_mean_ha=sum(vxc)/length(vxc),vxc_l2_ha_bohr32=sqrt(basis.dvol)*norm(vxc),
        local_mean_ha=sum(localpotential)/length(localpotential),local_l2_ha_bohr32=sqrt(basis.dvol)*norm(localpotential),
        local_fourier_G0=[real(local_nbar[1]),imag(local_nbar[1])],
        gradient_l2=sqrt(basis.dvol)*norm(density.∇ρ_real),gradient_max_abs=maximum(abs,density.∇ρ_real),
        sigma_minimum=minimum(density.σ_real),sigma_maximum=maximum(density.σ_real),
        array_sha256=Dict(string(k)=>array_hash(a) for (k,a) in pairs(arrays)),
        xc_call_count=1,backend,energy_scope="Only AtomicLocal, Xc, Ewald and PspCorrection; no T/NL/total-energy claim")
    (;summary,arrays,local_nbar)
end

function compare_common_to_history(evaluation,constants,endpoint,thresholds)
    h=endpoint["diagnostics"];terms=h["energy_terms_ha"]
    fields=(("atomic_local_ha",evaluation.atomic_local_ha,terms["AtomicLocal"]),
        ("xc_ha",evaluation.xc_ha,terms["Xc"]),
        ("integral_n_vxc_ha",evaluation.integral_n_vxc_ha,h["energy_checks"]["integral_n_vxc_ha"]),
        ("psp_correction_ha",constants.psp_correction_ha,terms["PspCorrection"]),
        ("ewald_ha",constants.ewald_ha,terms["Ewald"]))
    rows=[(;field,actual,historical,signed_difference_ha=actual-historical,
        threshold_ha=field in ("psp_correction_ha","ewald_ha") ? thresholds["same_source_constants_abs_ha"] : thresholds["same_source_common_abs_ha"])
        for (field,actual,historical) in fields]
    (;status=all(abs(r.signed_difference_ha)<=r.threshold_ha for r in rows) ? "PASS" : "FAIL",rows)
end

function density_response(reference,other,basis,thresholds)
    a=reference.arrays;q=other.arrays
    a.local_potential==q.local_potential || error("Different local potentials in same-implementation density response")
    delta=a.n-q.n;volume=basis.model.unit_cell_volume
    dnbar=vec(DFTK.fft(basis,reshape(delta,basis.fft_size)))/sqrt(volume)
    real_local=basis.dvol*dot(delta,a.local_potential)
    reciprocal_local=volume*real(dot(dnbar,reference.local_nbar))
    first_order=basis.dvol*dot(q.vxc,delta)
    xc_difference=reference.summary.xc_ha-other.summary.xc_ha
    (;status=abs(real_local-reciprocal_local)<=thresholds["local_parseval_abs_ha"] ? "PASS" : "FAIL",
        delta_electrons=basis.dvol*sum(delta),xc_density_response_ha=xc_difference,
        ixc_density_response_ha=reference.summary.integral_n_vxc_ha-other.summary.integral_n_vxc_ha,
        xc_first_order_at_Q_ha=first_order,xc_curvature_remainder_ha=xc_difference-first_order,
        local_density_response_real_ha=real_local,local_density_response_fourier_ha=reciprocal_local,
        local_real_minus_fourier_ha=real_local-reciprocal_local,
        source_support="All 64000 native bins including G=0 and Nyquist; no mean subtraction",
        potential_provenance="Same DFTK native local potential, not a QE potential",
        public_replay="RUNNER_REPORTED; complete new potential/gradient arrays remain local")
end

function evaluate_request!(result,request,outdir)
    request["schema_version"]==1 || error("Unsupported request schema")
    plan_path=SD.resolve_path(request["plan_path"])
    SD.checked_file(plan_path,request["plan_sha256"]);plan=SD.read_json(plan_path)
    string(VERSION)==plan["julia_version"]=="1.12.7" || error("Frozen Julia mismatch")
    tracked=Dict(plan_path=>request["plan_sha256"],(@__FILE__)=>SD.filehash(@__FILE__))
    result["plan_sha256"]=request["plan_sha256"];result["executed_script_sha256"]=tracked[@__FILE__]
    identity=SD.environment_identity(ROOT,(DFTK,PseudoPotentialIO));result["environment"]=identity
    identity.status=="PASS" || error("Frozen loaded environment mismatch")
    for (path,hash) in plan["source_sha256"]
        actual=SD.resolve_path(path);tracked[actual]=SD.checked_file(actual,hash)
        filesize(actual)==plan["source_bytes"][path] || error("Source byte length mismatch")
    end
    DFTK.disable_threading()
    Threads.nthreads()==BLAS.get_num_threads()==DFTK.mpi_nprocs(DFTK.MPI.COMM_WORLD)==1 || error("Serial execution required")
    source_plan=SD.read_json(SD.resolve_path(plan["historical_binding_plan"]))
    tables=Dict{String,Any}()
    for (key,names) in (("dftk",["A_out","B_out"]),("qe",["QE"]))
        transfer=request["transfers"][key];path=SD.resolve_path(transfer["path"])
        public_path=transfer["public_path"]
        public_path==(key=="dftk" ? "results/mg-soc-density-hartree/dftk-nout.csv.gz" : "results/mg-soc-density-hartree/qe-rho.csv.gz") || error("Wrong public coefficient source")
        haskey(plan["source_sha256"],public_path) || error("Unbound source pack")
        tracked[path]=SD.checked_file(path,transfer["sha256"])
        # Decompression/transfer equality is verified by the outer stdlib recorder;
        # both original gzip and passed plain-byte hashes are recorded here.
        tables[key]=read_coefficient_csv(path,names)
    end
    result["coefficient_transfers"]=request["transfers"]
    result["source_binding_status"]="PASS"
    physics=plan["physical"];thresholds=plan["thresholds"]
    volume=physics["volume_bohr3"];grid=DFTK.FFTGrid(Tuple(Int.(physics["fft_size"])),volume,DFTK.CPU())
    reps=Dict{String,Any}();originals=Dict{String,Vector{Float64}}();endpoints=Dict{String,Any}()
    result["reconstruction"]=Dict{String,Any}();result["original_sources"]=Dict{String,Any}()
    for (name,key,column) in (("A","dftk","A_out"),("B","dftk","B_out"),("Q","qe","QE"))
        table=tables[key]
        rep=reconstruct_density(table.millers,table.data[column],grid,volume,thresholds;
            points=source_plan["direct_fourier_miller_points"])
        reps[name]=rep;result["reconstruction"][name]=rep.report
        rep.report.status=="PASS" || error("Unsupported $name finite density representation; no modification made")
    end
    for name in ("A","B")
        endpoint=SD.read_json(SD.resolve_path(plan["sources"][name]["endpoint"]["path"]));endpoints[name]=endpoint
        path=SD.resolve_path(get(get(request,"source_paths",Dict()),name,plan["sources"][name]["checkpoint"]["path"]))
        try
            binding=SD.validate_historical_binding(source_plan,name,path);merge!(tracked,binding.tracked)
            state=SD.trusted_checkpoint(path,binding.source["checkpoint"]["sha256"])
            bound=SD.bound_densities(state,endpoint,grid.fft_size,volume/prod(grid.fft_size),source_plan["thresholds"])
            bound.closure.status=="PASS" || error("Historical state binding failed")
            originals[name]=bound.n_out # No use of X/f/eigenvalues; n_in only frozen binding.
            comparison=reconstruction_difference(bound.n_out,reps[name].n,thresholds)
            result["original_sources"][name]=(;status="PASS",source_run_id=binding.source["run_id"],
                checkpoint_sha256=binding.source["checkpoint"]["sha256"],n_out_sha256=array_hash(bound.n_out),
                same_source_reconstruction=comparison)
            comparison.status=="PASS" || error("$name original/represented density mismatch")
        catch err
            if err isa SD.MissingSource
                result["original_sources"][name]=(;status="BLOCKED_MISSING_SOURCE",reason=sprint(showerror,err))
            else
                rethrow()
            end
        end
    end
    result["density_representation_status"]="PASS"
    pseudo=SD.resolve_path(plan["pseudo_path"]);tracked[pseudo]=SD.checked_file(pseudo,plan["pseudo_sha256"])
    bundle=CommonData.load_bound_psp(ROOT;mode=:real_fr)
    bundle.sha256==plan["pseudo_sha256"] || error("Wrong common UPF source")
    static=static_basis(bundle,physics);result["constants"]=static.constants
    result["basis"]=(;fft_size=collect(static.basis.fft_size),n_electrons=static.basis.model.n_electrons,
        volume_bohr3=static.basis.model.unit_cell_volume,term_types=string.(typeof.(static.basis.terms)),
        kpoints=[collect(k.coordinate) for k in static.basis.kpoints],kweights=static.basis.kweights,
        ecut_ha=static.basis.Ecut,temperature_ha=static.basis.model.temperature)
    evaluations=Dict{String,Any}();result["evaluations"]=Dict{String,Any}();result["same_source"]=Dict{String,Any}()
    count_xc=0
    jobs=[(name*"_original_n_out",originals[name]) for name in ("A","B") if haskey(originals,name)]
    append!(jobs,[("Q_rep",reps["Q"].n),("A_reconstructed",reps["A"].n),("B_reconstructed",reps["B"].n)])
    for (name,n) in jobs
        count_xc<plan["max_xc_calls"] || error("Prescribed XC evaluation budget exhausted")
        evaluated=evaluate_density(static,n,name,thresholds);count_xc+=evaluated.summary.xc_call_count
        result["xc_calls_completed"]=count_xc
        result["evaluations"][name]=evaluated.summary;evaluations[name]=evaluated
        # Retain each completed fixed-input call before subsequent checks. A
        # recorder failure must not require repeating an already computed XC.
        partial=(;evaluations=Dict(key=>value.arrays for (key,value) in evaluations),
            reconstructed_complex=Dict(key=>rep.complex_n for (key,rep) in reps))
        serialize(joinpath(outdir,"arrays.bin.tmp"),partial)
        mv(joinpath(outdir,"arrays.bin.tmp"),joinpath(outdir,"arrays.bin");force=true)
        SD.write_json(joinpath(outdir,"progress.json"),result)
        evaluated.summary.status=="PASS" || error("Unsupported input to $name evaluation")
        if name!="Q_rep"
            label=first(split(name,'_'));check=compare_common_to_history(evaluated.summary,static.constants,endpoints[label],thresholds)
            result["same_source"][name]=check
            check.status=="PASS" || error("Same-source common-term restoration failed for $name; affected cross-code response stopped")
        end
    end
    result["same_source_common_terms_status"]=length(originals)==2 ? "PASS" : "BLOCKED_MISSING_SOURCE"
    result["responses"]=Dict{String,Any}()
    for name in ("A","B")
        haskey(originals,name) || continue
        response=density_response(evaluations[name*"_original_n_out"],evaluations["Q_rep"],static.basis,thresholds)
        result["responses"][name]=response
        response.status=="PASS" || error("Local real/Fourier response identity failed")
    end
    # Full new fields remain local. They are plain arrays, never a context/model.
    raw=(;evaluations=Dict(name=>e.arrays for (name,e) in evaluations),
        reconstructed_complex=Dict(name=>rep.complex_n for (name,rep) in reps),
        native_millers=reps["A"].native_millers,local_nbar=evaluations["Q_rep"].local_nbar)
    serialize(joinpath(outdir,"arrays.bin"),raw)
    result["local_arrays"]=(;path="arrays.bin",sha256=SD.filehash(joinpath(outdir,"arrays.bin")),
        public_replay="NOT_PUBLIC; new field integrals are runner measurements")
    CommonData.assert_bound_sources(bundle)
    for (path,hash) in tracked;SD.checked_file(path,hash);end
    result["source_unchanged_status"]="PASS"
    SD.environment_identity(ROOT,(DFTK,PseudoPotentialIO))==identity || error("Environment changed during evaluation")
    result["environment_recheck_status"]="PASS"
    result["execution_status"]=length(originals)==2 ? "PASS" : "BLOCKED_MISSING_SOURCE"
    nothing
end

function main(args)
    args==["--help"] && (println("Usage: evaluate_common_energy_terms.jl REQUEST.json NEW_IGNORED_DIR\nFive fixed-density common evaluations at most; no electronic solve.");return 0)
    length(args)==2 || (println(stderr,"Expected REQUEST.json NEW_IGNORED_DIR");return 2)
    outdir=abspath(args[2]);ispath(outdir) && (println(stderr,"Existing output refused");return 2)
    startswith(outdir,joinpath(ROOT,".work")*"/") || (println(stderr,"Use a new ignored .work directory");return 2)
    result=Dict{String,Any}("schema_version"=>1,"phase"=>"7D","execution_status"=>"RUNNING",
        "data_status"=>"NEW_POSTPROCESSING_OF_HISTORICAL_STATES","new_scf_status"=>"NOT_RUN",
        "new_eigensolve_status"=>"NOT_RUN","new_qe_numerical_status"=>"NOT_RUN","xc_calls_completed"=>0)
    code=1
    try
        mkpath(outdir);request=SD.read_json(args[1]);result["run_id"]=request["run_id"]
        evaluate_request!(result,request,outdir);code=result["execution_status"]=="PASS" ? 0 : 1
    catch err
        result["execution_status"]=err isa SD.MissingSource ? "BLOCKED_MISSING_SOURCE" : "FAIL"
        result["failure_reason"]=sprint(showerror,err);showerror(stderr,err,catch_backtrace());println(stderr)
    end
    result["exit_code"]=code
    try
        # The final verdict follows complete field persistence and summary writing.
        write(joinpath(outdir,"summary.txt"),"$(get(result,"run_id",basename(outdir))): $(result["execution_status"]), exit=$code\n")
        SD.write_json(joinpath(outdir,"metadata.json"),result)
    catch err
        code=1;println(stderr,"Persistence failure: ",sprint(showerror,err))
        try SD.write_json(joinpath(outdir,"metadata.json"),Dict("schema_version"=>1,"phase"=>"7D", "execution_status"=>"FAIL","exit_code"=>1,"failure_reason"=>"Persistence failure")) catch
            println(stderr,"Unable to persist safe failure record")
        end
    end
    code
end

end
abspath(PROGRAM_FILE)==(@__FILE__) && exit(CommonEnergyEvaluation.main(ARGS))
