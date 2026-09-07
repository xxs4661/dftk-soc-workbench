# QE local ionic potential: bound postprocessing audit

The two permitted pp.x slots completed once each from independent, authenticated
copies of the original G40 save. P0 registers on all **64000** physical nodes and
all **17** fixed complex modes. The reconstructed P2 mean supports the prior
G=0 prediction within native decimal-print precision. This is
**QE_PP_RECONSTRUCTION_BOUND_TO_HISTORICAL_G40**, not the historical SCF
in-memory potential or a private `tab_vloc(0)` measurement.

[Plan and inputs](../../benchmarks/mg-soc-qe-local-potential-v1/README.md) ·
[Evidence and run IDs](evidence.json) · [Complete comparison](comparison.json) ·
[Bound DFTK field receipt](saved-field-receipt.json) · [Full review](../phase7e-review.md)

| A−G40 partition | meV/cell |
| --- | ---: |
| Historical total E difference | +0.624440842 |
| Local combination L+Pc difference | +0.783189640 |
| ↳ density response | +0.213944969 |
| ↳ nonzero G shape at Q_rep | +0.115609946 |
| ↳ G=0 bookkeeping contribution | +0.453634725 |
| Remaining O combination | −0.068908841 |

The three indented scientific subterms partition the local combination, and
must not be added to that parent again. The residual's print halfwidth is
0.000520741 meV/cell; it is a decimal-output bound, not the total error of the
reconstruction. The derived QE T+NL-shaped ledger remainder is **not** an
independent measurement of either operator, nor an isolated SOC error.

P2 mean = 0.009185827445232273 Ha; tagged prediction difference
−8.05311e−13 Ha, against mean print halfwidth 1.36988e−10 Ha.
No fitted potential reference, density adjustment or E/F correction is applied.
A's original-array local drift is zero and B's is −1.42109e−14 Ha; public
coefficient reconstruction retains its separate density-source label.

All [potential coefficients](potentials.csv.gz), including G=0 and Nyquist,
and both native filplot files ([P2](P2/local-ionic.pp.gz), [P0](P0/charge.pp.gz))
are public. The existing complete density packs are referenced, not copied.
The shape field L2 is dominated by the DFTK tail outside the saved QE G set;
that tail does **not** contribute to shape_at_Q, whose Q_rep finite series
has no coefficients on that support. No exported high modes are removed.

Use an **already installed** Python 3.12 / NumPy environment (this run used
NumPy 2.3.5) for full public replay; the older arithmetic uses Python 3.9:

```sh
python_numpy scripts/check_qe_local_potential.py --all --legacy-python python3.9
```

`python_numpy` denotes the caller's existing interpreter, not an installer.
The check replays full FFTs, direct 17-mode sums, all-node registration,
coefficient integrals and every print-bound calculation using public files and
Git history only. It never reruns pp.x. The authenticated Julia source-array
extraction remains a separate recorded operation, with full raw arrays local.

Both native pp stderr streams contain IEEE_OVERFLOW_FLAG. Normal pp startup
reconstructs local/Hartree/XC potentials; no independent XC calculation or new
SCF/eigensolve was executed. IEEE origin remains NOT_LOCALIZED, numerical review
REVIEW_REQUIRED, physical convergence NOT_ESTABLISHED, and residual attribution
PARTIALLY_QUANTIFIED. The raw sources and frozen scientific code are unchanged.
