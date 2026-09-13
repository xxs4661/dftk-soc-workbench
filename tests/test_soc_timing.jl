# Synthetic control/timing tests only: no DFTK context or electronic calculation.
using Test, Random, LinearAlgebra, SHA
include("../prototypes/diagnostics.jl")
const D=WorkbenchDiagnostics

module SyntheticController
using LinearAlgebra, SHA
include("../prototypes/spinor/scf.jl")
end
module SecondSyntheticController
using LinearAlgebra, SHA
include("../prototypes/spinor/scf.jl")
end
module LegacySyntheticController
using LinearAlgebra, SHA
const root=normpath(joinpath(@__DIR__,".."))
const source=read(`git -C $root show 30befbc22ee52283a19a96694bfe20259891b583:prototypes/spinor/scf.jl`,String)
include_string(@__MODULE__,source,"E0/prototypes/spinor/scf.jl")
end

module SyntheticEnergyDFTK
using LinearAlgebra
struct TermKinetic;kinetic_energies;end
struct TermAtomicLocal;potential_values;end
struct TermHartree;end
struct TermXc;ρcore;end
struct TermEwald;energy;end
struct TermPspCorrection;energy;end
struct TermAtomicNonlocal;end
struct Energies;data::Dict{String,Float64};end
Base.pairs(e::Energies)=pairs(e.data)
Base.getproperty(e::Energies,key::Symbol)=key===:total ? sum(values(getfield(e,:data))) : getfield(e,key)
G_vectors(b,k)=[(0,0,0)]
function energy_hamiltonian(b,X,f;ρ)
    (;energies=Energies(Dict("Kinetic"=>2.,"AtomicLocal"=>3.,"Hartree"=>2.,
        "Xc"=>5.,"Ewald"=>7.,"PspCorrection"=>11.)),ham=[15.0*Matrix{ComplexF64}(I,2,2)])
end
total_local_potential(ham)=[13.0]
apply_kernel(term,b,rho)=[4.0]
end
module SyntheticEnergySpinor
_density_checked_weights(w,n)=w
end
module SyntheticEnergy
using LinearAlgebra
const DFTK=Main.SyntheticEnergyDFTK
const SpinorPrototype=Main.SyntheticEnergySpinor
include("../prototypes/fr_integration/energy.jl")
struct Context;basis;fr_blocks;end
validate_context(ctx::Context)=true
context_orbital_density(ctx::Context,X,f;stream_k=false)=(;n=[1.0],m=zeros(1,3))
compose_full_hamiltonian(ctx::Context,ham)=[28.0*Matrix{ComplexF64}(I,2,2)]
_context_density_binding!(ctx::Context,rho)=nothing
nonlocal_spin_decomposition(::Symbol,X,w,f)=(;full_ha=13.,projected_normalized_error=0.,decomposition_difference_ha=0.)
end

@testset "existing energy path with optional timing and synthetic providers" begin
    @test SyntheticEnergy.EnergyDiagnostics===D
    T=SyntheticEnergyDFTK
    basis=(;model=(;n_electrons=1),kpoints=[1],kweights=[1.0],dvol=1.0,fft_size=(1,1,1),
        terms=Any[T.TermKinetic([[2.0]]),T.TermAtomicLocal([3.0]),T.TermHartree(),
            T.TermXc(nothing),T.TermEwald(7.0),T.TermPspCorrection(11.0)])
    ctx=SyntheticEnergy.Context(basis,:synthetic)
    X=[reshape(ComplexF64[1,0],2,1)];f=[[1.0]]
    baseline=SyntheticEnergy.energy_snapshot(ctx,X,f;expected_n=[1.0],stream_k=true)
    session=D.Session("synthetic-energy";enabled=true)
    timed=D.with_span(session,:energy_snapshot) do
        SyntheticEnergy.energy_snapshot(ctx,X,f;expected_n=[1.0],stream_k=true,diagnostics=session)
    end
    @test timed.total==baseline.total==43.0
    @test timed.report==baseline.report && timed.terms==baseline.terms
    @test timed.density==baseline.density
    @test isempty(session.stack)
    for name in ("energy_density_recovery","energy_common_hamiltonian","energy_compose_hamiltonian",
                 "energy_nonlocal_decomposition","energy_hartree_kernel_check","energy_consistency_check")
        @test count(r->r.name==name,session.rows)==1
    end
    @test_throws ArgumentError SyntheticEnergy.energy_snapshot(ctx,X,f;expected_n=[2.0],diagnostics=session)
    @test isempty(session.stack)
end

module SyntheticFI
using SHA
runtime_enabled(ctx)=ctx.owned
function validate_context end
_source_snapshot(value)=repr(value)
integration_density_hash(value)=bytes2hex(SHA.sha256(reinterpret(UInt8,vec(copy(value)))))
reset_full_counters!(H)=nothing
full_operator_stats(H)=(;synthetic=true)
function assert_eigensolve_record(record,settings)
    maximum(record.explicit_residuals_ha)<=settings["thresholds"]["input_residual_ha"] || error("synthetic residual failed")
    record.orthogonality_frobenius<=settings["thresholds"]["gram_norm"] || error("synthetic Gram failed")
    true
end
function runtime_boundary!(ctx,event;ham=nothing)
    push!(ctx.events,event)
    ctx.fail_boundary && error("synthetic source validation failure")
    true
end
end
module SyntheticDFTK
using LinearAlgebra
module Smearing
struct FermiDirac end
end
struct TermKinetic
    kinetic_energies::Vector{Vector{Float64}}
end
ortho_qr(X)=Matrix(qr(X).Q)
end
module SyntheticSOC
using Random, LinearAlgebra
const FI=Main.SyntheticFI
const DFTK=Main.SyntheticDFTK
const Controller=Main.SyntheticController
const RunDiagnostics=Main.WorkbenchDiagnostics
ComponentKineticPreconditioner(args...;shift)=nothing
include("../prototypes/soc_scf/solver.jl")
include("../prototypes/soc_scf/scf.jl")
end
mutable struct SyntheticContext
    owned::Bool
    events::Vector{Symbol}
    fail_boundary::Bool
    basis::Any
end
SyntheticContext(owned,events,fail_boundary)=SyntheticContext(owned,events,fail_boundary,
    (;terms=[SyntheticDFTK.TermKinetic([zeros(32),zeros(32)])]))

struct SyntheticMapContext;basis;end
SyntheticFI.runtime_enabled(::SyntheticMapContext)=false
SyntheticFI.runtime_boundary!(::SyntheticMapContext,event;ham=nothing)=nothing
SyntheticFI.validate_context(::SyntheticMapContext)=true
function SyntheticSOC.soc_map(ctx::SyntheticMapContext,n,settings,previous,target;
        seed,map_index,is_closure=false,previous_potential=nothing,probe,hooks=NamedTuple(),
        progress=(r)->nothing,diagnostics=nothing)
    output=[1.2,0.8,1.0,1.0]
    sin=SyntheticController.density_summary(n,1.;n_electrons=4)
    sout=SyntheticController.density_summary(output,1.;n_electrons=4)
    diag=(;consumed_input_sha256=sin.sha256,orbital_density_sha256=sout.sha256)
    raw=(;all_X=[copy(n)],energy=(;ham=nothing))
    (;n_out=output,raw,diagnostics=diag,closure_ok=false,potential=[Float64(map_index)],target)
end

@testset "actual SOC driver closure forwarding with a synthetic map" begin
    settings=Dict("ensemble"=>Dict("tau_ha"=>.001,"smearing"=>"FermiDirac",
        "capacity_per_spinor_state"=>1,"root_maxiter"=>256,"root_electron_atol"=>1e-12),
        "solver"=>Dict("initial_target_states"=>24,"auxiliary_states"=>6,"target_increment"=>8,
            "max_target_states"=>48,"tolerance_ha"=>1e-10,"maxiter"=>300),
        "scf"=>Dict("alpha"=>.1,"max_maps"=>400),"seeds"=>Dict("potential_probe"=>17),
        "thresholds"=>Dict("density_fixedpoint_l2"=>1e-8,"electron_count_abs"=>1e-8))
    basis=(;model=(;temperature=.001,smearing=SyntheticDFTK.Smearing.FermiDirac(),n_electrons=4),
        dvol=1.,kpoints=[(;G_vectors=[(0,0,0)])])
    ctx=SyntheticMapContext(basis);session=D.Session("synthetic-map";enabled=true)
    stop=D.ControlledStop("DIAGNOSTIC_MAP_LIMIT";map_index=2)
    records=Any[]
    caught=try
        SyntheticSOC.soc_scf(ctx,ones(4),settings;seed=81001,diagnostics=session,
            callback=(record,raw)->begin
                push!(records,copy(record));record["map_index"]==2 && throw(stop)
            end)
    catch err;err end
    @test caught===stop
    @test length(records)==2 && all(r->r["status"]=="CONTINUE",records)
    @test isempty(session.stack)
    @test count(r->r.name=="scf_initialization",session.rows)==1
    @test count(r->r.name=="map_total",session.rows)==2
end

clock_fixture()=(t=Ref{UInt64}(0);(t,()->t[]))
@testset "optional scalar timing" begin
    t,clock=clock_fixture()
    session=D.Session("synthetic";enabled=true,clock)
    result=D.with_span(session,:parent;map_index=2) do
        t[]+=10
        D.with_span(session,:child;k_index=3) do
            t[]+=20
            12
        end
        t[]+=5
        41
    end
    @test result==41
    @test length(session.rows)==2
    child,parent=session.rows
    @test (child.inclusive_ns,child.exclusive_ns,parent.inclusive_ns,parent.exclusive_ns)==(20,20,35,15)
    @test child.parent_span==parent.span_id
    @test child.map_index==2 && child.k_index==3
    @test parent.status==child.status=="COMPLETE"
    @test isempty(session.stack)
    observed=Any[];D.flush!(session,rows->append!(observed,rows))
    @test length(observed)==2 && isempty(session.rows)
    @test all(all(v->v isa Union{Integer,AbstractString},values(r)) for r in observed)
    D.finish!(session)
    @test_throws ArgumentError D.with_span(()->1,session,:late)

    calls=Ref(0)
    off=D.Session("off";enabled=false,clock=()->(calls[]+=1;UInt64(0)))
    rng=MersenneTwister(123);expected=rand(copy(rng),5)
    @test D.with_span(()->rand(rng,5),off,:unused)==expected
    @test calls[]==0 && isempty(off.rows)
    @test rand(rng)==rand((r=MersenneTwister(123);rand(r,5);r))
    marker=ArgumentError("original")
    for mode in (nothing,off)
        caught=try D.with_span(()->throw(marker),mode,:failure);nothing catch err;err end
        @test caught===marker
    end
    function lexical(session)
        local value
        D.@span session :lexical 1 2 begin
            value=6
        end
        value+1
    end
    @test lexical(off)==7
    @test lexical(D.Session("on";enabled=true))==7
end

@testset "actual target-solver wrapper with synthetic returned eigenstates" begin
    settings=Dict("solver"=>Dict("auxiliary_states"=>6,"preconditioner_shift_ha"=>1.0,
        "tolerance_ha"=>1e-10,"maxiter"=>300),
        "thresholds"=>Dict("gram_norm"=>1e-10,"input_residual_ha"=>1e-10),
        "seeds"=>Dict("extension_stride"=>100))
    H=Matrix{ComplexF64}(I,64,64)
    # Identity-H exact states: this hook returns the supplied orthonormal
    # columns and known eigenvalues. It performs no eigensolve or SCF.
    supplied=(H,X,prec,k,map)->(;converged=true,n_iter=1,n_matvec=size(X,2),X=copy(X),λ=ones(size(X,2)))
    outputs=Any[]
    for diagnostics in (nothing,D.Session("solver-off"),D.Session("solver-on";enabled=true))
        ctx=SyntheticContext(true,Symbol[],false)
        progress=Any[]
        solved=SyntheticSOC.solve_soc_targets(ctx,[H,H],nothing,24,settings;
            seed=81001,map_index=1,solve_hook=supplied,
            progress=event->push!(progress,event),diagnostics)
        @test length(progress)==2 && length(solved.records)==2
        @test all(r->r.target_states==24 && r.auxiliary_states==6 && r.converged,solved.records)
        @test all(r->r.initial_unchanged && r.elapsed_seconds>=0,solved.records)
        push!(outputs,solved)
        if !isnothing(diagnostics) && diagnostics.enabled
            @test isempty(diagnostics.stack)
            @test count(r->r.name=="k_total",diagnostics.rows)==2
            @test count(r->r.name=="eigensolve_body",diagnostics.rows)==2
            @test count(r->r.name=="explicit_eigen_checks",diagnostics.rows)==2
        end
    end
    for tested in outputs[2:3]
        @test tested.X==outputs[1].X
        @test tested.all_X==outputs[1].all_X
        @test tested.eigenvalues==outputs[1].eigenvalues
        @test getproperty.(tested.records,:initial_sha256)==getproperty.(outputs[1].records,:initial_sha256)
    end
    stop=D.ControlledStop("USER_CANCELLED";boundary="k_before",map_index=1,k_index=1)
    session=D.Session("solver-stop";enabled=true,boundary_hook=(event,m,k)->(event=="k_before" && throw(stop)))
    solved_calls=Ref(0)
    caught=try
        SyntheticSOC.solve_soc_targets(SyntheticContext(true,Symbol[],false),[H],nothing,24,settings;
            seed=81001,map_index=1,solve_hook=(args...)->(solved_calls[]+=1),diagnostics=session)
    catch err;err end
    @test caught===stop && solved_calls[]==0
    @test isempty(session.stack)
end

@testset "exception closure and bounded flushing" begin
    t,clock=clock_fixture();session=D.Session("failure";enabled=true,clock)
    failure=ArgumentError("synthetic writer")
    caught=try
        D.with_span(session,:write) do
            t[]+=7;throw(failure)
        end
    catch err;err end
    @test caught===failure
    @test only(session.rows).status=="ERROR"
    @test only(session.rows).inclusive_ns==7 && isempty(session.stack)
    @test_throws ArgumentError D.flush!(session,rows->throw(failure))
    @test length(session.rows)==1
    stop=D.ControlledStop("USER_CANCELLED";boundary="before_k",map_index=1,k_index=2)
    caught=try D.with_span(()->throw(stop),session,:cancel) catch err;err end
    @test caught===stop
    @test last(session.rows).status=="STOPPED"
    @test D.stop_only(CompositeException([stop,stop]))
    @test !D.stop_only(CompositeException([stop,failure]))
    limited=D.Session("bounded";enabled=true,max_rows=1)
    D.with_span(()->1,limited,:one)
    @test_throws ArgumentError D.with_span(()->2,limited,:two)
    D.flush!(limited,rows->nothing)
    @test D.with_span(()->3,limited,:three)==3
    t,clock=clock_fixture();bad=D.Session("clock";enabled=true,clock)
    caught=try
        D.with_span(bad,:clock_failure) do
            t[]=typemax(UInt64);throw(failure)
        end
    catch err;err end
    @test caught isa CompositeException
    @test first(caught.exceptions)===failure
end

function synthetic_map(n,index,closing)
    output=[1.2,0.8,1.0,1.0]
    sin=SyntheticController.density_summary(n,1.0;n_electrons=4)
    sout=SyntheticController.density_summary(output,1.0;n_electrons=4)
    (;n_out=output,raw=(;index),closure_ok=false,
      diagnostics=(;consumed_input_sha256=sin.sha256,orbital_density_sha256=sout.sha256))
end

@testset "actual shared controller and guarded stop propagation" begin
    @test SyntheticController.RunDiagnostics===D
    @test SecondSyntheticController.RunDiagnostics===D
    ctx=SyntheticContext(true,Symbol[],false)
    for enabled in (false,true)
        t,clock=clock_fixture();events=Tuple[]
        session=D.Session("controller";enabled,clock,boundary_hook=(event,m,k)->push!(events,(event,m,k)))
        stop=D.ControlledStop("DIAGNOSTIC_MAP_LIMIT";boundary="map_saved",map_index=2)
        rows=Any[]
        callback=function(record,raw)
            t[]+=11;push!(rows,copy(record))
            record["map_index"]==2 && throw(stop)
        end
        caught=try
            SyntheticSOC._runtime_iterate_density_map(ctx,synthetic_map,ones(4);
                dvol=1.0,n_electrons=4,alpha=0.1,max_maps=400,callback,diagnostics=session)
        catch err;err end
        @test caught===stop
        @test length(rows)==2
        @test all(r->r["status"]=="CONTINUE",rows)
        @test isempty(session.stack)
        if enabled
            maps=filter(r->r.name=="map_total",session.rows)
            @test length(maps)==2
            @test all(r->r.inclusive_ns==11,maps) # Includes output callback work.
        else
            @test isempty(session.rows)
        end
    end
    stop=D.ControlledStop("TIME_BUDGET_EXCEEDED";boundary="map_before",map_index=1)
    session=D.Session("early";enabled=true,boundary_hook=(args...)->throw(stop))
    map_calls=Ref(0);callback_calls=Ref(0)
    caught=try
        SyntheticController.iterate_density_map((args...)->(map_calls[]+=1),ones(4);
            dvol=1.0,n_electrons=4,diagnostics=session,callback=(args...)->(callback_calls[]+=1))
    catch err;err end
    @test caught===stop && map_calls[]==callback_calls[]==0
    @test isempty(session.stack)

    # The exact old controller wraps a foreign cancellation exception: a real
    # regression uses this production controller and asserts the new typed path.
    numerical=ArgumentError("synthetic numerical error")
    caught=try
        SyntheticController.iterate_density_map((args...)->throw(numerical),ones(4);
            dvol=1.0,n_electrons=4,callback=(args...)->throw(stop))
    catch err;err end
    @test caught isa CompositeException
    @test caught.exceptions==[numerical,stop]

    payload=[1.0];session=D.Session("guards";enabled=true)
    caught=try
        SyntheticSOC._runtime_call(ctx,:synthetic;payload,diagnostics=session) do
            payload[1]=2.0;throw(stop)
        end
    catch err;err end
    @test caught isa CompositeException
    @test first(caught.exceptions)===stop
    @test occursin("changed a borrowed numerical payload",sprint(showerror,last(caught.exceptions)))
    @test isempty(session.stack)
    ctx.events=Symbol[];payload=[1.0]
    @test SyntheticSOC._runtime_call(()->42,ctx,:synthetic;payload,diagnostics=session)==42
    @test ctx.events==[:synthetic_entry,:synthetic_return]
end

@testset "fixed E0 cancellation counterexample and default controller parity" begin
    stop=D.ControlledStop("USER_CANCELLED";boundary="synthetic")
    old=try
        LegacySyntheticController.iterate_density_map((args...)->throw(stop),ones(4);
            dvol=1.0,n_electrons=4)
    catch err;err end
    new=try
        SyntheticController.iterate_density_map((args...)->throw(stop),ones(4);
            dvol=1.0,n_electrons=4)
    catch err;err end
    @test old isa LegacySyntheticController.DensityMapFailure
    @test old !== stop && occursin("USER_CANCELLED",old.reason)
    @test only(old.history)["status"]=="FAIL"
    @test new===stop
    # Exact-sentinel fallback permitted for the unedited E0 reference route.
    sentinel=LegacySyntheticController.DensityMapFailure("synthetic exact two-map stop",Any[])
    seen=Any[]
    caught=try
        LegacySyntheticController.iterate_density_map(synthetic_map,ones(4);
            dvol=1.0,n_electrons=4,alpha=0.1,max_maps=400,callback=(r,raw)->begin
                push!(seen,copy(r));r["map_index"]==2 && throw(sentinel)
            end)
    catch err;err end
    @test caught===sentinel && length(seen)==2
    snapshots=Any[]
    for controller in (LegacySyntheticController,SyntheticController)
        identity_map=(n,index,closing)->begin
            summary=controller.density_summary(n,1.;n_electrons=4)
            (;n_out=copy(n),raw=nothing,closure_ok=true,
              diagnostics=(;consumed_input_sha256=summary.sha256,orbital_density_sha256=summary.sha256))
        end
        push!(snapshots,controller.iterate_density_map(identity_map,ones(4);
            dvol=1.,n_electrons=4,max_maps=400,alpha=.1,density_tol=1e-8))
    end
    @test snapshots[1]==snapshots[2]
    @test snapshots[2].converged && snapshots[2].map_count==2
end
