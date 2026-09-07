# DFTK SOC workbench

A research workbench for norm-conserving UPF pseudopotentials, two-component
spinors and spin–orbit coupling on top of a frozen DFTK environment.

The repository contains a scalar Si baseline and restricted spinor/SOC prototypes.
The [first QE SOC comparison](results/mg-soc-qe-comparison/README.md) and Phase 6C
A/B are now **HISTORICAL_REUSED** references. Historical Phase 7A QE execution: **PASS**.
The new [solver/FFT diagnostics](results/mg-soc-qe-diagnostics/README.md) completed
one initialization check and five prescribed QE solves. Same-density D/C spectra
are stable under the declared filter; the 40³ grid control changes the energy and
relative spectra, while the remaining energy difference and IEEE warning origin
are unresolved. Numerical agreement is **REVIEW_REQUIRED** and physical convergence
is **NOT_ESTABLISHED**. This development branch has not been published to main.

- [Capabilities, evidence levels and limitations](docs/status.md)
- [Scientific results and offline review](results/README.md)
- [Physical inputs and reproduction](benchmarks/README.md)
- [Frozen Julia environment](environment/workbench/README.md)
- [Commands](scripts/README.md) · [Contributing](CONTRIBUTING.md)

For an offline review using public files only, run from the repository root:

```sh
python3.12 scripts/check_qe_soc_diagnostics.py --all --legacy-python python3.9
```

Exact replay of historical scalar RMS values uses Python 3.9 (the recorded
summation behavior); Python 3.12 or later is required by the QE-input preparer.
No calculation is started by the publication check. Physical reproduction
requires Julia 1.12.7, the locked checkouts, and separately acquired UPF files;
see the environment and case instructions before running a scientific driver.

Material AI assistance included GPT-5.6 Pro planning/review and Codex
implementation and testing. This is not independent expert certification;
see [the disclosure](docs/ai-assistance.md). The
[historical curation](docs/evidence-migration.md) performed no SCF/QE;
Phase 7A and Phase 7B have separate execution identities and preserve older results.

The combined publication check uses Python 3.9 for exact historical scalar
arithmetic and `python3.12` on PATH for standard-library TOML in the prototype
checks (`--modern-python PATH` selects an existing Python 3.11+ interpreter).
It installs no packages or environments.

The combined verifier now binds the historical UPF exporter to its reviewed Git
object at `ac22a64421c4a5444a399477b9a3215dbd913487`. Use a normal clone retaining
that history; no private execution archive is needed. The new SOC-only replay is
`python3.12 scripts/check_qe_soc_evidence.py`.

The new diagnostic checker wraps the unchanged historical publication checker;
it does not refresh the Phase 7A verifier hashes. New-case-only replay is
`python3.12 scripts/check_qe_soc_diagnostics.py`.
