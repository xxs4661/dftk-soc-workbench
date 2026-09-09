"""Workspace-owned R/n/m, borrowed only until reset. No occupation/root solver.
No caller may retain the arrays across reuse unless it makes an explicit copy.
"""
mutable struct DensityWorkspace
    R::Array{ComplexF64,3}
    n::Vector{Float64}
    m::Union{Nothing,Matrix{Float64}}
    active::Bool
    failed::Bool
    accumulated_states::Int
    completed_densities::Int
end
function DensityWorkspace(ncomp,nr)
    n=_positive(ncomp,"Density component count");r=_positive(nr,"Real grid size")
    n in (1,2) || throw(ArgumentError("Density physics supports scalar or two-component spinors only"))
    DensityWorkspace(zeros(ComplexF64,n,n,r),zeros(r),n==2 ? zeros(3,r) : nothing,false,false,0,0)
end
workspace_stats(ws::DensityWorkspace)=(;ws.accumulated_states,ws.completed_densities)
function reset_workspace_counters!(ws::DensityWorkspace)
    ws.accumulated_states=ws.completed_densities=0;ws
end
function _density_buffers(ws)
    isnothing(ws.m) ? (ws.R,ws.n) : (ws.R,ws.n,ws.m)
end
function reset_density!(ws::DensityWorkspace)
    _no_overlap(_density_buffers(ws))
    ncomp=size(ws.R,1);nr=length(ws.n)
    size(ws.R)==(ncomp,ncomp,nr) && ncomp in (1,2) && nr>0 &&
        (ncomp==1 ? isnothing(ws.m) : !isnothing(ws.m) && size(ws.m)==(3,nr)) ||
        throw(DimensionMismatch("Density workspace storage changed"))
    fill!(ws.R,0);fill!(ws.n,0);isnothing(ws.m) || fill!(ws.m,0)
    ws.active=true;ws.failed=false;ws.accumulated_states=0;ws
end
function accumulate_density!(ws::DensityWorkspace,u::AbstractArray,weight,f::AbstractVector)
    ws.active && !ws.failed || throw(ArgumentError("Reset a valid density workspace before accumulation"))
    try
        Base.require_one_based_indexing(u,f)
        ndims(u)==3 && size(u,1)==size(ws.R,1) && size(u,2)==length(ws.n) && size(u,3)>0 ||
            throw(DimensionMismatch("Density amplitudes need (component,grid,state) axes"))
        all(isfinite,u) || throw(ArgumentError("Nonfinite real-space amplitudes"))
        _occupations(f,size(u,3);capacity=size(u,1)==1 ? 2.0 : 1.0)
        weight isa Real && isfinite(weight) && weight>=0 || throw(ArgumentError("Finite nonnegative spatial weight required"))
        _protect_scratch(_density_buffers(ws),(u,f))
        ncomp,nr=size(u,1),size(u,2)
        for state in axes(u,3)
            factor=weight*f[state]
            iszero(factor) && continue
            for r in 1:nr,b in 1:ncomp,a in 1:ncomp
                ws.R[a,b,r]+=factor*u[a,r,state]*conj(u[b,r,state])
            end
        end
        all(isfinite,ws.R) || throw(ArgumentError("Nonfinite accumulated density"))
        ws.accumulated_states+=size(u,3);ws
    catch
        ws.failed=true;ws.active=false;rethrow()
    end
end
function finish_density!(ws::DensityWorkspace)
    ws.active && !ws.failed && ws.accumulated_states>0 || throw(ArgumentError("No complete valid density accumulation"))
    try
        ncomp,nr=size(ws.R,1),length(ws.n)
        for r in 1:nr
            value=0.0
            for a in 1:ncomp;value+=real(ws.R[a,a,r]);end
            ws.n[r]=value
            if ncomp==2
                ws.m[1,r]=2real(ws.R[1,2,r]);ws.m[2,r]=-2imag(ws.R[1,2,r])
                ws.m[3,r]=real(ws.R[1,1,r]-ws.R[2,2,r])
            end
        end
        all(isfinite,ws.R) && all(isfinite,ws.n) && (isnothing(ws.m)||all(isfinite,ws.m)) ||
            throw(ArgumentError("Nonfinite completed density"))
        ws.active=false;ws.completed_densities+=1
        (;R=ws.R,n=ws.n,m=ws.m)
    catch
        ws.failed=true;ws.active=false;rethrow()
    end
end
