# Phase 7F review — original orbitals and a bounded energy audit

The finite static audit passed every predeclared engineering gate in one run.
It identifies no new scientific implementation error. It resolves original-state
ownership and separates a same-evaluator orbital/occupation response from a
remaining cross-source combination. Native QE nonlocal energy remains unmeasured.

## Provenance, sequence and unchanged boundary

Base: `28e67d4aca41e11b38a6364503e2dbacc0dd1ee4`.
Branch: `codex/phase7f-wavefunction-energy-audit`.
Preparation: `aa088185ac1cbb134856c74e56134b21428806c2` (plan, formulas, headers, sources, thresholds committed
before any full coefficient/checkpoint read).
Execution: `dc8a97dbdf1ebf2fa2bfb52c38db01fcde3c927e`.
Run: `20260907T173343831194Z-80727713`, execution exit0, no formal retries.
The final ordinary commit SHA is reported after committing; no amend is used.

Initial worktree was clean at the accepted base. The frozen loaded identity is
Julia1.12.7, DFTK0.8.0 at2f51b91213e26726fb9c6a17e5fae235a1412d01 and
PseudoPotentialIO0.3.3 atfec942781560c391f20214ba4cd85fb2431deb84, both clean.
Actual resolved paths, UUIDs, Project/Manifest/source-lock hashes and before/after
identity checks are in the [plan](../benchmarks/mg-soc-wavefunction-energy-v1/plan.json)
and [nonlocal receipt](mg-soc-wavefunction-energy/nonlocal-checks.json).
No frozen core, prior configuration, dependency or historical numerical file changed.
Only the five current navigation pages change among pre-existing tracked files.

Before extraction,29 original files (41,715,394 bytes) were verified against
existing Phase7B/7C archive manifests and their current copies. Q is original
G40 SCF `20260907T112107073262Z-G40-3f9731a6`, not D40/C40/bands. A/B are
`20260906T151940Z-A-270110aa` and `20260906T153016Z-B-62835d43`.
Their SCFs are HISTORICAL_REUSED; all orbital arithmetic here is new static
postprocessing. Exact wfc/checkpoint/XML/charge hashes are in the plan.

## What was actually measured

1. **Binary and spinor identity.** Header and envelope checks uniquely found
   little-endian four-byte Fortran markers, I4/L4 and ComplexF64. The official
   QE7.5 writer/producer chain establishes up-NG then down-NG per band and
   already-Cartesian k/B in bohr^-1. The actual installed exact QE source commit
   remains NOT_CONFIRMED. `ngw` is a maximum original global G index, while
   `igwx`=2777/2770/2770 is the selected count; the reader does not conflate them.
   All three files have24 spinor states, ispin1, gamma=false and scale1.
   Occupations are original XML wg/wk, including exact zeros; original A/B tiny
   occupations remain intact. No conjugation, fitting, QR or normalization occurs.

2. **Density and representation.** Q recovers all22119 saved complex coefficients:
   max5.204170427930421e-18 e/bohr³, nonzero relativeL2
   4.522540301901716e-16. Direct enumeration proves all21421 possible within-k
   G−G products are inside that support and fit40³ (no Nyquist ambiguity).
   This certifies the complete finite orbital-product representation; it does not
   assume unknown physical modes zero. A/B original n_out maximum node differences
   are1.3322676295501878e-15 e/bohr³; relativeL2≤2.708e-16.
   Maximum norm error≤6.551e-15, Gram Frobenius≤2.169e-14, all electron gates pass.
   The17 independent correlation checks differ from FFT by≤5.365e-18 e/bohr³.

3. **Direct kinetic energy and A/B restoration.** Q T=29.07598791063465 Ha/cell,
   from original coefficient probabilities and |G+k|²/2, not an energy remainder.
   Its separate real-space covariant-gradient integral differs by−1.0658141036401503e-14 Ha.
   A T=29.075984450811465 and B T=29.07598445081151 Ha; both restore their
   historical T within3.553e-15 Ha. The same original f and one spatial weight
   enter each path. Analytic tilted-cell/nonzero-k tests independently detect
   omitted k, extra2π and transposed reciprocal columns.

4. **Frozen FR single operator.** Only after all preceding gates passed, three
   static FR blocks were built. P dimensions are5554×16,5540×16,5540×16 with
   full common16×16 D. The exact DFTK G order is authenticated by historical
   serialization hashes; Q is transferred by integer-G bijection and explicit
   block-to-interleaved spin rows. A N_D=−14.214054510747257 and
   B N_D=−14.214054510747609 Ha restore historical values within1.777e-15 Ha.
   Q N_D=−14.214055437803232 Ha is explicitly **DFTK's frozen FR operator on
   original QE orbitals**, not native QE NL. Action, projected and full spin-cross
   contractions agree within3.553e-15 Ha. No full Hamiltonian was built.

## Signed combination and print precision

All numbers below are Ha/cell; A is primary and B auxiliary. Full precision,
per-state tables, source tokens and signs remain in the [canonical comparison](mg-soc-wavefunction-energy/comparison.json).

| Term | A−Q | B−Q |
| --- | ---: | ---: |
| Direct ΔT | -3.459823187057509e-6 | -3.4598231408722313e-6 |
| Same-operator ΔN_D | +9.270559750973462e-7 | +9.27055623378692e-7 |
| S_response = Δ(T+N_D) | -2.532767211960163e-6 | -2.5327675174935393e-6 |
| J_Q, shared cross-source combination | +4.14040357554768e-10 | same |
| δL = L_saved − L_wfc, shared P2 | -4.883910697653117e-14 | same |
| New minus historical K drift | -3.552713678800501e-15 | -1.7763568394002505e-15 |
| Original Phase7E R | -2.5323531929188903e-6 | -2.532353505557694e-6 |

The A response is−0.06892010687580442 meV/cell: ΔT−0.09414658508582285
plus ΔN_D+0.02522647821001843. J_Q is+0.00001126661209084687 meV/cell.
Original E/F (A−G40+0.624440842 meV/cell) is unchanged.

O_Q=−64.47924879196043; L_wfc=−79.34118126437781.
The derived O_Q−L_wfc−T_Q=−14.214055438217272 is
`DERIVED_NL_SHAPED_REMAINDER_NOT_DIRECT_QE_NL`.
R_old=S_response+J_Q+δL−drift_S, with the stored old O grouping drift and
saved-local-replay drift explicitly retained; final closure error is
8.004311850237948e-15 Ha. No total-energy correction or empirical constant is used.

The reused P2 is a pp-reconstructed field, not original SCF memory. Its native
per-node token halfwidth propagates to u(L_wfc)=1.9136866777499194e-8 Ha
and u(J_Q)=1.9136882777499192e-8 Ha. The same potential is shared, so
u(δL)=dvol Σ|n_saved−n_wfc|uV=1.3429428949923918e-23 Ha; repeated P2/O
coefficients are combined before bounds. No independent-noise or RSS assumption.
J lies within this print interval, which is not a physical error bound or proof
of equality. δL and the closure drift are Float64 roundoff scale: this tiny print
halfwidth does not establish corresponding arithmetic or physical resolution.
The NumPy determinant returns1000.0000000000007 for the fixed10-bohr cube;
that ordinary rounding is disclosed, not a modified physical volume.

## Evidence levels and unresolved questions

The complete lossless Q coefficient package plus P/D replays Q density, both T
paths and the explicitly labeled DFTK operator expectation. A/B X remain private:
public per-state T/norm/f and complex up/down amplitudes replay scalar/projected
sums, while their extraction and n_out restoration are RUNNER_REPORTED.
Regenerating P needs the exact locked UPF and frozen Julia environment; it is
separate from applying the already published matrices. No duplicate density,
native WFC, UPF, private path or A/B checkpoint is published.

Q weighted eband agrees with the original XML to3.553e-15 Ha. This only checks
original f/epsilon bookkeeping; it is not H[n_in]ψ−εψ. The final saved output
charge, earlier deband/input-H state and subsequent output-density energy
reconstruction retain their separate meanings. Native QE NL is NOT_MEASURED;
original input-H residual is NOT_AVAILABLE. The result gives a clearer signed
response and remainder, without identifying a new scientific implementation bug.

There is no present evidence requiring further numerical compression of this
single-case J. The recommended next step is independent review/replay of this
public orbital/P/D package and its state conventions before approving any new
scientific stage. No next stage was started. Physical convergence remains
NOT_ESTABLISHED, IEEE origin NOT_LOCALIZED, interpretation REVIEW_REQUIRED.

## Commands, tests, archive and limits

The measurement command and exact execution identities are in
[evidence.json](mg-soc-wavefunction-energy/evidence.json). It used existing
Python3.12.14/NumPy2.3.5 and frozen Julia with one Julia/BLAS thread.
Raw child requests, output, exit receipts and cached arrays are under
`.work/phase7f/20260907T173343831194Z-80727713`; full process logs are archived.
The safe recorder publishes its final success result last; tests cover malformed
formats, source/occupation mismatch, storage failure and stale success reuse.

Final relevant test totals are152 new Python,88 new Julia synthetic and114
directly affected historical Python tests, all exit0 (354 assertions/tests counted
by their native suites; earlier reruns are not added). The complete public
Q coefficient/FR and historical check chain passed, exit0.
The new external archive `phase7f-20260907T170754Z` contains105 raw files,
36,067,236 bytes; all hashes verified. Raw-manifest SHA256 is
`6cbae7697fad7d87fd8022eed32ed05dbf0b9372f3a5b3a23f090cf0dea97487`.
Actual restore of the orbital NPZ and comparison JSON passed (2 files,6,180,000 bytes).
This is same-machine repository-external storage, not offsite. Test/log hashes,
process manifest and exact commands are in the evidence manifest. Exact-final-commit
clean-checkout replay is a postcommit delivery check, reported in the final reply
and external delivery receipt without amending this report. Synthetic
fixtures are not real pseudopotential or SCF evidence. Historical1387/1387 is
not a result of this phase; full upstream physics tests were NOT_RUN.

No formal scientific FAIL/BLOCKED or interrupted run occurred. Retained setup
issues: one synthetic Julia log redirection failed before launching Julia because
its new output directory was absent; a syntax-only system-Python bytecode check
hit its external cache permission; a read-only optional old-file lookup and a
mistyped working-directory invocation failed. These did not run physics and are
not hidden behind scientific PASS. Completed tests and formal work use the stated
existing runtimes; all failures and corrections remain in external process records.

Explicitly NOT_RUN: new SCF, eigensolve, occupation solve, pw.x/pp.x, independent
XC, extra Hartree/local-potential evaluation, scans, IEEE experiments and full
upstream test suite. No frozen code, historical result, source lock or environment
was changed. Only this development branch will be pushed; no PR/main/upstream
operation is authorized or performed in this phase.
