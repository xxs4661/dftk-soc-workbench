# Si acceptance semantics v2 — Phase 8A.1 erratum

This corrects the scope of one machine-readable aggregate, not a newly found
SOC physics error. The historical comparator calculated occupations but its
`manifold_assignment_status` combined only window isolation and group widths.
The original evidence and report already disclosed occupation and physical
interpretation **REVIEW_REQUIRED**. All original code, inputs, spectra,
occupations, E/F, warnings, process exits and evidence hashes remain unchanged.
The approximately 47.4576 meV finite-window split and same-density spin-trace
observation remain supported within their original scope.

The rules below precede formal assessment in an ordinary source commit.
Historical input: `61cb1c226dcfa8dbeccc63e8f43e33b2790a07c6`; historical physical
execution: `3948ed5d37660fe1e909aa6d12983234e317a479`. The new semantic execution
commit is recorded separately after execution; no old result becomes a new SCF.

| Version 2 field | Rule |
| --- | --- |
| `historical_replay_status` | Unmodified complete old checker succeeds in the exact detached historical snapshot. |
| `fixed_window_structure_status` | Both original window-isolation and doublet/quartet-width gates. |
| `fixed_window_splitting_comparison_status` | Frozen comparator's structure, resolvability and D/Q split-difference gates; no occupation condition added to this finite-window statistic. |
| `spin_trace_control_status` | Original dedicated null gate. Null `resolvable_soc_status=MISMATCH` is expected lack of a signal. |
| `gamma_occupation_diagnostic_status` | Both programs' minimum FD over plan states 3:8 is **>= 0.99999999**, without rounding or tolerance. FD uses each unchanged original SCF global mu and tau. |
| `manifold_prerequisites_status` | Both structures and occupations, split and null, original D full/null residual/Gram, D/Q spectral TR and Q reported solver gate must all pass. Otherwise REVIEW_REQUIRED. |
| `manifold_assignment_status` | MEASURED_PREREQUISITES_PASS only for all measured gates; otherwise MANIFOLD_ASSIGNMENT_REVIEW_REQUIRED. Never an unqualified top-level PASS. |
| `physical_manifold_interpretation` | REVIEW_REQUIRED even if measured prerequisites all pass. No new physical validation. |
| `semantic_validation_status` | Exact source identity, original replay, original numerical contract and new derivation successfully checked. |

Thresholds and indices come from the byte-authenticated [original plan](../../../benchmarks/si-soc-splitting-v1/plan.json).
The new [thin entry](../../../scripts/check_si_soc_status.py) calls the frozen
comparator, including its FD function, and original full-result `close` check.
No new occupation constraint is solved. Each spectral mu is also matched to its
parent SCF record. Missing fields, invalid/nonfinite data, source changes and
numerical replay mismatches are errors, not harmless review flags. Synthetic
prerequisite success does not establish irreps, continuous-path assignment,
physical convergence or an independent native QE nonlocal energy.

Default exit **0** means faithful evidence and status derivation, with review
flags retained. `--require-manifold-pass` returns **1** for known unmet
prerequisites; input/contract/replay errors return **2**. Original checker exits
and streams remain independently recorded, including any failure. No generic
`overall_scientific_PASS` is published.

Public-only reproduction from a checkout of this branch (existing standard
library Python; no installation or private data):

```sh
snapshot=$(mktemp -d)
git worktree add --detach "$snapshot/source" 61cb1c226dcfa8dbeccc63e8f43e33b2790a07c6
(cd "$snapshot/source" && python3 -B scripts/check_si_soc.py)
python3 -B scripts/check_si_soc_status.py --source-root "$snapshot/source"
python3 -B scripts/check_si_soc_status.py --source-root "$snapshot/source" --require-manifold-pass
```

The strict command is expected to return 1 on the saved data; inspect its real
exit instead of suppressing it. The old evidence binds old navigation bytes, so
run the old command **only in that snapshot**. Current navigation and every
historical scientific file are checked separately; no old hash is refreshed.
The snapshot contains only public Git files, without .work/UPF/cache/checkpoints.
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_si_soc*.py'`
runs the affected comparator and synthetic status regressions.

At source preparation, formal evaluations were NOT_RUN. The following results
were obtained only after ordinary source commit
`a03f91f56875a80e5b058fd86377ee0cd9317939` on macOS arm64 / existing Python3.12.14.
The compact [assessment](assessment.json) separates execution from science.

| Actual check | Exit / observation |
| --- | --- |
| Original complete checker, detached61cb1c2 | **0 / PASS** under its old contract; all old fields reproduced. |
| New default semantics | **0 / PASS** for faithful evidence/status derivation. |
| New strict manifold mode | **1 / REVIEW_REQUIRED**, preserved without suppression. |
| Existing comparator / driver protocol / new status tests | **0; 28 + 11 + 21 = 60 Python tests PASS**; synthetic negatives remain rejected inputs. |
| Saved assessment round trip | **0**; complete original derived result unchanged under original replay contract. |
| Clean source-commit clone and separate public JSON | **0**, --check-record; clone stayed clean, no private data or environment installation. |
| Help / missing required source argument | **0 / 2** respectively. |

Both new modes report fixed-window structure, split comparison and spin-trace
control **PASS**. The only unmet measured prerequisites are D and Q occupations:
minimum FD **0.99995952494121 / 0.9999595238092915**, below the unchanged
**0.99999999** threshold. Occupation and complete prerequisites are
**REVIEW_REQUIRED**; assignment is **MANIFOLD_ASSIGNMENT_REVIEW_REQUIRED**.
D/Q splits remain **0.04745761517555575 / 0.04745761244197689 eV**; signed
difference **2.7335788632676383e-9 eV**, null width **1.627601868839064e-12 eV**.
No spectrum/occupation/E/F/warning byte changed. All439 baseline files were
authenticated; only the six named current navigation documents may differ.
Frozen kernels, original comparator/checker/tests and dependency records match
the base exactly. Original physical execution remains3948ed5, not this run.

To verify this compact record after the historical worktree is prepared:

```sh
python3 -B scripts/check_si_soc_status.py --source-root "$snapshot/source" --check-record results/si-soc-splitting/status-correction/assessment.json
```

Physical interpretation remains **REVIEW_REQUIRED**, convergence
**NOT_ESTABLISHED**, irreps **NOT_COMPUTED**, continuous-path assignment and
independent native QE nonlocal energy **NOT_MEASURED**. Historical QE warnings
and IEEE **NOT_LOCALIZED** are unchanged. The initial new-document link check
failed and was corrected before the source commit; no historical hashes or
assertions were weakened. An additional invocation of the older `check_publication.check_frozen` returned
**1** both here and at fixed61cb1c2: its Phase6C frozen list rejects the
Phase8A-approved `common_data.jl` change. This inherited compatibility failure
is retained; that component is **not PASS**. The required original Si complete
checker and this phase's439-file comparison against61cb1c2 pass; no older
checker or hash was rewritten. Complete logs remain outside public results.
`git diff --check` and current
publication/link checks pass. A pre-delivery incremental archive verified **55
files and 6 restored samples**, including the code, new JSON and Git delta
bundle; manifest identity is in assessment.json. It is an external same-machine
backup, **not offsite**. Only this task delta was copied; no old UPF/WFC/raw
array archive was repacked. The final results commit and its clean replay are
recorded in a later delivery increment, without amending this report to name
its own commit.
New SCF, eigen/occupation solves, Julia, QE/pp, XC, projector construction,
parameter scans, CI, upstream suites and IEEE localization are **NOT_RUN**.
No Phase 8B work is authorized. Material AI assistance follows the
[existing disclosure](../../../docs/ai-assistance.md).
