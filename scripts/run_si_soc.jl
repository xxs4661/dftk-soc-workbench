#!/usr/bin/env julia
# One prescribed Si case; reuse the frozen ensemble, map controller and target solver.
include("run_soc_scf.jl")
include("../prototypes/crystal_soc/SpinTrace.jl")
const SI_CASE_DIR=joinpath(PHASE6C_ROOT,"benchmarks/si-soc-splitting-v1")
const SI_BASE="9342a5ea21a76acd0d74d228d4a2081394f702d0"
si_json(path)=JSON3.read(read(path,String),Dict{String,Any})
si_case()=si_json(joinpath(SI_CASE_DIR,"case.json"))
function si_sources()
    files=collect(keys(phase6c_sources()))
    append!(files,["prototypes/crystal_soc/SpinTrace.jl","scripts/run_si_soc.jl"])
    append!(files,["benchmarks/si-soc-splitting-v1/"*f for f in ("case.json","source.json","plan.json","qe-scf.in","qe-spectrum.in")])
    Dict(f=>filehash(joinpath(PHASE6C_ROOT,f)) for f in unique(files))
end
function si_context(case,kind)
    spec=si_json(joinpath(SI_CASE_DIR,"source.json"))
    bundle=FI.load_bound_psp(PHASE6C_ROOT;source_spec=spec)
    g=case["geometry"];lat=reduce(hcat,Float64.(v) for v in g["lattice_vectors_bohr"])
    pos=[Float64.(p) for p in g["positions_fractional"]]
    if kind=="scf"
        k=[Float64.(p["coordinate_fractional"]) for p in case["kpoints"]]
        w=Float64[p["weight_spatial"] for p in case["kpoints"]]
    elseif kind=="spectrum"
        k=[Float64.(p) for p in case["probe_kpoints"]];w=Float64.(case["probe_weights"])
    elseif kind=="null"
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
function si_validate_parent_receipt(receipt,case,sources,execution_commit)
    receipt isa AbstractDict || error("Parent must be a result object")
    get(receipt,"schema_version",nothing) === 1 && get(receipt,"case",nothing)=="si-soc-splitting-v1" &&
        get(receipt,"base_commit",nothing)==SI_BASE || error("Wrong parent schema/case/base")
    get(receipt,"action",nothing)=="D-SCF" && get(receipt,"execution_status",nothing)=="PASS" &&
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

function si_arity_valid(action,n)
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

function si_run(action,outdir,parent=nothing)
    allowed=("prepare","static","D-SCF","D-SPECTRUM","D-NULL-GAMMA")
    action in allowed || error("Unknown Si action")
    outdir=abspath(outdir)
    startswith(outdir,joinpath(PHASE6C_ROOT,".work/phase8a")*"/") || error("Si runs require ignored phase8a path")
    ispath(outdir) && error("Refusing existing run directory; no prior PASS reused")
    mkpath(outdir)
    result=Dict{String,Any}("schema_version"=>1,"case"=>"si-soc-splitting-v1","run_id"=>basename(outdir),
        "action"=>action,"base_commit"=>SI_BASE,"execution_status"=>"RUNNING","exit_code"=>1,
        "started_utc"=>string(now(UTC)),"numerical_review_status"=>"REVIEW_REQUIRED")
    phase6b_write(joinpath(outdir,"result.json"),result)
    try
        result["executed_source_sha256"]=si_sources()
        result["execution_commit"]=strip(read(`git -C $PHASE6C_ROOT rev-parse HEAD`,String))
        identity=environment_identity(PHASE6C_ROOT,(DFTK,PseudoPotentialIO));result["environment"]=identity
        phase6b_write(joinpath(outdir,"identity.raw.json"),identity;redact=false)
        identity.status=="PASS" || error("Frozen environment mismatch")
        DFTK.disable_threading();Threads.nthreads()==BLAS.get_num_threads()==1 || error("Single CPU thread required")
        DFTK.mpi_nprocs(DFTK.MPI.COMM_WORLD)==1 || error("Single MPI process required")
        case=si_case();settings=case["settings"]
        kind=action in ("prepare","D-SCF") ? "scf" : action=="D-NULL-GAMMA" ? "null" : "spectrum"
        built=si_context(case,kind);ctx=built.ctx;b=ctx.basis
        result["input"]=FI.common_data_summary(built.bundle);result["grid"]=si_grid(ctx)
        result["parallelism"]=(;julia=Threads.nthreads(),blas=BLAS.get_num_threads(),fft=DFTK.FFTW.get_num_threads(),mpi=1)
        phase6b_write(joinpath(outdir,"result.json"),result)
        if action=="static"
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
        elseif action=="D-SCF"
            n=fill(8/b.model.unit_cell_volume,prod(b.fft_size))
            phase6c_checkpoint(joinpath(outdir,"initial.bin"),(;n,seed=81001))
            progress=function(event)
                if hasproperty(event,:event) && event.event=="map_input_checkpoint"
                    phase6c_checkpoint(joinpath(outdir,"current-map-input.bin"),event)
                elseif hasproperty(event,:event) && event.event in ("target_solve","failed_target_solve")
                    if event.event=="target_solve"
                        phase6c_checkpoint(joinpath(outdir,"latest-k$(event.record.k_index).bin"),event.state)
                        si_append(joinpath(outdir,"solver.jsonl"),event.record)
                    else
                        phase6c_checkpoint(joinpath(outdir,"failed-solve.bin"),event)
                    end
                else
                    si_append(joinpath(outdir,"events.jsonl"),event)
                end
            end
            callback=function(record,raw)
                si_append(joinpath(outdir,"maps.jsonl"),record)
                result["completed_maps"]=record["map_index"];result["latest_map"]=record
                if !isnothing(raw)
                    state=(;X=raw.X,all_X=raw.all_X,f=raw.f,eigenvalues=raw.eigenvalues,n_in=raw.n_in,n_out=raw.n_out,
                        diagnostics=raw.diag,mu=raw.ensemble.mu,record)
                    phase6c_checkpoint(joinpath(outdir,"latest.bin"),state)
                    if record["map_index"]==1 || get(record,"density_candidate",false) || record["map_role"]=="closure" || record["status"]=="FAIL"
                        phase6c_checkpoint(joinpath(outdir,"map-$(lpad(record["map_index"],3,'0')).bin"),state)
                    end
                    println(stderr,"Si map=$(record["map_index"]) $(record["map_role"]) $(record["status"]) residual=$(get(record,"unmixed_residual_l2",nothing)) E=$(raw.thermal.internal_energy_ha)")
                end
                Sys.maxrss()<8*1024^3 || error("RESOURCE_BLOCKED: measured peak exceeds8GiB")
                phase6b_write(joinpath(outdir,"result.json"),result)
            end
            solved=SOC.soc_scf(ctx,n,settings;seed=81001,callback,progress);raw=solved.raw
            result["final"]=(;map_count=solved.map_count,n_in_sha256=FI.integration_density_hash(raw.n_in),
                n_out_sha256=FI.integration_density_hash(raw.n_out),mu_ha=raw.ensemble.mu,
                eigenvalues_ha=raw.eigenvalues,occupations=raw.f,diagnostics=raw.diag,
                unmixed_residual_l2=last(solved.history)["unmixed_residual_l2"])
            phase6c_checkpoint(joinpath(outdir,"final.bin"),(;n_in=raw.n_in,n_out=raw.n_out,X=raw.X,f=raw.f,
                eigenvalues=raw.eigenvalues,mu=raw.ensemble.mu,final=result["final"]))
            result["checkpoint_sha256"]=filehash(joinpath(outdir,"final.bin"))
        elseif action in ("D-SPECTRUM","D-NULL-GAMMA")
            isnothing(parent) && error("Missing successful D-SCF parent")
            parent=abspath(parent);receipt=si_json(joinpath(parent,"result.json"))
            startswith(realpath(parent),realpath(joinpath(PHASE6C_ROOT,".work/phase8a"))*"/") || error("Parent must belong to the new Si run area")
            si_validate_parent_receipt(receipt,case,result["executed_source_sha256"],result["execution_commit"])
            get(receipt,"run_id",nothing)==basename(parent) || error("Parent run ID differs from its directory")
            cp=joinpath(parent,"final.bin");filehash(cp)==receipt["checkpoint_sha256"] || error("Parent checkpoint hash mismatch")
            raw=deserialize(cp);FI.integration_density_hash(raw.n_out)==receipt["final"]["n_out_sha256"] || error("Wrong parent final density")
            H=FI.build_full_hamiltonian(ctx,raw.n_out)
            null=action=="D-NULL-GAMMA";ham=null ? SpinTrace.spin_trace_hamiltonian.(H.full) : H.full
            result["source_scf_run_id"]=receipt["run_id"];result["density_source_sha256"]=receipt["final"]["n_out_sha256"]
            result["parent_checkpoint_sha256"]=receipt["checkpoint_sha256"]
            result["parent_result_sha256"]=filehash(joinpath(parent,"result.json"))
            if !null
                result["time_reversal"]=FI.full_hamiltonian_checks(ctx,H.full,settings)
                result["time_reversal"].status=="PASS" || error("Final-density full-H time reversal failed")
            else
                result["spin_trace"]=si_spin_trace_report(first(H.full),settings)
                result["spin_trace"].status=="PASS" || error("Spin-dependent action is not identifiable")
            end
            progress=function(event)
                if event.event=="target_solve"
                    si_append(joinpath(outdir,"solver.jsonl"),event.record)
                    phase6c_checkpoint(joinpath(outdir,"k$(event.record.k_index).bin"),event.state)
                else
                    phase6c_checkpoint(joinpath(outdir,"failed-solve.bin"),event)
                end
            end
            sol=SOC.solve_soc_targets(ctx,ham,nothing,24,settings;seed=null ? 81301 : 81201,map_index=1,progress)
            points=[(;coordinate_fractional=collect(k.coordinate),eigenvalues_ha=sol.eigenvalues[i],
                residuals_ha=sol.records[i].explicit_residuals_ha,gram_frobenius=sol.records[i].orthogonality_frobenius,
                occupations=[SOC.fermi_logistic((e-raw.mu)/.001) for e in sol.eigenvalues[i]]) for (i,k) in enumerate(b.kpoints)]
            spectrum=(;schema_version=1,case="si-soc-splitting-v1",kind=null ? "null" : "spectrum",code="DFTK",
                run_id=result["run_id"],execution_status="PASS",process_exit_code=0,
                source_scf_run_id=receipt["run_id"],density_source_sha256=result["density_source_sha256"],
                pseudo_sha256=built.bundle.sha256,physical_operator=null ? "spin_trace_null" : "full_soc",
                n_electrons=8,n_bands=24,occupation_capacity=1,fermi_energy_ha=raw.mu,kpoints=points)
            # Only the final outer result is authoritative. Do not publish a
            # standalone PASS spectrum before all source/environment/I/O gates.
            result["spectrum"]=spectrum
        end
        Sys.maxrss()<8*1024^3 || error("RESOURCE_BLOCKED: measured peak exceeds8GiB")
        FI.validate_context(ctx);FI.assert_bound_sources(built.bundle)
        si_sources()==result["executed_source_sha256"] || error("Execution source/config changed")
        environment_identity(PHASE6C_ROOT,(DFTK,PseudoPotentialIO)).status=="PASS" || error("Environment changed")
        result["execution_status"]="PASS";result["exit_code"]=0
    catch err
        result["execution_status"]="FAIL";result["exit_code"]=1;result["reason"]=sprint(showerror,err)
        if haskey(result,"nlcc") && result["nlcc"] isa AbstractDict && result["nlcc"]["status"]=="RUNNING"
            result["nlcc"]["status"]="FAIL"
        end
        haskey(result,"spectrum") && (result["spectrum"]=merge(result["spectrum"],(;execution_status="FAIL",process_exit_code=1)))
        showerror(stderr,err,catch_backtrace());println(stderr)
    end
    result["finished_utc"]=string(now(UTC));result["peak_rss_bytes"]=Sys.maxrss()
    try
        phase6b_finite(result)
        write(joinpath(outdir,"summary.txt"),"$(result["run_id"]): $(result["execution_status"]) exit=$(result["exit_code"])\n")
        phase6b_write(joinpath(outdir,"result.json"),result)
    catch err
        result=Dict("schema_version"=>1,"case"=>"si-soc-splitting-v1","action"=>action,"run_id"=>basename(outdir),
            "execution_status"=>"FAIL","exit_code"=>1,"reason"=>"Persistence failure; see stderr")
        println(stderr,"Persistence failure: ",sprint(showerror,err))
        try phase6b_write(joinpath(outdir,"result.json"),result) catch;println(stderr,"Unable to persist failure");end
    end
    result["exit_code"]
end
function si_main(args)
    args==["--help"] && (println("run_si_soc.jl prepare|static|D-SCF|D-SPECTRUM|D-NULL-GAMMA NEW_RUN_DIR [PARENT_D_SCF_DIR]");return 0)
    !isempty(args) && si_arity_valid(args[1],length(args)) || return 2
    si_run(args[1],args[2],length(args)==3 ? args[3] : nothing)
end
abspath(PROGRAM_FILE)==(@__FILE__) && exit(si_main(ARGS))
