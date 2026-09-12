# Synthetic entry/profiling-protocol tests. No dependency load or real context.
using Test, SHA
include(joinpath(@__DIR__,"../benchmarks/soc-extra-v1/profile.jl"))
const XP=SOCExtraProfile

@testset "Extra baseline route never borrows an old suite or accepts an implicit candidate" begin
    @test XP.parse_options(["--help"])===nothing
    @test XP.safe_main(["--help"])==0
    for label in ("B0","K4")
        args=["--root","/synthetic","--case",label,"--mode","baseline","--output","/synthetic/new"]
        @test XP.parse_options(args)["--case"]==label
        @test XP.parse_options(vcat(args,["--check-only"]))["--check-only"]=="true"
        @test XP.parse_options(args)["--check-only"]=="false"
        @test_throws ArgumentError XP.parse_options(vcat(args,["--check-only","--check-only"]))
    end
    @test_throws ArgumentError XP.parse_options(String[])
    @test_throws ArgumentError XP.parse_options(["--help","--case","B0"])
    for (label,mode) in (("K6","baseline"),("B0","candidate"),("REF-B0","baseline"),("B0","legacy"))
        @test_throws ArgumentError XP.parse_options(["--root","x","--case",label,"--mode",mode,"--output","y"])
    end
    args=["--root","x","--case","B0","--mode","candidate","--output","y","--baseline-result","baseline.json"]
    @test XP.parse_options(args)["--baseline-result"]=="baseline.json"
    @test_throws ArgumentError XP.parse_options(["--root","x","--case","B0","--mode","baseline","--output","y","--baseline-result","baseline.json"])
    @test !isdefined(Main,:DFTK)
    @test !isdefined(Main,:FRIntegration)
end

@testset "Four operations retain five timing samples separately from profiler repetitions" begin
    @test XP.OPERATIONS==("FR_1","FR_24","full_H_24","pipeline_with_validation")
    calls=Ref(0);consumed=Ref(0);indices=Int[]
    f=()->(calls[]+=1)
    consume=x->begin consumed[]+=1; x end
    sampled=XP.SOCCoreMemory.measure_operation(f;consume,name="synthetic",on_sample=r->push!(indices,length(r["samples"])))
    @test calls[]==consumed[]==6
    @test indices==collect(0:5)
    @test sampled.report["warmup"]["index"]==0
    @test [s["index"] for s in sampled.report["samples"]]==collect(1:5)
    # Diagnostic calls change neither the completed sample list nor statistics.
    old_report=deepcopy(sampled.report)
    for name in XP.OPERATIONS
        before=calls[];XP.profile_work(f,consume,XP.PROFILE_CALLS[name])
        @test calls[]-before==XP.PROFILE_CALLS[name]
    end
    @test sampled.report==old_report
    @test calls[]==consumed[]
    @test XP.PROFILE_CALLS==Dict("FR_1"=>100,"FR_24"=>50,"full_H_24"=>3,"pipeline_with_validation"=>1)
    @test_throws ArgumentError XP.profile_work(f,consume,0)
    @test_throws ArgumentError XP.profile_work(f,consume,true)
    attempted=Ref(0)
    @test_throws ErrorException XP.profile_work(()->begin attempted[]+=1;error("synthetic operation failure") end,identity,3)
    @test attempted[]==1
end

@testset "No old output reuse, parent alias, or unconfined source" begin
    mktempdir() do temporary
        root=realpath(temporary)
        run=joinpath(root,".work/phase9a-extra/performance/synthetic")
        @test XP.prepare_output(root,run)==run
        write(joinpath(run,"worker-result.json"),"synthetic old result")
        @test_throws ArgumentError XP.prepare_output(root,run)
        @test read(joinpath(run,"worker-result.json"),String)=="synthetic old result"
        @test_throws ArgumentError XP.prepare_output(root,joinpath(root,"outside"))
        @test_throws ArgumentError XP.prepare_output(root,joinpath(root,".work/phase9a-extra/performance"))
        destination=joinpath(root,"elsewhere");mkdir(destination)
        link=joinpath(root,".work/phase9a-extra/performance/alias");symlink(destination,link)
        @test_throws ArgumentError XP.prepare_output(root,joinpath(link,"attempt"))
        @test !ispath(joinpath(destination,"attempt"))
        path="synthetic.bin";write(joinpath(root,path),UInt8[1,2,3])
        expected=bytes2hex(sha256(UInt8[1,2,3]))
        row=XP.checked_file(root,path;expected_sha=expected,bytes=3)
        @test row.sha256==expected && row.bytes==3
        @test_throws ArgumentError XP.checked_file(root,path;expected_sha=repeat("0",64))
        @test_throws ArgumentError XP.checked_file(root,path;bytes=4)
        @test_throws ArgumentError XP.checked_file(root,"../synthetic.bin")
        @test_throws ArgumentError XP.checked_file(root,joinpath(root,path))
        symlink(joinpath(root,path),joinpath(root,"alias.bin"))
        @test_throws ArgumentError XP.checked_file(root,"alias.bin")
    end
end

@testset "Baseline closure protects actual numerical source, separately identifies unused SCF adapters" begin
    for path in ("src/soc_kernels/nonlocal.jl","prototypes/fr_integration/runtime.jl",
        "prototypes/fr_integration/hamiltonian.jl","prototypes/relativistic/radial.jl",
        "prototypes/spinor/density.jl","prototypes/soc_scf/ensemble.jl","scripts/workbench_environment.jl")
        @test XP.baseline_path(path)
    end
    @test !XP.baseline_path("prototypes/soc_scf/solver.jl")
    @test !XP.baseline_path("prototypes/soc_scf/scf.jl")
    @test XP.BASE=="7630172808773a3d4ac2da825c27fe43a8705fb8"
    @test XP.LIMIT_BYTES==8*1024^3
    @test XP.ALLOCATION_SAMPLE_RATE==0.001
    @test XP.PROFILE_DELAY==0.002
end

@testset "Synthetic candidate arithmetic preserves scalar and array contracts" begin
    rows=Any[]
    XP.compare_values!(rows,(;operator=[1.0,2.0],energy=3.0),(;operator=[1.0,2.0+1e-13],energy=3.0+1e-11),"synthetic")
    @test length(rows)==2 && all(row.status=="PASS" for row in rows)
    rows=Any[]
    XP.compare_values!(rows,[1.0,2.0],[1.0,2.0+1e-8],"synthetic/operator")
    @test only(rows).status=="FAIL"
    rows=Any[]
    XP.compare_values!(rows,1.0,1.0+1e-8,"synthetic/energy")
    @test only(rows).status=="FAIL"
    @test_throws ArgumentError XP.compare_values!(Any[],[NaN],[NaN],"nonfinite")
    @test_throws ArgumentError XP.compare_values!(Any[],ones(2),ones(3),"shape")
    @test_throws ArgumentError XP.compare_values!(Any[],(;a=1.0),(;b=1.0),"fields")
    @test_throws ArgumentError XP.compare_values!(Any[],[1.0],Float32[1.0],"type")
end

# Only this stdlib test process defines the synthetic stub. Real profiling loads
# the unmodified keyword-only helper from the authenticated old measure.jl.
function old_roots(;data=nothing,built=nothing,H=nothing,outputs=nothing,energy=nothing)
    (;data,built,H,outputs,energy)
end
@testset "Synthetic actual keyword-only inventory call rejects the old positional mistake" begin
    payload=(;X=ones(ComplexF64,2,1));rhs=Dict(1=>ones(ComplexF64,2))
    built=(;ctx=:synthetic_context);H=(;full=[:synthetic_hamiltonian])
    @test_throws MethodError old_roots(data=(;payload,rhs),built,H)
    actual=XP.profile_roots(payload,rhs,built,H)
    @test actual.data.payload===payload
    @test actual.data.rhs===rhs
    @test actual.built===built
    @test actual.H===H
    @test actual.outputs===nothing && actual.energy===nothing
    second=XP.profile_roots(payload,rhs,built,H)
    @test second==actual
end
