# Explicit optimized adapters below use one stage-independent parent module.
# This happens only at module loading, never inside a numerical kernel.
if !isdefined(parentmodule(@__MODULE__), :SOCKernels)
    Base.include(parentmodule(@__MODULE__), joinpath(@__DIR__, "../../src/SOCKernels.jl"))
end
import ..SOCKernels

"""
Lift a square scalar operator to `Psi[component,G,state]`, flattened with
`row = component + ncomp*(G-1)`. The independent dense reference for this layout
is `kron(H, I_ncomp)`. No dense lifted matrix is constructed here.

Inputs and outputs of `mul!` must not alias. Each component is copied into a
contiguous spatial block before calling the existing scalar `mul!` interface.
Counters measure successful calls and columns, separately for lifted/scalar work.
This mutable prototype is intended for serial CPU use.
"""
mutable struct ComponentOperator{T,H}
    scalar::H
    ncomp::Int
    ng::Int
    operator_mul_calls::Int
    operator_columns::Int
    scalar_mul_calls::Int
    scalar_columns::Int
end

function ComponentOperator(H, ncomp::Integer)
    ncomp isa Bool && throw(ArgumentError("ncomp must be a positive integer count"))
    ncomp > 0 || throw(ArgumentError("ncomp must be positive"))
    shape = size(H)
    length(shape) == 2 && shape[1] == shape[2] ||
        throw(DimensionMismatch("The scalar operator must be square"))
    shape[1] > 0 || throw(ArgumentError("The spatial basis must be nonempty"))
    ComponentOperator{eltype(H),typeof(H)}(H, Int(ncomp), shape[1], 0, 0, 0, 0)
end

Base.size(A::ComponentOperator) = (A.ncomp * A.ng, A.ncomp * A.ng)
function Base.size(A::ComponentOperator, dim::Integer)
    dim > 0 || throw(ArgumentError("Dimension must be positive"))
    dim <= 2 ? A.ncomp * A.ng : 1
end
Base.eltype(::Type{ComponentOperator{T,H}}) where {T,H} = T
Base.eltype(A::ComponentOperator) = eltype(typeof(A))

function operator_stats(A::ComponentOperator)
    (; A.operator_mul_calls, A.operator_columns, A.scalar_mul_calls, A.scalar_columns)
end

function reset_counters!(A::ComponentOperator)
    A.operator_mul_calls = A.operator_columns = A.scalar_mul_calls = A.scalar_columns = 0
    A
end

function _check_component_arrays(Y, X, nrows; allow_exact_alias=false)
    Base.require_one_based_indexing(Y, X)
    size(Y) == size(X) || throw(DimensionMismatch("Input/output shapes must agree"))
    size(X, 1) == nrows || throw(DimensionMismatch("Expected $nrows component-interleaved rows"))
    if Base.mightalias(Y, X) && !(allow_exact_alias && Y === X)
        throw(ArgumentError("Input and output may not overlap"))
    end
end

function LinearAlgebra.mul!(Y::AbstractVecOrMat, A::ComponentOperator,
                            X::AbstractVecOrMat, alpha::Number, beta::Number)
    _check_component_arrays(Y, X, size(A, 1))
    Xm = reshape(X, size(X, 1), :)
    Ym = reshape(Y, size(Y, 1), :)
    nstates = size(Xm, 2)
    for component in 1:A.ncomp
        rows = component:A.ncomp:size(A, 1)
        spatial_in = Matrix(view(Xm, rows, :))
        spatial_out = similar(spatial_in, promote_type(eltype(A), eltype(X)))
        # DFTK's frozen scalar block supports matrix mul! (Hamiltonian.jl:137).
        mul!(spatial_out, A.scalar, spatial_in)
        A.scalar_mul_calls += 1
        A.scalar_columns += nstates
        destination = view(Ym, rows, :)
        if iszero(beta)  # Do not read uninitialized Y, including NaNs, for beta=0.
            destination .= alpha .* spatial_out
        else
            destination .= alpha .* spatial_out .+ beta .* destination
        end
    end
    A.operator_mul_calls += 1
    A.operator_columns += nstates
    Y
end

LinearAlgebra.mul!(Y::AbstractVecOrMat, A::ComponentOperator, X::AbstractVecOrMat) =
    mul!(Y, A, X, true, false)

function Base.:*(A::ComponentOperator, X::AbstractVecOrMat)
    Y = similar(X, promote_type(eltype(A), eltype(X)))
    mul!(Y, A, X)
end

"""
Positive, spin-independent kinetic preconditioner. Its diagonal is
`repeat(kinetic .+ shift; inner=ncomp)` in the same interleaved layout.
`shift` and `kinetic` are in Ha; the fixed positive shift defaults to 1 Ha.

The frozen LOBPCG interface calls `ldiv!(P,R)` and its existing no-op
`precondprep!(P,X)` fallback. No DFTK/solver method is replaced or patched.
Exact in-place application is supported; other overlapping views are rejected.
"""
struct ComponentKineticPreconditioner{T<:AbstractFloat}
    diagonal::Vector{T}
    ncomp::Int
    ng::Int
end

function ComponentKineticPreconditioner(kinetic::AbstractVector{<:Real}, ncomp::Integer;
                                        shift::Real=1.0)
    ncomp isa Bool && throw(ArgumentError("ncomp must be a positive integer count"))
    ncomp > 0 || throw(ArgumentError("ncomp must be positive"))
    isempty(kinetic) && throw(ArgumentError("The spatial kinetic vector must be nonempty"))
    all(x -> isfinite(x) && x >= 0, kinetic) ||
        throw(ArgumentError("Kinetic energies must be finite and nonnegative"))
    isfinite(shift) && shift > 0 || throw(ArgumentError("The kinetic shift must be finite and positive"))
    diagonal = repeat(Float64.(kinetic) .+ Float64(shift); inner=Int(ncomp))
    all(x -> isfinite(x) && x > 0, diagonal) ||
        throw(ArgumentError("The Float64 preconditioner diagonal must be finite and positive"))
    ComponentKineticPreconditioner(diagonal, Int(ncomp), length(kinetic))
end

Base.size(P::ComponentKineticPreconditioner) = (length(P.diagonal), length(P.diagonal))
function Base.size(P::ComponentKineticPreconditioner, dim::Integer)
    dim > 0 || throw(ArgumentError("Dimension must be positive"))
    dim <= 2 ? length(P.diagonal) : 1
end
Base.eltype(::Type{ComponentKineticPreconditioner{T}}) where {T} = T
Base.eltype(P::ComponentKineticPreconditioner) = eltype(typeof(P))

function LinearAlgebra.ldiv!(Y::AbstractVecOrMat, P::ComponentKineticPreconditioner,
                             R::AbstractVecOrMat)
    _check_component_arrays(Y, R, size(P, 1); allow_exact_alias=true)
    reshape(Y, size(Y, 1), :) .= reshape(R, size(R, 1), :) ./ P.diagonal
    Y
end
LinearAlgebra.ldiv!(P::ComponentKineticPreconditioner, R::AbstractVecOrMat) = ldiv!(R, P, R)
function Base.:(\)(P::ComponentKineticPreconditioner, R::AbstractVecOrMat)
    ldiv!(similar(R, promote_type(eltype(P), eltype(R))), P, R)
end

function LinearAlgebra.mul!(Y::AbstractVecOrMat, P::ComponentKineticPreconditioner,
                            R::AbstractVecOrMat)
    _check_component_arrays(Y, R, size(P, 1); allow_exact_alias=true)
    reshape(Y, size(Y, 1), :) .= reshape(R, size(R, 1), :) .* P.diagonal
    Y
end
function Base.:*(P::ComponentKineticPreconditioner, R::AbstractVecOrMat)
    mul!(similar(R, promote_type(eltype(P), eltype(R))), P, R)
end

# Opt-in helper, leaving ComponentOperator's historical default dispatch intact.
# Native DFTK retained-potential protection is additionally enforced by the full-H
# runtime adapter; arbitrary callbacks cannot be authenticated by numerical code.
function kernel_component_action!(Y,A::ComponentOperator,X,workspace,alpha=1,beta=0)
    if A.scalar isa AbstractMatrix
        for array in (Y,workspace.spatial_input,workspace.spatial_output,workspace.candidate)
            Base.mightalias(array,A.scalar) && throw(ArgumentError("Output/workspace aliases scalar operator storage"))
        end
    end
    action=(output,input)->mul!(output,A.scalar,input)
    SOCKernels.component_action!(Y,action,X,A.ncomp,workspace,alpha,beta)
end
