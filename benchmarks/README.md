# Cases and inputs

This catalogue links the fixed inputs behind the published comparisons. It is
not a general material-submission interface. Case README files preserve the
original experiment's settings, commands and execution restrictions; editing this
navigation does not change those restrictions.

To check published results now, use the [public reproduction guide](../docs/reproducibility.md).
To call the existing matrix core, use the [synthetic example](../examples/soc_kernels.jl)
and [runtime guide](../docs/soc-core-runtime.md). Neither performs a new material SCF.

## Silicon spectroscopy and sensitivity

| Fixed case | Inputs and scope | Published result |
| --- | --- | --- |
| Si scalar baseline and finite checks | [SR-LDA B0](si-sr-lda/README.md), [C1/C2/C3](si-sr-lda/phase4c/README.md): matched geometry/source and a limited cutoff/k matrix. | [Baseline](../results/scalar-si-baseline/README.md), [reference and sensitivity](../results/scalar-si-sensitivity/README.md) |
| Si SOC B0 | [FR-NC-PBE case](si-soc-splitting-v1/README.md): two-atom diamond primitive cell, NLCC, full SOC, Γ/p/−p probes and same-density spin-trace control. | [Spectra](../results/si-soc-splitting/README.md), [corrected interpretation](../results/si-soc-splitting/status-correction/README.md) |
| Si SOC E40/T05/K4 | [Three paired variants](si-soc-sensitivity-v1/README.md): cutoff, temperature and k-grid changes relative to B0. | [Finite responses](../results/si-soc-sensitivity/README.md) |
| Si QE K6/K8 | [QE-only reference cases](si-soc-k-reference-v1/README.md): fixed other settings, 216/512 SCF k points and own-density Γ probes. | [Trend and limits](../results/si-soc-k-reference/README.md); no DFTK K6/K8 calculation |

The scalar Si and SOC Si cases use different, separately authenticated sources.
The spin-trace control is not a scalar-pseudopotential SCF. Physical convergence
is not established by this collection.

## Magnesium comparison and reference audits

| Fixed case or audit | Input record | Published result |
| --- | --- | --- |
| Charge-only A/B SCF | [Mg parameters](mg-soc-fermi/parameters.json), [original QE checklist](mg-soc-fermi/checklist.md) | [Mg SCF](../results/mg-soc-scf/README.md); the QE input in this original checklist was prepared, not executed |
| Independent QE comparison | [Executed QE case](mg-soc-qe-v1/README.md) | [E/F/entropy and spectra](../results/mg-soc-qe-comparison/README.md) |
| Solver/FFT diagnostics | [Prescribed controls](mg-soc-qe-diagnostics-v1/README.md) | [Saved-density, grid and warning checks](../results/mg-soc-qe-diagnostics/README.md) |
| Density and Hartree | [Bound-source Fourier plan](mg-soc-density-hartree-v1/README.md) | [Native support and energy decomposition](../results/mg-soc-density-hartree/README.md) |
| Energy reference | [Existing-density/common-term plan](mg-soc-energy-reference-v1/README.md) | [Signed ledger and G=0 audit](../results/mg-soc-energy-reference/README.md) |
| Local ionic potential | [P2/P0 postprocessing inputs](mg-soc-qe-local-potential-v1/README.md) | [Reconstructed fields and local integrals](../results/mg-soc-qe-local-potential/README.md) |
| Original wavefunctions | [Static orbital audit](mg-soc-wavefunction-energy-v1/README.md) | [Kinetic and frozen-operator comparison](../results/mg-soc-wavefunction-energy/README.md) |
| Cross-environment replay | [Fixed Linux replay plan](mg-soc-public-replay-v1/README.md) | [Independent pass and frozen-checker failure](../results/mg-soc-public-replay/linux/README.md) |

Mg uses the recorded FR-PBEsol source family. Later audits reuse bound original
states; the listed plans do not authorize fresh calculations or replacements for
missing arrays.

## Mathematical and implementation checks

The [representation/operator evidence index](../results/README.md#representation-operators-and-energy-consistency)
links no-SOC, spin-angular, nonlocal and full-Hamiltonian checks. Their existing
fixtures and synthetic tests are distinct from physical input cases.

[Core static measurements](soc-core-memory-v1/README.md) use authenticated
historical Si B0/K4 orbitals. The [endpoint continuation](soc-core-memory-v1/resume/README.md)
uses unchanged B0 settings; its [completed regression](../results/soc-core-memory/completion/README.md)
is the current result. Static timing and dense-grid resource limits remain.

## What reproduction requires

- **Public checks:** use the stated clean [historical snapshots](../docs/history.md)
  and existing Python prerequisites. Published tables, spectra and selected
  coefficient packs support their documented offline arithmetic.
- **Recorded physical experiments:** source checkouts and separately acquired,
  hash-verified UPFs require the [frozen environment](../environment/workbench/README.md).
  Old launchers retain their source, parent-state and one-time execution guards;
  they are not unrestricted repeatable commands for new users.
- **Private-state audits:** original A/B checkpoints, some density/field arrays
  and static benchmark orbitals are not public. Their acquisition and extraction
  cannot be independently repeated from scalar receipts alone. The Mg public Q
  coefficient pack has the broader scope described in its report.

A general driver for new materials remains future work. See [scripts](../scripts/README.md)
for the distinction between runnable checks, environment preparation and archived
experiment drivers.
