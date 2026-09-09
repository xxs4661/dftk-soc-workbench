# Synthetic saved-array arithmetic only; no kernel, SCF or eigensolve execution.
using Test, LinearAlgebra
module SyntheticSavedComparison
include("../../benchmarks/soc-core-memory-v1/compare.jl")
end
const Saved= SyntheticSavedComparison
@testset "Saved arithmetic contracts and units (synthetic)" begin
    c=Saved.readjson(joinpath(@__DIR__,"../../benchmarks/soc-core-memory-v1/contract.json"))
    a=ComplexF64[1+im,2-im];b=a.+1e-14
    row=Saved.array_comparison(a,b,"FR_24",1e-12)
    @test row.status=="PASS"
    @test row.relative==norm(a-b)/max(norm(a),norm(b),1)
    @test !row.bitwise_equal
    @test_throws ErrorException Saved.array_comparison(a,ComplexF32.(a),"FR_24",1e-12)
    @test_throws ErrorException Saved.array_comparison(a,fill(NaN+0im,2),"FR_24",1e-12)
    @test_throws ErrorException Saved.array_comparison(a,reshape(a,1,2),"FR_24",1e-12)
    @test_throws ErrorException Saved.array_comparison([floatmax(Float64)],[-floatmax(Float64)],"FR_24",1e-12)
    rows=Any[]
    Saved.compare_values!(rows,1.0,1.0+1e-11,"energy/total_ha",c)
    @test only(rows).unit=="Ha/cell" && only(rows).status=="PASS"
    @test_throws ErrorException Saved.compare_values!(Any[],true,1,"energy/total_ha",c)
    @test_throws ErrorException Saved.compare_values!(Any[],Float32(1),1.,"energy/total_ha",c)
    empty!(rows);Saved.compare_values!(rows,.2,.2,"energy/entropy_dimensionless",c)
    @test only(rows).unit=="dimensionless" && only(rows).limit==0
    d=deepcopy(c);d["accuracy"]["density_R_n_m_relative"]=1e-15
    empty!(rows);Saved.compare_values!(rows,a,b,"density/R",d)
    @test only(rows).limit==1e-15 && only(rows).status=="FAIL"
    integral=Saved.density_integrals((;n=ones(4),m=zeros(3,4)),(;n=ones(4),m=zeros(3,4)),"synthetic",2.,c)
    @test integral.status=="PASS" && integral.reference_electrons==8
    @test Saved.density_integrals((;n=ones(4),m=zeros(3,4)),(;n=ones(4),m=zeros(3,4)),"synthetic",1.,c).status=="FAIL"
end

module SyntheticMeasurementPublic
include("../../benchmarks/soc-core-memory-v1/measure.jl")
end
@testset "Same actual CORE root retains workbench identity in public text" begin
    root="/synthetic/workbench";reference="/synthetic/reference"
    @test SyntheticMeasurementPublic.mpublic(root*"/environment/workbench/Project.toml",root,root)=="<workbench>/environment/workbench/Project.toml"
    @test SyntheticMeasurementPublic.mpublic(root*"/src/SOCKernels.jl",root,root)=="<workbench>/src/SOCKernels.jl"
    @test SyntheticMeasurementPublic.mpublic(root*"/.work/DFTK.jl/src/DFTK.jl",root,reference)=="<workbench>/.work/DFTK.jl/src/DFTK.jl"
    @test SyntheticMeasurementPublic.mpublic(reference*"/prototypes/relativistic/operator.jl",root,reference)=="<reference-root>/prototypes/relativistic/operator.jl"
end
