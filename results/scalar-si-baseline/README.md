# Si scalar baseline: B0

Historical execution and input comparability: PASS. Numerical agreement:
REVIEW_REQUIRED. This scalar evidence curation reruns no SCF or QE.

| Native quantity | DFTK | QE |
| --- | ---: | ---: |
| Total energy (Ha/cell) | -8.42888453274439 | -8.42888019560495 |

Raw maximum spectral difference: 1.34433699321849 eV.
With one sampled global HOMO reference per program, maximum difference:
8.47354046489931e-06 eV. No per-k shift or total-energy
correction is applied. The raw offset is retained and is not wholly attributed
to a gauge by this comparison.

[B0 native/normalized evidence](B0/result.json), [QE XML](B0/qe-data-file-schema.xml),
[QE stdout](B0/qe.stdout), [QE warnings](B0/qe.stderr), [DFTK stdout](B0/dftk.stdout),
[DFTK result](B0/dftk-result.json), [raw and referenced levels](B0/comparison.json)
and [provenance](evidence.json) support offline review. The original B0 result,
parsed QE result, comparison and case bytes remain golden regression fixtures.
The [shared environment](../shared/environment.json) is authoritative. The embedded
B0 environment is preserved only as part of the immutable golden fixture; its
entire object must equal the shared identity during every public check.
One copy of each repeated warning stream is referenced by its actual occurrences.

Use Python 3.9 for exact historical floating-point reductions:

```sh
PYTHONDONTWRITEBYTECODE=1 python3.9 scripts/curate_scalar_evidence.py --check
```

The [frozen input](../../benchmarks/si-sr-lda/case.json) retains eight scalar bands,
eight electrons, LDA/PW92 and NLCC. [Physical reproduction instructions](../../benchmarks/si-sr-lda/README.md)
require the hash-checked Si UPF and frozen runtime. No UPF or cache is published.
See [finite sensitivities](../scalar-si-sensitivity/README.md) before interpreting
this smoke baseline as convergence.

DFTK's historical solver-history zeros do not establish zero physical residuals;
independent B0 orbital-residual recomputation is NOT_RUN. QE per-band residual
norms are not available. QE stderr reports IEEE floating-point exception flags;
these remain visible despite normal exit and final convergence. The binary's
source commit is NOT_CONFIRMED. Package and binary identities are preserved in
[evidence.json](evidence.json) and the immutable B0 record.

The [historical Phase 4B report](https://github.com/xxs4661/dftk-soc-workbench/blob/8658992afa936f6cdb1a8055699ae9aa47b32297/results/phase4b-review.md)
retains the two failed attempts: a parser tag mismatch after converged QE and a
DFTK metadata accessor failure before SCF. Neither is recast as new calculation
success or physical nonconvergence.
