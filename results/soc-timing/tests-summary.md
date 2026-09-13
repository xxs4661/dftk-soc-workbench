# Cooperative control checks

These are bounded synthetic launcher–worker–recorder checks. They do not execute electronic structure or prove SCF convergence. Fixture commit/case IDs are intentionally synthetic.

The final launcher suite passed 13 tests with 12 actual worker records (exit 0). Added policy-identity and Julia 1.12.7 byte-unit assertions each passed separately. The affected old resource suite passed 13 tests; the old monitor suite first passed six with its Julia case skipped for an unselected depot, then that actual definition-only Julia case passed after selecting the existing frozen depot.

| Fixture | Native | Worker | Recorder | Recorded outcome | Closed | Forced cleanup |
|---|---:|---:|---:|---|---|---|
| Julia cooperate | 130 | 130 | 130 | USER_CANCELLED | true | true |
| Julia raw_sigint | -2 | null | 9 | FORCED_TERMINATION | null | true |
| Julia catch_sigint | 1 | 1 | 1 | FAIL | true | true |
| Python writefail | 1 | 1 | 1 | FAIL | true | false |
| Python wait | 124 | 124 | 124 | TIME_BUDGET_EXCEEDED | true | false |
| Python missing | 3 | null | 9 | FAIL | null | false |
| Python contradict | 7 | 0 | 9 | FAIL | null | false |
| Python normal | 0 | 0 | 0 | DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED | true | false |
| Python orphan | 130 | 130 | 130 | USER_CANCELLED | true | true |
| Python swallow | 0 | 0 | 9 | FAIL | null | false |
| Python ignore | -9 | null | 9 | FORCED_TERMINATION | null | true |
| Python wait | 130 | 130 | 130 | USER_CANCELLED | true | false |

All final launched-worker records report observed owned-process cleanup PASS. The Julia cooperative and caught-interrupt cases still needed cleanup signals for remaining observed descendants; those signals are retained. Missing/contradictory receipts and swallowed cancellation were rejected with recorder code 9. The write-failure case retained both its earlier cancellation request and the actual IsADirectoryError/code 1. No missing runtime-close field was changed to true.

Earlier attempts remain failures: the first had 12/12 failed assertions after sandbox process-list denial; the second had three failures among 12 tests. The latter exposed Julia TOML Int128 timestamp handling and two fixture assumptions about observed child cleanup. Complete sanitized failure logs and original raw hashes are preserved. Their exit codes remain 1.

The communicated cumulative budget is 112.317 seconds, including earlier failed attempts, legacy regressions and small unit diagnostics, against the 300-second limit. Per-attempt timing sources are explicit in cancel-tests.json; this rounded sum is not represented as an exact shared-clock measurement.

Evidence: cancel-tests.json contains all outcome fields, source hashes and public mappings; cancel-test-native.json.gz retains compact worker/outer/control/native receipts and both native streams; cancel-test-logs.json.gz retains test output and prior failed native diagnostics. Paths alone are sanitized. Full private process samples remain local.

Limitations: no real scientific cancellation or real 120-second grace expiration was run. Ownership coverage starts with observed processes. Synthetic two-map success is protocol-only. Final source bytes and the limited later pure checks are identified separately; a full-suite rerun after those pure changes is not claimed.
