# Synthetic interface/FD/receipt tests only. No source payload, context, SCF or eigensolve.
using Test
include("../scripts/run_si_soc.jl")

struct SyntheticSensitivityTemperatureContext
    basis::NamedTuple
end
# Fault injection for this synthetic type only: reach the existing model/settings
# guard without constructing a source, basis, Hamiltonian or iteration controller.
FI.validate_context(::SyntheticSensitivityTemperatureContext)=nothing

function sensitivity_parent(case)
    Dict{String,Any}("schema_version"=>1,"case"=>case["case"],"base_commit"=>SI_SENSITIVITY_BASE,
        "sensitivity_profile"=>case["sensitivity_profile"],
        "case_sha256"=>filehash(joinpath(PHASE6C_ROOT,si_case_path(case["sensitivity_profile"]))),
        "temperature_ha"=>case["electrons"]["temperature_ha"],"run_id"=>"synthetic-parent",
        "action"=>"D-SCF","execution_status"=>"PASS","exit_code"=>0,
        "execution_commit"=>"b"^40,"executed_source_sha256"=>Dict("synthetic"=>"a"^64),
        "input"=>Dict("sha256"=>case["pseudo"]["sha256"],"element"=>"Si","z_valence"=>4,
            "functional"=>"PBE","mode"=>"real_fr","has_so"=>true,"nlcc_present"=>true,
            "xc_identifiers"=>case["xc"]["dftk_identifiers"]),
        "grid"=>Dict("status"=>"PASS","basis"=>Dict("fft_grid"=>case["fft_size"],
            "n_electrons"=>8,"ecut_ha"=>case["cutoffs"]["dftk_ecut_ha"],
            "lattice_bohr"=>case["geometry"]["lattice_vectors_bohr"],
            "positions_fractional"=>case["geometry"]["positions_fractional"],"kpoints"=>deepcopy(case["kpoints"]))),
        "final"=>Dict("diagnostics"=>Dict("target_states"=>24)))
end

@testset "Si sensitivity restricted Julia interfaces (synthetic only)" begin
    old=si_case();settings=old["settings"]
    @test length(old["kpoints"])==8 && length(old["probe_kpoints"])==3
    @test old["cutoffs"]["dftk_ecut_ha"]==30 && old["electrons"]["temperature_ha"]==.001
    @test SOC.validate_soc_settings(settings)
    bad=deepcopy(settings);bad["ensemble"]["tau_ha"]=.0005
    @test_throws ErrorException SOC.validate_soc_settings(bad)
    @test_throws ErrorException si_case("unregistered")
    for profile in ("E40","T05","K4")
        case=si_case(profile);settings=case["settings"]
        tau=profile=="T05" ? .0005 : .001
        @test SOC.validate_soc_settings(settings;case_contract=case)
        @test case["electrons"]["temperature_ha"]==settings["ensemble"]["tau_ha"]==tau
        @test length(case["kpoints"])==(profile=="K4" ? 64 : 8)
        @test case["probe_kpoints"]==[[0.,0.,0.]] && case["probe_weights"]==[1.]
        @test_throws ErrorException SOC.validate_soc_settings(deepcopy(settings);case_contract=case)
        for (group,key,value) in (("ensemble","tau_ha",tau==.001 ? .0005 : .001),
                ("ensemble","root_electron_atol",1e-8),("solver","initial_target_states",32),
                ("solver","auxiliary_states",0),("solver","maxiter",301),
                ("solver","allow_band_expansion",true),("solver","stream_k",false),
                ("scf","alpha",.2),("scf","max_maps",401))
            changed=deepcopy(case);changed["settings"][group][key]=value
            @test_throws ErrorException SOC.validate_soc_settings(changed["settings"];case_contract=changed)
        end
        for (key,value) in (("case","si-soc-splitting-v1"),("sensitivity_profile","unregistered"),
                ("source_reference","different-source.json"))
            changed=deepcopy(case);changed[key]=value
            @test_throws ErrorException SOC.validate_soc_settings(changed["settings"];case_contract=changed)
        end
        changed=deepcopy(case);changed["pseudo"]["nlcc"]=1
        @test_throws ErrorException SOC.validate_soc_settings(changed["settings"];case_contract=changed)
        fake=SyntheticSensitivityTemperatureContext((;model=(;temperature=2tau,smearing=DFTK.Smearing.FermiDirac())))
        err=try SOC.soc_scf(fake,Float64[],settings;seed=81001,case_contract=case);nothing catch e;e end
        @test err isa ErrorException && occursin("Actual model and ensemble settings disagree",sprint(showerror,err))
        parent=sensitivity_parent(case);sources=parent["executed_source_sha256"]
        @test si_validate_parent_receipt(parent,case,sources,"b"^40)===parent
        for (key,value) in (("case","si-soc-splitting-v1"),("sensitivity_profile","unregistered"),
                ("case_sha256","f"^64),("temperature_ha",2tau),("execution_status","FAIL"),("exit_code",1))
            changed=deepcopy(parent);changed[key]=value
            @test_throws ErrorException si_validate_parent_receipt(changed,case,sources,"b"^40)
        end
        changed=deepcopy(parent);changed["grid"]["basis"]["kpoints"][1]["weight_spatial"]=1.
        @test_throws ErrorException si_validate_parent_receipt(changed,case,sources,"b"^40)
        @test si_arity_valid("prepare",2;profile) && si_arity_valid("D-SCF",2;profile) && si_arity_valid("D-GAMMA",3;profile)
        @test !si_arity_valid("D-SPECTRUM",3;profile) && !si_arity_valid("static",2;profile)
    end
    for args in (["D-GAMMA","NEW"],["D-GAMMA","NEW","--profile","T05"],
            ["D-SCF","NEW","--profile","unknown"],["static","NEW","--profile","E40"],
            ["D-GAMMA","NEW","PARENT","--profile"],["--profile","E40","D-SCF","NEW"])
        @test si_main(args)==2
    end
    values=[-.001,0.,.001];saved=copy(values)
    warmer=si_probe_occupations(values,0.,.001);colder=si_probe_occupations(values,0.,.0005)
    @test warmer[2]==colder[2]==.5
    @test colder[1]>warmer[1] && colder[3]<warmer[3]
    @test values==saved && sum(colder)!=8
    @test si_probe_occupations(values.+1.,1.,.0005)≈colder
    thermal1=SOC.ensemble_free_energy(2.,[[.25,.75]],[1.],.001)
    thermal2=SOC.ensemble_free_energy(2.,[[.25,.75]],[1.],.0005)
    @test thermal1.internal_energy_ha==thermal2.internal_energy_ha==2.
    @test thermal2.entropy_energy_ha==thermal1.entropy_energy_ha/2
    @test thermal2.entropy_dimensionless==thermal1.entropy_dimensionless
end
