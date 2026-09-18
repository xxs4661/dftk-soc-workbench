# Source-authentication / mutable-storage protection tests on artificial data.
# Actual frozen-R and candidate functions run; no real UPF/material/SCF/solve.
include("soc_boundary/fixtures.jl")

const FI=BoundaryCandidate
const D=WorkbenchDiagnostics
const VARIANTS=(("frozen R",BoundaryReference,:strict,ReferenceSOC),
    ("current strict",BoundaryCandidate,:strict,BoundarySOC),
    ("single validation",BoundaryCandidate,:single_validation_v1,BoundarySOC))

function assert_no_live_memo(rt)
    s=FI.runtime_summary(rt).validation
    @test !s.active && s.live_array_entries==0 && s.live_source_entries==0
    @test isnothing(rt._validation_active)
end

@testset "Legacy/current strict/OPT reject the same sequential changes before use" begin
    mutations=[
        "P content" => f->(f.ctx.fr_blocks[1].P[1]+=0.25),
        "D content" => f->(f.ctx.fr_blocks[1].D[1]+=0.25),
        "channel labels" => f->(f.ctx.fr_blocks[1].labels[1]=(;atom=2,l=1)),
        "second-block labels after shared-array reuse" => f->(f.ctx.fr_blocks[2].labels[1]=(;atom=2,l=1)),
        "same-size block replacement" => f->(f.ctx.fr_blocks[1]=SyntheticFR(copy(f.ctx.fr_blocks[1].P),copy(f.ctx.fr_blocks[1].D),deepcopy(f.ctx.fr_blocks[1].labels))),
        "common local source" => f->(f.ctx.bundles[1].common.local_ha[1]+=0.25),
        "common radial source" => f->(f.ctx.bundles[1].common.r[2]+=0.01),
        "parsed source array" => f->(f.ctx.bundles[1].parsed.local_[1]+=0.25),
        "source channel data" => f->(f.ctx.bundles[1].channels.channels[1].radial[1]+=0.25),
        "source NLCC" => f->(f.ctx.bundles[1].common.r2_core[2]+=0.25),
        "source metadata" => f->(f.ctx.bundles[1].sha256="changed"),
        "source-object replacement" => f->(f.ctx.bundles[1]=deepcopy(f.ctx.bundles[1])),
        "same-size common replacement" => f->(f.ctx.bundles[1].common=deepcopy(f.ctx.bundles[1].common)),
        "atom order" => f->reverse!(f.ctx.basis.model.atoms),
        "bundle order" => f->reverse!(f.ctx.bundles),
        "G order" => f->reverse!(f.ctx.basis.kpoints[1].G_vectors),
        "FFT mapping" => f->reverse!(f.ctx.basis.kpoints[1].mapping),
        "inverse FFT mapping" => f->reverse!(f.ctx.basis.kpoints[1].mapping_inv),
        "device FFT mapping" => f->reverse!(f.ctx.basis.kpoints[1].mapping_device),
        "k coordinate" => f->(f.ctx.basis.kpoints[1].coordinate[1]=0.25),
        "k replacement" => f->(f.ctx.basis.kpoints[1]=deepcopy(f.ctx.basis.kpoints[1])),
        "spatial weights" => f->(f.ctx.basis.kweights .= [0.6,0.4]),
        "lattice" => f->(f.ctx.basis.model.lattice[1,1]+=0.1),
        "atomic position" => f->(f.ctx.basis.model.positions[1][1]+=0.1),
        "electron count" => f->(f.ctx.basis.model.n_electrons=5),
        "FFT shape" => f->(f.ctx.basis.fft_size=(1,2,1)),
        "cutoff" => f->(f.ctx.basis.Ecut=3.),
        "temperature" => f->(f.ctx.basis.model.temperature=0.01),
        "model XC" => f->(f.ctx.basis.model.term_types[6].functionals=[:other]),
        "instantiated XC" => f->(f.ctx.basis.terms[6].functionals=[:other]),
        "NLCC switch" => f->(f.ctx.basis.model.term_types[6].use_nlcc=false),
        "derived core density" => f->(f.ctx.basis.terms[6].ρcore[1]+=0.25),
        "kinetic values" => f->(f.ctx.basis.terms[1].kinetic_energies[1][1]+=0.25),
        "kinetic scale" => f->(f.ctx.basis.terms[1].scaling_factor=2.),
        "Hartree values" => f->(f.ctx.basis.terms[5].poisson_green_coeffs[1]+=0.25),
        "Ewald value" => f->(f.ctx.basis.terms[3].energy+=0.25),
        "same-size derived replacement" => f->(f.ctx.basis.terms[5].poisson_green_coeffs=copy(f.ctx.basis.terms[5].poisson_green_coeffs)),
        "current potential content" => f->(f.common.blocks[1].local_op.potential[1]+=0.25),
        "same-size current potential replacement" => f->(f.common.blocks[1].local_op.potential=copy(f.common.blocks[1].local_op.potential)),
        "same-size current Fourier replacement" => f->(f.common.blocks[1].fourier_op.multiplier=copy(f.common.blocks[1].fourier_op.multiplier)),
        "common native nonlocal" => f->push!(f.common.blocks[1].operators,BoundaryDFTK.NonlocalOperator()),
    ]
    for (variant,mod,policy,SOC) in VARIANTS, (name,mutate!) in mutations
        @testset "$variant / $name" begin
            f=synthetic_runtime(mod;policy,shared_sources=false)
            try
                @test mod.runtime_boundary!(f.rt,:before_mutation;ham=f.full)
                mutate!(f);calls=Ref(0)
                # This entry is before the callback can publish/consume a value.
                err=captured(()->SOC._runtime_call(()->(calls[]+=1),f.rt,:external;ham=f.full))
                @test err isa ArgumentError
                @test calls[]==0
                mod===FI && assert_no_live_memo(f.rt)
            finally
                clean_fixture(f)
            end
            @test mod.runtime_summary(f.rt).closed
            @test mod.runtime_summary(f.rt).workspace_released
        end
    end
end

@testset "Unknown callbacks, double errors, stops and write failures retain boundaries" begin
    for (variant,mod,policy,SOC) in VARIANTS
        @testset "$variant" begin
            f=synthetic_runtime(mod;policy)
            try
                result=SOC._runtime_call(f.rt,:unknown;ham=f.full) do
                    mod===FI && assert_no_live_memo(f.rt)
                    41
                end
                @test result==41
                @test mod.runtime_boundary!(f.rt,:after_unknown;ham=f.full)
                p=f.ctx.fr_blocks[1].P;original=p[1]
                err=captured(()->SOC._runtime_call(f.rt,:unknown;ham=f.full) do
                    p[1]+=0.25
                    999
                end)
                @test err isa ArgumentError # altered callback result is never returned
                p[1]=original
                for stop in (ErrorException("synthetic callback failure"),
                    D.ControlledStop("USER_CANCELLED"),D.ControlledStop("TIME_BUDGET_EXCEEDED"),
                    D.ControlledStop("RESOURCE_HEADROOM"))
                    err=captured(()->SOC._runtime_call(f.rt,:unknown;ham=f.full) do
                        p[1]+=0.25
                        throw(stop)
                    end)
                    @test err isa CompositeException
                    leaves=flatten_errors(err)
                    @test any(x->x===stop,leaves)
                    @test any(x->x isa ArgumentError,leaves)
                    mod===FI && assert_no_live_memo(f.rt)
                    p[1]=original
                    # A separate boundary revalidates the restored state.
                    @test mod.runtime_boundary!(f.rt,:restored_after_error;ham=f.full)
                end
                settings=Dict("tolerance"=>1e-10);stamp=SOC._runtime_settings_stamp(f.rt,settings)
                payload=(;state=[1.,2.])
                @test_throws ArgumentError SOC._runtime_call(()->(payload.state[1]=3.),f.rt,:payload;
                    ham=f.full,payload,settings,stamp)
                @test_throws ArgumentError SOC._runtime_call(()->(settings["tolerance"]=1e-8),f.rt,:settings;
                    ham=f.full,settings,stamp)
                mktempdir() do directory
                    err=captured(()->SOC._runtime_call(()->open(directory,"w"),f.rt,:checkpoint;ham=f.full))
                    @test err isa SystemError
                    mod===FI && assert_no_live_memo(f.rt)
                end
            finally
                clean_fixture(f)
            end
            @test mod.runtime_summary(f.rt).closed && mod.runtime_summary(f.rt).workspace_released
            mod===FI && assert_no_live_memo(f.rt)
        end
    end
end

@testset "Runtime aliases, action reentry, stale handles and failure-atomic output" begin
    outputs=Any[]
    for (variant,mod,policy,SOC) in VARIANTS
        f=synthetic_runtime(mod;policy)
        try
            h=f.full[1];X=ComplexF64[1 im;2 -1;0.5 0;-im 0.5];Y=fill(3+2im,size(X))
            originalX=copy(X);before=copy(Y)
            @test_throws ArgumentError mul!(X,h,X)
            @test X==originalX
            @test_throws ArgumentError mul!(Y,h,X,NaN,0)
            @test Y==before
            for storage in (f.rt._workspace.common_action,f.rt._workspace.fr_action,
                            f.rt._workspace.nonlocal.candidate,f.rt._workspace.component.candidate)
                alias=@view storage[1:4,1:2];fill!(alias,3+2im);saved=copy(alias)
                @test_throws ArgumentError mul!(alias,h,X)
                @test alias==saved
            end
            mod._runtime_action_enter!(f.rt)
            @test_throws ArgumentError mod.runtime_boundary!(f.rt,:busy)
            @test_throws ArgumentError mod._runtime_action_enter!(f.rt)
            f.rt._busy=false
            push!(outputs,h*X)
            @test X==originalX
            current=mod.compose_full_hamiltonian(f.rt,f.common)
            @test_throws ArgumentError mod.runtime_boundary!(f.rt,:old;ham=f.full)
            @test_throws ArgumentError h*X
            @test mod.runtime_boundary!(f.rt,:new;ham=current)
            mod.close_runtime!(f.rt)
            @test_throws ArgumentError current[1]*X
            @test_throws ArgumentError mod.validate_context(f.rt)
            @test mod.close_runtime!(f.rt)===f.rt
        finally
            clean_fixture(f)
        end
    end
    @test outputs[1]==outputs[2]==outputs[3]
end

@testset "Single-call reuse is measured, next boundary rescans, and tokens expire" begin
    f=synthetic_runtime(;policy=:single_validation_v1)
    other=synthetic_runtime(;policy=:single_validation_v1)
    try
        before=FI.runtime_summary(f.rt).validation.counters
        @test FI.runtime_boundary!(f.rt,:measured;ham=f.full)
        after=FI.runtime_summary(f.rt).validation.counters
        for key in ("validation_calls","validation_completed","context_scan_calls","all_k_scan_calls")
            @test after[key]-before[key]==1
        end
        @test after["source_validation_calls"]-before["source_validation_calls"]==1
        @test after["source_validation_reuses"]-before["source_validation_reuses"]==1
        @test after["array_hash_calls"]>before["array_hash_calls"]
        @test after["array_hash_reuses"]>before["array_hash_reuses"]
        assert_no_live_memo(f.rt)
        @test FI.runtime_boundary!(f.rt,:next_boundary;ham=f.full)
        next=FI.runtime_summary(f.rt).validation.counters
        @test next["array_hash_calls"]-after["array_hash_calls"]==after["array_hash_calls"]-before["array_hash_calls"]
        @test next["source_validation_calls"]==after["source_validation_calls"]+1
        saved=Ref{Any}(nothing)
        FI._with_validation(f.rt) do memo
            saved[]=memo
            @test FI._validation_array_hash(memo,f.ctx.fr_blocks[1].P)==FI._fr_array_hash(f.ctx.fr_blocks[1].P)
            @test_throws ArgumentError FI.runtime_boundary!(f.rt,:nested_external_boundary)
            @test_throws ArgumentError FI._with_validation(_->nothing,f.rt)
            @test_throws ArgumentError FI._validation_bound_sources(other.rt,other.ctx.bundles[1],memo)
        end
        @test_throws ArgumentError FI._validation_array_hash(saved[],f.ctx.fr_blocks[1].P)
        @test isempty(saved[].arrays) && isempty(saved[].sources)
        @test saved[].owner===nothing && saved[].current===nothing && !saved[].active
        assert_no_live_memo(f.rt)
        failure=ErrorException("validation body failure")
        @test captured(()->FI._with_validation(f.rt) do memo
            saved[]=memo;FI._validation_array_hash(memo,f.ctx.fr_blocks[1].P);throw(failure)
        end)===failure
        assert_no_live_memo(f.rt)
        @test isempty(saved[].arrays) && saved[].owner===nothing
        @test_throws ArgumentError FI._with_validation(f.rt) do memo
            f.rt._generation+=1
            FI._validation_array_hash(memo,f.ctx.fr_blocks[1].P)
        end
        assert_no_live_memo(f.rt)
        # Fresh current handles after a deliberately advanced synthetic epoch.
        f.rt._generation-=1
        @test FI.runtime_boundary!(f.rt,:restored_generation;ham=f.full)
    finally
        clean_fixture(f);clean_fixture(other)
    end
    assert_no_live_memo(f.rt)
end

@testset "Default strict policy, return values, input bytes and RNG are unchanged" begin
    for (variant,mod,policy,SOC) in VARIANTS
        f=synthetic_runtime(mod;policy,default=mod===FI && policy===:strict)
        try
            input=copy(f.ctx.fr_blocks[1].P);digest=mod._fr_array_hash(input)
            Random.seed!(510);expected=rand(4);Random.seed!(510)
            off=D.Session("synthetic-boundary-default";enabled=false,clock=()->error("disabled clock called"))
            result=SOC._runtime_call(()->123,f.rt,:rng;ham=f.full,diagnostics=off)
            @test result==123 && rand(4)==expected
            @test f.ctx.fr_blocks[1].P==input && mod._fr_array_hash(input)==digest
            @test isempty(off.rows) && isempty(off.stack)
            if mod===FI
                summary=FI.runtime_summary(f.rt).validation
                @test summary.policy==string(policy)
                @test (policy===:strict)==(summary.counters===nothing)
                @test summary.counter_status==(policy===:strict ? "NOT_INSTRUMENTED" : "MEASURED_OPT_IN")
                assert_no_live_memo(f.rt)
            end
        finally
            clean_fixture(f)
        end
    end
end

include("soc_boundary/hash_contract.jl")

@testset "No synthetic authority survives runtime cleanup" begin
    for mod in (BoundaryReference,BoundaryCandidate)
        @test isempty(mod._FR_CONTEXT_CERTIFICATES)
        @test isempty(mod._BOUND_PSP_SOURCES)
    end
end
