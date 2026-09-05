# Workbench adapter for the frozen DFTK orbital FFT; no DFTK methods are changed.
# See DFTK src/fft.jl (normalization and spherical-grid mapping) and
# src/PlaneWaveBasis.jl (basis/k-point forwarding methods).

function check_component_fft_array(values::AbstractArray, spatial_size, label)
    ndims(values) == 3 || throw(DimensionMismatch("$label must have (component, spatial, state) axes"))
    size(values, 1) > 0 || throw(ArgumentError("$label needs at least one component"))
    size(values, 3) > 0 || throw(ArgumentError("$label needs at least one state"))
    size(values, 2) == spatial_size ||
        throw(DimensionMismatch("$label spatial axis must have length $spatial_size"))
    eltype(values) == ComplexF64 || throw(ArgumentError("$label must contain ComplexF64 values"))
    nothing
end

"""
    component_ifft(basis, kpt, Psi)

Convert `Psi[component,G,state]` to periodic Bloch components
`u[component,r,state]`, where `r` follows `vec(DFTK.r_vectors(basis))`.
DFTK uses `u(r) = sum_G Psi[G] exp(2πim G⋅r) / sqrt(Ω)`; the full
Bloch factor `exp(2πim k⋅r)` is not included. Thus the reciprocal norm
equals `basis.dvol * sum(abs2, u)` over both component and spatial axes.

This Float64 CPU prototype allocates its result and preserves its input.
The selected k point supplies its own `NG`; no common `NG` is assumed.
"""
function component_ifft(basis, kpt, Psi::AbstractArray)
    check_component_fft_array(Psi, length(DFTK.G_vectors(basis, kpt)), "Psi")
    ncomp, _, nstates = size(Psi)
    output = Array{ComplexF64}(undef, ncomp, prod(basis.fft_size), nstates)
    for state in 1:nstates, component in 1:ncomp
        # Component slices are strided in the interleaved representation.
        coefficients = copy(@view Psi[component, :, state])
        output[component, :, state] = vec(DFTK.ifft(basis, kpt, coefficients))
    end
    output
end

"""
    component_fft(basis, kpt, u)

Project periodic real-grid components `u[component,r,state]` onto the
selected k point's spherical plane-wave basis. This inverts `component_ifft`
on that subspace; arbitrary real-grid input is truncated to the same basis.
The result has `(component,G,state)` axes and the input is preserved.
"""
function component_fft(basis, kpt, u::AbstractArray)
    check_component_fft_array(u, prod(basis.fft_size), "u")
    ncomp, _, nstates = size(u)
    output = Array{ComplexF64}(undef, ncomp, length(DFTK.G_vectors(basis, kpt)), nstates)
    for state in 1:nstates, component in 1:ncomp
        # DFTK's mapped fft! overwrites its real-grid scratch. Use the existing
        # allocating fft interface and owned contiguous input, never a user view.
        grid = reshape(copy(@view u[component, :, state]), basis.fft_size)
        output[component, :, state] = DFTK.fft(basis, kpt, grid)
    end
    output
end
