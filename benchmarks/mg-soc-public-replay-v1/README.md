# Phase 7G: complete public replay on Linux

**Outcome: BLOCKED at workflow push authorization.** GitHub rejected the initial
push because the existing OAuth credential has no `workflow` scope. No Linux
job or real R/I replay ran. These are prepared methods, not executed numerical
results. See the [receipt and limits](../../results/mg-soc-public-replay/README.md).

This case checks reproducibility of the fixed Phase7F public evidence at
`747d7d3e21dadd8a5fef0183d2375e7f1f82c176`. It adds no scientific state or
projector. [plan.json](plan.json) fixes the59 required public file hashes,
Linux x86_64/Ubuntu24.04 target, Python3.12.14, NumPy2.3.5 binary wheel,
official Actions full commit SHAs and all comparison thresholds before execution.
[requirements.lock](requirements.lock) pins the exact CPython312 manylinux x86_64
wheel and SHA256; no source build or version fallback is permitted.

## Two distinct results

R executes the byte-identical frozen `python scripts/check_orbital_energy.py`
on a read-only detached baseline worktree, without `--all`. Its genuine output
and integer exit code remain authoritative for R. A small disclosed read-only
profile observer records values already returned by R for diagnosis; it does not
replace functions, mutate arrays, suppress exceptions, or repeat numeric calls.
Observer failure is recorded separately and cannot turn R into PASS.

I uses new standard-library/NumPy readers and mathematical functions, with
streamed per-k/per-band FFTs and explicitly constructed integer correspondences.
It never imports or calls the production parsing, density, kinetic, nonlocal or
comparison helpers. Synthetic tests precede use of historical target values.
The paths share public coefficients/P/D and NumPy, possibly also underlying
FFT/BLAS. Independence is at the new code path and mathematical cross-relations;
it is not a second DFT code, regenerated P/D or human expert certification.

Both inputs are the same full72 Q states, all original f/weights/eigenvalues,
actual integer G, published rectangular P/full D, native P2 text, saved density
and cited historical scalars. A/B permit **SCALAR_AND_PROJECTED_ONLY** replay;
private X, density/kinetic reconstruction from A/B X and UPF access are excluded.
No old numerical package is copied into this case.

## Contracts fixed before the run

Input Git blobs, NPZ containers and fixed numeric members, original WFC bytes,
P/D, P2 tokens, historical E/F and thresholds are exact identities. WFC files
are rebuilt in memory from the full canonical arrays and compared to all three
original whole-file hashes, without emitting new WFC files.

For newly derived values: norm/Gram≤1e-9; electrons≤1e-8; saved-density coefficient
max≤1e-10 e/bohr³ and nonzero relativeL2≤1e-9;17 direct correlation modes≤1e-11;
T, NL and A/B scalar/projected replay≤1e-9 Ha; local/J/signed-ledger differences
≤1e-10 Ha. J print-halfwidth tolerance is max(relative1e-10,absolute1e-22 Ha).
Geometry/cutoff/imaginary-component checks and exact dimensions are in the plan.
These do not modify R's existing stricter or byte-based checks. No physical
cross-code agreement threshold is invented.

New density hashes are recorded but not substituted for numerical norms. The
predeclared platform candidates are exactly:

- `state-checks.Q.backend.numpy_version` (environment string; a different version
  would also violate this case's environment lock and is not excused);
- `comparison.local_state.field_fingerprints.n_wfc`;
- `comparison.local_state.field_fingerprints.n_saved`.

P2 V/uV hashes, original input fingerprints, source/format/status strings and
geometry identity are not blanket exceptions. All differing leaves are enumerated;
unclassified or numerical failures remain failures. The historical reconstructed
real-density arrays are not public, so direct historical nodewise norms are
NOT_AVAILABLE. Report current R↔I node norms, all saved-coefficient residuals and
historical scalar differences with their distinct scopes.

A platform-density fingerprint failure stays **R FAIL** even if I passes every
numeric contract. The workflow stays red when tests, R, I or capture/identity
checks fail; successful packaging/upload never overrides the failure.

## Restricted execution

A single standard GitHub-hosted `ubuntu-24.04` job runs only on push to
`codex/phase7g-public-cross-env-replay` when the execution files change.
Permissions are `contents: read`; checkout does not persist credentials. The
public repository's existing Actions are enabled. Standard hosted compute for
public repositories is covered by [GitHub's documented free-use policy](https://docs.github.com/en/billing/concepts/product-billing/github-actions).
No account, protection, billing or secret setting changes are made.

The exact execution SHA is checked out; Git public history supplies a detached
read-only baseline. Dependency preparation is confined to an ephemeral virtual
environment, with no user site or bytecode writes, fixed NumPy wheel hash and
one-thread settings. Actual Python build, OS/architecture/CPU, NumPy configuration,
shared-library hashes and OpenBLAS thread count are recorded. Network is used
only for public checkout, dependency preparation and artifact transport. The
numerical scripts make no network calls; this is not an OS network-sandbox claim.

One formal run is allowed, plus at most one ordinary-commit retry for an evidenced
new engineering defect. Numerical failures do not trigger version/parameter
scans. Logs and diagnostics survive failure. Final receipts/docs may be committed
later, explicitly distinguishing tested_commit from delivery_commit and verifying
unchanged execution code, locks, plan and input hashes. No result-only push should
trigger another job. Temporary artifacts are downloaded into a new process archive;
the necessary compact receipts are also committed.

No SCF, eigen/occupation solve, QE/pp, Julia science, XC, UPF/P generation,
parameter scans or private scientific data access. Native QE NL stays NOT_MEASURED,
original Q input-H residual NOT_AVAILABLE, physical convergence NOT_ESTABLISHED,
IEEE origin NOT_LOCALIZED and interpretation REVIEW_REQUIRED.

## Prepared commands (real-data execution NOT_RUN)

In the declared ephemeral Linux environment, the wrapper is the execution entry:

```sh
python scripts/run_cross_env_replay.py --output NEW_RUN_DIR --wheel FIXED_WHEEL
```

It verifies the Actions event/commit, installed environment and fixed input
worktree; runs the five synthetic suites; then invokes R without `--all` and I
with `--source-root READ_ONLY_BASELINE --plan benchmarks/mg-soc-public-replay-v1/plan.json
--output NEW_I_DIR`. It returns nonzero if either path or diagnostics fail.
The wrapper is intentionally not a generic local-platform bypass. Direct I uses:

```sh
python scripts/replay_public_independent.py --source-root READ_ONLY_BASELINE --plan benchmarks/mg-soc-public-replay-v1/plan.json --output NEW_I_DIR
```

Do not interpret an unexecuted entry as validated real-data integration. No
permission expansion, substitute platform or second push was attempted here.
