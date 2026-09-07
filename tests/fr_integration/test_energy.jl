# Explicit general-complex operator/energy fixtures. They are not physical
# eigenstates, equilibrium occupations, or additional SCF calculations.
function integration_energy_fixture(ctx,seed)
    ne=Int(ctx.basis.model.n_electrons)
    nstates=max(16,ne+4)
    rng=MersenneTwister(seed)
    X=[Matrix(qr(randn(rng,ComplexF64,2length(DFTK.G_vectors(ctx.basis,k)),nstates)).Q)[:,1:nstates]
       for k in ctx.basis.kpoints]
    f=[vcat(ones(ne),zeros(nstates-ne)) for _ in X]
    (;X,f,seed,scope="General complex orthogonal energy/operator fixture; diagnostic capacity-one occupations")
end

function run_energy_tests(ctx_mg,ctx_si,native_si_basis,settings)
    FI=FRIntegration
    tol=settings["thresholds"]["energy_abs_ha"]
    mgfixture=integration_energy_fixture(ctx_mg,settings["seeds"]["mg_energy_fixture"])
    sifixture=integration_energy_fixture(ctx_si,settings["seeds"]["si_energy_fixture"])
    X,f=mgfixture.X,mgfixture.f
    savedX=deepcopy(X); savedf=deepcopy(f)
    mg=FI.energy_snapshot(ctx_mg,X,f)
    si=FI.compare_native_scalar_energy(ctx_si,sifixture.X,sifixture.f,native_si_basis)

    @testset "Current spinor density and six common plus one full FR energy" begin
        @test ctx_mg.basis.model.n_electrons==sum(a.psp.z_valence for a in ctx_mg.basis.model.atoms)
        @test ctx_mg.basis.model.n_electrons!=8 # The actual Mg header supplies ten, not the old Si helper.
        @test mg.report.native_nonlocal_terms==0
        @test Set(keys(mg.terms))==FI.FR_ENERGY_NAMES
        @test FI.assert_energy_consistency(mg)
        @test abs(mg.report.electron_count_real-ctx_mg.basis.model.n_electrons)<=1e-8
        @test abs(mg.report.electron_count_reciprocal-ctx_mg.basis.model.n_electrons)<=1e-8
        @test mg.report.component_norm_min>0 && mg.report.component_norm_max<0.9
        @test X==savedX && f==savedf
        @test all(norm(x'*x-Matrix{ComplexF64}(I,size(x,2),size(x,2)))<=1e-9 for x in X)
        factors=FI.energy_factors(ctx_mg.basis,X,f)
        for ik in eachindex(X)
            n=size(X[ik],2)
            @test factors.chi[ik][:,1:n]==X[ik][1:2:end,:]
            @test factors.chi[ik][:,n+1:end]==X[ik][2:2:end,:]
            @test factors.fchi[ik]==vcat(f[ik],f[ik])
        end
        nl=mg.nonlocal_decomposition
        @test abs(nl.full_ha-nl.diagonal_ha-nl.cross_ha)<=1e-11
        @test nl.projected_normalized_error<=1e-11
        @test abs(nl.cross_ha)>1e-12 # Resolved real-FR interference in a nonphysical complex trial state.
        # A legacy scalar nonlocal energy record cannot accompany the FR Hamiltonian.
        legacy=copy(mg.terms);legacy["AtomicNonlocal"]=pop!(legacy,"AtomicNonlocalFR")
        @test_throws ArgumentError FI.assert_energy_consistency(merge(mg,(;terms=legacy)))
        wrongterms=copy(mg.terms);wrongterms["AtomicNonlocalFR"]=nl.diagonal_ha
        wrong=merge(mg,(;terms=wrongterms,total=mg.total-nl.cross_ha))
        @test_throws ArgumentError FI.assert_energy_consistency(wrong)
        absent=copy(mg.terms);absent["AtomicNonlocalFR"]=0
        @test_throws ArgumentError FI.assert_energy_consistency(merge(mg,(;terms=absent,total=mg.total-nl.full_ha)))
        duplicate=copy(mg.terms);duplicate["AtomicNonlocalFR"]=2nl.full_ha
        @test_throws ArgumentError FI.assert_energy_consistency(merge(mg,(;terms=duplicate,total=mg.total+nl.full_ha)))
        @test_throws ArgumentError FI.assert_energy_consistency(merge(mg,(;total=mg.total+0.01)))
        fitted=copy(mg.terms);fitted["FittedReferenceConstant"]=0.01
        @test_throws ArgumentError FI.assert_energy_consistency(merge(mg,(;terms=fitted,total=mg.total+0.01)))
        for name in ("Ewald","PspCorrection")
            @test abs(mg.terms[name])>1e-8
            twice=copy(mg.terms);twice[name]*=2
            @test_throws ArgumentError FI.assert_energy_consistency(merge(mg,(;terms=twice,total=mg.total+mg.terms[name])))
        end
    end

    @testset "Reject stale densities, stale bands and malformed orbital data" begin
        altered=FI.rotate_orbital_pair(X,1,1,Int(ctx_mg.basis.model.n_electrons)+1,0.13)
        nnew=FI.orbital_density(ctx_mg.basis,altered,f).n
        @test norm(nnew-mg.density.n)>1e-8
        @test_throws ArgumentError FI.energy_snapshot(ctx_mg,altered,f;expected_n=mg.density.n)
        @test_throws ArgumentError FI.energy_snapshot(ctx_mg,X,f;expected_n=[NaN])
        invalid=deepcopy(X);invalid[1][1]=NaN
        @test_throws ArgumentError FI.energy_snapshot(ctx_mg,invalid,f)
        invalid=deepcopy(X);invalid[1]=invalid[1][1:end-1,:]
        @test_throws DimensionMismatch FI.energy_snapshot(ctx_mg,invalid,f)
        invalidf=deepcopy(f);invalidf[1][1]=2
        @test_throws ArgumentError FI.energy_snapshot(ctx_mg,X,invalidf)
        invalidf=deepcopy(f);invalidf[1][1]=0
        @test_throws ArgumentError FI.energy_snapshot(ctx_mg,X,invalidf)
        invalidf=deepcopy(f);pop!(invalidf[1])
        @test_throws DimensionMismatch FI.energy_snapshot(ctx_mg,X,invalidf)
        normed_components=deepcopy(X)
        for x in normed_components,s in 1:2,n in axes(x,2)
            view(x,s:2:size(x,1),n)./=norm(view(x,s:2:size(x,1),n))
        end
        @test_throws ArgumentError FI.energy_snapshot(ctx_mg,normed_components,f)
        nconstant=fill(ctx_mg.basis.model.n_electrons/ctx_mg.basis.model.unit_cell_volume,length(mg.density.n))
        stale=FI.build_full_hamiltonian(ctx_mg,nconstant)
        oldband=FI.occupied_expectation(stale.full,X,ctx_mg.basis.kweights,f)
        @test abs(oldband-mg.report.band_expectation_ha)>1e-8
        report=merge(mg.report,(;band_expectation_ha=oldband))
        @test_throws ArgumentError FI.assert_energy_consistency(merge(mg,(;report)))
    end

    @testset "Full charge-only GGA potential and actual NLCC ownership" begin
        basis=ctx_mg.basis
        xc=only(filter(t->t isa DFTK.TermXc,basis.terms))
        @test isnothing(xc.ρcore) && !mg.report.nlcc_present
        factors=FI.energy_factors(basis,X,f)
        complete=DFTK.xc_potential_real(xc,basis,factors.chi,factors.fchi;ρ=mg.rho)
        @test FI.integration_error(vec(complete.potential),mg.vxc)<=1e-10
        @test abs(complete.E-mg.terms["Xc"])<=tol
        derivatives=DFTK.LibxcDensities(basis,maximum(DFTK.max_required_derivative,xc.functionals),mg.rho,nothing)
        partial=DFTK.potential_terms(xc.functionals,derivatives)
        @test norm(vec(partial.Vρ)-mg.vxc)>1e-8 # GGA divergence is an actual, resolved contribution.
        sibasis=ctx_si.basis
        sixc=only(filter(t->t isa DFTK.TermXc,sibasis.terms))
        @test !isnothing(sixc.ρcore) && si.snapshot.report.nlcc_present
        core=copy(sixc.ρcore)
        @test sibasis.dvol*sum(core)>1e-8
        @test_throws ArgumentError FI.energy_valence_rho(sibasis,si.snapshot.density.n+vec(core))
        sf=FI.energy_factors(sibasis,sifixture.X,sifixture.f)
        duplicate=DFTK.xc_potential_real(sixc,sibasis,sf.chi,sf.fchi;ρ=si.snapshot.rho+core)
        @test abs(duplicate.E-si.snapshot.terms["Xc"])>1e-8
        @test sixc.ρcore==core
    end

    @testset "Native full scalar Si energy recovered term by term" begin
        @test abs(si.total_difference_ha)<=tol
        @test si.max_term_difference_ha<=tol
        @test all(abs(v)<=tol for v in values(si.term_differences_ha))
        @test FI.assert_energy_consistency(si.snapshot)
    end

    cfg=settings["spin_rotation"]
    axis=Float64.(cfg["axis"]);axis/=norm(axis)
    pauli=axis[1]*ComplexF64[0 1;1 0]+axis[2]*ComplexF64[0 -im;im 0]+axis[3]*ComplexF64[1 0;0 -1]
    U=cos(cfg["angle_rad"]/2)*Matrix{ComplexF64}(I,2,2)-im*sin(cfg["angle_rad"]/2)*pauli
    spin=FI.spin_rotation_diagnostic(ctx_mg,X,f,U)
    @testset "Fixed spin-only rotation separates charge and FR energy" begin
        @test spin.common_invariance_status=="PASS"
        @test spin.nonlocal_noninvariance_status=="RESOLVED"
        @test spin.status=="PASS"
        @test abs(spin.nonlocal_change_ha)>1e-12
        @test spin.total_minus_nonlocal_change_error_ha<=tol
        @test_throws ArgumentError FI.rotate_global_spin(X,2U)
        @test X==savedX
    end
    (;scope="General complex energy fixtures, actual Mg and real-scalar-Si synthetic limit; no eigensolve/SCF",
      mg_report=mg.report,mg_nonlocal=mg.nonlocal_decomposition,
      si_term_differences_ha=si.term_differences_ha,si_total_difference_ha=si.total_difference_ha,
      spin_rotation=spin)
end
