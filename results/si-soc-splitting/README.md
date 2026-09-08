# Phase 8A — Si SOC splitting and fixed-density control

[Current version 2 status and replay](status-correction/README.md) qualify the
old structural machine field: occupation and full manifold prerequisites remain
REVIEW_REQUIRED. The numerical report below is historical and unchanged.

**Five prescribed numerical slots executed once, all worker/recorder exits 0.**
The fixed-window splitting comparison and spin-trace control meet the predeclared
engineering gates. **Scientific and physical manifold interpretation remain
REVIEW_REQUIRED**: the extra predeclared Γ occupation saturation diagnostic is
not met, QE SCF eigensolver warnings and IEEE flags remain, and physical
convergence and space-group representation labels have not been established.
No parameter retry, extra SCF, material or convergence scan was run.

Accepted base `9342a5ea21a76acd0d74d228d4a2081394f702d0`; branch
`codex/phase8a-si-soc-splitting`. Source/plan/input preparation was committed as
`e5b940c7fb0234d4cb97572ee3f8225e9e8b6087`, followed by the tested execution
commit `3948ed5d37660fe1e909aa6d12983234e317a479`. All formal slots and the
five-density static check used this exact clean execution commit. Source identity
and geometry enumeration preceded it; static NLCC ran after that commit and
before either SCF. The plan's listed order placed static before the execution commit; the actual
wrapper required the execution commit first for identity binding. Static still
passed before any formal SCF. This ordering discrepancy is retained.

The [source and fixed inputs](../../benchmarks/si-soc-splitting-v1/README.md),
[plan](../../benchmarks/si-soc-splitting-v1/plan.json) and
[replay contract](../../benchmarks/si-soc-splitting-v1/replay-contract.json)
remain exactly as prepared. [Evidence](evidence.json) binds commands, code,
source/output hashes and status; [comparison](comparison.json) is canonical.

The official PseudoDojo FR-PBE source is `Si/Si_r.upf` at commit
`7aa01a3fcf5ad226caf25bd387a9be9612be9f27`, 291215 bytes, Git blob
`0bba6c59d28251b59bf831079a340f7147308611`, actual SHA-256
`cc91a6be43c3c89daf6c34410096e8d870f25152dbfb513bcf01afa5ab53eabf`.
Both programs rechecked these same full bytes. No UPF is redistributed.
The [complete parsing attestation](D-source-attestation.json) records NC/full,
PBE, valence 4, nonzero NLCC and all ten beta records: two radial projectors each
for s1/2, p1/2, p3/2, d3/2 and d5/2. Actual labels produce 36 columns per atom,
72 for two atoms. This covers real d channels and two-atom phases, unlike a
single-atom Mg case or synthetic d fixture. The Γ split-off is directly
identifiable; individual bands are not assigned exact atomic j or Γ7/Γ8 labels.

Geometry is the fixed diamond primitive cell at a=10.26 bohr, volume 270.011394
bohr³, positions (0,0,0)/(1/4,1/4,1/4), 8 valence electrons. Both use PBE,
NLCC, 30 Ha/60 Ry, QE ecutrho=240 Ry, explicit 48³ hard/smooth FFT, the eight
{0,−1/2}³ SCF points, capacity-one spinors, 24 target states, and FD τ=0.001 Ha.
The six D auxiliary states never enter density/FD/energy. D SCF plane-wave counts
are 2085/2120/2120/2100/2120/2100/2100/2120; probe counts are 2085/2104/2104.
Actual same-k G−G′ extrema are at most 17, strictly below Nyquist 24. Estimated
peak 3.16 GiB and observed D-SCF peak 2.21 GiB meet the 8 GiB bound.

| Slot | Outer run_id | Result / scope |
| --- | --- | --- |
| D-SCF | D-SCF-20260908T1420Z | PASS/0; 180 maps, map179 candidate then actual map180 closure |
| Q-SCF | Q-SCF-20260908T145232Z | PASS/0; 12 SCF steps; eigensolver interpretation REVIEW_REQUIRED |
| D-SPECTRUM | D-SPECTRUM-20260908T145347Z | PASS/0; Γ,p,−p, each24 states on final D n_out |
| Q-SPECTRUM | Q-SPECTRUM-20260908T145443Z | PASS/0; CG, Γ,p,−p, each24 states on own saved charge |
| D-NULL-GAMMA | D-NULL-GAMMA-20260908T145524Z | PASS/0; Γ24 states on the same D n_out, no SCF |

D numerical run IDs append `-dftk` to the outer ID. All tasks ran serially on
macOS arm64, Julia/BLAS/FFT/MPI threads/processes1. The [platform](platform.json),
D environment reference and [QE identity](Q-environment.json) record actual
loaded code/build hashes. Julia1.12.7, DFTK0.8.0 and PPIO0.3.3 remain pinned;
no source lock, Project/Manifest, upstream checkout or QE build was changed.

[D-SCF](D-SCF.json) and [all180 compact maps](D-trace.json) retain all24×8
formal eigenvalues/occupations and final explicit residuals. The formal spectrum
solves H[n_in]; orbital density/energy and the own-density residual use n_out.
D-SPECTRUM and null independently solve H[n_out], never copy the SCF spectrum.
The final unmixed L2 is 1.2515614163e-9; max input-H residual 9.9510615841e-11 Ha,
own-density old-eigenvalue residual 4.5553787807e-9 Ha, Gram1.5086312333e-14,
Pauli density ratio1.2121562777e-12; valence Ne=8.00000000000094.
The FD stationarity check actually evaluates18 partially occupied states,
max8.9928064995e-15 Ha; 174 endpoint states are excluded as declared.
Maximum top-two occupation5.0674034338e-173, double-counting difference
8.8817841970e-15 Ha and seven-term sum difference0 also pass.
No density, magnetization or occupation was clipped, filled or symmetrized.

[Q-SCF XML](Q-SCF/qe.xml), [stdout](Q-SCF/qe.stdout),
[stderr](Q-SCF/qe.stderr) and [parsed record](Q-SCF/qe-result.json)
retain all12 iterations, actual threshold changes, PBE/NLCC, domag=false and
zero magnetization. Ne=8.000000000036541; final reported SCF error
4.4720295716e-14 Ha. Twelve `c_bands` warning lines occurred in iterations
1/7/9/10. The [bands output](Q-SPECTRUM/qe.stdout) uses actual CG threshold
1e-13 Ry with no unconverged-target warning; this is not an explicit WFC residual.
Both QE tasks reported IEEE_INVALID_FLAG, IEEE_DIVIDE_BY_ZERO and
IEEE_OVERFLOW_FLAG in stderr: **NOT_LOCALIZED**. No new IEEE investigation ran.
The original SCF's eleven saved files and both receipts remain unchanged;
all files were copied without aliasing, and the original/copy charge SHA is
`3c6841bed3f23b45b421a966c449bbeae859a27293d4adb020f5d4ed19068630`.

| Γ quantity | D full SOC | QE full SOC |
| --- | ---: | ---: |
| mean(states3:4), Ha | 0.16990973629655645 | 0.23914107196982198 |
| mean(states5:8), Ha | 0.17165377148633165 | 0.24088510705914 |
| Δ_SO, meV | 47.457615175556 | 47.457612441977 |
| doublet width, eV | 3.9273919805e-14 | 1.3894659666e-11 |
| quartet width, eV | 9.7958219206e-13 | 5.5882467751e-9 |
| lower/upper isolation, eV | 11.994618315 / 2.394899371 | 11.994618486 / 2.394899188 |
| all-probe Kramers max, Ha | 5.6621374256e-15 | 1.2372058933e-10 |
| sorted p/−p max, Ha | 4.3298697960e-15 | 2.4799606813e-13 |

Signed D−Q splitting difference is **2.7335788633e-9 eV**, below the predeclared
1e-4 eV gate. Full 24-state [D](D-spectrum.json), [Q](Q-spectrum.json) and
[null](D-null.json) spectra are retained. This finite-case agreement is not an
experimental accuracy or universal SOC claim. Raw D−Q levels span
−0.069231352063 to −0.069231295385 Ha. After each program's single Γ quartet
reference, maximum differences at Γ/p/−p are 1.093554908e-6/8.523906965e-7/
8.523913732e-7 eV (RMS4.897415412e-7/3.995951131e-7/3.995951335e-7 eV).
No per-k/band fit or experimental target enters these statistics.

The structural fixed-window isolation and 2+4 tests pass. However, minimum
Γ3:8 diagnostic occupations are D0.99995952494121 and Q0.9999595238092915,
below the additional predeclared 0.99999999 saturation criterion:
**gamma_occupation_diagnostic_status=REVIEW_REQUIRED**. That extra conservative
criterion was not supplied as a physical-failure threshold by the task; it has
not been relaxed. Structural `manifold_assignment_status=PASS` must not be read
as physical manifold certification. Overall physical manifold interpretation
remains **REVIEW_REQUIRED**. Only three points are sampled; continuous-path
band crossings/inversions and space-group irreps were not evaluated.

The null is exactly W=(V_uu+V_dd)/2 and V_null=I_spin⊗W, with the same common
potential, n_out, core and original issued FR object. It is not V_NL=0, a beta
average, a scalar-UPF computation, or a new scalar SCF. The [control receipt](D-null-receipt.json)
reports trace/twirl/rotation/Hermiticity errors ≤3.043e-13 and a nonzero
spin-dependent action norm0.0016864389984. Γ states3:8 span
**1.6276018688e-12 eV**, and full Δ is >100 times that width.
The generic null `resolvable_soc_status=MISMATCH` is retained: lack of a
resolvable SOC signal is precisely this control's expected property.
D full/null max explicit residuals are9.9223102903e-11/9.0839779599e-11 Ha;
Gram3.4637232973e-14/2.8211464744e-14. Physical-q TR is runner-measured only
on Γ/±p; eight boundary-TRIM mappings have separate synthetic tests.

[Static NLCC evidence](D-static.json) contains exactly five positive trial-density
XC evaluations and both difference steps. Original PP_NLCC array SHA is
`f6a83dbb03c3f1eedbefa728d841de443dac2b10de554430737e4d24bb93cb48`.
Two-atom core integral1.4485097160857032 equals twice0.7242548580428518,
G=0 error4.44e-16. Core enters full PBE XC once; FD/Hartree and ∫n*vxc use
valence n, Ne8. The frozen XC convention and PspCorrection are unchanged.
The represented two-atom Fourier error is1.3581460382e-16, non-Nyquist error
1.3315179695e-16; the raw-atomic→native real(ifft) Hermitian-projection delta
is **1.2867950287e-10**, retained over the original even nonorthogonal grid.
No core values or modes were altered. Full GGA derivative −0.008912424207844988 Ha
has finite-difference errors2.4393410035e-10 at1e-4 and1.3007711228e-11 at1e-5.
These array/source-dependent measurements are **RUNNER_REPORTED**.

| Original SCF quantity, Ha/cell | D | Q | D−Q, meV/cell |
| --- | ---: | ---: | ---: |
| E | −8.368023851835549 | −8.36804460913415 | +0.564834869675 |
| F | −8.368024366448916 | −8.368045123751521 | +0.564834978627 |
| −TS | −5.146133665457469e-7 | −5.146173709646032e-7 | +1.0896578819e-7 |

[Energy ledger](energy.json) uses native D energy and QE E=F−demet, with original
SCF fields and print precision preserved. No constant is added or fitted.
The remaining total-energy difference is not attributed here; native QE
independent nonlocal energy is **NOT_MEASURED**. Public spectra replay splitting,
not unpublished wavefunctions, density norms or independent source extraction.

Only five shared interfaces changed: registered Si source loading, optional FFT,
optional per-k FFT streaming in density/energy and SCF forwarding, and disabling
automatic band growth for this case. Old defaults and physical formulas remain.
[Tests](tests.json): **2427/2427 distinct current assertions PASS** =1951 affected
Phase6A/6B/6C regressions +53 null +87 interfaces +156 boundary +118 driver +62
Python parser/recorder/comparison. These are workbench tests, not upstream counts.
Eager/stream density, magnetization and seven energy terms matched exactly;
real Mg static and old scalar Si source/default regressions passed. No Mg SCF,
Phase7G CI or full upstream suite was rerun; historical R FAIL/I PASS is unchanged.
[Pre-execution engineering failures](pre-execution-events.json) retain missing
cache/log-lock issues, sandbox MPI startup, the corrected driver syntax defect
and recorder negative-test failure. None was a retried formal numerical attempt.

Historical public-only entry: `python3 scripts/check_si_soc.py` from the fixed
61cb1c2 snapshot root; use the [current replay instructions](status-correction/README.md).
It authenticates public bytes, replays spectral statistics under the declared
floating contract and checks all383 historical files against the accepted base.
Both the current worktree and a fresh public-only clone passed (exit0), with
no `.work`, UPF or private arrays in the clone. The107 independent scalar/XML
review checks also passed. An offline PASS certifies faithful arithmetic replay,
not physical correctness.
Exact execution commands and raw/public hash links are in [evidence](evidence.json).
Initial staged diff-check failed on native QE trailing whitespace (exit2). Only
public stdout trailing spaces/tabs were removed; all tokens, line numbers and
warnings are unchanged. Original stdout/XML/stderr remain archived unmodified.
The [archive receipt](archive-receipt.json) records verified external same-machine
copy/tar of343 files, per-file hashes and9 sample restores; it is **not an offsite backup**.
Final delivery commit/bundle is recorded separately from the execution snapshot.

Physical cutoff/k/temperature convergence=NOT_ESTABLISHED;
noncollinear_magnetic_XC=NOT_IMPLEMENTED; upstream_acceptance=NOT_ESTABLISHED.
No independent scalar pseudo, new IEEE localization, extra material/scan, main
push, PR, merge or upstream contact was performed. Implementation and evidence
received material AI assistance under the [existing disclosure](../../docs/ai-assistance.md).
Interpretation remains subject to the explicit warnings and human review.
