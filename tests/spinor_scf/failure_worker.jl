# Synthetic subprocess worker exercising the actual new driver's persistence
# boundary. It never invokes run_phase5b!, builds B0, or performs an SCF solve.
include(joinpath(@__DIR__,"..","..","scripts","run_spinor_scf_b0.jl"))
length(ARGS)==2 || error("Usage: failure_worker.jl fault output_directory")
fault,outdir = ARGS
code = with_run_record(outdir) do result,run_directory
    result["fixture"] = "Synthetic callback map; no physical SCF executed"
    identity = environment_identity(PHASE5B_ROOT,(DFTK,PseudoPotentialIO))
    result["environment"] = identity
    identity.status=="PASS" || error("Synthetic worker environment mismatch")
    callback = (record,raw)->(result["last_synthetic_map"]=record)
    function mapper(n,i,closing)
        fault=="diagonalization_failure" && error("Injected synthetic diagonalization failure")
        if fault=="unsupported_occupation"
            fixed_gapped_occupations([collect(1.0:16.0)],[1.0];representation=:none)
        end
        out = fault=="nan" ? [NaN,4.0] : fault=="electron_drift" ? [4.0,4.1] : [5.0,3.0]
        (;n_out=out,raw=nothing,closure_ok=true,diagnostics=(;
            consumed_input_sha256=SpinorSCFPrototype._scf_hash(n),
            orbital_density_sha256=SpinorSCFPrototype._scf_hash(out)))
    end
    fault in ("map_budget","diagonalization_failure","nan","unsupported_occupation","electron_drift") ||
        error("Unknown synthetic fault")
    iterate_density_map(mapper,[4.0,4.0];dvol=1.0,max_maps=1,density_tol=1e-12,callback)
    # Reaching here must produce an unexpected success so the parent test fails;
    # do not manufacture an exception that could conceal a controller regression.
    result["synthetic_test_status"] = "UNEXPECTED_SUCCESS"
end
exit(code)
