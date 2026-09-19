module ValidationLocalObserver

# Diagnostic shadow only. Never include/install this in a performance process.
# The original files remain untouched; every replacement is returned for review.
using SHA, Serialization
export install_observer!, start_trace!, finish_trace!, observer_manifest, clear_observer!

mutable struct Observer
    role::String
    source_root::String
    enabled::Bool
    operation::String
    position::Tuple{String,String,Union{Nothing,Int}}
    objects::IdDict{Any,Int}
    hashed::IdDict{Any,Int}
    events::Vector{Dict{String,Any}}
    methods::Dict{String,Any}
    pending::Union{Nothing,Dict{String,Any}}
    deferred::Int
    max_events::Int
    patches::Vector{Dict{String,Any}}
end

function object_id!(o,a)
    get!(()->length(o.objects)+1,o.objects,a)
end
function source_location(o,m)
    file=String(m.file); located=Base.find_source_file(file)
    path=isnothing(located) ? file : located
    public=startswith(path,o.source_root*"/") ? relpath(path,o.source_root) :
        occursin("/share/julia/",path) ? "<JULIA>/"*split(path,"/share/julia/";limit=2)[2] : basename(path)
    Dict("file"=>public,"line"=>Int(m.line),"signature"=>string(m.sig),
         "file_sha256"=>isfile(path) ? bytes2hex(sha256(read(path))) : nothing)
end
function method!(o,name,f,args)
    key=name*"|"*string(args)
    haskey(o.methods,key) && return key
    o.methods[key]=merge(source_location(o,which(f,args)),Dict("function"=>name,"argument_types"=>string(args)))
    key
end

# Shallow identities only. Unknown methods are not invoked merely for metadata.
function metadata!(o,a)
    parent_object=if a isa SubArray || a isa Base.ReshapedArray || a isa Base.ReinterpretArray
        getfield(a,:parent)
    else
        nothing
    end
    owner=a isa Array ? getfield(getfield(a,:ref),:mem) : nothing
    reliable=a isa Array || (a isa SubArray && parent_object isa Array)
    stride=reliable ? collect(strides(a)) : nothing
    section,label,k=o.position
    Dict{String,Any}("section"=>section,"label"=>label,"k_index"=>k,
        "object_id"=>object_id!(o,a),"type"=>string(typeof(a)),"eltype"=>string(eltype(a)),
        "shape"=>collect(size(a)),"strides"=>stride,
        "strides_status"=>reliable ? "OBSERVED_STANDARD_LAYOUT" : "NOT_QUERIED_UNKNOWN_METHOD",
        "parent_type"=>isnothing(parent_object) ? nothing : string(typeof(parent_object)),
        "parent_id"=>isnothing(parent_object) ? nothing : object_id!(o,parent_object),
        "array_memory_owner_id"=>isnothing(owner) ? nothing : object_id!(o,owner))
end
function emit!(o,event)
    o.enabled || return
    length(o.events)<o.max_events || error("Diagnostic event cap exceeded; no truncation permitted")
    event["sequence"]=length(o.events)+1
    event["operation"]=o.operation
    push!(o.events,event)
end
function with_position(f,o,section,label,k)
    prior=o.position;o.position=(String(section),String(label),k)
    try f() finally o.position=prior end
end
function storage_position!(o,label)
    parts=split(label,'/');k=tryparse(Int,first(parts))
    o.position=(isnothing(k) ? "derived_storage" : "current_storage",String(label),k)
    nothing
end

function bytes!(o,a,copy_first)
    if !o.enabled
        return reinterpret(UInt8,vec(copy_first ? copy(a) : a))
    end
    event=metadata!(o,a);event["kind"]="array"
    event["branch"]=copy_first ? (o.role=="F" ? "fallback" : "copy_hash") : "canonical_hash"
    event["prior_hashes_same_key"]=get(o.hashed,a,0)
    methods=String[]
    if copy_first
        push!(methods,method!(o,"copy",copy,Tuple{typeof(a)}))
        if a isa SubArray
            p=getfield(a,:parent);inds=getfield(a,:indices)
            push!(methods,method!(o,"copy_parent_getindex",getindex,Tuple{typeof(p),map(typeof,inds)...}))
        end
    end
    t=time_ns();copied=copy_first ? copy(a) : a;event["copy_ns"]=copy_first ? Int(time_ns()-t) : nothing
    event["copy_status"]=copy_first ? "EXECUTED_ORIGINAL_EXPRESSION" : "NOT_EXECUTED"
    push!(methods,method!(o,"vec",vec,Tuple{typeof(copied)}))
    t=time_ns();v=vec(copied);event["vec_ns"]=Int(time_ns()-t)
    push!(methods,method!(o,"reinterpret",reinterpret,Tuple{Type{UInt8},typeof(v)}))
    t=time_ns();bytes=reinterpret(UInt8,v);event["reinterpret_ns"]=Int(time_ns()-t)
    push!(methods,method!(o,"sha256",SHA.sha256,Tuple{typeof(bytes)}))
    # These method selections are queried from actual observed byte-container
    # types and the frozen SHA context fields, without another SHA execution.
    counter=fieldtype(SHA.SHA256_CTX,:bytecount);buffer=fieldtype(SHA.SHA256_CTX,:buffer)
    push!(methods,method!(o,"sha_buffer_copyto_type_query",copyto!,Tuple{buffer,counter,typeof(bytes),counter,counter}))
    push!(methods,method!(o,"byte_getindex_type_query",getindex,Tuple{typeof(bytes),Int}))
    event["copy_result_type"]=string(typeof(copied));event["vec_result_type"]=string(typeof(v))
    event["bytes_type"]=string(typeof(bytes));event["input_bytes"]=length(bytes)
    event["method_keys"]=methods;event["method_query_scope"]="Observed intermediate types; SHA-internal copy/index selections are source-supported type queries, not call counts"
    o.pending=event
    bytes
end
function digest!(o,a,bytes)
    t=time_ns();digest=bytes2hex(SHA.sha256(bytes));elapsed=Int(time_ns()-t)
    if o.enabled
        isnothing(o.pending) && error("Diagnostic digest has no matching original bytes")
        o.pending["digest"]=digest;o.pending["sha_and_hex_ns"]=elapsed
        o.hashed[a]=get(o.hashed,a,0)+1
        # Emit at the actual hash completion, before a fallback finally clears
        # its memo. The enclosing helper fills memo-after fields on this row.
        emit!(o,o.pending)
    end
    digest
end
function hash!(o,a)
    b=bytes!(o,a,true);value=digest!(o,a,b)
    if o.enabled && o.deferred==0
        o.pending=nothing
    end
    value
end
function strict_gethash!(o,f,hashes,a)
    o.enabled || return get!(f,hashes,a)
    before=length(hashes);hit=haskey(hashes,a);o.deferred+=1
    try
        value=get!(f,hashes,a) # Original get! and callback, exactly once.
        event=hit ? merge(metadata!(o,a),Dict("kind"=>"array","branch"=>"reuse",
            "digest"=>value,"input_bytes"=>0,"prior_hashes_same_key"=>get(o.hashed,a,0))) : o.pending
        isnothing(event) && error("Missing observed strict hash")
        o.pending=nothing
        event["memo_before"]=before;event["memo_after"]=length(hashes)
        event["memo_scope"]="original_check_storage_local_IdDict"
        hit && emit!(o,event)
        value
    finally
        o.deferred-=1;o.pending=nothing
    end
end
function empty_memo!(o,memo,reason)
    before=length(memo.arrays);empty!(memo.arrays)
    o.enabled && emit!(o,Dict{String,Any}("kind"=>"memo_invalidation","reason"=>reason,
        "memo_before"=>before,"memo_after"=>length(memo.arrays),"source_memo_entries"=>length(memo.sources),
        "section"=>o.position[1],"label"=>o.position[2]))
    nothing
end
function candidate_hash!(o,f,memo,a)
    o.enabled || return f(memo,a)
    before=length(memo.arrays);o.deferred+=1
    try
        value=f(memo,a)
        hit=isnothing(o.pending)
        event=hit ? merge(metadata!(o,a),Dict("kind"=>"array","branch"=>"reuse",
            "digest"=>value,"input_bytes"=>0,"prior_hashes_same_key"=>get(o.hashed,a,0))) : o.pending
        o.pending=nothing
        event["memo_before"]=before;event["memo_after"]=length(memo.arrays)
        event["memo_scope"]="single_validation_v1_call_local"
        hit && emit!(o,event)
        value
    finally
        o.deferred-=1;o.pending=nothing
    end
end
function snapshot!(o,x)
    if !o.enabled
        io=IOBuffer();Serialization.serialize(io,x);return bytes2hex(sha256(take!(io)))
    end
    t=time_ns();io=IOBuffer();Serialization.serialize(io,x);serialization=Int(time_ns()-t)
    t=time_ns();bytes=take!(io);take_time=Int(time_ns()-t)
    t=time_ns();value=bytes2hex(sha256(bytes));hash_time=Int(time_ns()-t)
    emit!(o,Dict{String,Any}("kind"=>"source_snapshot","section"=>o.position[1],"label"=>o.position[2],
        "type"=>string(typeof(x)),"object_id"=>object_id!(o,x),"input_bytes"=>length(bytes),"digest"=>value,
        "serialization_ns"=>serialization,"take_bytes_ns"=>take_time,"sha_and_hex_ns"=>hash_time))
    value
end

function start_trace!(o::Observer,operation::AbstractString;max_events=2000)
    !o.enabled && o.deferred==0 || error("Observer already tracing")
    isempty(o.objects) && isempty(o.hashed) || error("Observer retains previous object references")
    empty!(o.events);empty!(o.methods);o.pending=nothing
    o.operation=String(operation);o.position=("unclassified","unclassified",nothing)
    o.max_events=Int(max_events);o.enabled=true;o
end
function finish_trace!(o::Observer)
    o.enabled && o.deferred==0 || error("Observer is not at a completed synchronous trace boundary")
    o.enabled=false
    result=Dict{String,Any}("schema_version"=>1,"role"=>o.role,"operation"=>o.operation,
        "scope"=>"INSTRUMENTED_DIAGNOSTIC_NOT_MAIN_TIMING","events"=>copy(o.events),"methods"=>copy(o.methods),
        "object_id_scope"=>"Process-local sequential IdDict/=== keys, not memory addresses or construction counts",
        "array_hash_calls"=>count(e->e["kind"]=="array" && e["branch"]!="reuse",o.events),
        "array_hash_bytes"=>sum((get(e,"input_bytes",0) for e in o.events if e["kind"]=="array");init=0),
        "source_hash_calls"=>count(e->e["kind"]=="source_snapshot",o.events),
        "source_hash_bytes"=>sum((get(e,"input_bytes",0) for e in o.events if e["kind"]=="source_snapshot");init=0),
        "array_reuses"=>count(e->e["kind"]=="array" && e["branch"]=="reuse",o.events),
        "memo_invalidations"=>count(e->e["kind"]=="memo_invalidation" && e["reason"]=="fallback_before",o.events),
        "memo_clear_operations"=>count(e->e["kind"]=="memo_invalidation",o.events),
        "nonempty_memo_clears"=>count(e->e["kind"]=="memo_invalidation" && e["memo_before"]>0,o.events))
    empty!(o.objects);empty!(o.hashed);empty!(o.events);empty!(o.methods);o.pending=nothing
    result["observer_live_object_entries_after_finish"]=length(o.objects)
    result
end
observer_manifest(o::Observer)=Dict("schema_version"=>1,"role"=>o.role,
    "scope"=>"INSTRUMENTED_DIAGNOSTIC_NOT_MAIN_TIMING","patches"=>copy(o.patches),
    "array_hash_expression"=>"bytes2hex(SHA.sha256(reinterpret(UInt8,vec(copy(a)))))",
    "source_hash_expression"=>"IOBuffer; Serialization.serialize; take!; bytes2hex(sha256)",
    "unknown_metadata_policy"=>"No arbitrary parent/strides calls; no extra content reads, copies or hashes for counting",
    "timing_scope"=>"Diagnostic substep wall samples include compilation/dispatch and observer perturbation; not performance samples")
function clear_observer!(o::Observer)
    o.deferred==0 || error("Cannot clear an observer during a hash callback")
    o.enabled=false;o.pending=nothing;empty!(o.objects);empty!(o.hashed)
    empty!(o.events);empty!(o.methods)
    Dict("status"=>"CLEARED","live_object_entries"=>length(o.objects),"live_hash_entries"=>length(o.hashed))
end

function one_function(text,anchor)
    hits=findall(anchor,text);length(hits)==1 || error("Observer source anchor is not unique: $anchor")
    start=first(only(hits));_,after=Meta.parse(text,start;greedy=true,raise=true)
    text[start:prevind(text,after)]
end
function replace_exact(text,old,new;n=1)
    length(findall(old,text))==n || error("Observer replacement mismatch: $old")
    replace(text,old=>new)
end
function install_observer!(FI::Module,role::AbstractString,source_root::AbstractString)
    role in ("S","F") || error("Only frozen S/F diagnostics are supported")
    isdefined(FI,:_LOCAL_VALIDATION_OBSERVER) && error("Observer already installed")
    root=realpath(source_root)
    o=Observer(String(role),root,false,"",("unclassified","unclassified",nothing),IdDict{Any,Int}(),
        IdDict{Any,Int}(),Dict{String,Any}[],Dict{String,Any}(),nothing,0,2000,Dict{String,Any}[])
    ham=read(joinpath(root,"prototypes/fr_integration/hamiltonian.jl"),String)
    runtime=read(joinpath(root,"prototypes/fr_integration/runtime.jl"),String)
    common=read(joinpath(root,"prototypes/fr_integration/common_data.jl"),String)
    hook="_LOCAL_PROBE";obs="_LOCAL_VALIDATION_OBSERVER"
    patches=Tuple{String,String,String}[]
    original="_fr_array_hash(a) = bytes2hex(SHA.sha256(reinterpret(UInt8, vec(copy(a)))))"
    length(findall(original,ham))==1 || error("Original array hash expression changed")
    push!(patches,("hamiltonian.jl",original,"_fr_array_hash(a) = $hook.hash!($obs,a)"))
    original=one_function(common,"function _source_snapshot(x)")
    push!(patches,("common_data.jl",original,"_source_snapshot(x) = $hook.snapshot!($obs,x)"))
    original=one_function(common,"function _assert_bound_sources(bundle::BoundPspBundle,entry;")
    patched=original
    for kind in ("common","channels","bundle.parsed")
        patched=replace_exact(patched,"_source_snapshot($kind)",
            "$hook.with_position(()->_source_snapshot($kind),$obs,\"source\",\"$kind\",nothing)")
    end
    push!(patches,("common_data.jl",original,patched))
    original=one_function(ham,role=="S" ? "function validate_context(ctx)" : "function _validate_context(ctx,memo)")
    patched=original
    for kind in ("P","D")
        call=role=="S" ? "_fr_array_hash(op.$kind)" : "_validation_array_hash(memo,op.$kind)"
        patched=replace_exact(patched,call,"$hook.with_position(()->$call,$obs,\"P/D\",\"$kind/\$ik\",ik)")
    end
    push!(patches,("hamiltonian.jl",original,patched))
    original=one_function(runtime,"function _check_storage(certificate,arrays)")
    patched=replace_exact(original,"for (saved,(label,array)) in zip(certificate,arrays)",
        "for (saved,(label,array)) in zip(certificate,arrays)\n        $hook.storage_position!($obs,label)")
    patched=replace_exact(patched,"get!(()->_fr_array_hash(array),hashes,array)",
        "$hook.strict_gethash!($obs,()->_fr_array_hash(array),hashes,array)")
    push!(patches,("runtime.jl",original,patched))
    if role=="F"
        original=one_function(runtime,"function _check_storage(certificate,arrays,memo::_ValidationMemo)")
        patched=replace_exact(original,"for (saved,(label,array)) in zip(certificate,arrays)",
            "for (saved,(label,array)) in zip(certificate,arrays)\n        $hook.storage_position!($obs,label)")
        push!(patches,("runtime.jl",original,patched))
        original=one_function(ham,"function _validation_array_hash(memo::_ValidationMemo,a)")
        patched=replace_exact(original,"function _validation_array_hash(memo::_ValidationMemo,a)",
            "function _local_original_validation_array_hash(memo::_ValidationMemo,a)")
        patched=replace_exact(patched,"bytes=reinterpret(UInt8,vec(a))","bytes=$hook.bytes!($obs,a,false)")
        patched=replace_exact(patched,"bytes=reinterpret(UInt8,vec(copy(a)))","bytes=$hook.bytes!($obs,a,true)")
        patched=replace_exact(patched,"digest=bytes2hex(SHA.sha256(bytes))","digest=$hook.digest!($obs,a,bytes)";n=2)
        patched=replace_exact(patched,"empty!(memo.arrays);counts[\"fallback_memo_invalidations\"]+=1",
            "$hook.empty_memo!($obs,memo,\"fallback_before\");counts[\"fallback_memo_invalidations\"]+=1")
        patched=replace_exact(patched,"        empty!(memo.arrays)","        $hook.empty_memo!($obs,memo,\"fallback_finally\")")
        patched*="\n_validation_array_hash(memo::_ValidationMemo,a) = $hook.candidate_hash!($obs,_local_original_validation_array_hash,memo,a)\n"
        push!(patches,("hamiltonian.jl",original,patched))
    end
    # Validate all source transformations before evaluating any method changes.
    for (file,original,patched) in patches
        Meta.parseall(patched)
        push!(o.patches,Dict("file"=>"prototypes/fr_integration/"*file,"original"=>original,"instrumented"=>patched,
            "source_file_sha256"=>bytes2hex(sha256(read(joinpath(root,"prototypes/fr_integration",file)))),
            "original_definition_sha256"=>bytes2hex(sha256(original)),"instrumented_definition_sha256"=>bytes2hex(sha256(patched))))
    end
    Core.eval(FI,:(const _LOCAL_PROBE = $(@__MODULE__)))
    Core.eval(FI,:(const _LOCAL_VALIDATION_OBSERVER = $o))
    for (_,_,patched) in patches
        Base.include_string(FI,patched,"INSTRUMENTED_DIAGNOSTIC/observe.jl")
    end
    o
end

end
