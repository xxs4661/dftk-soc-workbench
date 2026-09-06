# Possible upstream extraction and open questions

These are proposals for repository-owner discussion, not an accepted DFTK design.
The workbench uses prescribed Mg/Si cases, Float64/ComplexF64 CPU paths and
process-local `IdDict` identity registries. Those constraints and the current
layout do not imply that this code can be merged unchanged. No upstream message
or pull request was sent by this phase.

| Possible small module | Present limitation | Question for maintainers |
| --- | --- | --- |
| Component FFT/operator lifting and R/n/m density construction | Component-first storage and flattening are explicit prototype conventions; the existing scalar density bridge carries only charge. Noncollinear XC remains unimplemented. | What public wavefunction/density interface and ownership rules should support scalar, collinear and spinor data? |
| Angular/radial FR projectors and global capacity-one Fermi occupations | Kernels and tolerances currently specialize on Float64/ComplexF64; the driver fixes the tested material, k set and band-expansion policy. | Which numeric types and accuracy contracts belong in reusable kernels versus case orchestration? |
| Pure numerical kernels separated from stateful orchestration | Array mutation, scalar loops, CPU allocations and process-local identity checks have no AD/GPU validation. | Which interfaces need differentiation and accelerator support, and where should device-independent numerical code stop? |
| Matrix-free FR application and component workspace reuse | Current scratch allocation, source snapshots and repeated density/Hamiltonian checks prioritize auditability. Recorded counts are not a production performance benchmark. | Which cache lifetimes, batching and allocation budgets fit the upstream execution model? |
| Bound FR common-pseudopotential interface | Local, valence/core density and correction data are bound to the same parsed UPF as FR channels; current loader capabilities are process-local prototype machinery. Native SOC rejection remains intact. | Should common NC data be a shared public interface, and how should source identity, NLCC and scalar/FR projector ownership be expressed without these registries? |

The next scientific gate is the first independent QE SOC comparison of E and F.
These architectural questions do not add another internal-validation prerequisite.
The repository owner is responsible for any later upstream communication.
