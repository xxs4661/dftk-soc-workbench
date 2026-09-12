# One K6 retry: control contract

This continuation starts at `e40def9dcfd243131adae1ce16d8b22815560a87`.
The [machine-readable plan](k6-retry-10gib.json) fixes the two run IDs,
attempt numbers, resource policies, numerical body hashes and unchanged K6
input before execution. The actual clean execution commit is bound by one
local grant and a registry in the repository's common Git directory.

Only the second formal K6 SCF may use 10,737,418,240 bytes, with warning at
8,589,934,592 bytes. Its Gamma and all entry checks retain the default 8/7 GiB.
The original slot, failed run, plans, source lists and public evidence remain
unchanged. Another UUID, directory or worktree cannot mint another attempt.
The new fixed reservation is exclusive; a started worker consumes it even
when parsing, monitoring, computation or persistence fails.

## Resource admission and stopping

The new SCF uses fixed remaining growth **2,021,538,619 bytes**. Compared with
the old floor of 2,021,087,414 bytes, the increase accounts for the old formal
run's one-record history rather than the two-record pilot, and the slightly
larger observed serialization capacity. The four terms are 536,418,495
(uncovered history), 277,160,572 (serialization), 134,217,728 (later output),
and 1,073,741,824 bytes (unobserved fluctuation).

The old formal group's peak was 7,447,937,024 bytes; the separately measured
worker highwater was 7,528,939,520 bytes. Their maximum plus the fixed growth
is **9,550,478,139 bytes**. The source budget, retaining its original 2 GiB
runtime reserve, is **8,203,424,092 bytes**. Both fit the one-time limit as
engineering screening, not a strict memory bound. Buffer capacity residency
and transient allocations remain uncertain; no term is set to zero to pass.
Fresh host pressure, swap activity, process and disk checks are still required.

Gamma has its own positive fixed growth allowance of **1 GiB** for subsequent
solver/output fluctuations. It constructs one k point, reads the authenticated
K6 checkpoint and does not hold 216 simultaneous Gamma workspaces. Historical
B0 Gamma observed 1,693,384,704 bytes of group RSS; the K6 two-map checkpoint
payload was 806,502,837 bytes. These are contextual observations, not a proof
of the new Gamma peak or substitutes for its own 8 GiB monitoring. Entry and
parent checkpoint reads are also monitored under 8 GiB.

Every observation independently checks hard limit/serious pressure, then
`max(accumulated group peak, authenticated worker highwater) + fixed growth
>= effective limit`, then warning. A stop is latched even when current RSS
falls. The first reason is retained in an atomic, identity-bound stop file.
Julia checks the same policy at safe boundaries; an unresponsive worker is
escalated to owned-process termination after 30 seconds. Sampling is about
0.1 seconds and is not operating-system memory isolation. Cleanup alone
cannot make a resource-stopped run successful.

## Frozen science and evidence

No mathematical, SCF, FD, solver, seed, tolerance, layout or lifecycle
implementation changes are authorized. Whole-file checks protect the core,
upstream checkouts, environment, inputs and old evidence; frozen mathematical
regions protect the unchanged numerical bodies in edited driver files.
Old B0, pilot, performance, failed K6 and QE evidence retain their original
execution identity, `96795a6b2bf2ca4f6c8dcf6546287eb95bfe4504` where applicable.

Before SCF, synthetic tests exercise the sampler-to-Julia stop chain,
independent policy scopes and Gamma's actual parent hash echo, without a
material context or solve. Actual Gamma entry is permitted only after the
new SCF fully passes closure, resource, save and cleanup checks. Its parent
is checked under the parent's 10 GiB policy, and the child under its own 8 GiB.

Only qualified new SCF/Gamma endpoints permit comparison with historical
QE K6. The original fixed-state and 0.1 meV contracts remain unchanged.
Failure leaves comparison `NOT_ASSESSED`; default public replay can faithfully
replay a failure, whereas strict K6 replay cannot pass it. New compact evidence
belongs in `results/soc-extra/k6-retry-10gib/`. No B0, pilot, performance,
Linux, K8, QE/pp, CI or subsequent scientific stage is executed here.
