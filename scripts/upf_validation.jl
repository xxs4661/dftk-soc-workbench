module UpfValidation

export validate_metadata, classify_exception, check_construction, accept_metadata, SOC_MESSAGE

const SOC_MESSAGE = "Pseudopotential contains the following unsupported features/quantities: spin-orbit coupling"
# j is dimensionless. Tolerance only accommodates floating-point text roundoff;
# no rounding and no relative tolerance are used to legalize other j values.
const J_ATOL = 1e-10

function validate_metadata(m)
    fail(reason) = (; status="FAIL", reasons=[reason], mapping=NamedTuple[])
    unsupported(reason) = (; status="UNSUPPORTED", reasons=[reason], mapping=NamedTuple[])
    m.is_upf || return fail("Input did not parse as UpfFile")
    m.pseudo_type == "NC" || return fail("FR-NC mode requires pseudo_type=NC")
    m.has_so === true || return fail("FR-NC mode requires has_so=true")
    m.relativistic == "scalar" && return fail("FR-NC mode rejects scalar-relativistic input")
    m.relativistic == "full" || return unsupported("This validator requires explicit relativistic=full; other spellings are not inferred")
    (isnothing(m.relbetas) || isempty(m.relbetas)) &&
        return fail("Required spin-orbit beta metadata is absent")
    n = m.declared_count
    (n isa Integer && n > 0) || return fail("Missing or invalid declared projector count")
    # UPF v2 removes all-zero betas but does not reindex their source IDs. Do not
    # silently equate array position with source index or claim pruned files invalid.
    length(m.betas) == n || return unsupported(
        "Parsed beta count differs from header; possible parser pruning is not supported")
    for (label, records) in (("beta", m.betas), ("relativistic beta", m.relbetas))
        ids = [r.index for r in records]
        any(isnothing, ids) && return unsupported(
            "$label has no explicit parsed index; label/position inference is not supported")
        all(i -> i isa Integer && 1 <= i <= n, ids) ||
            return fail("$label index is outside the declared source-index range")
        length(unique(ids)) == length(ids) || return fail("Duplicate $label source index")
    end
    by_index = Dict(b.index => b for b in m.betas)
    Set(keys(by_index)) == Set(r.index for r in m.relbetas) ||
        return fail("Beta and relativistic-beta index sets differ: missing/unassociated record")
    mapping = NamedTuple[]
    for r in m.relbetas
        b = by_index[r.index]
        isnothing(r.l) && return unsupported("Relativistic beta lacks l; cannot establish l agreement")
        (b.l isa Integer && b.l >= 0 && r.l == b.l) ||
            return fail("Inconsistent or invalid l for beta index $(r.index)")
        j = r.j
        (j isa Real && isfinite(j)) || return fail("Non-finite or non-real j for beta index $(r.index)")
        allowed = b.l == 0 ? (0.5,) : (b.l - 0.5, b.l + 0.5)
        any(a -> isapprox(j, a; atol=J_ATOL, rtol=0), allowed) ||
            return fail("j violates angular-momentum constraints for beta index $(r.index)")
        push!(mapping, (; source_index=r.index, l=b.l, j))
    end
    # Uniqueness is by source index, never by (l,j). PP_RELWFC is not used here.
    (; status="PASS", reasons=String[], mapping=sort(mapping; by=x -> x.source_index))
end

function classify_exception(err, from_soc_guard)
    err isa ErrorException && err.msg == SOC_MESSAGE && from_soc_guard ?
        "EXPECTED_SOC_REJECTION" : "UNEXPECTED_ERROR"
end

function check_construction(construct; guard_file=nothing, guard_line=107)
    try
        construct()
        (; status="UNEXPECTED_SUCCESS", error_type=nothing, error_message=nothing,
           guard_origin=false, reasons=["Locked DFTK unexpectedly constructed the FR-NC input"])
    catch err
        # Identity/cleanliness must already have been verified by the caller.
        # Match the throwing frame in the locked constructor, not just the message.
        frames = stacktrace(catch_backtrace())
        from_guard = !isnothing(guard_file) && any(frames) do frame
            file = String(frame.file)
            isfile(file) && realpath(file) == realpath(guard_file) &&
                frame.line == guard_line && (frame.func == :PspUpf ||
                    startswith(string(frame.func), "#PspUpf#"))
        end
        status = classify_exception(err, from_guard)
        (; status, error_type=string(typeof(err)), error_message=sprint(showerror, err),
           guard_origin=from_guard, reasons=status == "EXPECTED_SOC_REJECTION" ? String[] :
            ["$(typeof(err)): $(sprint(showerror, err))"])
    end
end

function accept_metadata(metadata, construct; kwargs...)
    validation = validate_metadata(metadata)
    if validation.status != "PASS"
        return (; metadata_validation=validation, metadata_validation_status=validation.status,
                dftk_construction_status="NOT_RUN", overall_status=validation.status,
                reasons=validation.reasons, exit_code=4)
    end
    construction = check_construction(construct; kwargs...)
    success = construction.status == "EXPECTED_SOC_REJECTION"
    (; metadata_validation=validation, metadata_validation_status="PASS",
       dftk_construction_status=construction.status, dftk_construction=construction,
       overall_status=success ? "PASS" : "FAIL",
       reasons=construction.reasons, exit_code=success ? 0 : 5)
end

end
