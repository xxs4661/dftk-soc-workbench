# Synthetic lifecycle regression for the actual static driver's private helper.
# No driver main/local_work, material context, physics package, solve or monitor
# is called. Toy objects test ownership visibility at cooperative boundaries.
using Test
include("../benchmarks/soc-validation-local-v1/driver.jl")

mutable struct LifecycleToy
    name::Symbol
end
fresh_lifecycle_result()=Dict{String,Any}(
    "context_constructed"=>false,"owned_runtime_constructed"=>false,
    "runtime_state"=>"NOT_CONSTRUCTED","runtime_closed"=>false,
    "workspace_released"=>false,"stages"=>Dict{String,Any}())
lifecycle_error(f)=try f();nothing catch err;err end

function check_timing_fields(fields)
    for key in ("seconds","gc_seconds")
        @test fields[key] isa Real && !(fields[key] isa Bool) && isfinite(fields[key]) && fields[key]>=0
    end
    @test fields["allocation_bytes"] isa Integer && !(fields["allocation_bytes"] isa Bool) && fields["allocation_bytes"]>=0
    for key in ("compile_time","recompile_time")
        value=fields[key]
        @test isnothing(value) || (value isa Real && !(value isa Bool) && isfinite(value) && value>=0)
    end
end

@testset "Synthetic static-driver lifecycle; no material construction" begin
    @test VERSION==v"1.12.7"
    @test !isdefined(@__MODULE__,:FI) && !isdefined(@__MODULE__,:DFTK)
    boundaries=("context_setup_before","context_setup_after","runtime_setup_before","runtime_setup_after")
    for (index,where) in enumerate(boundaries)
        ctx=LifecycleToy(:context);rt=LifecycleToy(:runtime)
        cr=Ref{Any}(nothing);rr=Ref{Any}(nothing);result=fresh_lifecycle_result()
        context_calls=Ref(0);runtime_calls=Ref(0);seen=String[]
        stop=LD.ControlledStop("USER_CANCELLED";request_id="synthetic",boundary=where)
        boundary=event->begin push!(seen,event);event==where && throw(stop);nothing end
        error=lifecycle_error() do
            construct_static!(cr,rr,result,boundary,
                ()->(context_calls[]+=1;ctx),
                given->(runtime_calls[]+=1;@test(given===ctx);rt))
        end
        @test error===stop
        @test seen==collect(boundaries[1:index])
        @test context_calls[]==(index>=2 ? 1 : 0)
        @test runtime_calls[]==(index==4 ? 1 : 0)
        @test cr[]===(index>=2 ? ctx : nothing)
        @test rr[]===(index==4 ? rt : nothing)
        @test result["context_constructed"]===(index>=2)
        @test result["owned_runtime_constructed"]===(index==4)
        @test result["runtime_state"]==(index==4 ? "OPEN" : "NOT_CONSTRUCTED")
        @test result["runtime_closed"]===false && result["workspace_released"]===false
        @test Set(keys(result["stages"]))==Set(index==1 ? String[] : index==4 ? ["context_setup","runtime_setup"] : ["context_setup"])
        foreach(check_timing_fields,values(result["stages"]))
    end
    for failing in (:context,:runtime)
        ctx=LifecycleToy(:context);cr=Ref{Any}(nothing);rr=Ref{Any}(nothing)
        result=fresh_lifecycle_result();failure=ErrorException("synthetic native constructor failure")
        error=lifecycle_error() do
            construct_static!(cr,rr,result,event->nothing,
                ()->(failing===:context ? throw(failure) : ctx),given->throw(failure))
        end
        @test error===failure
        @test cr[]===(failing===:runtime ? ctx : nothing)
        @test isnothing(rr[])
        @test result["context_constructed"]===(failing===:runtime)
        @test result["owned_runtime_constructed"]===false
        @test !haskey(result["stages"],"runtime_setup")
    end
    ctx=LifecycleToy(:context);rt=LifecycleToy(:runtime)
    cr=Ref{Any}(nothing);rr=Ref{Any}(nothing);result=fresh_lifecycle_result();seen=String[]
    @test construct_static!(cr,rr,result,event->push!(seen,event),()->ctx,given->(@test(given===ctx);rt))===nothing
    @test cr[]===ctx && rr[]===rt && seen==collect(boundaries)
    @test result["context_constructed"] && result["owned_runtime_constructed"] && result["runtime_state"]=="OPEN"
    foreach(check_timing_fields,values(result["stages"]))
    value,timing=timed_record(()->rt)
    @test value===rt
    check_timing_fields(timing)
end
println("Synthetic lifecycle only; Julia ",VERSION,"; JSON3 ",Base.pkgversion(JSON3),"; no material context or monitoring")
