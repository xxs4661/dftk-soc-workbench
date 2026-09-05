# Stable modified-Hankel transform with the frozen DFTK physical-grid quadrature.
# The frozen hankel small-q guard is only 10eps; its sphericalbesselj_fast source
# warns about cancellation near zero. Evaluate jl(x)/x^l by its convergent series
# below |x|=.5, retaining q² corrections instead of replacing a neighborhood by a limit.
function _scaled_spherical_bessel(l::Int,x::Float64)
    if abs(x) <= 0.5
        term = inv(Float64(prod(1:2:2l+1))); value = term
        for k in 1:64
            term *= -x^2/(2k*(2l+2k+1))
            value += term
            abs(term) <= eps(Float64)*abs(value) && return value
        end
        error("Scaled spherical Bessel series did not converge")
    end
    DFTK.sphericalbesselj_fast(l,x)/x^l
end

"""F(q)/q^l = 4pi integral r*b_internal(r)*r^l*[jl(qr)/(qr)^l] dr."""
function radial_modified(model::ChannelModel,index::Integer,q::Real)
    isfinite(q) && q >= 0 || channel_fail("Radial wave-vector magnitude must be finite and nonnegative")
    c = model.channels[index]
    r = @view c.r[1:c.cutoff_radius_index]
    b = @view c.beta_internal[1:c.cutoff_radius_index]
    isfinite(Float64(q)*last(r)) || channel_fail("Radial qr exceeds finite Float64 range")
    quadrature = DFTK.default_psp_quadrature(r)
    result = 4π*quadrature(r) do i,ri
        ri*b[i]*ri^c.l*_scaled_spherical_bessel(c.l,Float64(q)*ri)
    end
    isfinite(result) || channel_fail("Nonfinite radial transform")
    Float64(result)
end

"""Full F(q), including 4pi but no spherical harmonic, phase or cell-volume factor."""
function radial_factor(model::ChannelModel,index::Integer,q::Real)
    modified = radial_modified(model,index,q)
    l = model.channels[index].l
    value = iszero(q) && l > 0 ? 0.0 : Float64(q)^l*modified
    isfinite(value) || channel_fail("Nonfinite full radial transform")
    value
end

"""Compact public radial provenance; no raw radial arrays are included."""
function channel_summary(model::ChannelModel)
    [(;channel_position=i,source_beta_index=c.source_beta_index,
       parsed_beta_position=c.parsed_beta_position,relbeta_source_index=c.relbeta_source_index,
       l=c.l,two_j=c.two_j,radial_projector=c.radial_projector,
       cutoff_radius_index=c.cutoff_radius_index,cutoff_bohr=c.cutoff_bohr,
       radial_grid_points=length(c.r),parsed_beta_points=length(c.beta_raw),
       r_first_bohr=first(c.r),r_last_bohr=last(c.r),
       tail_after_declared_cutoff="Checked exactly zero (or absent if beta ends at cutoff)",
       quadrature=string(nameof(DFTK.default_psp_quadrature(@view c.r[1:c.cutoff_radius_index]))),
       origin="Physical grid starts at recorded r_first; no extrapolated samples, no division by r",
       normalization="None; PP_RAB is not multiplied into a physical-grid quadrature",
       unit_convention=string(model.unit_convention)) for (i,c) in enumerate(model.channels)]
end
