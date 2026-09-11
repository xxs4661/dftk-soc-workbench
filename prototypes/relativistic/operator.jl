# Explicit optimized adapters below use one stage-independent parent module.
# This happens only at module loading, never inside a numerical kernel.
if !isdefined(parentmodule(@__MODULE__), :SOCKernels)
    Base.include(parentmodule(@__MODULE__), joinpath(@__DIR__, "../../src/SOCKernels.jl"))
end
import ..SOCKernels

# Independent component-interleaved nonlocal operator. No Hamiltonian/SCF patch.

"""One canonical table shared by P and expanded D: atom,l,2j,2mj,radial."""
function projector_labels(model, natoms::Integer)
    natoms > 0 && !(natoms isa Bool) || throw(ArgumentError("Positive atom count required"))
    groups = sort(unique((c.l,c.two_j) for c in model.channels))
    labels = NamedTuple[]
    for atom in 1:natoms, (l,two_j) in groups, two_mj in -two_j:2:two_j
        indices = findall(c->c.l==l && c.two_j==two_j,model.channels)
        sort!(indices;by=i->model.channels[i].radial_projector)
        for i in indices
            push!(labels,(;atom,l,two_j,two_mj,
                radial_projector=model.channels[i].radial_projector,channel_position=i))
        end
    end
    labels
end

function _check_projector_labels(model,labels,natoms)
    expected=projector_labels(model,natoms)
    length(labels)==length(expected) && Set(labels)==Set(expected) ||
        throw(ArgumentError("Column labels must include each atom/channel/mj exactly once"))
    length(Set(labels))==length(labels) || throw(ArgumentError("Duplicate column label"))
    nothing
end

"""Expand only same-atom/l/j/mj radial couplings; never multiply by degeneracy."""
function expanded_coupling(model,labels)
    isempty(labels) && throw(ArgumentError("Nonempty projector labels required"))
    natoms=maximum(label.atom for label in labels)
    _check_projector_labels(model,labels,natoms)
    d=zeros(ComplexF64,length(labels),length(labels))
    for (i,a) in enumerate(labels), (j,b) in enumerate(labels)
        if (a.atom,a.l,a.two_j,a.two_mj)==(b.atom,b.l,b.two_j,b.two_mj)
            d[i,j]=model.D[a.channel_position,b.channel_position]
        end
    end
    d
end

function _check_cartesian_vectors(vectors,label)
    isempty(vectors) && throw(ArgumentError("$label must be nonempty"))
    all(v->v isa AbstractVector && length(v)==3 &&
           all(x->x isa Real && isfinite(x),v),vectors) ||
        throw(ArgumentError("$label must contain finite Cartesian three-vectors"))
end

"""
Build P in rows sigma+2*(G-1), using Cartesian q [bohr^-1], R [bohr],
and volume [bohr^3]. The production radial function returns F/q^l;
spin_angular_solid supplies q^l*Omega, including the finite l=0 origin.
Thus no extra 4pi or q^l occurs here. All l>0 origin entries are zero.
"""
function build_projectors(model,qcart,positions_cart,volume;
                          labels=projector_labels(model,length(positions_cart)))
    _check_cartesian_vectors(qcart,"Wavevectors")
    _check_cartesian_vectors(positions_cart,"Atomic positions")
    volume isa Real && isfinite(volume) && volume>0 || throw(ArgumentError("Positive finite volume required"))
    _check_projector_labels(model,labels,length(positions_cart))
    p=zeros(ComplexF64,2length(qcart),length(labels))
    # Cache only rectangular channel-by-q radial factors, not a square PW kernel.
    radial=[radial_modified(model,i,norm(q)) for i in eachindex(model.channels), q in qcart]
    all(isfinite,radial) || error("Nonfinite radial projector factor")
    for (column,label) in enumerate(labels), (iq,q) in enumerate(qcart)
        angular=spin_angular_solid(label.l,label.two_j,label.two_mj,q)
        phase=cis(-dot(q,positions_cart[label.atom]))*(-im)^label.l/sqrt(volume)
        p[2iq-1:2iq,column]=phase*radial[label.channel_position,iq]*angular
    end
    all(isfinite,p) || error("Nonfinite spin-angular projector")
    p
end

"""
Rectangular-P nonlocal operator V=P*D*P'. Construction owns copies of P and D.
mul! explicitly rejects input/output overlap, and never reads Y when beta=0.
No production operation assembles the square 2NG-by-2NG kernel.
"""
struct FRNonlocalOperator{L}
    P::Matrix{ComplexF64}
    D::Matrix{ComplexF64}
    labels::L
end

function FRNonlocalOperator(P::AbstractMatrix,D::AbstractMatrix;labels=nothing)
    size(P,1)>0 && size(P,2)>0 || throw(DimensionMismatch("Nonempty rectangular P required"))
    size(D)==(size(P,2),size(P,2)) || throw(DimensionMismatch("D must act on the P columns"))
    all(isfinite,P) && all(isfinite,D) || throw(ArgumentError("Nonfinite P or D"))
    p,d=Matrix{ComplexF64}(P),Matrix{ComplexF64}(D)
    all(isfinite,p) && all(isfinite,d) || throw(ArgumentError("P or D is nonfinite after ComplexF64 conversion"))
    norm(d-d')<=1e-12*max(norm(d),1) || throw(ArgumentError("D must be Hermitian; no symmetrization is applied"))
    isnothing(labels) || length(labels)==size(P,2) || throw(DimensionMismatch("Label count differs from P columns"))
    owned_labels=isnothing(labels) ? nothing : copy(labels)
    FRNonlocalOperator{typeof(owned_labels)}(p,d,owned_labels)
end

function build_nonlocal_operator(model,qcart,positions_cart,volume)
    labels=projector_labels(model,length(positions_cart))
    P=build_projectors(model,qcart,positions_cart,volume;labels)
    D=expanded_coupling(model,labels)
    FRNonlocalOperator(P,D;labels)
end

Base.size(A::FRNonlocalOperator)=(size(A.P,1),size(A.P,1))
function Base.size(A::FRNonlocalOperator,dimension::Integer)
    dimension>0 || throw(ArgumentError("Dimension must be positive"))
    dimension<=2 ? size(A.P,1) : 1
end
Base.eltype(::Type{<:FRNonlocalOperator})=ComplexF64
Base.eltype(::FRNonlocalOperator)=ComplexF64

function LinearAlgebra.mul!(Y::AbstractVecOrMat,A::FRNonlocalOperator,X::AbstractVecOrMat,
                            alpha::Number,beta::Number)
    Base.require_one_based_indexing(Y,X)
    size(Y)==size(X) && size(X,1)==size(A,1) || throw(DimensionMismatch("Nonlocal input/output dimensions differ"))
    eltype(Y)==ComplexF64 || throw(ArgumentError("Nonlocal output must store ComplexF64 without narrowing"))
    (Base.mightalias(Y,X) || Base.mightalias(Y,A.P) || Base.mightalias(Y,A.D)) &&
        throw(ArgumentError("Nonlocal output may not alias its input or operator storage"))
    all(isfinite,X) && isfinite(alpha) && isfinite(beta) || throw(ArgumentError("Nonfinite nonlocal input or coefficient"))
    iszero(beta) || all(isfinite,Y) || throw(ArgumentError("Nonfinite beta-weighted output input"))
    result=alpha.*(A.P*(A.D*(A.P'*X)))
    iszero(beta) || (result .+= beta.*Y)
    all(isfinite,result) || throw(ArgumentError("Nonfinite nonlocal result"))
    Y .= result
    Y
end
LinearAlgebra.mul!(Y::AbstractVecOrMat,A::FRNonlocalOperator,X::AbstractVecOrMat)=mul!(Y,A,X,true,false)
function Base.:*(A::FRNonlocalOperator,X::AbstractVecOrMat)
    Y=similar(X,ComplexF64)
    mul!(Y,A,X)
end

function _check_nonlocal_energy(operators,X,weights,f)
    length(operators)==length(X)==length(weights)==length(f)>0 || throw(DimensionMismatch("One operator/state/weight/occupation set per k point required"))
    all(w->w isa Real && isfinite(w) && w>=0,weights) && abs(sum(weights)-1)<=1e-12 ||
        throw(ArgumentError("Spatial weights must sum to one without normalization"))
    for (A,x,occ) in zip(operators,X,f)
        x isa AbstractMatrix && size(x,1)==size(A,1) && length(occ)==size(x,2) ||
            throw(DimensionMismatch("Nonlocal energy orbital/occupation dimensions differ"))
        all(isfinite,x) && all(v->v isa Real && isfinite(v) && 0<=v<=1,occ) ||
            throw(ArgumentError("Finite spinors with capacity-one occupations required"))
    end
end

"""Occupied nonlocal expectation [Ha]; this is not a DFT total energy."""
function nonlocal_energy(operators,X,weights,f)
    _check_nonlocal_energy(operators,X,weights,f)
    total=0.0
    for (A,x,w,occ) in zip(operators,X,weights,f)
        vx=A*x
        total+=w*sum(occ[n]*real(dot(x[:,n],vx[:,n])) for n in axes(x,2))
    end
    isfinite(total) || error("Nonfinite nonlocal energy")
    total
end

"""Independent contraction in projector coefficient space, using P'X and D."""
function projected_nonlocal_energy(operators,X,weights,f)
    _check_nonlocal_energy(operators,X,weights,f)
    total=0.0
    for (A,x,w,occ) in zip(operators,X,weights,f)
        coefficients=A.P'*x
        weighted=A.D*coefficients
        for n in axes(x,2), i in axes(coefficients,1)
            total+=w*occ[n]*real(conj(coefficients[i,n])*weighted[i,n])
        end
    end
    isfinite(total) || error("Nonfinite projected nonlocal energy")
    total
end
nonlocal_energy(A::FRNonlocalOperator,X::AbstractMatrix,f)=nonlocal_energy([A],[X],[1.0],[f])
projected_nonlocal_energy(A::FRNonlocalOperator,X::AbstractMatrix,f)=projected_nonlocal_energy([A],[X],[1.0],[f])

# Opt-in numeric adapter. Legacy FRNonlocalOperator type/default mul! is unchanged.
# Runtime-owned P/D can be borrowed synchronously without a second retained copy.
function kernel_nonlocal_action!(Y,A::FRNonlocalOperator,X,workspace,alpha=1,beta=0)
    SOCKernels.nonlocal_action!(Y,A.P,A.D,X,workspace,alpha,beta)
end
kernel_owned_data(A::FRNonlocalOperator)=SOCKernels.NonlocalData(A.P,A.D;labels=A.labels)
