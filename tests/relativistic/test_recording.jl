function run_recording_tests(root,evidence_directory)
    worker=joinpath(@__DIR__,"failure_worker.jl")
    olddir=joinpath(evidence_directory,"historical-synthetic-pass")
    mkpath(olddir)
    oldbytes="{\"execution_status\":\"PASS\",\"scope\":\"synthetic historical sentinel\"}\n"
    write(joinpath(olddir,"result.json"),oldbytes)
    records=NamedTuple[]
    for kind in ("throw","nonfinite","incomplete")
        outdir=joinpath(evidence_directory,"current-synthetic-"*kind)
        log=joinpath(evidence_directory,"synthetic-"*kind*".log")
        cmd=`$(Base.julia_cmd()) --startup-file=no --project=$(joinpath(root,"environment/workbench")) $worker $kind $outdir`
        process=open(log,"w") do io
            run(pipeline(ignorestatus(cmd),stdout=io,stderr=io))
        end
        @test process.exitcode==1
        current=JSON3.read(read(joinpath(outdir,"result.json"),String))
        @test current.execution_status=="FAIL"
        @test current.exit_code==1
        @test current.run_id==basename(outdir)
        @test read(joinpath(olddir,"result.json"),String)==oldbytes
        push!(records,(;kind,exit_code=process.exitcode,result=current,
            log_path=relpath(log,root),result_path=relpath(joinpath(outdir,"result.json"),root)))
    end
    cmd=`$(Base.julia_cmd()) --startup-file=no --project=$(joinpath(root,"environment/workbench")) $worker throw $olddir`
    log=joinpath(evidence_directory,"synthetic-existing-directory.log")
    process=open(log,"w") do io
        run(pipeline(ignorestatus(cmd),stdout=io,stderr=io))
    end
    @test process.exitcode==2
    @test read(joinpath(olddir,"result.json"),String)==oldbytes
    (;scope="Synthetic recorder protocol, no Julia physics/SCF evidence",records,
      existing_directory_exit_code=process.exitcode,historical_pass_unchanged=true)
end
