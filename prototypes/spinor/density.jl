# Phase 5A: explicit capacities, real-space density, and synthetic local Pauli action.
# These functions do not call DFTK's :none occupation rule or its density routine.

function _density_checked_weights(weights, count; atol=1e-11)
    atol isa Real && isfinite(atol) && atol > 0 ||
        throw(ArgumentError("Weight/count tolerance must be finite and positive"))
    length(weights) == count && count > 0 ||
        throw(DimensionMismatch("One spatial weight is required for each k point"))
    all(w -> w isa Real && isfinite(w) && w >= 0, weights) ||
        throw(ArgumentError("Spatial weights must be finite, real, and nonnegative"))
    abs(sum(weights) - 1) <= atol ||
        throw(ArgumentError("Spatial k-point weights must sum to one; no automatic normalization"))
    Float64.(weights)
end

"""
    fixed_gapped_occupations(eigenvalues, weights; representation, n_electrons=8, atol=1e-11)

Limited zero-temperature helper for this eight-electron gapped prototype.
`:scalar` uses capacity 2, four occupied states, and eight target states;
`:spinor` uses capacity 1, eight occupied states, and sixteen target states.
Every additional auxiliary state is empty. The global HOMO must be strictly
below the global LUMO; the helper does not solve a metallic occupation problem.
Input eigenvalues are sorted finite real values in Ha, without reordering here.
"""
function fixed_gapped_occupations(eigenvalues, weights;
                                 representation::Symbol, n_electrons=8, atol=1e-11)
    n_electrons isa Real && isfinite(n_electrons) && n_electrons == 8 ||
        throw(ArgumentError("This helper is restricted to eight electrons"))
    capacity, n_occupied, n_target = if representation == :scalar
        (2.0, 4, 8)
    elseif representation == :spinor
        (1.0, 8, 16)
    else
        throw(ArgumentError("Specify :scalar or :spinor explicitly"))
    end
    kweights = _density_checked_weights(weights, length(eigenvalues); atol)
    for values in eigenvalues
        values isa AbstractVector && length(values) >= n_target ||
            throw(DimensionMismatch("Every k point needs all target states, including empty states"))
        all(x -> x isa Real && isfinite(x), values) ||
            throw(ArgumentError("All target and auxiliary eigenvalues must be finite and real"))
        issorted(values) || throw(ArgumentError("Eigenvalues must already be sorted"))
    end
    homo = maximum(values[n_occupied] for values in eigenvalues)
    lumo = minimum(values[n_occupied+1] for values in eigenvalues)
    lumo > homo || throw(ArgumentError("Fixed occupations require a strictly positive global gap"))
    occupations = [vcat(fill(capacity, n_occupied), zeros(length(values)-n_occupied))
                   for values in eigenvalues]
    count = sum(kweights .* sum.(occupations))
    abs(count - n_electrons) <= atol ||
        throw(ArgumentError("Weighted fixed occupations do not contain eight electrons"))
    (; occupations, capacity, n_occupied, n_target, n_electrons=count,
       homo=Float64(homo), lumo=Float64(lumo), gap=Float64(lumo-homo))
end

"""
    density_from_real_states(states, weights, occupations; atol=1e-11)

Each k-point array stores `(component, flat_real_grid, state)` periodic Bloch
amplitudes, in the `vec(DFTK.r_vectors(basis))` real-grid order. Amplitudes keep
the FFT normalization; no component is separately normalized here.

Accumulate `R[a,b,r] = sum(w*f*u[a]*conj(u[b]))`. For two components, return
`n = tr(R)` and `m = (2real(R12), -2imag(R12), R11-R22)`, with `m` shaped
`(3, flat_real_grid)`. This m is Pauli spin density, not a magnetic moment.
The scalar one-component path returns `m=nothing`. Integration subsequently
requires the real-grid volume element; this function does not multiply by it.
"""
function density_from_real_states(states, weights, occupations; atol=1e-11)
    kweights = _density_checked_weights(weights, length(states); atol)
    length(occupations) == length(states) ||
        throw(DimensionMismatch("One occupation vector is required for each k point"))
    first_state = first(states)
    first_state isa AbstractArray && ndims(first_state) == 3 ||
        throw(DimensionMismatch("Real-space states must have component, grid, and state axes"))
    ncomp, nr = size(first_state, 1), size(first_state, 2)
    ncomp in (1, 2) && nr > 0 ||
        throw(ArgumentError("Density physics is limited to one scalar or two spinor components"))
    capacity = ncomp == 1 ? 2.0 : 1.0
    for (values, occ) in zip(states, occupations)
        values isa AbstractArray && ndims(values) == 3 &&
            size(values, 1) == ncomp && size(values, 2) == nr ||
            throw(DimensionMismatch("All k points must share component count and real-space grid"))
        length(occ) == size(values, 3) ||
            throw(DimensionMismatch("State count and occupation count differ"))
        all(x -> x isa Number && isfinite(x), values) ||
            throw(ArgumentError("Real-space amplitudes must be finite"))
        all(f -> f isa Real && isfinite(f) && 0 <= f <= capacity, occ) ||
            throw(ArgumentError("Occupation exceeds this representation's explicit capacity"))
    end
    R = zeros(ComplexF64, ncomp, ncomp, nr)
    for (values, weight, occ) in zip(states, kweights, occupations)
        for state in axes(values, 3)
            factor = weight * occ[state]
            iszero(factor) && continue
            for r in 1:nr, b in 1:ncomp, a in 1:ncomp
                R[a, b, r] += factor * values[a, r, state] * conj(values[b, r, state])
            end
        end
    end
    all(isfinite, R) || throw(ArgumentError("Nonfinite accumulated density"))
    n = [sum(real(R[a, a, r]) for a in 1:ncomp) for r in 1:nr]
    m = if ncomp == 2
        vcat(reshape(2 .* real.(R[1, 2, :]), 1, nr),
             reshape(-2 .* imag.(R[1, 2, :]), 1, nr),
             reshape(real.(R[1, 1, :] .- R[2, 2, :]), 1, nr))
    else
        nothing
    end
    (; R, n, m)
end

"""
    apply_local_pauli(states, v, B)

Synthetic algebra adapter on `(2, flat_real_grid, state)` arrays.
`v` is a real scalar or vector of grid values; `B` is a real three-vector
or `(3, flat_real_grid)` matrix. Apply `v*I + B·sigma` pointwise into a new
array, with upper-right `Bx-im*By` and lower-left `Bx+im*By`.
This operator is not attached to Si and is not an SOC or physical-field model.
"""
function apply_local_pauli(states, v, B)
    states isa AbstractArray && ndims(states) == 3 && size(states, 1) == 2 ||
        throw(DimensionMismatch("Local Pauli action requires (2, real_grid, state) amplitudes"))
    all(x -> x isa Number && isfinite(x), states) ||
        throw(ArgumentError("Pauli input amplitudes must be finite"))
    nr = size(states, 2)
    potential = if v isa Real
        fill(v, nr)
    elseif v isa AbstractVector && length(v) == nr
        v
    else
        throw(DimensionMismatch("Scalar potential needs one real value per grid point"))
    end
    field = if B isa AbstractVector && length(B) == 3
        repeat(reshape(B, 3, 1), 1, nr)
    elseif B isa AbstractMatrix && size(B) == (3, nr)
        B
    else
        throw(DimensionMismatch("Pauli field must be a three-vector or a 3-by-grid array"))
    end
    all(x -> x isa Real && isfinite(x), potential) &&
        all(x -> x isa Real && isfinite(x), field) ||
        throw(ArgumentError("Hermitian Pauli coefficients must be finite and real"))
    output = similar(states, ComplexF64)
    for state in axes(states, 3), r in 1:nr
        bx, by, bz = field[:, r]
        up, down = states[1, r, state], states[2, r, state]
        output[1, r, state] = (potential[r]+bz)*up + (bx-im*by)*down
        output[2, r, state] = (bx+im*by)*up + (potential[r]-bz)*down
    end
    all(isfinite, output) || throw(ArgumentError("Nonfinite local Pauli result"))
    output
end

"""Opt-in statewise FFT and exact-order R/n/m accumulation.

The scope uses actual supplied k points, all physical states and capacity-one
spinor occupations (or the legacy supported scalar capacity two). It never
solves occupations, clips density or introduces core density. Returned arrays
are borrowed from ws until the next reset; no result is valid on an exception.
"""
function orbital_density!(ws::OrbitalDensityWorkspace,basis,X,weights,f;atol=1e-11)
    ncomp,nr=_orbital_density_request(ws,basis,X,weights,f;atol)
    SOCKernels.reset_density!(ws.density)
    try
        for ik in eachindex(X)
            x=X[ik];kpt=basis.kpoints[ik]
            for state in axes(x,2)
                u=_orbital_real_state!(ws,basis,kpt,x,state,ncomp,nr)
                SOCKernels.accumulate_density!(ws.density,u,weights[ik],@view(f[ik][state:state]))
            end
        end
        result=SOCKernels.finish_density!(ws.density)
        ws.density_calls+=1
        result
    catch
        ws.density.active=false;ws.density.failed=true;rethrow()
    end
end
