# Source/grid tests use real, authenticated sources without a physical solve.
# The band-budget fixture is explicitly a zero Hamiltonian, not a Si or Mg spectrum.
struct SyntheticBandBudgetHamiltonian
    ng::Int
end
Base.size(H::SyntheticBandBudgetHamiltonian)=(2H.ng,2H.ng)
Base.size(H::SyntheticBandBudgetHamiltonian,i::Integer)=i<=2 ? 2H.ng : 1
Base.:*(::SyntheticBandBudgetHamiltonian,X::AbstractMatrix)=zeros(ComplexF64,size(X))
FRIntegration.reset_full_counters!(H::SyntheticBandBudgetHamiltonian)=H
FRIntegration.full_operator_stats(::SyntheticBandBudgetHamiltonian)=(;synthetic=true,full_mul_calls=0)

function run_si_interface_tests(root,settings)
    FI=FRIntegration;SC=SOCSCF
    source=JSON3.read(read(joinpath(root,"benchmarks/si-soc-splitting-v1/source.json"),String),Dict{String,Any})
    bundle=FI.load_bound_psp(root;source_spec=source)
    @testset "Registered real Si source binds common, channels and NLCC once" begin
        @test isnothing(FI.assert_bound_sources(bundle))
        @test (bundle.common.element,bundle.common.z_valence,bundle.common.functional)==(:Si,4,"PBE")
        @test bundle.common.has_so && bundle.common.has_nlcc
        @test bundle.xc_identifiers==[:gga_x_pbe,:gga_c_pbe]
        @test bundle.common.nlcc_raw==bundle.parsed.nlcc
        @test bundle.common.r2_core==bundle.common.r.^2 .* bundle.parsed.nlcc
        @test any(!iszero,bundle.common.r2_core)
        @test Set((c.l,c.two_j) for c in bundle.channels.channels)==Set([(0,1),(1,1),(1,3),(2,3),(2,5)])
        @test length(RelativisticProjectors.projector_labels(bundle.channels,1))==36
        @test_throws ArgumentError FI.load_bound_psp(root;mode=:synthetic_scalar_limit,source_spec=source)
        @test_throws ArgumentError FI.load_bound_psp(root;source_spec="unregistered.json")
        for key in ("repository","commit","path","git_blob_sha1","sha256","local_path","source_url")
            bad=deepcopy(source);bad[key]="unregistered"
            @test_throws ArgumentError FI.load_bound_psp(root;source_spec=bad)
        end
        for (key,value) in (("schema_version",true),("schema_version",999),("bytes",291215.0),
                            ("bytes",291216),("xc_identifiers",["gga_x_pbe_sol","gga_c_pbe_sol"]))
            bad=deepcopy(source);bad[key]=value
            @test_throws ArgumentError FI.load_bound_psp(root;source_spec=bad)
        end
        for (key,value) in (("element","Mg"),("z_valence",10),("z_valence",4.0),("functional","PBESOL"),
                            ("has_so",1),("core_correction",false),("l_max",1),("number_of_proj",4),("mesh_size",4))
            bad=deepcopy(source);bad["expected_header"][key]=value
            @test_throws ArgumentError FI.load_bound_psp(root;source_spec=bad)
        end
        bad=deepcopy(source);delete!(bad["expected_header"],"core_correction")
        @test_throws ArgumentError FI.load_bound_psp(root;source_spec=bad)
        mktempdir() do dir
            # Deliberately corrupt bytes rejected before parsing; never a UPF fixture.
            path=joinpath(dir,source["local_path"]);mkpath(dirname(path))
            write(path,"synthetic corrupt source bytes")
            @test_throws ArgumentError FI.load_bound_psp(dir;source_spec=source)
            write(path,zeros(UInt8,source["bytes"]))
            @test_throws ArgumentError FI.load_bound_psp(dir;source_spec=source)
        end
    end
    mg=FI.load_bound_psp(root)
    scalar=FI.load_bound_psp(root;mode=:synthetic_scalar_limit)
    @testset "Historical omitted-source identities remain unchanged" begin
        @test mg.sha256=="19b117bfa920945bffaee91eefbcfbf9fd44e035f3708b965aae59aabf3be256"
        @test (mg.common.element,mg.common.z_valence,mg.common.functional,mg.common.has_nlcc)==(:Mg,10,"PBESOL",false)
        @test scalar.sha256=="686dd9f7d58fe63bdb1e595f0aeecf7d70d2857f06ffb00b8273950d6431e805"
        @test (scalar.common.element,scalar.common.z_valence,scalar.common.relativistic)==(:Si,4,"scalar")
        @test scalar.mode==:synthetic_scalar_limit && scalar.xc_identifiers==[:lda_x,:lda_c_pw]
    end
    # A small static basis tests parameter plumbing, not the production Si case.
    args=(fill(bundle,2),10.0Matrix{Float64}(I,3,3),[[0.,0.,0.],[.25,.25,.25]],[[0.,0.,0.]],[1.])
    kwargs=(;Ecut=1.,xc_identifiers=[:gga_x_pbe,:gga_c_pbe],mode=:real_fr,
        temperature=.001,smearing=DFTK.Smearing.FermiDirac())
    default=FI.build_context(args...;kwargs...)
    explicit_default=FI.build_context(args...;kwargs...,fft_size=nothing)
    explicit=FI.build_context(args...;kwargs...,fft_size=(16,16,16))
    @testset "FFT default and exact explicit grid; two-atom valence count" begin
        @test default.basis.fft_size==explicit_default.basis.fft_size
        @test default.basis.kpoints[1].G_vectors==explicit_default.basis.kpoints[1].G_vectors
        @test default.fr_blocks[1].P==explicit_default.fr_blocks[1].P
        @test explicit.basis.fft_size==(16,16,16)
        @test explicit.basis.model.n_electrons==8
        @test length(explicit.basis.model.atoms)==2
        @test size(explicit.fr_blocks[1].P,2)==72
        @test Set(label.atom for label in explicit.fr_blocks[1].labels)==Set([1,2])
        @test only(filter(t->t isa DFTK.Xc,explicit.basis.model.term_types)).use_nlcc
        @test !isnothing(only(filter(t->t isa DFTK.TermXc,explicit.basis.terms)).ρcore)
        @test_throws ArgumentError FI.build_context(args...;kwargs...,xc_identifiers=[:gga_x_pbe_sol,:gga_c_pbe_sol])
        @test_throws ArgumentError FI.context_valence_rho(explicit,fill(10/1000,16^3))
        for bad in ((0,16,16),(-1,16,16),(true,16,16),(16.,16.,16.),(16,16),(16,16,16,16),"16,16,16",(NaN,16,16))
            @test_throws ArgumentError FI.build_context(args...;kwargs...,fft_size=bad)
        end
        @test FI._checked_context_fft_size([16,16,16])==(16,16,16)
    end
    @testset "Synthetic tail failure stops before a forbidden expansion" begin
        ham=[SyntheticBandBudgetHamiltonian(length(explicit.basis.kpoints[1].G_vectors))]
        localsettings=deepcopy(settings);localsettings["solver"]["allow_band_expansion"]=false
        @test SC.validate_soc_settings(localsettings)
        calls=Ref(0);events=Any[]
        synthetic_solve=(H,initial,prec,ik,imap)->begin
            calls[]+=1
            (;converged=true,n_iter=1,X=copy(initial),λ=zeros(size(initial,2)),n_matvec=0)
        end
        err=try
            SC.solve_with_band_check(explicit,ham,nothing,24,localsettings;seed=80801,map_index=1,
                solve_hook=synthetic_solve,progress=r->push!(events,r))
            nothing
        catch e
            e
        end
        @test err isa SC.EnsembleError
        @test err.status=="INSUFFICIENT_BANDS"
        @test calls[]==1
        bands=[r for r in events if hasproperty(r,:event) && r.event=="band_completeness"]
        @test length(bands)==1
        @test only(bands).attempt.target==24
        @test only(bands).attempt.band.status=="EXPAND" # Failed input is still nonpassing.
        @test only(bands).attempt.band.maximum_top_occupation>1e-10
        localsettings["solver"]["allow_band_expansion"]="false"
        @test_throws ArgumentError SC.solve_with_band_check(explicit,ham,nothing,24,localsettings;
            seed=80801,map_index=1,solve_hook=synthetic_solve)
        @test calls[]==1
        # Omitted flag retains the old, bounded 24→32→40→48 synthetic chain.
        delete!(localsettings["solver"],"allow_band_expansion");empty!(events);calls[]=0
        @test_throws SC.EnsembleError SC.solve_with_band_check(explicit,ham,nothing,24,localsettings;
            seed=80801,map_index=1,solve_hook=synthetic_solve,progress=r->push!(events,r))
        @test calls[]==4
        @test [r.attempt.target for r in events if hasproperty(r,:event) && r.event=="band_completeness"]==[24,32,40,48]
    end
    @testset "Streaming preserves the existing density sum and uses one retained k workspace" begin
        coords=[[0.,0.,0.],[.125,.0625,-.1875],[-.125,-.0625,.1875]]
        # Static Mg avoids adding Si XC trial densities to its separately limited
        # five-density NLCC derivative experiment. This is not Mg SCF.
        streamingctx=FI.build_context([mg],args[2],[[0.,0.,0.]],coords,fill(1/3,3);
            Ecut=1.,xc_identifiers=mg.xc_identifiers,mode=:real_fr,
            temperature=.001,smearing=DFTK.Smearing.FermiDirac(),fft_size=(16,16,16))
        b=streamingctx.basis
        X=[SC.solver_initial(nothing,2length(k.G_vectors),24,80820+i) for (i,k) in enumerate(b.kpoints)]
        f=[vcat(ones(10),zeros(14)) for _ in X]
        savedX=deepcopy(X);savedf=deepcopy(f)
        eager=FI.orbital_density(b,X,f)
        streamed=FI.orbital_density(b,X,f;stream_k=true)
        @test eager.R==streamed.R && eager.n==streamed.n && eager.m==streamed.m
        @test X==savedX && f==savedf
        states=FI._StreamingRealStates(b,X)
        @test isnothing(states.workspace) && states.evaluations==0
        first_workspace=states[1]
        @test states[1]===first_workspace && states.evaluations==1
        @test states[2]===first_workspace && states.evaluations==2
        @test states[3]===first_workspace && states.evaluations==3
        @test states.cached_k==3 && sizeof(states.workspace)==2*16^3*24*sizeof(ComplexF64)
        @test_throws BoundsError states[0]
        @test_throws ArgumentError FI.orbital_density(b,X,f;stream_k="true")
        eager_energy=FI.energy_snapshot(streamingctx,X,f)
        streamed_energy=FI.energy_snapshot(streamingctx,X,f;stream_k=true)
        @test eager_energy.density.n==streamed_energy.density.n
        @test eager_energy.total==streamed_energy.total
        @test eager_energy.terms==streamed_energy.terms
        @test X==savedX && f==savedf
    end
    (;scope="Authenticated source and static basis tests; synthetic zero-Hamiltonian band-budget faults; no physical eigensolve or SCF")
end
