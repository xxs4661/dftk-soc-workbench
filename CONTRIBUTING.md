# Contributing

This workbench contains restricted scientific prototypes and case-specific
validation. Start with [current capabilities](docs/status.md) and the
[evidence policy](docs/evidence-policy.md); internal checks do not imply physical
convergence, external agreement or an architecture accepted by maintainers.

Keep contributions small and independently reviewable. Preserve mathematical
reference implementations and scientific failures as well as successes. Do not
copy or translate QE source algorithms, modify upstream checkouts, or communicate
upstream without separate explicit authorization. Do not redistribute UPF files
without verified permission or commit credentials, private paths, caches, source
copies, large binary arrays or raw working directories.

Existing source locks, Project/Manifest/checksums, case inputs and result records
are frozen. A new scientific case or environment requires its own reviewed exact
source/input provenance; do not silently update historical locks to describe it.
Record actual loaded code, executable identity, UPF SHA-256, units and thresholds
before interpreting new results.

1. Branch from the explicitly accepted base; preserve user changes and history.
2. Update affected documentation, command entry points and `docs/status.md` with
   the change. Unaffected documents do not need a new date.
3. Bind claims to specific inputs, execution versions, evidence and limitations.
   New functionality without external validation must not be called aligned.
4. Preserve NOT_RUN/BLOCKED results. Run affected tests, the publication checker,
   link/hash checks and `git diff --check`; do not weaken assertions or skip missing
   evidence to accommodate moved paths.
5. Store raw runs in ignored local directories and publish through explicit
   whitelists. Review the exact staged file list and diff; do not blindly copy
   a complete run or stage the whole tree.
6. Use ordinary commits. No automated amend, force-push or history rewriting.
   Documentation updates do not authorize merging main. After review the owner
   integrates the default branch by a separate explicit action.

Disclose material AI assistance as in [the existing disclosure](docs/ai-assistance.md).
Contributors remain responsible for understanding, testing and interpreting their
changes and responding to review.
