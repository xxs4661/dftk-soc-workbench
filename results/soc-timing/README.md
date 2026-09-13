# Bounded Si timing and controlled cancellation

Three fresh, two-map diagnostics completed with the existing Si SOC core. All
worker/recorder exits were **0/0**, with status
`DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED`, confirmed runtime/storage release and
owned-process cleanup. There is no `final.bin`, converged endpoint or Γ spectrum.
The B0 reference and timed paths satisfy the previously declared same-map
numerical contract. No performance optimization was made.

The directly observed K4 cost is dominated by validation boundaries: four
boundary groups total **637.454 s**, versus **242.201 s** in LOBPCG and **0.351 s**
in checkpoint serialization/write calls. This does not reconstruct the missing
timing of the canceled K6 run, or establish instrumentation overhead.

## Inputs, versions and execution

The [plan](../../benchmarks/soc-timing-v1/plan.md) was committed before changes at
`7c784e7` (an ancestor of the execution). Numerical E0 is
`30befbc22ee52283a19a96694bfe20259891b583`; the independent REF checkout actually
loaded its methods. The clean execution/adapter commit E1 is
`5830d69ce73c201875dca373f5cdf1f98a63e133`. Both TIMED jobs loaded E1. Source hashes,
actual method locations and package/environment receipts are in
[execution identities](execution-identities.json.gz); raw and public hashes are
separate in [raw identities](raw-identities.json) and [runs](runs.json).

The original [B0](../../benchmarks/si-soc-splitting-v1/case.json) and
[K4](../../benchmarks/si-soc-sensitivity-v1/K4/case.json) bytes were retained:
two Si atoms, the same NC-FR-PBE/NLCC input (SHA-256
`cc91a6be43c3c89daf6c34410096e8d870f25152dbfb513bcf01afa5ab53eabf`), 30 Ha,
48³ FFT, 8 electrons, tau 0.001 Ha, 24+6 states, seed 81001, alpha 0.1,
eigensolver tolerance 1e-10/maxiter 300. The physical controller max_maps=400
is unchanged; a precise callback stop bounds each new diagnostic at two maps.
Each starts from the prescribed uniform density. No historical/pilot state is used.

Actual platform: macOS arm64, Julia 1.12.7, Python 3.12.14; Julia/BLAS/FFT/MPI
all 1. Frozen DFTK 0.8.0 at `2f51b91213e26726fb9c6a17e5fae235a1412d01` and
PseudoPotentialIO 0.3.3 at `fec942781560c391f20214ba4cd85fb2431deb84` loaded from
the authenticated checkouts. Project, Manifest, source lock, physical inputs,
`src/soc_kernels`, upstream code and all old result bytes were not modified.

| Task / run suffix¹ | Complete maps | Monitored wall (s) | Per-map wall (s) | Sampled group peak / worker highwater (GiB) | Budget |
| --- | ---: | ---: | --- | --- | --- |
| T-B0-REF / `20260913T154940049438Z-c4386456` | 2 | 84.045760 | unavailable / unavailable | 2.1433 / 2.1152 | 15 min |
| T-B0-TIMED / `20260913T155204973464Z-c0cdaeaf` | 2 | 86.063893 | 39.859425 / 24.418722 | 2.2649 / 2.2369 | 15 min |
| T-K4-TIMED / `20260913T155409589722Z-ae671958` | 2 | 982.263320 | 502.295240 / 444.223802 | 3.6098 / 3.7613 | 30 min |

¹ Full run_id is task + `-` + suffix. Each task started once. The entire batch,
including inter-task gaps, was **1251.864 s / 20.864 min**, within 60 min.
All used 8 GiB / 7 GiB warning and a fixed 2 GiB remaining-growth allowance.
The policy uses max(cumulative sampled group peak, reported worker highwater),
not their sum or just current RSS. No resource/time request or forced signal was
observed in these three runs. These finite observations are not an SCF peak bound.

## Numerical observation and timing boundaries

| B0 same-map test | Map 1 | Map 2 | Declared limit |
| --- | ---: | ---: | ---: |
| absolute ΔE = absolute ΔF (Ha/cell) | 7.2831e-14 | 6.5725e-14 | 1e-10 |
| density relative L2 | 4.5268e-13 | 4.5509e-13 | 1e-10 |
| maximum raw 24-level difference (Ha) | 6.9389e-15 | 6.9944e-15 | 1e-9 |

No spectral reference was fitted. The [pair receipt](b0-equivalence.json) records
the actual comparison of newly exported private densities; public replay cannot
repeat that array norm. The full published [map spectra and occupations](map-spectra.json.gz)
let replay independently recompute ΔE/ΔF and raw-level maximum/RMS. The
[solver records](solver-records.json.gz) retain all 160 per-k records and native
residuals, iterations and matvec counts. [Map summaries](maps-summary.json) include
all six raw E/F values and fixed-point residuals, which remain unconverged.

B0 total iterations were 438/441 and solver column applications 11303/11327.
The initial map-1 subspace hashes match, but observed work counts are not identical.
Their cause is not isolated. **OVERHEAD_NOT_ESTABLISHED** applies: two cold runs,
with different observed iteration work, do not measure timer overhead or speedup.

| Timing coverage | B0 TIMED (s) | K4 TIMED (s) |
| --- | ---: | ---: |
| Closed worker span (sum of disjoint self times) | 84.024451 | 980.412763 |
| Named-stage self time | 73.177430 | 968.789831 |
| Structural/container self, cause unclassified | 10.847021 | 11.622931 |
| Monitor duration minus worker span, unattributed | 2.039443 | 1.850558 |
| Runtime entry + return checks | 8.708888 | 422.277245 |
| Checkpoint validation before + after | 5.067895 | 215.176467 |
| LOBPCG body | 30.824502 | 242.201227 |

Rows below the coverage decomposition are selected subsets, not extra durations
to add to it. [timing.csv](timing.csv) retains 2816 scalar spans; [phases.csv](phases.csv)
and [derived summaries](runs-derived.json) expose counts and self/inclusive totals.
Hierarchies close without missing or conflicting span records. Second maps are
subsequent maps, not proven fully compiled/warm maps. REF timing stays disabled;
its absent map start/end measurements remain null.

[Clock and span definitions](timing-schema.md) distinguish independent parent,
worker and UTC durations. The old `elapsed_seconds` expression has its original
boundaries, including guards/explicit checks and excluding later callback work;
it is not pure LOBPCG. Existing scientific checks, payload fingerprints and
per-k/map checkpoints remain. The old extra profiling observer's object-size /
serialization-size survey is not part of this diagnostic route; no profiler,
forced GC or hot-matvec logging was added. Whole-map callback k labels may retain
the last k; per-k timing follows `k_total` ancestry. Write calls do not measure
physical disk-flush latency. The final timing flush is measured separately;
final result writing and process exit are outside the worker span.

## Control tests, replay and limits

[Control tests](tests-summary.md) and [individual receipts](cancel-tests.json)
record actual synthetic launcher→worker→recorder outcomes, including cooperative
130/124, raw Julia SIGINT −2, failed/missing/contradictory receipts, write failure,
latched requests, and owned-child escalation. The successful suite had 13 tests
and 12 launched fixtures. Some intentionally surviving descendants needed signals;
those forced-cleanup flags are retained. Synthetic recorded cancellation is not
scientific PASS. The cumulative communicated signal-test budget was about
112.317 s against 300 s, including earlier failed attempts and legacy regressions.

Preparation failures are retained: sandbox process-list denial; the TOML wider
integer timestamp bug; fixture cleanup assumptions; three check-entry processes
that exited 0 but emitted no identity receipt; and a syntax error in the first
local offline analysis invocation. The entry binding bug was reproduced in a real
stdlib Julia script, then fixed before any numerical slot started. The three
final clean entry checks all passed explicit receipt/source/environment/no-context
validation. A later public-checker change strengthens numbered-map, duplicate-task
and source binding; it does not change E1 or rerun any numerical slot.

```sh
python3.12 -B benchmarks/soc-timing-v1/replay.py
python3.12 -B -m unittest discover -s tests -p 'test_soc_timing_analysis.py' -v
```

This read-only entry checks public byte identities, span arithmetic and B0
energy/spectrum arithmetic. It runs no SCF and reads no private density. The
[existing researcher entry](../../docs/getting-started.md) retains its frozen
historical checker and scientific review flags. For an already active diagnostic,
the [control tool](../../benchmarks/soc-timing-v1/control.py) provides
`stop --run-dir CANONICAL_RUN_DIRECTORY --run-id RUN_ID --execution-commit E1`;
ordinary cancellation first writes a bound cooperative request. Its 120+10+5 s
escalation is confined to observed owned processes. No canceled run may publish
SCF PASS or `final.bin`; no resume capability is certified.

The public arithmetic suite passed 24 tests; driver/entry tests passed 11, and
stdlib timer/controller checks passed 101 assertions. Validation commands, exits
and preparation evidence are in [preparation checks](preparation-checks.json.gz)
and [later arithmetic checks](post-execution-checks.json.gz). New full raw output, binary
checkpoints, analysis scripts and preservation receipts are kept locally and in
the repository-external `soc-timing-cancellation-20260913` incremental archive.
Native streams are [retained with only path redaction](native-streams.json.gz);
legacy executor filenames `qe.stdout`/`qe.stderr` do **not** imply a QE invocation.
Final clone/backup verification is recorded in [delivery checks](delivery-checks.json).

The canceled K6 remains unchanged: archive
`k6-attempt2-user-stop-20260913T134733Z-a5e78d3f`, analyzer SHA
`d31bb92d6825ab32cadae751ac1a242f9e0c6779817cdc415390a8cf53781c86`.
Only nine relevant small archived files were checked. Its 19 complete maps plus
15 partial-map-20 solves, 70931.933 s interval, 26899.724 s legacy per-k sum and
44032.209 s unattributed remainder remain historical. User cancellation, native
−2 / recorder 9, process exit with runtime close unconfirmed, no qualified endpoint
and resume unverified are unchanged. No old 409-file archive was recopied.

At most three follow-up investigations, requiring separate authorization:

1. First, trace why the existing immutable-source/runtime boundary checks dominate
   K4, preserving the checks while identifying exactly which certification is repeated.
2. Examine checkpoint validation separately from its much smaller serialization/write
   call cost; this evidence does not justify removing a check or claim an I/O bottleneck.
3. Inspect the remaining container/first-call and solver-work differences using their
   recorded identities; GC, native-library detail, late SCF maps and old K6 proportions
   remain unknown.

No K6/K8, Γ, QE/pp, full SCF, CI, new material, optimization or Phase 9B was run.
Existing 9A completion and all physical/manifold/performance review limitations remain.
