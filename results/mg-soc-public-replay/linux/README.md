# Phase 7G: Linux public replay — I PASS, R FAIL

The first formal public replay ran on **Ubuntu 24.04.4 x86_64**. The independent
implementation I passed all **380 checks**, exit **0**. The frozen original
checker R returned **FAIL, exit 1**, because its newly reconstructed density hash
differs from the historical Mac hash. The workflow correctly remains **failure**.
No numerical retry was performed and no old checker or threshold was changed.

[Run 34227336460](https://github.com/xxs4661/dftk-soc-workbench/actions/runs/34227336460)
and [job 102064570465](https://github.com/xxs4661/dftk-soc-workbench/actions/runs/34227336460/job/102064570465)
are bound to execution commit `58c1feae286c32e8ba017fdc2869eba908c9f4dc`, attempt 1.
[replay.json](replay.json) preserves the separate exits, all changed R leaves,
all I gates, numeric summaries and environment. [evidence.json](evidence.json)
binds the compact publication to original CI files and the archived artifact.

## Identity, environment and execution

| Role | Exact identity |
| --- | --- |
| Accepted scientific/data base | `747d7d3e21dadd8a5fef0183d2375e7f1f82c176` |
| Plan/environment/gates committed before execution | `757397ab0f0080f783d64841a6522db7f7d851b0` |
| Execution-code candidate | `95334efbab69fe97006ac76cbf4d676d4a7efd9f` |
| Actually executed / tested commit | `58c1feae286c32e8ba017fdc2869eba908c9f4dc` |
| Branch | `codex/phase7g-public-cross-env-replay` |
| Subsequent delivery | Ordinary documentation/receipt commit; executed code, plan, lock and inputs remain identical. This later commit was not run in CI. |

The earlier [authorization-blocked report](../README.md) and its machine records
remain byte-identical. The owner separately authorized persistent `workflow`
scope and completed local keyring authentication. After independent scope
verification, the first successful branch push started this run. The rejected
push and the local credential-save failure did not start a numerical process.
No account settings, main, protection rules, secrets or billing settings changed.

The actual CPU is **Intel Xeon 6973P-C**, kernel
`6.17.0-1022-azure`, runner image `20260831.293.1`. CPython **3.12.14** was the
hosted-toolcache build dated Aug 13 2026, compiled with GCC 13.3.0; it is not
claimed to be the other available Python tarball listed during preparation.
The actual executable SHA is recorded. NumPy **2.3.5** came from the exact
CPython 312 manylinux x86_64 wheel, SHA
`0d8163f43acde9a73c2a33605353a4f1bc4798745a8b1d73183b28e5b435ae28`.
OpenBLAS **0.3.30**, ILP64, reported **one actual thread** through its runtime
query; all six declared thread variables were 1. FFT uses NumPy pocketfft.
The three bundled library hashes, numeric extension hashes, and the digest of
all 1,314 installed package-file hashes are recorded. The full manifest remains
in the original archived environment receipt.

The original baseline was checked out as a detached read-only Git worktree.
All **59 input files** matched the exact base before and after evaluation; all
**13 execution/plan/lock files** matched the execution commit. NPZ containers
and **45 members** passed dtype/shape/expanded-byte identities. Three complete
original WFC files were reconstructed in memory, each with 28 records and 24
bands, matching these original hashes and byte counts:

| Original G40 file | Bytes | SHA-256 |
| --- | ---: | --- |
| wfc1 | 2,166,416 | `d56c746b2875764923cd09cf3ee27e70ac59a9780c193c45fd40f766353be485` |
| wfc2 | 2,160,956 | `a583623ef9802ac040282539c71d40bf7b67cb5948977fcad55eb338b5c616af` |
| wfc3 | 2,160,956 | `13b2987d722061a639d3285b77a815336433eae04bd5274093c423f347956a3a` |

No native WFC was exported. No private work directory, UPF, checkpoint or
historical private archive was accessed. Network served checkout, fixed-package
preparation and artifact transport; numerical scripts contain no network calls.
OS-level network isolation was **not enforced or claimed**.

## R's failure and its exact scope

The raw R stdout, with empty stderr, reports:

```text
Replay differs: ('2a554d911cc70969d7afb650adbeee103dfdbc7b2960629d8f4339c532f1e48e', '9f34eb4b8ff1672f9703b55453477f7789f6f18645cdbdb389dcc9c5eb5496f0')
```

This is `comparison.local_state.field_fingerprints.n_wfc`. The disclosed return
observer recorded the completed numerical reports without replacing functions,
repeating numeric calls or changing R's exit. Full leaf enumeration found:

| Field | Historical Mac hash | This Linux R hash |
| --- | --- | --- |
| `n_wfc` | `9f34eb4b8ff1672f9703b55453477f7789f6f18645cdbdb389dcc9c5eb5496f0` | `2a554d911cc70969d7afb650adbeee103dfdbc7b2960629d8f4339c532f1e48e` |
| `n_saved` | `780de08d2145ee849736ac5492d7d202a83c125aaa4b3d97fa7d700edcbc7400` | `5463c4843bf1074eda3714e53437875476cd811dab78d17ca250fd97de5199d0` |

These are the only two nonnumeric mismatches and were explicitly classified
before execution. Both hash newly derived real densities, not original inputs.
All **122 numerical changed leaves** meet R's unchanged `1e-11` comparison;
the largest is `1.4210854715202004e-14` Ha. No unclassified difference remains.
NumPy version, exact P2 V/uV hashes, source hashes, geometry and semantic fields
are not exempt. The original process stopped at the first hash; the observer's
leaf audit does not turn those subsequent diagnoses into an R PASS.

Current Linux R versus I has n_wfc maximum node difference
`2.220446049250313e-15` electron/bohr³ and relative L2
`2.565379153088867e-16`; current n_saved arrays are identical. These are
**current R/I comparisons**, not measurements against original Mac nodes.
The historical Mac dense arrays are not public; original-node differences
remain **NOT_AVAILABLE**. Saved Fourier coefficients provide a separate check.

## Independent results and unchanged contracts

Every original k and all **72 states**, including 14 zero-occupation states,
were retained. Physical f has capacity 1 and spatial weights are applied once.
All 22,119 saved density modes were checked. Actual integer enumeration produced
21,421 possible product modes, with **zero missing** from the saved support.
All 17 fixed non-FFT correlations were evaluated. No coefficient was fitted,
renormalized, cropped or phase-aligned.

| I diagnostic | Measured error / value | Declared gate |
| --- | ---: | ---: |
| Maximum state norm error | 5.7732e-15 | 1e-9 |
| Maximum per-k Gram Frobenius | 1.8020e-14 | 1e-9 |
| Maximum error across three electron counts | 5.3291e-15 electron | 1e-8 |
| Saved-density coefficient maximum error | 3.4762e-18 electron/bohr³ | 1e-10 |
| Nonzero-G relative L2 | 3.7490e-16 | 1e-9 |
| Direct correlation versus FFT / saved | 8.6736e-18 / 1.2145e-17 electron/bohr³ | 1e-11 |
| T gradient minus direct / direct minus historical | +1.0658e-14 / +1.0658e-14 Ha | 1e-9 |
| NL action minus projected | +5.3291e-15 Ha | 1e-9 |
| Q / A,B worst per-state NL historical difference | 8.8818e-15 / 1.3323e-15 Ha | 1e-9 |
| Q up/down complex amplitude maximum difference | 1.7166e-16 | original R bound 1e-11 |
| Largest local historical scalar difference | 5.6843e-14 Ha | 1e-10 |

The three electron counts are 10, 10, and 10.000000000000005. The reconstructed
orbital product coefficients outside the historical common support have L2
`2.574032163622697e-17`; this does not assert unknown physical modes vanish.
The computed volume is 1000.0000000000007 bohr³, within the declared geometry
gate of 1e-12; the original cell is unchanged.

| Quantity | This I result, Ha/cell |
| --- | ---: |
| Direct kinetic T_Q | 29.075987910634662 |
| Published frozen DFTK FR expectation on Q | −14.214055437803234 |
| Retained NL spin-cross contribution | −1.7889582957687973e-5 |
| L_wfc with the original P2 potential | −79.34118126437787 |
| L_saved with the same P2 potential | −79.3411812643779 |
| δL, integrated as a shared-potential difference | −4.2214445154025955e-14 |
| O_Q from the frozen historical ledger | −64.47924879196043 |
| J_Q = T_Q + N_D[Q] + L_wfc − O_Q | +4.1399061956326477e-10 |
| u(J_Q), printed-token halfwidth only | 1.913688277749921e-8 |

J differs from its historical arithmetic by `−4.973799150320701e-14` Ha; its
halfwidth differs by `1.6543612251060553e-23` Ha, within the predeclared contract.
u(δL) is `1.2231397271331697e-23` Ha. This tiny token interval excludes floating
reconstruction/reduction error: direct difference integration and subtraction
of the two local totals differ by `1.3792735723621948e-14` Ha. It cannot justify
extra physical precision. J remains below its token halfwidth; no fitted energy
constant or revised historical E/F is introduced.

The complete signed expression, with no parent/child double counting, is
`R_old = S_response + J_Q + δL − drift_S + historical_O_grouping_drift
− saved_local_replay_drift`. All six leaves and print-covariance arithmetic are
preserved in the numeric receipt:

| Endpoint | S_response, Ha | Reconstructed R_old, Ha | Difference from frozen R_old, Ha |
| --- | ---: | ---: | ---: |
| A | −2.5327672155128766e-6 | −2.5323532120406963e-6 | −1.912180605371551e-14 |
| B | −2.532767531704394e-6 | −2.5323535193504295e-6 | −1.3792735535514758e-14 |

A/B are **SCALAR_AND_PROJECTED_ONLY**: all published T rows and full complex
up/down projection amplitudes are replayed. Their original X, density and
kinetic reconstruction from X are not claimed. Q's NL is the **published DFTK
operator acting on original QE orbitals**, not native QE nonlocal energy.

## Commands, evidence and limits

The workflow invoked `python scripts/run_cross_env_replay.py --output NEW_RUN_DIR
--wheel FIXED_WHEEL`. R was exactly `python scripts/check_orbital_energy.py`
inside the baseline worktree, without `--all`. I used
`python scripts/replay_public_independent.py --source-root READ_ONLY_BASELINE
--plan benchmarks/mg-soc-public-replay-v1/plan.json --output NEW_I_DIR`.
The receipt records actual commands with disclosed path placeholders and hashes
of the untouched original stdout/stderr. The wrapper exited **1**; upload
succeeded without masking that exit. See the [fixed plan and lock](../../../benchmarks/mg-soc-public-replay-v1/README.md).

The five new synthetic suites ran on this Linux host: IO 9, math 14, independent
entry 7, observer 7, wrapper 10; **47/47 PASS**. I's 380 real-data gates are
separate from those unit-test counts and from all historical upstream results.
Final publication checks **passed**: links, exact hashes, frozen files, evidence
selection and `git diff --check`. An initial new-README relative-link error was
corrected and retained in the local check record. No old numerical chain ran on Mac.

The original 2,056,423-byte CI ZIP matches GitHub's digest
`d8635e9324c6ca0105d79dfd1d56d825083575f3f743a3838d062cb264c85b39`.
Its 36 files, complete terminal/CI records and dense diagnostic arrays remain in
external archive `phase7g-linux-replay-34227336460`. All **48** initial archive
files were restored and hash-verified. An initial local Python 3.9 tarfile API
error was retained; the same archive was then restored using existing Python
3.12.14, without installing anything or repeating a numerical computation.
Final publication files and the delivery Git bundle are appended separately.

The publication references the original numeric packages instead of copying
them. Every I gate and every changed R leaf is retained; repeated per-state
arrays are omitted only with explicit export policy and corresponding all-state
maximum-error/count records. The raw receipt hashes and archive preserve the
full originals. I shares input data, published P/D and NumPy, potentially also
FFT/BLAS, with R. Its new formulas are not a second DFT implementation or
independent human certification. The earlier incidental reading of summary
values by the format-reader author is disclosed in the receipt. Material
[AI assistance](../../../docs/ai-assistance.md) remains explicit.

The limited public Mg replay is complete, with a demonstrated frozen-checker
platform-byte limitation. Numerical interpretation remains **REVIEW_REQUIRED**;
native QE NL **NOT_MEASURED**, original Q H_input residual **NOT_AVAILABLE**,
physical convergence **NOT_ESTABLISHED**, IEEE origin **NOT_LOCALIZED**.
All new SCF, eigen/occupation solves, QE/pp, Julia science, XC, regenerated P/D,
parameter scans and full upstream physical suites are **NOT_RUN**.
Further value lies in more discriminating real SOC cases and interface review,
subject to separate human review, not in repeatedly reducing this case's J.
No next scientific stage, PR, main merge or upstream communication was started.
