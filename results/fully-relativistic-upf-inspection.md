# Fully relativistic NC-UPF inspection

**DFTK.jl locked commit:** `2f51b91213e26726fb9c6a17e5fae235a1412d01`

**PseudoPotentialIO.jl locked commit:** `fec942781560c391f20214ba4cd85fb2431deb84`

**Inspection status:** PASS (raw parsing succeeded and the expected, separate DFTK rejection was observed)

**Scope:** inspection only; no DFTK or PseudoPotentialIO source was changed and no SOC code was implemented.

## 1. Scope and locked source revisions

This report answers the Phase 3 source questions from clean detached checkouts at the commits above. PseudoPotentialIO v0.3.3 loaded by the locked DFTK environment has tree SHA-1 `749e921146af23d79563a9e9c409ae807fdc261b`, identical to the tree of the locked PseudoPotentialIO checkout. The compact citation index is [`source-map.md`](source-map.md).

## 2. Test pseudopotential provenance

| Field | Observed value |
| --- | --- |
| Element | `Mg` |
| Family identifier | `dojo.nc.fr.pbesol.v0_4.stringent.upf` |
| File | `Mg.upf` |
| Source/package | PseudoPotentialData v0.3.2, PseudoLibrary v0.2.1 artifact |
| Package classification | collection `dojo`, type `nc`, relativistic `fr`, generator family `oncvpsp3` |
| Package artifact tree | `b9d31b902d479f27ebd6420c6e4cc0bb5281d8b0` |
| Package archive SHA-256 | `30670649c0eb3f0537f64bf2ab98d1ebba005bdb72f07970673dacea2f3f2be4` |
| Selected file SHA-256 | `19b117bfa920945bffaee91eefbcfbf9fd44e035f3708b965aae59aabf3be256` |
| Local temporary path | `.work/pseudos/Mg.upf` |
| Redistribution | Not verified; inspected locally and not redistributed or committed |

The family was resolved through the installed PseudoPotentialData ecosystem, the first preferred source category. Its artifact declaration identifies the family, tree, archive checksum, and PseudoLibrary release URL. The package's code license is not treated as proof of the data artifact's redistribution terms.

## 3. Runtime status

[`upf-inspection.json`](upf-inspection.json) records only observed values. PseudoPotentialIO parsing returned `UpfFile` with UPF version `2.0.1`, pseudo type `NC`, relativistic mode `full`, and `has_so=true`. It found six beta projectors with angular momenta `[0,0,1,1,1,1]`, six relativistic beta records, `l` values `[0,1]`, `j` values `[0.5,1.5]`, and four relativistic wavefunction records. Every observed `PP_RELBETA` index matched the same indexed beta record.

The subsequent, separately recorded `DFTK.PspUpf` construction attempt returned `REJECTED` with `ErrorException`: `Pseudopotential contains the following unsupported features/quantities: spin-orbit coupling`. The inspection command exited `0` because successful raw parsing plus this recognized rejection is the expected inspection outcome. A parser failure or unexpected DFTK error returns nonzero.

## 4. PseudoPotentialIO parsing path

1. `load_psp_file` maps the `.upf` extension to `UpfFile` ([PseudoPotentialIO.jl @ `fec9427…`, `src/load.jl:1-12`, `load_psp_file`](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/load.jl#L1-L12)).
2. `UpfFile(io)` detects the version and calls `upf1_parse_psp` or `upf2_parse_psp` ([PseudoPotentialIO.jl @ `fec9427…`, `src/file/upf.jl:377-392`, `UpfFile`](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/file/upf.jl#L377-L392)).
3. For UPF v2, `upf2_parse_header` reads `relativistic` and reads `has_so` from the `PP_HEADER` attribute using `get_attr(Bool, …)` ([PseudoPotentialIO.jl @ `fec9427…`, `src/file/upf2.jl:148-185`, `upf2_parse_header`](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/file/upf2.jl#L148-L185)). The Boolean helper treats an attribute containing `T`, case-insensitively, as true; a missing attribute returns its default ([PseudoPotentialIO.jl @ `fec9427…`, `src/file/upf2.jl:725-746`, `parse_bool` and `get_attr`](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/file/upf2.jl#L725-L746)).
4. `upf2_parse_psp` checks for `PP_SPIN_ORB` and calls `upf2_parse_spin_orb` when present ([PseudoPotentialIO.jl @ `fec9427…`, `src/file/upf2.jl:1-83`, `upf2_parse_psp`](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/file/upf2.jl#L1-L83)). The latter filters child names for `PP_RELWFC.*` and `PP_RELBETA.*`, then maps the corresponding parsers ([PseudoPotentialIO.jl @ `fec9427…`, `src/file/upf2.jl:520-566`, `upf2_parse_relwfc`, `upf2_parse_relbeta`, `upf2_parse_spin_orb`](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/file/upf2.jl#L520-L566)).
5. For UPF v1, `has_so` and `relativistic` are inferred from the presence of `PP_ADDINFO`; `upf1_parse_addinfo` reads the relativistic wavefunction and beta records ([PseudoPotentialIO.jl @ `fec9427…`, `src/file/upf1.jl:137-158`, `upf1_parse_header`](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/file/upf1.jl#L137-L158); [`src/file/upf1.jl:383-406`, `upf1_parse_addinfo`](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/file/upf1.jl#L383-L406)).

## 5. Exact structures, fields, and parser functions

`UpfHeader` stores `pseudo_type::String`, `relativistic::Union{Nothing,String}`, `has_so::Bool`, `l_max::Int`, and `number_of_proj::Int` ([PseudoPotentialIO.jl @ `fec9427…`, `src/file/upf.jl:4-58`, `UpfHeader`](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/file/upf.jl#L4-L58)). `UpfBeta` stores `index::Union{Nothing,Int}` and `angular_momentum::Int`; `UpfNonlocal` stores `betas::Vector{UpfBeta}` and `dij::Matrix{Float64}` ([PseudoPotentialIO.jl @ `fec9427…`, `src/file/upf.jl:205-227`, `UpfBeta`, `UpfNonlocal`](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/file/upf.jl#L205-L227)).

The exact relativistic records are:

- `UpfRelWfc`: `jchi::Float64`, `index::Union{Nothing,Int}`, `els::Union{Nothing,String}`, `nn::Union{Nothing,Int}`, `lchi::Union{Nothing,Int}`, `oc::Union{Nothing,Float64}`.
- `UpfRelBeta`: `index::Union{Nothing,Int}`, `jjj::Float64`, `lll::Union{Nothing,Int}`.
- `UpfSpinOrb`: `relwfcs::Vector{UpfRelWfc}`, `relbetas::Vector{UpfRelBeta}`.

These definitions are in [PseudoPotentialIO.jl @ `fec9427…`, `src/file/upf.jl:248-274`, `UpfRelWfc`, `UpfRelBeta`, `UpfSpinOrb`](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/file/upf.jl#L248-L274). The optional `UpfFile.spin_orb::Union{Nothing,UpfSpinOrb}` retains the parsed group ([PseudoPotentialIO.jl @ `fec9427…`, `src/file/upf.jl:331-375`, `UpfFile`](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/file/upf.jl#L331-L375)). For v2, the parser functions are `upf2_parse_relwfc`, `upf2_parse_relbeta`, and `upf2_parse_spin_orb` at the cited lines above. For v1, the function is `upf1_parse_addinfo`.

The `UpfRelBeta.index` is the available link to a beta projector. This interpretation is supported by the locked Mg parser test, which checks that both beta and relativistic-beta indices follow their array positions and checks representative `lll`/`jjj` values ([PseudoPotentialIO.jl @ `fec9427…`, `test/file/upf2.jl:94-192`, `Mg.upf` testset](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/test/file/upf2.jl#L94-L192); [`test/file/upf2.jl:227-251`](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/test/file/upf2.jl#L227-L251)). Runtime inspection verified the mapping for this selected file; it does not prove that every possible UPF producer emits valid or contiguous indices.

## 6. DFTK construction path and exact rejection point

`PspUpf(path)` first calls `load_psp_file`, then dispatches to `PspUpf(::UpfFile)` ([DFTK.jl @ `2f51b91…`, `src/pseudo/PspUpf.jl:66-98`, `PspUpf`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/pseudo/PspUpf.jl#L66-L98)). In `PspUpf(pseudo::UpfFile; …)`, line 100 appends `spin-orbit coupling` when `pseudo.header.has_so`; lines 107-108 raise the unsupported-feature error ([DFTK.jl @ `2f51b91…`, `src/pseudo/PspUpf.jl:98-108`, `PspUpf(::UpfFile; …)`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/pseudo/PspUpf.jl#L98-L108)).

Observed nuance: the guard checks `header.has_so`; this locked function has no separate rejection predicate on the string `header.relativistic == "full"`. Therefore this report does not broaden the source finding beyond the condition actually implemented.

## 7. Relativistic metadata available upstream and the DFTK gap

PseudoPotentialIO retains header relativity and `has_so`, the optional spin-orbit container, `PP_RELWFC` quantum numbers, and each `PP_RELBETA` record's index, `l` (`lll`), and `j` (`jjj`) ([PseudoPotentialIO.jl @ `fec9427…`, `src/file/upf.jl:4-58`, `UpfHeader`](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/file/upf.jl#L4-L58); [`src/file/upf.jl:248-274`, relativistic types](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/file/upf.jl#L248-L274); [`src/file/upf.jl:331-375`, `UpfFile`](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/file/upf.jl#L331-L375)).

Current DFTK `PspUpf` represents scalar `lmax`, projectors grouped as `r2_projs[l+1][i]`, and coupling blocks `h[l+1][i,j]`. Its fields contain no `has_so`, relativistic-mode string, source beta index, `j`, `PP_RELWFC`, or `PP_RELBETA` representation ([DFTK.jl @ `2f51b91…`, `src/pseudo/PspUpf.jl:5-64`, `PspUpf`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/pseudo/PspUpf.jl#L5-L64)). The constructor rejects before those scalar arrays are built. In its supported path it filters betas by `angular_momentum` and slices `dij` by the same-`l` mask, preserving radial order within each filter result but not explicitly storing each original beta index ([DFTK.jl @ `2f51b91…`, `src/pseudo/PspUpf.jl:110-138`, `PspUpf(::UpfFile; …)`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/pseudo/PspUpf.jl#L110-L138)).

## 8. Scalar projector ordering

The actual `P`/`D` storage order is `(A,l,m,i)`: atom first, then angular momentum `l`, magnetic quantum number `m`, and radial-projector index `i` fastest. The source states that order and says nonzeros in `D` require matching `A`, `l`, and `m`; the loops allocate one atom block at a time, then one `h[l+1]` radial block for each `m` ([DFTK.jl @ `2f51b91…`, `src/terms/nonlocal.jl:103-142`, `build_projection_coefficients`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/terms/nonlocal.jl#L103-L142)). `build_projection_vectors` traverses pseudopotential groups and then their positions, matching the atom-block sequence ([DFTK.jl @ `2f51b91…`, `src/terms/nonlocal.jl:167-200`, `build_projection_vectors`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/terms/nonlocal.jl#L167-L200)). `build_projector_form_factors` computes offsets per `l` and `m` and places radial `i` at adjacent columns ([DFTK.jl @ `2f51b91…`, `src/terms/nonlocal.jl:203-245`, `build_projector_form_factors`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/terms/nonlocal.jl#L203-L245)).

There is a naming/iteration detail worth review: `projector_indices` returns tuple values `(i,l,m)` while nesting its generator loops as `l`, then `i`, then `m` ([DFTK.jl @ `2f51b91…`, `src/pseudo/NormConservingPsp.jl:187-189`, `projector_indices`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/pseudo/NormConservingPsp.jl#L187-L189)). It has no call sites in the locked `src/` or `test/` trees and is not the column-layout implementation. Any future work should avoid treating that helper's loop nesting as evidence contrary to the explicit `P`/`D` builders.

## 9. Current `P`, `D`, `P D P'`, and energy construction

- Radial real/Fourier evaluation: `eval_psp_projector_real` and `eval_psp_projector_fourier`; the latter calls `hankel` ([DFTK.jl @ `2f51b91…`, `src/pseudo/PspUpf.jl:182-208`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/pseudo/PspUpf.jl#L182-L208)).
- Atom-centered angular/radial form factors: `build_projector_form_factors` ([DFTK.jl @ `2f51b91…`, `src/terms/nonlocal.jl:203-245`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/terms/nonlocal.jl#L203-L245)).
- Projection matrix `P`: `build_projection_vectors` ([DFTK.jl @ `2f51b91…`, `src/terms/nonlocal.jl:167-200`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/terms/nonlocal.jl#L167-L200)).
- Coupling matrix `D`: both `build_projection_coefficients` methods ([DFTK.jl @ `2f51b91…`, `src/terms/nonlocal.jl:103-142`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/terms/nonlocal.jl#L103-L142)).
- Operator: `AtomicNonlocal` builds `P` and `D` and constructs `NonlocalOperator` ([DFTK.jl @ `2f51b91…`, `src/terms/nonlocal.jl:8-24`, `AtomicNonlocal`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/terms/nonlocal.jl#L8-L24)); `NonlocalOperator.apply!` applies `P*(D*(P'*ψ))`, and `Base.Matrix` materializes the same product ([DFTK.jl @ `2f51b91…`, `src/terms/operators.jl:115-129`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/terms/operators.jl#L115-L129)).
- Energy: `ene_ops(::TermAtomicNonlocal, …)` computes `P'ψ`, multiplies by `D`, weights band contributions and k-points, and reduces them ([DFTK.jl @ `2f51b91…`, `src/terms/nonlocal.jl:31-46`, `ene_ops`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/terms/nonlocal.jl#L31-L46)).

`D` is block diagonal across atoms, `l`, and `m`, and the same `h[l+1]` block is repeated for every `m` at a given `l`. It is **not required to be diagonal in radial projector indices**: the entire matrix `h[l+1]` is copied into each block. During UPF ingestion, DFTK selects only same-`l` `dij` submatrices, so cross-`l` entries are not represented ([DFTK.jl @ `2f51b91…`, `src/pseudo/PspUpf.jl:128-138`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/pseudo/PspUpf.jl#L128-L138); [`src/terms/nonlocal.jl:127-142`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/terms/nonlocal.jl#L127-L142)). The selected Mg file happens to have diagonal `dij`; that runtime fact is not a general DFTK assumption.

## 10. Minimal additive data-model proposal

The smallest candidate worth discussing is an **optional, immutable metadata companion** aligned with the current per-`l`, per-radial-projector storage. Each record would preserve the source beta index, `l`, and `j`, for example conceptually `(beta_index::Union{Nothing,Int}, l::Int, j::Float64)`, with optional header-level `has_so`/relativistic-mode provenance. It would carry no operator methods and would not alter `P`, `D`, `P D P'`, energy evaluation, or the current unsupported-feature guard.

This is a proposal, not an implementation. In particular, attaching a new field directly to `PspUpf` may not be the least disruptive API: a companion returned by an inspection/extraction function could preserve metadata while `PspUpf` continues to reject `has_so=true`. Maintainer discussion is needed before choosing either representation.

## 11. Compatibility considerations

- Scalar UPFs should observe no behavioral or numerical change; absent metadata should be represented as `nothing` or by an empty, explicitly non-relativistic companion.
- Existing `r2_projs[l+1][i]` and `h[l+1]` indexing must remain stable. A metadata list must validate its mapping against `UpfBeta.index` rather than assume array position for every producer.
- Adding a field to concrete `PspUpf` changes its positional construction and potentially serialization/type layout. A separate companion/accessor avoids that immediate compatibility cost.
- Metadata preservation must not silently make a fully relativistic UPF usable by the scalar nonlocal operator. The rejection boundary should remain explicit until a separately reviewed operator exists.
- PseudoPotentialIO permits nullable index/`l` fields, so any DFTK-facing validation must specify what missing or duplicate indices mean before ingestion is relaxed.

## 12. Facts versus hypotheses

### Observed facts

- PseudoPotentialIO has exact structures for relativistic wavefunction/beta records and stores them on `UpfFile` at the pinned definitions cited in section 5.
- The selected file parsed with six relativistic beta records covering `l=0,1` and `j=1/2,3/2`, and all six indices matched beta indices; see [`upf-inspection.json`](upf-inspection.json).
- DFTK rejects on `pseudo.header.has_so` before populating `PspUpf`; the exact guard is cited in section 6.
- Scalar `PspUpf` groups data by `l` and does not contain `j` or source-index fields; the exact fields and ingestion code are cited in section 7.
- The scalar nonlocal column layout and `D` block structure are those described in sections 8 and 9.

### Hypotheses requiring maintainer discussion

- An optional companion record is the smallest acceptable DFTK data-model change.
- The record should live inside `PspUpf`, beside it, or only at a preflight/parser boundary.
- `Float64` is the right long-term representation for half-integer `j` rather than a validated doubled integer or rational representation.
- `PP_RELWFC` metadata must also be retained in the first additive change; the immediate projector mapping requires `PP_RELBETA`, but later initialization or validation may need wavefunction records.
- Index equality is a sufficient mapping invariant for all UPF producers; the selected file and locked tests support it for their cases only.

## 13. Current scalar tests

DFTK's locked scalar tests check PseudoDojo UPF ingestion and stored projector data ([DFTK.jl @ `2f51b91…`, `test/PspUpf.jl:31-45`, `Check reading PseudoDojo Li UPF`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/test/PspUpf.jl#L31-L45)); compare UPF projectors to HGH in real and Fourier space ([`test/PspUpf.jl:90-118`, projector consistency](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/test/PspUpf.jl#L90-L118)); and independently compare the real/Fourier Hankel path ([`test/PspUpf.jl:149-173`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/test/PspUpf.jl#L149-L173)).

The Hamiltonian consistency helper compares every operator's matrix form with its application and checks the energy derivative ([DFTK.jl @ `2f51b91…`, `test/hamiltonian_consistency.jl:11-110`, `test_consistency_term`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/test/hamiltonian_consistency.jl#L11-L110)); it invokes `AtomicNonlocal` for both GTH and scalar UPF silicon inputs ([`test/hamiltonian_consistency.jl:145-150`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/test/hamiltonian_consistency.jl#L145-L150)). A separate energy regression asserts the scalar `AtomicNonlocal` contribution ([DFTK.jl @ `2f51b91…`, `test/energies_guess_density.jl:23-36`](https://github.com/xxs4661/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/test/energies_guess_density.jl#L23-L36)). These are scalar coverage, not SOC tests.

## 14. Unresolved questions

1. Should relativistic records be preserved in a generic pseudopotential metadata layer, in `PspUpf`, or only through an explicit preflight object while construction remains rejected?
2. Which consistency rules are required for missing, duplicated, reordered, or removed all-zero beta indices, especially because the v2 parser may remove all-zero beta rows and columns ([PseudoPotentialIO.jl @ `fec9427…`, `src/file/upf2.jl:448-467`, `upf2_parse_nonlocal`](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/file/upf2.jl#L448-L467))?
3. Should the first preservation layer include all `PP_RELWFC` fields or only projector metadata?
4. What representation and validation should DFTK use for half-integer `j`?
5. How should future spinor projector ordering relate to the current `(A,l,m,i)` scalar layout? This phase does not answer that design question.

## 15. Explicit non-claims

This phase does not establish:

- a correct SOC Hamiltonian;
- a correct Clebsch–Gordan convention;
- numerical agreement with Quantum ESPRESSO;
- an accepted or maintainer-approved DFTK architecture.

It also does not claim redistribution permission for the inspected UPF, that every UPF producer follows the selected file's index behavior, or that the current scalar projector layout should be reused unchanged for SOC.

## 16. Commands and exit codes

| Command | Exit | Result |
| --- | ---: | --- |
| `JULIA_DEPOT_PATH=.work/julia-depot julia --startup-file=no --project=.work/DFTK.jl -e 'using PseudoPotentialData; family = PseudoFamily("dojo.nc.fr.pbesol.v0_4.stringent.upf"); println(family[:Mg])'` | 0 | Resolved the installed package artifact. |
| `mkdir -p .work/pseudos` and `cp <resolved-artifact>/Mg.upf .work/pseudos/Mg.upf` | 0 | Staged the ignored inspection input locally. |
| First Julia `--help` run with `using JSON3` | 1 | Exposed that JSON3 was not a direct dependency; no result was concealed. The script was changed to use its own deterministic JSON serializer. |
| `bash -n scripts/run_upf_inspection.sh` | 0 | Shell syntax valid. |
| `JULIA_DEPOT_PATH=.work/julia-depot julia --startup-file=no --color=no --project=.work/DFTK.jl scripts/inspect_relativistic_upf.jl --help` | 0 | Usage path passed after the dependency-free change. |
| `bash scripts/run_upf_inspection.sh` | 0 | Raw parse `PASS`; DFTK construction `REJECTED`; inspection `PASS`. |
| `shasum -a 256 .work/pseudos/Mg.upf` | 0 | Independently confirmed `19b117…be256`. |
| `python3 -m json.tool results/upf-inspection.json` | 0 | JSON syntax valid. |
| Locked-source `nl -ba`/`sed` evidence captures and `rg` symbol/call-site searches | 0 | Generated the pinned line map from local checkouts. |
| Combined preflight/status command ending in `git symbolic-ref --short refs/remotes/origin/HEAD` | 128 | The local clone has no symbolic `origin/HEAD`; earlier subcommands confirmed Phase 1/2 commits. This does not affect the checked-out `main` branch. |
| First missing-input validation wrapper | 1 | The inspector correctly exited `2`, but the surrounding zsh command mistakenly assigned the read-only name `status`; the wrapper therefore exited `1`. |
| Missing-input validation rerun using `input_exit` | 0 | Observed and asserted the inspector's intended exit code `2`. |
| `gh repo view xxs4661/dftk-soc-workbench --json nameWithOwner,url,visibility,defaultBranchRef` (restricted network attempt) | 1 | Network access was unavailable in the restricted command context. |
| The same `gh repo view` command with approved network access | 0 | Confirmed public repository `xxs4661/dftk-soc-workbench`, default branch `main`. |
| `git ls-files '*.upf' '*.UPF'` plus extension search outside `.work` | 0 | No UPF payload is tracked or present outside the ignored workspace. |

The final validation, commit, and push commands are recorded in [`HANDOFF_TO_GPT56PRO.md`](../HANDOFF_TO_GPT56PRO.md) because they occur after this report is assembled.
