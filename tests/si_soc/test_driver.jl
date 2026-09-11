# Synthetic parent receipts and CLI contracts only. No source/model/numerical call.
using Test

function run_si_driver_tests()
    case=si_case()
    sources=Dict("synthetic source identity"=>"a"^64)
    head="b"^40
    input=Dict("sha256"=>case["pseudo"]["sha256"],"element"=>"Si","z_valence"=>4,
        "functional"=>"PBE","mode"=>"real_fr","has_so"=>true,"nlcc_present"=>true,
        "xc_identifiers"=>case["xc"]["dftk_identifiers"])
    basis=Dict("fft_grid"=>case["fft_size"],"n_electrons"=>8,"ecut_ha"=>30,
        "lattice_bohr"=>case["geometry"]["lattice_vectors_bohr"],
        "positions_fractional"=>case["geometry"]["positions_fractional"],"kpoints"=>deepcopy(case["kpoints"]))
    receipt=Dict{String,Any}("schema_version"=>1,"case"=>"si-soc-splitting-v1","base_commit"=>SI_BASE,
        "action"=>"D-SCF","execution_status"=>"PASS","exit_code"=>0,
        "execution_commit"=>head,"executed_source_sha256"=>sources,"input"=>input,
        "grid"=>Dict("status"=>"PASS","basis"=>basis),"final"=>Dict("diagnostics"=>Dict("target_states"=>24)))
    @testset "Synthetic action arity: invalid requests do not construct a context" begin
        @test si_main(["--help"]) == 0
        for args in (String[],["prepare"],["prepare","NEW","EXTRA_PARENT"],["D-SCF","NEW","EXTRA_PARENT"],
                     ["static","NEW","EXTRA_PARENT"],["D-SPECTRUM","NEW"],["D-NULL-GAMMA","NEW"],
                     ["unknown","NEW"],["D-SPECTRUM","NEW","PARENT","EXTRA"])
            @test si_main(args)==2
        end
        for action in ("prepare","static","D-SCF")
            @test si_arity_valid(action,2)
            @test !si_arity_valid(action,3)
        end
        for action in ("D-SPECTRUM","D-NULL-GAMMA")
            @test si_arity_valid(action,3)
            @test !si_arity_valid(action,2)
        end
    end
    @testset "Synthetic same-case same-execution parent receipt binding" begin
        @test si_validate_parent_receipt(receipt,case,sources,head)===receipt
        @test_throws ErrorException si_validate_parent_receipt(nothing,case,sources,head)
        for (key,value) in (("schema_version",true),("case","mg"),("base_commit","c"^40),
                            ("action","D-SPECTRUM"),("execution_status","FAIL"),("exit_code",false),
                            ("exit_code",1),("execution_commit","c"^40),("executed_source_sha256",Dict()),
                            ("input",nothing),("grid",nothing),("final",nothing))
            bad=deepcopy(receipt);bad[key]=value
            @test_throws ErrorException si_validate_parent_receipt(bad,case,sources,head)
        end
        for (key,value) in (("sha256","c"^64),("element","Mg"),("z_valence",10),
                            ("functional","PBESOL"),("mode","synthetic_scalar_limit"),
                            ("has_so",false),("nlcc_present",false),("xc_identifiers",["lda_x","lda_c_pw"]))
            bad=deepcopy(receipt);bad["input"][key]=value
            @test_throws ErrorException si_validate_parent_receipt(bad,case,sources,head)
        end
        for (key,value) in (("fft_grid",[40,40,40]),("n_electrons",10),("ecut_ha",40),
                            ("lattice_bohr",[[10.,0,0],[0,10.,0],[0,0,10.]]),
                            ("positions_fractional",[[0.,0,0]]),("kpoints",case["kpoints"][1:3]))
            bad=deepcopy(receipt);bad["grid"]["basis"][key]=value
            @test_throws ErrorException si_validate_parent_receipt(bad,case,sources,head)
        end
        bad=deepcopy(receipt);bad["grid"]["basis"]["kpoints"][1]["weight_spatial"]=1.
        @test_throws ErrorException si_validate_parent_receipt(bad,case,sources,head)
        bad=deepcopy(receipt);bad["final"]["diagnostics"]["target_states"]=48
        @test_throws ErrorException si_validate_parent_receipt(bad,case,sources,head)
    end
    @testset "Synthetic nonorthogonal even-grid real projection, no density change" begin
        # Analytic radial toy on an even grid, not source core data. The metric
        # gives unequal physical norms at cyclic Nyquist partners.
        modes=[0,1,-2,-1]
        recip=[-1. 1 1;1 -1 1;1 1 -1]
        raw=Array{ComplexF64}(undef,4,4,4)
        for I in CartesianIndices(raw)
            g=[modes[I[d]] for d in 1:3]
            q=recip*g
            raw[I]=(1+cis(-2π*sum(g)/4))/(1+sum(abs2,q))
        end
        saved=copy(raw)
        projected=si_real_fourier_coefficients(raw)
        independent=DFTK.FFTW.fft(real.(DFTK.FFTW.ifft(raw)))
        @test norm(projected-independent)<=1e-11
        @test norm(projected-raw)>1e-6
        @test projected[1]==raw[1]
        @test raw==saved
        for I in CartesianIndices(raw)
            J=CartesianIndex(ntuple(d->mod1(2-I[d],4),3))
            @test abs(projected[I]-conj(projected[J]))<=1e-11
        end
    end
    (;scope="Synthetic parent/CLI protocol only; no source or model evaluated")
end
