# Researcher-facing curation candidate

This changes the public reading and usage paths, not the numerical implementation.
The root README and current capability table now describe the completed
experimental workbench directly. Result/input/command navigation is organized by
scientific question. Four short guides connect the real interfaces, conventions,
reproduction scopes and fixed historical snapshots. Human contribution guidance
and agent execution rules are separated; material AI assistance remains disclosed.

Technical base: `e98552ccfb96fb27e07c9816559856d133b58310`.
Candidate branch: `codex/researcher-facing-curation`.
Only the 12 authorized current documents, four new guides, one new read-only
wrapper, its targeted tests and this handoff are in scope. All 666 other existing
files—including numerical code, drivers, old tests, environment/input records,
case reports, results and checkers—retain their exact bytes and paths.

The two researcher entries are:

```sh
python3.12 -B scripts/review.py core-regression
julia --startup-file=no --project=@stdlib examples/soc_kernels.jl
```

The first runs the original strict public checker at the completed historical
snapshot in its own outside-repository copy. The second runs the existing
synthetic matrix example using the current unchanged core. Neither performs a
new material calculation or exposes a general SOC package API.

## Checks actually performed

Clean candidate `48b7e98aa19531e01d9ee63b54fc886413fe1b09` was checked on
macOS arm64, Python 3.12.14 and existing Julia 1.12.7. Its temporary clone had
no private `.work` or UPF and remained clean.

| Command/check | Exit and scope |
| --- | --- |
| `python3.12 -B scripts/review.py core-regression` | **0**; original strict historical checker 0, public records/arithmetic only. Review flags remain visible. |
| `python3.12 -B -m unittest discover -s tests -p 'test_review.py' -v` | **0**, 12 synthetic wrapper tests, including native nonzero propagation, missing history, cleanup, unchanged user branch and failed metadata persistence. |
| `julia --startup-file=no --project=@stdlib examples/soc_kernels.jl` | **0**; unchanged synthetic matrix example. |
| Same Julia options, absolute example path from an unrelated directory | **0**; relative action error 1.3300522788115085e-16 and expectation difference 0.0 in both invocations. |
| Current byte boundary, canonical paths, links/anchors/privacy and `git diff --check` | **0**; all 666 protected files unchanged, 545 local links, 9 local anchors and 21 fixed Git links checked. |
| GitHub exact-candidate HTML | README table and two command blocks, 10 capability rows, and 30 methods math elements verified through the read-only rendering API. |

The initial new-methods link check failed on a nonexistent report path and was
corrected before the candidate. Browser screenshot preview was **BLOCKED** by
a navigation timeout; HTML rendering/structure was checked separately, not
claimed as a screenshot review. Full commands/streams and source facts remain
in local curation logs and the incremental archive. Other historical material
checkers, complete frozen-environment rebuild, upstream suites, SCF, QE/pp,
parameter scans and CI are **NOT_RUN** in this task.

The final delivery commit receives a further clean-clone entry check; its exact
identity and actual exits accompany the delivery without a self-referential hash.

Performance review, incomplete Si occupations/manifold interpretation, DFTK
K6/K8 NOT_RUN, physical convergence NOT_ESTABLISHED and Mg IEEE/native-nonlocal
limitations remain. The historical Linux R failure is preserved alongside I
success. Old whole-tree checkers run at their original snapshots; no old hash is
changed to accommodate these documents.

## Publication handoff

**The default homepage has not been published by this task.** Initial remote
main is `77bd2e151116bcc189b797e6da415d27a61d3a2b`; the technical base is its
descendant. Main-to-base already differs in 497 files, including intervening
scientific implementation and results. This curation changes 19 files relative
to that technical base. A later main-to-candidate merge therefore is not a
documentation-only change. No PR, main push, merge, default-branch change
or upstream communication is authorized here. Final branch identity and remote comparison are recorded at delivery without
amending historical results. The repository-external, same-machine archive
`researcher-curation-archive-20260910T161147Z-95cab0f7` binds the 19 changed files
and an incremental Git bundle. Six restored files (README, agent rules, methods,
environment guide, wrapper and tests) matched their SHA-256 values; the changed-file
manifest is `618cbe052a0a23070010d93ac11dffc2ec64798275fdbf3aa0435052096752fc`.
The final commit/log addendum is separate. No old scientific archive was repacked.
