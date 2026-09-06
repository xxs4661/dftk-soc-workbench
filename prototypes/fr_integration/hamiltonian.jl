"""Issued association of one common basis with its atom-ordered, same-source FR blocks."""
mutable struct FRHamiltonianContext
    basis
    bundles::Vector
    fr_blocks::Vector
    mode::Symbol
    xc_identifiers::Vector{Symbol}
end

# Certificates contain actual issued objects and independent value snapshots. A caller's
# equal hash strings, equal dimensions, or a separately constructed basis are insufficient.
const _FR_CONTEXT_CERTIFICATES = IdDict{FRHamiltonianContext,Any}()

_fr_array_hash(a) = bytes2hex(SHA.sha256(reinterpret(UInt8, vec(copy(a)))))

function _common_term_gate(basis)
    expected = (DFTK.Kinetic, DFTK.AtomicLocal, DFTK.Ewald,
                DFTK.PspCorrection, DFTK.Hartree, DFTK.Xc)
    ts = basis.model.term_types
    length(ts) == length(expected) &&
        all(count(t -> t isa T, ts) == 1 for T in expected) ||
        throw(ArgumentError("common model must contain exactly Kinetic, AtomicLocal, Ewald, PspCorrection, Hartree, Xc"))
    any(t -> t isa DFTK.TermAtomicNonlocal, basis.terms) &&
        throw(ArgumentError("native AtomicNonlocal is forbidden in the common basis"))
    instantiated = (DFTK.TermKinetic, DFTK.TermAtomicLocal, DFTK.TermEwald,
                    DFTK.TermPspCorrection, DFTK.TermHartree, DFTK.TermXc)
    length(basis.terms) == length(instantiated) &&
        all(count(t -> t isa T, basis.terms) == 1 for T in instantiated) ||
        throw(ArgumentError("instantiated common terms do not match the six declared terms"))
    basis.model.spin_polarization == :none && basis.model.n_spin_components == 1 ||
        throw(ArgumentError("common model must be charge-only with one scalar component"))
    basis.model.temperature == 0 || throw(ArgumentError("only zero-temperature diagnostic occupations are supported"))
    xc = only(filter(t -> t isa DFTK.Xc, ts))
    xc.use_nlcc && !xc.nlcc_from_vw && xc.scaling_factor == 1 && xc.potential_threshold == 0 ||
        throw(ArgumentError("common XC must retain the unscaled complete native NLCC path"))
    true
end

function _basis_snapshot(basis)
    (; model=basis.model, lattice=copy(basis.model.lattice),
       positions=deepcopy(basis.model.positions), atoms=copy(basis.model.atoms),
       weights=copy(basis.kweights), kpoints=copy(basis.kpoints),
       coords=[copy(k.coordinate) for k in basis.kpoints],
       G=[copy(k.G_vectors) for k in basis.kpoints],
       mapping=[copy(k.mapping) for k in basis.kpoints],
       mapping_inv=[copy(k.mapping_inv) for k in basis.kpoints],
       mapping_device=[copy(k.mapping_device) for k in basis.kpoints],
       fft_size=basis.fft_size, Ecut=basis.Ecut, n_electrons=basis.model.n_electrons)
end

function _context_certificate(ctx)
    haskey(_FR_CONTEXT_CERTIFICATES, ctx) ||
        throw(ArgumentError("context was not issued by build_context"))
    _FR_CONTEXT_CERTIFICATES[ctx]
end

function _validate_live_binding(ctx)
    cert = _context_certificate(ctx)
    basis = ctx.basis
    basis === cert.basis || throw(ArgumentError("basis object identity mismatch"))
    snap = cert.snapshot
    basis.model === snap.model && basis.model.lattice == snap.lattice &&
        basis.model.positions == snap.positions && basis.model.n_electrons == snap.n_electrons &&
        basis.fft_size == snap.fft_size && basis.Ecut == snap.Ecut ||
        throw(ArgumentError("crystal, atom positions, electron count, or basis settings changed"))
    ctx.mode == cert.mode && ctx.xc_identifiers == cert.xc_identifiers ||
        throw(ArgumentError("context mode or XC identity changed"))
    length(ctx.bundles) == length(cert.bundles) == length(basis.model.atoms) ||
        throw(ArgumentError("atom/source count mismatch"))
    for ia in eachindex(ctx.bundles)
        bundle = ctx.bundles[ia]
        bundle === cert.bundles[ia] || throw(ArgumentError("atom-ordered source bundle identity mismatch"))
        assert_bound_identity(bundle)
        basis.model.atoms[ia] === snap.atoms[ia] &&
            basis.model.atoms[ia].psp === bundle.common ||
            throw(ArgumentError("atom order or common pseudopotential object mismatch"))
    end
    basis.kweights == snap.weights && length(basis.kpoints) == length(snap.kpoints) ||
        throw(ArgumentError("spatial k-point weights or count changed"))
    for ik in eachindex(basis.kpoints)
        kpt = basis.kpoints[ik]
        kpt === snap.kpoints[ik] && kpt.coordinate == snap.coords[ik] &&
            kpt.G_vectors == snap.G[ik] && kpt.mapping == snap.mapping[ik] &&
            kpt.mapping_inv == snap.mapping_inv[ik] && kpt.mapping_device == snap.mapping_device[ik] ||
            throw(ArgumentError("k-point identity, coordinate, G order, or FFT mapping changed"))
    end
    length(ctx.fr_blocks) == length(cert.fr_blocks) &&
        all(ctx.fr_blocks[i] === cert.fr_blocks[i] for i in eachindex(ctx.fr_blocks)) ||
        throw(ArgumentError("FR blocks are missing, duplicated, reordered, or replaced"))
    _common_term_gate(basis)
    model_xc = only(filter(t -> t isa DFTK.Xc, basis.model.term_types))
    actual_xc = only(filter(t -> t isa DFTK.TermXc, basis.terms))
    DFTK.identifier.(model_xc.functionals) == ctx.xc_identifiers &&
        DFTK.identifier.(actual_xc.functionals) == ctx.xc_identifiers &&
        actual_xc.scaling_factor == model_xc.scaling_factor &&
        actual_xc.potential_threshold == model_xc.potential_threshold ||
        throw(ArgumentError("actual model/instantiated XC functionals differ from the bound UPF family"))
    true
end

"""Deep boundary validation; iterative mul! uses the lightweight object/grid checks above."""
function validate_context(ctx)
    _validate_live_binding(ctx)
    cert = _context_certificate(ctx)
    for bundle in ctx.bundles
        assert_bound_sources(bundle)
        Symbol.(bundle.xc_identifiers) == ctx.xc_identifiers && bundle.mode == ctx.mode ||
            throw(ArgumentError("bundle mode or XC family mismatch"))
    end
    for (ik, op) in enumerate(ctx.fr_blocks)
        _fr_array_hash(op.P) == cert.projector_hashes[ik] &&
            _fr_array_hash(op.D) == cert.coupling_hashes[ik] &&
            op.labels == cert.labels[ik] ||
            throw(ArgumentError("issued FR projector, radial coupling, or atom/channel labels changed"))
    end
    true
end
_validate_basis(ctx) = validate_context(ctx)

function _atom_ordered_fr(bundles, qcart, positions_cart, volume)
    individual = [RelativisticProjectors.build_nonlocal_operator(
        b.channels, qcart, [positions_cart[ia]], volume) for (ia, b) in enumerate(bundles)]
    P = reduce(hcat, op.P for op in individual)
    D = zeros(ComplexF64, size(P, 2), size(P, 2))
    labels = NamedTuple[]
    offset = 0
    for (ia, op) in enumerate(individual)
        inds = offset .+ (1:size(op.D, 1))
        D[inds, inds] = op.D
        append!(labels, [merge(label, (;atom=ia)) for label in op.labels])
        offset += size(op.D, 1)
    end
    RelativisticProjectors.FRNonlocalOperator(P, D; labels)
end

"""
Build six explicit common terms, then one FR operator per physical k point.
`bundles` has one issued bundle per atom in `positions` order. Scalar degeneration
requires the explicit `:synthetic_scalar_limit` mode and the issued Si bundle.
"""
function build_context(bundles, lattice, positions, kcoords, kweights;
                       Ecut, xc_identifiers, mode::Symbol)
    bs = collect(bundles)
    !isempty(bs) && length(bs) == length(positions) ||
        throw(ArgumentError("one issued source bundle per atom is required"))
    mode in (:real_fr, :synthetic_scalar_limit) || throw(ArgumentError("unsupported integration mode"))
    xcids = Symbol.(xc_identifiers)
    for b in bs
        assert_bound_sources(b)
        b.mode == mode || throw(ArgumentError("real-FR and synthetic scalar-limit modes cannot be mixed"))
        Symbol.(b.xc_identifiers) == xcids || throw(ArgumentError("XC family does not match the bound UPF"))
    end
    size(lattice) == (3, 3) && all(isfinite, lattice) && isfinite(det(lattice)) && abs(det(lattice)) > 0 ||
        throw(ArgumentError("finite nonsingular three-dimensional lattice required"))
    all(r -> length(r) == 3 && all(isfinite, r), positions) || throw(ArgumentError("invalid atomic positions"))
    !isempty(kcoords) && length(kcoords) == length(kweights) &&
        all(k -> length(k) == 3 && all(isfinite, k), kcoords) &&
        all(w -> isfinite(w) && w > 0, kweights) && abs(sum(kweights) - 1) <= 1e-12 ||
        throw(ArgumentError("explicit finite spatial k points and positive weights summing to one required"))
    length(unique(Tuple.(kcoords))) == length(kcoords) || throw(ArgumentError("duplicate physical k coordinates"))
    isfinite(Ecut) && Ecut > 0 || throw(ArgumentError("positive finite Ecut required"))
    ne = sum(b.common.z_valence for b in bs)
    ne isa Int && ne > 0 || throw(ArgumentError("this diagnostic requires positive integer header-derived electron count"))
    terms = [DFTK.Kinetic(), DFTK.AtomicLocal(), DFTK.Ewald(),
             DFTK.PspCorrection(), DFTK.Hartree(), DFTK.Xc(xcids)]
    atoms = [DFTK.ElementPsp(b.common.element, b.common) for b in bs]
    model = DFTK.Model(Matrix{Float64}(lattice), atoms, [Float64.(r) for r in positions];
        model_name="Phase 6B common-only integration", terms, n_electrons=ne,
        spin_polarization=:none, temperature=0.0, symmetries=false)
    basis = DFTK.PlaneWaveBasis(model; Ecut=Float64(Ecut),
        kgrid=DFTK.ExplicitKpoints([Float64.(k) for k in kcoords], Float64.(kweights)))
    length(basis.kpoints) == length(kcoords) &&
        [collect(k.coordinate) for k in basis.kpoints] == kcoords &&
        basis.kweights == kweights || throw(ArgumentError("actual explicit k-point order/weights differs from request"))
    poscart = [model.lattice * r for r in model.positions]
    ops = [_atom_ordered_fr(bs, collect(DFTK.Gplusk_vectors_cart(basis, k)),
                            poscart, model.unit_cell_volume) for k in basis.kpoints]
    ctx = FRHamiltonianContext(basis, bs, ops, mode, copy(xcids))
    _FR_CONTEXT_CERTIFICATES[ctx] = (; basis, bundles=copy(bs), fr_blocks=copy(ops), mode,
        xc_identifiers=copy(xcids), snapshot=_basis_snapshot(basis),
        projector_hashes=[_fr_array_hash(op.P) for op in ops],
        coupling_hashes=[_fr_array_hash(op.D) for op in ops], labels=[deepcopy(op.labels) for op in ops])
    validate_context(ctx)
    ctx
end

function _check_common_block(ctx, ik, scalar)
    1 <= ik <= length(ctx.basis.kpoints) || throw(BoundsError(ctx.basis.kpoints, ik))
    scalar isa DFTK.HamiltonianBlock && scalar.basis === ctx.basis &&
        scalar.kpoint === ctx.basis.kpoints[ik] ||
        throw(ArgumentError("common Hamiltonian block has wrong basis or physical k-point identity"))
    size(scalar) == (length(ctx.basis.kpoints[ik].G_vectors), length(ctx.basis.kpoints[ik].G_vectors)) ||
        throw(DimensionMismatch("common block/G list size mismatch"))
    any(op -> op isa DFTK.NonlocalOperator, scalar.operators) &&
        throw(ArgumentError("native nonlocal operator in common Hamiltonian"))
    if hasproperty(scalar, :optimized_operators)
        any(op -> op isa DFTK.NonlocalOperator, scalar.optimized_operators) &&
            throw(ArgumentError("native nonlocal operator in optimized common Hamiltonian"))
    end
    hasproperty(scalar, :nonlocal_op) && !isnothing(scalar.nonlocal_op) &&
        throw(ArgumentError("native nonlocal operator in common Hamiltonian"))
    true
end

"""Matrix-free component lift plus exactly one issued FR block; no dense PW matrix."""
struct FullHamiltonianBlock{C,S,F}
    context::C
    ik::Int
    common::S
    fr::F
    scalar_binding
    calls::Vector{Int}  # full calls, columns, FR calls, FR columns
    function FullHamiltonianBlock(ctx, ik::Integer, scalar, fr)
        _validate_live_binding(ctx)
        _check_common_block(ctx, ik, scalar)
        fr === ctx.fr_blocks[ik] || throw(ArgumentError("FR block was not issued for this physical k point"))
        lift = SpinorPrototype.ComponentOperator(scalar, 2)
        size(lift) == size(fr) || throw(DimensionMismatch("common lift/FR size mismatch"))
        new{typeof(ctx),typeof(lift),typeof(fr)}(ctx, Int(ik), lift, fr, scalar, zeros(Int, 4))
    end
end

Base.size(H::FullHamiltonianBlock) = size(H.fr)
Base.size(H::FullHamiltonianBlock, i::Integer) = i <= 2 ? size(H)[i] : 1
Base.eltype(::FullHamiltonianBlock) = ComplexF64

function _aliases_common_storage(Y, scalar)
    operators = hasproperty(scalar, :optimized_operators) ? scalar.optimized_operators : scalar.operators
    for op in operators
        op isa DFTK.RealSpaceMultiplication && Base.mightalias(Y, op.potential) && return true
        op isa DFTK.FourierMultiplication && Base.mightalias(Y, op.multiplier) && return true
    end
    # The optimized block owns summed arrays that need not be identical to an
    # original term's array. Protect these as well as the generic interface.
    hasproperty(scalar, :local_op) && Base.mightalias(Y, scalar.local_op.potential) && return true
    hasproperty(scalar, :fourier_op) && Base.mightalias(Y, scalar.fourier_op.multiplier) && return true
    false
end

function LinearAlgebra.mul!(Y::AbstractVecOrMat, H::FullHamiltonianBlock,
                            X::AbstractVecOrMat, alpha::Number, beta::Number)
    _validate_live_binding(H.context)
    H.common.scalar === H.scalar_binding && H.fr === H.context.fr_blocks[H.ik] &&
        H.common.ncomp == 2 && H.common.ng == size(H, 1) ÷ 2 ||
        throw(ArgumentError("full-H component or FR binding changed"))
    _check_common_block(H.context, H.ik, H.common.scalar)
    Base.require_one_based_indexing(Y, X)
    size(Y) == size(X) && size(X, 1) == size(H, 2) && size(X, 2) > 0 ||
        throw(DimensionMismatch("full-H input/output must have the same correct nonempty shape"))
    eltype(Y) === ComplexF64 || throw(ArgumentError("full-H output must be ComplexF64"))
    eltype(X) in (Float64, ComplexF64) || throw(ArgumentError("full-H input must be Float64 or ComplexF64"))
    (any(a -> Base.mightalias(Y, a), (X, H.fr.P, H.fr.D)) || _aliases_common_storage(Y, H.common.scalar)) &&
        throw(ArgumentError("full-H output aliases input or retained operator storage"))
    all(isfinite, X) && isfinite(alpha) && isfinite(beta) || throw(ArgumentError("nonfinite full-H input or scale"))
    a, b = ComplexF64(alpha), ComplexF64(beta)
    isfinite(a) && isfinite(b) || throw(ArgumentError("full-H scale overflows ComplexF64"))
    beta == 0 || all(isfinite, Y) || throw(ArgumentError("nonfinite full-H output with nonzero beta"))
    common_action = H.common * X
    fr_action = H.fr * X
    result = a .* (common_action .+ fr_action)
    beta == 0 || (result .+= b .* Y)
    all(isfinite, result) || throw(ArgumentError("full-H action produced nonfinite values"))
    copyto!(Y, result)
    H.calls .+= [1, size(X, 2), 1, size(X, 2)]
    Y
end
LinearAlgebra.mul!(Y::AbstractVecOrMat, H::FullHamiltonianBlock, X::AbstractVecOrMat) = mul!(Y, H, X, 1, 0)
function Base.:*(H::FullHamiltonianBlock, X::AbstractVecOrMat)
    Y = similar(X, ComplexF64)
    mul!(Y, H, X)
end

function full_operator_stats(H::FullHamiltonianBlock)
    (; full_mul_calls=H.calls[1], full_columns=H.calls[2],
       fr_mul_calls=H.calls[3], fr_columns=H.calls[4],
       common=SpinorPrototype.operator_stats(H.common))
end
function reset_full_counters!(H::FullHamiltonianBlock)
    fill!(H.calls, 0)
    SpinorPrototype.reset_counters!(H.common)
    H
end

"""Compose only with the common Hamiltonian returned on this actual context's basis."""
function compose_full_hamiltonian(ctx, common_ham; fr_blocks=ctx.fr_blocks)
    validate_context(ctx)
    common_ham isa DFTK.Hamiltonian && common_ham.basis === ctx.basis ||
        throw(ArgumentError("common Hamiltonian belongs to another basis"))
    length(common_ham.blocks) == length(ctx.fr_blocks) == length(fr_blocks) ||
        throw(ArgumentError("missing or extra common/FR blocks"))
    all(fr_blocks[i] === ctx.fr_blocks[i] for i in eachindex(fr_blocks)) ||
        throw(ArgumentError("FR block k/order/source identity mismatch"))
    [FullHamiltonianBlock(ctx, ik, common_ham.blocks[ik], fr_blocks[ik]) for ik in eachindex(fr_blocks)]
end

"""Validate only valence density: no clipping, electron renormalization, or core addition."""
function context_valence_rho(ctx, n; electron_atol=1e-8)
    validate_context(ctx)
    length(n) == prod(ctx.basis.fft_size) && eltype(n) <: Real && all(isfinite, n) ||
        throw(ArgumentError("finite real valence density on the actual FFT grid required"))
    v = Float64.(vec(n))
    all(isfinite, v) || throw(ArgumentError("valence density is not finite Float64"))
    minimum(v) >= -64eps(Float64) * max(1, maximum(abs, v)) ||
        throw(ArgumentError("negative valence density exceeds the roundoff bound"))
    abs(sum(v) * ctx.basis.dvol - ctx.basis.model.n_electrons) <= electron_atol ||
        throw(ArgumentError("valence density does not integrate to the header-derived electron count"))
    reshape(v, ctx.basis.fft_size..., 1)
end

function build_full_hamiltonian(ctx, n)
    rho = context_valence_rho(ctx, n)
    # With no orbitals the temporary kinetic energy is Inf; only the Hamiltonian
    # is retained. This is construction of one fixed-density operator, not SCF.
    common = DFTK.energy_hamiltonian(ctx.basis, nothing, nothing; ρ=rho).ham
    (; common, full=compose_full_hamiltonian(ctx, common), rho)
end

"""Effect-based replacement check, also usable on explicit missing/double fault objects."""
function check_full_decomposition(H, common, fr, X; atol=1e-10)
    actual = H * X
    expected = common * X + fr * X
    all(isfinite, actual) && all(isfinite, expected) || throw(ArgumentError("nonfinite decomposition action"))
    err = norm(actual - expected) / max(norm(actual), norm(expected), 1)
    err <= atol || throw(ArgumentError("full-H action is not common plus one FR contribution (error=$err)"))
    (; normalized_error=err, nonlocal_signal_norm=norm(fr * X))
end
