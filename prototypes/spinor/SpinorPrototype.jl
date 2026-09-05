"""Replaceable workbench prototype; not an accepted upstream API or SOC implementation."""
module SpinorPrototype
using LinearAlgebra
import DFTK

export flatten_components, unflatten_components
export ComponentOperator, ComponentKineticPreconditioner, reset_counters!, operator_stats
export component_ifft, component_fft
export fixed_gapped_occupations, density_from_real_states, apply_local_pauli

"""Expose Psi[component,G,state] as rows component+ncomp*(G-1), without copying."""
function flatten_components(psi::AbstractArray{<:Number,3})
    all(>(0), size(psi)) || throw(DimensionMismatch("Component, G and state counts must be positive"))
    reshape(psi, size(psi, 1) * size(psi, 2), size(psi, 3))
end

"""View flattened component-interleaved orbitals in the single prototype layout."""
function unflatten_components(x::AbstractMatrix, ncomp::Integer)
    ncomp > 0 && size(x, 1) > 0 && size(x, 2) > 0 && size(x, 1) % ncomp == 0 ||
        throw(DimensionMismatch("Rows must be a positive multiple of the component count"))
    reshape(x, ncomp, size(x, 1) ÷ ncomp, size(x, 2))
end

include("operators.jl")
include("fft.jl")
include("density.jl")
end
