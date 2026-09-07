#!/usr/bin/env julia

function usage()
    println("Usage: inspect_relativistic_upf.jl --mode fr-nc|inspect [--default-input | UPF_PATH]")
    println("       inspect_relativistic_upf.jl --check-environment | --unit-tests | --upstream-minimal")
    println("fr-nc validates metadata and expects the locked DFTK SOC guard; inspect only parses.")
    println("Exit codes: 0 accepted/information/help; 2 arguments; 3 parse; 4 metadata;")
    println("5 unexpected construction; 6 environment; 7 prerequisite; 8 checksum; 9 runtime/I/O.")
end

const ROOT = realpath(joinpath(@__DIR__, ".."))
include("workbench_environment.jl")
include("upf_validation.jl")
using .WorkbenchEnvironment, .UpfValidation, TOML

function arguments(args)
    mode, action, input, default = nothing, "inspect", nothing, false
    i = 1
    while i <= length(args)
        arg = args[i]
        if arg == "--mode"
            i += 1
            i <= length(args) || error("--mode needs a value")
            isnothing(mode) || error("--mode repeated")
            mode = args[i]
        elseif arg == "--default-input"
            default && error("--default-input repeated")
            default = true
        elseif arg in ("--check-environment", "--unit-tests", "--upstream-minimal")
            action == "inspect" || error("Only one action is allowed")
            action = arg
        elseif startswith(arg, "-")
            error("Unknown argument: $arg")
        else
            isnothing(input) || error("Expected at most one UPF path")
            input = arg
        end
        i += 1
    end
    if action == "inspect"
        mode in ("fr-nc", "inspect") || error("Explicit --mode fr-nc or inspect required")
        xor(default, !isnothing(input)) || error("Provide one UPF path or --default-input")
    else
        isnothing(mode) && isnothing(input) && !default || error("Action cannot be combined with input/mode")
    end
    (; mode, action, input, default)
end

function early_failure(code, status, reason)
    # Only fixed internal strings reach this dependency-free JSON envelope.
    println("{\"schema_version\":2,\"parse_status\":\"NOT_RUN\",\"metadata_validation_status\":\"NOT_RUN\",\"dftk_construction_status\":\"NOT_RUN\",\"overall_status\":\"$status\",\"exit_code\":$code,\"reasons\":[\"$reason\"]}")
    exit(code)
end

if ARGS == ["--help"] || ARGS == ["-h"]
    usage()
    exit(0)
end
const OPTIONS = try
    arguments(ARGS)
catch err
    println(stderr, "ARGUMENT_ERROR: ", public_data(sprint(showerror, err), ROOT))
    early_failure(2, "ARGUMENT_ERROR", "Invalid arguments; see stderr")
end
for file in ("config/sources.lock", "environment/workbench/Project.toml",
             "environment/workbench/Manifest.toml", "environment/workbench/checksums.toml")
    isfile(joinpath(ROOT, file)) || early_failure(7, "BLOCKED", "Required workbench environment file is missing")
end
for spec in values(TOML.parsefile(joinpath(ROOT, "config", "sources.lock"))["source"])
    isdir(joinpath(ROOT, spec["checkout"])) || early_failure(7, "BLOCKED", "Required source checkout is missing")
end
# Load packages at top level before calling main in a new Julia process.
try
    @eval using JSON3, DFTK, PseudoPotentialIO
catch err
    println(stderr, "ENVIRONMENT_ERROR: ", public_data(sprint(showerror, err), ROOT))
    early_failure(6, "ENVIRONMENT_MISMATCH", "Required package could not be loaded; see stderr")
end

include("upf_runtime.jl")
using .UpfRuntime

function main(options)
    result = Dict{String,Any}("schema_version" => 2, "parse_status" => "NOT_RUN",
        "metadata_validation_status" => "NOT_RUN", "dftk_construction_status" => "NOT_RUN",
        "overall_status" => "BLOCKED", "reasons" => String[])
    finish(code) = begin
        result["exit_code"] = code
        println(JSON3.write(public_data(result, ROOT)))
        code
    end
    identity = try
        environment_identity(ROOT, (DFTK, PseudoPotentialIO))
    catch err
        result["reasons"] = ["Environment prerequisites unavailable: " * sprint(showerror, err)]
        return finish(6)
    end
    result["environment"] = identity
    if identity.status != "PASS"
        result["overall_status"] = "ENVIRONMENT_MISMATCH"
        result["reasons"] = identity.reasons
        return finish(6)
    end
    try
        if options.action != "inspect"
            if options.action == "--unit-tests"
                redirect_stdout(stderr) do
                    Base.include(Main, joinpath(ROOT, "tests", "runtests.jl"))
                end
            elseif options.action == "--upstream-minimal"
                redirect_stdout(stderr) do
                    WorkbenchEnvironment.Pkg.test("DFTK"; test_args=["minimal"], allow_reresolve=false)
                end
            end
            result["overall_status"] = "PASS"
            result["action"] = options.action
            return finish(0)
        end
        result["mode"] = options.mode
        lock = TOML.parsefile(joinpath(ROOT, "config", "sources.lock"))
        pseudo = lock["pseudopotentials"]
        input = options.default ? joinpath(ROOT, pseudo["local_path"]) : abspath(options.input)
        result["input"] = Dict("path" => options.default ? pseudo["local_path"] : "<external-input>/" * basename(input))
        if !isfile(input)
            result["reasons"] = ["UPF input is missing"]
            return finish(7)
        end
        checksum = filehash(input)
        result["input"]["sha256"] = checksum
        if options.default
            result["input"]["expected_sha256"] = pseudo["file_sha256"]
            if checksum != pseudo["file_sha256"]
                result["overall_status"] = "INPUT_MISMATCH"
                result["reasons"] = ["Default Mg checksum differs from sources.lock"]
                return finish(8)
            end
            result["input"]["family_identifier"] = pseudo["family_identifier"]
            result["input"]["source_identifier"] = pseudo["source_identifier"]
            result["input"]["scope"] = "PBEsol family; metadata inspection only, not LDA/LSDA benchmarking"
        end
        parsing = parse_input(input)
        result["parse_status"] = parsing.status
        if parsing.status != "PASS"
            result["overall_status"] = "FAIL"
            result["reasons"] = parsing.reasons
            return finish(3)
        end
        parsed = parsing.parsed
        metadata = metadata_from_upf(parsed)
        result["parsed_type"] = string(typeof(parsed))
        if options.mode == "inspect"
            result["overall_status"] = "INFO_ONLY"
            result["reasons"] = ["Parsing succeeded; FR-NC acceptance was not requested"]
            return finish(0)
        end
        acceptance = accept_metadata(metadata,
            () -> DFTK.PspUpf(parsed; identifier=basename(input));
            guard_file=joinpath(dirname(pathof(DFTK)), "pseudo", "PspUpf.jl"))
        merge!(result, Dict(string(k) => v for (k,v) in pairs(acceptance)))
        finish(acceptance.exit_code)
    catch err
        result["overall_status"] = "ERROR"
        result["reasons"] = ["Unexpected runtime error: " * sprint(showerror, err)]
        finish(9)
    end
end

exit(main(OPTIONS))
