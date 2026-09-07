struct ChannelError <: Exception
    status::String
    reason::String
end
Base.showerror(io::IO, e::ChannelError) = print(io, e.status, ": ", e.reason)
channel_fail(reason) = throw(ChannelError("FAIL", reason))
channel_unsupported(reason) = throw(ChannelError("UNSUPPORTED", reason))

struct RadialChannel
    source_beta_index::Int
    parsed_beta_position::Int
    relbeta_source_index::Union{Nothing,Int}
    l::Int
    two_j::Int
    radial_projector::Int
    r::Vector{Float64}
    beta_raw::Vector{Float64}
    beta_internal::Vector{Float64}
    cutoff_radius_index::Int
    cutoff_bohr::Float64
end

struct ChannelModel
    channels::Vector{RadialChannel}
    D::Matrix{ComplexF64}
    D_raw_parsed::Matrix{ComplexF64}
    unit_convention::Symbol
    provenance
end

function _paired_scales(convention)
    convention == :dftk && return (0.5, 2.0)
    convention == :alternative && return (1.0, 0.5)
    channel_unsupported("Unknown beta/D paired unit convention")
end

function _valid_lj(l, two_j)
    l isa Integer && !(l isa Bool) && l >= 0 || channel_fail("Invalid l")
    l <= 3 || channel_unsupported("Prototype supports l=0,1,2,3 only")
    two_j isa Integer && !(two_j isa Bool) || channel_fail("two_j must be an integer")
    two_j in (l == 0 ? (1,) : (2l-1,2l+1)) || channel_fail("two_j violates l constraints")
end

function _checked_radial(record)
    r, beta, cutoff = record.r, record.beta_raw, record.cutoff_index
    r isa AbstractVector && beta isa AbstractVector && length(r) >= 2 ||
        channel_fail("Missing radial grid or beta array")
    all(x -> x isa Real && isfinite(x),r) && first(r) >= 0 && all(>(0),diff(r)) ||
        channel_fail("Radial grid must be finite, nonnegative and strictly increasing")
    all(x -> x isa Real && isfinite(x),beta) || channel_fail("Nonfinite/nonreal PP_BETA data")
    length(beta) <= length(r) || channel_fail("Beta data exceeds radial mesh length")
    cutoff isa Integer && !(cutoff isa Bool) && 2 <= cutoff <= length(beta) ||
        channel_fail("Missing or out-of-range cutoff index")
    # Missing samples between a short beta and its declared support are not guessed.
    length(beta) in (cutoff,length(r)) ||
        channel_unsupported("Beta length is neither its declared cutoff nor the complete mesh")
    all(iszero,@view beta[cutoff+1:end]) ||
        channel_unsupported("Nonzero beta beyond cutoff; truncation is not justified")
    if hasproperty(record,:cutoff_radius) && !isnothing(record.cutoff_radius)
        radius = record.cutoff_radius
        radius isa Real && isfinite(radius) && radius >= 0 || channel_fail("Invalid cutoff radius")
        isapprox(radius,r[cutoff];atol=1e-10,rtol=0) ||
            channel_unsupported("Cutoff radius and cutoff-index mesh point disagree")
    end
    Float64.(r),Float64.(beta),Int(cutoff)
end

function _checked_d(D,n)
    D isa AbstractMatrix && size(D) == (n,n) || channel_fail("D shape does not match parsed beta positions")
    all(x -> x isa Number && isfinite(x),D) || channel_fail("Nonfinite D")
    norm(D-adjoint(D))/max(norm(D),1) <= 1e-12 || channel_fail("D is not Hermitian within 1e-12")
    ComplexF64.(D)  # Copy only; do not symmetrize or discard off-diagonal entries.
end

function _assemble_channels(records, D_raw; unit_convention=:dftk, provenance=(; synthetic=true),
                            repeated_source_positions=false)
    isempty(records) && channel_fail("No radial channels")
    beta_scale,d_scale = _paired_scales(unit_convention)
    nraw = size(D_raw,1)
    raw = _checked_d(D_raw,nraw)
    positions = [r.parsed_position for r in records]
    all(p -> p isa Integer && !(p isa Bool) && 1 <= p <= nraw,positions) ||
        channel_fail("Parsed beta position is outside D")
    if !repeated_source_positions
        length(records) == nraw && Set(positions) == Set(1:nraw) ||
            channel_fail("Parsed beta positions have duplicates or omissions")
        ids = [r.source_index for r in records]
        all(i -> i isa Integer && !(i isa Bool) && i > 0,ids) && length(unique(ids)) == nraw ||
            channel_fail("Duplicate/missing source beta indices")
    end
    for r in records
        _valid_lj(r.l,r.two_j)
    end
    ordered = sort(collect(records);by=r->(r.l,r.two_j,r.parsed_position))
    channels = RadialChannel[]
    counts = Dict{Tuple{Int,Int},Int}()
    for rec in ordered
        r,beta,cutoff = _checked_radial(rec)
        key = (Int(rec.l),Int(rec.two_j)); radial = get(counts,key,0)+1; counts[key] = radial
        relid = hasproperty(rec,:relbeta_source_index) ? rec.relbeta_source_index : rec.source_index
        push!(channels,RadialChannel(rec.source_index,rec.parsed_position,relid,rec.l,rec.two_j,
            radial,r,beta,beta_scale.*beta,cutoff,r[cutoff]))
    end
    internal = zeros(ComplexF64,length(channels),length(channels))
    for (i,a) in enumerate(channels), (j,b) in enumerate(channels)
        value = raw[a.parsed_beta_position,b.parsed_beta_position]
        same_block = (a.l,a.two_j) == (b.l,b.two_j)
        if same_block
            internal[i,j] = d_scale*value
        elseif !repeated_source_positions && !iszero(value)
            channel_unsupported("Nonzero D coupling between distinct (l,j) blocks at parsed positions $(a.parsed_beta_position),$(b.parsed_beta_position)")
        end
    end
    ChannelModel(channels,internal,raw,unit_convention,provenance)
end

"""Explicit in-memory test fixture, never a physical UPF or a modified parsed input."""
synthetic_channel_model(records,D;unit_convention=:dftk,provenance=(;synthetic=true)) =
    _assemble_channels(records,D;unit_convention,provenance)

"""Real FR-NC channels; source IDs associate metadata, parsed positions index D."""
function channel_model(parsed;unit_convention=:dftk)
    parsed isa PseudoPotentialIO.UpfFile || channel_fail("Expected UpfFile")
    metadata = UpfRuntime.metadata_from_upf(parsed)
    validation = UpfValidation.validate_metadata(metadata)
    validation.status == "PASS" || throw(ChannelError(validation.status,join(validation.reasons,"; ")))
    # Existing validation has already checked finite j against legal values without rounding.
    rel = Dict(r.index=>r for r in parsed.spin_orb.relbetas)
    records = map(enumerate(parsed.nonlocal.betas)) do (position,beta)
        l = beta.angular_momentum; r = rel[beta.index]
        allowed = l == 0 ? (1,) : (2l-1,2l+1)
        tj = only(filter(t->isapprox(r.jjj,t/2;atol=UpfValidation.J_ATOL,rtol=0),allowed))
        (;source_index=beta.index,parsed_position=position,relbeta_source_index=r.index,l,two_j=tj,
          r=parsed.mesh.r,beta_raw=beta.beta,cutoff_index=beta.cutoff_radius_index,
          cutoff_radius=beta.cutoff_radius)
    end
    _assemble_channels(records,parsed.nonlocal.dij;unit_convention,
        provenance=(;synthetic=false,input_kind="real FR-NC UpfFile",metadata_status=validation.status,
          beta_semantics="PP_BETA stores r*beta; source index is metadata only; parsed order indexes D",
          parser_pruning="Rejected as UNSUPPORTED by unchanged metadata validator when declared/parsed counts differ"))
end
fr_channels(args...;kwargs...) = channel_model(args...;kwargs...)

"""Complete artificial j branches copied from scalar radial/D blocks; never a real FR file."""
function synthetic_scalar_degenerate(parsed;unit_convention=:dftk)
    parsed isa PseudoPotentialIO.UpfFile || channel_fail("Expected scalar UpfFile")
    h = parsed.header
    h.pseudo_type == "NC" && h.has_so === false && h.relativistic == "scalar" ||
        channel_fail("Synthetic scalar limit requires actual scalar NC input; FR channels are never averaged")
    betas = parsed.nonlocal.betas; n = length(betas)
    n == h.number_of_proj || channel_unsupported("Scalar parser pruning is not supported")
    ids = [b.index for b in betas]
    all(i->i isa Integer && 1 <= i <= n,ids) && length(unique(ids)) == n ||
        channel_unsupported("Scalar source indices cannot be explicitly mapped")
    raw = _checked_d(parsed.nonlocal.dij,n)
    for i in 1:n,j in 1:n
        betas[i].angular_momentum == betas[j].angular_momentum || iszero(raw[i,j]) ||
            channel_unsupported("Nonzero scalar D coupling between distinct l blocks")
    end
    records = NamedTuple[]
    for (position,beta) in enumerate(betas)
        l = beta.angular_momentum
        for tj in (l == 0 ? (1,) : (2l-1,2l+1))
            _valid_lj(l,tj)
            push!(records,(;source_index=beta.index,parsed_position=position,relbeta_source_index=nothing,
                l,two_j=tj,r=parsed.mesh.r,beta_raw=beta.beta,cutoff_index=beta.cutoff_radius_index,
                cutoff_radius=beta.cutoff_radius))
        end
    end
    _assemble_channels(records,raw;unit_convention,repeated_source_positions=true,
        provenance=(;synthetic=true,input_kind="Real scalar NC UPF expanded into complete synthetic degenerate j branches",
          duplication="Same radial functions and same D block in each allowed j branch; no averaging"))
end
scalar_degenerate_channels(args...;kwargs...) = synthetic_scalar_degenerate(args...;kwargs...)
