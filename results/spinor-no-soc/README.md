# Spinor validation without SOC

Phase 5A run `b0-20260905T104910Z` lifted the same converged scalar Si Hamiltonian
into two components and solved 16 target states at each of eight k points. Both the spinor
and scalar target spectra, residuals, occupations and occupied-subspace diagnostics are retained.
The spinor fixed-H occupied expectation is **0.05694236739494021 Ha/cell**;
it is a band expectation, not a DFT total energy. [Source log](fixed-h-source.log).

Phase 5B run `abc-20260905T130100Z` independently initialized spinor A/B,
then native scalar C. Both complete **53-map** histories survive, including candidate and
extra closure; no sparse sampling or hidden early residuals. [Source log](scf-source.log).

| Independent run | Total energy (Ha/cell) | Final density residual L2 |
|---|---:|---:|
| A | -8.428884532744394 | 3.220091734766808e-11 |
| B | -8.428884532744394 | 3.233562468001258e-11 |
| C native scalar | -8.428884532744393 | 4.720704502982586e-10 |

All endpoint target eigenvalues/residuals and independent scalar references remain public.
All three nonstationary finite-difference steps retain both original side energies and the
independently evaluated central Hamiltonian derivative. Seven-term E uses the returned
orbitals' own density; the double-counting identity uses H[n_out], without a fitted shift.
Hartree and electron counts use valence density; NLCC enters native XC once.

[Layout and implementation](../../prototypes/spinor/README.md),
[energy conventions](../../prototypes/spinor/SCF-DESIGN.md),
[5A thresholds](../../prototypes/spinor/tolerances.toml),
[5B settings](../../prototypes/spinor/phase5b.toml).

These are no-SOC, charge-only LDA runs on the original Si input. Magnetic XC, QE SOC
comparison and physical cutoff/k convergence were not established. A native log's `-Inf`
energy-change display is log10(0), not an infinite total energy.

## Review and reproduction

[evidence.json](evidence.json) is the canonical numerical source. Its provenance records
the original run IDs, execution HEAD/file hashes, fixed inputs and immutable source blobs.
Historical `REVIEW_REQUIRED` is preserved; AI-assisted arithmetic review is not external
expert certification. Current capabilities and limits are in [status](../../docs/status.md).

From the repository root, Python 3.11 or later runs public-data checks without Julia,
private arrays, SCF or QE:

```sh
python3.12 scripts/curate_prototype_evidence.py --check
```

This recomputes the retained tables and energy/spectral differences. Density, orbital,
operator-action and direct eigenvector-residual errors remain original runtime measurements
when their arrays are not public; a hash is not an independent numerical proof. Physical
reproduction requires the frozen environment and the licensed input at its recorded hash.
