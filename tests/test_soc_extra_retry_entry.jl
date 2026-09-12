# Synthetic entry/monitor protocol only: no DFTK context, Hamiltonian or solve.
using Test, JSON3, SHA, Serialization, LinearAlgebra
const PHASE6C_ROOT=normpath(joinpath(@__DIR__,".."))
module FakeDFTK
    disable_threading()=nothing
end
module FakePPIO end
module FakeFI
    using SHA
    const _FR_CONTEXT_CERTIFICATES=Dict()
    const _BOUND_PSP_SOURCES=Dict()
    integration_density_hash(n)=bytes2hex(sha256(reinterpret(UInt8,vec(n))))
end
const DFTK=FakeDFTK;const PseudoPotentialIO=FakePPIO;const FI=FakeFI
filehash(path)=bytes2hex(sha256(read(path)))
const READ_HOOK=Ref{Any}(nothing)
function si_json(path)
    value=JSON3.read(read(path,String),Dict{String,Any})
    isnothing(READ_HOOK[]) || READ_HOOK[](path)
    value
end
phase6b_write(path,x;kwargs...)=write(path,JSON3.write(x))
environment_identity(args...)=(;status="PASS",scope="SYNTHETIC_ENVIRONMENT_STUB")
include(joinpath(PHASE6C_ROOT,"benchmarks/soc-extra-v1/driver.jl"))
const FIXTURE_AUTH=Ref{Any}(nothing)
const AUTH_CALLS=Any[]
const MUTATE_SOURCES=Ref{Any}(nothing)
function si_extra_authorization(path,profile;action=nothing,outdir=nothing,check=false)
    push!(AUTH_CALLS,(;action,outdir,check));deepcopy(FIXTURE_AUTH[])
end
si_extra_case(profile)=si_json(joinpath(SI_EXTRA_DIR,profile*".json"))
function si_extra_check_sources(auth)
    isnothing(MUTATE_SOURCES[]) || MUTATE_SOURCES[]()
    true
end
function synthetic_fixture(body)
    area=joinpath(PHASE6C_ROOT,".work/phase9a-extra/runs");mkpath(area)
    mktempdir(area;prefix="synthetic-entry-") do home
        E=strip(read(`git -C $PHASE6C_ROOT rev-parse HEAD`,String));case=si_extra_case("K6")
        policy=Dict{String,Any}("schema_version"=>1,"policy_id"=>"k6-scf-attempt2-10gib-v1","run_id"=>"synthetic-parent", "action"=>"X-K6-SCF","case_sha256"=>"c"^64,"execution_commit"=>E,"limit_bytes"=>10*1024^3,"warning_bytes"=>8*1024^3,"remaining_growth_bytes"=>2021087414)
        child=merge(copy(policy),Dict("policy_id"=>"k6-gamma-entry-8gib-v1","action"=>"X-K6-GAMMA","run_id"=>"synthetic-child-ENTRY","limit_bytes"=>8*1024^3,"warning_bytes"=>7*1024^3,"remaining_growth_bytes"=>1024^3))
        ph=bytes2hex(sha256(JSON3.write(policy)));ch=bytes2hex(sha256(JSON3.write(child)))
        auth=Dict{String,Any}("execution_commit"=>E,"case_sha256"=>"c"^64,"contract_sha256"=>"a"^64,"executed_source_sha256"=>Dict("synthetic"=>"b"^64),"core_selection"=>"baseline","continuation_id"=>"k6-scf-attempt2-10gib-v1","resource_policies"=>Dict("X-K6-SCF"=>policy),"resource_policy_hashes"=>Dict("X-K6-SCF"=>ph),"selected_resource_policy"=>child,"selected_resource_policy_sha256"=>ch)
        parent=joinpath(home,"synthetic-parent-dftk");mkpath(parent)
        cp=joinpath(parent,"final.bin");raw=(;n_out=[1.,2.,5.]);serialize(cp,raw)
        receipt=Dict{String,Any}("schema_version"=>1,"phase"=>"9A-extra","extra_profile"=>"K6","case"=>case["case"],"action"=>"X-K6-SCF","execution_status"=>"PASS","exit_code"=>0,"runtime_closed"=>true,"runtime_dispatch_status"=>"PASS","resource_policy_status"=>"WORKER_BOUNDARY_CHECKS_PASS","run_id"=>basename(parent),"input"=>Dict("sha256"=>case["pseudo"]["sha256"]),"final"=>Dict("closure_status"=>"PASS","diagnostics"=>Dict("target_states"=>24),"n_out_sha256"=>FI.integration_density_hash(raw.n_out)),"checkpoint_sha256"=>filehash(cp),"grid"=>Dict("basis"=>Dict("n_electrons"=>8,"fft_grid"=>case["fft_size"],"ecut_ha"=>30,"kpoints"=>case["kpoints"])),"resource_policy"=>deepcopy(policy),"resource_policy_sha256"=>ph)
        for k in ("execution_commit","case_sha256","contract_sha256","executed_source_sha256");receipt[k]=auth[k];end
        phase6b_write(joinpath(parent,"result.json"),receipt)
        run=joinpath(home,child["run_id"]);mkpath(run);out=joinpath(run,child["run_id"]*"-dftk")
        policyfile=joinpath(run,"resource-policy.json");write(policyfile,JSON3.write(child))
        FIXTURE_AUTH[]=auth;empty!(AUTH_CALLS);MUTATE_SOURCES[]=nothing;READ_HOOK[]=nothing
        withenv("SOC_EXTRA_RESOURCE_POLICY_FILE"=>policyfile,"SOC_EXTRA_RUN_ID"=>child["run_id"],"SOC_EXTRA_WORKER_DIRECTORY"=>basename(out),"SOC_EXTRA_STOP_FILE"=>joinpath(run,"safe-boundary-stop.json")) do
            body((;home,parent,receipt,auth,case,policy,child,out,run,cp))
        end
    end
end
BLAS.set_num_threads(1)
@testset "Synthetic authentic Gamma parent echo" begin
    synthetic_fixture() do f
        before=(filehash(joinpath(f.parent,"result.json")),filehash(f.cp))
        @test si_extra_check_entry("X-K6-GAMMA",f.out,f.parent,"K6","synthetic-auth")==0
        result=si_json(joinpath(f.out,"result.json"))
        @test get(result,"parent_result_sha256",nothing)==before[1]
        @test get(result,"parent_checkpoint_sha256",nothing)==before[2]
        @test result["context_constructed"]===false && result["formal_slot_reserved"]===false
        @test result["numerical_execution_status"]=="NOT_RUN"
        @test result["resource_policy_status"]=="WORKER_BOUNDARY_CHECKS_PASS"
        @test before==(filehash(joinpath(f.parent,"result.json")),filehash(f.cp))
    end
end

@testset "Synthetic parent refusal and invariance" begin
    mutations=[r->(r["execution_status"]="FAIL"),r->(r["exit_code"]=1),r->(r["action"]="X-K6-PILOT"),
        r->(r["run_id"]="other-dftk"),r->(r["execution_commit"]="0"^40),r->(r["extra_profile"]="B0"),
        r->(r["runtime_closed"]=false),r->(r["resource_policy_status"]="STOP_REQUESTED"),r->(r["safe_boundary_stop_requested"]=true),r->(r["schema_version"]=true),r->(r["resource_policy_sha256"]="0"^64),
        r->(r["final"]["closure_status"]="FAIL"),r->delete!(r,"checkpoint_sha256"),
        r->(r["checkpoint_sha256"]="0"^64),r->(r["final"]["n_out_sha256"]="0"^64),
        r->(r["resource_policy"]["limit_bytes"]=8*1024^3)]
    for mutate in mutations
        synthetic_fixture() do f
            mutate(f.receipt);phase6b_write(joinpath(f.parent,"result.json"),f.receipt)
            @test si_extra_check_entry("X-K6-GAMMA",f.out,f.parent,"K6","synthetic-auth")!=0
            result=si_json(joinpath(f.out,"result.json"))
            @test result["execution_status"]=="FAIL" && result["context_constructed"]===false
            @test result["formal_slot_reserved"]===false
        end
    end
    for value in (nothing,"incorrect type",[1,2],42)
        synthetic_fixture() do f
            phase6b_write(joinpath(f.parent,"result.json"),value)
            @test si_extra_check_entry("X-K6-GAMMA",f.out,f.parent,"K6","synthetic-auth")!=0
        end
    end
    for file in ("result.json","final.bin")
        synthetic_fixture() do f
            MUTATE_SOURCES[]=()->open(io->write(io,UInt8(0)),joinpath(f.parent,file),"a")
            @test si_extra_check_entry("X-K6-GAMMA",f.out,f.parent,"K6","synthetic-auth")!=0
            @test occursin("parent changed",si_json(joinpath(f.out,"result.json"))["reason"])
        end
    end
    synthetic_fixture() do f
        receipt_path=joinpath(f.parent,"result.json")
        READ_HOOK[]=path->(path==receipt_path && open(io->write(io," "),path,"a"))
        @test si_extra_check_entry("X-K6-GAMMA",f.out,f.parent,"K6","synthetic-auth")!=0
        @test occursin("parent changed during read",si_json(joinpath(f.out,"result.json"))["reason"])
    end
    synthetic_fixture() do f
        serialize(f.cp,(;n_out=[NaN]));f.receipt["checkpoint_sha256"]=filehash(f.cp)
        phase6b_write(joinpath(f.parent,"result.json"),f.receipt)
        @test si_extra_check_entry("X-K6-GAMMA",f.out,f.parent,"K6","synthetic-auth")!=0
    end
    synthetic_fixture() do f
        @test si_extra_check_entry("X-K6-GAMMA",f.out,f.parent,"K6","synthetic-auth")==0
        @test length(AUTH_CALLS)==2 && all(c->c.check===true,AUTH_CALLS)
        @test all(c->c.action=="X-K6-GAMMA",AUTH_CALLS)
        @test isempty(FI._FR_CONTEXT_CERTIFICATES) && isempty(FI._BOUND_PSP_SOURCES)
        @test !ispath(joinpath(f.run,"slot.json"))
        @test f.auth["resource_policies"]["X-K6-SCF"]["limit_bytes"]==10*1024^3
        @test si_json(joinpath(f.out,"result.json"))["resource_policy"]["limit_bytes"]==8*1024^3
    end
end

function selected_state(f;limit=8*1024^3,growth=2021087414)
    policy=copy(f.child);policy["limit_bytes"]=limit;policy["remaining_growth_bytes"]=growth
    if limit==10*1024^3
        policy["action"]="X-K6-SCF";policy["policy_id"]="k6-scf-attempt2-10gib-v1";policy["warning_bytes"]=8*1024^3
    end
    auth=deepcopy(f.auth);auth["selected_resource_policy"]=policy
    write(joinpath(f.run,"resource-policy.json"),JSON3.write(policy))
    auth["selected_resource_policy_sha256"]=filehash(joinpath(f.run,"resource-policy.json"))
    si_extra_boundary_state(f.out,auth)
end
@testset "Synthetic fixed resource policy and first cause" begin
    synthetic_fixture() do f
        state=selected_state(f)
        @test isnothing(si_extra_report_boundary!(state,"synthetic_low",1024^3))
        report=si_json(joinpath(f.run,"resource-highwater.json"))
        @test report["highwater_bytes"]==1024^3 && report["units"]=="bytes"
        @test report["resource_policy_sha256"]==state.policy_sha256
        @test report["run_id"]==f.child["run_id"]
        @test isnothing(si_extra_report_boundary!(state,"synthetic_rss_fall",1024))
        @test si_json(joinpath(f.run,"resource-highwater.json"))["highwater_bytes"]==1024^3
        @test_throws ErrorException si_extra_report_boundary!(state,"synthetic_below_warning",7447937024)
        stop=joinpath(f.run,"safe-boundary-stop.json");first=read(stop)
        @test si_json(stop)["resource_decision"]["status"]=="STOP_AT_SAFE_BOUNDARY"
        @test !isnothing(state.first_stop_sha256)
        @test_throws ErrorException si_extra_report_boundary!(state,"synthetic_fall_after_stop",1024)
        @test read(stop)==first
        write(stop,String(first)*" ")
        @test_throws ErrorException si_extra_report_boundary!(state,"synthetic_stop_changed",1024)
    end
    for limit in (8*1024^3,10*1024^3)
        synthetic_fixture() do f
            state=selected_state(f;limit);edge=limit-state.policy["remaining_growth_bytes"]
            @test isnothing(si_extra_report_boundary!(state,"synthetic_below_equality",edge-1))
            @test_throws ErrorException si_extra_report_boundary!(state,"synthetic_equality",edge)
            @test si_json(joinpath(f.run,"safe-boundary-stop.json"))["resource_decision"]["screen_peak_bytes"]==edge
        end
        synthetic_fixture() do f
            state=selected_state(f;limit)
            @test_throws ErrorException si_extra_report_boundary!(state,"synthetic_emergency",limit)
            @test si_json(joinpath(f.run,"safe-boundary-stop.json"))["resource_decision"]["status"]=="RESOURCE_LIMIT"
        end
    end
    synthetic_fixture() do f
        state=selected_state(f;limit=10*1024^3)
        @test isnothing(si_extra_report_boundary!(state,"synthetic_8GiB_under_10",8*1024^3))
        @test !ispath(joinpath(f.run,"safe-boundary-stop.json"))
    end
    for invalid in (nothing,-1,NaN,true,1.5,0)
        synthetic_fixture() do f
            @test_throws ErrorException si_extra_report_boundary!(selected_state(f),"synthetic_invalid",invalid)
        end
    end
    synthetic_fixture() do f
        state=selected_state(f);path=joinpath(f.run,"resource-policy.json")
        write(path,read(path,String)*" ")
        @test_throws ErrorException si_extra_report_boundary!(state,"synthetic_policy_tamper",1)
    end
    synthetic_fixture() do f
        bad=deepcopy(f.auth);delete!(bad,"selected_resource_policy")
        @test_throws ErrorException si_extra_boundary_state(f.out,bad)
    end
    synthetic_fixture() do f
        bad=deepcopy(f.auth);bad["selected_resource_policy"]["limit_bytes"]=10*1024^3
        write(joinpath(f.run,"resource-policy.json"),JSON3.write(bad["selected_resource_policy"]))
        bad["selected_resource_policy_sha256"]=filehash(joinpath(f.run,"resource-policy.json"))
        @test_throws ErrorException si_extra_boundary_state(f.out,bad) # Gamma never inherits parent limit.
    end
end

@testset "Edited driver definitions parse" begin
    parsed(value)=!(value isa Expr) || (!(value.head in (:error,:incomplete)) && all(parsed,value.args))
    for file in ("benchmarks/soc-extra-v1/driver.jl","scripts/run_si_soc.jl")
        @test parsed(Meta.parseall(read(joinpath(PHASE6C_ROOT,file),String)))
    end
end

@testset "Synthetic foreign stop and immutable first request" begin
    for mutation in (r->(r["run_id"]="another"),r->(r["execution_commit"]="0"^40),
        r->(r["resource_policy_sha256"]="0"^64),r->(r["schema_version"]=true),
        r->(r["case_sha256"]="0"^64),r->(r["action"]="X-K6-SCF"),
        r->(r["resource_decision"]["remaining_growth_bytes"]-=1),
        r->(r["resource_decision"]["limit_bytes"]=10*1024^3),
        r->(r["resource_decision"]["screen_peak_bytes"]-=1),r->(r["first_requested_unix_time"]=-1))
        synthetic_fixture() do f
            state=selected_state(f);peak=7447937024
            stop=merge(si_extra_monitor_identity(state),Dict("policy_id"=>state.policy["policy_id"],
                "first_requested_unix_time"=>time(),"resource_decision"=>Dict{String,Any}(
                    "status"=>"STOP_AT_SAFE_BOUNDARY","reason"=>"synthetic group headroom",
                    "current_group_rss_bytes"=>1024,"peak_group_rss_bytes"=>peak,
                    "worker_highwater_bytes"=>1024,"screen_peak_bytes"=>peak,
                    "remaining_growth_bytes"=>state.policy["remaining_growth_bytes"],
                    "limit_bytes"=>state.policy["limit_bytes"],"warning_bytes"=>state.policy["warning_bytes"])))
            mutation(stop);path=joinpath(f.run,"safe-boundary-stop.json");write(path,JSON3.write(stop))
            before=filehash(path)
            @test_throws ErrorException si_extra_report_boundary!(state,"synthetic_foreign_stop",1024)
            @test state.first_stop_sha256===nothing && filehash(path)==before
        end
    end
    synthetic_fixture() do f
        state=selected_state(f)
        @test_throws ErrorException si_extra_report_boundary!(state,"synthetic_latch",7447937024)
        first=state.first_stop_sha256;rm(joinpath(f.run,"safe-boundary-stop.json"))
        @test_throws ErrorException si_extra_report_boundary!(state,"synthetic_removed",1024)
        @test state.first_stop_sha256==first && !ispath(joinpath(f.run,"safe-boundary-stop.json"))
    end
end
