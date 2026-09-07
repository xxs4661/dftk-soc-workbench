# Capability and validation status

This is the single complete current capability table. It describes evidence at
accepted development snapshot `8658992afa936f6cdb1a8055699ae9aa47b32297` and the
curated public data derived from it. Repository curation adds no scientific run.
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
| QE SOC comparison | [Input, parameters and checklist](../benchmarks/mg-soc-fermi/checklist.md): **PREPARED_NOT_EXECUTED** | E/F cross-code comparison **NOT_RUN**. This is the next scientific gate, subject to separate authorization and review. |
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

Historical upstream `:minimal` results remain historical; this curation did not
rerun numerical Julia tests, SCF, QE, or the full upstream suite. Tooling CLI
checks (including information-only Mg parsing) were checked separately. See each case for original run
identities, exact execution-file hashes, thresholds, adverse results and NOT_RUN
items. AI-assisted checks do not substitute for external physical validation.
