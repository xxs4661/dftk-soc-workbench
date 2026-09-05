# QE-aligned SOC support for DFTK.jl

## Status

This repository contains active design, source-inspection, and validation work. Spin-orbit coupling (SOC) has not yet been implemented. The design notes are proposals for discussion, not an architecture accepted by DFTK maintainers, and no numerical agreement with Quantum ESPRESSO (QE) has been established.

## Goal

The scoped goal is to investigate an implementation of SOC in DFTK.jl using fully relativistic norm-conserving UPF pseudopotentials and to validate numerical results against Quantum ESPRESSO.

## Initial v1 scope

- Fully relativistic norm-conserving UPF pseudopotentials
- Two-component spinor wavefunctions
- LDA / LSDA
- SCF calculations
- Band-structure calculations
- CPU implementation
- Explicit k-points or disabled spatial-symmetry reduction initially
- Numerical comparison against Quantum ESPRESSO

## Explicit non-goals for v1

- Ultrasoft pseudopotentials
- PAW
- Forces
- Stresses
- Phonons
- DFPT
- DFT+U
- GPU optimisation
- Complete magnetic-space-group support
- Machine-learning potentials

## Validation strategy

The planned validation ladder is deliberately incremental:

1. Check Hermiticity of each proposed spinor Hamiltonian contribution and of the assembled Hamiltonian.
2. Recover spin degeneracy in nonmagnetic calculations without SOC, subject to the chosen occupations and numerical tolerances.
3. Check time-reversal relations between paired k-points when the physical setup preserves time-reversal symmetry.
4. Check Kramers degeneracy at appropriate time-reversal-invariant k-points when its physical preconditions hold.
5. Check global spin-rotation invariance where the Hamiltonian and exchange-correlation approximation make that invariance applicable.
6. Compare eigenvalues and SOC splittings against matched QE calculations.
7. Demonstrate plane-wave cutoff and k-point convergence independently for both codes before cross-code comparisons.
8. Record exact pseudopotential family identifiers, source locations, licensing information, and SHA-256 checksums for every comparison.

No item in this plan is evidence that the corresponding check currently passes.

## Planned phases

1. Establish a scalar-relativistic QE–DFTK baseline.
2. Inspect fully relativistic UPF metadata and its current parser representation.
3. Discuss multicomponent and spinor data structures.
4. Design relativistic nonlocal projectors.
5. Design noncollinear density and exchange-correlation handling.
6. Build end-to-end SCF and band benchmarks.

## Related upstream work

This workbench follows existing upstream discussion without claiming ownership of it:

- [JuliaMolSim/DFTK.jl issue #526, “Non-collinear magnetism”](https://github.com/JuliaMolSim/DFTK.jl/issues/526)
- [JuliaMolSim/DFTK.jl issue #1272, “Making noncollinear calculation (`spin_polarization=:full`) enabled/supported”](https://github.com/JuliaMolSim/DFTK.jl/issues/1272)
- [JuliaMolSim/DFTK.jl pull request #1273, “Noncollinear (`spin_polarization=:full`) calculation added”](https://github.com/JuliaMolSim/DFTK.jl/pull/1273)
- The generic multicomponent discussion represented by those noncollinear density, wavefunction, Hamiltonian, and exchange-correlation proposals

The upstream items were open at the recorded inspection time; see [`config/sources.lock`](config/sources.lock). Their contents and status may change. This workbench is intended to complement existing noncollinear work by focusing on fully relativistic projector metadata, reproducible QE benchmarks, and incremental reviewable changes. It does not imply that any proposal has been accepted upstream.

Phase 4A hardens the acceptance tooling and environment identity checks; see the [Phase 4A review](results/phase4a-review.md). This does not add SOC support.

## Repository map

- [`rfc/soc-v1.md`](rfc/soc-v1.md): tentative v1 design and open questions
- [`config/`](config/README.md): pinned source and provenance records
- [`benchmarks/`](benchmarks/README.md): planned matched-code benchmark layout
- [`environment/`](environment/README.md): reproducibility records and templates
- [`results/`](results/README.md): policy for small, reviewable results
- [`scripts/`](scripts/README.md): policy for future automation
- [`results/fully-relativistic-upf-inspection.md`](results/fully-relativistic-upf-inspection.md): Phase 3 runtime and source inspection
- [`HANDOFF_TO_GPT56PRO.md`](HANDOFF_TO_GPT56PRO.md): reviewer-oriented execution and evidence handoff
- [`CONTRIBUTING.md`](CONTRIBUTING.md): contribution and clean-room rules
- [`MANUAL_ACTIONS.md`](MANUAL_ACTIONS.md): remaining human verification

## AI assistance disclosure

GPT-5.6 Pro is used for technical planning, theory review, test design and code review. OpenAI Codex is used for incremental implementation, repository inspection and test automation. The repository owner remains responsible for executing and interpreting tests, understanding the submitted code, maintaining the project and responding to technical review.

OpenAI Codex; exact model identifier not exposed to the task.

## Licensing and provenance

Quantum ESPRESSO is a numerical reference, not a source for line-by-line translation. This project will use independently written descriptions, interfaces, and tests; it will not copy or translate QE source code.

Pseudopotential files will not be redistributed unless their license explicitly permits it. Otherwise, only family identifiers, source information, license references, and SHA-256 checksums will be committed. The repository itself is available under the [MIT License](LICENSE).
