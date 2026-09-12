# Synthetic metadata and actual definitions only; no context or electronic solve.
using Test
include("../scripts/run_si_soc.jl")

@testset "Explicit extra contracts keep the historical physical inputs" begin
    for (profile,count) in (("B0",8),("K6",216))
        case=si_extra_case(profile)
        @test case["case"]=="soc-extra-v1/"*profile
        @test length(case["kpoints"])==count
        @test SOC.validate_soc_settings(case["settings"];case_contract=case)
        @test_throws ErrorException SOC.validate_soc_settings(deepcopy(case["settings"]);case_contract=case)
        for (section,key,value) in (("solver","stream_k",false),("solver","allow_band_expansion",true),
                ("solver","tolerance_ha",1e-8),("solver","initial_target_states",30),
                ("solver","auxiliary_states",0),("ensemble","tau_ha",.0005),("scf","alpha",.2),
                ("scf","max_maps",401))
            altered=deepcopy(case);altered["settings"][section][key]=value
            @test_throws ErrorException SOC.validate_soc_settings(altered["settings"];case_contract=altered)
        end
        altered=deepcopy(case);altered["kpoints"][1]["weight_spatial"]*=2
        @test_throws ErrorException SOC.validate_soc_settings(altered["settings"];case_contract=altered)
        altered=deepcopy(case);pop!(altered["kpoints"])
        @test_throws ErrorException SOC.validate_soc_settings(altered["settings"];case_contract=altered)
        altered=deepcopy(case);altered["extra_profile"]="K8"
        @test_throws ErrorException SOC.validate_soc_settings(altered["settings"];case_contract=altered)
    end
    @test_throws ErrorException si_extra_case("K8")
    @test_throws ErrorException si_case("K6") # Old route cannot impersonate extra.
    @test_throws ErrorException si_sources("K4";backend="soc-core")
    @test isempty(FI._FR_CONTEXT_CERTIFICATES) && isempty(FI._BOUND_PSP_SOURCES)
    @test si_main(["--check-definitions"])==0
end
