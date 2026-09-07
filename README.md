# DFTK SOC workbench

A research workbench for norm-conserving UPF pseudopotentials, two-component
spinors and spin–orbit coupling on top of a frozen DFTK environment.

The repository contains a scalar Si–Quantum ESPRESSO baseline and limited
sensitivity checks, a no-SOC spinor SCF prototype, and a charge-only Mg SOC SCF
prototype. The first **QE SOC comparison is NOT_RUN**: its input is prepared only.
These prescribed CPU cases do not establish physical convergence, noncollinear
magnetic XC, or upstream native SOC support.

- [Capabilities, evidence levels and limitations](docs/status.md)
- [Scientific results and offline review](results/README.md)
- [Physical inputs and reproduction](benchmarks/README.md)
- [Frozen Julia environment](environment/workbench/README.md)
- [Commands](scripts/README.md) · [Contributing](CONTRIBUTING.md)

For an offline review using public files only, run from the repository root:

```sh
python3.9 scripts/check_publication.py
```

Exact replay of historical scalar RMS values uses Python 3.9 (the recorded
summation behavior); Python 3.12 or later is required by the QE-input preparer.
No calculation is started by the publication check. Physical reproduction
requires Julia 1.12.7, the locked checkouts, and separately acquired UPF files;
see the environment and case instructions before running a scientific driver.

Material AI assistance included GPT-5.6 Pro planning/review and Codex
implementation and testing. This is not independent expert certification;
see [the disclosure](docs/ai-assistance.md). Current public evidence was organized
from the accepted development snapshot without new SCF/QE calculations; see the
[short migration note](docs/evidence-migration.md).

The combined publication check uses Python 3.9 for exact historical scalar
arithmetic and `python3.12` on PATH for standard-library TOML in the prototype
checks (`--modern-python PATH` selects an existing Python 3.11+ interpreter).
It installs no packages or environments.
