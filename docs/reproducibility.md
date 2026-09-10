# Reproduction scopes

A public result check and an electronic-structure calculation answer different
questions. This project publishes the data needed for specified numerical
comparisons, while some source extraction and array-dependent measurements remain
runner-reported. Start with [getting started](getting-started.md); use the
[history index](history.md) for the exact snapshots and original commands.

## Public core-regression entry

```sh
python3.12 -B scripts/review.py core-regression
```

The default case, if omitted, is also `core-regression`. The wrapper uses only
Git and an existing Python **3.12.x** interpreter; historical and curation checks
use **3.12.14**. It does not install packages or fetch history. A normal local
clone with the required history must contain this fixed publication:

`e98552ccfb96fb27e07c9816559856d133b58310`

That snapshot contains the completed Si core regression and its original
checker. The wrapper creates a unique independent local clone in a canonical
temporary directory outside the current repository, checks out the snapshot
detached, and invokes:

```text
python3.12 -B benchmarks/soc-core-memory-v1/resume/replay.py --root <historical-root> --require-endpoints
```

It removes only its own temporary copy. It does not change the caller's branch,
index, source files or other worktrees. Source `.work` files are not copied or
read. A shallow clone or missing snapshot is an explicit prerequisite error:
obtain complete repository history yourself and retry; the tool never substitutes
the current HEAD or a newer dependency.

For complete checker streams and local Git preparation metadata, pass
`--log-dir` with a **new directory outside the repository**, whose parent already
exists. Existing log paths are refused. Terminal output reports the child exit,
recorded delivery status, scope and scientific qualifications; failed checker
output is preserved rather than filtered into a success summary.

| Exit | Meaning |
| --- | --- |
| 0 | The frozen strict checker successfully replayed both recorded endpoints and their source, resource and regression contracts. This does not establish physical convergence. `--help` also returns 0 without checking results. |
| Original nonzero child exit | Propagated unchanged. The historical checker uses 1 for incomplete endpoints and 2 for malformed or mismatched evidence; native failure reasons remain visible. |
| 2 before a child runs, or after a wrapper I/O failure | Unsupported case/Python, missing history, clone/preparation failure or inability to complete requested output. No historical checker success is substituted. A nonzero child exit remains primary if output handling also fails. |

The old checker's **default** mode can return 0 for a faithfully recorded partial
delivery. This researcher entry deliberately invokes its **strict** mode. Neither
mode erases performance, occupation or physical-interpretation review flags.
The original partial-core snapshot still records its failed first execution;
the completed snapshot adds later evidence without rewriting that failure.

## What is independently available

| Evidence | Public replay can establish | Additional private or native prerequisite |
| --- | --- | --- |
| Completed core regression | Git/source binding, energy sums, all 24 Γ levels and split comparison, plus arithmetic of the recorded density-norm quotient. | Repeating the actual density-vector difference, orbital checks and RSS measurements needs the original checkpoint/runtime data. |
| Si SOC and sensitivity | Published levels, FD diagnostics, fixed-window structures, code/parameter responses and the native-output QE k-grid trend. | A new SCF or independent source extraction requires the input UPF, frozen software and a suitable experiment driver. |
| Mg density/Hartree and orbital audit | Public Fourier coefficients, complete Q spinor coefficients and published P/D actions permit the specified density, kinetic, Hartree and energy arithmetic. | A/B full orbital reconstruction is not public: their replay is limited to per-state tables/projection amplitudes. Original source extraction remains separately bound. |
| Mg local/XC/reference tables | Published fields and ledgers support the stated local integrals, precision propagation and saved scalar algebra. | Independent repetition of historical XC/field evaluation needs its frozen native environment and authenticated sources; public scalar replay does not execute XC. |

The [Mg Linux record](../results/mg-soc-public-replay/linux/README.md) retains
independent path I exit 0 and frozen path R exit 1, caused by two declared
derived-density byte hashes. An independent path passing does not relabel R.
No Linux from-scratch SOC SCF follows from that public-data test.

## Existing core example and native experiments

The [`examples/soc_kernels.jl`](../examples/soc_kernels.jl) example runs current
`SOCKernels` code on synthetic matrices using `LinearAlgebra` only. It demonstrates
matrix action and expectation contracts; it does not authenticate an UPF, create
a physical Hamiltonian or solve a material. [Runtime documentation](soc-core-runtime.md)
explains the actual interface and ownership.

Native DFTK experiments need Julia 1.12.7, the exact source checkouts **before**
instantiating the saved Manifest, and separately acquired input bytes. Follow the
[frozen environment guide](../environment/workbench/README.md). QE experiments
also bind an actual QE build and the case's input/unit conventions. Existing
historical launchers enforce prescribed sources, slots and parent checkpoints;
they are not an arbitrary-material API. Do not imitate an old authorization to
launch a new study. Missing original private data cannot be replaced by public
summary hashes or an unreported new calculation.

## Current documentation versus frozen evidence

Old checkers may bind README bytes or the entire tree. Run them at the named
historical publication, not against edited current documentation. The earlier
combined publication checker still has recorded frozen-source compatibility
failures at later snapshots. They remain failures; no old hash or acceptance
condition is changed by the new wrapper.

Curation checks the current document links, exact path case and authorized diff
separately. Its candidates and local check receipts are described in the
[curation handoff](../results/researcher-curation.md). These are documentation and
entry checks, not new scientific results.
