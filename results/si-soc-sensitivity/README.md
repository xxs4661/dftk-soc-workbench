# Si Γ SOC finite parameter sensitivity — Phase 8B

All 12 predeclared formal slots completed with worker/wrapper/capture exit 0. The three public datasets were replayed in an isolated clone. The verified same-machine incremental archive preserves complete new runs and process records; final-commit replay is recorded in the delivery supplement and post-commit response.

Completed public stages: E40, T05, K4 (12 completed formal slots of at most 12). Each completed stage separates execution, input comparability, fixed-window structure, code agreement, response agreement, FD diagnostics and physical interpretation. A process or offline replay exit 0 is not a physical convergence claim.

**The k-grid response exceeds the observation window.** K4 raises ΔD by 0.33150569714 meV and ΔQ by 0.331506913466 meV, both above the predeclared 0.1 meV window. Its code and response agreement screens are PASS and PASS. E40 and T05 changes stay within that finite-step window. This supports compatible responses between implementations while leaving B0's k-grid sensitivity visible; it does not establish k convergence. E40/K4 retain FD REVIEW_REQUIRED; T05's own-case FD diagnostic passes without changing historical B0.

Branch `codex/phase8b-si-soc-sensitivity`; accepted base `bc68aaf655d96dfd4335f6fa1a8e5ee76477c2a3`; preparation `4a58286183e4625ad7ae69b44eb80097e8ad6c7d`; executed source `48da17f47e998030a50c954c3abc38bca3a9df8f`. Final SHA belongs in the post-commit delivery response; it is not fabricated here.

[Frozen matrix and contracts](../../benchmarks/si-soc-sensitivity-v1/README.md) fix the same Si UPF (SHA-256 `cc91a6be43c3c89daf6c34410096e8d870f25152dbfb513bcf01afa5ab53eabf`), diamond primitive cell (a=10.26 bohr, two atoms), 8 electrons, charge-only PBE SOC with NLCC, 24 physical spinor states, capacity one and actual 48³ FFT. Each direction changes B0 independently; there is no combined E40+K4+T05 run.

| Case | D cutoff / Ha | QE wfc/rho / Ry | SCF k points | τ / Ha | Data status |
| --- | --- | --- | --- | --- | --- |
| B0 | 30 | 60 / 240 | 8 | 0.001 | HISTORICAL_REUSED |
| E40 | 40 | 80 / 320 | 8 | 0.001 | NEW_EXECUTION |
| T05 | 30 | 60 / 240 | 8 | 0.0005 | NEW_EXECUTION |
| K4 | 30 | 60 / 240 | 64 | 0.001 | NEW_EXECUTION |

B0 is bound to numerical publication `61cb1c226dcfa8dbeccc63e8f43e33b2790a07c6`, physical execution `3948ed5d37660fe1e909aa6d12983234e317a479`, and the accepted [status correction](../si-soc-splitting/status-correction/README.md) executed at `a03f91f56875a80e5b058fd86377ee0cd9317939` and delivered at the accepted base. Its Γ reference is the original own-final-density [D spectrum](../si-soc-splitting/D-spectrum.json) and [Q spectrum](../si-soc-splitting/Q-spectrum.json). No B0 calculation was rerun. B0 ΔD=0.04745761517555575 eV, ΔQ=0.04745761244197689 eV; B0 FD/physical review remains unchanged. Historical null is a B0-only reference, not a new variant control.

The main observable is mean(Γ states 5–8) minus mean(states 3–4), without an energy-zero fit. The two predeclared agreement screens are |D−Q|≤1e−4 eV and |responseD−responseQ|≤1e−4 eV. The separate |responseP|≤1e−4 eV screen describes a finite step, not correctness or an error bound.

| Case | ΔD / eV | ΔQ / eV | code gap / eV | D response / eV | Q response / eV | response gap / eV |
| --- | --- | --- | --- | --- | --- | --- |
| E40 | 0.0474563599241 | 0.0474563581802 | 1.74389874763e-09 | -1.25525143094e-06 | -1.25426175083e-06 | -9.89680115637e-10 |
| T05 | 0.0474575974178 | 0.0474575946906 | 2.72724065553e-09 | -1.77577345606e-08 | -1.77513963528e-08 | -6.33820773643e-12 |
| K4 | 0.0477891208727 | 0.0477891193554 | 1.51725272624e-09 | 0.00033150569714 | 0.000331506913466 | -1.21632613703e-09 |

| Case | Slots D/Q SCF, D/Q Γ | Inputs | Γ structure D/Q | Γ pairing D/Q | Code screen | Response screen | Finite-step D/Q |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E40 | PASS/PASS/PASS/PASS | PASS | PASS/PASS | PASS/PASS | PASS | PASS | WITHIN_SCREENING_WINDOW/WITHIN_SCREENING_WINDOW |
| T05 | PASS/PASS/PASS/PASS | PASS | PASS/PASS | PASS/PASS | PASS | PASS | WITHIN_SCREENING_WINDOW/WITHIN_SCREENING_WINDOW |
| K4 | PASS/PASS/PASS/PASS | PASS | PASS/PASS | PASS/PASS | PASS | PASS | CHANGE_EXCEEDS_SCREENING_WINDOW/CHANGE_EXCEEDS_SCREENING_WINDOW |

For all variants, `numerical_review_status=REVIEW_REQUIRED`, `physical_manifold_interpretation=REVIEW_REQUIRED`, and `physical_convergence=NOT_ESTABLISHED` remain separate. E40 raises wavefunction and density/potential spherical cutoffs together at fixed FFT and ratio; their effects are not separated. K4 and T05 prescribe one finite step each, without asymptotic, joint or zero-temperature inference. The three responses are not added into a joint error budget or used to fit an infinite-resolution limit.

| Case / code | Doublet width / eV | Quartet width / eV | Lower isolation / eV | Upper isolation / eV | Kramers max / Ha | min f(3:8) | max hole | (μ−εupper)/τ | FD diagnostic |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E40 / D | 1.73711568368e-14 | 3.53465278244e-13 | 11.994617704 | 2.39492229084 | 7.21644966006e-15 | 0.999959541171 | 4.04588290558e-05 | 10.1151852078 | REVIEW_REQUIRED |
| E40 / Q | 1.72359639205e-11 | 3.03009809127e-08 | 11.9946177462 | 2.39492233466 | 2.46552389616e-10 | 0.999959542288 | 4.04577119874e-05 | 10.1152128193 | REVIEW_REQUIRED |
| T05 / D | 4.30502582477e-14 | 8.98013281694e-13 | 11.9946204741 | 2.39489398702 | 4.88498130835e-15 | 0.999999998979 | 1.02068620222e-09 | 20.7027905859 | PASS |
| T05 / Q | 1.32277582974e-11 | 5.98977351273e-09 | 11.9946206447 | 2.39489380525 | 1.27934801641e-10 | 0.999999998945 | 1.05494901703e-09 | 20.6697733157 | PASS |
| K4 / D | 1.05737476398e-14 | 7.77925719213e-14 | 11.9458144444 | 2.49846684292 | 6.10622663544e-15 | 0.999993042363 | 6.9576367252e-06 | 11.8756637346 | REVIEW_REQUIRED |
| K4 / Q | 2.28317422251e-12 | 1.41955054448e-08 | 11.9458144407 | 2.49846686902 | 1.73156516903e-10 | 0.999993043345 | 6.9566546913e-06 | 11.8758048903 | REVIEW_REQUIRED |

The unchanged FD saturation threshold is 0.99999999. Γ diagnostics use the own parent SCF μ and actual case τ; Γ weights of one do not impose eight electrons or feed occupations back into SCF. T05's new-case FD PASS does not revise B0's original REVIEW_REQUIRED or establish zero-temperature physics. Γ precision uses D explicit state residuals and Gram, or QE's reported CG threshold 1e−13 Ry plus native termination/warnings. QE explicit wavefunction residuals are NOT_AVAILABLE; stdout rounding agreement is not a residual bound.

| Case / code | Native E / Ha | Native F / Ha | −TS / Ha | μ / Ha | SCF electron sum |
| --- | --- | --- | --- | --- | --- |
| E40 / D | -8.36803206441 | -8.36803257884 | -5.14426526747e-07 | 0.181767426257 | 8.0000000000001137 |
| E40 / Q | -8.36805281988 | -8.36805333433 | -5.14443458835e-07 | 0.250998766836 | 7.9999999999069002 |
| T05 / D | -8.36802432242 | -8.36802432243 | -1.15418577936e-11 | 0.182005665222 | 8.0000000000002256 |
| T05 / Q | -8.36804507974 | -8.36804507975 | -1.15388752124e-11 | 0.251220492159 | 7.9999999999660565 |
| K4 / D | -8.45517469209 | -8.4551747048 | -1.27107708584e-08 | 0.174087082223 | 8.0000000000000888 |
| K4 / Q | -8.45519545668 | -8.45519546939 | -1.2710997251e-08 | 0.243318536935 | 8.0000000000729727 |

QE F is native etot and E=F−demet; D uses spinor entropy once at the actual τ. No additive constant, occupancy capacity-two factor, total-energy correction, E/F average or zero-temperature extrapolation is used. The canonical data also retain separate −TS and entropy responses from B0.

**E40:** D performed 180 maps including the actual closure; Q SCF required 11 iterations (reported SCF error 1.68377360878e-13 Ha). D unmixed density residual 1.25227735337e-09; H[n_in] maximum state residual 9.03530841278e-11 Ha; H[n_out] old-eigenvalue residual 4.65437947681e-09 Ha; maximum Gram 1.69627028708e-14; Pauli density ratio 1.43206111396e-12. D stationarity EVALUATED on 18 partially occupied states, maximum residual 2.52575738102e-15 Ha. Top-two physical-state occupation maximum 5.06596167024e-173; energy-sum/double-counting discrepancies 0/7.1054273576e-15 Ha. Its separate D-GAMMA maximum state residual is 9.17053726782e-11 Ha, Gram 3.18752344434e-14. These array-dependent checks are RUNNER_REPORTED; their scalar/per-state reports are public, original arrays remain in local storage and the verified delivery archive.

E40 uncorrected E(D−Q)=2.07554753313e-05 Ha/cell and F(D−Q)=2.07554922635e-05 Ha/cell. Own-program E response from B0: D -8.21257345329e-06, Q -8.21075018287e-06 Ha/cell; F responses: D -8.21238661253e-06, Q -8.21057627043e-06. The two response-gap arithmetic routes differ by 0 eV.

E40 Q-SCF: 12 reported unconverged-eigenvalue lines; EIGENSOLVER_REVIEW_REQUIRED. IEEE: IEEE_INVALID_FLAG, IEEE_DIVIDE_BY_ZERO, IEEE_OVERFLOW_FLAG; NOT_LOCALIZED. All original warning lines are retained in the native logs.

E40 Q-GAMMA: 0 reported unconverged-eigenvalue lines; REPORTED_THRESHOLD_AVAILABLE. IEEE: IEEE_INVALID_FLAG, IEEE_DIVIDE_BY_ZERO, IEEE_OVERFLOW_FLAG; NOT_LOCALIZED. All original warning lines are retained in the native logs.

**T05:** D performed 180 maps including the actual closure; Q SCF required 12 iterations (reported SCF error 4.45365875025e-14 Ha). D unmixed density residual 1.25189088468e-09; H[n_in] maximum state residual 9.98553414221e-11 Ha; H[n_out] old-eigenvalue residual 4.55019265716e-09 Ha; maximum Gram 1.44761285369e-14; Pauli density ratio 1.21600987838e-12. D stationarity is NO_RESOLVABLE_PARTIAL_OCCUPATIONS: zero states meet the unchanged endpoint margin 1e-08. The stored zero maximum is not a measured derivative residual and no stationarity derivative PASS is inferred. Top-two physical-state occupation maximum 0; energy-sum/double-counting discrepancies -1.7763568394e-15/7.1054273576e-15 Ha. Its separate D-GAMMA maximum state residual is 9.17418696003e-11 Ha, Gram 3.36531389523e-14. These array-dependent checks are RUNNER_REPORTED; their scalar/per-state reports are public, original arrays remain in local storage and the verified delivery archive.

T05 uncorrected E(D−Q)=2.0757319648e-05 Ha/cell and F(D−Q)=2.07573196462e-05 Ha/cell. Own-program E response from B0: D -4.70587711021e-07, Q -4.70608757297e-07 Ha/cell; F responses: D 4.40141150193e-08, Q 4.39970744281e-08. The two response-gap arithmetic routes differ by 0 eV.

T05 Q-SCF: 12 reported unconverged-eigenvalue lines; EIGENSOLVER_REVIEW_REQUIRED. IEEE: IEEE_INVALID_FLAG, IEEE_DIVIDE_BY_ZERO, IEEE_OVERFLOW_FLAG; NOT_LOCALIZED. All original warning lines are retained in the native logs.

T05 Q-GAMMA: 0 reported unconverged-eigenvalue lines; REPORTED_THRESHOLD_AVAILABLE. IEEE: IEEE_INVALID_FLAG, IEEE_DIVIDE_BY_ZERO, IEEE_OVERFLOW_FLAG; NOT_LOCALIZED. All original warning lines are retained in the native logs.

**K4:** D performed 179 maps including the actual closure; Q SCF required 10 iterations (reported SCF error 2.74554597604e-13 Ha). D unmixed density residual 1.25471792798e-09; H[n_in] maximum state residual 9.99017074776e-11 Ha; H[n_out] old-eigenvalue residual 2.56782265417e-09 Ha; maximum Gram 1.88791876739e-14; Pauli density ratio 1.17433414167e-13. D stationarity EVALUATED on 18 partially occupied states, maximum residual 1.20459198172e-14 Ha. Top-two physical-state occupation maximum 1.85287295374e-174; energy-sum/double-counting discrepancies -1.7763568394e-15/8.881784197e-15 Ha. Its separate D-GAMMA maximum state residual is 8.75389498637e-11 Ha, Gram 3.38111558554e-14. These array-dependent checks are RUNNER_REPORTED; their scalar/per-state reports are public, original arrays remain in local storage and the verified delivery archive.

K4 uncorrected E(D−Q)=2.0764591655e-05 Ha/cell and F(D−Q)=2.07645918806e-05 Ha/cell. Own-program E response from B0: D -0.0871508402498, Q -0.0871508475429 Ha/cell; F responses: D -0.0871503383472, Q -0.0871503456365. The two response-gap arithmetic routes differ by 0 eV.

K4 Q-SCF: 82 reported unconverged-eigenvalue lines; EIGENSOLVER_REVIEW_REQUIRED. IEEE: IEEE_INVALID_FLAG, IEEE_DIVIDE_BY_ZERO, IEEE_OVERFLOW_FLAG; NOT_LOCALIZED. All original warning lines are retained in the native logs.

K4 Q-GAMMA: 0 reported unconverged-eigenvalue lines; REPORTED_THRESHOLD_AVAILABLE. IEEE: IEEE_INVALID_FLAG, IEEE_DIVIDE_BY_ZERO, IEEE_OVERFLOW_FLAG; NOT_LOCALIZED. All original warning lines are retained in the native logs.

| Case | Slot | Actual run ID | Exit worker/wrapper/capture | Execution | Elapsed / s | Peak RSS / GiB |
| --- | --- | --- | --- | --- | --- | --- |
| E40 | D-SCF | D-SCF-20260908T231632Z-2f8ec6f8 | 0/0/0 | PASS | 2198.805268 | 2.49043273926 |
| E40 | Q-SCF | Q-SCF-20260908T235336Z-24e47971 | 0/0/0 | PASS | 24.631624 | 0.287704467773 |
| E40 | D-GAMMA | D-GAMMA-20260908T235442Z-08406d4a | 0/0/0 | PASS | 22.122498 | 1.61065673828 |
| E40 | Q-GAMMA | Q-GAMMA-20260908T235547Z-3d6c87ec | 0/0/0 | PASS | 4.784229 | 0.287673950195 |
| T05 | D-SCF | D-SCF-20260908T235632Z-200bf045 | 0/0/0 | PASS | 1917.047969 | 2.3837890625 |
| T05 | Q-SCF | Q-SCF-20260909T002844Z-fbb97f24 | 0/0/0 | PASS | 20.683307 | 0.286743164062 |
| T05 | D-GAMMA | D-GAMMA-20260909T002926Z-8e9a0eb1 | 0/0/0 | PASS | 18.958852 | 1.44386291504 |
| T05 | Q-GAMMA | Q-GAMMA-20260909T002956Z-f7dfe0a4 | 0/0/0 | PASS | 4.014199 | 0.286849975586 |
| K4 | D-SCF | D-SCF-20260909T003031Z-dc60968c | 0/0/0 | PASS | 14166.18891 | 3.4009552002 |
| K4 | Q-SCF | Q-SCF-20260909T042657Z-dc321fc6 | 0/0/0 | PASS | 120.728844 | 0.286743164062 |
| K4 | D-GAMMA | D-GAMMA-20260909T042914Z-ad8659b7 | 0/0/0 | PASS | 19.36315 | 1.61418151855 |
| K4 | Q-GAMMA | Q-GAMMA-20260909T043006Z-a98da9a9 | 0/0/0 | PASS | 4.237308 | 0.287292480469 |

All real tasks use the frozen local macOS arm64 environment, one Julia/BLAS/FFT thread and one MPI process. [D identity](D-environment.json) records Julia 1.12.7, DFTK 0.8.0 at `2f51b91213e26726fb9c6a17e5fae235a1412d01` and PPIO 0.3.3 at `fec942781560c391f20214ba4cd85fb2431deb84`, both clean. [QE identity](Q-environment.json) binds QE 7.5, JLL 7.5.1+0, binary SHA-256 `0500a3db2fc668d4e558d6e667522fbd62793bdf87631776e6b0c4bc3c4e50f0` and the unchanged launch chain. Each run receipt rebinds its own case, input, source, environment and executed code.

[Preflights](preflights.json) completed for all three profiles before the first new SCF. The first E40 preflight `prepare-20260908T231125Z-570f7af9` failed: invocation exit 1, worker exit 143, partial worker record still RUNNING; MPI local-interface creation was denied by the execution sandbox and memory accounting was unavailable. This was not a numerical convergence failure or a formal SCF attempt. The original failure is retained. Subsequent permitted preflights passed with unchanged settings; conservative peaks E40/T05/K4 were 3,650,039,552 / 3,389,229,056 / 5,889,778,688 bytes (<8 GiB). Actual G−G′ extrema and requested QE sphere support fit 48³; native QE output independently confirms the used hard/smooth grids for completed runs.

The local K4 export preparation also recorded two failures, separate from the 12 successful numerical slots. An index filter included the E40/prepare entry as formal and its count assertion exited 1; the initial text export then exited 1 because the required immutable index snapshot was absent. Action-based selection and saving the snapshot fixed this export preparation, after which text-only export succeeded. The original note `K4-export-preparation-failure-note.json` and export-K4 logs remain in the local incremental archive scope. No physical slot, parameter, source input or numerical result was rerun or changed to correct these failures.

[Case reproduction commands](../../benchmarks/si-soc-sensitivity-v1/README.md) retain one controlled profile per invocation, all-three preflight gating and own-parent density binding. Each profile's `data.json` is the canonical full SCF endpoint and 24-state Γ dataset; `comparison.json` is its arithmetic/status summary. All 24 raw Γ levels are retained, with a diagnostic comparison after subtracting each program's single Γ quartet mean; no per-state shift or fitted reference is used. `D-trace.json`, `D-final-checks.json`, slot receipts and compressed native logs retain trace, diagnostics and adverse evidence. Export manifests distinguish source and public hashes. Existing B0 evidence is referenced; UPF and private wavefunction/density/checkpoint arrays are not included. The public data can replay spectra, occupations and response arithmetic but do not independently reproduce array-dependent SCF or operator checks from scratch.

Existing-code allowlist: `scripts/run_si_soc.jl`, `scripts/run_si_dftk.py`, `scripts/run_si_qe.py`, `scripts/si_soc_comparison.py`, `prototypes/soc_scf/solver.jl` (only `validate_soc_settings`) and `prototypes/soc_scf/scf.jl` (only contract forwarding). Default B0 settings and rejection rules remain; only authenticated T05 accepts τ=.0005. Frozen scientific formulas, upstream source, dependencies, original case/result bytes and historical checkers are unchanged. Current boundary and publication checks are recorded in [checks.json](checks.json); exact execution code remains bound separately from this results commit.

[Checks](checks.json) retain distinct preparation and final rerun receipts. The final affected rerun at executed source `48da17f47e998030a50c954c3abc38bca3a9df8f` passed 156 Python tests (107 existing,49 new), exit 0, and 223 Julia synthetic assertions (118 existing,105 new), exit 0. The preparation run passed the same counts; these two invocations are not added into a larger test suite. These are workbench tests, not upstream tests or new physical evidence. Historical numerical replay in its 61cb snapshot exited 0; historical status replay in bc68 exited 0 by default and 1 with the required-manifold option. The historical strict failure, Phase 7G R FAIL/I PASS and CI failure, and Phase 6C frozen-checker compatibility failure remain unchanged. Current publication-table, boundary, links/privacy and diff checks returned 0; their pre-commit receipts are recorded separately in checks.json. Exact-final-commit replay is performed after the ordinary results commit and retained in the external delivery supplement, so no self-referential final SHA or premature replay claim is embedded here.

**Not performed:** new variant spin-trace/null, p/−p spectra, Mg calculations, pp.x, zero-temperature calculation, independent scalar UPF, new material, extra scans/initial states/solver retries, independent XC directional checks, Phase 7G CI, full upstream suites or IEEE localization. Off-Γ TR and continuous band tracking are NOT_ASSESSED; irrep labels are NOT_COMPUTED; native QE nonlocal energy is not independently measured; magnetic XC and upstream support are not established. New SCF, eigen/occupation solves, SCF-internal XC and frozen projector construction did occur within completed authorized slots. Their execution is not on the NOT_RUN list.

Stop after the predeclared three cases and finite analysis, preserve unresolved results, and await human review. No convergence extrapolation, new parameter point, PR, main push, merge or upstream contact is authorized by this report.

The execution increment `phase8b-increment-20260909T043806Z-26d5ea45` contains 1,012 files / 2,169,931,913 bytes. Every file was hashed and the source snapshot rechecked; 19 bound restore samples and incremental Git-bundle restoration passed. Manifest SHA-256: `b7d188e6877f0f375aa62a79f81af4c16021da435d7b3d97da69b4679e833427`. This is a same-machine backup outside the repository, not off-site. The final Git bundle and post-archive checks are a separate delivery supplement.

The retained initial E40/T05 public reviewer exited 2 because its local protocol assumption excluded the frozen FD plateau branch with zero bisection iterations. Correcting only that ignored reviewer to check the existing plateau semantics gave a later exit 0; numerical data and scientific thresholds did not change. Original failure and correction logs are hash-referenced in [checks.json](checks.json).

## Public-only arithmetic replay

From the repository root, use Python 3.11 or newer (this delivery used 3.12.14).
This checks public bytes, then invokes the frozen comparison entry for each
canonical dataset. It creates temporary JSON text only; no `.work`, UPF,
private arrays, Julia or QE are needed. Exit 0 certifies replay under the
[predeclared contract](../../benchmarks/si-soc-sensitivity-v1/replay-contract.json),
including retention of K4's exceeded window and all review statuses.

```sh
python3.12 -B - <<'PYCODE'
import hashlib, json, math, subprocess, sys, tempfile
from pathlib import Path
root = Path.cwd()
result = root / 'results/si-soc-sensitivity'
evidence = json.loads((result / 'evidence.json').read_text())
for name, entry in evidence['public_files'].items():
    raw = (root / name).read_bytes()
    assert len(raw) == entry['bytes'], name
    assert hashlib.sha256(raw).hexdigest() == entry['sha256'], name

def close(a, b):
    assert type(a) is type(b)
    if isinstance(a, dict):
        assert a.keys() == b.keys()
        for key in a: close(a[key], b[key])
    elif isinstance(a, list):
        assert len(a) == len(b)
        for left, right in zip(a, b): close(left, right)
    elif isinstance(a, float):
        assert math.isfinite(a) and math.isfinite(b)
        assert abs(a-b) <= 1e-11 * max(1, abs(a), abs(b))
    else:
        assert a == b

for profile in ('E40', 'T05', 'K4'):
    data = json.loads((result / profile / 'data.json').read_text())
    with tempfile.TemporaryDirectory(prefix='si-response-') as directory:
        command = [sys.executable, '-B', 'scripts/si_soc_sensitivity.py',
                   '--root', str(root), '--profile', profile]
        for key in ('D-SCF', 'Q-SCF', 'D-GAMMA', 'Q-GAMMA', 'binding'):
            path = Path(directory) / (key + '.json')
            path.write_text(json.dumps(data[key], allow_nan=False))
            command += ['--' + key.lower(), str(path)]
        actual = json.loads(subprocess.check_output(command, text=True))
    expected = json.loads((result / profile / 'comparison.json').read_text())
    close(actual, expected)
    print(profile, 'REPLAY PASS', actual['limited_parameter_stability_status'])
PYCODE
```
