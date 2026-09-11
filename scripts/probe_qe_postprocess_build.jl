#!/usr/bin/env julia
# Read-only executable-product identity. Does not execute pw.x or pp.x.
using QuantumEspresso_jll, Libdl, SHA, TOML
q=QuantumEspresso_jll
hashfile(p)=bytes2hex(open(sha256,p))
result=Dict{String,Any}("julia_version"=>string(VERSION),
    "jll_uuid"=>string(Base.PkgId(q).uuid),"jll_version"=>string(pkgversion(q)),
    "jll_source"=>pathof(q),"active_project"=>Base.active_project(),
    "artifact_dir"=>q.artifact_dir,"numerical_executions"=>0)
result["products"]=Dict{String,Any}()
for (label,product) in (("pw",q.pwscf),("pp",q.pp))
    product() do executable
        p=realpath(executable)
        result["products"][label]=Dict("path"=>p,"sha256"=>hashfile(p),
          "library_environment"=>Dict(k=>get(ENV,k,"") for k in
            ("PATH","DYLD_FALLBACK_LIBRARY_PATH","DYLD_LIBRARY_PATH","LD_LIBRARY_PATH")))
    end
end
result["loaded_libraries"]=Dict(realpath(p)=>hashfile(p) for p in Libdl.dllist()
    if isfile(p) && (occursin("/.julia/artifacts/",p) || occursin("/lib/julia/",p)))
TOML.print(stdout,result;sorted=true)
