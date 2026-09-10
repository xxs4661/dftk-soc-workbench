# SOC core and memory audit — Phase 9A

**Continuation after this preserved partial snapshot:** [new Si endpoint report](completion/README.md)
records the explicitly authorized SCF attempt 2 and Gamma attempt 1 at E=281c535…:
both native/recorder exits are 0 and all original B0 regression limits pass.
Static results remain HISTORICAL_REUSED; time, K6 and physical interpretation
reviews remain. Final public-clone/archive verification is PENDING at this
reporting step. The complete original account below retains its original
1b42a270… execution and 98781fd partial-publication scope, including SCF attempt 1
FAIL and its unstarted Gamma. Those historical records were not relabeled.


**PARTIAL_DELIVERY.** Four authenticated static suites passed numerical,
allocation and sampled resource gates. The one authorized new Si B0 attempt
failed while parsing its Julia driver, before any SCF map. Gamma is
**BLOCKED_PARENT** and was not launched. A subsequent one-space syntax repair
and whole-source parser regression do not turn that execution into a success.
The new path's real SCF/endpoint integration remains **NOT_DEMONSTRATED**.

| Assessment | Actual result |
|---|---|
| Static identity / mathematical equivalence | PASS; private arrays, public arithmetic explicitly runner-reported |
| FR24 and full-pipeline allocation targets | PASS on B0 and K4; all five samples retained |
| Repeated live-storage reduction | PASS in static lifecycle; not seven contexts required by one SCF |
| Time | PERFORMANCE_REVIEW_REQUIRED; some warmed medians worsen by more than 10% |
| OPT-B0-SCF | FAIL; native 1, recorder 9; maps NOT_STARTED |
| OPT-B0-GAMMA / endpoint regressions | BLOCKED_PARENT / NOT_ASSESSED |
| K6 budget / K6 execution | INSUFFICIENT_EVIDENCE / NOT_RUN |
| Original publication checker | FAIL 1 at accepted base and current tree; old manifest unchanged |
| Physical convergence, IEEE, native QE NL, upstream SOC | Previous limitations unchanged |

## Identity and sequence

Branch `codex/phase9a-soc-core-memory`, accepted base
`c764311a5422b5c3cab5a7b78a02d420910c4e56`; initial tree was clean.
The [plan, sources and contract](../../benchmarks/soc-core-memory-v1/README.md)
were committed at `e4f16a51a0304f5e70f5ae038563d6760409c2c4` before measurements.
Reference harness commits were `f768be5f0d4631ee6b1c21ecc50431c9e57f7b16`
and cache-launch repair `bbe9aa7755f052900e6e9c4618252a410e1cc8f0`.
Successful REF workers loaded the complete clean **c764311…** legacy source in
isolated processes. Candidate static suites, comparison, gate and failed SCF
used clean exact execution commit **`1b42a27063ca65757d2c4f34d46fe4f1cd9929ed`**.
The subsequent result commit contains a syntax repair, parser regression and
reporting, with no remeasurement; its SHA is supplied after committing.

B0/K4 inputs are **HISTORICAL_REUSED** X/f/e/n_in/n_out from authenticated
original checkpoints. B0 producer/publication:
`3948ed5d37660fe1e909aa6d12983234e317a479` /
`61cb1c226dcfa8dbeccc63e8f43e33b2790a07c6`;
K4: `48da17f47e998030a50c954c3abc38bca3a9df8f` /
`557571fa6beb29e1ee57a5a0701ab3bded41fc78`.
Native bytes, ordered k/G/maps, P/D labels and numerical inputs were checked
before and after evaluation. [Sources](../../benchmarks/soc-core-memory-v1/sources.json)
and [replay data](replay-data.json) retain exact hashes and original run IDs.
No old SCF was rerun.

All four workers used macOS arm64, Julia **1.12.7**, one Julia/BLAS/FFT thread,
the same frozen workbench environment and existing package caches. Fresh-process
identity checks verified real loaded paths, UUIDs, versions and clean checkouts:
DFTK 0.8.0 at `2f51b91213e26726fb9c6a17e5fae235a1412d01`, PseudoPotentialIO 0.3.3
at `fec942781560c391f20214ba4cd85fb2431deb84`.
Manifest SHA-256: `5b8ae036ac430219a95d61a5e3cd20074e9ecd252335253bf7ada81278b08c37`;
Si UPF SHA-256: `cc91a6be43c3c89daf6c34410096e8d870f25152dbfb513bcf01afa5ab53eabf`.
[Source boundary](source-boundary.json) verifies unchanged old tests, history,
locks and upstream checkouts; actual preexisting edits are listed explicitly.
No dependency, UPF, frozen formula or upstream source changed. Real paths were
compared before redaction; public records do not replace runner-side checks.

## Static results

Each suite has 13 operations, **one warmup and five samples each**:
FR/component/full H with 1/24/30 RHS, full-k density, nonlocal, seven-term energy
and complete static pipeline. The extra six RHS columns use seed 91030 and have
no physical occupation. There were **zero development profiling rounds**.
[Replay data](replay-data.json) preserves all samples, compile/GC and cold costs;
[performance](performance.json) contains every derived ratio and gate.

| Suite / unique run suffix | FR24 median allocation, bytes | Pipeline median allocation, bytes | Pipeline median, s | Sampled RSS peak, bytes |
|---|---:|---:|---:|---:|
| REF-B0 / `20260909T103314263290Z-c672b973` | 3,271,232 | 7,593,430,360 | 4.289815666 | 3,212,132,352 |
| CORE-B0 / `20260909T113339230728Z-6007a16c` | 4,992 | 2,337,037,752 | 4.429607458 | 2,117,042,176 |
| REF-K4 / `20260909T103452759115Z-43829d19` | 3,271,232 | 57,933,178,920 | 29.027789708 | 4,603,723,776 |
| CORE-K4 / `20260909T113543161223Z-f1a5bdb1` | 4,992 | 15,897,385,656 | 31.191017542 | 3,590,062,080 |

FR24 allocation ratios are **0.00152603** (limit 0.5); pipeline ratios are
**0.307771 / 0.274409** (limit 1.1). Cumulative Julia allocations are not peak
live memory. The same process-group plus descendants RSS observer requested
0.1 s intervals with the unchanged 8 GiB gate; peaks are not continuous bounds.
REF-K4's slower 0.020872167 s FR24 sample remains. Pipeline time increased
**3.26% / 7.45%**; B0 FR24 increased **18.07%**. All flagged operations remain
visible; no timing-cause or exact speedup claim follows from fewer allocations.
Cold context allocation also increased: B0 2,041,136,760→2,183,217,176 bytes,
K4 8,491,311,080→9,195,240,824 bytes; initialization/compilation costs are separate.

[Comparison](comparison.json) uses `max(norm(new), norm(old), 1)`, with no fit.
Maximum array relative differences are **1.3827368666750414e-15 /
1.3838614118461928e-15** for B0/K4 (limit 1e-12); maximum scalar energy differences
are **4.440892098500626e-16 / 1.1102230246251565e-16 Ha** (limit 1e-10 Ha).
Actual P/D arrays compare exactly with separately exported old operators; labels,
k/G mappings and input identities pass. Density R/n/m, electron integrals,
T/NL, seven terms and E/F retain independent recovery checks. Old P/D export was
a constructor-only diagnostic, **zero timing samples**, not a replacement suite.
Its Julia world-age warning is retained in the private logs. CORE's incremental
progress rows are outside timed blocks; REF predates that durability helper.
Warmups, five samples and consumed workloads are unchanged.

## Ownership and supported API

[Design](../../docs/soc-core-runtime.md) and [synthetic example](../../examples/soc_kernels.jl)
describe `SOCKernels`, bounded P/D contractions, general component lifting and
spinor density accumulation. The pure core needs no case, Git, files or global
registry. Frozen DFTK enters through the scoped adapter; legacy defaults and
serialized types remain, and `soc-core` is explicit. This is a workbench API,
not an upstream-approved final architecture.

The adapter transfers source/context certificates from strong legacy registries
into an owned session, retains **one** actual P/D set, and shares bounded serial
workspaces. Deep checks occur at construction, map, solve, callback, replacement,
final output and close; each action retains dimensions, alias, generation and
finite-value checks. Independent density/energy, residual/Gram/Pauli and FD
checks remain. Close clears owned references on normal and exceptional exit.

Unique backing storage is counted over a union of roots, including view parents.
Static `session_closed` payload falls B0 **498,751,472→148,972,672** and K4
**3,002,204,752→497,577,824 bytes**. The old loop retained seven contexts; the new
loop leaves zero registered contexts. This demonstrates bounded session release,
**not seven P sets required by a single SCF**. Each individual context already
had one P/D set. Native pointers, SCF histories and solver overlap remain outside
what those static snapshots can fully bound.

## Failed endpoint and adverse results

**`OPT-B0-SCF-20260909T114559Z-0600f2bf`** at the candidate commit and passing
[static gate](gate.json) returned native **1**, recorder **9**. Julia rejected
`:isnothing(profile)` at `scripts/run_si_soc.jl:330`: the ternary colon lacked
following whitespace. Driver entry was never reached: no maps, initialization,
checkpoint, n/E/F/occupations or Gamma data. The 741,703,680-byte RSS and 3.720085 s
belong to parse/startup failure only. [Two-slot record](endpoints/endpoint-status.json)
and [complete redacted native stderr](endpoints/OPT-B0-SCF.stderr.txt.gz) bind raw
and public hashes. Raw `qe.stderr` is an inherited executor filename containing
Julia output, not a QE run.

Earlier checks loaded modules/comparison definitions; Python driver tests mocked
workers. They did not parse the complete real Si driver and missed its tail
syntax. The result-stage repair adds one space and a whole-file `Meta.parseall`
regression. Exact failed Git bytes are still rejected; all 29 new/changed Julia
files pass, **37/37**, exit 0, without evaluating numerical code. **No SCF retry**.
Gamma is **BLOCKED_PARENT** and new endpoint-vs-B0 regressions **NOT_ASSESSED**.
No new occupation/manifold conclusion can be derived; historical reviews remain.

Other preserved failures: first REF-B0 launch lacked the existing Roots cache
(native 1/recorder 9; zero samples; fixed by explicit existing depot selection);
first comparison launch used a relative request path (native 1; same code/data
then read with an absolute argument); initial synthetic/helper errors, including
the new parser test's first malformed Julia command literal; original publication
checker failures. Every failed attempt and repair remains in the external archive.
No worse performance sample was discarded.

The unchanged publication checker fails at **accepted c764311…** on
`common_data.jl` and at the candidate/current tree on `FRIntegration.jl` because
of its older frozen-science list. It was not refreshed or called PASS. Current
path/privacy and the explicitly authorized source whitelist are checked separately.
Existing Phase7G failure, 8A.1 strict exit 1 and old 6C compatibility failure remain.

## K6, replay, tests and archive

[Budget](memory-budget.json) preserves the old **12,614,633,984-byte** estimate
and 2 GiB runtime margin. Known roles plus retained allowances total
**6,788,850,928 bytes**, **not an upper bound**. Estimated new peak is null and
status **INSUFFICIENT_EVIDENCE**. [Lifecycle account](memory-budget.md) separates
observed sharing from conservative allowances. Solver/history/serialization,
GC/native and real SCF overlap remain unbounded; startup-failure RSS cannot fill
that gap. No K6 context or run was created.

Public arithmetic on a complete Git clone with Python 3.12, without `.work`,
UPF, Julia or private arrays:

```sh
python3.12 -B benchmarks/soc-core-memory-v1/replay_delivery.py --root .
python3.12 -B benchmarks/soc-core-memory-v1/replay_delivery.py --root . --require-endpoints
```

The first checks bindings and recomputes recorded static differences, all-five-
sample statistics, owner histograms, budget and failure status. Replay success
means **the partial record is consistent**, not SCF success. The strict command
must return **1** for the incomplete endpoint. Original array differences,
object reachability and RSS collection remain **RUNNER_REPORTED**; this performs
no kernel/SCF or density reconstruction. Git ancestry authenticates executed blobs.

[Test ledger](tests.json) has actual commands, exits, latest distinct counts and
raw log hashes: 551 new Julia static/synthetic assertions and 2,495 unchanged
Julia assertions passed before execution, alongside Python tests. Post-failure
parser and final replay checks are separate in [delivery checks](delivery-checks.json).
These are workbench tests; full upstream DFTK tests are **NOT_RUN**. Historical
1387/1387 is not a new result. [Archive verification](archive.json) binds the
external increment and actual restored-file hashes. Raw arrays, failed runs,
profiling and resource samples remain outside Git; history was not deleted.

DFTK K6/K8, extra Si/Mg SCF, QE/pp, CI, scans and Phase 9B are **NOT_RUN**.
Endpoint, performance and resource limitations require review before any next
stage or new execution authorization.
