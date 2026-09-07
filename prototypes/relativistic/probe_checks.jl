# Validation orchestration only: small Mg probes and a scalar Si action check.
# Independent angular references are explicitly loaded from tests by the entry.
p6error(a,b)=norm(a-b)/max(norm(a),norm(b),1)
p6hash(x)=bytes2hex(sha256(reinterpret(UInt8,vec(x))))
p6complex(z)=[real(z),imag(z)]

function probe_angular_checks(qvectors)
    records=NamedTuple[]
    for l in 0:3
        a=independent_angular_matrices(l)
        id=Matrix{ComplexF64}(I,2(2l+1),2(2l+1))
        branches=l==0 ? (1,) : (2l-1,2l+1)
        for tj in branches
            u=cg_matrix(l,tj); p=tj==2l+1 ? a.Pi_plus : a.Pi_minus
            j=tj/2; mj=Diagonal(collect(-tj:2:tj)./2)
            push!(records,(;l,two_j=tj,trace_projector=real(tr(p)),
                orthogonality=p6error(u'*u,Matrix{ComplexF64}(I,tj+1,tj+1)),
                projector=p6error(u*u',p),hermiticity=norm(p-p'),idempotence=p6error(p*p,p),
                jz=p6error(a.Jz*u,u*mj),j_squared=p6error(a.J2*u,j*(j+1)*u),
                completeness=p6error(a.Pi_plus+a.Pi_minus,id),
                cross_projector=norm(a.Pi_plus*a.Pi_minus)))
        end
    end
    point_errors=[p6error(complex_solid_harmonic(l,m,q),independent_solid_harmonic(l,m,q))
                  for l in 0:3 for m in -l:l for q in qvectors]
    checks=(:orthogonality,:projector,:hermiticity,:idempotence,:jz,:j_squared,:completeness,:cross_projector)
    max_error=max(maximum(getproperty(r,k) for r in records for k in checks),maximum(point_errors))
    (;records,point_value_max_error=maximum(point_errors),max_error,
      independent_reference="Ladder Lx/Ly/Lz, Pauli/2 and associated Legendre recurrence; no production CG/P")
end

# Diagnostic only: BigFloat elementary spherical Bessel recurrence plus ordinary
# physical-grid trapezoids. It does not call production Hankel/Bessel/quadrature.
# High precision controls cancellation in this reference at very small q.
function probe_trapezoidal_modified(model,index,q)
    c=model.channels[index]; n=c.cutoff_radius_index
    setprecision(BigFloat,256) do
        values=map(1:n) do i
            r=BigFloat(c.r[i]); x=BigFloat(q)*r
            scaled=if iszero(q)
                r^c.l/prod(BigFloat.(1:2:2c.l+1))
            elseif iszero(x)
                c.l==0 ? one(x) : zero(x)
            else
                a=sin(x)/x
                if c.l==0
                    a
                else
                    b=sin(x)/x^2-cos(x)/x
                    for l in 1:c.l-1
                        a,b=b,(2l+1)*b/x-a
                    end
                    b/BigFloat(q)^c.l
                end
            end
            r*BigFloat(c.beta_internal[i])*scaled
        end
        Float64(4big(π)*sum((BigFloat(c.r[i+1])-BigFloat(c.r[i]))*(values[i]+values[i+1])/2 for i in 1:n-1))
    end
end

function probe_reverse_pairs(qvectors)
    pairs=map(qvectors) do q
        ids=findall(r->norm(r+q)<1e-12,qvectors)
        length(ids)==1 || error("Time reversal needs a unique negative-q partner")
        only(ids)
    end
    all(pairs[pairs[i]]==i for i in eachindex(pairs)) || error("Invalid reversal involution")
    pairs
end

function probe_time_reverse(x,pairs)
    y=similar(x)
    for (i,j) in enumerate(pairs)
        y[2i-1,:]=conj.(x[2j,:])
        y[2i,:]=-conj.(x[2j-1,:])
    end
    y
end

function probe_mg(model,settings,outdir)
    g=settings["mg_probe"]
    lattice=reduce(hcat,Float64.(v) for v in g["lattice_bohr"])
    reciprocal=2π*inv(lattice)'
    volume=abs(det(lattice))
    positions=[lattice*Float64.(r) for r in g["positions_fractional"]]
    qs=[[reciprocal*(Float64.(G)+Float64.(k)) for G in g["g_vectors"]] for k in g["kpoints_fractional"]]
    qvectors=vcat(qs...)
    rng=Xoshiro(g["random_seed"])
    x=randn(rng,ComplexF64,2length(qvectors),g["input_columns"]); x./=norm(x)
    op=build_nonlocal_operator(model,qvectors,positions,volume)
    vx=op*x
    independent=independent_kernel(model,qvectors,positions,volume;radial=radial_factor)
    dense=op.P*(op.D*op.P')  # 78x78 probe only; never used for the Si basis.
    kernel_error=p6error(dense,independent)
    action_error=p6error(vx,independent*x)
    y=randn(rng,ComplexF64,size(x,1)); y./=norm(y)
    hermitian_error=p6error(dot(x[:,1],op*y),dot(op*x[:,1],y))
    pairs=probe_reverse_pairs(qvectors)
    tx=probe_time_reverse(x,pairs)
    tr_error=p6error(op*tx,probe_time_reverse(vx,pairs))
    t2_error=norm(probe_time_reverse(tx,pairs)+x)
    shift=lattice*Float64.(g["translation_fractional"])
    translated=build_nonlocal_operator(model,qvectors,[r+shift for r in positions],volume)
    phases=repeat([cis(-dot(q,shift)) for q in qvectors];inner=2)
    p_phase_error=p6error(translated.P,phases.*op.P)
    translation_error=p6error(translated*x,phases.*(op*(conj.(phases).*x)))
    second=lattice*Float64.(g["second_atom_fractional"])
    pair=build_nonlocal_operator(model,qvectors,vcat(positions,[second]),volume)
    secondop=build_nonlocal_operator(model,qvectors,[second],volume)
    atom_sum_error=p6error(pair*x,vx+secondop*x)
    ratio=g["algebraic_volume_ratio"]
    scaled=build_nonlocal_operator(model,qvectors,positions,volume*ratio)
    volume_p_error=p6error(scaled.P,op.P/sqrt(ratio))
    volume_v_error=p6error(scaled*x,vx/ratio)
    f=[1.0,0.6,0.0]
    energy=nonlocal_energy(op,x,f); projection_energy=projected_nonlocal_energy(op,x,f)
    per_k=map(enumerate(qs)) do (ik,q)
        k_op=build_nonlocal_operator(model,q,positions,volume)
        xk=randn(rng,ComplexF64,2length(q),g["input_columns"]); xk./=norm(xk)
        (;ik,k_fractional=g["kpoints_fractional"][ik],nq=length(q),projector_columns=size(k_op.P,2),
          projector_norm=norm(k_op.P),input_norm=norm(xk),action_norm=norm(k_op*xk),
          input_sha256=p6hash(xk),action_sha256=p6hash(k_op*xk))
    end
    selected=[(;row=i,column=j,value=p6complex(op.P[i,j])) for (i,j) in
        [(1,1),(3,1),(5,min(5,size(op.P,2))),(12,size(op.P,2)),(29,min(7,size(op.P,2))),(50,size(op.P,2))]]
    # Raw data may contain P/D and vectors, but never leaves ignored storage.
    rawpath=joinpath(outdir,"mg-probe.bin")
    serialize(rawpath,(;qvectors,positions,volume,P=op.P,D=op.D,labels=op.labels,x,vx,independent))
    checks=(;kernel_error,action_error,hermitian_error,tr_error,t2_error,p_phase_error,
              translation_error,atom_sum_error,volume_p_error,volume_v_error)
    (;geometry=g,volume_bohr3=volume,q_cart_bohr_minus1=qvectors,positions_cart_bohr=positions,
      reversal_pairs=pairs,column_labels=op.labels,projector_shape=collect(size(op.P)),
      per_k,selected_projector_values=selected,checks,max_error=maximum(values(checks)),
      nonlocal_energy_ha=energy,projected_nonlocal_energy_ha=projection_energy,
      energy_error=p6error(energy,projection_energy),
      spin_flip_block_norm=norm(dense[1:2:end,2:2:end]),
      spin_flip_imaginary_norm=norm(imag.(dense[1:2:end,2:2:end])),
      raw_file="mg-probe.bin",raw_sha256=filehash(rawpath),
      note="Real Mg PBEsol radial/D data, unchanged; independent operator probe, not a Mg phase, Si calculation or DFT total energy")
end

function probe_scalar_si(root,settings,outdir)
    path=joinpath(root,settings["scalar_si"]["case_path"])
    case=JSON3.read(read(path,String),Dict{String,Any})
    pseudo_path=joinpath(root,case["pseudo"]["local_path"])
    filehash(pseudo_path)==case["pseudo"]["sha256"] || error("Si UPF checksum mismatch")
    parsed=PseudoPotentialIO.load_psp_file(pseudo_path)
    channels=scalar_degenerate_channels(parsed)
    psp=DFTK.PspUpf(parsed;identifier="Frozen scalar Si",rcut=case["pseudo"]["dftk_rcut_bohr"])
    geometry=case["geometry"]
    lattice=reduce(hcat,Float64.(v) for v in geometry["lattice_vectors_bohr"])
    positions=[Float64.(r) for r in geometry["positions_fractional"]]
    model=DFTK.model_DFT(lattice,[DFTK.ElementPsp(:Si,psp) for _ in positions],positions;
        functionals=Symbol.(case["xc"]["dftk_identifiers"]),n_electrons=8,
        spin_polarization=:none,temperature=0.0,symmetries=false)
    coords=[Float64.(k["coordinate_fractional"]) for k in case["kpoints"]]
    weights=[Float64(k["weight_spatial"]) for k in case["kpoints"]]
    basis=DFTK.PlaneWaveBasis(model;Ecut=case["cutoffs"]["dftk_ecut_ha"],kgrid=DFTK.ExplicitKpoints(coords,weights))
    length(basis.kpoints)==8 || error("Frozen Si eight-point grid changed")
    term=only(filter(t->t isa DFTK.TermAtomicNonlocal,basis.terms))
    rng=Xoshiro(settings["scalar_si"]["random_seed"])
    rows=NamedTuple[]; raw=Any[]
    for (ik,kpt) in enumerate(basis.kpoints)
        q=collect(DFTK.Gplusk_vectors_cart(basis,kpt))
        op=build_nonlocal_operator(channels,q,[lattice*r for r in positions],model.unit_cell_volume)
        x=randn(rng,ComplexF64,2length(q),settings["scalar_si"]["input_columns"]); x./=norm(x)
        reference=zeros(ComplexF64,size(x))
        for n in axes(x,2), spin in 1:2
            output=@view reference[spin:2:end,n]
            input=@view x[spin:2:end,n]
            DFTK.apply!((;fourier=output),term.ops[ik],(;fourier=input))
        end
        actual=op*x
        push!(rows,(;ik,coordinate_fractional=collect(kpt.coordinate),weight=basis.kweights[ik],
            ng=length(q),projector_columns=size(op.P,2),scalar_columns=size(term.ops[ik].P,2),
            normalized_action_error=p6error(actual,reference),input_norm=norm(x),
            reference_norm=norm(reference),actual_norm=norm(actual),
            input_sha256=p6hash(x),reference_sha256=p6hash(reference),actual_sha256=p6hash(actual)))
        push!(raw,(;ik,x,reference,actual))
    end
    rawpath=joinpath(outdir,"si-scalar-limit.bin"); serialize(rawpath,raw)
    (;scope="SYNTHETIC complete spin-degenerate branches from REAL scalar Si; no real Si FR input, SOC benchmark or SCF",
      case_sha256=filehash(path),pseudo_sha256=filehash(pseudo_path),
      channels=channel_summary(channels),rows,max_error=maximum(r.normalized_action_error for r in rows),
      fft_grid=collect(basis.fft_size),volume_bohr3=model.unit_cell_volume,
      raw_file="si-scalar-limit.bin",raw_sha256=filehash(rawpath),dense_pw_matrix_constructed=false)
end

function run_probe_checks!(result,outdir,settings,root)
    tol=settings["tolerances"]
    result["angular_validation_status"]="RUNNING"
    result["angular"]=probe_angular_checks([[0.0,0.0,0.0],[0.3,-0.7,0.2],[-0.8,0.1,-0.4],[1e-8,2e-8,-3e-8]])
    result["angular"].max_error<=tol["angular"] || error("Angular reference mismatch")
    result["angular_validation_status"]="PASS"
    lock=TOML.parsefile(joinpath(root,"config/sources.lock"))
    path=joinpath(root,lock["pseudopotentials"]["local_path"])
    if !isfile(path)
        result["real_fr_runtime_status"]="BLOCKED"
        error("Locked Mg input missing; mathematical tests cannot substitute for real FR execution")
    end
    digest=filehash(path)
    digest==lock["pseudopotentials"]["file_sha256"] || error("Mg input SHA-256 mismatch")
    result["input"]=(;sha256=digest,source=lock["pseudopotentials"],case_sha256=filehash(joinpath(root,settings["scalar_si"]["case_path"])))
    result["metadata_status"]="RUNNING"
    parsed=parse_input(path)
    parsed.status=="PASS" || error(join(parsed.reasons,"; "))
    metadata=validate_metadata(metadata_from_upf(parsed.parsed))
    result["metadata"]=metadata
    metadata.status=="PASS" || error(join(metadata.reasons,"; "))
    channels=fr_channels(parsed.parsed)
    result["channels"]=channel_summary(channels)
    result["channel_provenance"]=channels.provenance
    result["d_raw_parsed"]=[[p6complex(x) for x in row] for row in eachrow(channels.D_raw_parsed)]
    result["d_internal"]=[[p6complex(x) for x in row] for row in eachrow(channels.D)]
    result["metadata_status"]="PASS"
    guard=check_construction(()->DFTK.PspUpf(parsed.parsed;identifier="Phase6A unchanged Mg");
        guard_file=joinpath(dirname(pathof(DFTK)),"pseudo","PspUpf.jl"))
    result["original_dftk_constructor"]=guard
    guard.status=="EXPECTED_SOC_REJECTION" || error("Frozen DFTK SOC guard changed")
    result["radial_validation_status"]="RUNNING"
    radial=[begin
        f=radial_factor(channels,i,q); h=radial_modified(channels,i,q)
        reference=probe_trapezoidal_modified(channels,i,q)
        (;channel_position=i,q_bohr_minus1=q,F=f,F_over_q_l=h,
          trapezoidal_F_over_q_l=reference,quadrature_difference=h-reference,
          normalized_quadrature_difference=p6error(h,reference))
    end for i in eachindex(channels.channels) for q in settings["mg_probe"]["radial_q_bohr_minus1"]]
    result["radial"]=(;values=radial,
        max_quadrature_sensitivity=maximum(r.normalized_quadrature_difference for r in radial),
        reference="256-bit elementary Bessel recurrence + physical-grid trapezoids; diagnostic difference, not an error bound",
        scope="All real Mg channels finite; Gaussian accuracy assessed separately by synthetic tests")
    result["radial_validation_status"]="PASS"
    result["real_fr_runtime_status"]="RUNNING"
    result["independent_operator_validation_status"]="RUNNING"
    mg=probe_mg(channels,settings,outdir); result["mg"]=mg
    phase6a_write(joinpath(outdir,"result.json"),result)
    mg.max_error<=tol["operator"] && mg.energy_error<=tol["nonlocal_energy"] || error("Real Mg operator check failed")
    result["independent_operator_validation_status"]="PASS"
    result["real_fr_runtime_status"]="PASS"
    result["scalar_limit_validation_status"]="RUNNING"
    si=probe_scalar_si(root,settings,outdir); result["scalar_si"]=si
    si.max_error<=tol["operator"] || error("Real scalar Si synthetic-degeneracy check failed")
    result["scalar_limit_validation_status"]="PASS"
end
