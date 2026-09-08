# Scientific evidence

- [Phase 8A: Si SOC splitting](si-soc-splitting/README.md) — five slots PASS/0; D/Q Δ=47.4576152/47.4576124 meV, same-density null restores near-sixfold Γ structure. Fixed-window structure, splitting and null gates pass; occupation diagnostic, QE warnings and physical interpretation remain REVIEW_REQUIRED. [Current semantics/replay](si-soc-splitting/status-correction/README.md): complete manifold prerequisites REVIEW_REQUIRED; original checker runs at the fixed historical commit.

- [Phase 7G: Linux public replay](mg-soc-public-replay/linux/README.md) — **I PASS/0, R FAIL/1**, CI failure; two predeclared density hashes, 380 I gates and 47 Linux synthetic tests PASS. [Initial authorization block](mg-soc-public-replay/README.md) preserved.
- [Phase 7F: original wavefunctions, kinetic and frozen nonlocal audit](mg-soc-wavefunction-energy/README.md) — full Q coefficient replay, A/B scalar/projection checks; [review](phase7f-review.md).

Phase 7C adds the [saved density/Hartree audit](mg-soc-density-hartree/README.md)
and complete native Fourier coefficients for offline replay, without new solves.
Phase 7B supplied the bounded QE solver/FFT/IEEE diagnostics. The Phase 7A SCF,
its bands result and Phase 6C A/B remain historical references; none was rerun. Current [capability status](../docs/status.md) separates execution,
internal checks, physical convergence and external validation.

| Scientific question | Public case |
| --- | --- |
| Does the input satisfy FR-NC metadata acceptance while native DFTK rejects SOC? | [UPF acceptance and recorder](upf-acceptance/README.md) |
| What agrees for one matched scalar Si input? | [Si scalar baseline](scalar-si-baseline/README.md) |
| What accounts for the common energy reference; how sensitive are cutoff and k integration? | [Si finite sensitivity](scalar-si-sensitivity/README.md) |
| Does the no-SOC spinor representation and SCF recover the scalar problem? | [No-SOC spinor](spinor-no-soc/README.md) |
| Are angular/radial projectors and independent kernels consistent? | [Relativistic projectors](relativistic-projectors/README.md) |
| Are the full Hamiltonian and orbital energy interfaces consistent at fixed density? | [FR Hamiltonian and energy](fr-hamiltonian-energy/README.md) |
| Do independent initial states close the prescribed charge-only SOC problem? | [Mg SOC SCF A/B](mg-soc-scf/README.md) |
| What agrees in the first independent QE SOC comparison? | [Mg QE SOC: E/F/entropy, all 24 states and limits](mg-soc-qe-comparison/README.md) |
| How sensitive is the fixed-density spectrum to solver choice and the SCF to 36³/40³ FFT? | [Mg QE diagnostics: original spectra, E/F, IEEE scope and unresolved residuals](mg-soc-qe-diagnostics/README.md) |
| Does the remaining difference appear in saved density/Hartree, and do native energies reconstruct? | [Mg density/Hartree: bound A/B/G40, complete coefficients, support and signed decomposition](mg-soc-density-hartree/README.md) |

Current [bound QE local-potential audit](mg-soc-qe-local-potential/README.md):
P2/P0 completed once each; complete native potential/token evidence supports
all-node and full Fourier replay, exact signed local decomposition and print
bounds. Remaining O residual and IEEE cause remain unresolved; no new SCF.

Each case has one evidence/provenance entry and its required source data. The
[shared environment](shared/environment.json) records the frozen Julia identity;
individual run receipts retain the fact and time of their own identity check.
Case-specific QE identity and actual execution source hashes remain attached to
the corresponding case. Input snapshots use immutable source references.

Run `python3.12 scripts/check_density_hartree.py --all --legacy-python python3.9` from the repository root to check
public paths/hashes and recompute the supported tables without `.work`, UPF files,
Julia or QE. The individual curation scripts expose offline check commands too.
Exact historical scalar RMS replay uses Python 3.9; newer Python summation can
change final bits, which is reported rather than hidden by relaxed assertions.

Public data is sufficient for these arithmetic checks, including Phase 7C's
complete native n_out/rho coefficient arithmetic. It does not reconstruct
unpublished wavefunctions or n_in fields, nor independently authenticate raw
checkpoint extraction. Small near-native logs retain actual
scientific warnings; full working arrays and process transcripts belong in an
independent local archive. [Publication policy](../docs/evidence-policy.md) and
[historical path mapping](../docs/evidence-migration.md) describe that boundary.

The combined publication check uses Python 3.9 for exact historical scalar
arithmetic and `python3.12` on PATH for standard-library TOML in the prototype
checks (`--modern-python PATH` selects an existing Python 3.11+ interpreter).
It installs no packages or environments.

New SOC offline replay: `python3.12 scripts/check_qe_soc_evidence.py`. The combined
checker also requires the reviewed historical UPF exporter Git object retained
in a normal clone. Its old evidence hash is not replaced by the evolving verifier.

## Historical energy/reference evidence

[Existing Mg SOC endpoint energy audit](mg-soc-energy-reference/README.md):
signed historical E/H/XC/Ewald/O ledger, fixed A/B/Q_rep common-term evaluation,
self recovery, XC density/evaluator split, and local finite G=0 diagnostic.
Only the source-convention candidate is inferred; QE separate T/NL/local are
not measured and residual attribution remains open.
