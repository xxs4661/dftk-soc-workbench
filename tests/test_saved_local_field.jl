#!/usr/bin/env julia
# Synthetic saved fields only. No historical arrays, UPF, model or XC evaluation.
using Test, LinearAlgebra, SHA, Serialization, JSON3
include("../scripts/extract_saved_local_field.jl")
const SL=SavedLocalFieldExtraction

function synthetic_saved_fields(shape,volume)
    nA=Float64[];nB=Float64[];nQ=Float64[];v=Float64[]
    for k in 0:shape[3]-1,j in 0:shape[2]-1,i in 0:shape[1]-1
        theta=2pi*(i/shape[1]+2j/shape[2]+k/shape[3])+.37
        phi=2pi*(2i/shape[1]-j/shape[2]+3k/shape[3])-.21
        a=.01+.002cos(theta)+.0007sin(phi)
        push!(nA,a);push!(nB,a+.00003cos(2pi*j/shape[2]+.11))
        push!(nQ,.01+.0019cos(theta)+.0006sin(phi))
        push!(v,.3+.4cos(theta)-.1sin(phi))
    end
    # The fixture writer creates the documented plain container, independent of
    # the reader; analytic Fourier coefficients below are the numerical oracle.
    arrays(n)=(;n=copy(n),vxc=zeros(length(n)),local_potential=copy(v),
        gradient=zeros(1,shape...,3),sigma=zeros(1,shape...))
    evaluations=Dict("A_original_n_out"=>arrays(nA),"B_original_n_out"=>arrays(nB),
        "Q_rep"=>arrays(nQ),"A_reconstructed"=>arrays(nA),"B_reconstructed"=>arrays(nB))
    grid=SL.DFTK.FFTGrid(shape,volume,SL.DFTK.CPU())
    millers=[Tuple(g) for g in vec(SL.DFTK.G_vectors(grid))]
    analytic=Dict((0,0,0)=>.3+0im,(1,2,1)=>.2cis(.37),(-1,-2,-1)=>.2cis(-.37),
        (2,-1,3)=>.05im*cis(-.21),(-2,1,-3)=>-.05im*cis(.21))
    local_nbar=ComplexF64[get(analytic,m,0im) for m in millers]
    raw=(;evaluations,reconstructed_complex=Dict("A"=>complex.(nA),"B"=>complex.(nB),"Q"=>complex.(nQ)),
        native_millers=millers,local_nbar)
    metadata=Dict{String,Any}("basis"=>Dict("fft_size"=>collect(shape),"volume_bohr3"=>volume),"evaluations"=>Dict{String,Any}())
    for name in SL.EVALUATIONS
        fields=evaluations[name]
        metadata["evaluations"][name]=Dict("status"=>"PASS",
            "array_sha256"=>Dict(string(k)=>SL.array_hash(a) for (k,a) in pairs(fields)),
            "density"=>Dict("sha256"=>SL.array_hash(fields.n)),
            "atomic_local_ha"=>volume*(name=="Q_rep" ? .00335 : .003365),"local_mean_ha"=>.3)
    end
    (;raw,metadata,analytic,nA,nB,nQ,v)
end

function run_saved_local_field_tests()
    # Phase 7E request section 11, fixed before synthetic execution. Production
    # reads the separately committed case plan, never these test constants.
    thresholds=Dict("fft_normalized"=>1e-11,"saved_local_energy_abs_ha"=>1e-8,
        "saved_local_mean_abs_ha"=>1e-11,"local_parseval_abs_ha"=>1e-9,"electron_count_abs"=>1e-8)
    identity=SL.SD.environment_identity(SL.ROOT,(SL.DFTK,SL.PseudoPotentialIO))
    identity.status=="PASS" && VERSION==v"1.12.7" || error("Frozen synthetic test environment required")
    SL.DFTK.disable_threading()
    points=[[0,0,0],[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1],
        [1,2,1],[-1,-2,-1],[2,-1,3],[-2,1,-3],[1,1,0],[-1,-1,0],
        [0,1,2],[0,-1,-2],[2,0,-1],[-2,0,1]]
    shape=(8,10,12);volume=1000.0;fixture=synthetic_saved_fields(shape,volume)
    physical=Dict("fft_size"=>collect(shape),"volume_bohr3"=>1000,"expected_electrons"=>10)
    @testset "Trusted saved local field and pure FFT" begin
        data=SL.saved_fields(fixture.raw,fixture.metadata,physical,thresholds,points)
        @test data.report.status=="PASS"
        @test data.report.physical_node_count==960
        @test data.report.local_fft.mean≈.3 atol=1e-14
        @test data.report.local_fft.g0[1]≈.3 atol=1e-14
        @test data.report.local_fft.complex_roundtrip_normalized<=1e-14
        @test data.report.local_fft.parseval_normalized<=1e-14
        @test maximum(x.normalized_error for x in data.report.local_fft.direct_checks)<=1e-14
        @test data.report.local_nbar_restoration_normalized<=1e-14
        @test data.report.saved_density_checks["A"].local_integral_ha≈3.365 atol=1e-12
        @test data.report.saved_density_checks["B"].local_integral_ha≈3.365 atol=1e-12
        @test data.report.saved_density_checks["Q"].local_integral_ha≈3.35 atol=1e-12
        @test all(abs(x.real_fourier_difference_ha)<=1e-12 for x in values(data.report.saved_density_checks))
        @test all(abs(x.electron_count-10)<=1e-12 for x in values(data.report.saved_density_checks))
        @test !data.report.applied_mean_shift && !data.report.applied_density_normalization
        @test all(abs(z-get(fixture.analytic,m,0im))<=1e-14 for (m,z) in zip(data.millers,data.coefficients))
        # Changing the array while retaining historical hashes is always rejected.
        for change in (:mean,:units,:axes,:origin,:conjugate,:density_swap)
            bad=deepcopy(fixture.raw)
            if change==:mean
                bad.evaluations["A_original_n_out"].local_potential .-= .3
            elseif change==:units
                bad.evaluations["A_original_n_out"].local_potential .*= 2
            elseif change==:axes
                a=reshape(fixture.v,shape)
                bad.evaluations["A_original_n_out"].local_potential .= vec(permutedims(a,(2,1,3)))
            elseif change==:origin
                bad.evaluations["A_original_n_out"].local_potential .= circshift(fixture.v,1)
            elseif change==:conjugate
                bad.local_nbar .= conj.(bad.local_nbar)
            else
                bad.evaluations["A_original_n_out"].n .= fixture.nB
            end
            @test_throws ErrorException SL.saved_fields(bad,fixture.metadata,physical,thresholds,points)
        end
        bad=deepcopy(fixture.raw);reverse!(bad.native_millers)
        @test_throws ErrorException SL.saved_fields(bad,fixture.metadata,physical,thresholds,points)
        bad=deepcopy(fixture.raw);bad.evaluations["Q_rep"].n[1]=NaN
        @test_throws ErrorException SL.saved_fields(bad,fixture.metadata,physical,thresholds,points)
        wrongmeta=deepcopy(fixture.metadata);wrongmeta["evaluations"]["A_original_n_out"]["local_mean_ha"]=0
        @test_throws ErrorException SL.saved_fields(fixture.raw,wrongmeta,physical,thresholds,points)
        wrongmeta=deepcopy(fixture.metadata);wrongmeta["evaluations"]["Q_rep"]["atomic_local_ha"]*=2
        @test_throws ErrorException SL.saved_fields(fixture.raw,wrongmeta,physical,thresholds,points)
        wrongphysical=copy(physical);wrongphysical["expected_electrons"]=20
        @test_throws ErrorException SL.saved_fields(fixture.raw,fixture.metadata,wrongphysical,thresholds,points)
        @test_throws ErrorException SL.field_fourier(vcat(fixture.v,fixture.v[1]),shape,volume,points,1e-11)
        @test_throws ErrorException SL.field_fourier(fixture.v,shape,volume,points[1:14],1e-11)
        @test_throws ErrorException SL.field_fourier(fixture.v,shape,volume,vcat(points,[points[1]]),1e-11)
        @test_throws ErrorException SL.field_fourier(fixture.v,shape,NaN,points,1e-11)
        # Integer-valued JSON volume still selects ComplexF64 FFT arithmetic.
        integer_volume=JSON3.read("{\"volume\":1000.0}",Dict{String,Any})["volume"]
        @test integer_volume isa Integer
        @test SL.field_fourier(fixture.v,shape,integer_volume,points,1e-11).coefficients isa Vector{ComplexF64}
        mkpath(joinpath(SL.ROOT,".work","phase7e-preflight"))
        mktempdir(joinpath(SL.ROOT,".work","phase7e-preflight")) do dir
            path=joinpath(dir,"synthetic-arrays.bin");serialize(path,fixture.raw);sha=SL.SD.filehash(path)
            raw=SL.trusted_arrays(path,sha)
            @test raw==fixture.raw
            calls=Ref(0)
            reader=io->begin calls[]+=1;deserialize(io) end
            @test_throws ErrorException SL.trusted_arrays(path,repeat("0",64);reader)
            @test calls[]==0 # source is rejected BEFORE deserialize
            open(path,"a") do io;write(io,UInt8(0));end
            @test_throws ErrorException SL.trusted_arrays(path,SL.SD.filehash(path))
            serialize(path,(;evaluations=fixture.raw.evaluations))
            @test_throws ErrorException SL.trusted_arrays(path,SL.SD.filehash(path))
            malformed=merge(fixture.raw,(;reconstructed_complex=Dict("Q"=>Ref(1.0))))
            serialize(path,malformed)
            @test_throws ErrorException SL.trusted_arrays(path,SL.SD.filehash(path))
            incomplete=deepcopy(fixture.raw);delete!(incomplete.evaluations,"B_original_n_out")
            serialize(path,incomplete)
            @test_throws ErrorException SL.trusted_arrays(path,SL.SD.filehash(path))
            out=joinpath(dir,"output");mkpath(out);output=SL.write_outputs(out,data)
            lines=readlines(joinpath(out,"native.csv"));@test length(lines)==961
            @test lines[1]=="m1,m2,m3,V_D_real,V_D_imag"
            @test !occursin('\r',read(joinpath(out,"native.csv"),String))
            reread=map(lines[2:end]) do line
                row=split(line,',');complex(parse(Float64,row[4]),parse(Float64,row[5]))
            end
            @test reread==data.coefficients
            fields=readlines(joinpath(out,"fields.csv"));@test fields[1]=="n_A,n_B,n_Q,V_D"
            values=reduce(hcat,[parse.(Float64,split(line,',')) for line in fields[2:end]])
            @test vec(values[1,:])==fixture.nA
            @test vec(values[2,:])==fixture.nB
            @test vec(values[3,:])==fixture.nQ
            @test vec(values[4,:])==fixture.v
            @test output.native.sha256==SL.SD.filehash(joinpath(out,"native.csv"))
            # Failed request publishes only a current failure, never an old PASS.
            request=joinpath(dir,"bad-request.json");write(request,"{\"schema_version\":999,\"run_id\":\"synthetic-bad\"}")
            failed=joinpath(dir,"failure");@test SL.main([request,failed])==1
            failure=SL.SD.read_json(joinpath(failed,"metadata.json"))
            @test failure["execution_status"]=="FAIL" && failure["exit_code"]==1
            @test !isfile(joinpath(failed,"native.csv"))
        end
        @test SL.main(["--help"])==0
        @test SL.main(String[])==2
    end
end
run_saved_local_field_tests()
