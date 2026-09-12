# Current capabilities and validation

This table describes the experimental workbench with its completed-core baseline
and supplementary validation, linking each conclusion to its evidence. It distinguishes function
support, numerical comparison, parameter sensitivity and independent replay.
A checker's exit 0 applies to its stated contract, not to every row of this table.

| Area | Implemented and observed | Remaining limitation / evidence |
| --- | --- | --- |
| FR-NC input handling | Source-index-aware metadata acceptance; explicit relativistic channels and NLCC/common-data binding. | NC scope only; the frozen native DFTK SOC rejection stays intact. [Acceptance](../results/upf-acceptance/README.md), [conventions](../prototypes/relativistic/CONVENTIONS.md). |
| Spinor representation and nonlocal operators | Two components, capacity-one occupations, FR spin-angular projectors and matrix-free nonlocal action; dense, angular, scalar-limit and time-reversal checks. | Prescribed CPU Float64/ComplexF64 cases; synthetic accuracy is separate from real-UPF quadrature. [Representation](../results/spinor-no-soc/README.md), [projectors](../results/relativistic-projectors/README.md). |
| Charge-only Hamiltonian and SCF | Common local/kinetic/Hartree/XC terms plus FR nonlocal action, seven-term energy, FD entropy and closure checks; real Mg and Si endpoints. | Nonmagnetic charge-only closure; magnetic XC is not implemented. [Hamiltonian](../results/fr-hamiltonian-energy/README.md), [Mg SCF](../results/mg-soc-scf/README.md), [Si](../results/si-soc-splitting/README.md). |
| Si SOC spectrum and control | Workbench/QE fixed Γ-window splitting, multiplet widths and same-density spin-trace control meet their contracts. | Γ occupation saturation and full manifold assignment remain REVIEW_REQUIRED; irreps and continuous band tracking are not established. [Corrected status](../results/si-soc-splitting/status-correction/README.md). |
| Si parameter sensitivity | Paired cutoff/temperature/k-grid perturbations; the 2³→4³ split response exceeds the 0.1 meV observation window in both codes. Historical QE-only 4³→6³→8³ steps are within that window. The new workbench K6 SCF stopped under the resource-headroom rule: FAIL, native/outer 1/1. | K6 Γ BLOCKED_PARENT; new dense-grid cross-code comparison NOT_ASSESSED; workbench K8 NOT_RUN; full physical convergence NOT_ESTABLISHED. [Paired data](../results/si-soc-sensitivity/README.md), [QE reference](../results/si-soc-k-reference/README.md), [K6 outcome](../results/soc-extra/README.md). |
| Mg cross-code energy and spectra | QE SCF, solver/FFT controls, raw/global-reference spectra, Fourier/Hartree, local-field and original-orbital energy diagnostics. | Agreement remains REVIEW_REQUIRED; pp-reconstructed fields are not original SCF memory. Independent native QE nonlocal energy NOT_MEASURED; IEEE origin NOT_LOCALIZED. [Mg evidence](../results/README.md#magnesium-cross-code-comparison-and-energy-reference). |
| Scalar energy-reference baseline | Si SR-LDA matched inputs and a local-potential finite-term diagnostic, with limited cutoff/k sensitivity. | Distinct input/family from Si SOC and PBEsol Mg; limited scans do not establish physical convergence. [Scalar baseline](../results/scalar-si-baseline/README.md), [reference audit](../results/scalar-si-sensitivity/README.md). |
| Reusable core and live adapter | Original static gates and completed 9A endpoints remain COMPLETED_UNCHANGED. A fresh B0 SCF/own-density Γ regression passes, including dispatch and release. Finite B0/K4 profiling retains the existing core; the two-map K6 pilot completed without establishing SCF convergence. | Earlier timing PERFORMANCE_REVIEW_REQUIRED persists; no new overall speedup is established. Pilot completion and engineering admission did not guarantee the formal K6 run. [Interfaces](soc-core-runtime.md), [static measurements](../results/soc-core-memory/README.md), [completed regression](../results/soc-core-memory/completion/README.md), [supplementary evidence](../results/soc-extra/README.md). |
| Public numerical replay | Core energy/spectrum arithmetic, Si finite-window data and the complete published Mg G40 Q orbital/density representation have specified public replay paths. Supplementary replay retains the K6 failure while checking recorded arithmetic. Mg independent Linux path I passed; frozen path R exited 1 for two derived-density hashes. | A/B full orbital extraction, private core density differences and resource measurements remain runner-reported. Linux native SCF/Γ remains NOT_RUN; public replay is distinct from it. [Scopes](reproducibility.md), [Linux record](../results/mg-soc-public-replay/linux/README.md). |
| Broader software support | Experimental independent workbench; source and ownership boundaries are documented. | Native upstream SOC integration/acceptance not established. Forces, stress, geometry optimization, USPP/PAW, DFPT, GPU/AD and MLP are outside validated scope. [Integration questions](soc-upstream-risks.md). |

## Reading the statuses

**PASS** means that the named recorded test or numerical comparison meets its
unchanged contract. **REVIEW_REQUIRED** preserves an unresolved interpretation,
occupation condition or performance observation. **NOT_RUN** identifies an
unperformed operation; **NOT_ASSESSED** and **NOT_ESTABLISHED** identify missing
comparisons or evidence for a broader conclusion.

Full physical convergence is not established for the SOC material predictions.
Good agreement between two codes at one setting and small regression differences
between two implementations do not replace a convergence study. Native solver
warnings and IEEE flags remain in the relevant case records.

The [history index](history.md) preserves earlier states, including failed runs
and whole-tree checker incompatibilities. Current documentation is updated in
place; those historical result bytes are not relabeled. For actual commands,
start with [getting started](getting-started.md) rather than a historical driver.
