# Parse source text only. Never include/evaluate a driver, numerical module,
# checkpoint, or physical input. This regression cannot certify an SCF run.
using Test, SHA, TOML

const SYNTAX_BASE = "c764311a5422b5c3cab5a7b78a02d420910c4e56"
const FAILED_DRIVER_EXECUTION = "1b42a27063ca65757d2c4f34d46fe4f1cd9929ed"
const SYNTAX_ROOT = normpath(joinpath(@__DIR__, "../.."))

function source_syntax_errors(source, filename)
    errors = String[]
    function inspect(tree)
        tree isa Expr || return
        if tree.head in (:error, :incomplete)
            push!(errors, sprint(show, tree))
        else
            foreach(inspect, tree.args)
        end
    end
    try
        inspect(Meta.parseall(source; filename))
    catch err
        push!(errors, sprint(showerror, err))
    end
    errors
end

function phase9a_julia_sources(root)
    # Include committed and working-tree changes plus this new untracked test.
    changed = read(Cmd(["git", "-C", root, "diff", "--name-only", "--diff-filter=ACMR", SYNTAX_BASE, "--", "*.jl"]), String)
    added = read(Cmd(["git", "-C", root, "ls-files", "--others", "--exclude-standard", "--", "*.jl"]), String)
    sort!(unique(filter(!isempty, vcat(split(changed, '\n'), split(added, '\n')))))
end

VERSION == v"1.12.7" || error("Use the frozen Julia 1.12.7 parser")
length(ARGS) <= 1 || error("Usage: test_source_syntax.jl [NEW_TOML_RECEIPT]")
!isempty(ARGS) && ispath(only(ARGS)) && error("Refusing existing syntax receipt")
record = Dict{String,Any}("scope"=>"SOURCE_PARSE_ONLY_NO_EVALUATION", "julia_version"=>string(VERSION),
    "failed_execution"=>FAILED_DRIVER_EXECUTION, "comparison_base"=>SYNTAX_BASE,
    "physical_run_status"=>"NOT_RUN", "files"=>Any[])
try
    suite = @testset "Whole Phase9A Julia sources and exact failed-driver parse regression" begin
        bad = read(`git -C $SYNTAX_ROOT show $(FAILED_DRIVER_EXECUTION*":scripts/run_si_soc.jl")`, String)
        bad_errors = source_syntax_errors(bad, "failed-execution/scripts/run_si_soc.jl")
        record["failed_driver"] = Dict("source_sha256"=>bytes2hex(sha256(bad)),
            "parse_status"=>isempty(bad_errors) ? "PASS" : "FAIL", "errors"=>bad_errors)
        @test !isempty(bad_errors)
        @test any(error->occursin("space required after", error), bad_errors)
        @test occursin(") :isnothing(profile)", bad)
        repaired = replace(bad, ") :isnothing(profile)"=>") : isnothing(profile)"; count=1)
        @test isempty(source_syntax_errors(repaired, "repaired-historical-driver.jl"))
        @test !isempty(source_syntax_errors("x = true ? 1 :foo()", "synthetic-ternary.jl"))
        @test !isempty(source_syntax_errors("function unfinished()", "synthetic-incomplete.jl"))

        paths = phase9a_julia_sources(SYNTAX_ROOT)
        @test "scripts/run_si_soc.jl" in paths
        @test "tests/soc_core_memory/test_source_syntax.jl" in paths
        for path in paths
            bytes = read(joinpath(SYNTAX_ROOT, path))
            errors = source_syntax_errors(String(copy(bytes)), path)
            push!(record["files"], Dict("path"=>path, "sha256"=>bytes2hex(sha256(bytes)),
                "parse_status"=>isempty(errors) ? "PASS" : "FAIL", "errors"=>errors))
            @test isempty(errors)
        end
    end
    counts = Test.get_test_counts(suite)
    record["assertions"] = counts.passes + counts.cumulative_passes
    record["status"] = "PASS"; record["exit_code"] = 0
catch
    record["status"] = "FAIL"; record["exit_code"] = 1
    rethrow()
finally
    if !isempty(ARGS)
        open(only(ARGS), "w") do io
            TOML.print(io, record)
        end
    end
end
