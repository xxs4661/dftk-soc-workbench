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

Checks completed before the candidate commit: 12 targeted synthetic wrapper
regressions passed. Exact source boundaries, 545 local links, nine local anchors,
21 fixed Git links, canonical filename case, privacy and Markdown structure
checks passed. Clean-candidate public replay and current/cross-directory Julia
example execution are **PENDING** at this drafting step. Full commands and raw process output remain in local
curation logs; the final delivery will report actual exits separately from
scientific statuses. No SCF, QE/pp, parameter scan, CI or upstream suite is run.

Performance review, incomplete Si occupations/manifold interpretation, DFTK
K6/K8 NOT_RUN, physical convergence NOT_ESTABLISHED and Mg IEEE/native-nonlocal
limitations remain. The historical Linux R failure is preserved alongside I
success. Old whole-tree checkers run at their original snapshots; no old hash is
changed to accommodate these documents.

## Publication handoff

**The default homepage has not been published by this task.** Initial remote
main is `77bd2e151116bcc189b797e6da415d27a61d3a2b`; the technical base is its
descendant. This branch is a review candidate. Merging it later would also bring
in the intervening scientific implementation and results, so main-to-candidate
is not a documentation-only diff. No PR, main push, merge, default-branch change
or upstream communication is authorized here. Final branch identity, incremental
backup/restore and remote comparison are recorded at delivery without amending
historical results.
