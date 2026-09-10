# SYNTHETIC authentication-transport tests only. No DFTK, checkpoint or density
# operation is loaded; the isolated bridge calls a temporary Python control stub.
using Test, SHA, JSON3
const ROOT=normpath(joinpath(@__DIR__,"../../.."))
const BRIDGE_SOURCE=read(joinpath(ROOT,"benchmarks/soc-core-memory-v1/endpoint_compare.jl"),String)
const BRIDGE_TEXT="function endpoint_resume_authorization("*split(split(BRIDGE_SOURCE,"function endpoint_resume_authorization(";limit=2)[2],"function endpoint_worker(";limit=2)[1]
digest(path)=bytes2hex(sha256(read(path)))
require_value(ok,reason)=ok || error(reason)
include_string(Main,BRIDGE_TEXT,"endpoint_compare.jl:isolated_authentication_bridge")

const CONTROL_STUB=raw"""
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[sys.argv.index('--root') + 1])
(root/'call.json').write_text(json.dumps(sys.argv[1:]))
settings = json.loads((root/'synthetic-response.json').read_text())
auth = pathlib.Path(sys.argv[sys.argv.index('--authorization') + 1])
response = dict(status='PASS', endpoint_execution_commit='a'*40,
                authorization_sha256=hashlib.sha256(auth.read_bytes()).hexdigest())
response.update(settings.get('response', {}))
if settings.get('mutate_authorization'):
    auth.write_text('SYNTHETIC CHANGED AUTHORIZATION\n')
if settings.get('malformed_json'):
    print('not json')
else:
    print(json.dumps(response))
sys.exit(settings.get('exit_code', 0))
"""

@testset "Synthetic continuation endpoint authentication bridge" begin
    python=get(ENV,"SOC_CORE_PYTHON","")
    @test isabspath(python) && isfile(python)
    mktempdir() do temporary
        root=realpath(temporary) # macOS tempdir may be a /var alias; contract stays strict.
        control=joinpath(root,"benchmarks/soc-core-memory-v1/resume/control.py")
        mkpath(dirname(control));write(control,CONTROL_STUB)
        auth=joinpath(root,"authorization.json");write(auth,"SYNTHETIC AUTHORIZATION\n")
        config=joinpath(root,"synthetic-response.json")
        scf=joinpath(root,"scf.json");gamma=joinpath(root,"gamma.json")
        configure(value)=write(config,JSON3.write(value))
        invoke()=endpoint_resume_authorization(root,auth,scf,gamma,"a"^40)
        configure(Dict());verified=invoke()
        @test verified["status"]=="PASS"
        @test verified["authorization_sha256"]==digest(auth)
        @test JSON3.read(read(joinpath(root,"call.json"),String),Vector{String})==[
            "verify-endpoints","--root",root,"--authorization",auth,"--execution-commit","a"^40,
            "--scf",scf,"--gamma",gamma]
        for response in (Dict("status"=>"FAIL"),Dict("endpoint_execution_commit"=>"b"^40),
                         Dict("authorization_sha256"=>"c"^64))
            configure(Dict("response"=>response))
            @test_throws ErrorException invoke()
        end
        configure(Dict("exit_code"=>7))
        @test_throws ProcessFailedException invoke()
        configure(Dict("malformed_json"=>true))
        @test_throws Exception invoke()
        configure(Dict("mutate_authorization"=>true))
        @test_throws ErrorException invoke()
        configure(Dict())
        withenv("SOC_CORE_PYTHON"=>nothing) do
            @test_throws ErrorException invoke()
        end
        withenv("SOC_CORE_PYTHON"=>"python3") do
            @test_throws ErrorException invoke()
        end
        link=joinpath(root,"authorization-link.json");symlink(auth,link)
        @test_throws ErrorException endpoint_resume_authorization(root,link,scf,gamma,"a"^40)
    end
end
