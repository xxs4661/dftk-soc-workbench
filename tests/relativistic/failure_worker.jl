# Synthetic recorder callback only: no Mg/Si operator or SCF execution.
include(joinpath(@__DIR__,"..","..","scripts","run_relativistic_projectors.jl"))
length(ARGS)==2 || error("Expected synthetic fault and new output directory")
kind,outdir=ARGS
code=with_phase6a_record(outdir) do result,path
    result["scope"]="SYNTHETIC recorder callback; no physical calculation"
    if kind=="throw"
        result["real_fr_runtime_status"]="RUNNING"
        error("Synthetic operator failure")
    elseif kind=="nonfinite"
        foreach(stage->result[stage]="PASS",PHASE6A_STAGES)
        result["synthetic_nonfinite"]=NaN
    elseif kind=="incomplete"
        result["metadata_status"]="PASS"
    else
        error("Unknown synthetic fault")
    end
end
exit(code)
