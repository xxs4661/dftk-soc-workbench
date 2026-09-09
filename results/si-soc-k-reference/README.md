# Si QE k-grid reference trend — Phase 8C

All four prescribed QE slots completed once, with exit 0, on the same clean
execution commit. The fixed-setting K4→K6 and K6→K8 Γ splitting changes are
**+0.047128386 and +0.008621197 meV**; both meet the predeclared 0.1 meV
finite-step observation window. The K4/K6/K8 range is **0.055749582 meV**.
This does not establish a converged physical value or a new DFTK/QE comparison.

## Sources and fixed scope

- Branch: `codex/phase8c-si-k-reference-trend`.
- Accepted base: `557571fa6beb29e1ee57a5a0701ab3bded41fc78`.
- Preparation: `4ba043c42141cce775dd5e5beed0f16b84b1e91b`.
- Exact clean numerical execution: `0af11bac432bfec7f9cf0d07b0571d3ae9449010`.
- Public provenance tooling: `b0a68dcc384237086ac3373aba54de4a3decaeb0`.
  Its independently bound replay hash does not replace the executed source hashes.
- Final delivery SHA and post-commit clone receipt are reported after the ordinary
  results commit, without self-referential hashes or amended history.

The [plan](../../benchmarks/si-soc-k-reference-v1/plan.json),
[allowed differences](../../benchmarks/si-soc-k-reference-v1/allowed-differences.json),
[source index](../../benchmarks/si-soc-k-reference-v1/sources.json) and
[numerical contract](../../benchmarks/si-soc-k-reference-v1/replay-contract.json)
were committed before execution. Only SCF k points/weights and operational
profile/prefix/path fields differ from K4: Si a=10.26 bohr, two atoms, PBE/NLCC,
fully relativistic NC, eight electrons, 24 capacity-one spinors, 60/240 Ry,
48³ hard/smooth FFT, tau=.001 Ha and the original solver settings remain fixed.
No numerical formula, DFTK driver, frozen dependency or historical result changed.

Actual existing UPF SHA-256:
`cc91a6be43c3c89daf6c34410096e8d870f25152dbfb513bcf01afa5ab53eabf`.
Every slot authenticated the same QE 7.5 / JLL 7.5.1+0 build, launcher, global
Project/Manifest and 19 selected libraries against the historical Q environment.
Binary SHA-256: `0500a3db2fc668d4e558d6e667522fbd62793bdf87631776e6b0c4bc3c4e50f0`.
Frozen clean DFTK `2f51b91213e26726fb9c6a17e5fae235a1412d01` and
PseudoPotentialIO `fec942781560c391f20214ba4cd85fb2431deb84` remained unchanged.
Per-slot build receipts and complete execution/input hash maps are indexed in
[evidence.json](evidence.json). Only read-only Julia/JLL identity initialization
was run; no DFTK numerical context was loaded.

B0 is HISTORICAL_REUSED from physical commit
`3948ed5d37660fe1e909aa6d12983234e317a479`, published at
`61cb1c226dcfa8dbeccc63e8f43e33b2790a07c6`: parent
`Q-SCF-20260908T145232Z`, Γ `Q-SPECTRUM-20260908T145443Z`.
K4 is HISTORICAL_REUSED from physical commit
`48da17f47e998030a50c954c3abc38bca3a9df8f`, accepted publication 557571f:
parent `Q-SCF-20260909T042657Z-dc321fc6`, Γ
`Q-GAMMA-20260909T043006Z-a98da9a9`.
The source index authenticates the old inputs, results and native outputs by hash;
they are referenced, not copied or rerun. All four old SCF/Γ native datasets were
reparsed by affected Python regression tests within the fixed floating contract.

## Four actual slots and resource checks

| Slot (one attempt) | run_id | worker / native exit | SCF iterations | sampled aggregate peak bytes |
| --- | --- | --- | --- | --- |
| K6/Q-SCF | Q-SCF-20260909T071457Z-22cd55e8 | 0 / 0 | 10 | 852361216 |
| K6/Q-GAMMA | Q-GAMMA-20260909T072256Z-11513d86 | 0 / 0 | — | 401408000 |
| K8/Q-SCF | Q-SCF-20260909T072337Z-ee073458 | 0 / 0 | 10 | 1413398528 |
| K8/Q-GAMMA | Q-GAMMA-20260909T074108Z-6689f34a | 0 / 0 | — | 414154752 |

Capture exits also all equal 0. Exact commands, UTC times, receipt/log hashes and
formal attempt counts are in [validation.json](validation.json). The order was
K6 SCF → K6 Γ → K8 SCF → K8 Γ, serial CPU, one MPI process/thread.
Both SCFs used fresh atomic initialization. Each Γ used its own ordinary copied
SCF save directory, original μ, case identity and full original save-file hash
inventory. Both parents were unchanged before/after; no hard-link aliases.
K6 parent charge SHA-256:
`bf639eb3b7b2a51dfa4a2cecb9cfd7db248196dea1a204931f44fe31f2190707`;
K8: `8d8ca337790e2034a591fe3ec7e747b85e569e3ddd069f048bafa327b4c0e0bb`.

Both preflights completed before either SCF. Independent integer/geometry
enumeration gives K6 216 points, 2085–2138 PW, sum 457287; K8 512 points,
2085–2148 PW, sum 1084665. Every native npw entry matches this predeclared list.
The density sphere has 16865 vectors; G−G′ component maximum 17 is below 48/2.
Full coordinates, weights, inversion and reciprocal mapping are checked.
K6 does not contain K4; K8 contains K4/B0 but not K6. No symmetry reduction.

The unchanged DFTK planning formula gives K6 12,614,633,984 and K8
25,844,114,432 bytes, both BUDGET_EXCEEDS_EXISTING_LIMIT (8 GiB).
These are predictions, not DFTK measured peaks or observed OOMs. Separate QE
budgets were 3,673,014,272 / 4,695,025,664 bytes. Required disk including
save copies, incremental backup/restore and an extra 10 GiB was 20,919,067,648
bytes; initial available disk was 900,706,738,176 bytes.
Native initialization estimated >391.31 / >850.70 MB per process for K6/K8;
the native startup's `0 MiB` available-memory report is retained without an
unsupported explanation. The aggregate peaks above come from 11805 actual
process-group/descendant samples, requested interval 0.1s; they are sampled
measurements, not continuous upper bounds. All ownership/cleanup checks passed,
with no remaining observed processes. Full samples and independent time/RSS
captures are archived, not repeated in public process JSON.

## Fixed Γ window and finite trend

Δ = mean(states 5–8) − mean(states 3–4), using the original unshifted 24-state
own-final-density spectra. No fitted zero, group reordering or infinite-k fit.

| QE case | Origin | Δ (meV) | doublet mean (Ha) | quartet mean (Ha) |
| --- | --- | --- | --- | --- |
| B0 | HISTORICAL_REUSED | 47.457612441977 | 0.2391410719698220 | 0.2408851070591400 |
| K4 | HISTORICAL_REUSED | 47.789119355443 | 0.2296865140331550 | 0.2314427317768395 |
| K6 | NEW_EXECUTION | 47.836247741097 | 0.2283784724936790 | 0.2301364221735914 |
| K8 | NEW_EXECUTION | 47.844868937899 | 0.2281377314067575 | 0.2298959979098087 |

| Step | Signed change (meV) | Absolute change (meV) | 0.1 meV observation |
| --- | --- | --- | --- |
| s24 | +0.331506913466 | 0.331506913466 | CHANGE_EXCEEDS_SCREENING_WINDOW |
| s46 | +0.047128385654 | 0.047128385654 | WITHIN_SCREENING_WINDOW |
| s68 | +0.008621196802 | 0.008621196802 | WITHIN_SCREENING_WINDOW |

`last_step_status` and `last_two_QE_steps_status` are
WITHIN_SCREENING_WINDOW; K4/K6/K8 range =0.05574958245571637 meV.
Signed changes are positive here, but monotonicity is not an error bound.
[trend.json](trend.json) retains signed/absolute values and all limitation states.

| QE case | doublet / quartet width (eV) | lower / upper isolation (eV) | max pair difference (Ha) | min FD f(3:8) |
| --- | --- | --- | --- | --- |
| B0 | 1.38947e-11 / 5.58825e-09 | 11.994618486 / 2.394899188 | 1.23721e-10 | 0.9999595238092915 |
| K4 | 2.28317e-12 / 1.41955e-08 | 11.945814441 / 2.498466869 | 1.73157e-10 | 0.9999930433453087 |
| K6 | 1.91838e-12 / 2.89581e-09 | 11.938707859 / 2.513595255 | 6.15202e-11 | 0.9999933153646072 |
| K8 | 1.26507e-12 / 1.19585e-08 | 11.937374496 / 2.516374262 | 2.24174e-10 | 0.9999700532719865 |

All fixed-window isolation/width/Δ/pairing screens pass: isolation≥.02 eV,
widths≤1e-5 eV, Δ≥.005 eV and pairing≤1e-7 Ha. Native Γ CG threshold is
1e-13 Ry, with normal completion and no unconverged target warning. Explicit
QE wavefunction residuals are NOT_AVAILABLE; input tolerance and rounded stdout
are not substitutes for residuals. The inherited analyzer's
`manifold_assignment_status=PASS` refers only to its isolated fixed window;
complete physical manifold interpretation remains REVIEW_REQUIRED.
All four Γ occupation diagnostics remain REVIEW_REQUIRED at the unchanged
0.99999999 condition. New K6/K8 maximum holes are 6.684635392772975e-6 and
2.9946728013485746e-5; (μ−uppermax)/tau is 11.915692205316102 and
10.41606054049049. Γ uses each original SCF μ; no single-k occupation solve
or enforcement of a Γ occupation sum of 8. Old 8A/8A.1/8B status bytes are unchanged.

## Native thermodynamics and warnings

| QE case | E (Ha/cell) | F (Ha/cell) | −TS (Ha/cell) | original μ (Ha) | weighted Ne |
| --- | --- | --- | --- | --- | --- |
| B0 | -8.368044609134150 | -8.368045123751521 | -5.14617370964603e-07 | 0.2509998633429109 | 8.00000000003654 |
| K4 | -8.455195456677012 | -8.455195469388009 | -1.2710997251013e-08 | 0.2433185369351423 | 8.00000000007297 |
| K6 | -8.461244555145500 | -8.461244558862044 | -3.71654327177084e-09 | 0.2420521144378173 | 8.00000000003173 |
| K8 | -8.461985395193462 | -8.461985401325629 | -6.13216604644069e-09 | 0.2403120586430998 | 8.00000000007116 |

Native F=etot, E=F−demet, −TS=demet. No correction or average is added.
Bands thermodynamics do not replace SCF data. New weighted Ne errors are
3.1733e-11 / 7.1156e-11, maximum FD differences 1.1103e-16 / 8.6398e-19,
and highest two-state occupations 0/0. The complete SCF e/f tables retain
their native precision; the parser and validator use different summation paths and differ in final
rounding bits; both are retained without renormalization.
SCF final error is 1.020398552237514e-13 / 9.441426809955038e-14 Ha;
both original density convergence criteria pass in 10 iterations.

| QE case | SCF unconverged / c_bands lines | Γ unconverged lines | IEEE (SCF and Γ) |
| --- | --- | --- | --- |
| B0 | 12 / 12 | 0 | INVALID, DIVIDE_BY_ZERO, OVERFLOW |
| K4 | 82 / 82 | 0 | INVALID, DIVIDE_BY_ZERO, OVERFLOW |
| K6 | 157 / 157 | 0 | INVALID, DIVIDE_BY_ZERO, OVERFLOW |
| K8 | 388 / 388 | 0 | INVALID, DIVIDE_BY_ZERO, OVERFLOW |

Counts are emitted lines, not numbers of distinct erroneous states. All original
iterations, ethr records, eigenvalue warning lines and stderr remain in the
compressed native text. Both new SCFs remain EIGENSOLVER_REVIEW_REQUIRED despite
normal exit and passing density convergence. Γ has no such warning; all four
new tasks report the three IEEE flags. Underflow/inexact were unreported, which
does not prove absence. IEEE cause remains NOT_LOCALIZED; no localization run.

## Public replay, tests and preservation

From a normal clone retaining Git history, using existing Python 3.12:

```sh
python3.12 -B scripts/si_qe_reference_evidence.py replay
PYTHONPATH=tests python3.12 -B -m unittest -v test_si_soc_comparison test_si_qe_runner test_si_soc_driver test_si_soc_status test_si_sensitivity test_si_sensitivity_driver test_si_sensitivity_qe test_si_soc_sensitivity test_si_qe_reference test_si_qe_reference_resources test_si_qe_reference_monitor test_si_qe_reference_runner test_si_qe_reference_evidence test_si_qe_reference_evidence_bindings
git diff --check
```

Public export and its full native reparse exited 0; a separate public replay also
exited 0. The 32 gzip payloads total 638,583 bytes (3,500,428 bytes / 38,633
lines after decompression); evidence/trend plus these payloads total 655,233 bytes.
Current links, publication paths, decompressed privacy, base-relative boundaries
and `git diff --check` passed; check receipts are in validation.json. Each of the four slots has
one gzip of native input/XML/stdout/stderr plus compact endpoint, iteration,
identity and provenance objects. Gzip/decompressed-public/original-native hashes
are recorded separately in evidence.json. For these 16 native text files, raw
and public SHA-256 are identical: no native text needed path replacement.
Public metadata replaces machine path prefixes; numerical tokens and warnings
are preserved. All final 216/512×24 e/f and Γ 24
are replayed, not only PASS summaries. Old B0/K4 numerical files stay at their
original paths. Replay needs no .work, UPF, private arrays, Julia, QE or NumPy;
saved charge/WFC extraction and resource measurements remain runner-reported,
not independently reproduced from public orbital arrays.

The final affected Python invocation passed 248 tests (144 existing, 104 new),
exit 0; the pre-execution invocation passed 233. Repeated invocations are not
added to these totals, and these are workbench tests, not upstream assertions.
Process-monitor tests use bounded synthetic children and require process-table
access. Preserved initial exit 1 records cover sandbox ps denial, a new-test field
typo, an overstrict derived-float comparison under existing Python 3.9, and the
post-execution draft test's relocation path. Repairs used actual schema/path,
approved process inspection and the already declared floating contract;
no physical retry or threshold relaxation occurred. Logs/hashes and actual
commands are in validation.json and the external increment. Only the public
provenance layer changed after numerical execution, adding complete parent
inventory checks and separately authenticated replay/execute versions.

The [execution archive receipt](archive.json) records 1712 files,
2,422,255,316 bytes, all-file hashes/source recheck, 32 restored required samples,
and a restored incremental Git bundle. Manifest SHA-256:
`41aed633c4af71586ecdf62f65b7153203333d7a36d6097705ec22d425ca004a`.
This is a same-machine directory outside the repository, not offsite protection;
it does not recopy the earlier 2.17 GB archive. The final ordinary commit's clean
public-clone replay and verified post-execution archive supplement receive
separate post-commit receipts, without backfilling a future SHA into this report.

DFTK K6/K8: NOT_RUN (exit null). New-grid same-parameter cross-code comparison:
NOT_ASSESSED. Physical, zero-temperature and joint cutoff/FFT convergence:
NOT_ESTABLISHED. Complete manifold interpretation: REVIEW_REQUIRED. No new Mg,
pp.x, DFTK numerical/Julia physical test, null, p/−p, independent XC, additional parameter
scan, CI or full upstream suite was run. The four QE tasks did perform their
normal SCF/bands/FD/Hartree/XC/projector work. Historical 7G R FAIL/1, I PASS/0,
CI failure and earlier scientific limitations remain unchanged and NOT_RERUN.
The authorized sequence is complete; stop for human review. A later DFTK
dense-grid anchor requires its own resource work and matching calculation;
these QE results cannot replace it.
