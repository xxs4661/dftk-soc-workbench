# Synthetic saved-array comparison tests; no physical context or calculation.
using Test,LinearAlgebra
root=normpath(joinpath(@__DIR__,".."))
require_value(ok,reason)=ok || error(reason)
# Evaluate only the named production arithmetic definitions. Loading the full
# historical comparison module would import DFTK; this test needs only stdlibs.
function load_function(path,name)
    parsed=Meta.parseall(read(path,String))
    function checked(x)
        x isa Expr || return
        x.head in (:error,:incomplete) && error("Parse error in $path: $x")
        foreach(checked,x.args)
    end
    checked(parsed)
    candidates=filter(parsed.args) do value
        value isa Expr && value.head==:function && value.args[1] isa Expr && value.args[1].head==:call && first(value.args[1].args)==name
    end
    Core.eval(Main,only(candidates))
end
load_function(joinpath(root,"benchmarks/soc-core-memory-v1/compare.jl"),:array_comparison)
load_function(joinpath(root,"benchmarks/soc-extra-v1/b0_regression.jl"),:extra_b0_metrics)
@testset "Synthetic B0 thresholds, not SCF" begin
    d=Dict{String,Any}("internal_energy_ha"=>-1.,"free_energy_ha"=>-1.01,"entropy_energy_ha"=>-.01,
        "energy_terms_ha"=>Dict("synthetic-$i"=>-1/7 for i in 1:7))
    old=Dict("final"=>Dict("diagnostics"=>d,"n_out_sha256"=>"reference"),"checkpoint_sha256"=>"synthetic-checkpoint")
    new=deepcopy(old);new["final"]["n_out_sha256"]="candidate"
    g=Dict("values_ha"=>collect(1.:24.).*.01,"delta_so_ev"=>.047)
    p=Dict("comparison"=>Dict("B0_density_norm_ratio"=>1e-8,"B0_E_F_abs_ha"=>1e-8,
        "B0_split_abs_ev"=>1e-6,"B0_gamma24_raw_max_ha"=>1e-7))
    f=(o,n,a,b,x,y)->extra_b0_metrics(o,n,a,b,x,y,p)
    m=f(old,new,[.5,.5],[.5,.5],g,g)
    @test m.status=="PASS" && m.n_out.reference_n_out_sha256=="reference" && m.n_out.candidate_n_out_sha256=="candidate"
    @test length(m.energy_terms)==7 && length(m.gamma.raw_differences_ha)==24
    @test f(old,new,[.5,.5],[.50001,.49999],g,g).status=="FAIL"
    for field in ("internal_energy_ha","free_energy_ha")
        bad=deepcopy(new);bad["final"]["diagnostics"][field]+=2e-8
        @test f(old,bad,[.5,.5],[.5,.5],g,g).status=="FAIL"
    end
    shifted=deepcopy(g);shifted["values_ha"][24]+=2e-7
    @test f(old,new,[.5,.5],[.5,.5],g,shifted).status=="FAIL"
    split=deepcopy(g);split["delta_so_ev"]+=2e-6
    @test f(old,new,[.5,.5],[.5,.5],g,split).status=="FAIL"
    bad=deepcopy(new);bad["final"]["diagnostics"]["energy_terms_ha"]["synthetic-1"]=NaN
    @test_throws ErrorException f(old,bad,[.5,.5],[.5,.5],g,g)
    short=deepcopy(g);pop!(short["values_ha"])
    @test_throws ErrorException f(old,new,[.5,.5],[.5,.5],g,short)
end
