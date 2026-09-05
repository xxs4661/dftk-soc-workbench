# All channel functions and matrices in this file are synthetic algebra fixtures.
# The runner supplies Test, Random, LinearAlgebra, RelativisticProjectors and the
# independent angular_reference.jl helpers. No physical SCF is performed here.

rel_operator_error(a,b)=norm(a-b)/max(norm(a),norm(b),1)

function time_reversal_pairs(qcart;atol=1e-12)
    pairs=Int[]
    for q in qcart
        matches=findall(p->norm(q+p)<=atol,qcart)
        length(matches)==1 || throw(ArgumentError("Each q needs exactly one -q partner"))
        push!(pairs,only(matches))
    end
    sort(pairs)==collect(eachindex(qcart)) && pairs[pairs]==collect(eachindex(qcart)) ||
        throw(ArgumentError("Wavevector reversal must be an involutive permutation"))
    pairs
end

"""Antiunitary probe helper: q reversal followed by i*sigma_y*K, in up/down rows."""
function time_reverse_probe(X::AbstractVecOrMat,pairs)
    size(X,1)==2length(pairs) || throw(DimensionMismatch("Time reversal needs 2NG rows"))
    sort(pairs)==collect(eachindex(pairs)) && pairs[pairs]==collect(eachindex(pairs)) ||
        throw(ArgumentError("Invalid time-reversal permutation"))
    input=reshape(X,size(X,1),:)
    output=similar(input,ComplexF64)
    for (iq,jq) in enumerate(pairs)
        output[2iq-1,:]=conj.(input[2jq,:])
        output[2iq,:]=-conj.(input[2jq-1,:])
    end
    reshape(output,size(X))
end

function _operator_gaussian_fixture(settings;l=1,degenerate=false)
    a0=settings["gaussian"]["a_bohr_minus2"]
    r=collect(range(0,settings["gaussian"]["rmax_bohr"];length=first(settings["gaussian"]["points"])))
    records=NamedTuple[]; exponents=Float64[]
    # Deliberately put j+ before j- in parsed order; internal order sorts j- first.
    branches=l==0 ? [1] : [2l+1,2l-1]
    D=zeros(Float64,2length(branches),2length(branches))
    for (branch,two_j) in enumerate(branches)
        isminus=two_j==2l-1
        for radial in 1:2
            i=length(records)+1
            a=a0*(1+0.3*(radial-1)+(degenerate ? 0 : 0.25isminus))
            push!(exponents,a)
            beta=r.^(l+1).*exp.(-a.*r.^2)
            push!(records,(;source_index=100+7i,parsed_position=i,l,two_j,
                r=copy(r),beta_raw=beta,cutoff_index=length(r)))
        end
        scale=degenerate || !isminus ? 1.0 : 0.65
        inds=(2branch-1):(2branch)
        D[inds,inds]=scale.*[1.3 0.23;0.23 -0.4]
    end
    model=RelativisticProjectors.synthetic_channel_model(records,D;
        provenance=(;scope="Synthetic Gaussian radial functions; not a physical UPF"))
    (;model,records,D_raw=D,a_by_parsed=exponents)
end

function _operator_analytic_radial(fixture,model,index,q)
    channel=model.channels[index]
    l=channel.l; a=fixture.a_by_parsed[channel.parsed_beta_position]
    # The synthetic raw beta is r^(l+1) exp(-a*r^2); :dftk uses raw/2.
    0.5*4π*sqrt(π)*q^l/(2^(l+2)*a^(l+1.5))*exp(-q^2/(4a))
end

function _operator_scalar_oracle(fixture,qcart,positions,volume)
    model=fixture.model; l=first(model.channels).l
    indices=[only(findall(c->c.two_j==2l+1 && c.radial_projector==i,model.channels)) for i in 1:2]
    columns=[(atom,m,radial) for atom in eachindex(positions) for m in -l:l for radial in 1:2]
    P=zeros(ComplexF64,length(qcart),length(columns))
    D=zeros(ComplexF64,length(columns),length(columns))
    for (j,(atom,m,radial)) in enumerate(columns), (iq,q) in enumerate(qcart)
        if iszero(norm(q)) && l>0
            continue
        end
        P[iq,j]=cis(-dot(q,positions[atom]))/sqrt(volume)*(-im)^l*
            _operator_analytic_radial(fixture,model,indices[radial],norm(q))*independent_Ylm(l,m,q)
    end
    for (i,a) in enumerate(columns), (j,b) in enumerate(columns)
        a[1:2]==b[1:2] && (D[i,j]=model.D[indices[a[3]],indices[b[3]]])
    end
    P*D*P'
end

function run_operator_tests(settings)
    RP=RelativisticProjectors
    tol=settings["tolerances"]["operator"]
    etol=settings["tolerances"]["nonlocal_energy"]
    rng=MersenneTwister(61013)
    qcart=[[0.,0,0],[0.2,0.3,0.5],[-0.2,-0.3,-0.5],
        [1.1,-0.4,0.7],[-1.1,0.4,-0.7],[0.6,0.9,-0.2],[-0.6,-0.9,0.2]]
    positions=[[0.31,-0.17,0.43]]; volume=64.0
    fixture=_operator_gaussian_fixture(settings)
    model=fixture.model
    A=RP.build_nonlocal_operator(model,qcart,positions,volume)
    dense=A.P*A.D*A.P'
    X=randn(rng,ComplexF64,size(A,1),3)
    x=randn(rng,ComplexF64,size(A,1)); y=randn(rng,ComplexF64,size(A,1))
    saved_X=copy(X)
    errors=Dict{String,Float64}()

    @testset "Synthetic matrix-free FR operator contract" begin
        @test size(A)==(2length(qcart),2length(qcart))
        @test size(A,3)==1
        @test eltype(A)==eltype(typeof(A))==ComplexF64
        @test_throws ArgumentError size(A,0)
        @test length(A.labels)==sum(c.two_j+1 for c in model.channels)==12
        keys=[(c.atom,c.l,c.two_j,c.two_mj,c.radial_projector) for c in A.labels]
        @test keys==sort(keys)
        @test length(unique(keys))==length(keys)
        @test any(!iszero,A.D-Diagonal(diag(A.D)))
        @test minimum(eigvals(Hermitian(A.D)))<0
        @test rel_operator_error(A*X,dense*X)<=tol
        @test rel_operator_error(A*x,dense*x)<=tol
        @test X==saved_X
        Y=fill(ComplexF64(NaN,NaN),size(X))
        @test mul!(Y,A,X)===Y
        @test rel_operator_error(Y,dense*X)<=tol
        old=copy(Y); alpha,beta=0.3+0.7im,-0.2+0.4im
        @test mul!(Y,A,X,alpha,beta)===Y
        @test rel_operator_error(Y,alpha*(dense*X)+beta*old)<=tol
        backing=randn(rng,ComplexF64,2size(A,1),6)
        view_X=@view backing[1:2:end,1:2:end]
        original=copy(backing); outback=zeros(ComplexF64,size(backing))
        view_Y=@view outback[1:2:end,1:2:end]
        mul!(view_Y,A,view_X)
        @test rel_operator_error(view_Y,dense*view_X)<=tol
        @test backing==original && all(iszero,outback[2:2:end,:]) && all(iszero,outback[:,2:2:end])
        @test_throws ArgumentError mul!(X,A,X)
        @test X==saved_X
        overlap=randn(rng,ComplexF64,size(A,1)+1,3); before=copy(overlap)
        @test_throws ArgumentError mul!(@view(overlap[2:end,:]),A,@view(overlap[1:end-1,:]))
        @test overlap==before
        @test_throws ArgumentError mul!(A.P,A,zeros(ComplexF64,size(A.P)))
        square=RP.FRNonlocalOperator(Matrix{ComplexF64}(I,3,3),Matrix{ComplexF64}(I,3,3))
        @test_throws ArgumentError mul!(square.D,square,ones(ComplexF64,3,3))
        @test_throws ArgumentError mul!(zeros(ComplexF32,size(X)),A,X)
        @test_throws DimensionMismatch A*zeros(ComplexF64,size(A,1)+1)
        @test_throws DimensionMismatch mul!(zeros(ComplexF64,size(A,1),2),A,X)
        nanx=copy(X);nanx[1]=NaN
        @test_throws ArgumentError A*nanx
        @test_throws ArgumentError mul!(Y,A,X,NaN,0)
        @test_throws ArgumentError mul!(fill(ComplexF64(NaN),size(X)),A,X,1,1)
        @test_throws ArgumentError RP.FRNonlocalOperator(fill(NaN,2,2),Matrix{Float64}(I,2,2))
        @test_throws ArgumentError RP.FRNonlocalOperator(ones(2,2),[1. 1;0 1])
        @test_throws DimensionMismatch RP.FRNonlocalOperator(ones(2,3),ones(2,2))
        @test_throws ArgumentError RP.FRNonlocalOperator(fill(big"1e1000",2,1),ones(1,1))
        overflow=RP.FRNonlocalOperator(fill(1e200,2,1),ones(1,1))
        @test_throws ArgumentError overflow*ones(ComplexF64,2)
        pcopy=copy(A.P);dcopy=copy(A.D);owned=RP.FRNonlocalOperator(pcopy,dcopy)
        pcopy[1]=100;dcopy[1]=100
        @test owned.P==A.P && owned.D==A.D
        @test_throws ArgumentError RP.build_projectors(model,qcart,positions,0.)
        @test_throws ArgumentError RP.build_projectors(model,[[NaN,0.,0.]],positions,volume)
        duplicate=copy(A.labels);duplicate[end]=duplicate[1]
        @test_throws ArgumentError RP.expanded_coupling(model,duplicate)
    end

    @testset "Independent ladder-LS kernel and nontrivial complex spin coupling" begin
        reference=independent_kernel(model,qcart,positions,volume;
            radial=(m,i,q)->_operator_analytic_radial(fixture,m,i,q))
        errors["independent_kernel"]=rel_operator_error(dense,reference)
        @test errors["independent_kernel"]<=tol
        @test rel_operator_error(A*X,reference*X)<=tol
        errors["hermiticity"]=rel_operator_error(dot(x,A*y),dot(A*x,y))
        @test errors["hermiticity"]<=tol
        @test norm(dense[1:2:end,2:2:end])>1e-8
        @test norm(imag.(dense))>1e-8
        @test rel_operator_error(A.P*A.D*transpose(A.P)*X,A*X)>1e-8
        wrong_phase=copy(A.P);wrong_phase[2:2:end,:].*=-1
        wrong=wrong_phase*A.D*wrong_phase'
        @test norm(wrong-wrong')<=tol
        @test rel_operator_error(wrong,reference)>1e-8  # Hermiticity alone misses this error.
        scalar=_operator_scalar_oracle(fixture,qcart,positions,volume)
        @test rel_operator_error(dense,kron(scalar,Matrix{ComplexF64}(I,2,2)))>1e-8
        diagonal_only=A.P*Diagonal(diag(A.D))*A.P'
        @test rel_operator_error(diagonal_only,dense)>1e-8
        # Both component and projector-space energy paths are weighted independently.
        B=RP.build_nonlocal_operator(model,[q.+[0.04,-0.03,0.02] for q in qcart],positions,volume)
        X2=randn(rng,ComplexF64,size(B,1),2)
        weights=[0.35,0.65]; f=[[1.,0.6,0.2],[0.8,0.3]]
        e=RP.nonlocal_energy([A,B],[X,X2],weights,f)
        ep=RP.projected_nonlocal_energy([A,B],[X,X2],weights,f)
        errors["energy_two_paths"]=rel_operator_error(e,ep)
        @test errors["energy_two_paths"]<=etol
        negative=RP.FRNonlocalOperator(A.P,-Matrix{ComplexF64}(I,size(A.D)...))
        @test RP.nonlocal_energy(negative,X,[1.,0.6,0.2])<0
        @test_throws ArgumentError RP.nonlocal_energy(A,X,[2.,0.,0.])
        @test_throws ArgumentError RP.nonlocal_energy([A],[X],[2.],[[1.,0.,0.]])
    end

    @testset "Paired units, radial basis, atom sum and spatial normalization" begin
        alternative=RP.synthetic_channel_model(fixture.records,fixture.D_raw;unit_convention=:alternative,
            provenance=(;scope="Synthetic paired-unit identity"))
        alternate=RP.build_nonlocal_operator(alternative,qcart,positions,volume)
        errors["paired_units"]=rel_operator_error(alternate*X,A*X)
        @test errors["paired_units"]<=tol
        @test rel_operator_error((RP.FRNonlocalOperator(A.P/2,A.D))*X,A*X)>1e-8
        @test rel_operator_error((RP.FRNonlocalOperator(A.P,A.D/2))*X,A*X)>1e-8
        @test rel_operator_error((RP.FRNonlocalOperator(A.P,2A.D))*X,A*X)>1e-8
        perm=collect(1:length(A.labels));perm[1:2]=reverse(perm[1:2])
        reordered=RP.FRNonlocalOperator(A.P[:,perm],A.D[perm,perm];labels=A.labels[perm])
        errors["reorder"]=rel_operator_error(reordered*X,A*X)
        @test errors["reorder"]<=tol
        @test rel_operator_error(RP.FRNonlocalOperator(A.P[:,perm],A.D)*X,A*X)>1e-8
        @test rel_operator_error(RP.FRNonlocalOperator(A.P,A.D[perm,perm])*X,A*X)>1e-8
        @test_throws ArgumentError RP.FRNonlocalOperator(A.P,A.D[perm,:])
        labels=A.labels[perm]
        @test RP.build_projectors(model,qcart,positions,volume;labels)==A.P[:,perm]
        @test RP.expanded_coupling(model,labels)==A.D[perm,perm]
        transform=Matrix{ComplexF64}(I,length(A.labels),length(A.labels))
        radial_change=ComplexF64[1+0.1im 0.25;-0.2im 1.1]
        for start in 1:2:length(A.labels)
            transform[start:start+1,start:start+1]=radial_change
        end
        @test cond(transform)<3
        changed=RP.FRNonlocalOperator(A.P*transform,transform\A.D/transform')
        errors["radial_basis"]=rel_operator_error(changed*X,A*X)
        @test errors["radial_basis"]<=tol
        second=[-0.27,0.2,0.11]
        both=RP.build_nonlocal_operator(model,qcart,[positions[1],second],volume)
        atom2=RP.build_nonlocal_operator(model,qcart,[second],volume)
        errors["atom_sum"]=rel_operator_error(both*X,A*X+atom2*X)
        @test errors["atom_sum"]<=tol
        @test all(iszero,both.D[1:length(A.labels),length(A.labels)+1:end])
        shift=[0.12,-0.19,0.08]
        shifted=RP.build_nonlocal_operator(model,qcart,[positions[1]+shift],volume)
        phase=repeat([cis(-dot(q,shift)) for q in qcart];inner=2)
        @test rel_operator_error(shifted.P,phase.*A.P)<=tol
        errors["translation"]=rel_operator_error(shifted*X,phase.*(A*(conj.(phase).*X)))
        @test errors["translation"]<=tol
        scaled=RP.build_nonlocal_operator(model,qcart,positions,4volume)
        @test rel_operator_error(scaled.P,A.P/2)<=tol
        errors["volume"]=rel_operator_error(scaled*X,A*X/4)
        @test errors["volume"]<=tol
    end

    @testset "Full q reversal and complete synthetic scalar limits l=0:3" begin
        pairs=time_reversal_pairs(qcart)
        @test rel_operator_error(time_reverse_probe(time_reverse_probe(X,pairs),pairs),-X)<=tol
        @test rel_operator_error(time_reverse_probe(time_reverse_probe(x,pairs),pairs),-x)<=tol
        errors["time_reversal"]=rel_operator_error(time_reverse_probe(A*X,pairs),A*time_reverse_probe(X,pairs))
        @test errors["time_reversal"]<=tol
        @test_throws ArgumentError time_reversal_pairs([[0.2,0.3,0.5]])
        @test_throws ArgumentError time_reversal_pairs(vcat(qcart,[qcart[1]]))
        U=ComplexF64[cos(0.31) im*sin(0.31);im*sin(0.31) cos(0.31)]
        S=kron(Matrix{ComplexF64}(I,length(qcart),length(qcart)),U)
        @test rel_operator_error(A*(S*X),S*(A*X))>1e-8 # No spin-only invariance for general j-dependent channels.
        for l in 0:3
            degenerate=_operator_gaussian_fixture(settings;l,degenerate=true)
            op=RP.build_nonlocal_operator(degenerate.model,qcart,positions,volume)
            scalar=_operator_scalar_oracle(degenerate,qcart,positions,volume)
            lifted=kron(scalar,Matrix{ComplexF64}(I,2,2))
            errors["scalar_l$l"]=rel_operator_error(op*X,lifted*X)
            @test errors["scalar_l$l"]<=tol
            @test rel_operator_error(op*(S*X),S*(op*X))<=tol
            # Direct P entry checks (-i)^l, atomic phase, F, and spin-angular phase;
            # an operator-only P D P' comparison would cancel a common column phase.
            column=only(findall(c->c.two_j==2l+1 && c.two_mj==2l+1 && c.radial_projector==1,op.labels))
            label=op.labels[column]
            iq=2;q=qcart[iq]
            direct=cis(-dot(q,positions[1]))*(-im)^l/sqrt(volume)*
                _operator_analytic_radial(degenerate,degenerate.model,label.channel_position,norm(q))*independent_Ylm(l,l,q)
            @test rel_operator_error(op.P[2iq-1,column],direct)<=tol
            @test abs(op.P[2iq,column])<=tol
            @test all(isfinite,op.P)
            if l>0
                @test all(iszero,op.P[1:2,:])
            else
                @test norm(op.P[1:2,:])>0
            end
        end
    end
    (;scope="Synthetic Gaussian channels and small algebra kernels; no physical SCF",errors)
end
