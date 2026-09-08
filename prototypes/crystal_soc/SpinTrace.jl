"""Fixed-density spin-trace diagnostic; never a scalar-pseudopotential or SCF model."""
module SpinTrace
using LinearAlgebra, Random
import ..FRIntegration
import ..RelativisticProjectors
import ..SpinorPrototype
const FI = FRIntegration
export SpinTraceNonlocal, SpinTraceHamiltonianBlock, spin_trace_hamiltonian
export spin_apply, pauli_twirl_action, spin_trace_diagnostics

"""Read-only view of V=PDP†: apply I_spin ⊗ (V_uu+V_dd)/2, interleaved."""
struct SpinTraceNonlocal{F}
    original::F
    function SpinTraceNonlocal(fr::RelativisticProjectors.FRNonlocalOperator)
        iseven(size(fr, 1)) || throw(DimensionMismatch("Spin-trace requires two interleaved components"))
        new{typeof(fr)}(fr)
    end
end
Base.size(A::SpinTraceNonlocal) = size(A.original)
Base.size(A::SpinTraceNonlocal, i::Integer) = size(A.original, i)
Base.eltype(::SpinTraceNonlocal) = ComplexF64

function _check_arrays(Y, A, X, alpha, beta)
    Base.require_one_based_indexing(Y, X)
    size(Y) == size(X) && size(X, 1) == size(A, 1) && size(X, 2) > 0 ||
        throw(DimensionMismatch("Spin-trace requires matching nonempty spinor input/output shapes"))
    eltype(Y) === ComplexF64 && eltype(X) in (Float64, ComplexF64) ||
        throw(ArgumentError("Spin-trace requires Float64/ComplexF64 input and ComplexF64 output"))
    fr = A.original
    any(a -> Base.mightalias(Y, a), (X, fr.P, fr.D)) &&
        throw(ArgumentError("Spin-trace output aliases input or retained P/D"))
    all(isfinite, X) && isfinite(alpha) && isfinite(beta) ||
        throw(ArgumentError("Nonfinite spin-trace input or scale"))
    a, b = ComplexF64(alpha), ComplexF64(beta)
    isfinite(a) && isfinite(b) || throw(ArgumentError("Spin-trace scale overflows ComplexF64"))
    iszero(b) || all(isfinite, Y) || throw(ArgumentError("Nonfinite beta-weighted output"))
    a, b
end

function LinearAlgebra.mul!(Y::AbstractVecOrMat, A::SpinTraceNonlocal,
                            X::AbstractVecOrMat, alpha::Number, beta::Number)
    a, b = _check_arrays(Y, A, X, alpha, beta)
    P, D = A.original.P, A.original.D
    Pu, Pd = @view(P[1:2:end, :]), @view(P[2:2:end, :])
    Xm = reshape(X, size(X, 1), :)
    result = similar(X, ComplexF64)
    Rm = reshape(result, size(X, 1), :)
    # Each component sees the same spatial W, retaining both radial/j branches.
    # The adjoints and 1/2 are essential; no square plane-wave matrix is formed.
    for sigma in 1:2
        z = @view Xm[sigma:2:end, :]
        Rm[sigma:2:end, :] = (Pu * (D * (Pu' * z)) + Pd * (D * (Pd' * z))) / 2
    end
    result .*= a
    iszero(b) || (result .+= b .* Y)
    all(isfinite, result) || throw(ArgumentError("Nonfinite spin-trace action"))
    copyto!(Y, result)
end
LinearAlgebra.mul!(Y::AbstractVecOrMat, A::SpinTraceNonlocal, X::AbstractVecOrMat) = mul!(Y, A, X, 1, 0)
Base.:*(A::SpinTraceNonlocal, X::AbstractVecOrMat) = mul!(similar(X, ComplexF64), A, X)

"""Own diagnostic wrapper, bound to an issued full block without replacing its FR data."""
struct SpinTraceHamiltonianBlock{F,C,N}
    full_binding::F
    common::C
    fr::N
    calls::Vector{Int}
    function SpinTraceHamiltonianBlock(full::FI.FullHamiltonianBlock)
        FI.validate_context(full.context)
        FI._check_common_block(full.context, full.ik, full.scalar_binding)
        full.fr === full.context.fr_blocks[full.ik] || throw(ArgumentError("Unissued FR block"))
        full.common.scalar === full.scalar_binding && full.common.ncomp == 2 &&
            full.common.ng == size(full, 1) ÷ 2 || throw(ArgumentError("Full common binding changed"))
        # Own counters; scalar common potential, density and issued P/D stay identical.
        common = SpinorPrototype.ComponentOperator(full.scalar_binding, 2)
        fr = SpinTraceNonlocal(full.fr)
        new{typeof(full),typeof(common),typeof(fr)}(full, common, fr, zeros(Int, 4))
    end
end
spin_trace_hamiltonian(full::FI.FullHamiltonianBlock) = SpinTraceHamiltonianBlock(full)
Base.size(H::SpinTraceHamiltonianBlock) = size(H.fr)
Base.size(H::SpinTraceHamiltonianBlock, i::Integer) = size(H.fr, i)
Base.eltype(::SpinTraceHamiltonianBlock) = ComplexF64

function LinearAlgebra.mul!(Y::AbstractVecOrMat, H::SpinTraceHamiltonianBlock,
                            X::AbstractVecOrMat, alpha::Number, beta::Number)
    full = H.full_binding
    FI._validate_live_binding(full.context)
    H.fr.original === full.fr === full.context.fr_blocks[full.ik] &&
        H.common.scalar === full.scalar_binding && H.common.ncomp == 2 &&
        H.common.ng == size(H, 1) ÷ 2 || throw(ArgumentError("Spin-trace diagnostic binding changed"))
    FI._check_common_block(full.context, full.ik, H.common.scalar)
    a, b = _check_arrays(Y, H.fr, X, alpha, beta)
    FI._aliases_common_storage(Y, H.common.scalar) &&
        throw(ArgumentError("Spin-trace output aliases retained common potential"))
    result = a .* (H.common * X + H.fr * X)
    iszero(b) || (result .+= b .* Y)
    all(isfinite, result) || throw(ArgumentError("Nonfinite diagnostic Hamiltonian action"))
    copyto!(Y, result)
    H.calls .+= [1, size(X, 2), 1, size(X, 2)]
    Y
end
LinearAlgebra.mul!(Y::AbstractVecOrMat, H::SpinTraceHamiltonianBlock, X::AbstractVecOrMat) = mul!(Y, H, X, 1, 0)
Base.:*(H::SpinTraceHamiltonianBlock, X::AbstractVecOrMat) = mul!(similar(X, ComplexF64), H, X)

# New-type methods reuse the frozen target solver without altering old methods.
function FI.full_operator_stats(H::SpinTraceHamiltonianBlock)
    (; full_mul_calls=H.calls[1], full_columns=H.calls[2], fr_mul_calls=H.calls[3],
       fr_columns=H.calls[4], common=SpinorPrototype.operator_stats(H.common),
       nonlocal_semantics="spin-trace diagnostic; not the full-SOC FR action")
end
function FI.reset_full_counters!(H::SpinTraceHamiltonianBlock)
    fill!(H.calls, 0)
    SpinorPrototype.reset_counters!(H.common)
    H
end

"""Global 2×2 spin action in component-interleaved layout; no physical q reversal."""
function spin_apply(U, X::AbstractVecOrMat)
    size(U) == (2, 2) && iseven(size(X, 1)) || throw(DimensionMismatch("Interleaved spin dimensions"))
    Y = similar(X, ComplexF64)
    Xm, Ym = reshape(X, size(X, 1), :), reshape(Y, size(Y, 1), :)
    Ym[1:2:end, :] = U[1, 1] .* Xm[1:2:end, :] + U[1, 2] .* Xm[2:2:end, :]
    Ym[2:2:end, :] = U[2, 1] .* Xm[1:2:end, :] + U[2, 2] .* Xm[2:2:end, :]
    Y
end

"""Independent finite Pauli twirl using the original full FR action only."""
function pauli_twirl_action(fr, X)
    result = fr * X
    for sigma in (ComplexF64[0 1; 1 0], ComplexF64[0 -im; im 0], ComplexF64[1 0; 0 -1])
        result .+= spin_apply(sigma, fr * spin_apply(sigma, X))
    end
    result ./ 4
end

_err(a, b) = norm(a-b) / max(norm(a), norm(b), 1)

"""Static actual-source random action checks; no eigensolve or density evaluation."""
function spin_trace_diagnostics(full::FI.FullHamiltonianBlock; seed::Integer, nprobe=3, atol=1e-11)
    FI.validate_context(full.context)
    null = spin_trace_hamiltonian(full)
    rng = MersenneTwister(seed)
    X, Y = [randn(rng, ComplexF64, size(full, 1), nprobe) for _ in 1:2]
    X ./= norm(X); Y ./= norm(Y); saved = copy(X)
    a, phase = .371, .293
    U = ComplexF64[cos(a) cis(phase)*sin(a); -cis(-phase)*sin(a) cos(a)]
    original_counts = FI.full_operator_stats(full)
    fr, N = full.fr, null.fr
    P, D = fr.P, fr.D
    Pu, Pd = @view(P[1:2:end, :]), @view(P[2:2:end, :])
    trace_full = real(dot(P, P*D))
    # Two identical spin blocks, each retaining one half of the two block traces.
    trace_null = 2 * real((dot(Pu, Pu*D) + dot(Pd, Pd*D))/2)
    checks = (; pauli_twirl=_err(N*X, pauli_twirl_action(fr, X)),
        global_spin_rotation=_err(N*spin_apply(U, X), spin_apply(U, N*X)),
        full_nonlocal_hermiticity=_err(dot(X, fr*Y), dot(fr*X, Y)),
        null_nonlocal_hermiticity=_err(dot(X, N*Y), dot(N*X, Y)),
        spin_trace_preservation=_err(trace_full, trace_null),
        common_plus_null=_err(null*X, full.common*X + N*X))
    # Full action is sampled for Hermiticity after preserving the counter baseline.
    full_hermiticity = _err(dot(X, full*Y), dot(full*X, Y))
    null_hermiticity = _err(dot(X, null*Y), dot(null*X, Y))
    FI.validate_context(full.context)
    X == saved || error("Static spin-trace test modified its input")
    all(isfinite, values(checks)) && all(x -> x <= atol, values(checks)) &&
        max(full_hermiticity, null_hermiticity) <= atol || error("Spin-trace static contract failed")
    (; scope="RUNNER_REPORTED actual-source fixed-density random actions; no solve",
       seed, nprobe, threshold=atol, checks, full_hermiticity, null_hermiticity,
       full_trace=trace_full, null_trace=trace_null,
       spin_dependent_action_norm=norm(fr*X-N*X), nonlocal_action_norm=norm(fr*X),
       common_scalar_object_identical=null.common.scalar === full.scalar_binding,
       issued_fr_object_identical=N.original === full.context.fr_blocks[full.ik],
       input_unchanged=true, original_counts_before=original_counts,
       context_valid_after=true, status="PASS")
end
end
