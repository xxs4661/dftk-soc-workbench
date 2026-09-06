# Si finite cutoff and k-point sensitivity

Historical B0/C1/C2/C3 execution and input comparability: PASS. Numerical
agreement: REVIEW_REQUIRED. Full k-point convergence: NOT_ESTABLISHED.
The frozen sequence is 30/40/50 Ha at eight explicit points, then 50 Ha at
64 points. Geometry, pseudopotential, XC, occupations and tolerances are fixed.

| Change | DFTK ΔE (meV/atom) | QE ΔE (meV/atom) |
| --- | ---: | ---: |
| B0 → C1 | -0.102315243386168 | -0.102289842054087 |
| C1 → C2 | -0.0559043075550952 | -0.0559043193251869 |
| C2 → C3 | -1212.89493523177 | -1212.89482505351 |

The 8→64-point change is large. On the original eight common points, maximum
Gamma-HOMO-referenced spectral changes are
0.228587318244992 eV (DFTK) and
0.228579504561804 eV (QE).
These observations cannot establish a converged gap or dense-grid baseline.

The independent input-based prediction is C = 0.049402732655435877 Ha, from
alpha = 6.6696503558517817 Ha·bohr³ and C = 2 alpha / volume.
The published [reference](reference.json) retains grid, units, trapezoid and
coarsening diagnostics, and its nonzero finite tail. The quadratic/trapezoid
C difference is 3.102687657961617e-06 Ha;
it is a method sensitivity, not a rigorous bound. Integration stops at the
last actual radial grid point. The unintegrated tail is not fitted away.
The predicted spectrum difference is −C; the tables preserve raw differences,
one global HOMO reference per program and the independent delta+C diagnostic.
No spectral fit supplies C and no total-energy correction is added.

Public-only reintegration is NOT_AVAILABLE_WITHOUT_UPF. The reference factors,
all pair comparisons and all ten tables (1088 rows) are independently recomputed
from public native XML/JSON, without fetching a pseudopotential or running QE:

```sh
PYTHONDONTWRITEBYTECODE=1 python3.9 scripts/curate_scalar_evidence.py --check
PYTHONDONTWRITEBYTECODE=1 python3.9 scripts/curate_scalar_evidence.py --tables .work/new-scalar-tables
```

[Evidence](evidence.json) contains exact historical summaries and row fingerprints;
rows regenerate from native results, not from hashes. Native records:
[C1 XML](C1/qe-data-file-schema.xml), [C1 QE stdout](C1/qe.stdout), [C1 DFTK](C1/dftk-result.json);
[C2 XML](C2/qe-data-file-schema.xml), [C2 QE stdout](C2/qe.stdout), [C2 DFTK](C2/dftk-result.json);
[C3 XML](C3/qe-data-file-schema.xml), [C3 QE stdout](C3/qe.stdout), [C3 DFTK](C3/dftk-result.json).
[Repeated QE warnings](../scalar-si-baseline/B0/qe.stderr) occurred in all four runs.
C3 stdout also retains the “eigenvalues threshold was too large” diagnostic
before tighter final diagonalization. DFTK residual histories and explicit final
residuals are retained separately; B0 has no independent residual recomputation.

See the [frozen cases and reference conventions](../../benchmarks/si-sr-lda/phase4c/README.md)
and [historical Phase 4C report](https://github.com/xxs4661/dftk-soc-workbench/blob/8658992afa936f6cdb1a8055699ae9aa47b32297/results/phase4c-review.md).
C is a corresponding-source convention prediction, not a numeric extraction of
the installed QE binary's internal G=0 coefficient. The binary source commit
remains unconfirmed. This curation performs no SCF and establishes no SOC result.
