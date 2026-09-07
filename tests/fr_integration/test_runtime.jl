# Synthetic eigensolver records and publication faults; never numerical evidence.
function run_integration_runtime_tests(ctx,settings,evidence)
    @testset "Explicit solver and residual failures cannot pass" begin
        good=(;converged=true,eigenvalues_ha=[-1.0,0.0],explicit_residuals_ha=[1e-12,2e-12],orthogonality_frobenius=1e-12)
        @test FI.assert_eigensolve_record(good,settings)
        @test_throws ErrorException FI.assert_eigensolve_record(merge(good,(;converged=false)),settings)
        @test_throws ErrorException FI.assert_eigensolve_record(merge(good,(;explicit_residuals_ha=[2e-9,1e-12])),settings)
        @test_throws ErrorException FI.assert_eigensolve_record(merge(good,(;orthogonality_frobenius=2e-9)),settings)
        @test_throws ErrorException FI.assert_eigensolve_record(merge(good,(;eigenvalues_ha=[NaN,0.0])),settings)
        @test_throws ArgumentError FI.time_reverse_spinor(ones(ComplexF64,4),[1,1])
        @test_throws DimensionMismatch FI.time_reverse_spinor(ones(ComplexF64,5),[2,1])
        b=ctx.basis
        # Regression: the old uncanonicalized Dict key lost Gamma q=0 because
        # isequal(-0.0,0.0) is false, although the physical coordinates coincide.
        @test !haskey(Dict((0.0,0.0,0.0)=>1),(-0.0,-0.0,-0.0))
        gm=FI.time_reversal_map(b,b.kpoints[1],b.kpoints[1])
        gx=randn(MersenneTwister(62100),ComplexF64,2length(gm),2)
        @test norm(FI.time_reverse_spinor(FI.time_reverse_spinor(gx,gm),gm)+gx)<=1e-12
        m=FI.time_reversal_map(b,b.kpoints[2],b.kpoints[3])
        reverse=FI.time_reversal_map(b,b.kpoints[3],b.kpoints[2])
        x=randn(MersenneTwister(62101),ComplexF64,2length(m),2)
        @test norm(FI.time_reverse_spinor(FI.time_reverse_spinor(x,m),reverse)+x)<=1e-12
    end
    @testset "Fresh run publication rejects stale success" begin
        success=(r,d)->foreach(k->r[k]="PASS",PHASE6B_STAGES)
        old=joinpath(evidence,"synthetic-old-pass")
        @test with_phase6b_record(success,old)==0
        oldbytes=read(joinpath(old,"result.json"))
        failure=(r,d)->error("Synthetic worker failure")
        @test with_phase6b_record(failure,old)==2
        @test read(joinpath(old,"result.json"))==oldbytes
        fresh=joinpath(evidence,"synthetic-fresh-failure")
        @test with_phase6b_record(failure,fresh)!=0
        @test JSON3.read(read(joinpath(fresh,"result.json"),String))["execution_status"]=="FAIL"
        missing=joinpath(evidence,"synthetic-missing-stage")
        @test with_phase6b_record((r,d)->nothing,missing)!=0
        @test JSON3.read(read(joinpath(missing,"result.json"),String))["execution_status"]!="PASS"
        bad=joinpath(evidence,"synthetic-encoding-failure")
        @test with_phase6b_record(bad) do r,d
            success(r,d);r["invalid_numeric"]=NaN
        end != 0
        @test JSON3.read(read(joinpath(bad,"result.json"),String))["execution_status"]=="FAIL"
        @test phase6b_main(["--help"])==0
        @test phase6b_main(String[])==2
    end
    reference=FI.fixed_reference_density(ctx.basis,settings)
    full=FI.build_full_hamiltonian(ctx,reference.n)
    symmetry=FI.full_hamiltonian_checks(ctx,full.full,settings)
    @testset "All actual full-H blocks and Gamma signed-zero regression" begin
        @test symmetry.status=="PASS"
        @test all(r.normalized_error<=settings["thresholds"]["time_reversal_normalized"] for r in symmetry.time_reversal)
    end
    (;scope="Synthetic eigensolver/publication faults and actual full-H/G-set checks",status="PASS",full_hamiltonian=symmetry)
end
