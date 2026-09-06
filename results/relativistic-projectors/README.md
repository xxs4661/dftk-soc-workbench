# Relativistic nonlocal projectors

Run `mg-si-20260905T164800Z` used real Mg full-relativistic NC PBEsol data
for an algebraic 39-q probe and the real scalar Si input for an artificial complete
spin-degenerate limit. It was not a physical Mg SCF or a real FR Si benchmark.
Actual execution was `2026-09-05T16:22:47.274` to `2026-09-05T16:22:53.779` UTC;
the run-ID label's time is not substituted for these recorded timestamps. [Source log](source.log).

The canonical evidence retains **7 angular (l,j) rows**, **56 Gaussian rows on two grids**,
**42 full-F and 42 modified-F real Mg quadrature rows**, and **8 Si action rows**.
The independent CG ladder and L·S projector/kernel references remain distinct from production:
[mathematical reference](../../tests/relativistic/angular_reference.jl),
[conventions](../../prototypes/relativistic/CONVENTIONS.md),
[fixed settings](../../prototypes/relativistic/phase6a.toml).

Maximum Gaussian normalized full-F error: **5.140749206874912e-15**.
Maximum real-Mg modified-F quadrature sensitivity: **1.2025369715562562e-06**.
These measure different things: the real-Mg difference is not a strict error bound. The two
independent trapezoidal sums follow different floating arithmetic routes and are both retained;
modified-F additionally carries the nonzero l>0 origin limit. Real Mg covers l=0,1; l=2,3 is synthetic.

The Mg spin-flip block norm is **2.7171370446737336e-05**, with imaginary norm
**1.6001052587386565e-05**. Small signals remain visible alongside normalized errors.
Channel labels and raw/internal D, reciprocal coordinates, two-path energy and all operator
checks are retained. Public angular error rows permit table aggregation; they are not full
CG matrices. Original P/D/X/kernel readback did not recheck unretained translation/volume/multiatom states.

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
