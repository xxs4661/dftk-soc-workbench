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

"""Opt-in bounded orbital FFT/density scratch, one physical state at a time.

No input is owned here. The caller's session authenticates basis/k/mapping/source
at its explicit boundaries. Returned density arrays are workspace-borrowed until
next use; a retained endpoint needs an explicit owned snapshot. No legacy FFT or
density function changes dispatch. This serial workspace cannot be shared across
concurrent calls.
"""
mutable struct OrbitalDensityWorkspace
    coefficients::Vector{ComplexF64}
    grid::Array{ComplexF64,3}
    real_state::Array{ComplexF64,3}
    density::SOCKernels.DensityWorkspace
    inverse_fft_calls::Int
    transformed_states::Int
    density_calls::Int
end
function OrbitalDensityWorkspace(max_ng,nr,fft_size,ncomp=2)
    ng=SOCKernels._positive(max_ng,"FFT coefficient capacity")
    r=SOCKernels._positive(nr,"FFT real grid size")
    n=SOCKernels._positive(ncomp,"Density component count")
    fft_size isa Tuple && length(fft_size)==3 && all(x->x isa Integer && !(x isa Bool) && x>0,fft_size) && prod(fft_size)==r ||
        throw(DimensionMismatch("Explicit three-dimensional FFT size differs from nr"))
    n in (1,2) || throw(ArgumentError("Physical density supports one or two components"))
    OrbitalDensityWorkspace(Vector{ComplexF64}(undef,ng),Array{ComplexF64}(undef,fft_size),
        Array{ComplexF64}(undef,n,r,1),SOCKernels.DensityWorkspace(n,r),0,0,0)
end
SOCKernels.workspace_stats(ws::OrbitalDensityWorkspace)=(;ws.inverse_fft_calls,ws.transformed_states,ws.density_calls,
    density=SOCKernels.workspace_stats(ws.density))
function SOCKernels.reset_workspace_counters!(ws::OrbitalDensityWorkspace)
    ws.inverse_fft_calls=ws.transformed_states=ws.density_calls=0
    SOCKernels.reset_workspace_counters!(ws.density);ws
end
function _orbital_workspace_buffers(ws)
    (ws.coefficients,ws.grid,ws.real_state,SOCKernels._density_buffers(ws.density)...)
end
function _orbital_density_request(ws,basis,X,weights,f;atol=1e-11)
    nk=length(basis.kpoints);ncomp=size(ws.real_state,1);nr=prod(basis.fft_size)
    length(X)==length(f)==nk>0 || throw(DimensionMismatch("One matrix/occupation set per physical k required"))
    SOCKernels.validate_weights(weights,nk;atol)
    weights==basis.kweights || throw(ArgumentError("Weights differ from the supplied actual basis"))
    size(ws.grid)==basis.fft_size && size(ws.real_state)==(ncomp,nr,1) && length(ws.density.n)==nr &&
        size(ws.density.R)==(ncomp,ncomp,nr) || throw(DimensionMismatch("Density workspace FFT/component shape changed"))
    buffers=_orbital_workspace_buffers(ws);SOCKernels._no_overlap(buffers)
    for ik in eachindex(X)
        x=X[ik];occ=f[ik];kpt=basis.kpoints[ik];ng=length(DFTK.G_vectors(basis,kpt))
        x isa AbstractMatrix && eltype(x)===ComplexF64 && size(x,1)==ncomp*ng && size(x,2)>0 && ng<=length(ws.coefficients) ||
            throw(DimensionMismatch("Physical component/G/state or workspace capacity mismatch"))
        Base.require_one_based_indexing(x,occ)
        all(isfinite,x) || throw(ArgumentError("Nonfinite reciprocal orbital"))
        SOCKernels._occupations(occ,size(x,2);capacity=ncomp==1 ? 2.0 : 1.0)
        SOCKernels._protect_scratch(buffers,(x,occ,weights))
        length(kpt.mapping)==ng && all(i->1<=i<=nr,kpt.mapping) || throw(ArgumentError("Invalid actual k/FFT mapping"))
    end
    ncomp,nr
end
function _orbital_real_state!(ws,basis,kpt,x,state,ncomp,nr)
    ng=size(x,1)÷ncomp;coefficients=@view ws.coefficients[1:ng]
    for component in 1:ncomp
        for g in 1:ng;coefficients[g]=x[component+ncomp*(g-1),state];end
        DFTK.ifft!(ws.grid,basis,kpt,coefficients)
        all(isfinite,ws.grid) || throw(ArgumentError("Nonfinite periodic Bloch component"))
        for r in 1:nr;ws.real_state[component,r,1]=ws.grid[r];end
        ws.inverse_fft_calls+=1
    end
    ws.transformed_states+=1
    ws.real_state
end
