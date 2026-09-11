# Saved Mg density and Hartree audit — review required

The remaining cross-code difference **does appear in the saved valence density
and Hartree term**. All three source densities recover their own historical
Hartree terms within 1.1e-13 Ha. This establishes a same-source arithmetic check,
not physical convergence or a cause for the full total-energy difference.
Numerical agreement remains **REVIEW_REQUIRED**; residual attribution remains
**NOT_ESTABLISHED**. No SCF, eigensolve, QE executable, UPF reading or new IEEE
experiment was performed.

## Sources and evidence levels

Accepted base `d2ed86316bd030f9d662a1089edb83c94d8f2607`; preparation `b1a5b6a52777332c9593e584a4b02e2067fc534a`;
actual extraction/analysis commit `2b0c9268ffdbc20f67007aac89ec51db4cb7679d`.
The ordinary second preparation commit fixed coefficient publication/transfer
binding before any real extraction. No history was rewritten.

New extraction run: `20260907T132708175964Z-8d33b91c`
(2026-09-07T13:27:28.290952+00:00 to 2026-09-07T13:27:40.415937+00:00, process/recorder exit 0).
A and B extraction ran first, then G40 charge parsing.

| Source | Original run ID | Original array / state |
| --- | --- | --- |
| A | `20260906T151940Z-A-270110aa` | Julia Serialization `final.bin`: n_out primary energy state, n_in closure only |
| B | `20260906T153016Z-B-62835d43` | Julia Serialization `final.bin`: n_out primary energy state, n_in closure only |
| G40 | `20260907T112107073262Z-G40-3f9731a6` | Original SCF charge-density.dat: saved unmixed output total charge |

All original SCFs are **HISTORICAL_REUSED**. New results are
**NEW_EXTRACTION_FROM_HISTORICAL_ARRAYS**, not new electronic-structure runs.
The [plan/source table](../../benchmarks/mg-soc-density-hartree-v1/plan.json)
binds bytes, sizes, original receipts, endpoints, maps and the already published
Phase 7B archive manifest. [Evidence](evidence.json) records actual source hashes,
checks and execution code. A/B each have 191 maps; both density hashes match their
own endpoint and closure record. The checks were performed on trusted hashes
before Julia deserialization, then again after reading. All protected bytes
remain unchanged.

Two evidence levels remain distinct: (1) source-byte extraction/run/state binding
was performed by this workbench runner; (2) complete public n_out/rho coefficients
allow independent offline arithmetic. Public hashes do not recreate original
SCFs or prove extraction by a separate researcher. Full checkpoints, source
charge/XML/receipts and n_in coefficients remain in the verified local archive.

DFTK full energy uses n_out; its final eigensolve used H[n_in]. QE's successful
converged branch refreshes v_of_rho with unmixed output rho before write_scf.
The [source/format chain](../../benchmarks/mg-soc-density-hartree-v1/source-conventions.md)
binds that interpretation to G40's SCF/exit/convergence/noncolin/spinorbit/
do_magnetization fields. This is the corresponding QE 7.5 source convention:
the exact source commit of the installed JLL binary remains unavailable. No
native QE potential array was extracted.

## Array, Fourier and support checks

The actual Julia version is 1.12.7, DFTK 0.8.0 at
`2f51b91213e26726fb9c6a17e5fae235a1412d01`, and PseudoPotentialIO 0.3.3 at
`fec942781560c391f20214ba4cd85fb2431deb84`; both loaded local checkouts are clean.
Fresh process identity checks match [the frozen environment](../shared/environment.json),
including real loaded paths/UUIDs, active project and Manifest checksum
`5b8ae036ac430219a95d61a5e3cd20074e9ecd252335253bf7ada81278b08c37`.
No dependency was installed or changed. Julia only reads plain Float64 density
vectors and uses the existing FFTGrid; no model or Hamiltonian is constructed.

Each vector has 64,000 Float64 elements, reshaped column-major to 40³, with
fractional grid origin zero. DFTK c is divided by sqrt(Ω), yielding
nbar=FFT(n)/Ngrid. QE saved rho_g already follows that convention: no factor of
2, 1/3, Ry/Ha or fitted phase/scale is applied. Ω=1000 bohr³. The actual binary
has one unique encoding: little endian, 4-byte record markers/INTEGER/LOGICAL,
8-byte real and 16-byte complex; record payload lengths 12,72,265428,353904.
It is full G, gamma_only=false, nspin=1, 619,448 bytes. Saved reciprocal columns
are 2π/10 times the Cartesian axes; AᵀB/(2π) error is zero. The largest QE q²/2
is 59.61241058257972 Ha, within the unchanged 60 Ha density cutoff.

| Source | Native G (including zero) | Integer range per axis | max q norm / bohr⁻¹ |
| --- | ---: | --- | ---: |
| A_out | 64000 | -20 to 19 | 21.7655923708 |
| B_out | 64000 | -20 to 19 | 21.7655923708 |
| QE | 22119 | -17 to 17 | 10.9190119134 |

A/Q and B/Q each have **22,118 common nonzero** modes, **41,881 DFTK-only**
and **0 QE-only** modes. G=0 is unique. The common sets contain no Nyquist
ambiguity and close under strict -m. All 4,681 DFTK native Nyquist representatives
remain in native energy sums; they are not doubled. DFTK modular conjugacy
passes even though its strict continuous -m list lacks those representatives.
For A/B, the strict unambiguous common set has 59,318 modes; the full same-support
A/B norm is additionally computed on all 64,000 native bins. Missing modes are
never called zero; true zero-valued coefficients remain present.

The four real-array FFT/direct checks use all 17 predeclared modes (including
non-axis +/- pairs): maximum absolute difference 2.275e-18 electron/bohr³.
Maximum Parseval relative difference is 1.592e-16; modular conjugacy is below
2.601e-16 relative L2. No averaging or symmetry projection was applied.
The coefficient package retains all modes and Float64 precision with exact-bit
round trips, UTF-8/LF CSV and gzip mtime=0.

| Source | N_e from public G=0 | Independent native EH / Ha | Recomputed minus historical EH / Ha |
| --- | ---: | ---: | ---: |
| A_out | 9.9999999999999982 | 28.516778812881142 | -3.5527136788e-14 |
| B_out | 10.000000000000005 | 28.516778812880915 | -3.5527136788e-14 |
| QE | 10.000000000000002 | 28.516784779924716 | +1.0658141036e-13 |

All G=0 imaginary electron counts are zero. All electron-count, support,
self-Hartree and sum-path gates pass their predeclared tolerances. These are
engineering results; no cross-code difference acceptance threshold was chosen.

A/B same-run real-space closure norms recompute exactly to
1.6542346674852517e-9 / 1.6537267865203399e-9 electron/bohr^(3/2).
A separate Fourier sum differs by only 2.52e-18 / 6.19e-18 in those units.
The n_in native EH values are 28.51677880123298 / 28.51677880123454 Ha;
they are not the n_out endpoint energy. Because n_in coefficients are not public,
these closure/n_in/real-array FFT checks remain explicitly **runner-reported**.

## Common density and independently constructed Hartree potential

Use positive valence nbar and q=B m. On the common nonzero set,
L2=sqrt(Ω sum |D-Q|²); relative L2 uses only QE's common nonzero fluctuations,
not G=0. The independent Poisson diagnostic is vH=4πnbar/q² with vH_0=0.
It excludes all XC, ionic, Ewald, PspCorrection and nonlocal terms.

| Difference | Density projected L2 / electron·bohr⁻³ᐟ² | Relative L2 | vH projected L2 / Ha·bohr³ᐟ² |
| --- | ---: | ---: | ---: |
| A_out_minus_QE | 2.966217396997e-07 | 8.918425419781e-08 | 4.006815319676e-06 |
| B_out_minus_QE | 2.966218209037e-07 | 8.918427861317e-08 | 4.006814621416e-06 |
| A_out_minus_B_out | 5.082550682907e-13 | 1.528153406470e-13 | 5.200650865004e-12 |

The A−QE maximum complex density-coefficient difference is
1.7651244127891684e-9 electron/bohr³ at m=(0,1,-1); the vH coefficient maximum
is 3.73632581376796e-8 Ha at m=(0,1,0). Both real and imaginary parts and exact
m/q/left/right values are in [comparison.json](comparison.json), derivable from
the complete [DFTK coefficients](dftk-nout.csv.gz) and [QE coefficients](qe-rho.csv.gz).
Norm-coverage fractions are also reported there; they are not correctness rates.
These are common-support projections, not a full cross-code real-space L2.

## Signed Hartree decomposition

EH=2πΩ sum_native,nonzero |nbar|²/q². For delta=D-Q, common energy difference
contains **both** 2 Re(conj(Q) delta) and |delta|². The positive quadratic term
alone is not the signed Hartree difference. Full support, cross-term and fixed
shell recombinations all close within 1e-10 Ha. A separate cubic-formula script,
without importing the analyzer, reproduces native EH and the decompositions.

| Contribution / Ha per cell | A−G40 | B−G40 |
| --- | ---: | ---: |
| native_difference_ha | -5.967043573917863e-06 | -5.967043801291538e-06 |
| common_difference_ha | -5.967043573917863e-06 | -5.967043801291538e-06 |
| left_exclusive_ha | +1.373791116226432e-32 | +1.302672190254187e-32 |
| right_exclusive_ha | +0.000000000000000e+00 | +0.000000000000000e+00 |
| common_linear_cross_term_ha | -5.967044018496902e-06 | -5.967044246936141e-06 |
| common_nonnegative_quadratic_ha | +4.447549718269878e-13 | +4.447551210720724e-13 |

The DFTK-only Hartree tail is about 1e-32 Ha and QE has no exclusive nonzero
modes here. The observed Hartree difference resides in the common support;
missing-support energy does not account for it at this precision. This is a
statement about the saved coefficients, not a claim about every operator or
all numerical errors.

| Fixed shell q²/2 / Ha (lower excluded, upper included) | A−QE signed native contribution / Ha |
| --- | ---: |
| (0, 1] | -5.296443671198858e-06 |
| (1, 5] | -5.078764218069409e-07 |
| (5, 15] | -1.634780969483884e-07 |
| (15, 30] | +1.052859910366521e-09 |
| (30, 60] | -2.982425756012375e-10 |
| (60, ∞] | +1.373791116226432e-32 |

| Signed quantity | Ha/cell | meV/cell |
| --- | ---: | ---: |
| Historical A−G40 total E | +2.294777767986034e-05 | +0.624440841934 |
| Recomputed A−G40 Hartree | -5.967043573917863e-06 | -0.162371527436 |
| 其余能量项的未分解差 | +2.891482125377820e-05 | +0.786812369370 |

The last row is a signed remainder, not an identified SOC/nonlocal/radial error.
No fitted constant or correction was added to total energy. No absolute-value
percentage budget or attribution to a single mechanism is supported.

## Reproduction, tests and archive

From a normal public checkout, only standard-library Python is required:

```sh
python3.12 scripts/check_density_hartree.py
python3.12 scripts/check_density_hartree.py --all --legacy-python python3.9
python3.12 -m unittest discover -s tests -p 'test_density*.py' -v
python3.12 -m unittest discover -s tests -p test_qe_charge_density.py -v
```

The first command reads only public files. The combined command preserves the
byte-frozen Phase 7B/7A checkers and older Python 3.9 scalar arithmetic. It does
not access private arrays, .work, Julia, QE, UPF or the network. Independent
replay can call `iter_common_differences` to enumerate every complex density
and Poisson difference rather than storing another duplicate full table.

To repeat source extraction, first recover the exact historical files and their
bound receipts/manifest under the plan's relative paths; no automatic download
or scientific rerun is provided. With the existing frozen Julia depot:

```sh
python3.12 scripts/run_density_hartree_audit.py --output .work/phase7c/NEW_UNIQUE_ID \
  --qe-raw-manifest /path/to/verified/raw-manifest.json --qe-raw-root .work/phase7b
julia --startup-file=no --project=environment/workbench tests/test_soc_density_fft.jl
```

The manifest path is supplied explicitly. Missing source data is BLOCKED; do
not reconstruct it from public energies or rerun SCF. The full n_in/n_out CSVs
are local, while public data contains complete A_out/B_out/QE coefficients only.
The plan and mathematical source conventions remain the authority for all
thresholds. Extraction and later public verifier versions are separately bound.

Final tests, exact commands/exits/log hashes, public-only replay, frozen-file
checks and repository-external backup/restoration receipt are in
[evidence.json](evidence.json). New Python checks: **72 passed** (49 density/
recorder/public-integrity and 23 binary parser tests); historical Python
regressions: **198 passed** (175 SOC adapters and 23 publication checks).
The small Julia array suite passed **93 assertions**. The combined old/new
replay also passed in a separate public-only clone without .work or private
sources. Complete local process logs retain the first
synthetic MPI startup failure (exit 143 before tests); the subsequent frozen
Julia synthetic suite passed 93 assertions. The real extraction had no failed
attempt and no retry. The two pre-extraction recorder findings and their new
negative tests are retained in ordinary commits.

The archive is on the same machine outside the repository, with copied source
bytes, all new raw extraction data, logs and Git history verified by hashes and
sample restoration. Raw/source archive: **35 files, 47,985,904 bytes**, all hashes
verified; **9 files, 40,000,996 bytes** restored and verified independently in a
temporary directory. Its manifest SHA-256 is
`b69f29a782afcd3682205695ba10d93472f542fbacbc7e7346c223bdca2b815b`.
All **259 frozen tracked files** outside the five allowed navigation pages are
unchanged, and both upstream checkouts remain clean at their locked commits.
It is **not offsite backup**. It is not required for public
coefficient arithmetic. Historical Phase 6C/7A/7B inputs/results/reports,
scientific kernels, dependencies and both upstream checkouts remain unchanged.

NOT_RUN: all new SCF/eigensolves/QE/pp.x, old physical runs and upstream numerical
suites, UPF integration, potential transfer, physical convergence scans and IEEE
localization. Full cross-code real-space density is **NOT_ASSESSED**; residual
attribution and physical convergence are **NOT_ESTABLISHED**, historical IEEE
origin **NOT_LOCALIZED**, and numerical agreement **REVIEW_REQUIRED**.
The known same-source Hartree checks pass; the cause of the remaining energy
terms stays open. Stop here for human review, without another experiment.
