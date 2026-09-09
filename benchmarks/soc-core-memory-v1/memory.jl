"""Measurement support only: no scientific kernel, file I/O or project lookup."""
module SOCCoreMemory

using LinearAlgebra

export measure_operation, unique_memory, MeasurementFailure

struct MeasurementFailure <: Exception
    partial_report::Dict{String,Any}
    cause
    backtrace
end
Base.showerror(io::IO, error::MeasurementFailure) =
    print(io, "Measured operation failed; completed samples retained: ", sprint(showerror, error.cause))

# Only small scalar diagnostics enter a report. Scientific arrays stay with the
# caller via last_value, never in the compact timing ledger.
function _compact(value; depth=0)
    depth <= 8 || throw(ArgumentError("Consumed diagnostics are too deeply nested"))
    if value === nothing || value isa Bool
        value
    elseif value isa Real
        isfinite(value) || throw(ArgumentError("Consumed diagnostics must be finite"))
        value
    elseif value isa Complex
        isfinite(value) || throw(ArgumentError("Consumed diagnostics must be finite"))
        Dict("real"=>real(value), "imag"=>imag(value))
    elseif value isa AbstractString || value isa Symbol
        text=string(value)
        ncodeunits(text)<=4096 || throw(ArgumentError("Consumed diagnostic text is too large"))
        text
    elseif value isa NamedTuple
        length(value)<=64 || throw(ArgumentError("Too many consumed diagnostics"))
        Dict(string(k)=>_compact(v;depth=depth+1) for (k,v) in pairs(value))
    elseif value isa Tuple
        length(value)<=64 || throw(ArgumentError("Consumed tuple is too large"))
        [_compact(v;depth=depth+1) for v in value]
    else
        throw(ArgumentError("Consume must return compact scalar/tuple diagnostics, not arrays or objects"))
    end
end

function _one_sample(f, consume, keep_value, index)
    timing = @timed begin
        try
            actual = f()
            consumed = _compact(consume(actual))
            (;ok=true, consumed, actual=keep_value ? actual : nothing, cause=nothing, backtrace=nothing)
        catch error
            (;ok=false, consumed=nothing, actual=nothing, cause=error, backtrace=catch_backtrace())
        end
    end
    record=Dict{String,Any}(
        "index"=>index, "status"=>timing.value.ok ? "PASS" : "FAIL",
        "time_seconds"=>timing.time, "allocated_bytes"=>timing.bytes,
        "gc_seconds"=>timing.gctime, "compile_seconds"=>timing.compile_time,
        "recompile_seconds"=>timing.recompile_time, "lock_conflicts"=>timing.lock_conflicts,
        "gcstats"=>Dict(string(k)=>getproperty(timing.gcstats,k) for k in propertynames(timing.gcstats)),
        "consumed"=>timing.value.consumed)
    if !timing.value.ok
        record["error_type"]=string(typeof(timing.value.cause))
        record["reason"]=sprint(showerror,timing.value.cause)
    end
    (;record, timing.value.actual, timing.value.cause, timing.value.backtrace)
end

function _statistics(samples)
    fields=("time_seconds","allocated_bytes","gc_seconds","compile_seconds","recompile_seconds","lock_conflicts")
    Dict(field=>begin
        values=sort([r[field] for r in samples])
        Dict("median"=>values[3],"min"=>first(values),"max"=>last(values))
    end for field in fields)
end

"""
    measure_operation(f; consume, name="operation", warmup=1, samples=5)

Call f exactly once for warmup and five times for measurement. consume and compact
validation are inside the same timed region on each call. No separate allocation
probe, GC request, serialization or numeric warmup is performed. Only the final
measured value is returned; prior outputs are not retained by the ledger.

On error stop immediately and throw MeasurementFailure containing partial_report,
including the failed measured sample and all preceding records. A caller must
persist that failure; this helper never turns an exception into a successful run.
"""
function measure_operation(f; consume, name="operation", warmup=1, samples=5,on_sample=(report)->nothing)
    warmup isa Integer && !(warmup isa Bool) && warmup==1 ||
        throw(ArgumentError("The frozen contract requires exactly one warmup"))
    samples isa Integer && !(samples isa Bool) && samples==5 ||
        throw(ArgumentError("The frozen contract requires exactly five measured samples"))
    report=Dict{String,Any}("schema_version"=>1,"operation"=>string(name),"status"=>"RUNNING",
        "warmup_count"=>1,"requested_samples"=>5,"samples"=>Dict{String,Any}[],
        "consume_policy"=>"Caller consume plus compact finite validation is included in every timed call; no output serialization, file I/O, forced GC or extra allocation probe by this helper",
        "allocation_scope"=>"Cumulative Julia allocations, not live storage or native/RSS peak",
        "warmup_scope"=>"Recorded separately; not included in warmed statistics")
    first=_one_sample(f,consume,false,0)
    report["warmup"]=first.record
    notify_sample()=try
        on_sample(report)  # Optional persistence outside every measured operation.
    catch error
        report["status"]="FAIL"
        report["completed_samples"]=count(s->s["status"]=="PASS",report["samples"])
        throw(MeasurementFailure(report,error,catch_backtrace()))
    end
    notify_sample()
    if first.cause!==nothing
        report["status"]="FAIL";report["completed_samples"]=0
        throw(MeasurementFailure(report,first.cause,first.backtrace))
    end
    last_value=nothing
    for index in 1:5
        sample=_one_sample(f,consume,index==5,index)
        push!(report["samples"],sample.record)
        notify_sample()
        if sample.cause!==nothing
            report["status"]="FAIL";report["completed_samples"]=index-1
            throw(MeasurementFailure(report,sample.cause,sample.backtrace))
        end
        index==5 && (last_value=sample.actual)
    end
    report["statistics"]=_statistics(report["samples"])
    report["completed_samples"]=5;report["status"]="PASS"
    (;report,last_value)
end

const _SKIP = Union{Module,DataType,UnionAll,Method,Core.MethodInstance,Core.CodeInfo,GlobalRef}
const _PARENT_WRAPPER = Union{SubArray,Base.ReshapedArray,Base.ReinterpretArray,
    Adjoint,Transpose,Hermitian,Symmetric,UpperTriangular,LowerTriangular,
    UnitUpperTriangular,UnitLowerTriangular}

function _interval_bytes(intervals)
    isempty(intervals) && return 0
    ordered=sort(intervals;by=first)
    total=UInt(0);left,right=first(ordered)
    for (a,b) in Iterators.drop(ordered,1)
        if a<=right
            right=max(right,b)
        else
            total+=right-left;left,right=a,b
        end
    end
    Int(total+right-left)
end

"""
    unique_memory(roots; max_objects=1_000_000)

One Base.summarysize over the combined root graph plus a dense Julia storage
inventory. Uses frozen Julia Array.ref.mem / GenericMemory backing owners, and
unions their observed data intervals to avoid duplicate storage even when
separate headers share bytes. No addresses, object pointers, dictionary keys or
string contents are reported. Views retain explicit parent edges. Opaque/native
allocations are not estimated. This observation is outside numerical timing.

Callbacks/closures are traversed by fields, not called. Modules and compiler
metadata are excluded; unknown AbstractArray implementations are traversed only
by fields, never iterated (which could otherwise invoke a lazy calculation).
"""
function unique_memory(roots; max_objects=1_000_000)
    max_objects isa Integer && !(max_objects isa Bool) && max_objects>0 ||
        throw(ArgumentError("Positive object inventory limit required"))
    seen=IdDict{Any,Int}();owners=IdDict{Any,Int}()
    arrays=Dict{String,Any}[];storage=Dict{String,Any}[]
    intervals=Tuple{UInt,UInt}[];unaccounted=Dict{String,Any}[]
    array_rows=IdDict{Any,Int}();seen_memory=IdDict{Any,Bool}()
    skipped=Dict{String,Int}();opaque_pointers=Ref(0)
    function skip_type(x)
        name=string(nameof(typeof(x)));skipped[name]=get(skipped,name,0)+1
    end
    function backing(x)
        if x isa Array
            return getfield(getfield(x,:ref),:mem)
        elseif x isa Core.GenericMemory
            return x
        elseif x isa _PARENT_WRAPPER
            return backing(parent(x))
        end
        nothing
    end
    function register_owner(mem,path)
        haskey(owners,mem) && return owners[mem]
        index=length(storage)+1;owners[mem]=index
        bytes=sizeof(mem)
        if bytes>0
            pointer=Base.unsafe_convert(Ptr{Cvoid},mem)
            start=UInt(pointer);stop=start+UInt(bytes)
            stop>=start || throw(ArgumentError("Backing-storage address overflow"))
            push!(intervals,(start,stop))
        end
        push!(storage,Dict("storage_id"=>index,"first_path"=>path,
            "element_type"=>string(eltype(mem)),"allocated_elements"=>length(mem),
            "sizeof_payload_bytes"=>bytes))
        index
    end
    function walk_memory(mem,path)
        register_owner(mem,path)
        haskey(seen_memory,mem) && return
        seen_memory[mem]=true
        if !isbitstype(eltype(mem))
            for index in eachindex(mem)
                isassigned(mem,index) && visit(mem[index],path*".element[$index]")
            end
        end
    end
    function visit(x,path)
        if x isa _SKIP
            skip_type(x);return nothing
        elseif x isa Ptr
            opaque_pointers[]+=1;return nothing
        elseif x===nothing || x isa Number || x isa Symbol || x isa AbstractString || isbitstype(typeof(x))
            return nothing
        end
        if haskey(seen,x)
            if haskey(array_rows,x)
                row=arrays[array_rows[x]];row["additional_alias_paths"]+=1
                length(row["alias_path_examples"])<4 && push!(row["alias_path_examples"],path)
            end
            return seen[x]
        end
        length(seen)<max_objects || throw(ArgumentError("Memory inventory object limit exceeded; no partial census declared complete"))
        id=length(seen)+1;seen[x]=id
        if x isa Core.GenericMemory
            walk_memory(x,path)
        elseif x isa Array || x isa _PARENT_WRAPPER || x isa AbstractArray
            mem=backing(x)
            row=Dict{String,Any}("object_id"=>id,"first_path"=>path,
                "array_type"=>string(nameof(typeof(x))),"element_type"=>string(eltype(x)),
                "shape"=>(x isa Array || x isa _PARENT_WRAPPER) ? collect(size(x)) : nothing,"additional_alias_paths"=>0,"alias_path_examples"=>String[],
                "storage_id"=>mem===nothing ? nothing : register_owner(mem,path),"parent_object_id"=>nothing)
            push!(arrays,row);array_rows[x]=length(arrays)
            if x isa Array
                walk_memory(mem,path*".backing")
            elseif x isa _PARENT_WRAPPER
                row["parent_object_id"]=visit(parent(x),path*".parent")
                # Index vectors can own storage as well as the viewed parent.
                for field in fieldnames(typeof(x))
                    isdefined(x,field) && visit(getfield(x,field),path*"."*string(field))
                end
            else
                push!(unaccounted,Dict("path"=>path,"type"=>string(nameof(typeof(x))),
                    "reason"=>"Unknown AbstractArray backing; only fields traversed, no native or lazy value evaluation"))
                for field in fieldnames(typeof(x))
                    isdefined(x,field) && visit(getfield(x,field),path*"."*string(field))
                end
            end
        elseif x isa AbstractDict
            # Traverse retained table fields, including Dict keys/values and
            # IdDict backing arrays. Iterating pairs alone would omit the table
            # capacity and can invoke arbitrary custom dictionary code.
            for field in fieldnames(typeof(x))
                isdefined(x,field) && visit(getfield(x,field),path*"."*string(field))
            end
        elseif x isa Tuple || x isa NamedTuple
            for field in fieldnames(typeof(x))
                isdefined(x,field) && visit(getfield(x,field),path*"."*string(field))
            end
        else
            for field in fieldnames(typeof(x))
                isdefined(x,field) && visit(getfield(x,field),path*"."*string(field))
            end
        end
        id
    end
    # The roots and owner dictionaries remain strongly reachable while pointers
    # are inspected; raw addresses are discarded and never become public IDs.
    GC.@preserve roots owners begin
        visit(roots,"roots")
        summary=Base.summarysize(roots;exclude=_SKIP)
        raw=sum((r["sizeof_payload_bytes"] for r in storage);init=0)
        unique=_interval_bytes(intervals)
        Dict{String,Any}("schema_version"=>1,"status"=>isempty(unaccounted) ? "COMPLETE_FOR_RECOGNIZED_JULIA_STORAGE" : "PARTIAL_UNKNOWN_ARRAY_STORAGE",
            "combined_summarysize_bytes"=>summary,"dense_unique_payload_bytes"=>unique,
            "backing_owner_payload_sum_bytes"=>raw,"overlap_payload_bytes"=>raw-unique,
            "reachable_objects"=>length(seen),"array_objects"=>length(arrays),"backing_owners"=>length(storage),
            "arrays"=>arrays,"storage"=>storage,"unaccounted_arrays"=>unaccounted,
            "skipped_metadata_types"=>skipped,"opaque_pointer_fields"=>opaque_pointers[],
            "scope"=>"One combined Julia root summary and recognized backing-storage payload; not cumulative allocations, native malloc, JIT memory or process RSS",
            "storage_identity"=>"Actual Array.ref.mem / GenericMemory owner identity; union of backing data intervals, no addresses published",
            "view_policy"=>"Whole retained parent allocation counted once; view logical elements are not added again")
    end
end

end
