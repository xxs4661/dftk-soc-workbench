# SYNTHETIC protocol/definition checks only. No source bundle, context or solve.
using Test
include("../../../scripts/run_si_soc.jl")

@testset "complete real driver definitions and nonnumerical CLI" begin
    @test isempty(FI._FR_CONTEXT_CERTIFICATES)
    @test isempty(FI._BOUND_PSP_SOURCES)
    @test si_main(["--check-definitions"])==0
    @test si_main(["--help"])==0
    for args in (["--check-entry"], ["--resume-authorization"],
                 ["OPT-B0-SCF","OUT","--backend","soc-core","--core-gate","GATE","--check-entry"],
                 ["OPT-B0-SCF","OUT","--backend","legacy","--core-gate","GATE","--resume-authorization","AUTH"],
                 ["OPT-B0-GAMMA","OUT","--backend","soc-core","--core-gate","GATE","--resume-authorization","AUTH"],
                 ["D-SCF","OUT","--backend","soc-core","--core-gate","GATE","--resume-authorization","AUTH"],
                 ["OPT-B0-SCF","OUT","PARENT","--backend","soc-core","--core-gate","GATE","--resume-authorization","AUTH"],
                 ["--check-definitions","--check-entry"])
        @test si_main(args)==2
    end
    auth=Dict{String,Any}(k=>"SYNTHETIC" for k in ("resume_id","resume_preparation_commit","resume_from_commit",
        "static_execution_commit","endpoint_execution_commit","authorization_sha256"))
    scf=si_resume_fields(auth,"OPT-B0-SCF");gamma=si_resume_fields(auth,"OPT-B0-GAMMA")
    @test scf["attempt"]==2
    @test gamma["attempt"]==1
    @test scf["resume_authorization_sha256"]==auth["authorization_sha256"]
    @test si_resume_parent(scf,auth)===scf
    @test_throws ErrorException si_resume_parent(gamma,auth)
    @test_throws ErrorException si_resume_fields(auth,"D-SCF")
    @test_throws ErrorException si_sources(;resume=true)
    @test isempty(FI._FR_CONTEXT_CERTIFICATES)
    @test isempty(FI._BOUND_PSP_SOURCES)
end
