# First Mg QE SOC comparison — review required

One new QE 7.5 SOC SCF and one warning-triggered fixed-density bands calculation
have completed. Input comparability, native E/F interpretation and offline
comparison pass; **numerical agreement is REVIEW_REQUIRED**. Physical convergence
is **NOT_ESTABLISHED**. This does not validate noncollinear magnetic XC or provide
upstream native SOC support.

The default publication was completed first through [PR #1](https://github.com/xxs4661/dftk-soc-workbench/pull/1):
`1e78bdb406f74dbae9601edd3a158cb04df24bd0` → ordinary merge
`77bd2e151116bcc189b797e6da415d27a61d3a2b`, which is this phase's base.
Reviewed `ac22a64421c4a5444a399477b9a3215dbd913487` remains an ancestor;
the remote main tree and directly downloaded README/status/results entries
matched the reviewed tree `6d13576c190986a4872e8948fb7c1a851961e950`.
Main remained unchanged during this benchmark development.

## Sources and execution

[Evidence](evidence.json) binds inputs, binary, original/public hashes, execution
source hashes, corrected verifier identity, failures and the publication receipt.
[Case](../../benchmarks/mg-soc-qe-v1/README.md) fixes one Mg, 10 bohr cube,
PBEsol FR-NC without NLCC, 10 electrons, 24 capacity-one spinors, Γ/k± at 1/3,
15 Ha cutoff and FD tau=0.001 Ha. No physical setting was changed after execution.

| Source | Run ID | Status |
| --- | --- | --- |
| DFTK A, primary | `20260906T151940Z-A-270110aa` | HISTORICAL_REUSED |
| DFTK B, auxiliary | `20260906T153016Z-B-62835d43` | HISTORICAL_REUSED |
| New QE SCF | `20260907T001853989732Z-c88a8fa3` | Process 0; 15 iterations; SCF converged |
| One fixed-density bands check | `20260907T002225710098Z-bands-1561a3f2` | Process 0; original SCF's 19 files unchanged |

A/B canonical [endpoints and provenance](../mg-soc-scf/README.md) are referenced,
not copied or rerun. Their density, Pauli and operator-array claims remain
HISTORICAL_RUNNER_REPORTED. The new fresh-process Julia identity check passed
with the unchanged locked checkouts and Manifest; no Julia numerical test or
SCF was run. Existing QE JLL 7.5.1+0 starts PWSCF 7.5; real binary SHA-256 is
`0500a3db2fc668d4e558d6e667522fbd62793bdf87631776e6b0c4bc3c4e50f0`.
Launcher/runner/binary match the historical scalar QE identity. Source commit
is null, not inferred from the version. MPI uses one process/node and the
subspace algorithm is serial; conservative thread settings and linked BLAS/MPI
libraries are recorded.

The first launch `20260907T001820229335Z-d0eb93e7` failed before SCF at MPI
initialization: sandbox OFI permission denied, process 143. The identical input
was retried through normal permission review. No old PASS was reused.
The successful solver's first recorder exited 9 because the initial parser
incorrectly required a zero `starting_magnetization` XML field. QE omits that
optional field when all starting values are zero; the input and actual
`do_magnetization=false` establish the charge-only case. Same native bytes were
reparsed after correcting the adapter; the failed record remains local.

The [original predeclaration](../../benchmarks/mg-soc-qe-v1/case.predeclared.json)
also incorrectly listed QE's PBEsol indices as 1/1/10/8. Only that metadata is
corrected to 1/4/10/8 in [case.json](../../benchmarks/mg-soc-qe-v1/case.json),
following [QE's fixed functional table](https://github.com/QEF/q-e/blob/qe-7.5/XClib/qe_dft_list.f90#L116-L118).
`qe.in`, UPF, all physical settings and original parser tolerances are unchanged.
The offline checker proves this is the only case change; actual QE had correctly
selected PBESOL without an `input_dft` override.

## E, F and entropy

XML energies are Ha; stdout energy is Ry and bands/Fermi energy are eV. The
[QE 7.5 writer](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/pw_restart_new.f90#L695-L727)
and [FD energy convention](https://lists.quantum-espresso.org/pipermail/users/2005-October/003180.html)
establish `etot=F`, `demet=-TS`, `E=F-demet`. No zero-temperature extrapolation,
empirical constant, or PspCorrection is applied to QE energy.

| Source | E (Ha/cell) | F (Ha/cell) | −TS (Ha/cell) |
| --- | ---: | ---: | ---: |
| DFTK A | −57.325987985147734 | −57.325987985147734 | −1.2426050669902276e−37 |
| DFTK B | −57.32598798514773 | −57.32598798514773 | −1.2426050665736325e−37 |
| QE SCF | −57.32602794786339 | −57.32602794786339 | native displayed 0 |

A−QE E and F are **+3.9962715653985015e−5 Ha/cell**
(**+0.0010874408910988974 eV/cell**); B−QE is
+3.996271566109044e−5 Ha/cell. This is a one-atom cell; per-cell and per-atom
values coincide. Entropy differences equal the tiny A/B values above, without
a meaningful relative error. QE's native zero retains XML/text tokens and
printed precision, not a claim of mathematical zero; occupation-derived entropy
is a separate diagnostic. Electron sums are 10 within the predeclared tolerance.

Native QE energy terms are preserved in [qe-result.json](qe-result.json), without
forcing a seven-term DFTK decomposition. Formally matching Hartree, XC and Ewald
terms are compared at each program's own final density: A−QE differences are
+8.687443240873449e−5, +1.8955653623642377e−5 and
+1.840410490672184e−8 Ha/cell respectively. B differences and source keys are in
the comparison JSON; this does not independently validate density equality. Substituting XML fields into
`eband-ehart-vtxc+etxc+ewald+demet` leaves F minus this partial sum equal to
−3.692822836853793e−6 Ha. This is not a supported total-energy identity:
[QE computes its orbital potential subtraction earlier](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/electrons.f90#L843-L847),
then [refreshes final-density terms](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/electrons.f90#L978-L1005);
the required `deband` is not published in this XML. No extra identity is imposed,
no energy is patched, and the discrepancy is retained as incomplete-decomposition
evidence. The final branch sets `descf=0`; it is not attributed to a nonzero descf.

## Spectra and precision

All Γ/k± points are matched modulo reciprocal lattice integers, independent of
row order. The [SCF CSV](eigenvalues.csv) and [bands CSV](eigenvalues-refinement.csv)
include all 24 states, occupations, raw differences and one global HOMO reference
per program, for both A and B. No per-point/band fitting is used. All occupations
satisfy the predeclared endpoint criterion; each engine has a separated sampled
gap. Chemical potentials lie on an occupation plateau and need not coincide.

A−QE statistics below are eV, with unweighted RMS over included k/state entries.
Full occupied/empty/all summaries for A and B are in
[SCF comparison](comparison.json) and [separate bands comparison](comparison-refinement.json).

| QE spectrum | States per k | Raw max / RMS | Global HOMO max / RMS |
| --- | ---: | ---: | ---: |
| SCF | 16 | 0.2500328924 / 0.2497625624 | 0.0006559845 / 0.0003503422 |
| SCF | 24 | 0.2500328924 / 0.2498170507 | 0.0006559845 / 0.0002958219 |
| Fixed-density bands | 16 | 0.2500357686 / 0.2497579567 | 0.0006703826 / 0.0003603911 |
| Fixed-density bands | 24 | 0.2500357686 / 0.2498165229 | 0.0006703826 / 0.0003034025 |

For SCF/all24, the occupied-state referenced max/RMS are
0.0006559845/0.0004338421 eV; empty-state values are
0.0002138925/0.0001248038 eV. B differences are separately retained, not selected
for closer agreement. The raw common offset is near minus Mg's existing
PspCorrection/10 = **−0.009187494522099392 Ha**. This is a non-fitted diagnostic
from Mg, not the Si constant; QE internal G=0 was not directly extracted.
It neither explains all residual differences nor changes E/F or any spectrum.

The SCF ends with `2 eigenvalues not converged` at `ethr=1.36e−12 Ry`.
The warning identifies no band indices. The only additional bands run used the
same fixed density/settings and explicit initial threshold 1e−10 Ry, with no
`c_bands` warning. This threshold is less strict than the last SCF threshold;
absence of a warning does not prove better absolute accuracy. Its raw change
from SCF is max **8.159001257529441e−7 Ha** (2.2201773460007833e−5 eV).
It inherits SCF μ and recomputes occupations at that μ; it supplies no E/F.
Its zero energy placeholders are never consumed. Original SCF files and copied
charge-density bytes were verified unchanged.

Both [SCF stderr](qe.stderr) and [bands stderr](qe-refinement.stderr) report
IEEE_INVALID_FLAG, IEEE_DIVIDE_BY_ZERO and IEEE_OVERFLOW_FLAG. They remain
unresolved warnings despite normal exits, finite final values and convergence.
QE exposes no individual `||Hψ−εψ||` here: **NOT_AVAILABLE**. Printed `ethr` and
SCF error (1.739665246124743e−12 Ha) are not substituted for those residuals.
All 72 XML eigenvalues match native stdout within its printed 0.0001 eV precision.
Historical DFTK endpoint eigenpairs belong to H[n_in], with recorded H[n_out]
residuals around 1e−8 Ha; ~1e−13 Ha A/B repeatability is not absolute accuracy.

Both engines have spatial plane waves 2777/2770/2770, but QE uses density/smooth
FFT **36³**, compared with DFTK **40³**. Numerical settings are therefore
INPUT_PASS_WITH_NUMERICAL_DIFFERENCES. The residual total-energy/spectral
mismatch is not fully explained; it cannot be assigned solely to FFT, zero point,
or solver error without further authorized work. The slightly larger referenced
bands difference is retained. Kramers/±k diagnostics are supplementary.

## Offline review, tests and stopping point

```sh
python3.12 scripts/check_qe_soc_evidence.py
python3.9 scripts/check_publication.py
python3.12 -m unittest discover -s tests -p 'test_qe_soc_*.py' -v
python3.12 -m unittest discover -s tests -p test_publication.py -v
```

New/affected Python tests: 96 SOC parser/comparison/recorder/public-evidence tests,
23 publication tests, and 91 prior scalar/preparation regressions, **210 passed**.
A's separate clean publication check and original 9 boundary tests also passed.
Commands, interpreter versions, exits and log hashes are in evidence; process
logs remain local. The clean public replay uses no `.work`, UPF, Julia, QE or
private archive. The combined check needs Python 3.9 for exact historical scalar
arithmetic and Python 3.12 for newer adapters; it verifies the old UPF exporter
against the original `ac22...` Git object without refreshing its evidence hash.

All 86 frozen scientific files, locks and historical result bytes are preserved.
New raw runs (51 files, 22,184,055 bytes) were copied to a repository-external
archive, hash-verified and restored to a separate temporary directory. This is
same-machine storage, not an offsite backup. The 6 public native outputs preserve
all numerical fields/warnings; public stdout trims only trailing spaces/tabs and
CSV uses LF. Original and public hashes are distinct fields.
Execution source versions and subsequent adapter/recorder changes remain
separately identifiable; no historical execution hash was refreshed.

NOT_RUN: new DFTK A/B, historical array/density revalidation, cross-code density
L2, physical cutoff/k/temperature convergence, new Julia/upstream numerical
suites, additional materials or scans. Noncollinear magnetic XC remains
NOT_IMPLEMENTED. This first comparison is ready for review with its differences
and warnings; no new physical agreement threshold was selected. Work stops here.
