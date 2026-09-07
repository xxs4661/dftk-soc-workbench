# Synthetic four-cell callback maps exercise the existing density controller.
# They are protocol/budget fixtures, not SOC orbitals or physical SCF results.
function run_soc_controller_tests()
    controller=SpinorSCFPrototype.iterate_density_map
    summarize=SpinorSCFPrototype.density_summary
    digest=SpinorSCFPrototype._scf_hash
    dvol=.25; n10=fill(10.0,4); n8=fill(8.0,4)
    function mapped(input,output,index;consumed=input,orbital=output,closure_ok=true)
        (;n_out=copy(output),closure_ok,raw=(;synthetic_map=index,returned_density=copy(output)),
          diagnostics=(;consumed_input_sha256=digest(consumed),orbital_density_sha256=digest(orbital)))
    end
    function failed(action)
        err=try action();nothing catch caught;caught end
        @test err isa SpinorSCFPrototype.DensityMapFailure
        err isa SpinorSCFPrototype.DensityMapFailure || error("Expected controller failure fixture")
        @test !isempty(err.history) && last(err.history)["status"]=="FAIL"
        @test all(r["status"]!="PASS" for r in err.history)
        err
    end
    evidence=Dict{String,Any}("scope"=>"Synthetic density-map controller tests only; no physical SCF")
    @testset "Explicit ten-electron controller and historical default eight" begin
        @test summarize(n10,dvol;n_electrons=10).electron_count==10
        @test summarize(n8,dvol).electron_count==8
        roles=Bool[];records=Any[];raws=Any[]
        identity=function(n,i,closing)
            push!(roles,closing);mapped(n,n,i)
        end
        original=reshape(copy(n10),2,2);saved=copy(original)
        ten=controller(identity,original;dvol,n_electrons=10,max_maps=2,
            callback=(r,raw)->(push!(records,r);push!(raws,raw)))
        @test ten.status=="PASS" && ten.converged && ten.map_count==2
        @test roles==[false,true]
        @test original==saved
        @test ten.n_out==vec(saved) && ten.raw.returned_density==ten.n_out
        @test ten.raw.synthetic_map==2 && raws[end]===ten.raw
        @test records==ten.history && length(records)==2
        @test [r["map_role"] for r in records]==["iteration","closure"]
        @test all(r["n_in"].electron_count==r["n_out"].electron_count==10 for r in records)
        @test records[1]["n_next"].sha256==records[2]["n_in"].sha256
        @test records[2]["n_out"].sha256==digest(ten.n_out)
        eight=controller((n,i,c)->mapped(n,n,i),n8;dvol,max_maps=2)
        explicit_eight=controller((n,i,c)->mapped(n,n,i),n8;dvol,n_electrons=8,max_maps=2)
        @test eight.n_out==explicit_eight.n_out && eight.map_count==explicit_eight.map_count==2
        @test eight.history==explicit_eight.history
        calls=Ref(0)
        wrong_default=failed(()->controller((n,i,c)->(calls[]+=1;mapped(n,n,i)),n10;dvol,max_maps=2))
        @test calls[]==0
        @test occursin("electron count drift",wrong_default.reason)
        @test length(wrong_default.history)==1
        evidence["explicit_ten_map_count"]=ten.map_count
        evidence["default_eight_map_count"]=eight.map_count
    end

    @testset "Unmixed residual and a mandatory additional closure map" begin
        out=n10+[2.,-2.,0.,0.]
        small=failed(()->controller((n,i,c)->mapped(n,out,i),n10;dvol,n_electrons=10,
            alpha=1e-10,max_maps=1,density_tol=1e-8))
        record=only(small.history)
        @test record["unmixed_residual_l2"]>1
        @test record["mixed_step_l2"]<1e-8
        @test !record["density_candidate"]
        @test record["next_density_source"]=="linear_mixing"
        @test n10==fill(10.,4)
        roles=Bool[]
        one=failed(()->controller((n,i,c)->(push!(roles,c);mapped(n,n,i)),n10;
            dvol,n_electrons=10,max_maps=1))
        @test roles==[false]
        @test only(one.history)["density_candidate"]
        @test occursin("Maximum density-map",one.reason)
        evidence["small_alpha"]=record
    end

    # The first candidate differs slightly from its input. Its failed closure
    # produces a large valid output. That output must enter the subsequent mix.
    function closure_fixture()
        inputs=Vector{Float64}[];roles=Bool[]
        mapper=function(n,i,closing)
            push!(inputs,copy(n));push!(roles,closing)
            output=i==1 ? n+[2e-9,-2e-9,0.,0.] : i==2 ? n+[1.,-1.,0.,0.] : copy(n)
            mapped(n,output,i;closure_ok=i!=2)
        end
        (;mapper,inputs,roles)
    end
    @testset "Failed closure is retained and consumes the shared map budget" begin
        for budget in (2,3)
            fixture=closure_fixture();callbacks=Any[]
            failure=failed(()->controller(fixture.mapper,n10;dvol,n_electrons=10,alpha=.1,
                max_maps=budget,density_tol=1e-8,callback=(r,raw)->push!(callbacks,(;record=r,raw))))
            @test length(failure.history)==length(fixture.inputs)==length(callbacks)==budget
            @test fixture.roles[1:2]==[false,true]
            @test failure.history[2]["map_role"]=="closure"
            @test !failure.history[2]["closure_checks_passed"]
            @test failure.history[2]["n_out"].sha256!=failure.history[1]["n_out"].sha256
            @test callbacks[2].raw.synthetic_map==2
            @test failure.history[2]["next_density_source"]=="linear_mixing"
            if budget==3
                @test fixture.roles==[false,true,false]
                @test norm(fixture.inputs[3]-(fixture.inputs[2]+[.1,-.1,0.,0.]))<1e-14
                @test failure.history[2]["n_next"].sha256==failure.history[3]["n_in"].sha256
                @test failure.history[3]["density_candidate"] # Cannot skip the fourth map.
            end
        end
        fixture=closure_fixture()
        closed=controller(fixture.mapper,n10;dvol,n_electrons=10,alpha=.1,max_maps=4,density_tol=1e-8)
        @test closed.status=="PASS" && closed.map_count==4
        @test fixture.roles==[false,true,false,true]
        @test [r["status"] for r in closed.history]==["CANDIDATE","CONTINUE","CANDIDATE","PASS"]
        @test closed.raw.synthetic_map==4
        @test closed.n_out==fixture.inputs[4] && closed.raw.returned_density==closed.n_out
        @test closed.n_out!=n10 && closed.n_out!=fixture.inputs[2]
        @test closed.history[2]["n_next"].sha256==closed.history[3]["n_in"].sha256
        @test closed.history[3]["n_out"].sha256==closed.history[4]["n_in"].sha256
        evidence["failed_closure_then_actual_acceptance"]=closed.history
    end

    @testset "Stale input, swapped density hashes and invalid counts cannot pass" begin
        stale=failed(()->controller((n,i,c)->mapped(n,n10+[1.,-1.,0.,0.],i;consumed=n10),n10;
            dvol,n_electrons=10,alpha=.1,max_maps=4))
        @test length(stale.history)==2
        @test occursin("Hamiltonian consumed stale",stale.reason)
        @test stale.history[1]["n_next"].sha256!=digest(n10)
        swapped=failed(()->controller((n,i,c)->mapped(n,n+[1.,-1.,0.,0.],i;
            consumed=n+[1.,-1.,0.,0.],orbital=n),n10;dvol,n_electrons=10))
        @test occursin("mismatched input density",swapped.reason)
        wrong_output=failed(()->controller((n,i,c)->mapped(n,n+[1.,-1.,0.,0.],i;orbital=n),n10;
            dvol,n_electrons=10))
        @test occursin("Output density differs",wrong_output.reason)
        for bad in ([NaN,10.,10.,10.],[-1.,11.,15.,15.],[10.,10.,10.,10.01],[10.,10.,20.])
            saved=copy(n10);callbacks=Any[]
            fault=failed(()->controller((n,i,c)->mapped(n,bad,i),n10;dvol,n_electrons=10,
                callback=(r,raw)->push!(callbacks,(;r,raw))))
            @test n10==saved
            @test length(fault.history)==length(callbacks)==1
            @test callbacks[1].r["status"]=="FAIL"
        end
        for badne in (8,0,-1,NaN,Inf)
            calls=Ref(0)
            fault=failed(()->controller((n,i,c)->(calls[]+=1;mapped(n,n,i)),n10;dvol,n_electrons=badne))
            @test calls[]==0 && length(fault.history)==1
        end
        badflag=failed(()->controller((n,i,c)->mapped(n,n,i;closure_ok=1),n10;dvol,n_electrons=10))
        @test occursin("Boolean",badflag.reason)
        solve_failure=failed(()->controller((n,i,c)->error("Synthetic eigensolver failed"),n10;dvol,n_electrons=10))
        @test occursin("Synthetic eigensolver failed",solve_failure.reason)
        @test_throws ArgumentError summarize(n10,dvol;n_electrons=NaN)
        @test_throws ArgumentError summarize(n10,dvol;n_electrons=8)
        @test_throws ArgumentError controller((n,i,c)->mapped(n,n,i),n10;dvol,n_electrons=10,alpha=0)
        @test_throws ArgumentError controller((n,i,c)->mapped(n,n,i),n10;dvol,n_electrons=10,max_maps=0)
        evidence["ownership_failure_reasons"]=[stale.reason,swapped.reason,wrong_output.reason]
    end
    evidence
end
