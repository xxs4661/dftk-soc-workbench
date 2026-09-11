#!/usr/bin/env julia
# Synthetic arithmetic and protocol fixtures only: no historical checkpoint is read.
using Test, LinearAlgebra, SHA, JSON3, Serialization
include("../scripts/extract_soc_density.jl")
const SD = SOCDensityExtraction

struct ForbiddenCheckpointObject
    value::Int
end
synthetic_json(path,value)=write(path,JSON3.write(value)*"\n")

function synthetic_density(shape,lattice;shift=(0.0,0.0,0.0))
    # Positive, non-axis-aligned, phase-bearing analytic periodic density.
    m=(1,2,3);p=(2,-1,3);a=0.0012;b=0.0007;phase=0.37
    volume=abs(det(lattice));mean=10/volume
    n=Float64[]
    for k in 0:shape[3]-1,j in 0:shape[2]-1,i in 0:shape[1]-1
        s=(i/shape[1]-shift[1],j/shape[2]-shift[2],k/shape[3]-shift[3])
        push!(n,mean+a*cos(2pi*sum(m.*s)+phase)+b*sin(2pi*sum(p.*s)))
    end
    coefficients=Dict((0,0,0)=>complex(mean),m=>a/2*cis(phase),(-1,-2,-3)=>a/2*cis(-phase),
        p=>-im*b/2,(-2,1,-3)=>im*b/2)
    for g in keys(coefficients)
        coefficients[g]*=cis(-2pi*sum(g.*shift))
    end
    # This hand formula sums the two real sinusoidal components, rather than
    # sharing the production reciprocal-coefficient summation expression.
    qm=2pi*(transpose(lattice)\collect(m));qp=2pi*(transpose(lattice)\collect(p))
    hartree=pi*volume*(a^2/dot(qm,qm)+b^2/dot(qp,qp))
    (;n,coefficients,hartree)
end

function synthetic_fixture(dir,plan_template)
    shape=Tuple(Int.(plan_template["fft_size"]))
    lattice=Matrix{Float64}(I,3,3)*10
    sample=synthetic_density(shape,lattice)
    nout=sample.n;nin=copy(nout)
    nin[1]+=1e-10;nin[2]-=1e-10
    final=(;target_states=24,map_count=2,n_in_sha256=SD.density_hash(nin),
        n_out_sha256=SD.density_hash(nout),unmixed_residual_l2=sqrt(1000/prod(shape))*norm(nout-nin))
    state=(;X=Matrix{ComplexF64}[],f=Vector{Float64}[],eigenvalues=Vector{Float64}[],
        n_in=nin,n_out=nout,R=zeros(ComplexF64,2,2,length(nin)),m=zeros(3,length(nin)),final)
    sourcepath=joinpath(dir,"synthetic-final.bin");serialize(sourcepath,state)
    digest=SD.filehash(sourcepath)
    endpointpath=joinpath(dir,"synthetic-endpoint.json");synthetic_json(endpointpath,final)
    run_id="SYNTHETIC_PROTOCOL_ONLY_A"
    receiptpath=joinpath(dir,"synthetic-receipt.json")
    synthetic_json(receiptpath,(;run_id,label="A",execution_status="PASS",checkpoint_sha256=digest,final))
    mapspath=joinpath(dir,"synthetic-maps.jsonl")
    records=[(;map_index=i,map_role=i==2 ? "closure" : "iteration",status="PASS",
        n_in=(;sha256=final.n_in_sha256),n_out=(;sha256=final.n_out_sha256),
        unmixed_residual_l2=final.unmixed_residual_l2) for i in 1:2]
    write(mapspath,join(JSON3.write.(records),"\n")*"\n")
    evidencepath=joinpath(dir,"synthetic-evidence.json")
    evidence=Dict("runs"=>Dict("A"=>Dict("run_id"=>run_id,"label"=>"A","execution_status"=>"PASS","checkpoint_sha256"=>digest)),
        "basis"=>Dict("fft_grid"=>collect(shape),"n_electrons"=>10,"lattice_bohr"=>[[10.,0.,0.],[0.,10.,0.],[0.,0.,10.]]))
    synthetic_json(evidencepath,evidence)
    ref(path)=Dict("path"=>path,"sha256"=>SD.filehash(path),"bytes"=>filesize(path))
    plan=deepcopy(plan_template)
    plan["sources"]=Dict("A"=>Dict("run_id"=>run_id,"checkpoint"=>ref(sourcepath),
        "endpoint"=>ref(endpointpath),"receipt"=>ref(receiptpath),"maps"=>ref(mapspath),"historical_evidence_path"=>evidencepath))
    plan["source_evidence_sha256"]=Dict(evidencepath=>SD.filehash(evidencepath))
    planpath=joinpath(dir,"synthetic-plan.json");synthetic_json(planpath,plan)
    requestpath=joinpath(dir,"synthetic-request.json")
    synthetic_json(requestpath,Dict("schema_version"=>1,"plan_path"=>planpath,"plan_sha256"=>SD.filehash(planpath),"label"=>"A"))
    (;state,final,sourcepath,digest,requestpath,plan)
end

function run_soc_density_fft_tests()
    plan=SD.read_json(joinpath(SD.ROOT,"benchmarks/mg-soc-density-hartree-v1/plan.json"))
    thresholds=plan["thresholds"];points=plan["direct_fourier_miller_points"]
    identity=SD.environment_identity(SD.ROOT,(SD.DFTK,SD.PseudoPotentialIO))
    identity.status=="PASS" || error("Synthetic tests require the frozen environment")
    string(VERSION)=="1.12.7" || error("Frozen Julia required")
    SD.DFTK.disable_threading()
    @testset "Synthetic SOC density FFT and trusted-source protocol" begin
        shape=(40,42,44)
        lattice=[7.0 0.4 1.2;0.0 9.0 0.3;0.5 0.0 11.0]
        original=synthetic_density(shape,lattice)
        source_hash=SD.density_hash(original.n)
        transformed=SD.density_fourier(original.n,lattice,shape,points,10,thresholds)
        coeff=Dict(zip(transformed.millers,transformed.coefficients))
        @test transformed.diagnostics.status=="PASS"
        @test length(transformed.diagnostics.direct_sum_checks) == 17
        @test SD.density_hash(original.n)==source_hash
        @test minimum(original.n)>0
        @test abs(transformed.diagnostics.electron_count_real-10)<1e-12
        @test transformed.diagnostics.parseval_relative<=1e-13
        @test transformed.diagnostics.reciprocal_duality_max_abs<=1e-14
        @test length(coeff)==prod(shape)
        @test (-20,0,0) in keys(coeff)
        @test !haskey(coeff,(20,0,0))
        @test transformed.diagnostics.strict_negative_missing_count>0
        @test transformed.diagnostics.discrete_conjugacy_relative_l2<=1e-13
        nyquist=vec([10/abs(det(lattice))+.002*(-1.0)^i for i in 0:shape[1]-1,j in 0:shape[2]-1,k in 0:shape[3]-1])
        nyquist_fft=SD.density_fourier(nyquist,lattice,shape,points,10,thresholds)
        nyquist_coeff=Dict(zip(nyquist_fft.millers,nyquist_fft.coefficients))
        @test abs(nyquist_coeff[(-20,0,0)]-.002)<=1e-14
        @test !haskey(nyquist_coeff,(20,0,0))
        @test nyquist_fft.diagnostics.discrete_conjugacy_relative_l2<=1e-13
        # Independent explicit analytic coefficients and direct DFT signs, not
        # only an FFT/inverse-FFT round trip. Fixed absolute tolerance 1e-14.
        for m in points
            g=Tuple(m);expected=get(original.coefficients,g,0.0+0.0im)
            @test abs(coeff[g]-expected)<=1e-14
            @test abs(SD.direct_coefficient(original.n,shape,g)-expected)<=1e-14
        end
        @test imag(coeff[(2,-1,3)])<0
        volume=abs(det(lattice))
        @test maximum(abs,transformed.orthonormal_coefficients/sqrt(volume)-transformed.coefficients)==0
        @test abs(coeff[(0,0,0)]-10/volume)<1e-16
        @test abs(transformed.orthonormal_coefficients[1]-coeff[(0,0,0)])>1e-3 # catches lost sqrt(Omega)
        reciprocal=2pi*inv(transpose(lattice))
        # Standard independent Poisson arithmetic, with the analytic energy above.
        eh=2pi*volume*sum(abs2(v)/sum(abs2,reciprocal*collect(g)) for (g,v) in coeff if g!=(0,0,0))
        @test abs(eh-original.hartree)<=1e-13
        @test abs(2eh-original.hartree)>1e-5 # Ry/Ha or capacity-two mistake is detectable
        shifted=synthetic_density(shape,lattice;shift=(0.17,0.23,0.31))
        shifted_fft=SD.density_fourier(shifted.n,lattice,shape,points,10,thresholds)
        shifted_coeff=Dict(zip(shifted_fft.millers,shifted_fft.coefficients))
        @test shifted_fft.diagnostics.status=="PASS"
        @test abs(shifted_coeff[(1,2,3)]-shifted.coefficients[(1,2,3)])<=1e-14
        @test abs(shifted_coeff[(1,2,3)]-coeff[(1,2,3)])>1e-4
        shifted_eh=2pi*volume*sum(abs2(v)/sum(abs2,reciprocal*collect(g)) for (g,v) in shifted_coeff if g!=(0,0,0))
        @test abs(eh-shifted_eh)<=1e-13
        @test SD.density_fourier(2original.n,lattice,shape,points,10,thresholds).diagnostics.status=="FAIL"
        @test SD.density_fourier(original.n/3,lattice,shape,points,10,thresholds).diagnostics.status=="FAIL"
        wrongly_ordered=vec(permutedims(reshape(original.n,shape),(3,2,1)))
        @test abs(SD.direct_coefficient(wrongly_ordered,shape,(1,2,3))-original.coefficients[(1,2,3)])>1e-5
        @test_throws ErrorException SD.density_fourier(original.n[1:end-1],lattice,shape,points,10,thresholds)
        @test_throws ErrorException SD.density_fourier(fill(NaN,length(original.n)),lattice,shape,points,10,thresholds)
        @test_throws ErrorException SD.density_fourier(original.n,lattice,shape,points[1:14],10,thresholds)
        @test_throws ErrorException SD.density_fourier(original.n,lattice,shape,vcat(points[1:16],[points[1]]),10,thresholds)

        # SHA-before-deserialize is enforced even for malformed input bytes.
        mktempdir(joinpath(SD.ROOT,".work");prefix="phase7c-synthetic-") do temp
            fixture=synthetic_fixture(temp,plan)
            @test SD.trusted_checkpoint(fixture.sourcepath,fixture.digest).n_in==fixture.state.n_in
            called=Ref(false)
            badreader=io -> (called[]=true;error("Reader must not run"))
            @test_throws ErrorException SD.trusted_checkpoint(fixture.sourcepath,"0"^64;reader=badreader)
            @test !called[]
            malformed=joinpath(temp,"not-serialization.bin");write(malformed,"SYNTHETIC MALFORMED BYTES")
            @test_throws ErrorException SD.trusted_checkpoint(malformed,"0"^64;reader=badreader)
            @test !called[]
            @test_throws SD.MissingSource SD.trusted_checkpoint(joinpath(temp,"missing.bin"),fixture.digest)
            bad=merge(fixture.state,(;n_in=fixture.state.n_out,n_out=fixture.state.n_in))
            endpoint=JSON3.read(JSON3.write(fixture.final),Dict{String,Any})
            @test_throws ErrorException SD.bound_densities(bad,endpoint,(40,40,40),1000/64000,thresholds)
            @test_throws ErrorException SD.bound_densities(merge(fixture.state,(;n_in=Float32.(fixture.state.n_in))),endpoint,(40,40,40),1000/64000,thresholds)
            @test_throws ErrorException SD.bound_densities(merge(fixture.state,(;n_in=reshape(fixture.state.n_in,40,40,40))),endpoint,(40,40,40),1000/64000,thresholds)
            @test_throws ErrorException SD.bound_densities(merge(fixture.state,(;final=merge(fixture.final,(;map_count=3)))),endpoint,(40,40,40),1000/64000,thresholds)
            @test SD.bound_densities(fixture.state,endpoint,(40,40,40),1000/64000,thresholds).closure.status=="PASS"
            @test_throws ErrorException SD.require_plain(ForbiddenCheckpointObject(1))
            @test_throws ErrorException SD.require_plain((;bad=NaN))
            forbidden=joinpath(temp,"synthetic-unsupported.bin");serialize(forbidden,(;fixture.state...,final=ForbiddenCheckpointObject(1)))
            @test_throws ErrorException SD.trusted_checkpoint(forbidden,SD.filehash(forbidden))
            trailing=joinpath(temp,"synthetic-trailing.bin");write(trailing,vcat(read(fixture.sourcepath),UInt8[0]))
            @test_throws ErrorException SD.trusted_checkpoint(trailing,SD.filehash(trailing))
            badplan=deepcopy(fixture.plan);badplan["sources"]["A"]["run_id"]="WRONG_SYNTHETIC_RUN"
            @test_throws ErrorException SD.validate_historical_binding(badplan,"A",fixture.sourcepath)
            out=joinpath(temp,"success")
            @test SD.extract_request(fixture.requestpath,out)==0
            @test SD.read_json(joinpath(out,"metadata.json"))["execution_status"]=="PASS"
            before=read(joinpath(out,"metadata.json"))
            @test SD.extract_request(fixture.requestpath,out)==2
            @test read(joinpath(out,"metadata.json"))==before
            failure=joinpath(temp,"write-failure")
            failing_writer=(path,a,b)->error("SYNTHETIC CSV generation/write failure")
            @test SD.extract_request(fixture.requestpath,failure;csv_writer=failing_writer)==1
            @test SD.read_json(joinpath(failure,"metadata.json"))["execution_status"]=="FAIL"
            @test !isfile(joinpath(failure,"native.csv"))
            failure2=joinpath(temp,"summary-failure")
            summary_failure=(path,a,b)->(SD.write_native_csv(path,a,b);mkdir(joinpath(dirname(path),"summary.txt")))
            @test SD.extract_request(fixture.requestpath,failure2;csv_writer=summary_failure)==1
            @test SD.read_json(joinpath(failure2,"metadata.json"))["execution_status"]=="FAIL"
        end
        @test SD.main(["--help"])==0
        @test SD.main(String[])==2
    end
end

abspath(PROGRAM_FILE)==(@__FILE__) && run_soc_density_fft_tests()
