# Phase 4C: finite Si reference and sensitivity checks

This directory adds only the prescribed three configurations. The accepted
[Phase 4B case](../case.json) and its results are immutable. All geometrical,
pseudopotential, XC, NLCC, electronic, SCF and diagonalization settings remain
identical. Each new case records all changes and its historical reference.

| Setting | DFTK cutoff (Ha) | QE ecutwfc / ecutrho (Ry) | Explicit k points | Provenance |
| --- | ---: | ---: | ---: | --- |
| B0 | 30 | 60 / 240 | 8 | HISTORICAL_REUSED, commit f05e6d70750f10d5ea87ebb9f7c6a5ec993c7063, run 20260905T040945688395Z-1cc8a50c |
| [C1](C1.json) | 40 | 80 / 320 | 8 | New execution |
| [C2](C2.json) | 50 | 100 / 400 | 8 | New execution |
| [C3](C3.json) | 50 | 100 / 400 | 64 | New execution |

The eight-point Cartesian product is `{0,-1/2}^3`. The 64-point product is
`{0,1/4,-1/2,-1/4}^3`; the former is a checked subset of the latter.
Spatial weights are respectively 1/8 and 1/64. The parser requires the expected
count from the request, and still checks unique coordinates, eight electrons,
eight scalar bands and the QE spin-degeneracy normalization. New cases declare
`n_kpoints`; the old case's explicit input list supplies its count without
rewriting the historical file. The old generator produces byte-identical B0
inputs and the revised parser/comparator reproduces its saved result exactly.

## Independent local-potential reference

For this neutral two-Si, eight-electron cell, in Hartree atomic units:

`alpha = 4*pi * integral_0^R [r^2*Vloc_Ha(r) + Z*r] dr`

`C = 2*alpha / volume`, with `Vloc_Ha = PP_LOCAL/2`, `Z=4`.

The [UPF format specification](https://pseudopotentials.quantum-espresso.org/home/unified-pseudopotential-format)
identifies PP_R as bohr and PP_LOCAL as Ry. The Coulomb tail is cancelled
pointwise before integration; neither divergent piece is integrated separately
to infinity. The actual PP_R array defines the upper limit, 15.09 bohr.
The historical metadata key `rho_cutoff_bohr` is not consulted: the UPF header
attribute `rho_cutoff` denotes a suggested density **energy** cutoff, not a
radial integration limit. The historical configuration remains untouched.

`inspect_si_reference.py` reads the original XML arrays directly with the Python
standard library. Its primary quadrature integrates local quadratic interpolants
on the actual coordinates, including the final single interval. It works on
uneven grids, as tested with analytic artificial functions. The selected grid
happens to be essentially uniform (1510 points, 0.01 bohr spacing). A full-grid
trapezoid and strides 2/3/4 of the same quadratic method provide sensitivity
diagnostics. They are not rigorous error bounds. The small nonzero finite-grid
tail and the unintegrated region beyond R are explicitly reported.

This calculation imports neither DFTK nor PseudoPotentialIO and reads no spectra.
The separate DFTK value is its actual `energy_components_ha.PspCorrection / 8`.
The fixed DFTK implementation converts [UPF Ry to Ha](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/pseudo/PspUpf.jl#L114),
sets [local G=0 to zero](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/pseudo/PspUpf.jl#L236),
and evaluates [the finite radial correction](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/pseudo/PspUpf.jl#L308).
Its [PspCorrection term](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/terms/psp_correction.jl#L18)
adds the energy `N*C` for this neutral system, with a
[zero operator](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/terms/operators.jl#L55).
It therefore does not shift the Hamiltonian eigenvalues.

The corresponding QE 7.5 tagged sources define the finite
[local G=0 coefficient](https://github.com/QEF/q-e/blob/qe-7.5/upflib/vloc_mod.f90#L151)
in Ry, and [retain it in the summed local potential](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/setlocal.f90#L67).
At G=0 the [atomic structure factor](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/struct_fact.f90#L89)
counts the two Si atoms. The usual periodic [Hartree potential omits its G=0 component](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/v_of_rho.f90#L665),
while the [ionic potential enters the Hamiltonian](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/set_vrs.f90#L41).
The [native energy bookkeeping](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/electrons.f90#L843)
already retains the ionic contribution. These conventions predict
`epsilon_DFTK - epsilon_QE approximately equals -C`; they do not authorize a
second addition/subtraction of `N*C` to either SCF total energy.

This is a **prediction from corresponding tagged-source conventions and input
data**. No public output used here exposes the actual binary's internal numeric
G=0 value; that value was not directly extracted. The JLL binary source commit
is unconfirmed, although version, startup chain and binary hash match B0.
No QE algorithm was copied, translated, modified or recompiled.

## Running and analyzing

Use the existing frozen workbench environment and the exact Si UPF from the
[original retrieval instructions](../README.md#pseudopotential-and-retrieval).
No package installation or dependency update is part of these commands.

```sh
JULIA_DEPOT_PATH=/path/to/existing/workbench/cache python3 scripts/run_recorded.py identity
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts:tests python3 -m unittest -v test_scalar_baseline test_qe_baseline_parser test_phase4c_baseline test_si_reference test_si_sensitivity
python3 scripts/inspect_si_reference.py --case benchmarks/si-sr-lda/case.json --output .work/new-reference.json
python3 scripts/run_scalar_baseline.py --case benchmarks/si-sr-lda/phase4c/C1.json --julia-depot /path/to/existing/workbench/cache
python3 scripts/run_scalar_baseline.py --case benchmarks/si-sr-lda/phase4c/C2.json --julia-depot /path/to/existing/workbench/cache
python3 scripts/run_scalar_baseline.py --case benchmarks/si-sr-lda/phase4c/C3.json --julia-depot /path/to/existing/workbench/cache
```

The standalone identity command uses the existing Julia cache; the independent
integral needs only Python's standard library and the selected UPF. Each paired run checks
the actual loaded environment and QE launch chain against the historical record
before SCF; the actual startup version is checked before DFTK. Each receives a
fresh run ID. Run the commands sequentially. Do not repeat B0 SCF or expand the
matrix. The complete raw data, including non-public large artifacts, remains
under `.work/scalar-baseline/<run_id>/`.

```sh
python3 scripts/analyze_si_sensitivity.py --reference .work/new-reference.json \
  --b0 .work/scalar-baseline/20260905T040945688395Z-1cc8a50c \
  --c1 .work/scalar-baseline/C1_RUN_ID --c2 .work/scalar-baseline/C2_RUN_ID \
  --c3 .work/scalar-baseline/C3_RUN_ID --output .work/NEW_ANALYSIS_DIRECTORY
```

The analyzer anchors B0 to its accepted raw hashes, checks all current input
hashes and process/convergence records, reparses QE XML, and reproduces the
paired comparisons. It consumes the independent-integral record only when its
success, schema, case hash and independence flags are valid. Full raw differences,
single sampled-global-HOMO differences, and `delta+C_independent` diagnostics
are preserved in per-setting CSVs. No spectral fit supplies C.

Within each program, both cutoff and cross-grid spectral changes use the Gamma
highest occupied level as **one reference per entire solution**. Only the common
original eight points enter cross-grid spectral changes. Raw reference values,
raw spectra and total energies remain in the tables. The two grids' sampled gaps
are separate observations, not a proof of a converged fundamental gap.

The worker now additionally recomputes `norm(H*psi-lambda*psi)` for every target
state on the unchanged final SCF Hamiltonian. It preserves the old solver-history
residuals (which can contain zeros for locked states), SCF energies, eigensolver
settings and convergence criteria. Matrix application uses the pinned
[Hamiltonian block API](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/terms/Hamiltonian.jl#L67).

The limited results and review-dependent next-stage recommendations are in
[results/phase4c-review.md](../../../results/phase4c-review.md). This phase does
not establish full k-point convergence or implement/validate SOC or spinors.
