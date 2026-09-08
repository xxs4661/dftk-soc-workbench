# Phase 8B: finite Si SOC parameter sensitivity

PREDECLARED_NOT_EXECUTED. Three independent changes relative to historical
[Si B0](../si-soc-splitting-v1/README.md); B0 is not rerun. The immutable
[plan](plan.json), [complete difference table](allowed-differences.json) and
[replay contract](replay-contract.json) precede every new numerical slot.

| Profile | D cutoff Ha / QE wfc,rho Ry | SCF points | tau Ha | Fixed-density probes |
| --- | --- | --- | --- | --- |
| [E40](E40/case.json) | 40 / 80,320 | 8 | 0.001 | Gamma only, 24 spinors |
| [T05](T05/case.json) | 30 / 60,240 | 8 | 0.0005 | Gamma only, 24 spinors |
| [K4](K4/case.json) | 30 / 60,240 | 64 | 0.001 | Gamma only, 24 spinors |

All use the unchanged [source](../si-soc-splitting-v1/source.json): two-atom Si,
a=10.26 bohr, FR NC-PBE with NLCC/s/p/d, Ne8, 48cubed FFT, capacity-one FD.
QE inputs are [E40 SCF](E40/qe-scf.in)/[Gamma](E40/qe-gamma.in),
[T05 SCF](T05/qe-scf.in)/[Gamma](T05/qe-gamma.in),
[K4 SCF](K4/qe-scf.in)/[Gamma](K4/qe-gamma.in).
All hard/smooth dimensions are explicit. The [QE parameter reference](https://www.quantum-espresso.org/Doc/INPUT_PW.html)
confirms Ry input cutoff/degauss units and density/potential meaning of ecutrho;
actual frozen binary output must still match. E40 changes both spherical
cutoffs at fixed ratio and FFT, not wavefunction cutoff alone.

All three source/basis/G-difference/memory preflights must pass first. Then run
E40, T05, K4 serially; within each: D-SCF, Q-SCF, D-GAMMA, Q-GAMMA, once each.
SCF starts from its own uniform/atomic state, never from another case. Gamma
reads only its own successful parent's final density and inherited global mu.
No Gamma electron-count root or new null/p-minus-p task is permitted.

For each program, Delta is mean(states5:8)-mean(states3:4). Code gaps and the
two independently calculated responses relative to B0 are distinct from the
per-program 0.1meV finite-step observation window. Exceeding that window can
coexist with matching program responses. Structure failures preserve fixed-index
algebra but are WINDOW_ONLY_NOT_IDENTIFIED; no band-window selection or fit.
Occupation uses the unchanged 0.99999999 diagnostic at actual case tau/mu.
Physical interpretation remains REVIEW_REQUIRED, convergence NOT_ESTABLISHED.

Only the six old code files listed in plan.json may change. The two SOC core
files are restricted to explicit settings-contract validation/forwarding;
formulas, solvers and old defaults stay fixed. Original checkers run in their
61cb1c2/bc68aaf historical worktrees, not in this evolving tree. Source/plan,
execution and results will be separate ordinary commits.

[Current result entry](../../results/si-soc-sensitivity/README.md) will retain
actual exits, warnings and missing slots. Raw save/checkpoints stay ignored and
in verified incremental same-machine external backups; no UPF is published.
