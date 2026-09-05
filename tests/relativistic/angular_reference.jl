# Independent small-matrix mathematical references. This file intentionally
# never calls DFTK real harmonics or production CG/spin-angular/projector code.
# Associated Legendre functions include the Condon–Shortley (-1)^m phase.

function independent_Ylm(l,m,q)
    0<=l<=3 && -l<=m<=l || throw(ArgumentError("Reference harmonic label out of range"))
    length(q)==3 && all(isfinite,q) || throw(ArgumentError("Invalid reference direction"))
    l==0 && return ComplexF64(1/sqrt(4π))
    radius = sqrt(sum(abs2,q))
    radius>0 || throw(DomainError(q,"Ordinary harmonic reference needs a nonzero direction"))
    a = abs(m)
    z = q[3]/radius
    # sin(theta) is computed from x,y to avoid cancellation near the poles.
    sin_theta = hypot(q[1],q[2])/radius
    pmm = 1.0
    for i in 1:a
        pmm *= -(2i-1)*sin_theta
    end
    plm = pmm
    if l>a
        previous,plm = pmm,(2a+1)*z*pmm
        for degree in (a+2):l
            previous,plm = plm,((2degree-1)*z*plm-(degree+a-1)*previous)/(degree-a)
        end
    end
    normalization = sqrt((2l+1)/(4π)*factorial(l-a)/factorial(l+a))
    value = normalization*plm*cis(a*atan(q[2],q[1]))
    ComplexF64(m<0 ? (isodd(a) ? -1 : 1)*conj(value) : value)
end

function independent_solid_harmonic(l,m,q)
    radius = sqrt(sum(abs2,q))
    iszero(radius) && l>0 && return 0.0+0.0im
    radius^l*independent_Ylm(l,m,q)
end

"""Ladder-operator reference in m-major, (up,down) uncoupled order; no CG."""
function independent_angular_matrices(l)
    0<=l<=3 || throw(ArgumentError("Unsupported reference l"))
    n = 2l+1
    Lplus = zeros(ComplexF64,n,n)
    for m in -l:(l-1)
        Lplus[m+l+2,m+l+1] = sqrt(l*(l+1)-m*(m+1))
    end
    Lminus = Lplus'
    Lx,Ly = (Lplus+Lminus)/2,(Lplus-Lminus)/(2im)
    Lz = Diagonal(ComplexF64.(collect(-l:l)))
    Sx = ComplexF64[0 1;1 0]/2
    Sy = ComplexF64[0 -im;im 0]/2
    Sz = ComplexF64[1 0;0 -1]/2
    Iorb,Id = Matrix{ComplexF64}(I,n,n),Matrix{ComplexF64}(I,2n,2n)
    LdotS = kron(Lx,Sx)+kron(Ly,Sy)+kron(Lz,Sz)
    Jz = kron(Lz,Matrix{ComplexF64}(I,2,2))+kron(Iorb,Sz)
    Jminus = kron(Lminus,Matrix{ComplexF64}(I,2,2))+kron(Iorb,Sx-im*Sy)
    J2 = (l*(l+1)+3/4)*Id+2LdotS
    Pi_plus = (2LdotS+(l+1)*Id)/(2l+1)
    Pi_minus = l==0 ? zeros(ComplexF64,2,2) : (l*Id-2LdotS)/(2l+1)
    (;LdotS,Jz,J2,Jminus,Pi_plus,Pi_minus)
end

"""Coupled columns from highest-weight projection and J lowering, never production CG."""
function independent_cg_ladder(l,two_j)
    two_j in (l==0 ? (1,) : (2l-1,2l+1)) || throw(ArgumentError("Invalid reference j branch"))
    matrices = independent_angular_matrices(l)
    result = zeros(ComplexF64,2(2l+1),two_j+1)
    if two_j==2l+1
        result[1+4l,end] = 1  # |m=l,up> fixes the plus-branch phase.
    else
        # Project |m=l-1,up> onto j-, choosing its upper coefficient negative.
        seed = -matrices.Pi_minus[:,1+2(2l-1)]
        result[:,end] = seed/norm(seed)
    end
    j = two_j/2
    for column in (two_j+1):-1:2
        M = (-two_j+2(column-1))/2
        result[:,column-1] = matrices.Jminus*result[:,column]/sqrt((j+M)*(j-M+1))
    end
    result
end

"""
    independent_kernel(model,qcart,positions_cart,volume;radial)

Small-only (at most 128 q vectors) nonlocal matrix built by direct uncoupled
Y_lm/ladder-Pi_j/radial-D contraction. `radial(model,index,q)` supplies full
F(q), including 4pi but excluding angular/phase/volume factors. No production
CG or P is used. Synthetic tests may supply analytic radial transforms; real
Mg checks can share the declared radial discretization while independently
checking the angular kernel. This is not an independent radial quadrature.
"""
function independent_kernel(model,qcart,positions_cart,volume;radial)
    0<length(qcart)<=128 || throw(ArgumentError("Independent dense kernel is limited to 1:128 probe vectors"))
    volume>0 && isfinite(volume) || throw(ArgumentError("Invalid reference volume"))
    all(q->length(q)==3 && all(isfinite,q),qcart) || throw(ArgumentError("Invalid reference q vectors"))
    all(r->length(r)==3 && all(isfinite,r),positions_cart) || throw(ArgumentError("Invalid reference atom positions"))
    nc = length(model.channels)
    size(model.D)==(nc,nc) || throw(DimensionMismatch("Reference coupling shape mismatch"))
    for i in 1:nc,j in 1:nc
        ci,cj = model.channels[i],model.channels[j]
        (ci.l,ci.two_j)==(cj.l,cj.two_j) || iszero(model.D[i,j]) ||
            throw(ArgumentError("Reference cannot discard cross-(l,j) coupling"))
    end
    nq = length(qcart)
    result = zeros(ComplexF64,2nq,2nq)
    blocks = unique([(c.l,c.two_j) for c in model.channels])
    magnitudes = norm.(qcart)
    for (l,two_j) in blocks
        indices = findall(c->c.l==l && c.two_j==two_j,model.channels)
        matrices = independent_angular_matrices(l)
        Pi = two_j==2l+1 ? matrices.Pi_plus : matrices.Pi_minus
        iseven(two_j) && throw(ArgumentError("Reference two_j must be odd"))
        two_j in (l==0 ? (1,) : (2l-1,2l+1)) || throw(ArgumentError("Invalid reference j branch"))
        harmonics = map(eachindex(qcart)) do iq
            W = zeros(ComplexF64,2,2(2l+1))
            if magnitudes[iq]>0 || l==0
                for m in -l:l,spin in 1:2
                    W[spin,spin+2(m+l)] = independent_Ylm(l,m,qcart[iq])
                end
            end
            W
        end
        radial_values = [radial(model,index,magnitudes[iq]) for index in indices,iq in 1:nq]
        all(isfinite,radial_values) || throw(ArgumentError("Nonfinite reference radial values"))
        for R in positions_cart,iq in 1:nq,jq in 1:nq
            # l is the same on both sides of a spherical (l,j) block, so the
            # Fourier (-i)^l phases cancel. Their direct P values need a
            # separate extremal-mj test, provided by the operator tests.
            radial_sum = sum(radial_values[a,iq]*model.D[ia,ib]*conj(radial_values[b,jq])
                             for (a,ia) in enumerate(indices),(b,ib) in enumerate(indices))
            phase = cis(-dot(qcart[iq],R))*cis(dot(qcart[jq],R))/volume
            result[(2iq-1):2iq,(2jq-1):2jq] .+= phase*radial_sum*(harmonics[iq]*Pi*harmonics[jq]')
        end
    end
    all(isfinite,result) || throw(ArgumentError("Nonfinite independent kernel"))
    result
end
