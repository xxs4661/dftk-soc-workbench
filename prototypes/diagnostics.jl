"""Internal, optional run observations. No numerical objects or algorithms live here."""
module WorkbenchDiagnostics

export Session, ControlledStop, with_span, boundary!, flush!, finish!, @span

struct ControlledStop <: Exception
    reason::String
    request_id::String
    boundary::String
    map_index::Int
    k_index::Int
end
ControlledStop(reason; request_id="", boundary="", map_index=0, k_index=0) =
    ControlledStop(String(reason), String(request_id), String(boundary), Int(map_index), Int(k_index))
Base.showerror(io::IO, err::ControlledStop) =
    print(io, err.reason, " at ", err.boundary, " (map=", err.map_index, ", k=", err.k_index, ")")

mutable struct Frame
    id::Int
    parent::Int
    name::String
    map_index::Int
    k_index::Int
    start_ns::Int
    child_ns::Int
end

"""One serial session; its clock and boundary hook must capture scalar control state only."""
mutable struct Session{C,H}
    run_id::String
    pid::Int
    enabled::Bool
    clock::C
    boundary_hook::H
    origin::UInt64
    last_offset::Int
    next_id::Int
    stack::Vector{Frame}
    rows::Vector{NamedTuple}
    max_rows::Int
    finished::Bool
end

function Session(run_id; enabled=false, clock=time_ns,
                 boundary_hook=(event,map_index,k_index)->nothing, max_rows=20000)
    enabled isa Bool || throw(ArgumentError("Timing enabled must be Boolean"))
    max_rows isa Integer && !(max_rows isa Bool) && max_rows>0 ||
        throw(ArgumentError("Positive bounded timing buffer required"))
    origin=enabled ? UInt64(clock()) : UInt64(0)
    Session(String(run_id),Int(getpid()),enabled,clock,boundary_hook,origin,0,1,
            Frame[],NamedTuple[],Int(max_rows),false)
end

function offset!(session::Session)
    now=UInt64(session.clock())
    # Unsigned subtraction also handles the eventual time_ns counter wrap.
    value=Int(now-session.origin)
    value>=session.last_offset || throw(ArgumentError("Diagnostic clock moved backwards"))
    session.last_offset=value
end

start_span!(::Nothing,name;map_index=0,k_index=0)=nothing
function start_span!(session::Session,name;map_index=0,k_index=0)
    session.finished && throw(ArgumentError("Diagnostic session is already finished"))
    session.enabled || return nothing
    length(session.rows)+length(session.stack)<session.max_rows ||
        throw(ArgumentError("Timing buffer full; flush at an existing safe boundary"))
    parent=isempty(session.stack) ? 0 : last(session.stack).id
    if !isempty(session.stack)
        map_index==0 && (map_index=last(session.stack).map_index)
        k_index==0 && (k_index=last(session.stack).k_index)
    end
    frame=Frame(session.next_id,parent,String(name),Int(map_index),Int(k_index),offset!(session),0)
    session.next_id+=1;push!(session.stack,frame)
    frame.id
end

end_span!(::Nothing,token,status)=nothing
function end_span!(session::Session,token,status)
    isnothing(token) && return nothing
    !isempty(session.stack) && last(session.stack).id==token ||
        throw(ArgumentError("Diagnostic spans must close in serial nesting order"))
    frame=last(session.stack);finish=offset!(session)
    elapsed=finish-frame.start_ns
    self=elapsed-frame.child_ns
    self>=0 || throw(ArgumentError("Child spans exceed parent duration"))
    pop!(session.stack)
    isempty(session.stack) || (last(session.stack).child_ns+=elapsed)
    push!(session.rows,(;run_id=session.run_id,pid=session.pid,span_id=frame.id,
        parent_span=frame.parent,name=frame.name,map_index=frame.map_index,k_index=frame.k_index,
        start_offset_ns=frame.start_ns,end_offset_ns=finish,inclusive_ns=elapsed,
        exclusive_ns=self,calls=1,status=String(status)))
    nothing
end

stop_only(err)=err isa ControlledStop
stop_only(err::CompositeException)=!isempty(err.exceptions) && all(stop_only,err.exceptions)
function close_preserving!(session,token,failure)
    status=isnothing(failure) ? "COMPLETE" :
        failure isa ControlledStop && failure.reason=="DIAGNOSTIC_MAP_LIMIT" ? "DIAGNOSTIC_COMPLETED" :
        stop_only(failure) ? "STOPPED" : "ERROR"
    try
        end_span!(session,token,status)
    catch observation_error
        isnothing(failure) && rethrow()
        throw(CompositeException([failure,observation_error]))
    end
end

function with_span(f,session,name;map_index=0,k_index=0)
    token=start_span!(session,name;map_index,k_index);failure=nothing
    try
        f()
    catch err
        failure=err;rethrow()
    finally
        close_preserving!(session,token,failure)
    end
end

"""Wrap a lexical block; declare outputs in the enclosing scope before the block."""
macro span(session,name,map_index,k_index,body)
    quote
        local token=start_span!($(esc(session)),$(esc(name));
                               map_index=$(esc(map_index)),k_index=$(esc(k_index)))
        local failure=nothing
        try
            $(esc(body))
        catch err
            failure=err
            rethrow()
        finally
            close_preserving!($(esc(session)),token,failure)
        end
    end
end

boundary!(::Nothing,event;map_index=0,k_index=0)=nothing
function boundary!(session::Session,event;map_index=0,k_index=0)
    session.finished && throw(ArgumentError("Diagnostic session is already finished"))
    if !isempty(session.stack)
        map_index==0 && (map_index=last(session.stack).map_index)
        k_index==0 && (k_index=last(session.stack).k_index)
    end
    session.boundary_hook(String(event),Int(map_index),Int(k_index))
    nothing
end

flush!(::Nothing,sink)=nothing
function flush!(session::Session,sink)
    isempty(session.rows) && return nothing
    # This is a scalar-only batch, never a numerical checkpoint. On failed write
    # retain the rows and propagate the actual error; do not publish success.
    sink(copy(session.rows))
    empty!(session.rows)
    nothing
end
finish!(::Nothing)=nothing
function finish!(session::Session)
    isempty(session.stack) || throw(ArgumentError("Unclosed diagnostic spans remain"))
    session.finished=true
    nothing
end

end
