"""Serial contiguous component buffers plus staged output, no lifted dense matrix."""
mutable struct ComponentWorkspace
    spatial_input::Matrix{ComplexF64}
    spatial_output::Matrix{ComplexF64}
    candidate::Matrix{ComplexF64}
    ncomp::Int
    action_calls::Int
    action_columns::Int
    scalar_calls::Int
    scalar_columns::Int
end
function ComponentWorkspace(max_ng,max_rhs,ncomp)
    ng=_positive(max_ng,"Spatial capacity");b=_positive(max_rhs,"RHS capacity");n=_positive(ncomp,"Component count")
    ComponentWorkspace(Matrix{ComplexF64}(undef,ng,b),Matrix{ComplexF64}(undef,ng,b),
        Matrix{ComplexF64}(undef,n*ng,b),n,0,0,0,0)
end
workspace_stats(ws::ComponentWorkspace)=(;ws.action_calls,ws.action_columns,ws.scalar_calls,ws.scalar_columns)
function reset_workspace_counters!(ws::ComponentWorkspace)
    ws.action_calls=ws.action_columns=ws.scalar_calls=ws.scalar_columns=0;ws
end
"""
Apply a trusted synchronous scalar mul! callback to every component. It must
preserve spatial input and not retain scratch. The adapter protects actual scalar
operator storage and owns its validity; this generic function does no reflection
into a callback or source authentication. Counters count successful full calls.
"""
function component_action!(Y::AbstractVecOrMat,scalar_mul!,X::AbstractVecOrMat,ncomp,
                           ws::ComponentWorkspace,alpha::Number=1,beta::Number=0)
    n=_positive(ncomp,"Component count")
    size(X,1)>0 && size(X,1)%n==0 || throw(DimensionMismatch("Rows must be divisible by component count"))
    _xy(Y,X,size(X,1));a,beta64=_scales(alpha,beta)
    iszero(beta64) || all(isfinite,Y) || throw(ArgumentError("Nonfinite beta-weighted output input"))
    ng=size(X,1)÷n;b=size(X,2)
    n==ws.ncomp && size(ws.spatial_input,1)>=ng && size(ws.spatial_input,2)>=b &&
        size(ws.spatial_output,1)>=ng && size(ws.spatial_output,2)>=b &&
        size(ws.candidate,1)>=n*ng && size(ws.candidate,2)>=b ||
        throw(DimensionMismatch("Component workspace capacity/count mismatch"))
    _protect_scratch((ws.spatial_input,ws.spatial_output,ws.candidate),(X,),(Y,))
    input=@view ws.spatial_input[1:ng,1:b];output=@view ws.spatial_output[1:ng,1:b]
    candidate=@view ws.candidate[1:n*ng,1:b];xm=reshape(X,n*ng,:)
    for component in 1:n
        for state in 1:b,g in 1:ng
            input[g,state]=xm[component+n*(g-1),state]
        end
        # Poisoning catches a callback which does not actually fill its output.
        fill!(output,ComplexF64(NaN,NaN))
        scalar_mul!(output,input)
        all(isfinite,output) || throw(ArgumentError("Scalar callback produced incomplete/nonfinite output"))
        for state in 1:b,g in 1:ng
            input[g,state]==xm[component+n*(g-1),state] || throw(ArgumentError("Scalar callback changed its input"))
            candidate[component+n*(g-1),state]=output[g,state]
        end
    end
    _publish!(Y,candidate,a,beta64)
    ws.action_calls+=1;ws.action_columns+=b;ws.scalar_calls+=n;ws.scalar_columns+=n*b
    Y
end
