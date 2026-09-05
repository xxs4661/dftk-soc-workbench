# Deliberately artificial two-cell density maps test controller semantics only.
# No synthetic map is evidence that the physical spinor SCF has converged.
function scf_test_map(n_in,n_out; consumed=n_in,orbital=n_out,raw=nothing,closure_ok=true)
    digest(n) = SpinorSCFPrototype._scf_hash(n)
    (; n_out,raw,closure_ok,diagnostics=(;
        consumed_input_sha256=digest(consumed),orbital_density_sha256=digest(orbital)))
end

function scf_test_failure(action)
    err = try
        action()
        nothing
    catch caught
        caught
    end
    @test err isa SpinorSCFPrototype.DensityMapFailure
    err isa SpinorSCFPrototype.DensityMapFailure || error("Expected an injected map failure")
    @test !isempty(err.history)
    @test last(err.history)["status"] == "FAIL"
    @test all(record["status"] != "PASS" for record in err.history)
    err
end

function run_scf_tests(basis,settings,energy_fixture,root,evidence_directory)
    n0 = [4.0,4.0]
    evidence = Dict{String,Any}()
    @testset "Unmixed residual, closure and total map budget (synthetic)" begin
        mapper = (n,i,c)->scf_test_map(n,[5.0,3.0])
        small = scf_test_failure(() -> iterate_density_map(mapper,n0;dvol=1.0,
            alpha=1e-8,max_maps=1,density_tol=1e-6))
        record = only(small.history)
        @test record["unmixed_residual_l2"] > 1
        @test record["mixed_step_l2"] < 1e-6
        @test !record["density_candidate"]
        @test occursin("Maximum density-map",small.reason)
        evidence["small_alpha"] = record

        roles = Bool[]
        identity_map = function(n,i,closing)
            push!(roles,closing)
            scf_test_map(n,copy(n);raw=(;origin="synthetic orbitals at map $i",map=i,n=copy(n)))
        end
        budget = scf_test_failure(() -> iterate_density_map(identity_map,n0;
            dvol=1.0,max_maps=1,density_tol=1e-12))
        @test only(budget.history)["density_candidate"]
        @test only(budget.history)["map_role"] == "iteration"
        empty!(roles)
        closed = iterate_density_map(identity_map,n0;dvol=1.0,max_maps=2,density_tol=1e-12)
        @test closed.converged && closed.status == "PASS"
        @test closed.map_count == 2
        @test roles == [false,true]
        @test closed.raw.map == 2
        @test closed.raw.origin == "synthetic orbitals at map 2"
        @test closed.n_out == closed.raw.n
        @test last(closed.history)["map_role"] == "closure"
        @test last(closed.history)["n_out"].sha256 == SpinorSCFPrototype._scf_hash(closed.raw.n)
        # The controller's final object is the current map result. There is no
        # scalar-reference argument; this sentinel cannot supply output values.
        scalar_reference_sentinel = (;energy=-999.0,n=[999.0,-991.0])
        @test closed.raw.n != scalar_reference_sentinel.n
        @test !hasproperty(closed.raw,:energy)

        inputs = Vector{Float64}[]
        closure_failure = function(n,i,closing)
            push!(inputs,copy(n))
            out = i==1 ? copy(n) : [5.0,3.0]
            scf_test_map(n,out;closure_ok=i!=2)
        end
        failed = scf_test_failure(() -> iterate_density_map(closure_failure,n0;
            dvol=1.0,alpha=0.3,max_maps=3,density_tol=1e-12))
        @test failed.history[2]["map_role"] == "closure"
        @test !failed.history[2]["closure_checks_passed"]
        @test failed.history[2]["next_density_source"] == "linear_mixing"
        @test inputs[3] ≈ [4.3,3.7] atol=1e-14 rtol=0
        @test failed.history[2]["n_next"].sha256 == failed.history[3]["n_in"].sha256
        @test length(failed.history) == 3
        evidence["failed_closure"] = failed.history
    end

    @testset "Stale Hamiltonian and wrong density ownership (synthetic)" begin
        frozen_source = Ref{Union{Nothing,Vector{Float64}}}(nothing)
        frozen_map = function(n,i,c)
            isnothing(frozen_source[]) && (frozen_source[]=copy(n))
            scf_test_map(n,[5.0,3.0];consumed=frozen_source[])
        end
        frozen = scf_test_failure(() -> iterate_density_map(frozen_map,n0;
            dvol=1.0,max_maps=4,density_tol=1e-12))
        @test length(frozen.history) == 2
        @test occursin("Hamiltonian consumed stale",frozen.reason)
        @test frozen.history[1]["n_next"].sha256 != frozen.history[1]["n_in"].sha256
        stale_output = (n,i,c)->scf_test_map(n,copy(n);orbital=[5.0,3.0])
        stale = scf_test_failure(() -> iterate_density_map(stale_output,n0;dvol=1.0))
        @test occursin("Output density differs",stale.reason)
        swapped = (n,i,c)->scf_test_map(n,[5.0,3.0];consumed=[5.0,3.0],orbital=n)
        swapped_error = scf_test_failure(() -> iterate_density_map(swapped,n0;dvol=1.0))
        @test occursin("mismatched input density",swapped_error.reason)
        @test_throws ArgumentError SpinorSCFPrototype.density_summary([-0.01,8.01],1.0)
        @test_throws ArgumentError SpinorSCFPrototype.density_summary([4.0,NaN],1.0)
        @test_throws ArgumentError SpinorSCFPrototype.density_summary([4.0,4.1],1.0)
        for bad_out in ([NaN,4.0],[-0.01,8.01],[4.0,4.1])
            saved_n0 = copy(n0)
            scf_test_failure(() -> iterate_density_map((n,i,c)->scf_test_map(n,bad_out),n0;dvol=1.0))
            @test n0 == saved_n0
        end
        evidence["ownership_failure_reasons"] = [frozen.reason,stale.reason,swapped_error.reason]
    end

    @testset "Real-path gates with injected failure before a completed map" begin
        changed = energy_test_rotate(energy_fixture.X,1,1,9,0.13)
        changed_n = density_from_orbitals(basis,changed,energy_fixture.f).n
        frozen = scf_test_failure(() -> spinor_scf(basis,changed_n,settings;seed=56901,
            hooks=(;ham=(fresh,n,i)->energy_fixture.snapshot.ham)))
        @test occursin("Hamiltonian hook froze",frozen.reason)
        @test length(frozen.history) == 1
        failed_solver = (A,initial,P,ik,i)->(;converged=false,n_iter=0)
        failed = scf_test_failure(() -> spinor_scf(basis,energy_fixture.snapshot.density.n,
            settings;seed=56902,hooks=(;solve=failed_solver)))
        @test occursin("diagonalization failed",failed.reason)
        bad_solver = (A,initial,P,ik,i)->(;converged=true,n_iter=1,
            X=fill(ComplexF64(NaN,0),size(initial)),λ=zeros(size(initial,2)))
        nonfinite = scf_test_failure(() -> spinor_scf(basis,energy_fixture.snapshot.density.n,
            settings;seed=56903,hooks=(;solve=bad_solver)))
        @test occursin("Nonfinite eigensolver",nonfinite.reason)
        evidence["real_path_injected_failures"] = [frozen.reason,failed.reason,nonfinite.reason]
    end

    @testset "Synthetic worker failures use actual driver publishing boundary" begin
        fault_root = mktempdir(evidence_directory;prefix="synthetic-cli-",cleanup=false)
        old_dir = joinpath(fault_root,"historical-pass-fixture")
        mkpath(old_dir)
        old_path = joinpath(old_dir,"result.json")
        write(old_path,JSON3.write((;run_id="historical-synthetic-fixture",execution_status="PASS",
            fixture="Synthetic old result only; not physical SCF evidence")))
        old_bytes = read(old_path)
        worker = joinpath(@__DIR__,"failure_worker.jl")
        project = joinpath(root,"environment","workbench")
        records = Any[]
        for fault in ("map_budget","diagonalization_failure","nan","unsupported_occupation","electron_drift")
            run_id = basename(fault_root)*"-"*fault
            outdir = joinpath(fault_root,run_id)
            logpath = joinpath(fault_root,fault*".log")
            command = `$(Base.julia_cmd()) --startup-file=no --color=no --project=$project $worker $fault $outdir`
            process = open(logpath,"w") do io
                run(pipeline(ignorestatus(command),stdout=io,stderr=io))
            end
            @test process.exitcode != 0
            result = JSON3.read(read(joinpath(outdir,"result.json"),String),Dict{String,Any})
            @test result["execution_status"] == "FAIL"
            @test result["exit_code"] == process.exitcode
            @test result["run_id"] == run_id
            @test result["fixture"] == "Synthetic callback map; no physical SCF executed"
            @test !isempty(result["failure_reason"])
            @test read(old_path) == old_bytes
            push!(records,(;fault,exit_code=process.exitcode,run_id,
                result=relpath(joinpath(outdir,"result.json"),evidence_directory),
                log=relpath(logpath,evidence_directory)))
        end
        @test length(unique(r.run_id for r in records)) == 5
        # Existing PASS directories are refused before any overwrite/readback.
        reuse_log = joinpath(fault_root,"refused-existing.log")
        command = `$(Base.julia_cmd()) --startup-file=no --color=no --project=$project $worker map_budget $old_dir`
        process = open(reuse_log,"w") do io
            run(pipeline(ignorestatus(command),stdout=io,stderr=io))
        end
        @test process.exitcode == 2
        @test read(old_path) == old_bytes
        @test occursin("Refusing existing run directory",read(reuse_log,String))
        evidence["cli_faults"] = records
        evidence["existing_directory_exit_code"] = process.exitcode
    end
    evidence
end
