"""Owned public input data. Runtime adapters may instead pass privately owned P,D.
Arrays in this struct remain mutable Julia arrays: concurrent external mutation is
unsupported; ownership is not a security sandbox. Public construction copies.
"""
struct NonlocalData{L}
    P::Matrix{ComplexF64}
    D::Matrix{ComplexF64}
    labels::L
end
function _pd(P,D)
    Base.require_one_based_indexing(P,D)
    size(P,1)>0 && size(P,2)>0 && size(D)==(size(P,2),size(P,2)) ||
        throw(DimensionMismatch("Nonempty rectangular P and column-space D required"))
    all(isfinite,P) && all(isfinite,D) || throw(ArgumentError("Nonfinite P or D"))
    # Scale first to avoid squared-norm overflow. No symmetrization or loss of
    # offdiagonal couplings; this is the existing relative Hermiticity tolerance.
    scale=max(maximum(abs,D),1.0);norm2=0.0;error2=0.0
    for j in axes(D,2),i in axes(D,1)
        a=D[i,j]/scale;b=conj(D[j,i])/scale
        norm2+=abs2(a);error2+=abs2(a-b)
    end
    sqrt(error2)<=1e-12*max(sqrt(norm2),inv(scale)) || throw(ArgumentError("D must be Hermitian; no symmetrization"))
    nothing
end
function NonlocalData(P::AbstractMatrix,D::AbstractMatrix;labels=nothing)
    _pd(P,D)
    p,d=Matrix{ComplexF64}(P),Matrix{ComplexF64}(D);_pd(p,d)
    isnothing(labels) || length(labels)==size(p,2) || throw(DimensionMismatch("One label per projector column required"))
    owned_labels=isnothing(labels) ? nothing : deepcopy(labels)
    NonlocalData{typeof(owned_labels)}(p,d,owned_labels)
end

"""One serial maximum-size workspace, shared across k and active RHS counts."""
mutable struct NonlocalWorkspace
    coefficients::Matrix{ComplexF64}
    weighted::Matrix{ComplexF64}
    candidate::Matrix{ComplexF64}
    action_calls::Int
    action_columns::Int
    expectation_calls::Int
    projected_calls::Int
end
function NonlocalWorkspace(max_rows,max_projectors,max_rhs)
    r=_positive(max_rows,"Row capacity");p=_positive(max_projectors,"Projector capacity");b=_positive(max_rhs,"RHS capacity")
    NonlocalWorkspace(Matrix{ComplexF64}(undef,p,b),Matrix{ComplexF64}(undef,p,b),
        Matrix{ComplexF64}(undef,r,b),0,0,0,0)
end
workspace_stats(ws::NonlocalWorkspace)=(;ws.action_calls,ws.action_columns,ws.expectation_calls,ws.projected_calls)
function reset_workspace_counters!(ws::NonlocalWorkspace)
    ws.action_calls=ws.action_columns=ws.expectation_calls=ws.projected_calls=0;ws
end
function _nonlocal_input(P,D,X,ws;Y=nothing)
    _pd(P,D)
    Base.require_one_based_indexing(X)
    size(X,1)==size(P,1) && size(X,2)>0 || throw(DimensionMismatch("Nonlocal orbital shape differs from P"))
    eltype(X) in (Float64,ComplexF64) && all(isfinite,X) || throw(ArgumentError("Finite Float64/ComplexF64 orbitals required"))
    r,p,b=size(P,1),size(P,2),size(X,2)
    size(ws.coefficients,1)>=p && size(ws.coefficients,2)>=b &&
        size(ws.weighted,1)>=p && size(ws.weighted,2)>=b &&
        size(ws.candidate,1)>=r && size(ws.candidate,2)>=b ||
        throw(DimensionMismatch("Nonlocal workspace capacity exceeded"))
    _protect_scratch((ws.coefficients,ws.weighted,ws.candidate),(P,D,X),isnothing(Y) ? () : (Y,))
    r,p,b
end
function _project!(P,D,X,ws,r,p,b)
    C=@view ws.coefficients[1:p,1:b];U=@view ws.weighted[1:p,1:b]
    mul!(C,adjoint(P),reshape(X,r,:))
    all(isfinite,C) || throw(ArgumentError("Nonfinite projector coefficients"))
    mul!(U,D,C)
    all(isfinite,U) || throw(ArgumentError("Nonfinite weighted projector coefficients"))
    C,U
end
function _contract!(P,D,X,ws,r,p,b)
    C,U=_project!(P,D,X,ws,r,p,b)
    result=@view ws.candidate[1:r,1:b]
    mul!(result,P,U)
    all(isfinite,result) || throw(ArgumentError("Nonfinite nonlocal result"))
    result
end
function nonlocal_action!(Y::AbstractVecOrMat,P::AbstractMatrix,D::AbstractMatrix,X::AbstractVecOrMat,
                          ws::NonlocalWorkspace,alpha::Number=1,beta::Number=0)
    _xy(Y,X,size(P,1));a,beta64=_scales(alpha,beta)
    iszero(beta64) || all(isfinite,Y) || throw(ArgumentError("Nonfinite beta-weighted output input"))
    r,p,b=_nonlocal_input(P,D,X,ws;Y)
    result=_contract!(P,D,X,ws,r,p,b)
    _publish!(Y,result,a,beta64)
    ws.action_calls+=1;ws.action_columns+=b
    Y
end
nonlocal_action!(Y,data::NonlocalData,X,ws,alpha=1,beta=0)=nonlocal_action!(Y,data.P,data.D,X,ws,alpha,beta)

function _energy_input(P,D,X,f,weight,ws)
    X isa AbstractMatrix || throw(DimensionMismatch("Energy needs a matrix of physical states"))
    _occupations(f,size(X,2))
    weight isa Real && isfinite(weight) && weight>=0 || throw(ArgumentError("Finite nonnegative spatial weight required"))
    r,p,b=_nonlocal_input(P,D,X,ws)
    for scratch in (ws.coefficients,ws.weighted,ws.candidate)
        Base.mightalias(scratch,f) && throw(ArgumentError("Occupation input overlaps workspace"))
    end
    r,p,b
end
"""Full-space occupied expectation: explicitly constructs V*X in bounded scratch."""
function nonlocal_expectation(P,D,X,f,weight,ws::NonlocalWorkspace)
    r,p,b=_energy_input(P,D,X,f,weight,ws)
    result=_contract!(P,D,X,ws,r,p,b);total=0.0
    for n in 1:b
        total+=weight*f[n]*real(dot(@view(X[:,n]),@view(result[:,n])))
    end
    isfinite(total) || throw(ArgumentError("Nonfinite nonlocal expectation"))
    ws.expectation_calls+=1;total
end
nonlocal_expectation(data::NonlocalData,X,f,weight,ws)=nonlocal_expectation(data.P,data.D,X,f,weight,ws)
"""Projector-space contraction, distinct from the full-space dot(X,V*X) route.
An explicit seed preserves one ordered accumulator across separately supplied k.
"""
function projected_nonlocal_energy(P,D,X,f,weight,ws::NonlocalWorkspace;initial_total=0.0)
    initial_total isa Real && isfinite(initial_total) || throw(ArgumentError("Finite real accumulation seed required"))
    total=Float64(initial_total)
    isfinite(total) || throw(ArgumentError("Accumulation seed overflows Float64"))
    r,p,b=_energy_input(P,D,X,f,weight,ws);C,U=_project!(P,D,X,ws,r,p,b)
    for n in 1:b,i in 1:p
        total+=weight*f[n]*real(conj(C[i,n])*U[i,n])
    end
    isfinite(total) || throw(ArgumentError("Nonfinite projected expectation"))
    ws.projected_calls+=1;total
end
projected_nonlocal_energy(data::NonlocalData,X,f,weight,ws;initial_total=0.0)=projected_nonlocal_energy(data.P,data.D,X,f,weight,ws;initial_total)
