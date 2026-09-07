# Synthetic workers test publication only; no Julia/UPF validation is inferred.
function run_soc_recording_tests(outdir)
    @testset "Phase 6C isolated result and failure publication" begin
        old=joinpath(outdir,"existing");mkpath(old)
        write(joinpath(old,"result.json"),"historical sentinel")
        called=Ref(false)
        @test phase6c_record((r,p)->(called[]=true),"A",old)==2
        @test !called[]
        @test read(joinpath(old,"result.json"),String)=="historical sentinel"
        failed=joinpath(outdir,"failed")
        @test phase6c_record("A",failed) do r,p
            foreach(k->r[k]="PASS",SOC_STAGES)
            error("Synthetic failure after provisional stage success")
        end == 1
        @test JSON3.read(read(joinpath(failed,"result.json"),String)).execution_status=="FAIL"
        invalid=joinpath(outdir,"invalid-json")
        @test phase6c_record("B",invalid) do r,p
            foreach(k->r[k]="PASS",SOC_STAGES);r["nonfinite"]=NaN
        end == 1
        @test JSON3.read(read(joinpath(invalid,"result.json"),String)).execution_status=="FAIL"
        summaryfail=joinpath(outdir,"summary-write-fail")
        @test phase6c_record("A",summaryfail) do r,p
            foreach(k->r[k]="PASS",SOC_STAGES);mkdir(joinpath(p,"summary.txt.tmp"))
        end == 1
        @test JSON3.read(read(joinpath(summaryfail,"result.json"),String)).execution_status=="FAIL"
        @test phase6c_main(["--help"])==0
        @test phase6c_main(String[])==2
        @test phase6c_record((r,p)->nothing,"C",joinpath(outdir,"bad-label"))==2
    end
    (;scope="Synthetic publication workers; existing runs refused and failed current runs never publish PASS")
end
