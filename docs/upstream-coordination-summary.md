# SOC workbench coordination summary

Historical scalar Si QE–DFTK baselines and limited cutoff/k-point sensitivity
checks were executed; numerical interpretation remains subject to review.
No-SOC spinor charge-only SCF was tested separately. FR angular/radial projectors
and nonlocal operators passed internal checks; Phase 6B then integrated a full
Hamiltonian and seven-term orbital-energy prototype at fixed density, without SCF.

Phase 6C completed two independent charge-only Mg SOC SCF runs, each with 191
density maps, global capacity-one Fermi–Dirac occupations at tau=0.001 Ha, and
24 target spinor states per explicit k point. Endpoint closure, energy/free-energy,
time-reversal and A/B comparison checks passed their declared engineering
thresholds. These are CPU Float64/ComplexF64 checks of a prescribed periodic
fixture, not physically converged material predictions.
`numerical_review_status=REVIEW_REQUIRED`.

One matching QE 7.5 input is `PREPARED_NOT_EXECUTED`; the QE SOC benchmark remains
`NOT_RUN`. The next scientific gate is the first independent QE SOC comparison of
internal energy E and free energy F. Noncollinear XC is `NOT_IMPLEMENTED`;
upstream native support is `NOT_IMPLEMENTED_BY_THIS_PHASE`.

Material AI assistance: Codex coordinated implementation; parallel agents worked
on numerical kernels, tests, comparison and QE preparation. Specific model
identifiers: **not exposed**. These AI-assisted checks and conversation reviews
are not independent human-expert or maintainer review, or third-party replication.
The repository owner retains responsibility and handles upstream communication;
none was sent by this phase. The current APIs and identity registries are prototypes,
not an accepted upstream architecture.

Reports fixed at the accepted base:
[scalar baseline](https://github.com/xxs4661/dftk-soc-workbench/blob/9ec5ef155ad6c078ad6379a6b32f23b7f27da7eb/results/phase4b-review.md),
[limited sensitivity](https://github.com/xxs4661/dftk-soc-workbench/blob/9ec5ef155ad6c078ad6379a6b32f23b7f27da7eb/results/phase4c-review.md),
[no-SOC SCF](https://github.com/xxs4661/dftk-soc-workbench/blob/9ec5ef155ad6c078ad6379a6b32f23b7f27da7eb/results/phase5b-review.md),
[FR projectors](https://github.com/xxs4661/dftk-soc-workbench/blob/9ec5ef155ad6c078ad6379a6b32f23b7f27da7eb/results/phase6a-review.md),
[full Hamiltonian/energy](https://github.com/xxs4661/dftk-soc-workbench/blob/9ec5ef155ad6c078ad6379a6b32f23b7f27da7eb/results/phase6b-review.md).
[Current Phase 6C report](../results/phase6c-review.md) and
[upstream questions](soc-upstream-risks.md) resolve within this commit's view.
