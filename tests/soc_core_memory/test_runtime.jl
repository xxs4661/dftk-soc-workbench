# Static authenticated old-Mg adapter fixtures plus synthetic mutation faults.
# No SCF, eigensolve, occupation solve, Si run or historical result rewrite.
using Test
include("../../scripts/run_fr_integration.jl")

function runtime_test_context(root)
    bundle=FI.load_bound_psp(root)
    FI.build_context([bundle],10.0Matrix{Float64}(I,3,3),[[0.,0.,0.]],
        [[0.,0.,0.]],[1.];Ecut=1.0,xc_identifiers=bundle.xc_identifiers,
        mode=:real_fr,fft_size=(16,16,16))
end

function run_owned_runtime_tests(root)
    original_contexts=length(FI._FR_CONTEXT_CERTIFICATES)
    original_sources=length(FI._BOUND_PSP_SOURCES)
    ctx=runtime_test_context(root);bundle=only(ctx.bundles)
    token=bundle._token;original_p=only(ctx.fr_blocks).P
    n=fill(ctx.basis.model.n_electrons/ctx.basis.model.unit_cell_volume,prod(ctx.basis.fft_size))
    old=FI.build_full_hamiltonian(ctx,n)
    rng=MersenneTwister(910031)
    probes=Dict(k=>randn(rng,ComplexF64,size(only(old.full),1),k) for k in (1,24,30))
    expectations=Dict(k=>(;fr=only(ctx.fr_blocks)*x,common=only(old.full).common*x,full=only(old.full)*x)
        for (k,x) in probes)
    X=[Matrix(DFTK.ortho_qr(randn(rng,ComplexF64,size(only(old.full),1),24)))]
    f=[vcat(ones(Int(ctx.basis.model.n_electrons)),zeros(24-Int(ctx.basis.model.n_electrons)))]
    old_density=FI.orbital_density(ctx.basis,X,f;stream_k=true)
    old_energy=FI.energy_snapshot(ctx,X,f;stream_k=true)
    rt=FI.owned_runtime(ctx;max_rhs=30)
    try
        @testset "Strict issuance, one original P set, no new global authority" begin
            @test FI.runtime_enabled(rt) && !FI.runtime_enabled(ctx)
            @test !haskey(FI._FR_CONTEXT_CERTIFICATES,ctx)
            @test !haskey(FI._BOUND_PSP_SOURCES,token)
            @test length(FI._FR_CONTEXT_CERTIFICATES)==original_contexts
            @test length(FI._BOUND_PSP_SOURCES)==original_sources
            @test rt.basis===ctx.basis && rt.fr_blocks===ctx.fr_blocks
            @test only(FI.runtime_fr_blocks(rt)).P===original_p
            @test FI.validate_context(rt)
            forged=FI.FRHamiltonianContext(ctx.basis,ctx.bundles,ctx.fr_blocks,ctx.mode,ctx.xc_identifiers)
            @test_throws ArgumentError FI.owned_runtime(forged)
            @test_throws ArgumentError FI.validate_context(ctx)
            @test_throws ArgumentError FI.owned_runtime(ctx)
            @test FI.runtime_summary(rt).owned_source_entries==1
        end
        H=FI.build_full_hamiltonian(rt,n);h=only(H.full)
        @testset "Core FR/common/full action and active RHS transitions" begin
            @test_throws ArgumentError FI.FullHamiltonianBlock(rt,1,only(H.common.blocks),only(rt.fr_blocks))
            for k in (30,1,24,1,30)
                x=probes[k]
                @test FI.integration_error(only(FI.runtime_fr_blocks(rt))*x,expectations[k].fr)<=1e-12
                @test FI.integration_error(h.common*x,expectations[k].common)<=1e-12
                @test FI.integration_error(h*x,expectations[k].full)<=1e-12
                y=fill(ComplexF64(NaN),size(x));mul!(y,h,x,1,0)
                @test FI.integration_error(y,expectations[k].full)<=1e-12
            end
            @test FI.runtime_boundary!(rt,:synthetic_solver_return;ham=H.full)
            @test FI.full_operator_stats(h).backend=="soc-core"
            @test FI.runtime_summary(rt).counters.full_mul_calls>0
            @test FI.runtime_summary(rt).counters.component_mul_calls>0
            @test FI.runtime_summary(rt).counters.fr_mul_calls>0
        end
        @testset "Local contracts retain failure-atomic output" begin
            x=probes[1];y=fill(3.0+2im,size(x));saved=copy(y)
            @test_throws ArgumentError mul!(x,h,x)
            @test_throws ArgumentError mul!(y,h,x,NaN,0)
            @test y==saved
            for backing in (rt._workspace.common_action,rt._workspace.fr_action,
                            rt._workspace.component.candidate,rt._workspace.nonlocal.candidate)
                alias=@view backing[1:size(x,1),1:1];fill!(alias,3+2im);before=copy(alias)
                @test_throws ArgumentError mul!(alias,h,x,0,2)
                @test alias==before
            end
            @test_throws ArgumentError mul!(y,h,x,1,Inf)
            @test y==saved
            bad=copy(x);bad[1]=NaN
            @test_throws ArgumentError mul!(y,h,bad)
            @test y==saved
            @test_throws DimensionMismatch mul!(zeros(ComplexF64,size(x,1),31),h,zeros(ComplexF64,size(x,1),31))
            y .= NaN
            @test_throws ArgumentError mul!(y,h,x,1,1)
            @test all(isnan,real.(y))
            # Finite scales which overflow the *completed* result must not
            # publish a partial common action to the caller's output.
            y .= complex(floatmax(Float64));saved=copy(y)
            @test_throws ArgumentError mul!(y,h,x,0,2)
            @test y==saved
            rt._busy=true
            @test_throws ArgumentError h*x
            rt._busy=false
            @test FI.runtime_boundary!(rt,:after_rejected_reentry;ham=H.full)
        end
        @testset "External aliases are checked at declared boundaries" begin
            p=only(ctx.fr_blocks).P;before=p[1];p[1]+=0.1
            @test_throws ArgumentError FI.runtime_boundary!(rt,:caller_projector_mutation)
            p[1]=before
            d=only(ctx.fr_blocks).D;before=d[1];d[1]+=0.1
            @test_throws ArgumentError FI.runtime_boundary!(rt,:caller_coupling_mutation)
            d[1]=before
            before=bundle.common.local_ha[1];bundle.common.local_ha[1]+=0.1
            @test_throws ArgumentError FI.runtime_boundary!(rt,:caller_source_mutation)
            bundle.common.local_ha[1]=before
            mapping=only(ctx.basis.kpoints).mapping;before=mapping[1];mapping[1]=mapping[2]
            @test_throws ArgumentError FI.runtime_boundary!(rt,:caller_mapping_mutation)
            mapping[1]=before
            kinetic=only(filter(t->t isa DFTK.TermKinetic,rt.basis.terms)).kinetic_energies[1]
            before=kinetic[1];kinetic[1]+=0.1
            @test_throws ArgumentError FI.runtime_boundary!(rt,:caller_kinetic_mutation)
            kinetic[1]=before
            localop=only(H.common.blocks).local_op.potential
            before=localop[1];localop[1]+=0.1
            @test_throws ArgumentError FI.runtime_boundary!(rt,:caller_potential_mutation)
            localop[1]=before
            @test FI.runtime_boundary!(rt,:restored_valid_state;ham=H.full)
        end
        @testset "Density and seven-energy recovery stay independent" begin
            density=FI.context_orbital_density(rt,X,f;stream_k=true)
            @test norm(density.R-old_density.R)<=1e-12*max(norm(old_density.R),1)
            @test norm(density.n-old_density.n)<=1e-12*max(norm(old_density.n),1)
            @test norm(density.m-old_density.m)<=1e-12*max(norm(old_density.m),1)
            snapshot=deepcopy(density)
            again=FI.context_orbital_density(rt,X,f;stream_k=true)
            @test density==snapshot
            @test !Base.mightalias(density.R,again.R) && !Base.mightalias(density.n,again.n)
            @test !Base.mightalias(density.m,again.m)
            energy=FI.energy_snapshot(rt,X,f;expected_n=density.n,stream_k=true)
            @test Set(keys(energy.terms))==FI.FR_ENERGY_NAMES
            @test all(abs(energy.terms[key]-old_energy.terms[key])<=1e-10 for key in keys(old_energy.terms))
            @test abs(energy.total-old_energy.total)<=1e-10
            @test abs(energy.nonlocal_decomposition.projected_full_ha-old_energy.nonlocal_decomposition.projected_full_ha)<=1e-10
            @test FI.assert_energy_consistency(energy)
            @test density==snapshot
            @test FI.runtime_summary(rt).counters.density_calls==3
            operators=FI.runtime_fr_blocks(rt)
            @test abs(RelativisticProjectors.projected_nonlocal_energy(operators,X,rt.basis.kweights,f)-
                RelativisticProjectors.projected_nonlocal_energy(ctx.fr_blocks,X,ctx.basis.kweights,f))<=1e-10
        end
        @testset "Replacing current potential invalidates old handles" begin
            @test_throws ArgumentError h*probes[1]
            @test_throws ArgumentError FI.runtime_boundary!(rt,:stale_solver_return;ham=H.full)
            current=FI.build_full_hamiltonian(rt,n)
            @test FI.runtime_boundary!(rt,:current_solver_return;ham=current.full)
            @test FI.runtime_boundary!(rt,:tuple_solver_return;ham=(only(current.full),))
            @test_throws ArgumentError FI.runtime_boundary!(rt,:tuple_stale_return;ham=(h,))
            @test_throws ArgumentError FI.runtime_boundary!(rt,:tuple_wrong_type;ham=(only(current.full),nothing))
            @test all(isfinite,only(current.full)*probes[1])
            handles=FI.runtime_fr_blocks(rt)
            old_generation=FI.runtime_summary(rt).generation
            FI.close_runtime!(rt)
            summary=FI.runtime_summary(rt)
            @test summary.closed && summary.workspace_released && summary.owned_source_entries==0
            @test !summary.owned_context_present && summary.generation>old_generation
            @test FI.close_runtime!(rt)===rt
            @test_throws ArgumentError only(current.full)*probes[1]
            @test_throws ArgumentError only(handles)*probes[1]
            @test_throws ArgumentError FI.runtime_boundary!(rt,:after_close)
        end
    finally
        FI.close_runtime!(rt)
    end
    @test length(FI._FR_CONTEXT_CERTIFICATES)==original_contexts
    @test length(FI._BOUND_PSP_SOURCES)==original_sources
end

function closed_runtime_fixture(root;inject_failure=false,mutate_source=false)
    ctx=runtime_test_context(root);p=WeakRef(only(ctx.fr_blocks).P);weakctx=WeakRef(ctx)
    rt=FI.owned_runtime(ctx);n=fill(10/1000,16^3)
    h=only(FI.build_full_hamiltonian(rt,n).full)
    cause=nothing
    try
        if mutate_source
            only(ctx.fr_blocks).P[1]+=0.1
        elseif inject_failure
            error("synthetic callback failure")
        end
    catch error
        cause=error
    finally
        try
            FI.close_runtime!(rt)
        catch error
            isnothing(cause) && (cause=error)
        end
    end
    (;rt,h,p,weakctx,cause)
end

function run_owned_lifetime_tests(root)
    contexts=length(FI._FR_CONTEXT_CERTIFICATES);sources=length(FI._BOUND_PSP_SOURCES)
    @testset "Normal and exceptional close release original heavy owners" begin
        for mode in (:normal,:callback_failure,:source_mutation)
            state=closed_runtime_fixture(root;inject_failure=mode==:callback_failure,mutate_source=mode==:source_mutation)
            @test FI.runtime_summary(state.rt).closed
            @test FI.runtime_summary(state.rt).workspace_released
            @test (mode==:normal)==isnothing(state.cause)
            @test length(FI._FR_CONTEXT_CERTIFICATES)==contexts
            @test length(FI._BOUND_PSP_SOURCES)==sources
            # Explicitly separate reachability test; never part of a measured
            # action/map or a strategy to lower the production peak.
            for _ in 1:3
                GC.gc()
            end
            @test isnothing(state.p.value)
            @test isnothing(state.weakctx.value)
            @test_throws ArgumentError FI.runtime_boundary!(state.rt,:closed_callback)
        end
    end
end

if abspath(PROGRAM_FILE)==@__FILE__
    DFTK.disable_threading()
    @testset "Scoped SOC runtime: authenticated static fixtures and synthetic faults" begin
        run_owned_runtime_tests(PHASE6B_ROOT)
        run_owned_lifetime_tests(PHASE6B_ROOT)
    end
end
