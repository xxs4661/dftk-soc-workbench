# RFC: Investigating SOC support in DFTK.jl, v1

**Status:** Historical initial proposal, not current capability status and not accepted upstream.
See [current capabilities](../docs/status.md) for implemented prototype scope.

**Scope:** Fully relativistic norm-conserving UPF pseudopotentials on CPU

**Evidence level:** Architectural statements explicitly marked as proposals, hypotheses, or open questions remain undecided

## 1. Problem statement

This RFC investigates how DFTK might support an end-to-end SOC calculation using fully relativistic norm-conserving UPF pseudopotentials, two-component spinors, SCF, and band structures. It organizes the questions and tests needed to investigate that capability. It is not a claim of implementation, correctness, QE agreement, or maintainer acceptance.

**Proposal:** Decompose the work into separately reviewable representation, operator, density/XC, and validation increments, retaining scalar-relativistic behavior as a regression baseline.

## 2. Why SOC requires two-component spinors

For spin-1/2 electrons, a single Kohn–Sham state in a fixed spatial basis has two complex spin amplitudes,

\[
\Psi_{n\mathbf{k}}(\mathbf{r}) =
\begin{pmatrix}
\psi_{n\mathbf{k},\uparrow}(\mathbf{r}) \\
\psi_{n\mathbf{k},\downarrow}(\mathbf{r})
\end{pmatrix}.
\]

An SOC Hamiltonian generally couples these amplitudes, so independent scalar up/down channels are insufficient. The corresponding local one-particle density is a \(2\times2\) Hermitian matrix, equivalently expressible through charge density \(n\) and magnetization \((m_x,m_y,m_z)\).

**Hypothesis:** A two-component complex representation can be introduced while preserving existing scalar and collinear paths through explicit adapters or specialized dispatch. This requires source inspection and profiling before a layout is selected.

## 3. Tentative support matrix

Every entry in this matrix is a **proposal**, not a completed capability.

| Area | Proposed v1 status | Evidence still required |
| --- | --- | --- |
| Norm-conserving, fully relativistic UPF | In scope | Parser metadata inventory and fixtures |
| Scalar-relativistic norm-conserving UPF | Regression baseline | Matched DFTK–QE inputs and convergence |
| Two-component spinors | In scope | Layout decision, operator interfaces, tests |
| LDA / LSDA | In scope | Noncollinear XC convention and limiting cases |
| SCF | In scope | Density, mixing, occupations, convergence tests |
| Band structures | In scope | Explicit path and comparable QE settings |
| CPU | In scope | Correctness and baseline performance |
| Spatial symmetry reduction | Deferred or disabled | Future magnetic double-group design |
| Ultrasoft / PAW | Out of scope | Separate augmentation formalism |
| Forces, stresses, DFPT, phonons | Out of scope | Derivatives of the accepted energy/operator design |
| DFT+U and GPU optimisation | Out of scope | Separate follow-up design |

## 4. Non-goals

The v1 proposal excludes ultrasoft pseudopotentials, PAW, forces, stresses, phonons, DFPT, DFT+U, GPU optimisation, complete magnetic-space-group support, and machine-learning potentials. It also excludes source-level reproduction or translation of Quantum ESPRESSO.

## 5. Known upstream context

The following upstream work is relevant and is not owned by this workbench:

- [Issue #526](https://github.com/JuliaMolSim/DFTK.jl/issues/526) raises non-collinear magnetism and SOC.
- [Issue #1272](https://github.com/JuliaMolSim/DFTK.jl/issues/1272) discusses enabling `spin_polarization=:full`.
- [Pull request #1273](https://github.com/JuliaMolSim/DFTK.jl/pull/1273) proposes noncollinear support.
- The generic multicomponent discussion spans spinor wavefunctions, four real density/magnetization components, coupled Hamiltonians, and noncollinear XC handling.

Their status is recorded in [`../config/sources.lock`](../config/sources.lock). **Open question:** Which concepts, if any, from the ongoing generic multicomponent discussion will be accepted upstream, and which interfaces will remain stable enough for SOC work?

## 6. Open design question: spinor wavefunction layout

**Open question:** Should the spin component be represented as a dedicated array dimension, folded into the row dimension of each plane-wave coefficient matrix, or expressed through a small static-vector element type?

**Proposal:** Evaluate candidate layouts against these criteria before choosing one:

- compatibility with current FFT, linear algebra, eigensolver, MPI, and checkpoint interfaces;
- ability to apply local \(2\times2\) potentials and nonlocal projectors without unnecessary copies;
- explicit, testable indexing conventions;
- preservation of scalar and collinear performance; and
- future extensibility without requiring v1 GPU support.

**Hypothesis:** A dedicated spin dimension may make the physics clearest, while a flattened matrix may integrate more directly with existing eigensolver interfaces. Benchmarks and source inspection are needed to resolve the trade-off.

## 7. Open design question: density matrix versus `(n, mx, my, mz)`

At each real-space point, a Hermitian spin-density matrix can be decomposed as

\[
\rho = \tfrac{1}{2}\left(n I + m_x\sigma_x + m_y\sigma_y + m_z\sigma_z\right).
\]

**Open question:** Should the primary stored representation be the complex \(2\times2\) density matrix or the four real fields \((n,m_x,m_y,m_z)\)?

**Proposal:** Compare both representations for numerical constraints, XC interfaces, mixing, symmetrization, memory layout, diagnostics, and conversions at API boundaries.

**Hypothesis:** Four real fields could fit density mixing and XC evaluation naturally, while a matrix representation could make covariance and Hermiticity more explicit. Neither choice is accepted here.

## 8. Open design question: preserving `(l, j, projector-index)` UPF metadata

Fully relativistic nonlocal pseudopotentials require enough metadata to distinguish angular-momentum channels that share \(l\) but differ in total angular momentum \(j\), as well as multiple projectors within a channel.

**Open question:** Which current UPF parsing layers preserve `l`, `j`, projector order/index, coupling coefficients, and convention information, and where is any information lost?

**Proposal:** Build a small metadata inventory using legally obtained fixtures or sanitized metadata summaries. Preserve source ordering and explicit identifiers until canonicalization is shown to be safe.

**Hypothesis:** Collapsing projectors by \(l\) alone would be insufficient for a fully relativistic operator. Parser and format evidence is required before specifying an API.

## 9. Tentative nonlocal operator structure `P * D * P'`

**Proposal:** Investigate a nonlocal operator expressed schematically as

\[
V_\mathrm{NL} = P D P^\dagger,
\]

where \(P\) maps spinor plane-wave coefficients to a projector space and \(D\) couples projector channels using pseudopotential metadata. Here \(P^\dagger\), written as `P'` in Julia notation, is the adjoint.

**Open question:** Should spin-angular coupling be encoded in \(P\), in \(D\), or split between them, and what indexing makes Hermiticity auditable?

**Proposal:** Require dimension, convention, and Hermiticity tests for each factor and for the composed operator. Avoid materializing a dense plane-wave-space matrix.

**Hypothesis:** Factoring the operator can reuse low-rank nonlocal machinery, but the existing interfaces must be inspected before this becomes a concrete design.

## 10. Symmetry deferral strategy for v1

**Proposal:** Use explicit k-points or disable spatial-symmetry reduction initially. Retain only symmetry operations whose action on spinors and SOC Hamiltonians has been derived and tested.

**Open question:** What is the smallest correct treatment of time reversal needed for v1 without implying complete magnetic-space-group support?

**Hypothesis:** Deferring spatial reduction will simplify correctness arguments at an acceptable v1 performance cost. This must be measured on the selected benchmarks.

## 11. QE validation plan

**Proposal:** Treat QE as an independent numerical reference using matched physics and convergence settings, not matched implementation details.

1. Select a small nonmagnetic system with suitable scalar- and fully relativistic norm-conserving UPF variants.
2. Record exact UPF identifiers, provenance, licenses, and SHA-256 checksums without committing restricted files.
3. Establish independently converged scalar-relativistic QE and DFTK baselines.
4. Add fully relativistic QE reference calculations with explicit k-points and record all relevant input flags.
5. When a DFTK implementation exists, compare eigenvalues and SOC splittings using declared band-matching rules and tolerances.
6. Test Hermiticity, no-SOC spin degeneracy, time reversal, appropriate Kramers degeneracy, and applicable spin rotations.
7. Archive small sanitized tables and environment metadata; keep raw and large outputs outside Git.

**Open question:** Which material and pseudopotential family provide the smallest license-compatible benchmark with clearly resolved SOC splittings?

## 12. Licensing and clean-room implementation constraints

Quantum ESPRESSO is a numerical reference. No QE source code will be copied, translated line by line, or used to imply compatible internal architecture. Public scientific papers, format documentation, independently derived equations, observed numerical inputs/outputs, and suitably licensed upstream APIs may inform the work with attribution.

**Proposal:** Record the provenance and license of every external artifact. Commit pseudopotential files only when redistribution is explicitly permitted; otherwise commit identifiers, source information, license references, and SHA-256 checksums.

## 13. Risks and unknowns

- **Open question:** Does the existing UPF parser expose all fully relativistic channel metadata without loss?
- **Open question:** Can a spinor layout integrate with current eigensolvers, FFTs, checkpointing, and post-processing without broad churn?
- **Open question:** Which sign, phase, spherical-harmonic, and projector-order conventions must be normalized across inputs and operators?
- **Hypothesis:** Silent convention mismatches are a larger correctness risk than floating-point error in early comparisons.
- **Open question:** Which LSDA/noncollinear XC interface handles low-magnetization limits robustly?
- **Open question:** How should band correspondence be established near crossings and degeneracies?
- **Open question:** What memory and runtime regressions are acceptable for scalar and collinear calculations?
- **Open question:** How will upstream noncollinear work evolve, and which parts can be reused after review?

## 14. Proposed incremental pull-request decomposition

This is a **proposal** for future work; no upstream pull request is opened by this phase.

1. Documentation-only inventory of fully relativistic UPF metadata and conventions.
2. Parser fixtures and metadata preservation, preferably in the owning parser repository after explicit authorization.
3. Spinor container and linear-algebra primitives with scalar-path regression tests.
4. Local spin-independent operators acting on spinors.
5. Relativistic nonlocal projector operator with Hermiticity tests.
6. Noncollinear density and LDA/LSDA potential representation.
7. SCF plumbing with symmetry reduction disabled or explicitly constrained.
8. Band-structure support and matched QE benchmark reports.

**Open question:** The owning repository and exact boundary of each increment depend on upstream feedback and source inspection.

## 15. Acceptance tests

The following are **proposed** acceptance tests; none is reported as passing:

- Unit-level dimension, adjoint, and Hermiticity checks for spinor operators.
- Recovery of existing scalar or collinear results when the new path is inactive.
- Recovery of spin degeneracy without SOC for appropriate nonmagnetic systems.
- Time-reversal relations at paired k-points when time-reversal symmetry applies.
- Kramers degeneracy at appropriate time-reversal-invariant k-points when all preconditions apply.
- Global spin-rotation invariance where applicable without SOC.
- Cutoff and k-point convergence demonstrated before cross-code comparison.
- QE–DFTK eigenvalue and SOC-splitting comparisons with documented band matching and tolerances.
- Reproducibility from exact source revisions, environment records, inputs, pseudopotential identifiers, and SHA-256 checksums.
- No regression in the existing test suite and a documented CPU cost for the spinor path.

**Open question:** Numerical tolerances remain pending verification until representative converged baselines exist.

## 16. AI-assistance disclosure

GPT-5.6 Pro is used for technical planning, theory review, test design and code review. OpenAI Codex is used for incremental implementation, repository inspection and test automation. The repository owner remains responsible for executing and interpreting tests, understanding the submitted code, maintaining the project and responding to technical review.

OpenAI Codex; exact model identifier not exposed to the task.
