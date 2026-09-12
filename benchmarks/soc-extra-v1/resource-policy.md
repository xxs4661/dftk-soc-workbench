# Si K6 resource admission

This is a finite engineering admission policy for the extra experiment. It does
not change the old Si gate or turn a pilot into a converged calculation.
`resources.py` binds the original budget, successful owned-core B0 observations,
the K6 case and the public integer-G geometry implementation by SHA-256.
Geometry is independently re-enumerated with that frozen routine; native K6
must then reproduce 216 points, sum NG=457287, maximum NG=2138, 72 projector
columns per k and 48³ FFT before its maps. No K8 context is constructed.

## Engineering estimate and lifecycle

The historical accounting subtotal is 6,788,850,928 bytes. It already retains
one P/D set, padded G/mapping capacities and snapshots, both prior/current
X24 and all_X30 plus energy factors, a serial one-k solver allowance, three
common-H local-potential sets, all 14 owned workspace buffers, the old broad
FFT/field allowances, and the original **2 GiB runtime reserve**. All original
terms are retained in the new machine-readable budget for inspection. The source
explicitly retains prior-map raw data while the next map is evaluated; no
unproved X/all_X alias reduction is credited. Ownership transfer consumes the
original context and certificates without making another complete P set.

One term is updated for the actual owned path. The old679,477,248-byte FFT
allowance assumed24-state real tensors; `context_orbital_density(OwnedRuntime)`
uses the already inventoried14 workspace buffers and returns independent
density copies. Frozen DFTK `src/terms/Hamiltonian.jl` shares one complex real-grid
scratch across all k in each single-thread H generation. Price three such
generations (5,308,416 bytes), two overlapping common-term traversals each
with two Hartree, four density-gradient and three GGA-divergence complex-grid
temporaries (31,850,496 bytes), and a further nonzero64 MiB for unobserved
native FFT staging:104,267,776 bytes. `hartree.jl` and `xc.jl` establish these
field-transform scopes. The88,473,600-byte real-field allowance and2 GiB runtime
reserve remain. This is a source-based lifecycle estimate, not a change to
the old coefficient, old gate or physical implementation. The runtime/pilot
object and RSS observations must still assess its adequacy.

Extra allowances are 1 GiB for an active callback-serialization buffer,
64 MiB for further container/dictionary capacity and 512 MiB for 400 maps of
diagnostics. The callback fingerprints a plain payload before and after output;
X24+all_X30 alone occupies 790,191,936 bytes at K6. Unreachable earlier buffers
may remain allocated until ordinary GC. They are part of the unchanged runtime
reserve, not assumed absent or continuously bounded. No forced GC or heap hint
is introduced. The historical B0 sampled peak of 2,442,264,576 bytes over 180
maps corroborates real lifecycle operation; it is not scaled by k count or
subtracted from this budget.

The history allowance exceeds the old 172.8 MB payload illustrations and
explicitly prices object/header growth. The authenticated full B0 map log has
180 rows, 7,669,624 bytes and a maximum 43,219-byte JSON row; its last map has
1,821 scalar/string leaves. These serialization sizes are context for an
estimate, not measurements of Julia object storage. Pilot `Base.summarysize`
observations must assess the actual history and largest map record.

Construction precedes orbitals/history: its separate envelope retains full P,
D, geometry, runtime workspace, updated FFT/original fields and runtime reserve, plus
64 MiB for per-k projector assembly and transfer transients. The peak estimate
is the maximum of construction and map envelopes. This avoids pretending that
all constructor temporaries must coexist with the final 400-map history, while
retaining nonzero constructor costs.

Before observations, the two-map estimate is **7,357,176,499 bytes** and the
400-map estimate is **7,891,363,056 bytes**. Observed or inferred larger
serialization capacities and history graphs can increase these numbers. Neither
value is a proven maximum; the source estimate alone cannot admit formal SCF.

## Pilot and formal admission

Initial host/source/resource checks return `PILOT_ELIGIBLE`, with native exit
null. A single pilot may complete at most two original density maps and must
finish with `PILOT_COMPLETED_NOT_SCF_CONVERGED`, native/recorder0, valid actual
geometry, nonempty RSS samples and successful owned-process cleanup.

The pilot receipt's `lifecycle` contains positive integer `history_bytes`,
`history_map_count`, `max_record_bytes`, `serialization_payload_bytes` and
`serialization_buffer_capacity_bytes`. The graph sizes include headers and
capacity. `serialization_capacity_evidence` distinguishes `MEASURED_ACTIVE_BUFFER`
from `INFERRED_FROM_FROZEN_BUFFER_GROWTH`. For the latter, a CountingIO runs
standard Serialization without retaining bytes; length L is used in the exact
monotonic Julia1.12.7 `overallocation(L)` upper-capacity formula. Default
IOBuffer starts at32 bytes and uses Memory storage; `_resize!` overallocates,
and the specialized writable `take!` wraps the existing storage without copying
the whole payload. This requires append-only serialization, Julia1.12.7 and
the exact `base/iobuffer.jl`/`base/array.jl` hashes recorded in `BUFFER_SOURCES`.
It is an inferred capacity bound, not a direct measurement of the hidden
authentication buffer, a GC-lifetime proof or an RSS bound. For example,
L=790,191,936 bytes gives capacity≤1,090,292,520 bytes. A
missing observation or unbound inference blocks admission instead of becoming zero. The full
history allowance is increased, when necessary, to twice the larger of the
observed average map graph and largest map graph, times400. The serialization
allowance is at least1 GiB and at least125% of the measured/inferred buffer capacity.
These formulas are fixed before the pilot and can only increase estimates.

Formal admission requires both updated source envelope below8 GiB and:

```
pilot sampled peak
+ remaining priced history growth
+ uncovered serialization capacity allowance
+ 128 MiB later output/checkpoint overhead
+ 1 GiB unobserved fluctuation reserve
< 8 GiB
```

The observed extrapolation does not add the separate2 GiB source-model margin
again. Pilot RSS already includes actual loaded runtime. A pilot reaching the
7 GiB warning point is insufficient for full-run admission under this policy.
The sole success state is `PROVISIONAL_GO_WITH_MONITORING`, not a scientific
PASS. In particular, a low pilot RSS cannot override an excessive history or
serialization estimate.

## Runtime monitoring and host

The runner must monitor the recorded process group and descendants, preserving
the existing0.1-second RSS policy. At8 GiB or explicit severe host pressure,
terminate only that owned group and record `RESOURCE_LIMIT`. At7 GiB, retain
the warning and check priced remaining growth at the next safe boundary;
unknown growth or projected8 GiB requires stopping. Missing pressure/RSS
observations are monitoring failure. These are sampled safeguards, not OS
memory isolation, and may miss inter-sample peaks.

Read-only host queries inspect processes, memory pressure, physical memory and
free space. macOS critical pressure level4 or system-wide free percentage≤5%
counts as severe; Linux MemAvailable≤5% or full memory PSI avg10≥10% does too.
These operational indicators and any unavailable optional kernel field are
reported explicitly. No memory stress probe or unrelated process termination
is performed. Require24 GiB free at both run and archive locations: it includes
the 10 GiB unused reserve, checkpoints, native logs, an ordinary increment and
restore space. Recheck before each slot; a snapshot does not reserve resources.

The host functions return local observations. The publication layer removes
private paths from errors and does not publish the full process command table.
All synthetic tests exercise decisions only, except the read-only integer
geometry recomputation; they are not physical or RSS pilot evidence.
