# Mg QE SOC diagnostics — residuals remain under review

Five prescribed numerical solves and one initialization-only check completed,
with no retries or additional parameter choices. Same-density Davidson/CG raw
spectra satisfy the predeclared stability filter on both grids. The grid+SCF
response changes both E/F and relative spectra, but **numerical agreement remains
REVIEW_REQUIRED**, **physical convergence NOT_ESTABLISHED**, and **IEEE origin
NOT_LOCALIZED**. No DFTK A/B calculation was repeated.

Base: `9d49ca88bfe3c4add0e6c80c1376f006d065e306`. Preparation/execution commit:
`57ccbdc07d4d618f8dcf4135ab4cc28b62b7552f`. This is the development branch
`codex/phase7b-qe-soc-diagnostics`; main is unchanged and no PR is created.

[Evidence and receipts](evidence.json), [canonical native reparse](canonical.json),
[complete comparison summaries](comparison.json), and [all signed differences](differences.csv)
are the public review package. The latter has 22 complete pairs × 72 states =
1584 rows, with raw left/right values and occupations. Every pair has lowest16
and all24 summaries, separately all/occupied/empty, maximum positions and RMS.
Original QE XML/stdout/stderr are linked per slot below; historical Q36, bands,
A and B are referenced from their existing packages, not copied or rebranded.

## Predeclared inputs, execution and source binding

The [plan and exact inputs](../../benchmarks/mg-soc-qe-diagnostics-v1/README.md)
were saved before execution; plan SHA-256:
`5aca5e3351109cfe5a6c59628cd640067952431d91ae5349254d98190bf60712`.
One Mg at (0.17,0.23,0.31), 10 bohr cubic cell, 10 electrons, 24 capacity-one
spinors, Γ/k± each 1/3, PBEsol [1,4,10,8], FR-NC/no NLCC,
30/120 Ry cutoffs and FD tau=0.001 Ha are unchanged. `noncolin/lspinorb`,
charge-only magnetization and all three symmetry/reduction controls are checked.
Mg UPF SHA is `19b117bfa920945bffaee91eefbcfbf9fd44e035f3708b965aae59aabf3be256`.
No input_dft override or fitted energy constant is used.

| Slot | Actual run ID | Action / process exit | Actual hard/smooth | Native files |
| --- | --- | --- | --- | --- |
| I36 | `20260907T111929978454Z-I36-b582abea` | initialization only; numerical NOT_RUN; 0 | 36³ / 36³ | [XML](I36/qe.xml), [stdout](I36/qe.stdout), [stderr](I36/qe.stderr) |
| D36 | `20260907T111948528180Z-D36-3d8fff49` | david bands, same saved density; 0 | 36³ / 36³ | [XML](D36/qe.xml), [stdout](D36/qe.stdout), [stderr](D36/qe.stderr) |
| C36 | `20260907T112027797228Z-C36-09d225c5` | cg bands, same saved density; 0 | 36³ / 36³ | [XML](C36/qe.xml), [stdout](C36/qe.stdout), [stderr](C36/qe.stderr) |
| G40 | `20260907T112107073262Z-G40-3f9731a6` | SCF, 15 iterations; 0 | 40³ / 40³ | [XML](G40/qe.xml), [stdout](G40/qe.stdout), [stderr](G40/qe.stderr) |
| D40 | `20260907T112146269902Z-D40-3e4c90c8` | david bands, same saved density; 0 | 40³ / 40³ | [XML](D40/qe.xml), [stdout](D40/qe.stdout), [stderr](D40/qe.stderr) |
| C40 | `20260907T112203309625Z-C40-80fdb528` | cg bands, same saved density; 0 | 40³ / 40³ | [XML](C40/qe.xml), [stdout](C40/qe.stdout), [stderr](C40/qe.stderr) |

All six execution/input contracts passed; fixed-density bindings passed for
D36/C36/D40/C40. All numerical outputs contain 3×24 finite levels with space
plane-wave counts 2777/2770/2770 matched by k coordinates. Count equality does
not prove G-vector ordering. SCF source, old bands source, all 220 protected
historical public/source files, 86 registered scientific files and the two clean
upstream checkouts were checked before/after each run.

Historical Q36 is `20260907T001853989732Z-c88a8fa3`; historical bands is
`20260907T002225710098Z-bands-1561a3f2`, both **HISTORICAL_REUSED** from the accepted
Phase 7A commit. A/B run IDs and immutable endpoint hashes remain in the
[original SCF evidence](../mg-soc-scf/evidence.json). A is always primary and B
is an auxiliary independently initialized historical reproduction.

The complete original SCF was found in its recorded local run and independently
in the Phase 7A external archive. Its 19 files and the old bands' 21 files match
raw manifest SHA `097bd3c9539eb9ec5c35525e4243f1772dcda229e9b2de836c8fe3e955edb671`.
All 19 original SCF files were physically restored to a new temporary directory
and hash checked before execution. Old bands wavefunctions differ from the SCF;
they were never used to seed D36/C36. Each pair received ordinary independent
copies of its source charge/wfc/XML, with unequal source/worker inodes. Original
source and worker charge hashes remained unchanged. G40 used fresh scratch;
D40/C40 used its one pinned post-SCF snapshot. The six required .save file hashes
and per-slot copy receipts are public; the large payloads remain local. These
receipts support runner-reported byte binding, not public revalidation of arrays.

Within each D/C pair, only diagonalization and the algorithm-specific control
field differ. All bands actions explicitly read file potential and wavefunctions,
with no atomic/random fallback and no new charge-SCF loop. Both use 1e-13 Ry,
full empty-state accuracy; Davidson ndim=2, CG maxiter=200. G40 adds only six FFT
dimensions to the original SCF input, whose initial threshold is 1e-10 Ry,
mixing 0.1, conv_thr 1e-10 Ry and maximum steps 400. Prefix and inherited comment
remain identical to 7A; independent run directories supply the new identifiers.
Complete text differences are reproducible from the frozen old input and the
strict generator, rather than unspecified overrides.

XML/native stdout agree on the real solver (`davidson`/`cg`) and reported
threshold. QE serializes input `diago_thr_init` in Ry while `conv_thr` is in Ha;
no factor-two guess is used. The writer does not expose Davidson ndim, so that
field is input-hash verified, not claimed as a separately measured native value.
[QE 7.5 control serialization](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/pw_init_qexsd_input.f90#L477-L486)
and [electron-control fields](https://github.com/QEF/q-e/blob/qe-7.5/Modules/qexsd_input.f90#L226-L255)
provide these conventions.

All processes used the same existing binary SHA
`0500a3db2fc668d4e558d6e667522fbd62793bdf87631776e6b0c4bc3c4e50f0`, launcher and
JLL runner as 7A: PWSCF 7.5, JLL 7.5.1+0, MPI one process/node, each recorded thread
limit one. Before/after probes ran the actual JLL launch environment in fresh
Julia 1.12.7 processes. The 19 library hashes plus QE global Project/Manifest
hashes are a **new Phase 7B baseline** checked through this matrix; 7A did not
publish old per-library hashes, so historical byte identity at that finer level
cannot be independently asserted. The actual QE child dyld load path and the
exact build source commit were not separately traced. No dependency changed.

## Same-density solver observations

Signed differences use left minus right. RMS is unweighted over selected k/band
entries; occupied means left f≥0.5, with opposite classifications recorded too.
Same-density comparisons use **raw spectra only**, with no reference shift.
The ≤1e-7 Ha/no-unconverged-warning rule was fixed before running.

| Pair | States/k | Group | Raw max (Ha) | RMS (Ha) | Maximum location in left record |
| --- | ---: | --- | ---: | ---: | --- |
| D36_minus_C36 | 16 | all | 1.51811896387e-12 | 4.39175334931e-13 | [0.0, 0.0, 0.0], band 7, f=1 |
| D36_minus_C36 | 16 | occupied | 1.51811896387e-12 | 5.47645179852e-13 | [0.0, 0.0, 0.0], band 7, f=1 |
| D36_minus_C36 | 16 | empty | 2.96151991819e-13 | 1.20310131765e-13 | [0.0, 0.0, 0.0], band 11, f=1.777e-57 |
| D36_minus_C36 | 24 | all | 8.52728998524e-12 | 1.08992652849e-12 | [0.0, 0.0, 0.0], band 24, f=0 |
| D36_minus_C36 | 24 | occupied | 1.51811896387e-12 | 5.47645179852e-13 | [0.0, 0.0, 0.0], band 7, f=1 |
| D36_minus_C36 | 24 | empty | 8.52728998524e-12 | 1.34990485565e-12 | [0.0, 0.0, 0.0], band 24, f=0 |
| D40_minus_C40 | 16 | all | 2.76464268145e-12 | 6.96464065415e-13 | [0.0, 0.0, 0.0], band 15, f=1.094e-57 |
| D40_minus_C40 | 16 | occupied | 9.99200722163e-14 | 3.62057651954e-14 | [0.0, 0.0, 0.0], band 8, f=1 |
| D40_minus_C40 | 16 | empty | 2.76464268145e-12 | 1.13636016417e-12 | [0.0, 0.0, 0.0], band 15, f=1.094e-57 |
| D40_minus_C40 | 24 | all | 3.68949315543e-12 | 1.02964848088e-12 | [0.0, 0.0, 0.0], band 22, f=7.214e-76 |
| D40_minus_C40 | 24 | occupied | 9.99200722163e-14 | 3.62057651954e-14 | [0.0, 0.0, 0.0], band 8, f=1 |
| D40_minus_C40 | 24 | empty | 3.68949315543e-12 | 1.34777900069e-12 | [0.0, 0.0, 0.0], band 22, f=7.214e-76 |

Both grids have **CROSS_SOLVER_STABILITY_OBSERVED**. This is tested sensitivity
within the same QE operator and potential, not independent physics or a measured
`||Hψ−εψ||` bound. Per-state residuals are **NOT_AVAILABLE**; ethr, SCF error and
D/C differences do not replace them.

| Raw same-density change | All24 max (Ha) | RMS (Ha) | Max (meV) |
| --- | ---: | ---: | ---: |
| D36_minus_Q36 | 8.15899761669e-07 | 3.60631574376e-07 | 0.0222017635528 |
| C36_minus_Q36 | 8.15899816473e-07 | 3.60631559302e-07 | 0.0222017650441 |
| D36_minus_old_bands | 1.70822189727e-10 | 2.19456173755e-11 | 4.64830858404e-06 |
| C36_minus_old_bands | 1.79349479712e-10 | 2.29589172019e-11 | 4.88034796546e-06 |
| D40_minus_G40 | 1.89692471197e-06 | 1.2424022296e-06 | 0.0516179510171 |
| C40_minus_G40 | 1.89692471197e-06 | 1.24240223677e-06 | 0.0516179510171 |

The original SCF spectra are retained even where their fixed-density bands change
is larger than D/C disagreement. G40 SCF converged in 15 iterations with estimated SCF energy
accuracy 7.098161073690468e-12 Ha (not a charge-density norm), but its last SCF diagonalization still reports two
unconverged eigenvalues at 1.11e-12 Ry. All 11 native unconverged messages remain
public. D40/C40 use the predeclared stricter 1e-13 Ry and supply no E/F.

## E/F and the one grid control

All values below are Ha/cell unless stated; the cell has one atom. Native QE
F=etot, −TS=demet and E=F−demet; no zero-temperature extrapolation or correction
is added. Native XML and stdout tokens are retained. QE printed zero is a finite
precision representation, not a mathematical zero claim.

| Source | E | F | −TS |
| --- | ---: | ---: | ---: |
| A | -57.325987985147734 | -57.325987985147734 | -1.2426050669902276e-37 |
| B | -57.325987985147727 | -57.325987985147727 | -1.2426050665736325e-37 |
| Q36 | -57.326027947863388 | -57.326027947863388 | 0 |
| G40 | -57.326010932925413 | -57.326010932925413 | 0 |

| Signed difference (E and F identical at printed precision) | Ha/cell | meV/cell | μeV/cell |
| --- | ---: | ---: | ---: |
| A_minus_Q36 | +3.9962715653985e-05 | +1.0874408911 | +1087.4408911 |
| B_minus_Q36 | +3.99627156610904e-05 | +1.08744089129 | +1087.44089129 |
| A_minus_G40 | +2.29477776798603e-05 | +0.624440841934 | +624.440841934 |
| B_minus_G40 | +2.29477776869658e-05 | +0.624440842127 | +624.440842127 |
| G40_minus_Q36 | +1.70149379741247e-05 | +0.463000049165 | +463.000049165 |

The E/F change of +0.463000049165 meV reduces the A−QE difference from
+1.087440891099 to +0.624440841934 meV. A/B cross-grid bookkeeping identities
have zero arithmetic residual; this is an algebra check, not a causal error
budget. Native entropy differences and unit conversions to eV/meV/μeV are in
the comparison JSON. Only formally matching Hartree, XC and Ewald terms are mapped:

| Term | A−Q36 (Ha) | A−G40 (Ha) | G40−Q36 (Ha) |
| --- | ---: | ---: | ---: |
| Hartree | +8.68744324087345e-05 | -5.96704343180932e-06 | +9.28414758405438e-05 |
| Xc | +1.89556536236424e-05 | +2.64708180086615e-06 | +1.63085718227762e-05 |
| Ewald | +1.84041049067218e-08 | +1.84041049067218e-08 | +0 |

B and all conversion fields are preserved too. The XML partial combination
`eband−ehart−vtxc+etxc+ewald+demet` is not imposed as a complete same-density energy
identity. Its retained F-minus-partial difference is −3.692822836854e-6 Ha for
Q36 and +1.627159322481e-5 Ha for G40; no energy field is patched.

## Cross-program spectra and grid sensitivity

Every k point is uniquely matched modulo reciprocal integer vectors. For each
engine, one global sampled HOMO is used only if all occupations satisfy the
unchanged 1e-8 saturation criterion. All actual endpoints meet it. Raw values,
reference values and unused bands remain available. No per-k/per-band shift,
least-squares fit, selection between A/B or assembly of a best spectrum occurs.

A−QE maxima/RMS below are meV. Full B tables, lowest16/all24 occupied/empty groups,
and every maximum's k, band and occupation are in the canonical summaries.

| QE result | States/k | Raw max / RMS | Global-reference max / RMS | C-diagnostic max |
| --- | ---: | ---: | ---: | ---: |
| Q36 | 16 | 250.032892 / 249.762562 | 0.655984475 / 0.350342229 | 0.627554161 |
| Q36 | 24 | 250.032892 / 249.817051 | 0.655984475 / 0.295821866 | 0.627554161 |
| D36 | 16 | 250.035769 / 249.757957 | 0.670382551 / 0.360391095 | 0.639076003 |
| D36 | 24 | 250.035769 / 249.816523 | 0.670382551 / 0.303402594 | 0.639076003 |
| C36 | 16 | 250.035769 / 249.757957 | 0.670382554 / 0.360391095 | 0.639076005 |
| C36 | 24 | 250.035769 / 249.816523 | 0.670382554 / 0.303402597 | 0.639076005 |
| G40 | 16 | 249.94311 / 249.922501 | 0.0314711484 / 0.0220076637 | 0.0992402877 |
| G40 | 24 | 249.948681 / 249.926789 | 0.0314711484 / 0.018809595 | 0.0992402877 |
| D40 | 16 | 249.957106 / 249.956336 | 0.00207443025 / 0.00142114346 | 0.049430633 |
| D40 | 24 | 249.960021 / 249.956343 | 0.0049891074 / 0.00185926039 | 0.0509669532 |
| C40 | 16 | 249.957106 / 249.956336 | 0.00207443061 / 0.00142114375 | 0.0494306329 |
| C40 | 24 | 249.960021 / 249.956343 | 0.00498911008 / 0.00185925973 | 0.0509668556 |

The all24 referenced A−QE maximum is 0.655984475 meV for Q36, 0.670382551 meV
for D36, 0.0314711484 meV for G40 SCF and 0.00498910740 meV for D40.
The D36 refinement slightly increases the old SCF referenced maximum; this is
retained. For 40³ fixed-density bands, the all24 maximum lies at Γ, **empty band17**;
its occupied maximum is about 6.65e-8 Ha at k± band2. For Q36 and G40 SCF, the
largest referenced differences involve occupied states. Thus no occupied-only
or empty-only subset is substituted for the full table.

Mg's existing C=PspCorrection/10=0.009187494522099392 Ha remains an independent,
non-fitted diagnostic: raw(DFTK−QE)+C. It is consistent with the approximate common offset
scale; that origin was not directly verified and the remaining residual is unexplained. The actual QE internal G=0 value was not extracted.
C is never added to E/F and never replaces a saved eigenvalue.

| Same-method 40³−36³ spectrum | Raw all24 max/RMS (Ha) | Global max/RMS (Ha) | Global max (meV) |
| --- | ---: | ---: | ---: |
| D40_minus_D36 | 2.1723910292e-05 / 9.26541129196e-06 | 2.46909469941e-05 / 1.11875515726e-05 | 0.671874895435 |
| C40_minus_C36 | 2.1723910385e-05 / 9.26541144002e-06 | 2.46909470896e-05 / 1.11875517341e-05 | 0.671874898033 |

These two grids measure FFT plus self-consistent density response. They do not
isolate a quadrature, radial/nonlocal projector or SOC error, establish physical
cutoff/k/temperature convergence, or prove identical discrete Hamiltonians even
when both programs use 40³. Signs and cancellations forbid interpreting the
smaller differences as elimination of a particular implementation error.

## Native warning matrix and limits of attribution

`R` means reported in that run's native stderr; `NR` means not reported, not
proven absent. Every process exit was 0. The matrix includes all historical and
new sources; per-stream native line numbers/text are in comparison JSON.

| Run | Numerical convergence / c_bands warning | invalid | divide-by-zero | overflow | underflow | inexact |
| --- | --- | --- | --- | --- | --- | --- |
| I36 | NOT_RUN initialization; none | NR | NR | R | NR | NR |
| Q36 | SCF converged; unconverged eigenvalue warnings | R | R | R | NR | NR |
| old_bands | bands completed; no unconverged warning | R | R | R | NR | NR |
| D36 | bands completed; no unconverged warning | R | R | R | NR | NR |
| C36 | bands completed; no unconverged warning | NR | NR | R | NR | NR |
| G40 | SCF converged; unconverged eigenvalue warnings | R | R | R | NR | NR |
| D40 | bands completed; no unconverged warning | R | R | R | NR | NR |
| C40 | bands completed; no unconverged warning | NR | NR | R | NR | NR |

I36 actually wrote config-init XML status 255/nstep0 while the process returned
0; it did not enter SCF or full bands. Both 36³ grids are read from actual XML,
with the printed dense grid corroborating it. QE's timing section headings such
as “Called by c_bands” are not evidence that an eigensolve occurred. The
[fixed initialization branch](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/run_pwscf.f90#L139-L159)
and [build-dependent termination mapping](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/stop_run.f90#L54-L92)
explain the two status levels.

Observed: I36/CG report overflow only; Davidson and the SCFs additionally report
invalid/divide-by-zero. Scope narrowing: overflow can be reported without the
full SCF or eigensolver path. This does not locate the operation or explain the
other two flags. The solver-dependent display pattern is a clue, not proof of a
Davidson defect or CG correctness. The source-level scope is the audited setup/pre_init/data_structure/summary/
memory_report branch; no particular floating-point expression was isolated.
Shared library and later solver paths remain unexcluded, without an operation-level
stack or isolation experiment. No such runtime localization
was performed. [GNU Fortran's termination summary](https://gcc.gnu.org/onlinedocs/gfortran/Debugging-Options.html)
can print accumulated flags and does not establish when they arose.

`warning_origin_status=NOT_LOCALIZED`; `residual_attribution_status=NOT_ESTABLISHED`.
No flags were cleared or suppressed, no compiler option was treated as a runtime
switch, and no preload/rebuild/debugger/system-permission workaround was used.
Normal exits, finite arrays, matching grids and D/C agreement remain separate
from the unresolved IEEE quality concern.

## Verification, evidence boundary and stopping point

Run the new and unchanged old offline checks with their recorded interpreters:

```sh
python3.12 scripts/check_qe_soc_diagnostics.py --all --legacy-python python3.9
python3.12 -m unittest discover -s tests -p 'test_qe_soc_*.py' -v
python3.12 -m unittest discover -s tests -p test_publication.py -v
git diff --check
```

The six actual runner commands are `python3.12 scripts/run_qe_soc_diagnostics.py
I36` followed by D36, C36, G40, D40 and C40, sequentially. All recorder and process
exits were 0. Input/source hashes and UTC preflight/start/end times are bound per
slot. Normal permission review was used for the existing MPI launcher; no sandbox
failure or numerical retry occurred in this matrix.

Before execution, 66 directed tests plus old public replay passed. Final affected
tests: **175 SOC tests (96 original + 79 diagnostics) and 23 publication tests,
198 distinct test methods passed**, all commands exited 0. Python 3.12.14 was
used for these tests/new arithmetic and Python 3.9.6 for the unchanged historical
scalar replay. A separate public-only clone passed the combined checker without
.work, UPF, Julia, QE or private archive. Exact commands/exits/log hashes and
the clean-copy receipt are in
[evidence](evidence.json). Synthetic metadata/output mutations test protocol
rejection; they are not pseudopotential calculations. Pre-execution test-fixture
and integration failures are retained in the local process archive, never counted
as passing runs. No failed scientific slot was omitted.

The frozen 7A parser, comparator, runner and publication checker remain byte
identical. A new wrapper calls the old checks unchanged under Python 3.9 and the
new adapter under Python 3.12. Two post-execution recording fixes exclude c_bands
profiling headings from warnings and read I36's available smooth-grid XML. The
original parser results and preparation code remain archived, and all original
numerical fields and true warning flags match the new reparse exactly. Historical
hashes and scientific tolerances were not refreshed. The final local preparation
interface also rejects a missing library/environment baseline; the actual six runs
already had all 21 hashes checked before and after execution. No new solve was
needed for this prerequisite guard.

New raw data: 138 files, 64,866,703 bytes, copied and hash checked in the
repository-external local archive `phase7b-20260907T111422Z`. Its raw manifest SHA
is `70a3235baa0a7361ac7fe57fa6b76ff795670c3f6a91b472156d3a6a10d3a2e4`.
Forty actual sampled files (14,250,165 bytes), spanning every new run's streams,
XML/receipts and numerical source charge/wfc, were restored and checked in a
separate temporary directory. This is same-machine storage, **not offsite backup**.
The old archives were untouched. Public/native file hashes are separate; stdout
only has trailing spaces/tabs trimmed, with no lines or warnings removed. Small
complete I36 XML/stdout retain verifiable initialization context, while all .save,
UPF, density/wfc arrays and full process/source-audit logs stay local/archived.

NOT_RUN: new DFTK A/B, Julia/upstream numerical suites; cross-program density or
wavefunction-array comparisons; runtime IEEE localization; new grids, solver
thresholds, materials or physical convergence scans; further SOC/spinor work.
Per-state native residuals and exact installed QE source commit remain unavailable.
No required numerical slot is BLOCKED; no computational failure or retry occurred.

The controls narrow the tested eigensolver sensitivity and measure a grid+SCF
response, but do not close the residual budget. The single recommended next step,
subject to separate review, is to read the **existing** A40/G40 charge Fourier
coefficients, verify normalization/units and actual G lists independently, then
compare only exactly common nonzero G components. No interpolation, new SCF,
potential transfer or hybrid Hamiltonian is implied. That would measure the
remaining density/electrostatic difference before attributing it to radial or
SOC-projector implementation. It is **NOT_RUN** here. Work stops for review.
