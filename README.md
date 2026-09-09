# DFTK SOC workbench

A research workbench for norm-conserving UPF pseudopotentials, two-component
spinors and spin–orbit coupling on top of a frozen DFTK environment.

Phase 8B [Si SOC sensitivity](results/si-soc-sensitivity/README.md) is
complete: 12 prescribed slots exited 0. E40/T05 changes stay within the
0.1 meV observation window; K4 changes the splitting by about **+0.331506 meV**
in both programs, exceeding that window while their responses agree.
Physical interpretation remains **REVIEW_REQUIRED** and convergence
**NOT_ESTABLISHED**; occupation diagnostics and QE warnings are reported separately.

Phase 8A [Si SOC splitting](results/si-soc-splitting/README.md) completed its
five prescribed slots once each: D/Q Γ splits **47.4576152 / 47.4576124 meV**,
difference **2.7336e-9 eV**; same-density spin-trace six-state width **1.6276e-12 eV**.
The fixed-window structure, splitting and null gates pass. Physical manifold/scientific interpretation
remains **REVIEW_REQUIRED**: extra occupation-saturation diagnostic unmet, QE SCF
eigensolver warnings and IEEE flags retained, physical convergence not established.
The 2427 Phase 8A assertions are historical. [Version 2 status semantics and
public replay](results/si-soc-splitting/status-correction/README.md) separate
fixed-window PASS from occupation and complete manifold prerequisites
**REVIEW_REQUIRED**. The old checker requires the fixed historical snapshot.
Phase 8A.1 added no physical calculation; the new Phase 8B slots are reported separately.

Phase 7G [Linux public replay](results/mg-soc-public-replay/linux/README.md)
completed: **I PASS / exit 0**, all 380 numerical gates; **R FAIL / exit 1**
for the two predeclared derived-density hashes. CI remains **failure**.
All 47 Linux synthetic tests passed. Input/WFC identities match; no unclassified
numerical difference remains. Native QE NL and physical convergence retain
their limitations. The earlier authorization-blocked records remain unchanged.

The scalar Si baseline and restricted spinor/SOC prototypes use frozen dependencies.
Phase 6C A/B and the [first QE SOC comparison](results/mg-soc-qe-comparison/README.md)
remain **HISTORICAL_REUSED**. Historical Phase 7A QE execution: **PASS**.
The [solver/FFT diagnostics](results/mg-soc-qe-diagnostics/README.md),
[saved density/Hartree audit](results/mg-soc-density-hartree/README.md) and
[energy/reference ledger](results/mg-soc-energy-reference/README.md) preserve
all earlier results and limitations.

The preceding [QE local-potential audit](results/mg-soc-qe-local-potential/README.md)
executed two same-build pp.x slots on independent G40 copies. All 64000 P0
nodes and 17 complex modes register. The pp-reconstructed mean supports the
prior G=0 prediction; it is not extraction of historical SCF memory.
A−G40 local bookkeeping separates into density response +0.213944969,
nonzero G shape +0.115609946 and G=0 +0.453634725 meV/cell, leaving a derived
O residual −0.068908841 meV/cell. Native E/F is unchanged. This residual is
not independently measured QE kinetic/nonlocal energy. Numerical review is
**REVIEW_REQUIRED**, physical convergence **NOT_ESTABLISHED**, and IEEE origin
**NOT_LOCALIZED**. No new SCF/eigensolve or independent XC run was performed;
normal pp initialization did reconstruct potentials. Main is unchanged.

The earlier [original-wavefunction audit](results/mg-soc-wavefunction-energy/README.md)
reads the bound original G40 and A/B endpoints without new solves. All finite
orbital-density, direct/gradient kinetic and frozen FR gates pass. The A−Q
common-evaluator T+NL response is −0.068920107 meV/cell; the remaining
cross-source combination J is +0.000011267 meV/cell, with P2/token halfwidth
0.000520741 meV/cell. Native QE NL is **NOT_MEASURED** and the original
input-Hamiltonian residual **NOT_AVAILABLE**. Complete canonical Q coefficients
and one P/D set permit public replay; A/B source extraction remains runner-reported.

- [Capabilities, evidence levels and limitations](docs/status.md)
- [Scientific results and offline review](results/README.md)
- [Physical inputs and reproduction](benchmarks/README.md)
- [Frozen Julia environment](environment/workbench/README.md)
- [Commands](scripts/README.md) · [Contributing](CONTRIBUTING.md)

For an offline review using public files only, run from the repository root:

```sh
python_numpy scripts/check_orbital_energy.py --all --legacy-python python3.9
```

`python_numpy` is an existing Python 3.12 interpreter with NumPy (tested 2.3.5);
no dependency installation is performed. Full fields, registration and precision
propagation are replayed. Exact historical scalar RMS values use Python 3.9 (the recorded
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

[Si source and fixed matrix](benchmarks/si-soc-splitting-v1/README.md) bind the new
two-atom FR-NC-PBE/NLCC case. The spin-trace control is fixed-density only,
not an independent scalar pseudopotential or SCF.
