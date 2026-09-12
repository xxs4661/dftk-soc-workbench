# Si owned-core validation extension

This experiment tests the completed core at a larger Si k grid. It preserves the
published 9A completion and all historical evidence. The [plan](plan.json) fixes
inputs, the single-candidate performance screen, conditional slots, resource
policy and numerical contracts before measurements. [Sources](sources.json)
bind the baseline and historical inputs; B0/K6 have distinct extra case identities.

The pilot is real electronic-structure work (at most two full density maps),
not a converged SCF. Formal K6 starts independently and remains conditional on
both engineering memory estimates below 8 GiB with continuous sampled monitoring.
No DFTK K8, new QE, CI or upstream contact is authorized by this experiment.

The [core decision](decision.json) retains the completed implementation after
the bounded B0/K4 profiling. The extra callback retains diagnostic records for
resource accounting, so a new B0/own-density Gamma regression is required before
K6. This does not change the SCF map, solver, occupations or physical formulas.
The [resource policy](resource-policy.md) distinguishes estimates, sampled RSS
and a two-map pilot from formal convergence. Every physical run requires its own
new contract and nonrepeatable slot; the historical gates remain unchanged.

Public evidence is linked from [the result page](../../results/soc-extra/README.md).
Its arithmetic entry is `python3.12 -B benchmarks/soc-extra-v1/replay.py`.
Default exit 0 means the published records replay consistently; it can coexist
with unrun slots or scientific review requirements. `--require-k6` additionally
requires the completed K6 pair and both predeclared splitting screens.
