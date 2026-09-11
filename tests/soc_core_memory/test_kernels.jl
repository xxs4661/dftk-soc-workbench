# Synthetic algebra and optional frozen-DFTK FFT adapter tests, never physical evidence.
using Test, Random, LinearAlgebra
include(joinpath(@__DIR__,"../../src/SOCKernels.jl"))
using .SOCKernels
const KERNEL_ROOT=normpath(joinpath(@__DIR__,"../.."))
relative_error(a,b)=norm(a-b)/max(norm(a),norm(b),1)

# Deliberately independent explicit sum: no call to any production contraction.
function dense_oracle(P,D)
    result=zeros(ComplexF64,size(P,1),size(P,1))
    for j in axes(result,2),i in axes(result,1),b in axes(D,2),a in axes(D,1)
        result[i,j]+=P[i,a]*D[a,b]*conj(P[j,b])
    end
    result
end
function density_oracle(states,weights,occupations)
    ncomp,nr=size(first(states),1),size(first(states),2)
    R=zeros(ComplexF64,ncomp,ncomp,nr)
    for ik in eachindex(states),state in axes(states[ik],3),r in 1:nr
        vector=states[ik][:,r,state]
        R[:,:,r].+=weights[ik]*occupations[ik][state].*(vector*vector')
    end
    n=[real(tr(R[:,:,r])) for r in 1:nr]
    m=ncomp==1 ? nothing : hcat([[2real(R[1,2,r]),-2imag(R[1,2,r]),real(R[1,1,r]-R[2,2,r])] for r in 1:nr]...)
    (;R,n,m)
end

@testset "Rectangular complex nonlocal actions and bounded RHS/k switching" begin
    rng=MersenneTwister(91091)
    D=ComplexF64[2 .3+.4im -.2im;.3-.4im -1 .7+.1im;.2im .7-.1im .5]
    ws=NonlocalWorkspace(14,4,30)
    for nr in (10,14,10),columns in (30,1,24)
        P=randn(rng,ComplexF64,nr,3);K=dense_oracle(P,D)
        @test norm(imag.(K))>0 && norm(K-K')<1e-11
        X=randn(rng,ComplexF64,nr,columns);saved=copy(X)
        Y=fill(ComplexF64(NaN,NaN),size(X))
        @test nonlocal_action!(Y,P,D,X,ws)===Y
        @test relative_error(Y,K*X)<=1e-12
        @test X==saved
        old=copy(Y);alpha,beta=.3+.7im,-.2+.4im
        nonlocal_action!(Y,P,D,X,ws,alpha,beta)
        @test relative_error(Y,alpha*(K*X)+beta*old)<=1e-12
        nonlocal_action!(Y,P,D,X,ws,0,0);@test all(iszero,Y)
        f=columns==1 ? [.4] : collect(range(.1,.9;length=columns));w=.7
        oracle=w*sum(f[j]*real(dot(X[:,j],K*X[:,j])) for j in axes(X,2))
        @test abs(nonlocal_expectation(P,D,X,f,w,ws)-oracle)<=1e-10
        @test abs(projected_nonlocal_energy(P,D,X,f,w,ws)-oracle)<=1e-10
        if columns==1
            x=vec(X);y=similar(x)
            nonlocal_action!(y,P,D,x,ws)
            @test relative_error(y,K*x)<=1e-12
        end
        backing=zeros(ComplexF64,2nr,2columns);input=zeros(ComplexF64,size(backing))
        xv=@view input[1:2:end,1:2:end];yv=@view backing[1:2:end,1:2:end];xv.=X
        nonlocal_action!(yv,P,D,xv,ws)
        @test relative_error(yv,K*X)<=1e-12
        @test all(iszero,backing[2:2:end,:]) && all(iszero,backing[:,2:2:end])
    end
    @test workspace_stats(ws).action_calls>0 && workspace_stats(ws).projected_calls==9
    # Carry the very same scalar across k: no reset/subtotal regrouping.
    seed=-17.25;ordered=seed;actual=seed
    for nr in (10,14)
        P=randn(rng,ComplexF64,nr,3);X=randn(rng,ComplexF64,nr,24);f=fill(.6,24)
        C=P'*X;U=D*C
        for state in axes(X,2),i in axes(C,1)
            ordered+=.5*f[state]*real(conj(C[i,state])*U[i,state])
        end
        actual=projected_nonlocal_energy(P,D,X,f,.5,ws;initial_total=actual)
    end
    @test actual==ordered
    @test_throws ArgumentError projected_nonlocal_energy(ones(2,1),ones(1,1),ones(2,1),[1.],1.,ws;initial_total=NaN)
    @test_throws ArgumentError projected_nonlocal_energy(ones(2,1),ones(1,1),ones(2,1),[1.],1.,ws;initial_total=big"1e1000")
    reset_workspace_counters!(ws);@test all(iszero,values(workspace_stats(ws)))
end

@testset "Owned arrays, alias rejection and failure-atomic publication" begin
    rng=MersenneTwister(91092);P=randn(rng,ComplexF64,8,3);D=Matrix{ComplexF64}(I,3,3)
    labels=[Dict("column"=>i) for i in 1:3];data=NonlocalData(P,D;labels)
    P0=copy(P);D0=copy(D);P[1]+=1;D[1]+=1;labels[1]["column"]=99
    @test data.P==P0 && data.D==D0 && data.labels[1]["column"]==1
    X=ones(ComplexF64,8,3);Y=fill(ComplexF64(42),8,3);ws=NonlocalWorkspace(8,3,30)
    saved=copy(Y)
    for bad in (NaN,Inf)
        x=copy(X);x[1]=bad
        @test_throws ArgumentError nonlocal_action!(Y,data,x,ws)
        @test Y==saved
    end
    @test_throws ArgumentError nonlocal_action!(Y,data,X,ws,big"1e1000",0)
    @test_throws ArgumentError nonlocal_action!(Y,data,X,ws,NaN,0)
    @test Y==saved
    @test_throws ArgumentError nonlocal_action!(X,data,X,ws)
    @test_throws ArgumentError nonlocal_action!(@view(data.P[:,:]),data,X,ws)
    @test_throws ArgumentError nonlocal_action!(@view(ws.candidate[:,1:3]),data,X,ws)
    fill!(ws.candidate,1)
    @test_throws ArgumentError nonlocal_action!(Y,data,@view(ws.candidate[:,1:3]),ws)
    old_weighted=ws.weighted;ws.weighted=ws.coefficients
    @test_throws ArgumentError nonlocal_action!(Y,data,X,ws)
    ws.weighted=old_weighted
    overlap=ones(ComplexF64,9,3)
    @test_throws ArgumentError nonlocal_action!(@view(overlap[2:end,:]),data,@view(overlap[1:end-1,:]),ws)
    @test_throws DimensionMismatch nonlocal_action!(Y,data,X,NonlocalWorkspace(8,3,1))
    @test_throws DimensionMismatch nonlocal_action!(zeros(ComplexF64,7,3),data,X,ws)
    @test_throws ArgumentError nonlocal_action!(zeros(ComplexF32,size(Y)),data,X,ws)
    @test_throws ArgumentError nonlocal_action!(fill(ComplexF64(NaN),size(Y)),data,X,ws,1,1)
    huge=NonlocalData(fill(1e200,8,3),Matrix{Float64}(I,3,3))
    @test_throws ArgumentError nonlocal_action!(Y,huge,X,ws)
    @test Y==saved
    @test_throws ArgumentError NonlocalData(ones(2,2),[1. 1.;0. 1.])
    @test_throws ArgumentError NonlocalData(fill(NaN,2,2),Matrix{Float64}(I,2,2))
    @test_throws ArgumentError NonlocalData(fill(big"1e1000",2,2),Matrix{Float64}(I,2,2))
    @test_throws ArgumentError projected_nonlocal_energy(data,X,[2.,0,0],1.,ws)
    @test_throws ArgumentError nonlocal_expectation(data,X,ones(3),NaN,ws)
    @test_throws ArgumentError NonlocalWorkspace(8,3,true)
    # Tiny nonzero f is not a disposable empty-band shortcut. This synthetic
    # scaling makes its contribution finite and visible, without overflow.
    tiny=NonlocalData(fill(1e150,2,1),ones(1,1));smallws=NonlocalWorkspace(2,1,1)
    @test nonlocal_expectation(tiny,ones(2,1),[1e-300],1.,smallws)≈4.0 rtol=1e-14
    @test projected_nonlocal_energy(tiny,ones(2,1),[1e-300],1.,smallws)≈4.0 rtol=1e-14
    @test projected_nonlocal_energy(tiny,ones(2,1),[0.0],1.,smallws)==0.0
end

@testset "General component count with independent dense oracle and callback failures" begin
    rng=MersenneTwister(91093)
    for ncomp in (1,2,3)
        ws=ComponentWorkspace(7,30,ncomp)
        for ng in (4,7,4),columns in (30,1,24)
            raw=randn(rng,ComplexF64,ng,ng);H=raw+raw'
            scalar=(y,x)->mul!(y,H,x)
            X=randn(rng,ComplexF64,ncomp*ng,columns);saved=copy(X)
            Y=fill(ComplexF64(NaN),size(X));K=kron(H,Matrix{ComplexF64}(I,ncomp,ncomp))
            @test component_action!(Y,scalar,X,ncomp,ws)===Y
            @test relative_error(Y,K*X)<=1e-12 && X==saved
            old=copy(Y);component_action!(Y,scalar,X,ncomp,ws,.2+.1im,-.3im)
            @test relative_error(Y,(.2+.1im)*(K*X)-.3im*old)<=1e-12
            if columns==1
                x=vec(X);y=similar(x);component_action!(y,scalar,x,ncomp,ws)
                @test relative_error(y,K*x)<=1e-12
            end
        end
        @test workspace_stats(ws).scalar_calls==ncomp*workspace_stats(ws).action_calls
    end
    ws=ComponentWorkspace(4,3,2);X=ones(ComplexF64,8,3);Y=fill(ComplexF64(42),8,3);before=copy(Y)
    callback=(y,x)->begin fill!(y,1);x[1]=9;end
    @test_throws ArgumentError component_action!(Y,callback,X,2,ws)
    @test Y==before && all(==(1),X)
    @test_throws ArgumentError component_action!(Y,(y,x)->fill!(y,Inf),X,2,ws)
    @test Y==before
    @test_throws ArgumentError component_action!(Y,(y,x)->(y[1]=1),X,2,ws)
    @test Y==before
    @test_throws ArgumentError component_action!(X,(y,x)->copyto!(y,x),X,2,ws)
    @test_throws DimensionMismatch component_action!(Y,(y,x)->copyto!(y,x),X,3,ws)
    @test_throws ArgumentError component_action!(Y,(y,x)->copyto!(y,x),X,2,ws,Inf,0)
    @test_throws ArgumentError ComponentWorkspace(4,3,0)
end

@testset "Exact density order, capacities and complex Pauli sign" begin
    rng=MersenneTwister(91094)
    for ncomp in (1,2)
        states=[randn(rng,ComplexF64,ncomp,7,3),randn(rng,ComplexF64,ncomp,7,2)]
        f=ncomp==1 ? [[1.8,.2,0.0],[1.0,.6]] : [[.9,.2,0.0],[.8,.4]]
        weights=[.3,.7];reference=density_oracle(states,weights,f)
        ws=DensityWorkspace(ncomp,7);reset_density!(ws)
        for (u,w,occ) in zip(states,weights,f);accumulate_density!(ws,u,w,occ);end
        result=finish_density!(ws)
        @test relative_error(result.R,reference.R)<=1e-12
        @test relative_error(result.n,reference.n)<=1e-12
        @test ncomp==1 ? result.m===nothing : relative_error(result.m,reference.m)<=1e-12
        old=deepcopy(result);reset_density!(ws)
        for (u,w,occ) in zip(states,weights,f),state in axes(u,3)
            accumulate_density!(ws,@view(u[:,:,state:state]),w,@view(occ[state:state]))
        end
        statewise=finish_density!(ws)
        @test statewise.R==old.R && statewise.n==old.n
        @test ncomp==1 || statewise.m==old.m
    end
    ws=DensityWorkspace(2,1);reset_density!(ws)
    accumulate_density!(ws,reshape(ComplexF64[1,im]/sqrt(2),2,1,1),1.,[1.])
    result=finish_density!(ws);@test vec(result.m)≈[0.,1.,0.] atol=1e-14
    @test_throws ArgumentError finish_density!(ws)
    @test_throws ArgumentError DensityWorkspace(3,7)
    reset_density!(ws)
    @test_throws ArgumentError accumulate_density!(ws,ones(ComplexF64,2,1,1),1.,[2.])
    @test ws.failed && !ws.active
    @test_throws ArgumentError finish_density!(ws)
    reset_density!(ws)
    @test_throws ArgumentError accumulate_density!(ws,reshape(ws.R,2,1,2),1.,ones(2))
    reset_density!(ws)
    @test_throws ArgumentError accumulate_density!(ws,fill(ComplexF64(1e200),2,1,1),1.,[1.])
    @test ws.failed
    @test validate_weights([.2,.8],2)
    @test_throws ArgumentError validate_weights([.2,.7],2)
    @test_throws ArgumentError validate_weights([-.1,1.1],2)
    tinyws=DensityWorkspace(2,1);reset_density!(tinyws)
    accumulate_density!(tinyws,reshape(ComplexF64[1e150,im*1e150],2,1,1),1.,[1e-300])
    tinyresult=finish_density!(tinyws)
    @test tinyresult.n[1]≈2.0 rtol=1e-14
    @test tinyresult.m[2,1]≈2.0 rtol=1e-14
end

if "--with-fft-adapter" in ARGS
    @eval import DFTK, PseudoPotentialIO
    include(joinpath(KERNEL_ROOT,"scripts/workbench_environment.jl"))
    identity=WorkbenchEnvironment.environment_identity(KERNEL_ROOT,(DFTK,PseudoPotentialIO))
    identity.status=="PASS" || error("Frozen identity failed before synthetic FFT adapter tests")
    include(joinpath(KERNEL_ROOT,"prototypes/spinor/SpinorPrototype.jl"))
    const SP=SpinorPrototype
    @testset "Frozen FFT statewise adapter, synthetic coefficients only" begin
        rng=MersenneTwister(91095)
        model=DFTK.Model(Matrix(Diagonal([6.,7.,8.]));n_electrons=2,terms=[DFTK.Kinetic()],symmetries=false)
        basis=DFTK.PlaneWaveBasis(model;Ecut=3.,kgrid=DFTK.ExplicitKpoints([[0.,0.,0.],[.19,.07,-.13]]))
        ngs=[length(DFTK.G_vectors(basis,k)) for k in basis.kpoints];nr=prod(basis.fft_size)
        @test length(unique(ngs))==2
        for ncomp in (1,2)
            ws=SP.OrbitalDensityWorkspace(maximum(ngs),nr,basis.fft_size,ncomp)
            for columns in (3,1,4)
                X=[randn(rng,ComplexF64,ncomp*ng,columns) for ng in ngs];saved=deepcopy(X)
                f=[fill(ncomp==1 ? 1.3 : .7,columns) for _ in ngs]
                states=[SP.component_ifft(basis,k,reshape(x,ncomp,size(x,1)÷ncomp,columns)) for (k,x) in zip(basis.kpoints,X)]
                old=SP.density_from_real_states(states,basis.kweights,f)
                result=SP.orbital_density!(ws,basis,X,basis.kweights,f)
                @test relative_error(result.R,old.R)<=1e-12 && relative_error(result.n,old.n)<=1e-12
                @test ncomp==1 || relative_error(result.m,old.m)<=1e-12
                @test X==saved
            end
            @test workspace_stats(ws).inverse_fft_calls==ncomp*length(ngs)*(3+1+4)
            @test workspace_stats(ws).density_calls==3
            X=[ones(ComplexF64,ncomp*ng,1) for ng in ngs];f=[[.5] for _ in ngs]
            X[1][1]=NaN
            @test_throws ArgumentError SP.orbital_density!(ws,basis,X,basis.kweights,f)
        end
        @test SP.SOCKernels===SOCKernels
    end
end
println("Kernel test scope: synthetic algebra", "--with-fft-adapter" in ARGS ? " and synthetic coefficients on frozen FFT basis" : " only", "; Julia ", VERSION)
