using Test
isdefined(@__MODULE__, :UpfValidation) || include("../scripts/upf_validation.jl")
using .UpfValidation

# In-memory metadata only: these objects have no radial data and are NOT physical UPFs.
beta(i, l) = (; index=i, l)
relbeta(i, l, j) = (; index=i, l, j)
function metadata(; kwargs...)
    merge((; is_upf=true, pseudo_type="NC", has_so=true, relativistic="full",
           declared_count=3, betas=[beta(1, 0), beta(2, 1), beta(3, 1)],
           relbetas=[relbeta(1, 0, 0.5), relbeta(2, 1, 0.5), relbeta(3, 1, 0.5)]),
          (; kwargs...))
end

@testset "FR-NC metadata (memory objects only)" begin
    @test validate_metadata(metadata()).status == "PASS"
    for bad in (metadata(is_upf=false), metadata(has_so=false, relativistic="scalar"),
                metadata(pseudo_type="US"), metadata(pseudo_type="USPP"),
                metadata(pseudo_type="PAW"), metadata(relativistic="scalar"),
                metadata(relbetas=nothing), metadata(relbetas=[]),
                metadata(betas=[beta(1,0), beta(1,1), beta(3,1)]),
                metadata(relbetas=[relbeta(1,0,0.5), relbeta(2,1,0.5), relbeta(2,1,0.5)]),
                metadata(relbetas=[relbeta(1,0,0.5), relbeta(2,1,0.5)]),
                metadata(relbetas=[relbeta(1,0,0.5), relbeta(2,1,0.5), relbeta(4,1,0.5)]),
                metadata(relbetas=[relbeta(nothing,0,0.5), relbeta(2,1,0.5), relbeta(3,1,0.5)]),
                metadata(betas=[beta(nothing,0), beta(2,1), beta(3,1)]),
                metadata(relbetas=[relbeta(1,1,0.5), relbeta(2,1,0.5), relbeta(3,1,0.5)]))
        r = validate_metadata(bad)
        @test r.status != "PASS"
        @test !isempty(r.reasons)
    end
    for j in (1.5, NaN, Inf, -0.5, 0.0, 0.50001)
        @test validate_metadata(metadata(relbetas=[relbeta(1,0,j), relbeta(2,1,0.5), relbeta(3,1,0.5)])).status != "PASS"
    end
    for j in (0.5, 1.5)
        @test validate_metadata(metadata(relbetas=[relbeta(1,0,0.5), relbeta(2,1,j), relbeta(3,1,j)])).status == "PASS"
    end
    # Multiple radial projectors may share (l,j), and a partner j branch is not required.
    @test validate_metadata(metadata()).status == "PASS"
    @test validate_metadata(metadata(relbetas=reverse(metadata().relbetas), betas=reverse(metadata().betas))).status == "PASS"
    @test validate_metadata(metadata(relbetas=[relbeta(1,0,0.5+1e-12), relbeta(2,1,0.5), relbeta(3,1,0.5)])).status == "PASS"
    # A pruned source record is unsupported; never infer a new positional index.
    @test validate_metadata(metadata(betas=[beta(1,0), beta(3,1)])).status == "UNSUPPORTED"
end

@testset "DFTK construction classification" begin
    @test classify_exception(ErrorException("unrelated unsupported feature"), true) == "UNEXPECTED_ERROR"
    @test classify_exception(ErrorException(SOC_MESSAGE), false) == "UNEXPECTED_ERROR"
    @test classify_exception(ArgumentError(SOC_MESSAGE), true) == "UNEXPECTED_ERROR"
    @test classify_exception(ErrorException(SOC_MESSAGE * ",gipaw data"), true) == "UNEXPECTED_ERROR"
    @test classify_exception(ErrorException(SOC_MESSAGE), true) == "EXPECTED_SOC_REJECTION"
    @test check_construction(() -> nothing).status == "UNEXPECTED_SUCCESS"
    @test check_construction(() -> error("unexpected runtime failure")).status == "UNEXPECTED_ERROR"
    @test accept_metadata(metadata(), () -> nothing).exit_code == 5
    @test accept_metadata(metadata(), () -> error("unrelated unsupported feature")).exit_code == 5
    @test accept_metadata(metadata(), () -> error("unexpected runtime failure")).exit_code == 5
    called = Ref(false)
    rejected = accept_metadata(metadata(has_so=false), () -> (called[] = true))
    @test rejected.exit_code == 4
    @test rejected.metadata_validation_status == "FAIL"
    @test rejected.dftk_construction_status == "NOT_RUN"
    @test !called[]
end

if isdefined(@__MODULE__, :UpfRuntime)
    @testset "Parsing and beta adapter" begin
        @test UpfRuntime.parse_input("unused"; loader=_ -> nothing).status == "FAIL"
        @test UpfRuntime.parse_input("unused"; loader=_ -> error("parse failure")).status == "FAIL"
        # Explicitly non-physical memory metadata; no PP_RELWFC property exists.
        m = metadata()
        parsed_fields = (; header=(; pseudo_type=m.pseudo_type, has_so=m.has_so,
            relativistic=m.relativistic, number_of_proj=m.declared_count),
            nonlocal=(; betas=[(; index=b.index, angular_momentum=b.l) for b in m.betas]),
            spin_orb=(; relbetas=[(; index=b.index, lll=b.l, jjj=b.j) for b in m.relbetas]))
        @test validate_metadata(UpfRuntime.metadata_from_upf(parsed_fields)).status == "PASS"
    end
end

if isdefined(@__MODULE__, :WorkbenchEnvironment) && isdefined(@__MODULE__, :DFTK)
    @testset "Loaded package identity" begin
        root = realpath(joinpath(@__DIR__, ".."))
        @test WorkbenchEnvironment.environment_identity(root, (DFTK, PseudoPotentialIO)).status == "PASS"
        wrong = WorkbenchEnvironment.environment_identity(root, (DFTK, DFTK))
        @test wrong.status == "MISMATCH"
        @test "pseudopotentialio loaded UUID mismatch" in wrong.reasons
    end
end
