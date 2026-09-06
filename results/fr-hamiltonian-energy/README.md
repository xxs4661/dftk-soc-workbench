# Full relativistic Hamiltonian and energy

Run `20260906T004533Z-real-2eb791c8` solved three fixed-density Mg k-point problems,
16 target states each. All **48 target eigenvalues and direct residuals**, seven energy terms,
spin decomposition and three +/- finite-difference steps remain in the canonical evidence.
The six common DFTK terms exclude native nonlocal; the full operator adds one FR nonlocal term.
[Source log](source.log), [implementation](../../prototypes/fr_integration/README.md),
[fixed settings](../../prototypes/fr_integration/phase6b.toml).

The energy of solved orbitals at their own n_X is **-53.33046239986318 Ha/cell**.
It is not a self-consistent energy: n_X−n_ref L2 is **4.069221362833036**,
and the current-H expectation minus the old-reference eigenvalue sum is
**71.11715057361907 Ha**. These discrepancies are retained
because they establish why energy must use the orbitals' own density.

The general-complex fixture has nonlocal cross energy
**4.515470814429347e-06 Ha/cell**; the solved-orbital cross term is
**-6.880696639368161e-06 Ha/cell**. The independent full/diagonal/cross
values and nonzero spin-rotation response are retained, not only normalized errors.

The Si test uses the original real scalar input with synthetic complete degenerate j branches,
LDA/NLCC and no new Si SCF. Its recorded full-H action maximum is
**4.0625427618255424e-17**.

## Resolved defects and historical prose correction

Failed attempt `20260906T004258Z-real-621db3c3` exited 1:
`ArgumentError: G+k reversal is not bijective`. The signed-zero Gamma dictionary key stopped full-H checks after
the Si stage passed; Mg eigensolves were **NOT_RUN**. The later successful run
performed the three solves once, after the Gamma/T² regression fixed the key representation.
The failure receipt and executed source identity remain public.

The [historical report](https://github.com/xxs4661/dftk-soc-workbench/blob/8658992afa936f6cdb1a8055699ae9aa47b32297/results/phase6b-review.md)
displayed Si action error `3.997e-17`; the final JSON actually records
`4.0625427618255424e-17`. This page uses the latter without changing historical numerical data.
An earlier common-data rejection confused raw header whitespace with frozen-parser functional
normalization; current source-bound checks and regressions preserve the correct distinction.

This phase did not run SOC SCF, QE SOC, magnetic XC or physical convergence scans.
Diagnostic first-ten-per-k occupations did not establish global ground-state filling.

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
