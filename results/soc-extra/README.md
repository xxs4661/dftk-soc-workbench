# Si retained-core validation and K6 resource outcome

The existing core is retained, and a fresh Si B0 SCF/own-density Γ regression
passes. The K6 pilot completed its two permitted maps, but the one formal K6 SCF
attempt stopped under the predeclared resource-headroom rule before convergence.
No workbench K6 Γ spectrum or new K6 D−QE comparison is available. This outcome
does not revoke the completed Phase 9A core result.

Numerical execution: `96795a6b2bf2ca4f6c8dcf6546287eb95bfe4504`.
Technical/public baseline: `7630172808773a3d4ac2da825c27fe43a8705fb8`.
Performance execution: `e90f9ab1916b24c6118cf670dee1a78f98cdcff6`.
Later public postprocessing is identified by the containing Git commit; it does not relabel numerical E.
The source-bound workers retain the `soc-core` backend and frozen Julia 1.12.7,
DFTK `2f51b91213e26726fb9c6a17e5fae235a1412d01`, and PseudoPotentialIO
`fec942781560c391f20214ba4cd85fb2431deb84` environment. No optional core candidate
was applied. Upstream files, dependency versions and physical inputs were not
changed for the computations. The SCF map, LOBPCG/FD body and old refusal checks retain their baseline bytes. Only explicit extra routing, case validation and bounded observation/stop hooks were added; the altered diagnostic retention required the fresh B0 regression.

## Public evidence and replay

The [fixed plan](../../benchmarks/soc-extra-v1/plan.json),
[sources](../../benchmarks/soc-extra-v1/sources.json), explicit
[B0](../../benchmarks/soc-extra-v1/B0.json) / [K6](../../benchmarks/soc-extra-v1/K6.json)
inputs and [resource policy](../../benchmarks/soc-extra-v1/resource-policy.md)
precede execution. [Canonical numerical data](data.json.gz) are losslessly
compressed; [the manifest](evidence.json) binds selected raw/public/gzip identities.
All fresh B0 final SCF eigenvalues/occupations, its Γ24 spectrum, raw E/F/entropy,
seven energy terms and compact completed/failed map traces are retained. No
qualified final K6 data exist. Large private arrays are not duplicated publicly.

```sh
python3.12 -B benchmarks/soc-extra-v1/replay.py
python3.12 -B benchmarks/soc-extra-v1/replay.py --require-k6
```

Use an existing Python 3.12 and complete local Git history. Default exit 0 means
consistent public arithmetic, including explicitly failed/unrun slots; it does
not mean K6 passed. Strict mode additionally requires a qualified K6 pair and
both unchanged 0.1 meV screens. The commands start no Julia or electronic
structure and read no private checkpoints. The existing researcher
[`review.py core-regression`](../../scripts/README.md) checks the older fixed
completion snapshot; its success cannot replace this new evidence replay.

Historical QE K6 is authenticated and reparsed from its existing native public
files, not rerun. Its Γ split is approximately 47.836247741 meV. New D−QE and
K4→K6 response differences remain **NOT_ASSESSED** without a qualified D endpoint.
Its 157 SCF solver-warning lines and IEEE scope remain preserved. A later
comparison with historical legacy K4 would span implementations, not constitute
a same-new-core k-only control experiment.

## Core regression and finite performance

| B0 regression against completed 9A | Recorded new − historical | Unchanged limit |
| --- | ---: | ---: |
| Internal energy E | −1.7763568394002505e−15 Ha/cell | 1e−8 Ha |
| Free energy F | −1.7763568394002505e−15 Ha/cell | 1e−8 Ha |
| Density relative norm | 3.2265288173360495e−13 | 1e−8 |
| Raw Γ24 maximum level difference | 6.4698246760031e−14 Ha | 1e−7 Ha |
| Fixed-window Γ split difference | +1.5105972028806036e−14 eV | 1e−6 eV |

The fresh B0 SCF and Γ each have outer/native exits 0/0; saved regression gate
PASS/0, actual core dispatch and closed/released workspace checks pass. Sampled
process-tree peaks are 2,554,167,296 B and 1,693,384,704 B. Full values, historical identities and density-comparison scope are in the
[public data](data.json.gz). Density-array differences remain runner-reported;
this is a workbench regression, not a new QE pair.

Four operations on authenticated B0/K4 inputs each retain one warmup and five
samples. The pipeline median times are 4.252856458 / 30.34585 s, with cumulative
allocation medians 2,303,581,160 / 15,840,422,600 B. They are different workloads,
not a measured optimization speedup. The finite profiles do not establish the
predeclared benefit from the one permitted hash-input-copy candidate, so it was
not attempted. Cumulative allocations, retained objects and profiler-inclusive
RSS remain separate in [the full samples](performance.json) and [diagnosis](diagnosis.json).

Time is seconds and allocation is cumulative bytes per operation. Ranges retain
all five samples; profiler calls are separate.

| Case | Operation | Time median [min–max], s | Allocation median [min–max], B |
| --- | --- | ---: | ---: |
| B0 | `FR_1` | 0.000557542 [0.000540208–0.000579958] | 4,928 [4,928–5,152] |
| B0 | `FR_24` | 0.003146167 [0.002960292–0.003279917] | 4,992 [4,992–5,216] |
| B0 | `full_H_24` | 0.041604166 [0.041572791–0.054458417] | 1,794,880 [1,794,880–1,794,880] |
| B0 | `pipeline_with_validation` | 4.252856458 [4.226693708–4.391516708] | 2,303,581,160 [2,293,717,992–2,320,229,192] |
| K4 | `FR_1` | 0.000612709 [0.000593541–0.000624417] | 4,928 [4,928–5,152] |
| K4 | `FR_24` | 0.003094292 [0.003031208–0.003295708] | 4,992 [4,992–5,216] |
| K4 | `full_H_24` | 0.044048708 [0.043766167–0.044221666] | 1,794,880 [1,794,880–1,794,880] |
| K4 | `pipeline_with_validation` | 30.345850000 [30.323356667–30.561479208] | 15,840,422,600 [15,791,433,000–15,858,328,040] |


Prepared unique dense payloads: 109,755,296 B (B0), 566,877,184 B (K4). Whole
diagnostic sampled RSS: 2,727,936,000 / 5,282,562,048 B, including profiling and
export. Cold build/load, GC/compilation and object inventories remain in the
full sample record. These are distinct measurements, not an SCF timing or
peak-memory decomposition.

## K6 pilot, formal stop and scientific consequence

| Operation | Actual outcome | Native / outer exit |
| --- | --- | --- |
| X-K6-PILOT | Two complete maps; PILOT_COMPLETED_NOT_SCF_CONVERGED | 0 / 0 |
| X-K6-SCF | FAIL; one complete map, stopped in the second map at a solver-progress boundary | 1 / 1 |
| X-K6-GAMMA | BLOCKED_PARENT; no worker started | null / null |
| Linux B0 SCF/Γ | NOT_RUN | null / null |
| Workbench K6 versus historical QE K6 | NOT_ASSESSED; no qualified workbench endpoint | not a calculation exit |

The pilot sampled 6,432,358,400 B process-tree RSS (native worker high-water
6,619,267,072 B). Its completed maps were resource observations, not SCF
convergence or a warm start for the formal run.

The pre-run source/object estimate was 8,203,424,086 B (7.6400340404 GiB),
including the unchanged 2 GiB runtime reserve. The pilot-based estimate was
8,453,445,814 B (7.8728849199 GiB), including 2,021,087,414 B remaining growth
and at least 1 GiB unobserved fluctuation within that growth. These distinct
estimates admitted only `PROVISIONAL_GO_WITH_MONITORING`, with 136,488,778 B
headroom on the latter estimate. The subsequent observation invalidated the
remaining-headroom screen; provisional admission was not a peak-memory guarantee.

Formal run `X-K6-SCF-20260912T125749806970Z-9b5c1377` completed map 1 with unmixed
residual 0.44909426504123184. The saved solver rows contain all 216 k points of
map 1 and k1–k73 of map 2. The map-2 receipt is FAIL and contains no `n_out`.
The raw worker's `completed_maps=2` counts these two receipts, including failure;
it must not be presented as two completed density maps. Runtime close, workspace
release and process cleanup passed after the failure.

The recorded screening arithmetic is:

```
sampled peak       7,447,937,024 B  (6.9364318848 GiB)
fixed growth       2,021,087,414 B
projected screen   9,469,024,438 B  (8.8187162187 GiB)
unchanged limit    8,589,934,592 B  (8 GiB)
```

The automatic monitor implemented this headroom check only after sampled RSS
reached 7 GiB, missing the below-7-GiB/insufficient-headroom branch. The agent's
read-only review therefore requested the existing safe-boundary stop according
to the predeclared user/plan rule. The recorded runtime omission remains for review before future runs.
No parameter, source, threshold or fixed
growth allowance was changed. A later decrease in RSS does not erase the peak
or justify reducing that allowance. This is an engineering-screen exceedance,
not measured sampled RSS reaching 8 GiB, an OOM event or a proven future peak.
Worker-native high-water was 7,528,939,520 B and has a different observation
scope. The sampler's resource-status PASS only means its own threshold/cleanup
record passed; the scientific worker and overall run remain FAIL/1.

K6 Γ and K4→K6 workbench splitting/response comparisons are unavailable. The
historical QE K6 evidence is preserved but cannot replace the missing endpoint.
The declared 0.1 meV window is unchanged; no new comparison is marked passing.

## Preserved failures and limits

The first performance preparation attempt remains native/outer 9/9 before any
warmup, sample or profiler call. The separate [Γ entry-only record](gamma-entry-failure/evidence.json) remains
outer/native 9/0 for missing echoed parent hashes; its independent diagnosis
and successful later formal Γ are not a retroactive entry-check PASS. At E,
`diagnosis.json` still references the pre-compaction performance byte hash;
that exact binding check failed. The reference is now corrected in separately
identified public postprocessing, with parsed performance numbers unchanged.
Historical scientific results and failures remain intact.

B0 Γ occupation saturation remains REVIEW_REQUIRED (0.9999595249412169 versus
0.99999999); complete manifold assignment remains REVIEW_REQUIRED and full
physical convergence NOT_ESTABLISHED. Workbench K8 is NOT_RUN. Mg disagreements,
reconstructed-field and native-nonlocal-energy limitations, and unresolved IEEE
origins are not resolved by this work. No QE/pp, CI, new material or Phase 9B
execution was added. Linux public replay is not a Linux SCF.

Public arithmetic and check commands, actual exits and selected native logs are
recorded in [checks.json](checks.json). The initial current-tree historical
continuation test exited 1 on five old source hashes; its fixed-baseline replay
passed. The monitor headroom counterexample also exits 1: the frozen monitor
returns CONTINUE below 7 GiB despite the fixed peak-plus-growth screen failing.
The new read-only public layer checks that arithmetic and preserves the failed
SCF. It does not claim the frozen runtime monitor was repaired; this omission
and the entry-only parent-hash echo need review before future numerical work.

Complete profiling, checkpoints and process records belong to the incremental
repository-external archive, with actual restore receipts kept outside Git.
Only this development branch is submitted; the default main homepage is not
newly published. The local maintainer note is prepared, not sent.

Run identities are in the canonical data; sanitized original native command
arrays and their raw receipt hashes are in [checks.json](checks.json). Numerical
commands were `scripts/run_si_dftk.py` with each explicit extra action/profile,
source authorization and E; Γ additionally bound its own parent. Runs were
X-B0-SCF-20260912T095142925295Z-5beddab2,
X-B0-GAMMA-20260912T104611503053Z-d095fe92,
X-K6-PILOT-20260912T104806269817Z-c3066352, and
X-K6-SCF-20260912T125749806970Z-9b5c1377. Every executed numerical slot was used once.
