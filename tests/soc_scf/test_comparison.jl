# These arrays and records are synthetic comparison fixtures, not SOC solutions.
isdefined(@__MODULE__, :compare_soc_results) || include("../../scripts/compare_soc_scf.jl")

function synthetic_soc_comparison_fixture(label;target=24)
    settings=TOML.parsefile(PHASE6C_CONFIG);mg=settings["mg"];nr=8
    input=Dict{String,Any}("sha256"=>repeat("d",64),"element"=>"Mg","functional"=>"PBESOL",
        "relativistic"=>"full","has_so"=>true,"nlcc_present"=>false,"z_valence"=>10,
        "xc_identifiers"=>mg["xc_identifiers"])
    basis=Dict{String,Any}("ecut_ha"=>15.,"fft_grid"=>[2,2,2],"volume_bohr3"=>1000.,"n_electrons"=>10,
        "lattice_bohr"=>[[10.,0.,0.],[0.,10.,0.],[0.,0.,10.]],"positions_fractional"=>mg["positions_fractional"],
        "native_nonlocal_terms"=>0,"term_types"=>["synthetic common terms"],
        "kpoints"=>[Dict{String,Any}("coordinate_fractional"=>copy(q),"weight_spatial"=>w,
            "ng"=>32,"g_order_sha256"=>repeat(string(i),64)) for (i,(q,w)) in enumerate(zip(mg["kpoints"],mg["kweights"]))])
    # Different prescribed spectra per k make an accidental row match detectable.
    eigenvalues=[collect(range(-2.0 + 0.01ik;step=0.2,length=target)) for ik in 1:3]
    f=[vcat(ones(10),zeros(target-10)) for _ in 1:3]
    n=fill(.01,nr);R=zeros(ComplexF64,2,2,nr);R[1,1,:].=n/2;R[2,2,:].=n/2
    final=Dict{String,Any}("target_states"=>target,"n_in_sha256"=>FI.integration_density_hash(n),
        "n_out_sha256"=>FI.integration_density_hash(n),"eigenvalues_ha"=>eigenvalues,"occupations"=>f,"mu_ha"=>0.,
        "diagnostics"=>Dict("internal_energy_ha"=>-50.,"free_energy_ha"=>-50.,
            "entropy_energy_ha"=>0.,"entropy_dimensionless"=>0.))
    environment=Dict("status"=>"PASS","fixture_scope"=>"SYNTHETIC: no environment attestation")
    run=Dict{String,Any}("schema_version"=>1,"phase"=>"6C","label"=>label,"run_id"=>"synthetic-"*label,
        "execution_status"=>"PASS","exit_code"=>0,"config_sha256"=>"synthetic-config", "settings"=>settings,
        "checkpoint_sha256"=>"synthetic-checkpoint-"*label,"environment"=>environment,"final_environment"=>copy(environment),
        "temperature_ha"=>.001,"smearing"=>"FermiDirac","input"=>input,"basis"=>basis,"final"=>final,
        "executed_source_sha256"=>Dict("fixture"=>"not actual source"))
    foreach(key->run[key]="PASS",SOC_STAGES)
    state=(;X=[zeros(ComplexF64,64,target) for _ in 1:3],f=deepcopy(f),eigenvalues=deepcopy(eigenvalues),
        n_in=copy(n),n_out=copy(n),R,m=zeros(3,nr),final=deepcopy(final))
    (;run,state,settings)
end

function synthetic_soc_sync!(run,state)
    final=run["final"]
    final["n_in_sha256"]=FI.integration_density_hash(state.n_in)
    final["n_out_sha256"]=FI.integration_density_hash(state.n_out)
    final["eigenvalues_ha"]=deepcopy(state.eigenvalues);final["occupations"]=deepcopy(state.f)
    merge(state,(;final=deepcopy(final)))
end

function synthetic_soc_compare(a,b,sa,sb,settings)
    compare_soc_results(a,b,sa,sb,settings;config_sha256="synthetic-config",
        run_hashes=Dict("A"=>repeat("a",64),"B"=>repeat("b",64)),
        checkpoint_hashes=Dict("A"=>"synthetic-checkpoint-A","B"=>"synthetic-checkpoint-B"))
end

function run_soc_comparison_tests()
    @testset "Synthetic A/B endpoint comparison" begin
        fa=synthetic_soc_comparison_fixture("A");fb=synthetic_soc_comparison_fixture("B")
        a,b,sa,sb,settings=fa.run,fb.run,fa.state,fb.state,fa.settings
        result=synthetic_soc_compare(a,b,sa,sb,settings)
        @test result["two_initial_states_comparison_status"]=="PASS"
        @test result["common_target_states"]==24
        @test result["density_relative_l2"]==0
        @test result["max_raw_eigenvalue_difference_ha"]==0
        @test result["numerical_review_status"]=="REVIEW_REQUIRED"
        @test result["qe_soc_benchmark_status"]=="NOT_RUN"
        @test result["runs"]["A"]["result_sha256"]==repeat("a",64)
        # Match the driver's actual final.bin representation: arrays plus nested
        # NamedTuple final/diagnostics, serialized without any context or token.
        named_diag=(; (Symbol(k)=>v for (k,v) in b["final"]["diagnostics"])...)
        named_final=(; (Symbol(k)=>(k=="diagnostics" ? named_diag : v) for (k,v) in b["final"])...)
        io=IOBuffer();serialize(io,merge(sb,(;final=named_final)));seekstart(io)
        restored=deserialize(io)
        @test synthetic_soc_compare(a,b,sa,restored,settings)["two_initial_states_comparison_status"]=="PASS"

        # Permute entire k blocks, then add a reciprocal lattice integer.
        p=[3,1,2];bp=deepcopy(b)
        bp["basis"]["kpoints"]=bp["basis"]["kpoints"][p]
        bp["basis"]["kpoints"][1]["coordinate_fractional"] .+= [1.,-2.,3.]
        sp=merge(sb,(;X=sb.X[p],f=sb.f[p],eigenvalues=sb.eigenvalues[p]))
        sp=synthetic_soc_sync!(bp,sp)
        permuted=synthetic_soc_compare(a,bp,sa,sp,settings)
        @test permuted["two_initial_states_comparison_status"]=="PASS"
        @test permuted["kpoint_mapping_b_for_a"]==[2,3,1]

        for fault in ("duplicate","missing","weight","G-order")
            bad=deepcopy(b)
            if fault=="duplicate"
                bad["basis"]["kpoints"][2]["coordinate_fractional"]=copy(bad["basis"]["kpoints"][1]["coordinate_fractional"])
            elseif fault=="missing"
                bad["basis"]["kpoints"][2]["coordinate_fractional"]=[.2,.3,.4]
            elseif fault=="weight"
                bad["basis"]["kpoints"][2]["weight_spatial"]=.5
            else
                bad["basis"]["kpoints"][2]["g_order_sha256"]="wrong"
            end
            @test_throws ArgumentError synthetic_soc_compare(a,bad,sa,sb,settings)
        end

        # An energy offset must fail; no fitted shift or HOMO alignment is used.
        shifted=deepcopy(sb)
        foreach(e->e .+= 1e-4,shifted.eigenvalues)
        bs=deepcopy(b);shifted=synthetic_soc_sync!(bs,shifted)
        r=synthetic_soc_compare(a,bs,sa,shifted,settings)
        @test r["two_initial_states_comparison_status"]=="DIFFERENT_SOLUTIONS"
        @test r["exit_code"]!=0
        @test r["max_raw_eigenvalue_difference_ha"]>1e-6
        # Band 17 is outside the explicitly requested lowest-16 spectral gate.
        high=deepcopy(sb);high.eigenvalues[1][17]+=1e-4
        bh=deepcopy(b);high=synthetic_soc_sync!(bh,high)
        @test synthetic_soc_compare(a,bh,sa,high,settings)["two_initial_states_comparison_status"]=="PASS"

        for amount in (1e-8,1e-5)
            sn=deepcopy(sb);sn.n_out[1]+=amount;sn.n_out[2]-=amount
            bn=deepcopy(b);sn=synthetic_soc_sync!(bn,sn)
            r=synthetic_soc_compare(a,bn,sa,sn,settings)
            @test r["two_initial_states_comparison_status"]==(amount==1e-8 ? "PASS" : "DIFFERENT_SOLUTIONS")
        end
        for field in ("internal_energy_ha","free_energy_ha")
            bad=deepcopy(b);bad["final"]["diagnostics"][field]+=2e-7
            st=synthetic_soc_sync!(bad,sb)
            @test synthetic_soc_compare(a,bad,sa,st,settings)["two_initial_states_comparison_status"]=="DIFFERENT_SOLUTIONS"
        end

        # Chemical potential, occupations and entropy are reported diagnostics.
        bd=deepcopy(b);sd=deepcopy(sb)
        bd["final"]["mu_ha"]=100.
        bd["final"]["diagnostics"]["entropy_dimensionless"]=1.
        sd.f[1][10]=.8;sd.f[1][11]=.2
        sd=synthetic_soc_sync!(bd,sd)
        r=synthetic_soc_compare(a,bd,sa,sd,settings)
        @test r["two_initial_states_comparison_status"]=="PASS"
        @test r["diagnostic_only"]["mu_abs_difference_ha"]==100.
        @test r["diagnostic_only"]["shared_state_occupation_max_difference"]≈.2
        @test r["diagnostic_only"]["entropy_abs_difference_dimensionless"]==1.

        larger=synthetic_soc_comparison_fixture("B";target=32)
        r=synthetic_soc_compare(a,larger.run,sa,larger.state,settings)
        @test r["two_initial_states_comparison_status"]=="REVIEW_REQUIRED"
        @test isnothing(r["common_target_states"])
        @test r["exit_code"]!=0

        for key in ("execution_status",SOC_STAGES...)
            bad=deepcopy(b);bad[key]="FAIL"
            @test_throws ArgumentError synthetic_soc_compare(a,bad,sa,sb,settings)
        end
        for key in ("config_sha256","checkpoint_sha256","run_id")
            bad=deepcopy(b);bad[key]=key=="run_id" ? a[key] : "wrong"
            @test_throws ArgumentError synthetic_soc_compare(a,bad,sa,sb,settings)
        end
        for section in ("input","environment","executed_source_sha256")
            bad=deepcopy(b);bad[section]["different"]="synthetic mismatch"
            @test_throws ArgumentError synthetic_soc_compare(a,bad,sa,sb,settings)
        end
        for key in ("ecut_ha","n_electrons","volume_bohr3")
            bad=deepcopy(b);bad["basis"][key]+=1
            @test_throws ArgumentError synthetic_soc_compare(a,bad,sa,sb,settings)
        end
        stale=deepcopy(sb);stale.n_out[1]+=1e-8
        @test_throws ArgumentError synthetic_soc_compare(a,b,sa,stale,settings)
        nonfinite=deepcopy(sb);nonfinite.eigenvalues[1][1]=NaN
        @test_throws ArgumentError synthetic_soc_compare(a,b,sa,nonfinite,settings)
        @test_throws ArgumentError synthetic_soc_compare(a,b,sa,merge(sb,(;context="forbidden")),settings)

        @test compare_soc_main(["--help"])==0
        @test compare_soc_main(String[])==2
        mktempdir(joinpath(PHASE6C_ROOT,".work")) do dir
            old=joinpath(dir,"old.json");write(old,"historical sentinel")
            @test compare_soc_main(["missing-a","missing-b",old])==2
            @test read(old,String)=="historical sentinel"
            ap=joinpath(dir,"A");bp=joinpath(dir,"B");mkpath(ap);mkpath(bp)
            for (path,run) in ((ap,a),(bp,b))
                write(joinpath(path,"result.json"),JSON3.write(run))
                write(joinpath(path,"final.bin"),"deliberately not a Julia checkpoint")
            end
            ah,bh=filehash(joinpath(ap,"result.json")),filehash(joinpath(bp,"result.json"))
            out=joinpath(dir,"failure.json")
            @test compare_soc_main([joinpath(ap,"result.json"),joinpath(bp,"result.json"),out])==1
            r=JSON3.read(read(out,String))
            @test r.two_initial_states_comparison_status=="FAIL"
            @test occursin("checkpoint SHA-256",r.failure_reason)
            @test filehash(joinpath(ap,"result.json"))==ah && filehash(joinpath(bp,"result.json"))==bh
        end
    end
    (;scope="Synthetic endpoint arrays and records only; no physical solve, SCF or QE",
      matching="Fractional k coordinates modulo reciprocal lattice integers, independent of eigenvalues")
end
