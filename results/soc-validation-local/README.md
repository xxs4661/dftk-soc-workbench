# Local validation probe: blocked before static execution

**Partial preparation; `BLOCKED_RESOURCE_OBSERVATION`.** No K4 static context
was constructed, no S/F type trace or timing was measured, and no correction C
was selected. This record does not complete the requested local experiment.
The existing [boundary candidate's performance failure](../soc-boundary/README.md)
is unchanged; strict validation remains the default.

## What prevented the experiment

The execution sandbox denied `ps` (shell exit **127**). The existing resource
sampler independently raised `PermissionError: [Errno 1] Operation not permitted:
'ps'`. Required process-group/RSS observation could not be established. No
static slot was reserved or consumed, and observation was not bypassed.

One separate **no-context** S entry check then failed during MPI initialization,
before method/location and loaded-environment checks: native exit **15**, recorder
exit **9**, `MPIDI_POSIX_comm_bootstrap: Out of memory`. Its run ID is
`DIAG-S-ENTRY-20260919T035938649873Z-470d12ba` (11.0006 s outer wall).
This error is **not a measurement of 8 GiB exhaustion**; its cause was not
established. MPI settings and frozen dependencies were not changed; F's entry
was NOT_RUN. [Native failure projection](entry-S-native.log) retains the error
stack with addresses redacted; original bytes remain in the external archive.

| Requested evidence | Actual status |
| --- | --- |
| DIAG-S / DIAG-F, actual fallback types and access order | NOT_RUN / NOT_OBSERVED |
| Loss of strict storage reuse on the actual K4 objects | CAUSE_NOT_ISOLATED |
| S/F actual hash/copy/reuse/clear work | NOT_MEASURED |
| Candidate C and its protection/byte-equivalence gate | NO_CANDIDATE_SELECTED / NOT_RUN |
| BENCH-S / BENCH-F / BENCH-C, 2 warmups + 5 samples | NOT_RUN; no samples |
| C full-boundary median ≤ 90% of S | NOT_ASSESSED |
| New numerical regressions or material results | NOT_RUN |

The [types](types.csv), [work](work.csv) and [samples](samples.csv) tables contain
headers only. Their empty bodies mean **unmeasured**, not zero cost or zero
fallbacks. Synthetic wrapper tests do not identify the real fallback types.
In particular, this round does not establish that SubArray explains the
historical regression or quantify lost reuse. No speedup is claimed.

## Input and implementation identity

The [plan](../../benchmarks/soc-validation-local-v1/plan.md) and
[contract](../../benchmarks/soc-validation-local-v1/contract.json) were committed
before preparation code, at `d7dd0c6ffd197d632018afc117667849cf655036`.
Prepared tools and the failed no-context entry bind
`e308f5bb35d2a4f4cd14366d12728240c50fca56`; **this is not a measured C execution
commit**. There is no C or `E_new`.

| Identity | SHA / meaning |
| --- | --- |
| Branch base B / F source | `de2d3661bdd4a0a5081ae322b7c7e723ef0e6fdd` |
| S source R | `d9e19af3557c923a1e4f7e64510092d47975cc7c` |
| Historical failed-candidate execution | `761e09d8fe99f99fcccb0f1b10704916d336ccb8` |
| Main observed before work | `7630172808773a3d4ac2da825c27fe43a8705fb8` |

The canonical [fixture](../../benchmarks/soc-validation-local-v1/fixture.json)
binds the unchanged K4 input and the independent V-K4-REF map-1 density export:
884,736 bytes, 110,592 little-endian Float64 values, 48³ grid, SHA-256
`3a18d5b9774d8d6db4aa73e7f5176983398044b52698f7186e062a826dc870cc`.
The original receipt/summary/archive chain and file bytes were authenticated.
An independent summation gives 8.00000000000001 electrons; no normalization was
applied. This is a **HISTORICAL_REUSED, NOT_SCF_CONVERGED** map output, not a new
density. Uniform-density fallback was not selected. No binary checkpoint was
deserialized.

Independent clean R and B source checkouts were bound before entry. Seventy-one
relevant B science-source files match the old failed execution. The fixture
records separate strict/F source hashes. These are file-identity checks:
newly **loaded DFTK/PPIO identity is NOT_VERIFIED**, and actual P/D, G mapping,
potential, type/layout/alias comparability remains NOT_OBSERVED.

## Preparation checks and public replay

The added static-only driver/observer and supervisor adapter remain unexercised
with a material context. The observer's diagnostic shadow is separate from
untouched strict main timing; no production certification file was changed.
The supervisor refuses static startup without monitoring, and requires actual
S/F observations and a committed selection/protection gate before any benchmark.
There is no such selection gate here.

| Actual check | Outcome / exit | Public log |
| --- | --- | --- |
| Python driver/control/record protocol | 42 passed, 2 skipped (44 discovered); 0 | [log](python-preparation.log) |
| Julia diagnostic-shadow synthetic assertions | 92/92; 0 | [log](observer-synthetic.log) |
| Julia driver helper lifecycle with toy constructors | 99/99; 0 | [log](lifecycle-synthetic.log) |
| `Meta.parseall`, all 123 tracked Julia files | 0 | [log](syntax-parse.log) |
| Preparation replay test with misplaced test assertion | 1, retained; later fixed without weakening assertion | [failure](replay-test-preparation-failure.log) |
| Actual process observation / S entry | 127 / native 15, recorder 9 | [observation](process-observation.log), [entry](entry-S-native.log) |

The two skipped tests require real monitored cancellation/timeout subprocesses;
mocked protocol and toy lifecycle checks do not replace them. C-specific real
type protection and performance gates are NOT_RUN. Earlier preparation logs,
including the test insertion error, are retained rather than overwritten.

From a full clone with Python 3.12, replay the public blocked record:

```sh
python3.12 -B benchmarks/soc-validation-local-v1/replay.py
python3.12 -B benchmarks/soc-validation-local-v1/replay.py --strict
```

The first returns **0 only for consistent hashes and blocked statuses**. Strict
acceptance returns **1**, preserving NOT_RUN; malformed or contradictory evidence
returns 9. It reads neither private density arrays nor `.work`, and starts no
Julia worker. The [record](record.json) binds public projection hashes separately
from raw-log hashes in the logs. It does not prove runner-reported private input
authentication or certify the unexecuted static driver.

## Budget, cleanup and preserved limits

Static starts: **0/5**; static work budget consumed: **0/1,800 s**. No measured
static wall, peak RSS, runtime close or release result exists. The no-context
entry's direct subprocess exit was collected; independent process-group cleanup
could not be verified because process observation is unavailable. No material
runtime/context was constructed. No material stop, resume or cleanup PASS is
inferred from synthetic tests.

The 8 GiB limit, 7 GiB warning, 2 GiB fixed reserve and 120+10+5 s disposal
contract remain unchanged. No source, physical input, environment, old gate,
old candidate or historical result was altered. No map, SCF, eigensolve,
occupation solve, Γ, QE, CI or upstream contact occurred.

Previous K6 user cancellation, native −2 / recorder 9, unconfirmed normal
runtime closure, lack of qualified endpoint and unverified resume remain.
The previous 10 GiB authorization remains consumed. This blocked preparation
does not reopen it or authorize a new numerical experiment.

Only this round's small records, prepared code and required density are archived
outside the repository, with an incremental Git bundle and byte-checked finite
restore. This is a same-machine archive, not off-site storage. Final clone,
restore and push receipts are external; the final delivery reports their actual
outcomes without changing historical hashes. Human review is required before
deciding how to resolve the environment blockers and resume the diagnosis.
