#!/usr/bin/env julia
# Synthetic coefficients and plain protocol objects only; no historical state or UPF.
using Test, LinearAlgebra, Random, SHA, Serialization, JSON3
include("../scripts/extract_orbital_nonlocal.jl")
const ON=OrbitalNonlocalExtraction
jsondict(x)=JSON3.read(JSON3.write(x),Dict{String,Any})

function synthetic_orbitals(points;target=3)
    rng=MersenneTwister(77001)
    X=[Matrix(qr(randn(rng,ComplexF64,2size(p.millers,2),target)).Q)[:,1:target] for p in points]
    f=[Float64[1,.2,0] for _ in points];e=[Float64[-.7,.1,1.5] for _ in points]
    nout=fill(.01,8);nin=copy(nout);nin[1]+=1e-10;nin[2]-=1e-10
    final=(;target_states=target,map_count=2,n_in_sha256=ON.SD.density_hash(nin),
        n_out_sha256=ON.SD.density_hash(nout),unmixed_residual_l2=norm(nout-nin),
        occupations=f,eigenvalues_ha=e)
    (;X,f,eigenvalues=e,n_in=nin,n_out=nout,R=zeros(ComplexF64,2,2,8),m=zeros(3,8),final)
end

function run_orbital_nonlocal_tests()
    identity=ON.SD.environment_identity(ON.ROOT,(ON.DFTK,ON.PseudoPotentialIO))
    identity.status=="PASS" && VERSION==v"1.12.7" || error("Frozen synthetic Julia environment required")
    ON.DFTK.disable_threading()
    @testset "Synthetic orbital transport and frozen nonlocal contraction" begin
        plan=ON.SD.read_json(joinpath(ON.ROOT,"benchmarks/mg-soc-wavefunction-energy-v1/plan.json"))
        @test isnothing(ON.check_plan_environment(plan,identity))
        badplan=deepcopy(plan);badplan["identity"]["environment"]["julia_version"]="0.0.0"
        @test_throws ErrorException ON.check_plan_environment(badplan,identity)
        badplan=deepcopy(plan);delete!(badplan["source_sha256"],"environment/workbench/Manifest.toml")
        @test_throws ErrorException ON.check_plan_environment(badplan,identity)
        badplan=deepcopy(plan);badplan["identity"]["environment"]["packages"]["dftk"]["commit"]="0"^40
        @test_throws ErrorException ON.check_plan_environment(badplan,identity)
        # Sheared cell and nonzero, non-axis k: independent scalar cutoff oracle.
        A=[7.0 .4 1.2;0.0 9.0 .3;.5 0.0 11.0]
        B=2pi*inv(A');k=[.13,-.17,.08];shape=(8,10,12);ecut=1.5
        kp=ON.DFTK.Kpoint(1,k,ON.DFTK.Mat3{Float64}(B),shape,ecut;variational=true,architecture=ON.DFTK.CPU())
        axesnative(n)=vcat(0:div(n-1,2),-div(n,2):-1)
        expected=NTuple{3,Int}[]
        for z in axesnative(shape[3]),y in axesnative(shape[2]),x in axesnative(shape[1])
            m=[x,y,z];q=2pi*(A'\(m+k))
            sum(v*v for v in q)/2<=ecut && push!(expected,(x,y,z))
        end
        @test Tuple.(kp.G_vectors)==expected
        physical=Dict("lattice_vectors_bohr"=>collect.(eachcol(A)),"fft_size"=>collect(shape),
            "ecut_ha"=>ecut,"expected_electrons"=>10,"kpoints"=>[k],"kweights"=>[1.])
        # Historical fixture independently uses the exact native receipt hash.
        historical=Dict("lattice_bohr"=>collect.(eachcol(A)),"fft_grid"=>collect(shape),
            "ecut_ha"=>ecut,"volume_bohr3"=>abs(det(A)),"n_electrons"=>10,
            "kpoints"=>[Dict("coordinate_fractional"=>k,"weight_spatial"=>1.,"ng"=>length(expected),
                "g_order_sha256"=>ON.source_snapshot(collect(kp.G_vectors)))])
        recovered=ON.recover_kpoints(physical,historical)
        @test recovered.points[1].millers==reduce(hcat,collect.(expected))
        @test recovered.reciprocal≈B atol=1e-15
        @test recovered.points[1].k_cart≈B*k atol=1e-15
        @test maximum(abs,A'*recovered.reciprocal/(2pi)-I)<1e-14
        wrong=deepcopy(historical);wrong["kpoints"][1]["g_order_sha256"]=ON.source_snapshot(reverse(collect(kp.G_vectors)))
        @test_throws ErrorException ON.recover_kpoints(physical,wrong) # same NG, wrong order
        wrong=deepcopy(physical);wrong["kpoints"]=[-k]
        @test_throws ErrorException ON.recover_kpoints(wrong,historical)
        wrong=deepcopy(physical);wrong["lattice_vectors_bohr"]=collect.(eachrow(A))
        @test_throws ErrorException ON.recover_kpoints(wrong,historical)

        fixture=synthetic_orbitals(recovered.points);endpoint=jsondict(fixture.final)
        @test isnothing(ON.bound_orbitals(fixture,endpoint,recovered.points;target=3))
        for field in (:f,:eigenvalues,:X)
            bad=deepcopy(fixture)
            field==:f ? (bad.f[1][2]+=.01) : field==:eigenvalues ? (bad.eigenvalues[1][1]+=.01) : (bad.X[1][1]=NaN)
            @test_throws ErrorException ON.bound_orbitals(bad,endpoint,recovered.points;target=3)
        end
        @test_throws ErrorException ON.bound_orbitals(fixture,endpoint,recovered.points;target=24)
        bad=merge(fixture,(;X=[Float32.(real.(fixture.X[1]))]))
        @test_throws ErrorException ON.bound_orbitals(bad,endpoint,recovered.points;target=3)
        bad=merge(fixture,(;X=[fixture.X[1][1:end-2,:]]))
        @test_throws ErrorException ON.bound_orbitals(bad,endpoint,recovered.points;target=3)

        g=recovered.points[1].millers;x=fixture.X[1];permutation=reverse(1:size(g,2))
        sourceg=g[:,permutation];rows=reduce(vcat,([2i-1,2i] for i in permutation));sourcex=x[rows,:]
        mapped=ON.reorder_spinors(g,sourceg,sourcex)
        @test ON.array_hash(mapped.X)==ON.array_hash(x)
        @test mapped.permutation==collect(permutation)
        @test ON.array_hash(ON.reorder_spinors(g,sourceg,x).X)!=ON.array_hash(x) # coefficients-only/G-only swaps cannot be disguised
        duplicate=copy(sourceg);duplicate[:,1]=duplicate[:,2]
        @test_throws ErrorException ON.reorder_spinors(g,duplicate,sourcex)
        shifted=copy(sourceg);shifted[1,1]+=100
        @test_throws ErrorException ON.reorder_spinors(g,shifted,sourcex)
        @test_throws ErrorException ON.reorder_spinors(g,sourceg[:,1:end-1],sourcex)
        @test_throws ErrorException ON.reorder_spinors(Float64.(g),sourceg,sourcex)

        rng=MersenneTwister(77002);P=randn(rng,ComplexF64,12,4)
        z=randn(rng,ComplexF64,4,4);D=(z+z')/2
        op=ON.RP.FRNonlocalOperator(P,D)
        X=Matrix(qr(randn(rng,ComplexF64,12,3)).Q)[:,1:3];f=[1.,.7,0.];w=.31
        audit=ON.nonlocal_contractions(op,X,f,w)
        # Independent tiny dense oracle is test-only, never in production.
        V=P*D*P';dense=sum(w*f[n]*real(dot(X[:,n],V*X[:,n])) for n in 1:3)
        @test abs(audit.total_action-dense)<=1e-12
        @test abs(audit.total_projected-dense)<=1e-12
        @test abs(audit.total_spin-dense)<=1e-12
        @test audit.projection_split_max_abs<=1e-12
        @test abs(ON.RP.nonlocal_energy(op,X,f)*w-dense)<=1e-12
        @test abs(ON.RP.projected_nonlocal_energy(op,X,f)*w-dense)<=1e-12
        @test abs(sum(w*r.occupation*(r.up_up_ha+r.down_down_ha) for r in audit.rows)-dense)>1e-4
        diagonal=ON.RP.FRNonlocalOperator(P,Matrix(Diagonal(diag(D))))
        @test abs(ON.nonlocal_contractions(diagonal,X,f,w).total_action-dense)>1e-4
        @test abs(ON.nonlocal_contractions(op,conj.(X),f,w).total_action-dense)>1e-4
        phases=Diagonal(cis.([.31,-.52,1.7]))
        @test abs(ON.nonlocal_contractions(op,X*phases,f,w).total_action-dense)<=1e-12
        U=Matrix(qr(randn(rng,ComplexF64,3,3)).Q)
        equal=fill(.7,3)
        @test abs(ON.nonlocal_contractions(op,X,equal,w).total_action-ON.nonlocal_contractions(op,X*U,equal,w).total_action)<=1e-12
        @test abs(ON.nonlocal_contractions(op,X*U,f,w).total_action-dense)>1e-4
        @test abs(ON.nonlocal_contractions(op,2X,f,w).total_action-4dense)<=1e-11 # evaluator never renormalizes
        @test_throws ErrorException ON.nonlocal_contractions(op,X,[2.,.7,0.],w)
        @test_throws ErrorException ON.nonlocal_contractions(op,X,[1.,NaN,0.],w)
        @test_throws ErrorException ON.nonlocal_contractions(op,X[1:end-1,:],f,w)
        @test_throws ErrorException ON.nonlocal_contractions(op,X,f,NaN)
        # A phase-bearing Pauli-y cross block explicitly catches lost imaginary spin information.
        py=ComplexF64[1 0;0 im];dy=ComplexF64[0 1;1 0]
        spy=ON.RP.FRNonlocalOperator(py,dy);xy=reshape(ComplexF64[1,im]/sqrt(2),2,1)
        sy=ON.nonlocal_contractions(spy,xy,[1.],1.)
        @test abs(sy.total_action-1)<=1e-12
        @test abs(sy.rows[1].spin_cross_ha-1)<=1e-12
        @test sy.rows[1].up_up_ha==sy.rows[1].down_down_ha==0

        gate=Dict("schema_version"=>1,"phase"=>"7F","execution_status"=>"PASS","plan_sha256"=>"a"^64,
            "orbital_metadata_sha256"=>Dict("A"=>"b"^64,"B"=>"c"^64,"Q"=>"d"^64),
            "checks"=>Dict(key=>"PASS" for key in ON.GATE_CHECKS))
        @test isnothing(ON.validate_gate(gate,"a"^64,gate["orbital_metadata_sha256"]))
        for key in ON.GATE_CHECKS
            bad=deepcopy(gate);bad["checks"][key]="FAIL"
            @test_throws ErrorException ON.validate_gate(bad,"a"^64,gate["orbital_metadata_sha256"])
        end
        @test_throws ErrorException ON.validate_gate(gate,"0"^64,gate["orbital_metadata_sha256"])
        changed=copy(gate["orbital_metadata_sha256"]);changed["Q"]="e"^64
        @test_throws ErrorException ON.validate_gate(gate,"a"^64,changed)
        bad=deepcopy(gate);bad["execution_status"]="FAIL"
        @test_throws ErrorException ON.validate_gate(bad,"a"^64,gate["orbital_metadata_sha256"])

        mkpath(joinpath(ON.ROOT,".work","phase7f-preflight"))
        mktempdir(joinpath(ON.ROOT,".work","phase7f-preflight")) do dir
            # Preserve subnormal values and signed zeros; primitive output is not JSON-rounded.
            tiny=reshape(ComplexF64[complex(-0.,0.),complex(nextfloat(0.),-nextfloat(0.)),1+2im,-3+4im],2,2,1)
            for (name,values) in (("coefficients",tiny),("f",[0.,nextfloat(0.),1.]),("millers",Int64[-2 0;1 2;0 -3]))
                descriptor=jsondict(ON.write_array(dir,name,values))
                recovered_array=ON.read_array(dir,descriptor)
                @test ON.array_hash(recovered_array)==ON.array_hash(values)
                @test descriptor["bitwise_roundtrip_status"]=="PASS"
                wrong=copy(descriptor);wrong["order"]="C"
                @test_throws ErrorException ON.read_array(dir,wrong)
                wrong=copy(descriptor);wrong["sha256"]="0"^64
                @test_throws ErrorException ON.read_array(dir,wrong)
                wrong=copy(descriptor);wrong["path"]="../"*descriptor["path"]
                @test_throws ErrorException ON.read_array(dir,wrong)
                wrong=copy(descriptor);wrong["shape"]=[10^8]
                @test_throws ErrorException ON.read_array(dir,wrong)
                open(joinpath(dir,descriptor["path"]),"a") do io;write(io,UInt8(0));end
                @test_throws ErrorException ON.read_array(dir,descriptor)
            end
            path=joinpath(dir,"synthetic-final.bin");serialize(path,fixture)
            calls=Ref(0);reader=io->(calls[]+=1;deserialize(io))
            @test_throws ErrorException ON.SD.trusted_checkpoint(path,"0"^64;reader)
            @test calls[]==0
            parsed=ON.SD.trusted_checkpoint(path,ON.SD.filehash(path))
            @test ON.array_hash(parsed.X[1])==ON.array_hash(fixture.X[1])
            bad=merge(fixture,(;n_out=fixture.n_in,n_in=fixture.n_out))
            @test_throws ErrorException ON.SD.bound_densities(bad,endpoint,(2,2,2),1.,Dict("closure_l2_abs"=>1e-12))
            serialize(path,merge(fixture,(;X=Ref(1.))))
            @test_throws ErrorException ON.SD.trusted_checkpoint(path,ON.SD.filehash(path))
            request=joinpath(dir,"bad-request.json");write(request,JSON3.write(Dict("schema_version"=>999)))
            out=joinpath(dir,"failure")
            @test ON.main([request,out])==1
            failure=ON.SD.read_json(joinpath(out,"metadata.json"))
            @test failure["execution_status"]=="FAIL" && failure["exit_code"]==1
            @test failure["nonlocal_operator_constructions"]==0
            @test ON.main([request,out])==2
            @test ON.SD.read_json(joinpath(out,"metadata.json"))==failure
        end
        @test ON.main(["--help"])==0
        @test ON.main(String[])==2
    end
end
run_orbital_nonlocal_tests()
