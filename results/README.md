# Scientific evidence

The new Phase 7A Mg case adds one QE SCF and a warning-triggered fixed-density
spectral refinement. Earlier calculations remain historical, including the reused
Phase 6C A/B references. Current [capability status](../docs/status.md) separates execution,
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

Each case has one evidence/provenance entry and its required source data. The
[shared environment](shared/environment.json) records the frozen Julia identity;
individual run receipts retain the fact and time of their own identity check.
Case-specific QE identity and actual execution source hashes remain attached to
the corresponding case. Input snapshots use immutable source references.

Run `python3.9 scripts/check_publication.py` from the repository root to check
public paths/hashes and recompute the supported tables without `.work`, UPF files,
Julia or QE. The individual curation scripts expose offline check commands too.
Exact historical scalar RMS replay uses Python 3.9; newer Python summation can
change final bits, which is reported rather than hidden by relaxed assertions.

Public data is sufficient for these arithmetic checks, not reconstruction of
unpublished wavefunctions or density fields. Small near-native logs retain actual
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
