# Local macOS benchmark environment template

Run these commands from the workbench repository root on the Mac that will execute a benchmark. Phase 2 did run in a local macOS workspace, but this file remains an unfilled template for future runs; the actual Phase 2 observations are in [the fixed historical report](https://github.com/xxs4661/dftk-soc-workbench/blob/8658992afa936f6cdb1a8055699ae9aa47b32297/results/environment-summary.md).

## Collection commands

```bash
date -u '+%Y-%m-%dT%H:%M:%SZ'
sw_vers
uname -m
uname -srv
sysctl -n machdep.cpu.brand_string || sysctl -n hw.model
sysctl -n hw.memsize
julia --version
julia --startup-file=no -e 'using Base.Threads; println(nthreads())'
julia --startup-file=no -e 'using LinearAlgebra; versioninfo(); println(BLAS.get_config())'
git --version
pw.x -version
scripts/fetch_sources.sh
scripts/collect_environment.sh
scripts/bootstrap_dftk.sh
scripts/run_dftk_minimal.sh
```

If an optional command is unavailable or exits nonzero, record that exit code instead of substituting a guessed value. `scripts/run_dftk_minimal.sh` writes the DFTK minimal-test result and a timestamped sanitized log.

## Benchmark record

Copy this checklist into a benchmark-specific environment record and replace each explicitly documented future value before interpreting numerical results.

| Field | Value |
| --- | --- |
| UTC capture time | pending verification |
| macOS version and build | pending verification |
| CPU / architecture | pending verification |
| Physical memory | pending verification |
| Julia version | pending verification |
| DFTK repository and commit | pending verification |
| Julia project dependency state | pending verification |
| Quantum ESPRESSO version or commit | pending verification |
| QE build configuration and compiler | pending verification |
| BLAS / LAPACK implementation | pending verification |
| MPI implementation and process count | pending verification |
| Thread counts | pending verification |
| Benchmark input revision | pending verification |
| Pseudopotential identifiers | pending verification |
| Pseudopotential SHA-256 checksums | pending verification |

Also record any environment variables that materially affect numerical behavior, while redacting secrets and avoiding user-specific absolute paths. State whether each run was local, sandboxed, virtualized, or scheduled through a cluster.
