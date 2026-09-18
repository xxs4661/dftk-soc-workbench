# Si boundary-validation candidate: equivalent maps, slower execution

The opt-in `single_validation_v1` candidate passes the declared B0/K4 same-map
numerical limits and the separate synthetic protection tests. **Both K4 performance
targets fail.** Validation-related self time increases by 34.60%, and monitored
wall time by 25.55%. This is a failed performance candidate, not an accepted speedup;
the ordinary strict path remains the default. Do not promote this candidate based
on its numerical agreement.

All four new tasks completed exactly two maps, with native worker / recorder
exits **0 / 0**, status `DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED`, confirmed runtime,
workspace and owned-process cleanup. No task created `final.bin`. No extra attempt,
full SCF, Γ, K6/K8, QE, profiler, parameter scan or CI was run. Existing completed
9A results and the canceled K6 record remain unchanged.

## Versions, boundaries and input

- Reference R: `d9e19af3557c923a1e4f7e64510092d47975cc7c`, loaded from an independent clean checkout.
- Initial design commit: `f7283e415556a97e7aa743bda5a7fb7be1eab586`.
- Frozen numerical/adapter execution E: `761e09d8fe99f99fcccb0f1b10704916d336ccb8`.
- REF uses R numerical methods; OPT uses E and explicitly selects the candidate.
  Both use the same E adapter and enabled timing. Actual method locations, source
  hashes and environment receipts are in [identities](identities.json.gz).
- macOS arm64, Julia 1.12.7, Python 3.12.14; Julia/BLAS/FFT/MPI each 1.
  Frozen DFTK `2f51b91213e26726fb9c6a17e5fae235a1412d01` and PseudoPotentialIO
  `fec942781560c391f20214ba4cd85fb2431deb84` were loaded; both checkouts clean.

The [design](../../benchmarks/soc-boundary-v1/plan.md) and executable
[contract](../../benchmarks/soc-boundary-v1/contract.json) were fixed before execution.
The unchanged [B0](../../benchmarks/si-soc-splitting-v1/case.json) and
[K4](../../benchmarks/si-soc-sensitivity-v1/K4/case.json) specify two-atom Si,
FR-NC-PBE/NLCC, UPF SHA-256
`cc91a6be43c3c89daf6c34410096e8d870f25152dbfb513bcf01afa5ab53eabf`,
30 Ha, 48³ FFT, 8 electrons, tau 0.001 Ha, 24 physical + 6 auxiliary states,
seed 81001, alpha 0.1 and original solver tolerance 1e-10/maxiter 300.
Each task starts afresh from the prescribed uniform density. Controller max_maps
remains 400; the original precise diagnostic stop limits each execution to two maps.

The only numerical-adapter candidate changes are in
[hamiltonian.jl](../../prototypes/fr_integration/hamiltonian.jl) and
[runtime.jl](../../prototypes/fr_integration/runtime.jl). A fresh memo lives within
one synchronous validation call: identical issued source bundles and canonical
dense array digests can be reused inside that call. Every occurrence retains
identity, shape, label and binding checks. Dense Float64/ComplexF64 arrays use
exactly the old digest bytes without a preliminary copy; other layouts use the
old copy/vec/reinterpret/SHA expression and clear the array memo. No certification
crosses an unknown callback, numerical action, checkpoint, return, error or close.
All original runtime and checkpoint boundaries remain. The source loop finishes
before array fallbacks; this narrow ordering does not authorize arbitrary future
interleaving with side-effecting array implementations.

## Four fresh diagnostics

Full run IDs are the task plus the suffix below. These are new R/E comparisons;
the historical T-* runs and their 637-second subtotal were not reused as reference.

| Task | Run suffix | Monitor wall (s) | Map 1 / 2 span (s) | Sampled peak / reported worker highwater (GiB) |
|---|---|---:|---:|---:|
| V-B0-REF | `20260918T163335199429Z-421d1b9a` | 81.256641 | 37.860032 / 23.891245 | 2.1529 / 2.1252 |
| V-B0-OPT | `20260918T163537622651Z-28c96042` | 87.788789 | 40.822027 / 26.122078 | 2.0141 / 1.9868 |
| V-K4-REF | `20260918T163741147858Z-37f8e6d7` | 974.248941 | 496.227459 / 442.681855 | 3.4088 / 3.4408 |
| V-K4-OPT | `20260918T165415932661Z-f966fd9e` | 1223.181584 | 621.822302 / 565.349133 | 3.4053 / 3.3829 |

The batch through the final comparison took **2480.277 s (41.34 min)**, including
launch/compilation/output and inter-task gaps, against 90 minutes. B0 pairs were
qualified before K4; K4 REF was qualified before OPT. Each slot was consumed once.
All tasks used 8 GiB / 7 GiB warning / 2 GiB fixed growth. Policy takes
max(sampled group peak, reported worker highwater), not their sum or current RSS.
K4 REF/OPT max-plus-reserve was 5,841,960,960 / 5,803,933,696 bytes, below
8,589,934,592. No stop request or forced signal occurred. These are finite resource
observations, not a guaranteed bound for complete SCF. Worker highwater is the last
reported `Sys.maxrss()`, not an independently collected post-exit getrusage value.

## Same-map numerical comparison

Differences below are OPT minus REF. No spectrum shift, state fitting, density
renormalization or comparison against a converged historical endpoint is used.

| Profile / map | ΔE = ΔF (Ha/cell) | Density relative L2 | Raw 24-level max difference (Ha) |
|---|---:|---:|---:|
| B0 / 1 | +9.5923e-14 | 5.2377e-13 | 6.7168e-15 |
| B0 / 2 | −1.4211e-14 | 8.0427e-13 | 6.8279e-15 |
| K4 / 1 | +1.4211e-14 | 2.2397e-13 | 1.1324e-14 |
| K4 / 2 | −6.3949e-14 | 2.3944e-13 | 1.0880e-14 |
| Fixed limits | 1e-10 each | 1e-10 | 1e-9 |

The density denominator is max(norm(REF), norm(OPT), 1). [runs.json](runs.json)
retains all norms, differences, denominators and acquisition hashes. Public replay
checks that arithmetic; the full density comparison remains **runner-reported**,
using this batch's private 48³ Float64 exports. It does not read the binary
checkpoints. [data.json.gz](data.json.gz) supplies every raw E/F and seven energy
terms, all spectra/occupations, original scientific diagnostics, solver records
and closed scalar spans. Coordinate matching uses the declared k points, not
energy closeness. Electron, Gram, Pauli, FD/tail and energy/own-density checks retain
their original thresholds.

Map 1 / 2 fixed-point residuals in both paths are approximately 0.468935/0.411977
for B0 and 0.450571/0.394303 for K4. They are **not converged SCF endpoints**. First-map initial
subspace hashes match at 8/8 B0 and 64/64 K4 points. Second-map hashes differ: each
run uses its own previous orbitals, not another run's state. Workload is not identical:

| Profile / map | REF / OPT iterations | REF / OPT solver RHS-column matvec equivalents |
|---|---:|---:|
| B0 / 1 | 266 / 263 | 6799 / 6768 |
| B0 / 2 | 176 / 175 | 4541 / 4524 |
| K4 / 1 | 2352 / 2358 | 55845 / 55857 |
| K4 / 2 | 1656 / 1663 | 39271 / 39326 |

## Cost and protection evidence

| Disjoint measured self-time quantity | K4 REF (s) | K4 OPT (s) | OPT / REF |
|---|---:|---:|---:|
| All declared validation + mixed categories | 727.378321 | 979.083072 | 1.346044; target ≤0.50 **NOT MET** |
| Old four runtime/checkpoint boundary groups | 629.911745 | 876.451984 | auxiliary subtotal |
| LOBPCG body | 241.034651 | 237.811722 | workload context |
| Whole monitored wall | 974.248941 | 1223.181584 | 1.255512; target ≤0.80 **NOT MET** |

[phases.csv](phases.csv) is regenerated from closed spans. Only self times are
summed; parent/child inclusive durations are never added twice. The contract
conservatively includes mixed initialization, controller, callback, density and
energy stages containing unseparated checks. Those totals are not pure hashing
or certification time. New memo/setup/cleanup costs stay inside these categories.
Worker spans total 972.192110 / 1221.203590 s; monitor-minus-worker is 2.056832 /
1.977994 s, **unattributed**. Final timing flush is separately recorded; final
receipt writing and process exit lie outside worker_total. Write-call spans do not
measure physical disk flush. Legacy `elapsed_seconds` retains its original bounds.

The complete REF/OPT boundary dictionaries match: 142 successful B0 runtime
boundaries and 814 K4 boundaries, including close (conversion/close markers are
excluded from the count). Checkpoint before/after counts are 22/22 and 134/134;
no checkpoint or protection was removed. Candidate counters after close:

| Counter, actual opt-in instrumentation | B0 | K4 |
|---|---:|---:|
| context / all-k scan entries | 148 / 148 | 820 / 820 |
| full source validations / same-call source reuses | 148 / 148 | 820 / 820 |
| completed array hashes / digest reuses | 10048 / 266 | 467008 / 1610 |
| completed array-hash bytes | 9926528760 | 446722059384 |
| fallback hashes / memo invalidations | 1064 / 1064 | 51520 / 51520 |
| maximum live array / source entries | 28 / 1 | 196 / 1 |
| live entries after close | 0 / 0 | 0 / 0 |

These bytes are cumulative work, not resident memory. They exclude source
serialization snapshots, constructor certificates, payload/settings/density hashes.
All-k entries are calls entering the G loop, not k iterations or every storage
traversal. R's internal hash/byte/reuse totals were **NOT_MEASURED**: R was not
instrumented or modified, and missing counters are not zero. Its successful boundary
events imply at least 814 context/G checks in K4, a source-derived lower bound only.
No measured net hash-work reduction is established. Conservative fallback clears
can lose the old `_check_storage` local memo's reuse; their contribution to the
observed slowdown is a candidate explanation, not an isolated timing attribution.
Actual fallback types were not recorded. No follow-up measurement or tuning occurred.

Protection equivalence is separate from the numerical pair. The actual validation
bodies from R, current default and OPT passed **1172 synthetic assertions** across
41 sequential fault kinds, including P/D/potential/G/source replacement, callbacks
that mutate and throw, stale/foreign tokens, reentry, aliasing and close/error paths.
Dense/complex/signed-zero/view hash bytes match the old convention; defaults and
RNG consumption are tested. Artificial provider objects are not physical UPFs.

## Checks, failures and replay

The preparation/check archive is [checks.json.gz](checks.json.gz), successful
source-bound coverage is [protection.json.gz](protection.json.gz), and native logs
are [native-logs.json.gz](native-logs.json.gz). Raw, public-text and compressed
hashes are distinguished; full local processes and arrays are incrementally backed
up outside Git. The backup is on the same machine, not off-site, and byte restore
is not proof of exact SCF resumability.

- 1172 Julia protection assertions, 101 timer assertions and parsing of all 119
  tracked Julia files passed. Four fresh no-context entries loaded R/E methods and
  the frozen environment without context construction or slot consumption.
- Final relevant Python suites: 81 tests passed (13 registration, 33 public protocol,
  11 legacy driver, 24 legacy analysis). Controlled process/resource suites: 30 tests
  passed. Explicit inherited control/timer helper bytes are recorded in the gate.
- Cumulative real synthetic-control testing: 44.852 s of the 300-second allowance.
  New adapter cooperative cancel and independent timeout produced 130 and 124.
  These are synthetic control tests, not material SCF cancellation results.
- Preparation failures are preserved: one old SIGINT fixture received timeout 124
  instead of caught InterruptException; deterministic wait readiness was repaired,
  without changing production stop rules or its single authenticated SIGINT/assertions.
  The handler-level cause of the missed SIGINT was not established.
  An overbroad test discovery ran a historical extra hash checker in the wrong tree
  and exited 1; no hash was changed. At its proper fixed `e40def9…` snapshot,
  that suite subsequently passed all 20 tests, exit 0. New public-protocol negatives first exposed 24
  failures, followed by one synthetic category-total expectation correction, before
  all 33 final cases passed. None consumed a numerical slot.

```sh
python3.12 -B benchmarks/soc-boundary-v1/replay.py
python3.12 -B benchmarks/soc-boundary-v1/replay.py --strict
python3.12 -B benchmarks/soc-boundary-v1/replay.py --tables /tmp/new-boundary-tables
```

Default replay exits **0** for public identity/arithmetic consistency; strict
optimization acceptance exits **1**, because both performance targets fail.
The tables command needs a writable output directory and changes no original data.
This is public arithmetic replay, not another SOC calculation or a repeat of
private density acquisition. Final clone checks and incremental backup restoration
are summarized in [verification.md](verification.md).

One cold ordered pair is not a statistical performance result. Ordinary workstation
activity was not isolated; solver work differs slightly, and full SCF scaling,
K6 timing, allocation-volume changes and per-fallback cost remain unestablished.
The old canceled K6 retains user-cancellation, native −2 / recorder 9, unconfirmed
runtime shutdown, no qualified endpoint and unverified resume capability. No
consumed authorization was reopened. This AI-assisted candidate awaits human review;
no next scientific stage is authorized by this result.
