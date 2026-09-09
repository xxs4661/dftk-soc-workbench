# Synthetic control-boundary contracts; no SCF or eigen/occupation solve.
using Test
const BoundaryFI=Main.FRIntegration
const BoundarySOC=Main.SOCSCF

function synthetic_boundary_map(n,imap,closing)
    summary=BoundarySOC.Controller.density_summary(n,1.;n_electrons=4)
    (;n_out=copy(n),raw=nothing,closure_ok=true,
      diagnostics=(;consumed_input_sha256=summary.sha256,orbital_density_sha256=summary.sha256))
end

mutable struct SyntheticOwnedBoundary
    events::Vector{Symbol}
    corrupted::Bool
end
struct SyntheticLegacyBoundary end
BoundaryFI.runtime_enabled(::SyntheticOwnedBoundary)=true
BoundaryFI.runtime_enabled(::SyntheticLegacyBoundary)=false
function BoundaryFI.runtime_boundary!(ctx::SyntheticOwnedBoundary,event;ham=nothing)
    push!(ctx.events,event)
    ctx.corrupted && error("synthetic boundary mutation")
    nothing
end
BoundaryFI.runtime_boundary!(::SyntheticLegacyBoundary,event;ham=nothing)=nothing

@testset "Controller callback retry preserves the first failure and history" begin
    ctx=SyntheticOwnedBoundary(Symbol[],false)
    original=ErrorException("synthetic first callback failed and corrupted its boundary")
    calls=Ref(0);records=Any[]
    callback=(record,raw)->BoundarySOC._runtime_call(ctx,:map_callback) do
        calls[]+=1;push!(records,record);ctx.corrupted=true;throw(original)
    end
    caught=try
        BoundarySOC._runtime_iterate_density_map(ctx,synthetic_boundary_map,ones(4);
            callback,dvol=1.,n_electrons=4,max_maps=3)
        nothing
    catch err
        err
    end
    @test caught isa CompositeException
    @test caught.exceptions[1] isa CompositeException
    @test caught.exceptions[1].exceptions[1]===original
    @test occursin("synthetic boundary mutation",sprint(showerror,caught.exceptions[2]))
    @test calls[]==1  # Retry rejects at entry, before invoking the user callback.
    @test only(records)["status"]=="FAIL"
    @test occursin("synthetic first callback",only(records)["failure_reason"])

    for context in (SyntheticOwnedBoundary(Symbol[],false),SyntheticLegacyBoundary())
        calls=Ref(0);first_error=ErrorException("synthetic callback failure without source mutation")
        callback=(record,raw)->begin
            calls[]+=1
            calls[]==1 && throw(first_error)
            nothing
        end
        caught=try
            BoundarySOC._runtime_iterate_density_map(context,synthetic_boundary_map,ones(4);
                callback,dvol=1.,n_electrons=4,max_maps=3)
            nothing
        catch err
            err
        end
        controller_error=if BoundaryFI.runtime_enabled(context)
            @test caught isa CompositeException
            @test caught.exceptions[1]===first_error
            caught.exceptions[2]
        else
            caught  # Legacy retains the exact original controller exception type.
        end
        @test controller_error isa BoundarySOC.Controller.DensityMapFailure
        @test only(controller_error.history)["status"]=="FAIL"
        @test occursin("synthetic callback failure",controller_error.reason)
        @test calls[]==2
    end

    seen=Int[]
    success=BoundarySOC._runtime_iterate_density_map(SyntheticOwnedBoundary(Symbol[],false),
        synthetic_boundary_map,ones(4);callback=(r,raw)->push!(seen,r["map_index"]),
        dvol=1.,n_electrons=4,max_maps=3)
    @test success.status=="PASS" && success.converged && success.map_count==2
    @test seen==[1,2]
end

@testset "Synthetic SOC runtime boundary contracts, no solve" begin
    ctx=SyntheticOwnedBoundary(Symbol[],false)
    settings=Dict("tolerance"=>1e-10,"mixing"=>.1)
    stamp=BoundarySOC._runtime_settings_stamp(ctx,settings)
    x=ComplexF64[1+im,2-im];before=copy(x)
    value=BoundarySOC._runtime_call(()->sum(abs2,x),ctx,:callback;
        settings,stamp,payload=(;x))
    @test value==7
    @test x==before
    @test ctx.events==[:callback_entry,:callback_return]

    @test_throws ArgumentError BoundarySOC._runtime_call(
        ()->(x[1]=3),ctx,:callback;settings,stamp,payload=(;x))
    x.=before
    @test_throws ArgumentError BoundarySOC._runtime_call(
        ()->(settings["tolerance"]=1e-8),ctx,:callback;settings,stamp)
    @test_throws ArgumentError BoundarySOC._runtime_check_settings(ctx,settings,stamp)
    settings["tolerance"]=1e-10

    original=ErrorException("synthetic callback failure")
    caught=try
        BoundarySOC._runtime_call(()->throw(original),ctx,:callback;settings,stamp)
        nothing
    catch error
        error
    end
    @test caught===original
    @test last(ctx.events)==:callback_error

    caught=try
        BoundarySOC._runtime_call(ctx,:callback;settings,stamp) do
            ctx.corrupted=true
            throw(original)
        end
        nothing
    catch error
        error
    end
    @test caught isa CompositeException
    @test caught.exceptions[1]===original
    @test occursin("synthetic boundary mutation",sprint(showerror,caught.exceptions[2]))

    legacy=SyntheticLegacyBoundary()
    @test BoundarySOC._runtime_settings_stamp(legacy,settings)===nothing
    @test BoundarySOC._runtime_call(()->(x[1]=4),legacy,:callback;payload=(;x))==4
    @test x[1]==4  # New opt-in observation-only contract does not redefine legacy callbacks.
end

@testset "Every callback-visible saved numerical field is protected" begin
    for field in (:rho,:local_potential,:vH,:vxc)
        energy=(;ham=nothing,common_ham=nothing,rho=[1.],local_potential=[2.],vH=[3.],vxc=[4.])
        raw=(;X=[1.],all_X=[2.],f=[.5],eigenvalues=[1.],n_in=[1.],n_out=[1.],
          density=(;n=[1.]),energy,thermal=(;total=1.),ensemble=(;f=[.5]),diag=(;checked=true))
        payload=BoundarySOC._runtime_callback_payload(Dict("status"=>"PASS"),raw)
        @test !hasproperty(payload.energy,:ham) && !hasproperty(payload.energy,:common_ham)
        ctx=SyntheticOwnedBoundary(Symbol[],false)
        @test_throws ArgumentError BoundarySOC._runtime_call(
            ()->(getproperty(energy,field)[1]+=1),ctx,:callback;payload)
    end
    raw=(;X=[1.],all_X=[2.],f=[.5],eigenvalues=[1.],n_in=[1.],n_out=[1.],
      density=(;n=[1.]),energy=(;ham=nothing,common_ham=nothing,total=1.),
      thermal=(;total=1.),ensemble=(;f=[.5]),diag=(;checked=true))
    payload=BoundarySOC._runtime_callback_payload(Dict("status"=>"PASS"),raw)
    ctx=SyntheticOwnedBoundary(Symbol[],false)
    @test_throws ArgumentError BoundarySOC._runtime_call(()->(raw.ensemble.f[1]=.2),ctx,:callback;payload)
end
