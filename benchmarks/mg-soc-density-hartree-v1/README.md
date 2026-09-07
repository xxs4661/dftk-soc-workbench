# Existing Mg density and Hartree audit

This plan is fixed before the first real extraction. The machine-readable
[plan](plan.json) binds original bytes, source receipts, units, 17 direct Fourier
checks and engineering thresholds. No new electronic-structure calculation is
permitted. The accepted base is `d2ed86316bd030f9d662a1089edb83c94d8f2607`.

| Source | Original run | Density role |
| --- | --- | --- |
| A | `20260906T151940Z-A-270110aa` | Primary `n_out`; `n_in` only for same-run closure |
| B | `20260906T153016Z-B-62835d43` | Auxiliary `n_out`; no selection by agreement |
| G40 | `20260907T112107073262Z-G40-3f9731a6` | Original SCF saved total charge, never a bands directory |

The original calculations are **HISTORICAL_REUSED**. New array work is
**NEW_EXTRACTION_FROM_HISTORICAL_ARRAYS**. The model stays one Mg at fractional
(0.17,0.23,0.31) in a 10 bohr cube, ten valence electrons, PBEsol FR-NC without
NLCC, 15 Ha, three historical k points, tau=0.001 Ha and 40³ FFT. The existing
UPF is identified by its historical SHA only; this task does not read it.

## Binding and restricted extraction

Before deserialization, bind A/B checkpoint bytes to the Phase 6C execution
receipt and public evidence, verify the raw result and maps hashes and run ID,
and use the frozen Julia 1.12.7 environment. The producer
[writes](../../scripts/run_soc_scf.jl) a plain Julia Serialization NamedTuple
with `X,f,eigenvalues,n_in,n_out,R,m,final`; it is not JLD2 or an SCFResult.
Read density arrays without recreating orbitals, a model or Hamiltonian.
Use the producer's `sha256(reinterpret(UInt8,vec(n)))`, original Float64
column-major layout, both endpoint hashes and final map count. Do not normalize,
clip, mix, symmetrize, shift or recompute density from X/f.

The [SCF map](../../prototypes/soc_scf/scf.jl) solves in H[n_in] and evaluates
complete energy at the same X/f-derived n_out. Recompute
`sqrt(dvol)*norm(n_out-n_in)` against the final stored norm; its unit is
electron/bohr^(3/2). In-only full coefficients remain local, so these closure
and in-only EH measurements remain runner-reported to public-only reviewers.

G40 paths are selected from the original Phase 7B raw archive manifest, whose
SHA is already published in [its evidence](../../results/mg-soc-qe-diagnostics/evidence.json).
Verify original charge, XML, input, snapshot and process receipts. Read the
actual integer Miller table, not an inferred order or orbital plane-wave count.
File structure follows [QE 7.5 io_base](https://github.com/QEF/q-e/blob/qe-7.5/Modules/io_base.f90):
Fortran records contain gamma_only/ngm/nspin; three reciprocal vectors;
`mill(3,ngm)`; one Complex128 record per saved component. Independently test
4/8-byte record markers, logical and integer widths, both byte orders, all
record trailers, lengths, finite values, size limits and complete file end.
Reject ambiguous candidates, duplicates or missing G=0. The prescribed full-G,
charge-only case requires gamma_only=false, nspin=1 and actual ngm=22119.
Half-G and HDF5 are explicitly unsupported, without doubling or completion.

[io_rho_xml](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/io_rho_xml.f90#L52-L62)
writes only total charge for noncollinear nonmagnetic runs and passes `bg*tpiba`
and `rho%of_g`. The converged branch in
[electrons](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/electrons.f90#L978-L1005)
refreshes v_of_rho using unmixed output rho; after the convergence exit it
[writes that rho](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/electrons.f90#L1229-L1256).
Bind this path to actual G40 XML noncolin/spinorbit/domag and successful SCF
receipts. A tagged source convention is not proof that the installed binary was
built from that exact commit. The previous binary/source-provenance limitation
remains. If state binding is unclear, report UNRESOLVED, not a physical error.

## Fixed Fourier and Poisson arithmetic

A's columns are direct lattice vectors, Ω=abs(det A), B=2π A^(-T), q=B m.
Verify AᵀB/(2π)=I. The saved QE B already includes 2π/alat. Positive valence
density n has units electron/bohr³. Define

```
nbar_m = (1/Ω) integral n(r) exp(-i q_m·r) dr
       = FFT(n)_m / N_grid
n(r)  = sum_m nbar_m exp(i q_m·r)
N_e   = Ω real(nbar_0)
c_m   = sqrt(Ω) nbar_m
vH_m  = 4π nbar_m / |q_m|²       (m != 0); vH_0 = 0
EH_S  = 2π Ω sum_(m in S, m!=0) |nbar_m|² / |q_m|²
```

The frozen [DFTK fft](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/fft.jl)
uses c=sqrt(Ω)/N_grid FFT(n), native [0:19;-20:-1] axes and column-major bins.
Its [Hartree term](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/terms/hartree.jl)
agrees with `1/2 sum (4π/q²)|c|²`. QE's forward transform stores nbar;
[v_h](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/v_of_rho.f90) uses e2=2 in
Ry units and converts dimensionless G² with tpiba². XML writes Ha. The full G
list is not doubled. The independent analyzer implements standard Poisson
arithmetic, not translated QE code or a call to the native Hartree evaluator.
No G+k, extra spin factor, k weight, density Ry/Ha conversion or G=0 division.

The 17 fixed direct sums include G=0, eight +/- pairs and non-axis modes.
Direct sums use actual fractional grid coordinates starting at zero, unrelated
to atom position. Check Parseval `dvol sum |n|² = Ω sum |nbar|²` on full grids.
Synthetic positive cosine/sine densities with nonzero phase provide independent
analytic signs, coefficients, electron counts and EH; they are not real Mg.

## Native supports and comparisons

Retain every actual DFTK native FFT mode and every QE saved Miller mode,
including present numerical zeros. Common comparisons use exact integer
intersection excluding G=0 and any Nyquist ambiguity, then require strict -m
closure. Report ambiguous modes separately; do not fold differing physical q
into a shared FFT bin. Full native EH retains the original Nyquist representative.
Discrete modulo-grid conjugacy and strict continuous -m closure are separate.
Missing coefficients are missing, not zero. No full cross-code real-space L2
claim follows from a common-support projection.

For delta=D-Q on common nonzero C, report full complex differences, maxima and
positions, `sqrt(Ω sum_C |delta|²)` and
`sqrt(sum_C |delta|² / sum_C |Q|²)`. A zero denominator is NOT_APPLICABLE.
Also report nonzero native norms and common fractions; these are not accuracy
percentages. The analogous independent vH difference has projected L2 units
Ha*bohr^(3/2). It is not an extracted native QE potential array.

Report A_out/Q, B_out/Q and A_out/B_out, plus local same-run out/in closure.
Compare independent native EH with each historical same-state Hartree term.
No Ewald, ionic, NLCC, PspCorrection, XC or nonlocal term enters this formula.
Decompose the signed native difference completely:

```
EH_D - EH_Q = (EH_D,C - EH_Q,C) + EH_D,outside_C - EH_Q,outside_C
EH_D,C - EH_Q,C = 2πΩ sum_C [2 Re(conj(Q)*delta) + |delta|²] / q²
```

Report linear and nonnegative quadratic parts separately; the latter is not
the signed energy difference. Fixed shell upper edges are 1,5,15,30,60 Ha in
q²/2; each lower edge is excluded and upper included, with final >60 shell.
All native modes and all shells remain. Compare historical delta Etotal with
new delta EH and call their difference **其余能量项的未分解差**; do not assign
it to SOC or another term. Failed same-source EH gates stop physical attribution.

## Gates, evidence and stopping point

All tolerances are in plan.json and fixed before real extraction. Exact source
hash/run ID/record/count checks, 1e-8 electron count, 1e-8 Ha same-source EH,
1e-10 Ha decompositions, fixed FFT/direct/Parseval/conjugacy checks are engineering
gates. Cross-code differences are measurements with no fitted acceptance limit.

Publish deterministic gzip CSV (mtime=0, UTF-8/LF, Float64 round-trip): one shared
DFTK G table with A_out/B_out real and imaginary parts, and one QE G table.
Keep full native supports and precision. Public standard-library replay must
recover all advertised coefficient/Poisson/support/EH arithmetic using these
files alone. Source-byte binding is a separate runner-performed evidence tier.
Original .bin/.save and full local diagnostics go to a verified repository-external
same-machine archive with a restoration check; this is not offsite backup.

Preparation is committed before formal A/B then G40 extraction. Each attempt
uses a new directory; failures cannot borrow prior PASS. New SCF/eigensolve/QE,
physical convergence and IEEE localization remain NOT_RUN/NOT_ESTABLISHED/
NOT_LOCALIZED. Numerical agreement is REVIEW_REQUIRED, full cross-code density
is NOT_ASSESSED, residual attribution stays NOT_ESTABLISHED. Only this branch
is pushed; stop for review without starting another experiment.
