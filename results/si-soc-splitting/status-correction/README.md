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

Preparation status: formal historical replay, default/strict assessment and
clean-checkout verification **NOT_RUN** at this source-preparation step.
New SCF, eigen/occupation solves, Julia, QE/pp, XC, projector construction,
parameter scans, CI, upstream suites and IEEE localization are **NOT_RUN**.
No Phase 8B work is authorized. Material AI assistance follows the
[existing disclosure](../../../docs/ai-assistance.md).
