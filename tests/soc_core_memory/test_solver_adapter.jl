# Synthetic Hermitian matrices only: bounded core callback ABI with frozen LOBPCG.
# This is not a material, physical Hamiltonian, SCF or endpoint execution.
using Test, Random, LinearAlgebra, JSON3
import DFTK, PseudoPotentialIO
const SOLVER_ADAPTER_ROOT=normpath(joinpath(@__DIR__,"../.."))
include(joinpath(SOLVER_ADAPTER_ROOT,"scripts/workbench_environment.jl"))
identity=WorkbenchEnvironment.environment_identity(SOLVER_ADAPTER_ROOT,(DFTK,PseudoPotentialIO))
identity.status=="PASS" || error("Frozen identity failed before synthetic solver test")
DFTK.disable_threading()
include(joinpath(SOLVER_ADAPTER_ROOT,"prototypes/spinor/SpinorPrototype.jl"))
const SK=SpinorPrototype.SOCKernels

# Test-only numeric adapter. All actual lifting goes through the new core;
# it neither builds a basis nor imports real-source provenance adapters.
struct SyntheticBoundedLift
    scalar::Matrix{ComplexF64}
    workspace::SK.ComponentWorkspace
    calls::Vector{NamedTuple}
end
Base.size(A::SyntheticBoundedLift)=(2size(A.scalar,1),2size(A.scalar,1))
Base.size(A::SyntheticBoundedLift,i::Integer)=i>0 ? (i<=2 ? size(A)[1] : 1) : throw(ArgumentError("Positive axis required"))
Base.eltype(::SyntheticBoundedLift)=ComplexF64
Base.eltype(::Type{SyntheticBoundedLift})=ComplexF64
function LinearAlgebra.mul!(Y::AbstractVecOrMat,A::SyntheticBoundedLift,X::AbstractVecOrMat,alpha::Number,beta::Number)
    SK.component_action!(Y,(out,input)->mul!(out,A.scalar,input),X,2,A.workspace,alpha,beta)
    push!(A.calls,(;rhs=size(X,2),rank=ndims(X),input_type=string(typeof(X))))
    Y
end
LinearAlgebra.mul!(Y::AbstractVecOrMat,A::SyntheticBoundedLift,X::AbstractVecOrMat)=mul!(Y,A,X,1,0)
Base.:*(A::SyntheticBoundedLift,X::AbstractVecOrMat)=mul!(similar(X,ComplexF64),A,X)

@testset "Frozen LOBPCG through bounded core on synthetic dense Hermitian scalar" begin
    rng=MersenneTwister(910306);ng=80;columns=30;target=24
    levels=collect(range(.5,20.;length=ng))
    Q=Matrix(qr(randn(rng,ComplexF64,ng,ng)).Q)
    scalar=Matrix(Hermitian(Q*Diagonal(levels)*Q'))
    saved_scalar=copy(scalar)
    A=SyntheticBoundedLift(scalar,SK.ComponentWorkspace(ng,columns,2),NamedTuple[])
    X0=Matrix(qr(randn(rng,ComplexF64,2ng,columns)).Q)[:,1:columns]
    saved_X0=copy(X0)
    @test norm(X0'X0-I)<=1e-11
    prec=SpinorPrototype.ComponentKineticPreconditioner(zeros(ng),2;shift=1.)
    result=DFTK.lobpcg_hyper(A,X0;prec,tol=1e-10,maxiter=300,miniter=1,n_conv_check=target)
    solver_calls=copy(A.calls);solver_stats=SK.workspace_stats(A.workspace)
    @test result.converged && result.n_iter>0
    @test size(result.X)==(2ng,columns) && length(result.λ)==columns
    @test !isempty(solver_calls) && maximum(x.rhs for x in solver_calls)<=columns
    @test all(1<=x.rhs<=columns && x.rank in (1,2) for x in solver_calls)
    @test solver_stats.action_calls==length(solver_calls)
    @test solver_stats.scalar_calls==2solver_stats.action_calls
    @test solver_stats.scalar_columns==2sum(x.rhs for x in solver_calls)
    @test X0==saved_X0 && scalar==saved_scalar
    x=result.X[:,1:target];lambda=result.λ[1:target]
    residual=A*x-x.*transpose(lambda)
    residual_max=maximum(norm(column) for column in eachcol(residual))
    gram=norm(x'x-I);value_error=maximum(abs.(lambda-repeat(levels[1:target÷2];inner=2)))
    @test isfinite(residual_max) && residual_max<=1e-9
    @test gram<=1e-9
    @test value_error<=1e-9
    # The very same workspace subsequently sees30 -> vector1 -> matrix24.
    # Dense kron is an independent synthetic oracle, never the kernel path.
    dense=kron(scalar,Matrix{ComplexF64}(I,2,2))
    for rhs in (X0,copy(X0[:,1]),copy(X0[:,1:24]))
        before=copy(rhs);Y=fill(ComplexF64(NaN,NaN),size(rhs))
        mul!(Y,A,rhs)
        @test norm(Y-dense*rhs)/max(norm(dense*rhs),1)<=1e-12
        @test rhs==before
    end
    rejected=ones(ComplexF64,2ng,31);Y=fill(ComplexF64(9),size(rejected));before=copy(Y)
    @test_throws DimensionMismatch mul!(Y,A,rejected)
    @test Y==before
    println(JSON3.write((;scope="SYNTHETIC_ONLY_FROZEN_LOBPCG_CORE_ABI",target_states=target,solver_columns=columns,
        solver_iterations=result.n_iter,solver_rhs_widths=sort(unique(r.rhs for r in solver_calls)),
        solver_input_types=sort(unique(r.input_type for r in solver_calls)),solver_call_count=length(solver_calls),
        residual_max,gram,constructed_spectrum_error=value_error,environment_status=identity.status,
        manifest_sha256=identity.manifest_sha256)))
end
