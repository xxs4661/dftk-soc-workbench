# Phase 9A continuation — successful Si endpoints

**New SCF, Gamma and endpoint regressions PASS.** The authorized second SCF
attempt completed 180 maps; the first actual Gamma attempt used its final
`n_out`. Both native workers and recorders exited 0. The four original static
suites remain **HISTORICAL_REUSED**. **PERFORMANCE_REVIEW_REQUIRED**, the
insufficient K6 budget and physical interpretation limits remain separate.
The repository-external incremental backup restored and verified **185/185**
files. Final clean-public-clone verification is **PENDING** at this reporting step.

## Identity, inheritance and entry

The existing `codex/phase9a-soc-core-memory` branch continued from partial
publication `98781fd0ce6c2f4138ed010e115a13e370410d58`. The
[continuation plan](../../../benchmarks/soc-core-memory-v1/resume/README.md)
was committed at `234fe85d4e9386d9889bd1af256a28394ba88089` before execution.
Both new numerical tasks and both successful comparisons used clean E
**`281c53525a70cf21c36973956d5303d3201a73eb`**. Reporting is a later commit;
its identity is supplied with the completed delivery, without amending E.

The [original static gate](../gate.json) still belongs to
`1b42a27063ca65757d2c4f34d46fe4f1cd9929ed`, SHA-256
`29621b5bc01245edd6bc1de0a5871636b9851240c271213676f6db3227d06efd`.
REF harness `bbe9aa7755f052900e6e9c4618252a410e1cc8f0` loaded original numerical
source `c764311a5422b5c3cab5a7b78a02d420910c4e56`.
The separate [continuation authorization projection](authorization.json)
binds E to unchanged complete core/adapter/include sets, approved driver bytes,
inputs, environment, all four raw suites and original failed slot. Its original
immutable raw SHA-256 is
`119447d08eb037475696e26829799a56d8bc6865fb7ef438e836a55d9bf7b59b`.
The status is **STATIC_EVIDENCE_REUSED_UNCHANGED_CORE**, not static measurements
performed at E. [Original samples and performance](../performance.json) are
referenced without copying or resampling.

The prior Julia ternary whitespace repair remains. Whole-file parsing still
rejects the exact failed source. The endpoint CLI now uses Git's exact
`D-spectrum.json`; historical files were not renamed or duplicated, and its
numerical `evaluate` body is unchanged. Explicit continuation routing preserves
the default same-commit gate, the original failed slot and the global active
lock. Only this preparation's one SCF 2 / Gamma 1 reservation pair is accepted.

Real `CHECK-ENTRY-20260910T131635Z-4331be25` at E returned native 0 / recorder 0,
**CHECK_ONLY_PASS**: complete definitions, source/environment and routing were
checked with zero contexts, zero registrations and no formal reservation.
Both later workers again authenticated Julia 1.12.7, DFTK 0.8.0 at
`2f51b91213e26726fb9c6a17e5fae235a1412d01` and PseudoPotentialIO 0.3.3 at
`fec942781560c391f20214ba4cd85fb2431deb84`, with clean frozen checkouts.
Manifest SHA-256 remains
`5b8ae036ac430219a95d61a5e3cd20074e9ecd252335253bf7ada81278b08c37`.
Si FR-NC-PBE UPF SHA-256 remains
`cc91a6be43c3c89daf6c34410096e8d870f25152dbfb513bcf01afa5ab53eabf`.

## Actual tasks and unchanged physical contract

| Logical action / cumulative attempt | New run_id | Native / recorder | Result |
|---|---|---|---|
| OPT-B0-SCF / 2 | `OPT-B0-SCF-RESUME-20260910T131756Z-9d9840be` | 0 / 0 | PASS, 180 maps including closure |
| OPT-B0-GAMMA / 1 | `OPT-B0-GAMMA-RESUME-20260910T141203Z-28121ef8` | 0 / 0 | PASS, single Gamma with 24 states |

[Slot records](endpoints.json), [SCF worker](OPT-B0-SCF/worker.json),
[all compact maps](OPT-B0-SCF/trace.json) and
[Gamma worker with all 24 levels/occupations/residuals](OPT-B0-GAMMA/worker.json)
retain source, native and resource bindings. Public projections have their own
hashes; `raw_sha256` identifies the unredacted source rather than claiming that
raw and public bytes coincide. Full native text streams, including empty stdout,
are retained as gzip beside each worker. Their inherited `qe.*` filenames
contain Julia output; **no QE command ran**.

The [B0 case](../../../benchmarks/si-soc-splitting-v1/case.json) is unchanged:
two-atom Si, a=10.26 bohr, PBE/NLCC, 8 valence electrons, eight explicit k points,
30 Ha, 48³ FFT, tau=0.001 Ha, 24 physical states plus 6 auxiliary columns, no band
expansion. SCF used seed 81001, fresh uniform valence density, alpha 0.1,
max_maps 400 and original solver/closure thresholds. Gamma used seed 81201,
this SCF's checkpoint and n_out, and parent mu=0.18176855561634891 Ha. Its FD
occupations are diagnostic only; no new chemical-potential solve or feedback.
The new checkpoint SHA-256 is
`aa34831d2bdfc5c973346ac237d0c77fa799f9074eb326047c4f37c9f53eb289`;
new n_out SHA-256 is
`1b881be85c18228e078a0bb10df15f94ec21642fa405e2ef9562b9ebf5d667fd`.

SCF final unmixed residual is **1.2515299004558643e-9**. Maximum input-H residual
is 9.950939448195395e-11 Ha; self-density H and Rayleigh residuals are
4.555367322975013e-9 and 4.239452001094899e-9 Ha. Gram norm is
1.4553895003065912e-14; Pauli-density relative L2 is 1.227039380600477e-12.
Real/reciprocal electron counts are 8.000000000000943/8.000000000000949.
Tail occupation, stationarity, Rayleigh-occupation and energy recovery checks
pass their original thresholds. Gamma's maximum explicit residual is
9.815276728756093e-11 Ha, Gram norm 3.368372384760556e-14 and normalized
operator time-reversal error 3.077170672702937e-17.

## Regression against historical B0

The historical reference is original Si execution
`3948ed5d37660fe1e909aa6d12983234e317a479`, publication
`61cb1c226dcfa8dbeccc63e8f43e33b2790a07c6`:
[SCF](../../si-soc-splitting/D-SCF.json) and
[exact Gamma source](../../si-soc-splitting/D-spectrum.json).
[Endpoint metrics](endpoint-metrics.json) preserve every raw spectral difference
and all seven energy terms. [Density comparison](density-comparison.json) is
from authenticated private checkpoints, with original formulas and thresholds.
No zero point was fitted, energy corrected or density adjusted.

| Metric, new minus historical where signed | Actual difference | Original limit | Status |
|---|---:|---:|---|
| E | +1.7763568394002505e-15 Ha/cell | 1e-8 | PASS |
| F | +1.7763568394002505e-15 Ha/cell | 1e-8 | PASS |
| -TS | +4.852439996583073e-18 Ha/cell | Diagnostic | Retained |
| n_out normalized L2 | 7.184134576766379e-14 | 1e-8 | PASS |
| Gamma all 24 raw maximum absolute difference | 7.771561172376096e-15 Ha | 1e-7 | PASS |
| Fixed 3–4/5–8 split-off difference | +1.4349632593280148e-14 eV | 1e-6 | PASS |

Density uses exactly
`norm(new-old) / max(norm(new), norm(old), 1)` on the stored real-space vectors.
Absolute L2 is 8.873330709004814e-13, with norms 12.351286872745016 and
12.351286872744739. The vectors and their comparison remain
**RUNNER_REPORTED_PRIVATE_ENDPOINT_ARRAY_COMPARISON**; public replay can check
the reported quotient and source hashes, not independently recover private
arrays. It does not substitute a different physical integration norm.

New E=-8.368023851835547 Ha/cell, F=-8.368024366448914 Ha/cell and
-TS=-5.146133665408945e-7 Ha/cell. Uncorrected seven-term differences are:

| Term | New minus historical, Ha/cell |
|---|---:|
| Kinetic | +1.6475709685437323e-13 |
| AtomicLocal | -5.950795411990839e-14 |
| AtomicNonlocalFR | -1.361133428190442e-13 |
| Hartree | +5.1736392947532295e-14 |
| Xc | -2.1760371282653068e-14 |
| Ewald | 0 |
| PspCorrection | 0 |

Gamma split-off is 0.0474576151755701 eV, versus 0.04745761517555575 eV historical.
The fixed window structure passes, but minimum occupation in states 3–8 is
**0.9999595249412089**, below 0.99999999. Complete manifold assignment and physical
interpretation remain **REVIEW_REQUIRED**; no irreps, new null, continuous band
tracking, new QE comparison or physical convergence claim follows.

## Actual runtime and resource observations

| Observation | SCF | Gamma |
|---|---:|---:|
| FR actions | 24,616 | 34 |
| Component /full actions | 23,176 / 23,176 | 34 / 34 |
| Density actions | 360 | 0 |
| Sampled aggregate RSS peak, bytes | 2,442,264,576 | 1,930,739,712 |
| Nonempty RSS samples | 26,707 | 235 |
| Observer elapsed seconds | 3118.339902458014 | 27.61242275001132 |

Both exercised the explicit `soc-core` runtime, one consumed source/context and
original P/D set, 72 maximum projectors, 30 RHS and 110592 real-grid nodes.
SCF/Gamma workspace maximum NG is 2120/2085. Normal close leaves no context,
zero owned sources and released workspace; process cleanup reports no remaining
owned process. The unchanged observer covers the session and descendants,
requests 0.1 s samples and enforces 8 GiB. Sampled peaks are not continuous bounds;
initialization, serialization, compilation and iterations are included in these
observations. They are not a timing-controlled comparison against historical SCF.

The original [performance review](../performance.json) remains; no timing or
allocation suite was rerun. This B0 SCF completes endpoint resource evidence
but does not bound K6 solver/history/GC/native overlap. The original
[K6 budget](../memory-budget.json) remains **INSUFFICIENT_EVIDENCE**, new peak
estimate null, and K6/K8 execution **NOT_RUN**. No budget was lowered or extra
context created from this one peak.

## Tests, failures, public replay and delivery

Preparation passed 38 new Python protocol tests, 88 affected Python tests,
39 whole-source syntax assertions,21 actual driver-definition/CLI assertions
and13 synthetic authentication-bridge assertions. Dedicated 20/15/4 reruns
overlap those counts. These are workbench checks, not newly run upstream tests;
historical 551/2495 and 1387/1387 remain historical.

Retained preparation failures include the exact-case endpoint CLI regression,
aliased temporary-root fixtures and an intermediate synthetic process-proof
fixture error. No threshold was relaxed. The first metrics postprocessing
command returned 1 because it requested a nonexistent standalone `spectrum.json`.
The exact `worker.spectrum` subtree was then extracted from the same authenticated
Gamma result and the real, unchanged metrics CLI returned 0. No scientific task
was restarted, no raw worker edited and no alternative spectral values supplied.
The density comparator had already returned 0 at E.

The [original partial report](../README.md) and
[first failed slot](../endpoints/endpoint-status.json) are preserved:
SCF 1 native 1 / recorder 9 before driver entry, Gamma then BLOCKED_PARENT. Original
public replay, actually run at detached 98781fd without private files, returned
**default 0 / strict 1** and still says PARTIAL/end_to_end FAIL. Original publication
checker incompatibilities likewise remain historical failures.

New public-only replay uses a complete Git clone and existing Python 3.12:

```sh
python3.12 -B benchmarks/soc-core-memory-v1/resume/replay.py --root .
python3.12 -B benchmarks/soc-core-memory-v1/resume/replay.py --root . --require-endpoints
```

The new default validates the recorded delivery, including a properly recorded
failure. Strict 0 requires both new endpoints and all source/resource/regression
gates; malformed evidence exits 2. Public energy/spectrum and reported norm
arithmetic is distinct from private density, orbital, ownership and RSS
measurements. Final clean-clone replay and its test receipt remain **PENDING**
at this reporting step. [Incremental backup verification](archive.json) records
185/185 restored files (191,680,654 source bytes), their manifest and the 164,673,892-byte
compressed archive. The execution Git bundle retains 98781fd through E. This is
a verified same-machine repository-external backup, not an off-site backup.
Raw arrays and full process history remain there rather than in Git.

No new static suite, extra SCF/Gamma, K6/K8, QE/pp, null/p±, new material, CI,
full upstream suite, IEEE localization or Phase 9B was run. The two authorized
new slots are consumed; further numerical attempts require new authorization.
