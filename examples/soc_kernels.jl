#!/usr/bin/env julia
# Run by absolute script path from any directory, including one without .git/.work.
# Synthetic complex matrices only; this is not a pseudopotential or material test.
using LinearAlgebra
include(joinpath(@__DIR__,"../src/SOCKernels.jl"))
using .SOCKernels

P=ComplexF64[1 .2im; .4+.1im -.3; -.2im .7; .3 -.5im]
D=ComplexF64[1 .2+.3im; .2-.3im -.4]
X=ComplexF64[.2 .5im; -.3im .7; .8 .1-.2im; -.4 .6im]
# Mapping is explicit input data, not discovered from a case or repository.
row_mapping=[3,4,1,2]
owned=NonlocalData(P[row_mapping,:],D;labels=(:synthetic_a,:synthetic_b))
ws=NonlocalWorkspace(4,2,2);Y=fill(ComplexF64(NaN),size(X))
nonlocal_action!(Y,owned,X[row_mapping,:],ws)
reference=(P*D*P'*X)[row_mapping,:]
relative_error=norm(Y-reference)/max(norm(Y),norm(reference),1)
relative_error<=1e-12 || error("Synthetic nonlocal example differs from its dense oracle")
f=[.8,.2]
full=nonlocal_expectation(owned,X[row_mapping,:],f,1.,ws)
projected=projected_nonlocal_energy(owned,X[row_mapping,:],f,1.,ws)
abs(full-projected)<=1e-12 || error("Two synthetic expectation contractions differ")
println("Synthetic reusable core: relative error=",relative_error,", expectation difference=",full-projected)
println("No source authentication or physical-material claim is made by this example.")
