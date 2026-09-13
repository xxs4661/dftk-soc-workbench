# Bounded timing and cancellation diagnostic

Base E0 is `30befbc22ee52283a19a96694bfe20259891b583`, authenticated against
the canceled K6 recorder and repository-external archive. This is a continuation
of engineering validation, not Phase 9B. The archived 19 complete maps and partial
map 20, native −2 / recorder 9, unconfirmed runtime close and unverified resume
remain historical facts. Their uninstrumented time will not be assigned new costs.

Implementation boundary: a small default-off scalar timer/typed-stop helper;
`prototypes/soc_scf/{scf,solver}.jl` and the shared spinor controller for boundary
wrappers only; the existing Si driver plus thin diagnostic routing; the existing
Python executor/recorder hooks for owned-process control. No matrix-core,
physics, solver/mixing formula, frozen environment, input or historical evidence
changes. Preserve existing validation, fingerprints, checkpoint writes and RNG.

Control contract: first valid run/version-bound stop request is latched.
USER_CANCELLED (130), TIME_BUDGET_EXCEEDED (124), DIAGNOSTIC_MAP_LIMIT (0,
DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED), resource stops and failures are distinct.
Actual negative OS exits remain negative. Missing/stale receipts remain missing;
cleanup and scientific success are separate. No canceled SCF PASS/final.bin.
Independent deadlines request cooperation; owned group TERM after 120 seconds,
KILL after 10 further seconds, cleanup check after 5. Resource emergency remains
independent. Synthetic chain tests have seconds deadlines and a five-minute batch.

Timing contract: monotonic process-local hierarchical spans, inclusive and self
time, explicit interrupted/truncated records, no parent/child double count. Full
map includes controller work and callback. Old elapsed_seconds stays unchanged.
Cover startup/context, H/boundaries, k initial/solver/checks/output, FD, density,
energy, fingerprints/serialization/write, map callbacks and close. No per-matvec
instrumentation, object retention, profiling, forced GC or optimizations.

After control tests and source/environment checks, freeze clean E1. Single starts:
T-B0-REF exact independent E0 (15 min), T-B0-TIMED E1 (15 min), then only if both
complete and equivalent, T-K4-TIMED E1 (30 min). Each at most two maps; total batch
60 min including startup and gaps, with no next start below five minutes left.
All 8 GiB limit / 7 GiB warning, single thread, original uniform initial density,
seed 81001, 30 Ha / 48³ FFT / tau .001 / 24+6 states / alpha .1 / tol 1e-10 /
maxiter 300 / physical max_maps 400. B0 and historical K4 inputs are immutable.
No K6/K8, Gamma, QE, full SCF, CI, retry or historical warm start.

B0 map 1 and 2 separately: absolute E/F differences ≤1e-10 Ha; relative density
norm difference ≤1e-10 using max(norms,1); same-k raw 24-state differences ≤1e-9 Ha.
No fitted references. Incomplete pairs are not PASS. Cold paired times do not
establish instrumentation overhead. Publish compact numeric records, cancellation
receipts, timing definitions and offline checks; archive only new raw output.
Run researcher replay and the stdlib core example in their original scopes.
Inspect the complete unpushed ancestor range before ordinary new-branch-only push.
