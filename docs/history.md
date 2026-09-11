# Historical experiments and review snapshots

Current documentation describes the maintained workbench. The snapshots below
preserve earlier inputs, reports and checker contracts. A **review snapshot** is
a publication commit, not necessarily the commit that executed its calculations;
each evidence manifest retains the actual execution identity.

Some checkers bind navigation bytes or the entire tree. Run them in the indicated
clean snapshot with complete local Git history, not in a newly edited checkout.
[Reproduction instructions](reproducibility.md) explain prerequisites, scope and
exit codes. The current public entry selects the completed core snapshot without
changing the user's branch.

## Representation and initial validation

| Original stages | Topic | Fixed review snapshot and record |
| --- | --- | --- |
| 4A/4A.1, 4B/4C, 5A/5B, 6A/6B/6C | UPF acceptance; scalar Si reference; no-SOC spinors; FR projectors, Hamiltonian and Mg SCF | [ac22a64](https://github.com/xxs4661/dftk-soc-workbench/tree/ac22a64421c4a5444a399477b9a3215dbd913487), the first curated [scientific index](https://github.com/xxs4661/dftk-soc-workbench/blob/ac22a64421c4a5444a399477b9a3215dbd913487/results/README.md) |

The [SOC v1 RFC](../rfc/soc-v1.md) is a historical proposal, not an accepted
upstream design or current general API. The preserved
[relativistic conventions](../prototypes/relativistic/CONVENTIONS.md) describe the
FR prototype. Both have the same bytes in `ac22a64`; current methods and owned
runtime interfaces are described in [methods](methods.md) and
[core runtime](soc-core-runtime.md).

## Magnesium comparison and audits

| Original stages | Topic | Fixed review snapshot and original entry |
| --- | --- | --- |
| 7A–7F | QE comparison, solver/FFT controls, density/Hartree, energy reference, local potential and original orbitals | [747d7d3](https://github.com/xxs4661/dftk-soc-workbench/tree/747d7d3e21dadd8a5fef0183d2375e7f1f82c176); [orbital replay instructions](https://github.com/xxs4661/dftk-soc-workbench/blob/747d7d3e21dadd8a5fef0183d2375e7f1f82c176/results/mg-soc-wavefunction-energy/README.md) |
| 7G | Independent Linux public-data replay and frozen-checker failure | [9342a5e](https://github.com/xxs4661/dftk-soc-workbench/tree/9342a5ea21a76acd0d74d228d4a2081394f702d0); [separate R/I receipts](../results/mg-soc-public-replay/linux/replay.json) |

At `747d7d3`, the combined command is
`python_numpy scripts/check_orbital_energy.py --all --legacy-python python3.9`.
`python_numpy` means an existing Python/NumPy interpreter; the recorded runtime
was Python 3.12.14/NumPy 2.3.5. Older scalar arithmetic also needs Python 3.9.
The Linux experiment ran the frozen R checker at `747d7d3` and independent code
at `58c1feae286c32e8ba017fdc2869eba908c9f4dc`: **R FAIL/1, I PASS/0**.
Its [native commands and platform](../results/mg-soc-public-replay/linux/README.md)
are retained, without presenting public replay as a new Linux SOC SCF.

## Silicon spectra and sensitivity

| Original stages | Topic | Fixed review snapshot and original entry |
| --- | --- | --- |
| 8A | Original SOC spectra and spin-trace control | [61cb1c2](https://github.com/xxs4661/dftk-soc-workbench/tree/61cb1c226dcfa8dbeccc63e8f43e33b2790a07c6); `python3 -B scripts/check_si_soc.py` |
| 8A.1 | Occupation-aware status assessment | [bc68aaf](https://github.com/xxs4661/dftk-soc-workbench/tree/bc68aaf655d96dfd4335f6fa1a8e5ee76477c2a3); [two-snapshot instructions](https://github.com/xxs4661/dftk-soc-workbench/blob/bc68aaf655d96dfd4335f6fa1a8e5ee76477c2a3/results/si-soc-splitting/status-correction/README.md) |
| 8B | Paired E40/T05/K4 finite responses | [557571f](https://github.com/xxs4661/dftk-soc-workbench/tree/557571fa6beb29e1ee57a5a0701ab3bded41fc78); complete public arithmetic `PYCODE` block in the [case report](https://github.com/xxs4661/dftk-soc-workbench/blob/557571fa6beb29e1ee57a5a0701ab3bded41fc78/results/si-soc-sensitivity/README.md#public-only-arithmetic-replay) |
| 8C | QE-only K6/K8 finite trend | [c764311](https://github.com/xxs4661/dftk-soc-workbench/tree/c764311a5422b5c3cab5a7b78a02d420910c4e56); `python3.12 -B scripts/si_qe_reference_evidence.py replay` |

The status assessment runs its code in `bc68aaf` with `--source-root` pointing
to a separate clean `61cb1c2` tree. Default validation returns 0 on the recorded
data; `--require-manifold-pass` returns 1. That strict result does not change the
original spectra. K4's exceeded finite-step window also remains part of a
successful arithmetic replay.

## Core allocation and endpoint regression

| Original stages | Topic | Fixed review snapshot and original entry |
| --- | --- | --- |
| 9A initial | Static equivalence/allocation evidence and failed first endpoint attempt | [98781fd](https://github.com/xxs4661/dftk-soc-workbench/tree/98781fd0ce6c2f4138ed010e115a13e370410d58); [partial report](https://github.com/xxs4661/dftk-soc-workbench/blob/98781fd0ce6c2f4138ed010e115a13e370410d58/results/soc-core-memory/README.md) |
| 9A continuation | Completed Si SCF and own-density Γ regression, reusing the original static measurements | [e98552c](https://github.com/xxs4661/dftk-soc-workbench/tree/e98552ccfb96fb27e07c9816559856d133b58310); [completion](../results/soc-core-memory/completion/README.md) |

At the completed snapshot:

```sh
python3.12 -B benchmarks/soc-core-memory-v1/resume/replay.py --root . --require-endpoints
```

This checks public records and arithmetic. Static execution remains
`1b42a27063ca65757d2c4f34d46fe4f1cd9929ed`; continuation execution remains
`281c53525a70cf21c36973956d5303d3201a73eb`. The earlier failure is preserved,
and later success does not turn timing review, private-array measurements or
unrun dense-grid calculations into stronger evidence.
