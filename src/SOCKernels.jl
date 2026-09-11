"""Serial CPU numerical kernels with explicit arrays and bounded caller workspaces.

The module knows no materials, source files, project, run identities or DFTK.
Real-source authentication and fixed-session ownership belong to its adapter.
"""
module SOCKernels
using LinearAlgebra
export NonlocalData, NonlocalWorkspace, nonlocal_action!, nonlocal_expectation,
       projected_nonlocal_energy, ComponentWorkspace, component_action!,
       DensityWorkspace, reset_density!, accumulate_density!, finish_density!,
       validate_weights, workspace_stats, reset_workspace_counters!

_positive(x,label)=x isa Integer && !(x isa Bool) && x>0 ? Int(x) :
    throw(ArgumentError("$label must be a positive integer"))
function _scales(alpha,beta)
    alpha isa Number && beta isa Number && isfinite(alpha) && isfinite(beta) ||
        throw(ArgumentError("Finite alpha and beta required"))
    a,b=ComplexF64(alpha),ComplexF64(beta)
    isfinite(a) && isfinite(b) || throw(ArgumentError("Scales overflow ComplexF64"))
    a,b
end
function _no_overlap(arrays)
    for i in eachindex(arrays),j in firstindex(arrays):i-1
        Base.mightalias(arrays[i],arrays[j]) && throw(ArgumentError("Input/output/operator/workspace arrays may not overlap"))
    end
    nothing
end
function _protect_scratch(scratch,readers,writers=())
    _no_overlap(scratch)
    for buffer in scratch, input in readers
        Base.mightalias(buffer,input) && throw(ArgumentError("Workspace overlaps a numerical input"))
    end
    for output in writers
        for input in readers
            Base.mightalias(output,input) && throw(ArgumentError("Output overlaps numerical input or operator storage"))
        end
        for buffer in scratch
            Base.mightalias(output,buffer) && throw(ArgumentError("Output overlaps private workspace storage"))
        end
    end
    nothing
end
function _xy(Y,X,rows)
    Base.require_one_based_indexing(Y,X)
    size(Y)==size(X) && size(X,1)==rows && size(X,2)>0 ||
        throw(DimensionMismatch("Input/output must have the same correct nonempty shape"))
    eltype(Y)===ComplexF64 || throw(ArgumentError("Output must store ComplexF64 without narrowing"))
    eltype(X) in (Float64,ComplexF64) || throw(ArgumentError("Input must store Float64 or ComplexF64"))
    all(isfinite,X) || throw(ArgumentError("Nonfinite numerical input"))
    nothing
end
function _publish!(Y,candidate,a,b)
    ym=reshape(Y,size(Y,1),:)
    if iszero(b)
        for i in eachindex(candidate);candidate[i]=a*candidate[i];end
    else
        for i in eachindex(candidate);candidate[i]=a*candidate[i]+b*ym[i];end
    end
    all(isfinite,candidate) || throw(ArgumentError("Nonfinite numerical result; output not published"))
    copyto!(ym,candidate)
    Y
end
function _occupations(f,columns;capacity=1.0)
    f isa AbstractVector && length(f)==columns || throw(DimensionMismatch("One occupation per state required"))
    Base.require_one_based_indexing(f)
    all(v->v isa Real && isfinite(v) && 0<=v<=capacity,f) ||
        throw(ArgumentError("Finite occupations within explicit capacity required"))
    nothing
end
function validate_weights(weights,count;atol=1e-11)
    atol isa Real && isfinite(atol) && atol>0 || throw(ArgumentError("Positive finite weight tolerance required"))
    length(weights)==count && count>0 || throw(DimensionMismatch("One weight per k required"))
    all(w->w isa Real && isfinite(w) && w>=0,weights) && abs(sum(weights)-1)<=atol ||
        throw(ArgumentError("Spatial weights must sum to one; no normalization"))
    true
end
include("soc_kernels/nonlocal.jl")
include("soc_kernels/components.jl")
include("soc_kernels/density.jl")
end
