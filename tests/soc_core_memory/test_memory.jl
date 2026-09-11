# Stdlib-only synthetic metadata/measurement tests; no DFTK, FFT or physics.
using Test, LinearAlgebra
include(joinpath(@__DIR__,"../../benchmarks/soc-core-memory-v1/memory.jl"))
using .SOCCoreMemory

struct UnknownLazyArray <: AbstractVector{Float64}
    hidden::Vector{Float64}
end
Base.size(::UnknownLazyArray)=error("must not invoke unknown lazy size")
Base.getindex(::UnknownLazyArray,::Int)=error("must not evaluate lazy values")
mutable struct SyntheticCycle
    value
end

@testset "Fixed warmup/five actual samples, no lost final output" begin
    calls=Ref(0);consumed=Ref(0)
    operation=()->begin calls[]+=1;fill(Float64(calls[]),3) end
    consume=x->begin consumed[]+=1;(checksum=sum(abs2,x),shape=size(x)) end
    output=measure_operation(operation;consume,name="synthetic")
    @test calls[]==consumed[]==6
    @test output.last_value==fill(6.0,3)
    report=output.report
    @test report["status"]=="PASS" && report["completed_samples"]==5
    @test report["warmup"]["index"]==0
    @test report["warmup"]["consumed"]["checksum"]==3
    @test [s["index"] for s in report["samples"]]==collect(1:5)
    @test [s["consumed"]["checksum"] for s in report["samples"]]==3 .* (collect(2:6).^2)
    for field in ("time_seconds","allocated_bytes","gc_seconds","compile_seconds","recompile_seconds")
        values=[sample[field] for sample in report["samples"]]
        @test all(x->isfinite(x)&&x>=0,values)
        @test report["statistics"][field]==Dict("median"=>sort(values)[3],"min"=>minimum(values),"max"=>maximum(values))
    end
    @test !haskey(report,"last_value")
    @test_throws ArgumentError measure_operation(operation;consume,warmup=0)
    @test_throws ArgumentError measure_operation(operation;consume,samples=6)
    @test_throws ArgumentError measure_operation(operation;consume,warmup=true)
    @test calls[]==6
end

@testset "Failures retain actual partial timing and stop" begin
    calls=Ref(0)
    failure=try
        measure_operation(()->begin calls[]+=1;calls[]==3 && error("synthetic failure");calls[] end;consume=identity)
        nothing
    catch error
        error
    end
    @test failure isa MeasurementFailure
    @test calls[]==3
    @test failure.partial_report["status"]=="FAIL"
    @test failure.partial_report["completed_samples"]==1
    @test length(failure.partial_report["samples"])==2
    @test failure.partial_report["samples"][end]["status"]=="FAIL"
    @test occursin("synthetic failure",sprint(showerror,failure))
    @test_throws MeasurementFailure measure_operation(()->[1.0];consume=identity)
    @test_throws MeasurementFailure measure_operation(()->1;consume=x->NaN)
    @test_throws MeasurementFailure measure_operation(()->1;consume=x->zeros(100))
end

@testset "Unique real backing storage and view/parent aliases" begin
    array=reshape(collect(1.0:24.0),4,6)
    view1=@view array[2:3,2:5]
    flat=reshape(array,24)
    reinterpreted=reinterpret(UInt8,vec(array))
    adjoint_view=view1'
    roots=(;array,view1,flat,reinterpreted,adjoint_view,again=array)
    report=unique_memory(roots)
    @test report["status"]=="COMPLETE_FOR_RECOGNIZED_JULIA_STORAGE"
    @test report["dense_unique_payload_bytes"]==sizeof(array)
    @test report["backing_owners"]==1
    @test report["overlap_payload_bytes"]==0
    @test report["array_objects"]>=5
    @test any(r->r["parent_object_id"]!==nothing,report["arrays"])
    @test any(r->r["additional_alias_paths"]>0,report["arrays"])
    @test report["combined_summarysize_bytes"]==Base.summarysize(roots;exclude=SOCCoreMemory._SKIP)
    @test report["combined_summarysize_bytes"]>=report["dense_unique_payload_bytes"]
    @test !occursin("0x",repr(report))
    two=unique_memory((array=array,copied=copy(array)))
    @test two["dense_unique_payload_bytes"]==2sizeof(array)
    @test two["backing_owners"]==2
    @test unique_memory((empty1=Float64[],empty2=Float64[]))["dense_unique_payload_bytes"]==0
end

@testset "Overlapping distinct headers, referenced arrays and closure roots" begin
    original=collect(1.0:20.0)
    GC.@preserve original begin
        alias=unsafe_wrap(Array,pointer(original),length(original);own=false)
        report=unique_memory((;original,alias))
        @test report["backing_owners"]==2
        @test report["dense_unique_payload_bytes"]==sizeof(original)
        @test report["overlap_payload_bytes"]==sizeof(original)
    end
    inner=zeros(ComplexF64,7)
    collection=[inner,inner]
    report=unique_memory((;collection))
    @test report["dense_unique_payload_bytes"]==sizeof(inner)+sizeof(collection)
    @test report["backing_owners"]==2
    callback=let state=inner
        ()->state
    end
    cycle=SyntheticCycle(nothing);cycle.value=cycle
    roots=(;callback,cycle,inner)
    report=unique_memory(roots)
    @test report["dense_unique_payload_bytes"]==sizeof(inner)
    @test report["reachable_objects"]>0
    @test_throws ArgumentError unique_memory(roots;max_objects=1)
end

@testset "Unknown/native metadata is not fabricated or evaluated" begin
    lazy=UnknownLazyArray(ones(5))
    report=unique_memory((lazy=lazy,compiler=Main,pointer=Ptr{Cvoid}(0)))
    @test report["status"]=="PARTIAL_UNKNOWN_ARRAY_STORAGE"
    @test length(report["unaccounted_arrays"])==1
    @test report["dense_unique_payload_bytes"]==sizeof(lazy.hidden)
    @test report["opaque_pointer_fields"]==1
    @test haskey(report["skipped_metadata_types"],"Module")
    @test !haskey(report,"native_malloc_bytes")
end

@testset "Registry table capacity counted without leaking dictionary keys" begin
    matrix=zeros(3,4)
    dict=Dict("/synthetic/private/path"=>matrix)
    registry=IdDict{Any,Any}(matrix=>dict)
    report=unique_memory((;registry,matrix))
    @test report["dense_unique_payload_bytes"]>sizeof(matrix)
    @test report["backing_owners"]>=4
    @test !occursin("/synthetic/private/path",repr(report))
    @test any(row->occursin(".registry.",row["first_path"]),report["storage"])
    @test report["combined_summarysize_bytes"]==Base.summarysize((;registry,matrix);exclude=SOCCoreMemory._SKIP)
end

@testset "Incremental observer runs outside samples and preserves failures" begin
    calls=Ref(0);rows=Int[]
    result=measure_operation(()->(calls[]+=1);consume=identity,on_sample=r->push!(rows,length(r["samples"])))
    @test calls[]==6 && rows==collect(0:5)
    calls[]=0
    failure=try
        measure_operation(()->(calls[]+=1);consume=identity,on_sample=r->length(r["samples"])==2 && error("synthetic disk failure"))
        nothing
    catch error
        error
    end
    @test calls[]==3
    @test failure isa MeasurementFailure
    @test failure.partial_report["status"]=="FAIL"
    @test failure.partial_report["completed_samples"]==2
    @test length(failure.partial_report["samples"])==2
    @test occursin("synthetic disk failure",sprint(showerror,failure))
end
