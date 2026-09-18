"""Scalar-only cooperative request checks for the explicitly enabled timing workers."""
module SocTimingControl
using TOML, SHA
const D = Main.WorkbenchDiagnostics
export State, load_control, boundary!, summary

mutable struct State
    directory::String
    config::Dict{String,Any}
    config_bytes::Vector{UInt8}
    control_sha256::String
    request::Union{Nothing,Dict{String,Any}}
    request_sha256::Union{Nothing,String}
    ack::Union{Nothing,Dict{String,Any}}
    last_boundary::String
    highwater_bytes::Int
end

function safe_read(path)
    dir=dirname(path)
    abspath(dir)==realpath(dir) && !islink(dir) && !islink(path) || error("Control path alias refused")
    isfile(path) && filesize(path)<=65536 || error("Control file missing/too large")
    read(path)
end

function atomictoml(path,data)
    # Own independent process-specific temporary; no array or runtime references.
    tmp=path*".tmp-"*string(getpid())
    ispath(tmp) && error("Unfinished control temporary already exists")
    open(tmp,"w") do io
        TOML.print(io,data;sorted=true)
    end
    mv(tmp,path;force=true)
    nothing
end

function load_control(directory;expected_run_id,expected_execution_commit,
                      expected_source_commit,expected_task_id,expected_case_sha256)
    dir=abspath(directory)
    dir==realpath(dir) && !islink(dir) || error("Run directory alias refused")
    raw=safe_read(joinpath(dir,"control.toml"));c=TOML.parse(String(copy(raw)))
    get(c,"schema_version",nothing)===1 && get(c,"run_id",nothing)==basename(dir) &&
        get(c,"worker_id",nothing)=="worker" || error("Control schema/directory differs")
    for (key,expected) in (("run_id",expected_run_id),("execution_commit",expected_execution_commit),
        ("source_commit",expected_source_commit),("task_id",expected_task_id),("case_sha256",expected_case_sha256))
        get(c,key,nothing)==expected || error("Control identity differs: "*key)
    end
    (get(c,"limit_bytes",0),get(c,"warning_bytes",0),get(c,"remaining_growth_bytes",0))==
        (8*1024^3,7*1024^3,2*1024^3) || error("Timing control cannot alter8/7 GiB or2 GiB headroom")
    if !get(c,"synthetic",false)
        get(c,"task_id",nothing) in ("T-B0-REF","T-B0-TIMED","T-K4-TIMED",
            "V-B0-REF","V-B0-OPT","V-K4-REF","V-K4-OPT") || error("Unregistered real task")
        (c["grace_seconds"],c["term_seconds"],c["kill_seconds"])==(120,10,5) || error("Real escalation budget changed")
        if startswith(c["task_id"],"V-")
            ref=endswith(c["task_id"],"-REF")
            get(c,"experiment",nothing)=="soc-boundary-v1" && get(c,"timing_enabled",nothing)===true &&
                get(c,"validation_policy",nothing)==(ref ? "strict" : "single_validation_v1") ||
                error("Boundary control policy changed")
            c["source_commit"]==(ref ? "d9e19af3557c923a1e4f7e64510092d47975cc7c" : c["execution_commit"]) ||
                error("Boundary control numerical version changed")
            c["budget_seconds"]==(startswith(c["task_id"],"V-B0-") ? 900 : 1800) || error("Boundary task budget changed")
            get(c,"protection_gate_sha256",nothing) isa String &&
                occursin(r"^[a-f0-9]{64}$",c["protection_gate_sha256"]) || error("Boundary protection receipt missing")
        end
    else
        startswith(c["task_id"],"SYNTHETIC-") || error("Synthetic task identity differs")
    end
    State(dir,c,raw,bytes2hex(sha256(raw)),nothing,nothing,nothing,"",0)
end

native_highwater_bytes()=Int(Sys.maxrss())

function boundary!(s::State,event,map_index=0,k_index=0;propagate=true)
    # This function is only called at coarse safe boundaries, never inside matvec/FFT.
    safe_read(joinpath(s.directory,"control.toml"))==s.config_bytes || error("Control changed during worker")
    s.last_boundary=String(event)
    # Julia1.12.7 Sys.maxrss is already bytes on every platform (base/sysinfo.jl).
    high=native_highwater_bytes()
    s.highwater_bytes=max(s.highwater_bytes,high)
    highwater=Dict{String,Any}("schema_version"=>1,"run_id"=>s.config["run_id"],
        "execution_commit"=>s.config["execution_commit"],"control_sha256"=>s.control_sha256,
        "highwater_bytes"=>s.highwater_bytes,"units"=>"bytes","event"=>String(event),
        "reported_unix_ns"=>round(Int,time()*1e9))
    atomictoml(joinpath(s.directory,"resource-highwater.toml"),highwater)
    path=joinpath(s.directory,"stop-request.toml")
    islink(path) && error("Linked stop request refused")
    if !ispath(path)
        isnothing(s.request_sha256) || error("Latched stop request removed")
        return nothing
    end
    raw=safe_read(path);r=TOML.parse(String(copy(raw)));digest=bytes2hex(sha256(raw))
    get(r,"schema_version",nothing)===1 || error("Stop schema invalid")
    for key in ("run_id","execution_commit","source_commit","nonce")
        get(r,key,nothing)==s.config[key] || error("Stop request belongs to another run: "*key)
    end
    get(r,"control_sha256",nothing)==s.control_sha256 || error("Stop control hash mismatch")
    reason=get(r,"reason",nothing)
    reason in ("USER_CANCELLED","TIME_BUDGET_EXCEEDED","RESOURCE_LIMIT","RESOURCE_HEADROOM","HOST_PRESSURE") || error("Undeclared stop reason")
    stamp=get(r,"requested_unix_ns",nothing);now=round(Int,time()*1e9)
    stamp isa Integer && !(stamp isa Bool) && typemin(Int)<=stamp<=typemax(Int) && s.config["created_unix_ns"]<=stamp<=now+10^9 || error("Stale/future stop request")
    get(r,"request_id",nothing) isa String && occursin(r"^[a-f0-9]{32}$",r["request_id"]) || error("Bad request id")
    if isnothing(s.request_sha256)
        s.request=r;s.request_sha256=digest
        s.ack=Dict{String,Any}("schema_version"=>1,"run_id"=>s.config["run_id"],
            "execution_commit"=>s.config["execution_commit"],"control_sha256"=>s.control_sha256,
            "request_sha256"=>digest,"request_id"=>r["request_id"],"reason"=>reason,
            "requested_unix_ns"=>stamp,"acknowledged_unix_ns"=>now,"boundary"=>String(event),
            "map_index"=>map_index,"k_index"=>k_index)
        ispath(joinpath(s.directory,"stop-ack.toml")) && error("Stop acknowledgment already exists before first observation")
        atomictoml(joinpath(s.directory,"stop-ack.toml"),s.ack)
    else
        s.request_sha256==digest || error("First stop request bytes changed")
    end
    propagate && throw(D.ControlledStop(reason;request_id=r["request_id"],boundary=event,map_index,k_index))
    nothing
end

function summary(s::State)
    Dict{String,Any}("control_sha256"=>s.control_sha256,"stop_request"=>s.request,
        "first_request_sha256"=>s.request_sha256,"ack"=>s.ack,"last_boundary"=>s.last_boundary,
        "first_request_id"=>(isnothing(s.request) ? nothing : s.request["request_id"]),
        "stop_reason"=>(isnothing(s.request) ? nothing : s.request["reason"]),
        "requested_unix_ns"=>(isnothing(s.request) ? nothing : s.request["requested_unix_ns"]),
        "acknowledged_unix_ns"=>(isnothing(s.ack) ? nothing : s.ack["acknowledged_unix_ns"]),
        "acknowledged_boundary"=>(isnothing(s.ack) ? nothing : s.ack["boundary"]))
end
end
