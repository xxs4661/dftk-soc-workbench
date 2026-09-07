# DFTK SOC workbench

A research workbench for norm-conserving UPF pseudopotentials, two-component
spinors and spin–orbit coupling on top of a frozen DFTK environment.

The repository contains a scalar Si baseline and restricted spinor/SOC prototypes.
The [first QE SOC comparison](results/mg-soc-qe-comparison/README.md) and Phase 6C
A/B are now **HISTORICAL_REUSED** references. Historical Phase 7A QE execution: **PASS**.
The historical [solver/FFT diagnostics](results/mg-soc-qe-diagnostics/README.md) completed
one initialization check and five prescribed QE solves. Same-density D/C spectra
are stable under the declared filter; the 40³ grid control changes the energy and
relative spectra, while the remaining energy difference and IEEE warning origin
are unresolved. Numerical agreement is **REVIEW_REQUIRED** and physical convergence
is **NOT_ESTABLISHED**. The new [saved density/Hartree audit](results/mg-soc-density-hartree/README.md)
reads existing A/B and G40 arrays without new solves. All native Hartree terms
are recovered within 1.1e-13 Ha; A−QE common-support density L2 is 2.97e-7
electron/bohr^(3/2), with Hartree difference −0.16237 meV/cell. This does not
explain the whole +0.62444 meV total-energy difference. Full cross-code real-space
density is NOT_ASSESSED; residual attribution remains NOT_ESTABLISHED.
The [energy/reference audit](results/mg-soc-energy-reference/README.md) now
completes the signed native energy ledger and evaluates fixed historical A/B and
QE finite-series densities with the frozen local/PBEsol implementation. A's
+0.62444 meV difference separates into Hartree −0.16237, XC +0.07203,
Ewald +0.00050 and a still-combined single-electron +0.71428 meV. Five fixed-density
XC evaluations restore same-source terms; a +0.45363 meV local G=0 candidate is
source-convention evidence, not runtime attribution or an energy correction.
Residual attribution stays open; no new SCF, eigen solve or QE run occurred.
This development branch has not been published to main.

- [Capabilities, evidence levels and limitations](docs/status.md)
- [Scientific results and offline review](results/README.md)
- [Physical inputs and reproduction](benchmarks/README.md)
- [Frozen Julia environment](environment/workbench/README.md)
- [Commands](scripts/README.md) · [Contributing](CONTRIBUTING.md)

For an offline review using public files only, run from the repository root:

```sh
python3.12 scripts/check_energy_reference.py --all --legacy-python python3.9
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
Phase 7C publishes complete native n_out/rho Fourier coefficients for offline
arithmetic; original source extraction and n_in closure checks remain separately
identified runner-performed measurements.

The combined publication check uses Python 3.9 for exact historical scalar
arithmetic and `python3.12` on PATH for standard-library TOML in the prototype
checks (`--modern-python PATH` selects an existing Python 3.11+ interpreter).
It installs no packages or environments.

The combined verifier now binds the historical UPF exporter to its reviewed Git
object at `ac22a64421c4a5444a399477b9a3215dbd913487`. Use a normal clone retaining
that history; no private execution archive is needed. The new SOC-only replay is
`python3.12 scripts/check_qe_soc_evidence.py`.

The historical diagnostic checker wraps the unchanged publication checker;
it does not refresh the Phase 7A verifier hashes. New-case-only replay is
`python3.12 scripts/check_qe_soc_diagnostics.py`.
The new array-only replay is `python3.12 scripts/check_density_hartree.py`.

The current energy-table replay is `python3.12 scripts/check_energy_reference.py`.
It replays saved scalar algebra; frozen Julia and authenticated private sources
are required to independently repeat XC/field evaluation.
