# Commands and their scope

Start with [getting started](../docs/getting-started.md). This directory contains
both public review tools and the drivers that produced historical experiments.
They do not share a single generic material-calculation interface.

## Public result review

From a normal clone with local Git history and an existing Python 3.12:

```sh
python3.12 -B scripts/review.py core-regression
```

[`review.py`](review.py) creates its own temporary clean copy outside the current
repository, checks out the fixed completed-core snapshot and runs the original
strict public checker. It starts no Julia, QE, SCF or occupation solver and reads
no private `.work` data. Its summary preserves scientific review flags and the
original exit. `--log-dir` accepts a new directory outside the repository for
complete output and preparation metadata. See [reproduction and exit semantics](../docs/reproducibility.md).

Other checkers cover [Si](../results/README.md#silicon-soc-spectra-and-sensitivity)
and [Mg](../results/README.md#magnesium-cross-code-comparison-and-energy-reference).
Use the explicit fixed snapshots and original commands in the
[history index](../docs/history.md). Do not run an old whole-tree checker on
updated documentation and then edit its hashes to make it pass.

## Core example

```sh
julia --startup-file=no --project=@stdlib examples/soc_kernels.jl
```

This existing [example](../examples/soc_kernels.jl) is at the repository root's
`examples/` path. It exercises the actual `SOCKernels` matrix interface on small
synthetic inputs, including a dense reference and two expectation contractions.
It needs no pseudopotential or DFTK installation. It is not an SCF example or a
registered Julia package. See [runtime and ownership](../docs/soc-core-runtime.md).

## Environment and input preparation

For development that actually uses the frozen DFTK adapter, follow the
[environment guide](../environment/workbench/README.md). Existing entry points:

| Entry | What it does / prerequisite |
| --- | --- |
| `fetch_sources.sh` | Obtain the exact local source checkouts before instantiation; optional `--source-cache DIR` reuses source repositories. |
| `bootstrap_dftk.sh` | Instantiate the saved workbench environment, then check loaded identity in a fresh Julia process. May need package downloads. |
| `python3 scripts/run_recorded.py identity` | Check the actual Julia, Manifest and loaded checkout identities; no SCF. |
| `run_upf_inspection.sh [UPF_PATH]` | Strict FR-NC metadata acceptance and the locked DFTK's expected SOC rejection; default Mg bytes must match the lock. |
| `python3 scripts/run_recorded.py tests` | Workbench Julia tests using the frozen environment; not upstream DFTK tests. |
| `run_dftk_minimal.sh` | The separate historical upstream minimal-test selection; not part of public result replay. |

The [UPF acceptance record](../results/upf-acceptance/README.md) explains parser,
metadata, construction and exit statuses. Information-only inspection does not
satisfy strict acceptance. [`run_recorded.py`](run_recorded.py) preserves
per-run output and checks the worker protocol; a record cannot borrow an earlier
run's PASS.

## Historical experiment drivers

These are implementation and reproduction references, not commands to launch
unrestricted new experiments. Their original provenance, source, exact-commit,
parent-density and single-use controls remain enforced. Published slots cannot
be reused by changing a label or pretending to have an old authorization.

| Scientific operation | Source and fixed input documentation |
| --- | --- |
| Scalar Si paired SCF / spectra | `run_scalar_baseline.py`; [scalar case](../benchmarks/si-sr-lda/README.md) |
| Charge-only Mg SOC SCF | `run_soc_scf.jl`; [SOC prototype](../prototypes/soc_scf/README.md) |
| Si SOC and own-density spectra | `run_si_dftk.py`, `run_si_soc.jl`, `run_si_qe.py`; [Si inputs](../benchmarks/si-soc-splitting-v1/README.md) |
| Mg QE comparison / fixed diagnostics | `run_qe_soc.py`, `run_qe_soc_diagnostics.py`; [case index](../benchmarks/README.md) |
| Original saved-density / field / orbital extraction | `run_density_hartree_audit.py`, `run_energy_reference_audit.py`, `run_orbital_energy_audit.py`; require authenticated original private save files. |
| Local-potential reconstruction | `run_qe_local_postprocess.py`; historical bounded pp.x experiment, not read-only arithmetic replay. |

A new material calculation still requires explicit input validation, a suitable
unconsumed driver contract and further integration work. Public numerical packs
cannot replace missing UPF, checkpoint or wavefunction sources. The current
curation does not add such a driver.

## Maintenance

The `curate_*_evidence.py` and case-specific export tools select recorded fields;
their export modes are distinct from read-only checks. The original
`check_publication.py` binds an earlier scientific tree and must retain its
historical successes and compatibility failures. Contributor checks and evidence
selection are described in [CONTRIBUTING](../CONTRIBUTING.md) and the
[evidence policy](../docs/evidence-policy.md). Agent execution boundaries live in
[AGENTS.md](../AGENTS.md), not in the researcher quick start.
