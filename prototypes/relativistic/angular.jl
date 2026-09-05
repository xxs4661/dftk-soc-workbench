# Complex Condon–Shortley harmonics are defined by the locked DFTK real solid
# harmonics, src/common/spherical_harmonics.jl. No frozen methods are changed.

function _angular_l(l)
    l isa Integer && !(l isa Bool) || throw(ArgumentError("l must be an integer"))
    0 <= l <= 3 || throw(ArgumentError("UNSUPPORTED: only l=0,1,2,3 angular channels are implemented"))
    Int(l)
end

function _angular_lm(l,m)
    l = _angular_l(l)
    m isa Integer && !(m isa Bool) && -l <= m <= l ||
        throw(ArgumentError("m must be an integer in -l:l"))
    l,Int(m)
end

function _angular_q(q)
    q isa AbstractVector && length(q)==3 || throw(DimensionMismatch("Angular argument needs three Cartesian coordinates"))
    all(x->x isa Real && isfinite(x),q) || throw(ArgumentError("Angular coordinates must be finite and real"))
    vector = Float64.(q)
    all(isfinite,vector) && isfinite(norm(vector)) || throw(ArgumentError("Angular coordinates overflow Float64"))
    vector
end

function _angular_jm(l,two_j,two_mj=nothing)
    l = _angular_l(l)
    two_j isa Integer && !(two_j isa Bool) || throw(ArgumentError("two_j must be an integer"))
    allowed = l==0 ? (1,) : (2l-1,2l+1)
    two_j in allowed || throw(ArgumentError("two_j violates the l±1/2 angular constraint"))
    if !isnothing(two_mj)
        two_mj isa Integer && !(two_mj isa Bool) &&
            -two_j <= two_mj <= two_j && iseven(two_mj+two_j) ||
            throw(ArgumentError("two_mj must be -two_j:2:two_j"))
    end
    l,Int(two_j)
end

"""
    real_to_complex_transform(l)

Rows and columns follow m=-l:l. Applied to DFTK's real solid-harmonic
values R, this gives complex CS values C=q^l Y: for m>0,
C_m=(-1)^m(R_m+iR_-m)/sqrt(2), C_-m=(R_m-iR_-m)/sqrt(2).
"""
function real_to_complex_transform(l)
    l = _angular_l(l)
    transform = zeros(ComplexF64,2l+1,2l+1)
    transform[l+1,l+1] = 1
    for m in 1:l
        phase = isodd(m) ? -1.0 : 1.0
        transform[l+m+1,l+m+1] = phase/sqrt(2)
        transform[l+m+1,l-m+1] = phase*im/sqrt(2)
        transform[l-m+1,l+m+1] = 1/sqrt(2)
        transform[l-m+1,l-m+1] = -im/sqrt(2)
    end
    transform
end

"""Return |q|^l Y_lm(qhat) in the complex Condon–Shortley convention."""
function complex_solid_harmonic(l,m,q)
    l,m = _angular_lm(l,m)
    vector = _angular_q(q)
    value = if m==0
        ComplexF64(DFTK.solid_harmonic_real(l,0,vector))
    else
        a = abs(m)
        positive = DFTK.solid_harmonic_real(l,a,vector)
        negative = DFTK.solid_harmonic_real(l,-a,vector)
        m>0 ? (isodd(m) ? -1.0 : 1.0)*(positive+im*negative)/sqrt(2) :
              (positive-im*negative)/sqrt(2)
    end
    isfinite(value) || throw(ArgumentError("Nonfinite complex solid harmonic"))
    ComplexF64(value)
end

function _cg_components(l,two_j,two_mj)
    l,two_j = _angular_jm(l,two_j,two_mj)
    m_up,m_down = (two_mj-1)÷2,(two_mj+1)÷2
    denominator = 2(2l+1)
    if two_j==2l+1
        c_up = sqrt((2l+two_mj+1)/denominator)
        c_down = sqrt((2l-two_mj+1)/denominator)
    else
        c_up = -sqrt((2l-two_mj+1)/denominator)
        c_down = sqrt((2l+two_mj+1)/denominator)
    end
    (;m_up,m_down,c_up,c_down)
end

"""
Return CG columns for ascending two_mj. Uncoupled rows are
sigma+2*(m+l), sigma=(up=1,down=2), m=-l:l.
"""
function cg_matrix(l,two_j)
    l,two_j = _angular_jm(l,two_j)
    result = zeros(ComplexF64,2(2l+1),two_j+1)
    for (column,two_mj) in enumerate(-two_j:2:two_j)
        c = _cg_components(l,two_j,two_mj)
        c.c_up!=0 && (result[1+2(c.m_up+l),column]=c.c_up)
        c.c_down!=0 && (result[2+2(c.m_down+l),column]=c.c_down)
    end
    result
end

"""
Return q^l times the (up,down) spin-angular function. It pairs directly with
the modified radial factor F(q)/q^l, and remains polynomial at q=0.
"""
function spin_angular_solid(l,two_j,two_mj,q)
    l,_ = _angular_jm(l,two_j,two_mj)
    vector = _angular_q(q)
    c = _cg_components(l,two_j,two_mj)
    result = zeros(ComplexF64,2)
    # End-point zero coefficients must not call nonexistent m harmonics.
    c.c_up!=0 && (result[1]=c.c_up*complex_solid_harmonic(l,c.m_up,vector))
    c.c_down!=0 && (result[2]=c.c_down*complex_solid_harmonic(l,c.m_down,vector))
    result
end

"""Ordinary spin-angular function for a nonzero direction; l=0 also permits zero."""
function spin_angular(l,two_j,two_mj,q)
    l,_ = _angular_jm(l,two_j,two_mj)
    vector = _angular_q(q)
    magnitude = norm(vector)
    if iszero(magnitude)
        l==0 || throw(DomainError(q,"A zero vector has no angular direction for l>0"))
        return spin_angular_solid(l,two_j,two_mj,vector)
    end
    spin_angular_solid(l,two_j,two_mj,vector/magnitude)
end
