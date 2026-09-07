# Capability and validation status

This is the single complete current capability table. It describes evidence at
the historical development snapshot `8658992afa936f6cdb1a8055699ae9aa47b32297` and
the first Phase 7A QE SOC comparison based on published main
`77bd2e151116bcc189b797e6da415d27a61d3a2b`, plus Phase 7B diagnostics based on
`9d49ca88bfe3c4add0e6c80c1376f006d065e306`, and the Phase 7C saved-array audit
based on `d2ed86316bd030f9d662a1089edb83c94d8f2607`. All original SCFs remain
HISTORICAL_REUSED. Phase 7C performs NEW_EXTRACTION_FROM_HISTORICAL_ARRAYS;
Phase 7D adds NEW_POSTPROCESSING_OF_HISTORICAL_STATES based on
`45225ee1accabd0aae36acec072f0f6ba7dd1de8`; Phase 7E adds two bound pp reconstructions based on
`fe5e4c85700f5902afee9a345b9f1bb2c8e58e1a`. Main is unchanged.
Acceptance of a development starting point is not an independent expert rerun;
historical `REVIEW_REQUIRED` fields remain unchanged.

| Capability | Evidence and scope | Limit / next validation |
| --- | --- | --- |
| FR-NC UPF acceptance and recorder | [Strict Mg metadata acceptance, exact native SOC rejection, regression code](../results/upf-acceptance/README.md) | Native DFTK constructor rejection remains intact; information-only parsing is not acceptance. |
| Scalar Si / QE 7.5 | [B0 matched 30 Ha, eight-point input and raw spectra](../results/scalar-si-baseline/README.md) | One Si SR-LDA NC input; raw eigenvalue reference differs. |
| Energy-reference and limited sensitivity | [B0/C1/C2/C3, independent local-potential finite-term diagnostic](../results/scalar-si-sensitivity/README.md) | Only 30/40/50 Ha and eight/64 points; complete k convergence NOT_ESTABLISHED. QE internal G=0 value was not directly extracted. |
| No-SOC spinor representation and SCF | [Fixed-potential test; independent A/B spinor and C scalar closures](../results/spinor-no-soc/README.md) | Nonmagnetic LDA, capacity-one spinors; no noncollinear magnetic XC. |
| Relativistic channels / nonlocal operator | [CG and independent L·S, Gaussian and real Mg quadrature, Si scalar limit](../results/relativistic-projectors/README.md) | CPU prescribed fixtures; synthetic analytic accuracy is distinct from real-UPF quadrature sensitivity. |
| Full FR Hamiltonian and energy | [Seven terms, orbital variations and fixed-density eigenpairs](../results/fr-hamiltonian-energy/README.md) | Fixed-density test is not SCF; density mismatch and old-spectrum energy mismatch are retained limitations. |
| Charge-only SOC SCF | [Independent Mg A/B, 191 maps each, 24 target states per k point](../results/mg-soc-scf/README.md) | PBEsol Mg, three explicit k points, 15 Ha, tau=0.001 Ha; internal engineering closure only. No resolvable partial occupations in actual endpoint stationarity check. |
| QE SOC comparison | [New Mg QE 7.5 SCF, one fixed-density refinement and Phase 6C A/B](../results/mg-soc-qe-comparison/README.md). QE execution: **PASS**. | E/F and raw/global-reference spectra compared; numerical agreement **REVIEW_REQUIRED**. FFT 36³ vs 40³; SCF eigenvalue warnings and native IEEE flags retained. Density L2 comparison NOT_RUN. |
| QE solver/FFT/IEEE diagnostics | [Six prescribed slots, identical-density D/C and one 40³ SCF control](../results/mg-soc-qe-diagnostics/README.md). All slots executed; I36 is initialization only. | D/C stability observed at both grids; A−QE E/F remains +0.624440842 meV/cell at 40³. IEEE origin **NOT_LOCALIZED**; residual attribution **NOT_ESTABLISHED**, agreement **REVIEW_REQUIRED**. Same grids do not certify equal operators. |
| Existing density/Hartree arrays | [Bound A/B final n_out and G40 SCF rho; complete Fourier coefficients](../results/mg-soc-density-hartree/README.md). All three native Hartree terms reconstructed within 1.1e-13 Ha; 22,118 shared nonzero G. | A−QE density projected L2 2.9662e-7 electron/bohr^(3/2); Hartree −0.16237 meV/cell, other energy terms' undecomposed difference +0.78681 meV/cell. Full cross-code real-space density **NOT_ASSESSED**; physical attribution **NOT_ESTABLISHED**, agreement **REVIEW_REQUIRED**. No new solve. |
| Existing-density energy/reference audit | [Signed full ledger; A/B local/XC/Pc/Ewald restored; complete Q_rep evaluated with frozen full PBEsol](../results/mg-soc-energy-reference/README.md). Five fixed-density calls; no new solve. | A XC density response +0.01735 meV, Q_rep evaluator residual +0.05468 meV; O combination difference +0.71428 meV. Native QE local potential NOT_EXTRACTED, separate T/NL NOT_AVAILABLE. G=0 candidate +0.45363 meV is tagged prediction, not causal proof. Agreement REVIEW_REQUIRED; attribution open. |
| QE reconstructed local ionic potential | [Same-build P2/P0, complete fields, all-node registration and signed local ledger](../results/mg-soc-qe-local-potential/README.md). Both pp calls PASS; 64000 nodes/17 modes register. | P2 mean supports tagged G=0; A local response/shape/G0 = +0.213945/+0.115610/+0.453635 meV, remaining O = −0.068909 meV. Historical memory/tab_vloc NOT_EXTRACTED; independent T/NL NOT_AVAILABLE. Attribution PARTIALLY_QUANTIFIED, review REVIEW_REQUIRED, IEEE NOT_LOCALIZED. |
| Noncollinear magnetic XC | **NOT_IMPLEMENTED** | Charge-only closure does not validate magnetic XC. |
| Physical cutoff/k/temperature convergence | **NOT_ESTABLISHED** | Limited scalar sensitivity and prescribed Mg cases do not establish converged material predictions. |
| Upstream native support / architecture acceptance | **NOT_IMPLEMENTED_BY_THIS_WORKBENCH** / **NOT_ESTABLISHED** | Neither core checkout changed; no maintainer endorsement implied. [Open architectural questions](soc-upstream-risks.md). |
| USPP/PAW, forces, stress, optimization, DFPT, GPU/AD, MLP | **OUT_OF_SCOPE / NOT_RUN** | No claims are supported by these cases. |

Public offline checks reparse small QE XML outputs and recompute stored spectra,
energy sums, finite-difference tables and iteration summaries. Density/Pauli
norms and Hamiltonian actions requiring unshared orbitals or density arrays are
**runner-reported**, with source hashes and physical reproduction instructions;
hashes alone are not independent numerical verification. UPF reintegration from
original bytes requires acquiring the recorded input. Licensed inputs are not
redistributed by this repository.
Phase 7C now makes complete native n_out/rho coefficient and Hartree arithmetic
publicly replayable for the first time. Source deserialization/FFT/direct sums
and n_in closure remain runner-performed checks; no public coefficient pack
substitutes for independent raw source extraction. Earlier NOT_RUN statements
describe their own historical phase and are not rewritten.

Historical upstream `:minimal` results remain historical; Phase 7A does not rerun
DFTK A/B or numerical Julia/upstream suites. A fresh frozen-environment identity
check and affected Python tests accompany the new QE run. The old
[preparation package](../benchmarks/mg-soc-fermi/checklist.md) remains
PREPARED_NOT_EXECUTED; it is not relabeled as an earlier executed benchmark.
See each case for original run identities, exact execution-file hashes, thresholds, adverse results and NOT_RUN
items. AI-assisted checks do not substitute for external physical validation.

Phase 7B reruns only affected Python checks and public arithmetic. New DFTK/Julia
numerical suites and additional physical convergence scans are **NOT_RUN**.
Phase 7C reruns the new small array/math tests and affected public checks only.
New SCF/eigensolves/QE and full upstream numerical suites are NOT_RUN.
The public-only entry is `python3.12 scripts/check_density_hartree.py --all
--legacy-python python3.9`; it preserves all old case checks.

Phase 7D preserves the earlier real-space extraction scope: Q_rep is the complete
saved finite series on original40³ nodes, not independently extracted native QE
real-space data. New full-field integrals are runner-reported; public replay
recomputes saved energy-table algebra. The current entry is
`python3.12 scripts/check_energy_reference.py --all --legacy-python python3.9`.
No new SCF, eigensolve, QE/pp.x or IEEE localization was executed.

Phase 7E's current public entry is `python_numpy scripts/check_qe_local_potential.py
--all --legacy-python python3.9`, with an existing NumPy backend. Full P2/DFTK
fields, original P0 tokens, complete coefficient integrals and print propagation
are replayable. Original Julia field extraction remains separately bound to
archived source arrays. Two pp initializations were executed, including their
normal potential/Hartree/XC work; independent XC and new solvers were NOT_RUN.
Earlier phase-specific NOT_EXTRACTED/NOT_RUN statements remain historical.
