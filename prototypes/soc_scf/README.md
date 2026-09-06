# Phase 6C restricted charge-only SOC SCF

This workbench prototype joins the Phase 6B FR Hamiltonian to the existing
Phase 5B density-map controller. The controller's optional electron count now
accepts the actual Mg header count; its historical default remains eight.
The FR context accepts an explicit positive temperature and FermiDirac
smearing; its default is still zero temperature with no smearing.

The six common terms have no native Entropy. The seventh internal-energy term
is the FR nonlocal contribution. `ensemble.jl` supplies one global,
capacity-one weighted Fermi root and adds physical-spinor entropy exactly
once. No scalar occupations, native capacity-two entropy, density
renormalization, or magnetization clearing is used.

`phase6c.toml` fixes the Mg input, tau=0.001 Ha, seeds, 24+6 initial state
counts, 24→32→40→48 target expansion, alpha=0.1, 400-map budget (including
closure), and all numerical gates before testing. Auxiliary states never enter
occupations or energy. New expansion columns are orthogonal random directions.
Every closure candidate receives another actual solve at its output density.

Run in a fresh process with the frozen `environment/workbench` project:

```
julia --startup-file=no --project=environment/workbench tests/soc_scf/runtests.jl .work/NEW_TEST_RUN
julia --startup-file=no --project=environment/workbench scripts/run_soc_scf.jl A .work/NEW_A_RUN
julia --startup-file=no --project=environment/workbench scripts/run_soc_scf.jl B .work/NEW_B_RUN
```

Use the existing frozen package cache and one Julia/BLAS/FFT/MPI process/thread.
A and B run sequentially with independent initial states; never initialize B
from A or from historical orbitals. Existing output directories are refused.
Each completed map records its input/output/next hashes and diagnostics. Raw
array checkpoints stay under `.work`; they contain no serialized context or
identity tokens. This phase implements no automatic recovery: an interrupted
run requires explicit source/input/config verification and fresh context
reconstruction before any future array-based recovery.

Seven-term E is evaluated at the returned physical X/f/n_out. Formal f comes
from the solved H[n_in]; own-density H[n_out] residuals and the Rayleigh-based
occupation recalculation are separate closure diagnostics. Energy, entropy,
and free energy are never mixed across densities. The endpoint TR action uses
H[n_out]; closure eigenvalues retain their H[n_in] provenance.

This is not noncollinear magnetic XC, an upstream-ready API, a convergence
study, or independent QE validation. See the Phase 6C report for actual run
statuses, including any failures. The next scientific gate is independent QE
SOC comparison; preparing an input does not execute it.

The [curated Mg evidence](../../results/mg-soc-scf/README.md) retains both
191-map histories, complete target spectra and state residuals. Its documented
Python standard-library check recomputes public energy and spectral arithmetic
without loading Julia or private checkpoints. Density and orbital-dependent
quantities remain explicitly identified as original runner measurements.
