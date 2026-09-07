# Phase 7E review — local ionic potential and signed ledger

The two requested pp.x calls and the saved-field extraction completed. The P0 registration and numerical identities pass their predeclared gates. G=0 is supported at the level of **same-build pp reconstruction bound to historical G40**, not historical in-memory potential extraction. The remaining energy combination is still unresolved; numerical review remains required.

## Execution and source identity

- Base: `fe5e4c85700f5902afee9a345b9f1bb2c8e58e1a`.
- Branch: `codex/phase7e-qe-local-potential-audit`.
- Preparation: `de92ca3ee6591bf0f76bf8d8ec08ab4540f77280`; exact plan, P2/P0 inputs, identity and format/gates committed before numerical invocation.
- Executed version: `8c18549536dbd0c0a6d337e6cdedd319f3788d70`. The later publication checker has its separate current file hashes in [evidence](mg-soc-qe-local-potential/evidence.json).
- Original worktree was clean at the accepted base; 299 predecessor files other than the five current navigation pages remain byte-identical. No history rewriting or core/dependency changes. Final delivery SHA is supplied after its ordinary commit, without self-referential amend.

| Operation | run_id | Process/recorder exit | Actual numerical calls |
| --- | --- | --- | --- |
| P2 | `20260907T160845617600Z-P2-9842a6f9` | 0 / 0 | 1 pp.x |
| P0 | `20260907T160907555915Z-P0-5fa78c40` | 0 / 0 | 1 pp.x |
| Saved DFTK field | `20260907T160918658618Z-Dfield-90372b75` | 0 | 0 solver / model / XC calls; saved arrays and FFT only |

Run IDs use UTC; native QE banners use host local time (Asia/Shanghai). P2 ran before P0. Both use the existing `pp.x → qe-jll → qe-runner.jl → QuantumEspresso_jll.pp` product path; one process and the same five single-thread environment variables as G40. No numerical retries or alternate executable were used. Both filplot headers confirm 40³ allocated/physical grids, no padding, ibrav=0, 10 bohr cell, Mg position (0.17,0.23,0.31), 10 valence electrons, 30 Ry and dual=4. Exact INPUTPP bytes are in the [plan](../benchmarks/mg-soc-qe-local-potential-v1/plan.json).

Existing QuantumEspresso_jll **7.5.1+0**, UUID `74603b90-2fcf-5710-a7d7-830b31b8b33c`, selects artifact `273d3312b2a70e6223250dbf4a39ab3f28b04104` on aarch64 macOS / MPICH. Its wrapper declares both executable products. Fresh read-only product inspection and actual paths, launcher/runner hashes, package metadata, the 19 previously audited loaded libraries, and unchanged global Julia Project/Manifest bind the shared build; neither filename nor version alone is used. Exact installed QE source commit remains unconfirmed.

- pw.x SHA-256: `0500a3db2fc668d4e558d6e667522fbd62793bdf87631776e6b0c4bc3c4e50f0`.
- pp.x SHA-256: `cb94cb4b430f5ac52300c5377998a5a7f70f06441da9b24814762cf2324786bd`.
- G40 original SCF: `20260907T112107073262Z-G40-3f9731a6`, **HISTORICAL_REUSED**. All 23 original run files matched the Phase7B archive. XML, charge and UPF were ordinary independent copies, with unchanged XML resolving an additional same-hash `pseudo/Mg.upf`. No wavefunctions were needed. Original full-tree and required working-copy after-checks are unchanged.
- Mg UPF SHA-256: `19b117bfa920945bffaee91eefbcfbf9fd44e035f3708b965aae59aabf3be256`. One Mg, FR-NC, 10 electrons, PBEsol, no NLCC, the original lattice/k/cutoff/tau are retained.
- Saved DFTK source: successful Phase7D `20260907T144446657126Z-8fa3b4d2`; arrays SHA-256 `09f440183eac2db99168a7729079471074f7f0b1536fa8e229732e268d029c93`. Metadata/receipt, producer commit and same-machine archive were authenticated before Julia deserialization.
- Fresh workbench identity: `20260907T155851653535Z-f643dbdb`, exit 0. Julia 1.12.7, DFTK 0.8.0 at `2f51b91213e26726fb9c6a17e5fae235a1412d01`, PseudoPotentialIO 0.3.3 at `fec942781560c391f20214ba4cd85fb2431deb84`, both clean. Manifest SHA `5b8ae036ac430219a95d61a5e3cd20074e9ecd252335253bf7ada81278b08c37`. Actual package paths compared before redaction; extractor identity exactly matches the producer environment.

## Representation and precision

Native `5(1pe17.9)` payload tokens are preserved losslessly, with token-specific nearest decimal halfwidths. Ry→Ha is applied once to P2 and its halfwidths; P0 is electron/bohr³ unchanged. First index is fastest and only physical nodes enter integration. Noncubic, sheared, padded and phase-sensitive synthetic fixtures test these conventions independently of the production parser. [Tagged format/call-chain sources](../benchmarks/mg-soc-qe-local-potential-v1/filplot-conventions.md) document public pp initialization, including normal local/Hartree/XC reconstruction.

P0 versus high-precision Q_rep: **64000/64000 nodes pass**, with no axis/origin/conjugacy search. Maximum point difference 4.972970924e−10 electron/bohr³; L2 4.636839512e−10 electron/bohr^(3/2). Each point is checked against its own token halfwidth plus 1e−12·max(1,|Q_rep|). Electron difference −2.054889592e−11 against token integral halfwidth 2.232696875e−9 plus 1e−8 electron. All 17 complex modes pass; maximum difference 8.358460578e−14 electron/bohr³. The main integral uses Q_rep, never P0 printed values.

Full 64000-bin FFT/IFFT and direct-mode checks pass normalized <=1e−11. Public real/Fourier energy disagreement is at most 2.84217e−14 Ha (gate 1e−9). The public reconstruction of original A/B/Q and V_D differs by at most 1.78e−15 electron/bohr³ and 7.11e−15 Ha. Original A local+Pc drift is 0; B drift −1.42109e−14 Ha. Public last-bit reconstruction shifts are separately labelled and not written back to historical values.

| Mean / bound | Ha |
| --- | ---: |
| P2 reconstructed mean C_Qpp | 0.0091858274452322735 |
| Tagged C_Q | 0.0091858274460375842 |
| C_Qpp − C_Qtag | -8.05310679253e-13 |
| C_D_book = Pc/10 | 0.0091874945220993924 |
| Original DFTK mean, accurate node sum | -4.96407152749e-19 |
| DFTK Fourier zero representative | -4.4408920985e-18 |
| u_meanV | 1.36988230469e-10 |
| u_L_Q from Q_rep | 1.91368667775e-08 |
| Companion bound using both printed inputs | 3.77715335054e-08 |

The two print targets 1e−8 Ha (mean) and 1e−7 Ha (local energy) are met. These are output-quantization bounds, not rigorous total numerical/physical error bounds. The tiny native DFTK mean is retained (different reductions can round it to zero); it is not manually removed. The non-fitted G0 consistency rule is u_meanV+1e−9 Ha. Its success supports only this pp reconstruction and tagged prediction.

## Local integrals and complete signed bookkeeping

Original-array direct integrals in Ha/cell:
- L_D_A: `-79.433027427910432`.
- L_D_B: `-79.433027427909877`.
- L_D_Q: `-79.433035290243012`.
- L_Qpp_Q: `-79.341181264377838`.
- L_Qpp_printed_P0: `-79.341181264345167`.

All use dvol=1000/64000 bohr³. Independent ordinary Fourier inner products retain G0 and Nyquist, without ±G doubling. Pc is the historical 0.09187494522099392 Ha and is added once only in bookkeeping. No SCF E/F is corrected.

| Signed term | A−G40 Ha/cell | A meV/cell | B meV/cell |
| --- | ---: | ---: | ---: |
| Historical E | +2.29477776799e-05 | +0.624440842 | +0.624440842 |
| Historical Hartree | -5.96704343181e-06 | -0.162371524 | -0.162371530 |
| Historical XC | +2.64708180087e-06 | +0.072030765 | +0.072030765 |
| Historical Ewald | +1.84041049067e-08 | +0.000500801 | +0.000500801 |
| Historical O combination | +2.62493352068e-05 | +0.714280799 | +0.714280806 |
| Local L+Pc combination | +2.87816883997e-05 | +0.783189640 | +0.783189655 |
| Local child: density response | +7.86233257961e-06 | +0.213944969 | +0.213944984 |
| Local child: nonzero G shape | +4.24858714817e-06 | +0.115609946 | +0.115609946 |
| Local child: G0 | +1.66707686711e-05 | +0.453634725 | +0.453634725 |
| Remaining O combination | -2.53235319292e-06 | -0.068908841 | -0.068908849 |

Total recombination uses H + XC + Ewald + local parent + remainder; the three local children are not added a second time. Their exact identity retains N_Q=10.000000000000004 and mean_D. Only a labelled auxiliary formula uses N_model·(C_D−C_Qpp). The historical partition subtracts the explicit original-field drift. Largest original local/total closure discrepancy is below 5e−15 Ha (gate1e−10).

The remaining A combination is -0.068908841 meV/cell with print halfwidth 0.000520741 meV/cell. Correlated occurrences of the same printed V are combined symbolically before propagating widths; no independent-noise/RSS or assumed cancellation is used.

`Q_TNL_ledger_post = 14.861932472417436 Ha` is labelled **DERIVED_LEDGER_REMAINDER_USING_PP_RECONSTRUCTED_LOCAL_INTEGRAL**. It is O_Q from the historical ledger minus a new reconstructed-field integral, not independently measured QE T+NL, separate T or NL, or an isolated SOC error. Endpoint/eband/deband/SCF-correction and reconstruction limits from Phase7D remain.

Nonzero G maximum complex coefficient difference is 2.246459863e−6 Ha at (12,14,4); raw and zero-mean field L2 are 0.290599118972 and 0.008271764840 Ha·bohr^(3/2). All 64000 representatives are retained. Of these, 41881 lie outside the actual saved QE list of 22119. P2’s largest outside coefficient 2.53950e−12 Ha is compatible with its uniform print bound 1.36988e−10 Ha plus floating margin. The DFTK outside-support field L2 0.008271753354 dominates the field shape norm, **but those modes do not contribute to shape_at_Q**, since the specified finite Q series lacks them. This does not assert unknown physical modes are zero or identify a physical cause of the in-support energy difference.

## Evidence, commands, tests and preservation

Public evidence is one full potential coefficient pack, the two complete native filplot gzip files, raw stdout/stderr and bound small receipts, one complete replay result and the original-array source receipt. The Phase7C densities and Phase7D ledger are referenced by path/hash. Every coefficient integral, registration test and token uncertainty can be recomputed from these public inputs. Source arrays/save/UPF and full preparation/debug records remain local and in the external archive.

Actual operations (portable interpreter/depot names replace private installation paths; exact local commands and exit records are archived):

```sh
python3.12 scripts/run_recorded.py identity
julia --startup-file=no scripts/probe_qe_postprocess_build.jl
python3.12 scripts/run_qe_local_postprocess.py P2
python3.12 scripts/run_qe_local_postprocess.py P0
JULIA_DEPOT_PATH=<frozen-existing-depot> JULIA_LOAD_PATH=@:@stdlib OPENBLAS_NUM_THREADS=1 JULIA_NUM_THREADS=1 julia --startup-file=no --color=no --project=environment/workbench scripts/extract_saved_local_field.jl .work/phase7e/field-request.json .work/phase7e/20260907T160918658618Z-Dfield-90372b75
python_numpy scripts/check_qe_local_potential.py --all --legacy-python python3.9
git diff --check
```

Python/NumPy backend is existing Python3.12.14 / NumPy2.3.5; no packages installed. Frozen Julia1.12.7 independently performs source-field FFT checks. Public replay never launches Julia, QE or reads .work/private data. The unchanged older check chain uses Python3.12 and Python3.9.6 for its historical summation contract.

Raw incremental archive: `phase7e-20260907T154626Z`, **same machine, not offsite**. Manifest SHA `a1ee6f033d36e05f569745a50d4bbfe2172349793508e464751f487a5fc45059` verifies 39 new files / 24,862,588 bytes. Five restore samples verify 11,042,807 bytes, including both native filplots and the complete DFTK field/coefficients. Older7B/7D sources remain manifest references. Full process logs, ordinary Git increment and exact-final-checkout verification are recorded separately in that archive.

Both pp stderr files contain **IEEE_OVERFLOW_FLAG**. No new trap/debug/compiler experiments were run. Historical IEEE origins remain **NOT_LOCALIZED**. Successful pp calls did include normal local/Hartree/XC initialization, so this is not described as “zero XC evaluation.”

## Tests and delivery checks

| Check actually run | Result | Archived/local log |
| --- | --- | --- |
| New Python synthetic contracts: filplot19 + recorder13 + comparison20 + full FFT10 + publication19 | **81/81 PASS**, exit0, no skips | `.agent-work/phase7e/new-tests-final.log` |
| Saved-array/FFT Julia synthetic tests | **54/54 PASS**, exit0 | `.work/phase7e-preflight/saved-local-field-synthetic-attempt-2.log` |
| Affected prior Python tests: energy ledger/comparison/public/runner, density/Hartree/public/recorder, QE charge and both process runners | **162/162 PASS**, exit0, no skips | `.agent-work/phase7e/affected-tests.log` |
| Full public replay, including unchanged predecessor chain | **PASS**, exit0 | `.agent-work/phase7e/full-public-check-attempt1.log` |
| Frozen 299 files, original G40 full tree, DFTK saved source, QE dependencies and both upstream checkouts | **PASS**, clean/unchanged | final source-preservation receipt in process archive |
| `git diff --check` | **PASS**, exit0 | final validation log |
| Exact final Git checkout, public files only | Performed after final commit; result and exact SHA recorded in external final-commit verification and final reply | archive `final-commit-public-replay.log` |

The initial staged whitespace check returned exit2 because six native QE stdout lines contain trailing spaces. Both new public stdout files were losslessly gzip-compressed; raw bytes and raw hashes are unchanged, and full original files remain archived. No numerical run was repeated.

The 81-test invocation loads `test_qe_filplot`, `test_qe_local_postprocess`,
`test_qe_local_potential_comparison`, `test_qe_local_fields_replay` and
`test_qe_local_potential_public` through unittest with the existing NumPy
interpreter. Its five-module list, count and log SHA are in public evidence.
The corresponding new negative tests reject malformed/wrong-unit/padded
fields, wrong sources and hashes, stale outputs, process/parse/storage failure,
field/phase/P0 defects, Pc factors, double-counting, false T/NL labels and
incorrect precision propagation. Negative cases passing means their invalid
inputs were rejected. These are workbench synthetic tests, never new DFTK
upstream or physical runs. Historical 1387/1387 and earlier92/67/100 are not
used as current results. Full upstream tests remain NOT_RUN.

## Final status and limits

| Status dimension | Result |
| --- | --- |
| pp_build_identity / historical_G40_binding | PASS |
| P2_postprocessing / native_filplot_parse | PASS |
| P0_density_registration / DFTK_saved_local_field | PASS |
| qe_local_potential | RECONSTRUCTED_BY_SAME_BUILD_PP_FROM_BOUND_G40 |
| historical_in_memory_vloc / internal_tab_vloc | NOT_EXTRACTED |
| G0_prediction_comparison | SUPPORTED_BY_PP_RECONSTRUCTED_MEAN |
| local_same_density / nonzero_G_shape | MEASURED_WITH_P0_AND_PRINT_LIMITS / MEASURED_COMPLETE_NATIVE_GRID |
| local_energy_decomposition / derived_remaining_combination | PASS_ALGEBRA / DERIVED_NOT_INDEPENDENT_T_NL |
| output_precision | PASS targets; not a total-error certificate |
| numerical_review / physical_convergence | REVIEW_REQUIRED / NOT_ESTABLISHED |
| residual_attribution / IEEE origin | PARTIALLY_QUANTIFIED / NOT_LOCALIZED |
| independent_QE_T_NL | NOT_AVAILABLE |
| new SCF / eigensolve / independent XC / parameter scans / full upstream suite | NOT_RUN |

No real postprocessing call failed, was blocked or retried, and no precision gate was relaxed. An initial **synthetic** Julia test hit an unsupported temporary-directory keyword (32 passed, one error); only that new test was fixed, and its failed log is retained. Synthetic negative cases are validator tests, not physical failures. No historical result or failure was removed. The remaining O residual, potential reconstruction vs historical-memory distinction, installed source-commit uncertainty, unresolved T/NL composition and physical convergence remain open. Work stops for review; no next scientific phase, PR, main update or upstream contact is authorized by this delivery.
