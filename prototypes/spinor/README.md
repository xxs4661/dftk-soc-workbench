# Phase 5A component prototype

This replaceable workbench prototype tests two-component orbitals on the fixed
final scalar Si Hamiltonian. It does not implement SOC, a spinor SCF loop,
noncollinear LSDA, forces, stress, or a physical magnetic field. The synthetic
Pauli operator is an algebra test only. No DFTK or dependency method is replaced.

## Representation and scalar operator

Orbitals have shape `Psi[component, G, state]`. Julia column-major flattening
gives `row = component + ncomp*(G-1)`, with states as matrix columns. Each k point
supplies its own `NG`; the component count, plane-wave count, state count, and
spatial k-point weight are separate quantities. Generic algebra and FFT tests use
`ncomp=1,2,3`; the physical spinor experiment uses exactly two components.

`ComponentOperator(H,ncomp)` applies the same scalar `H` independently to every
component. In this layout its small dense reference is `kron(H,I_ncomp)`.
Production application copies each strided component into an `NG × nstates`
block and calls the existing scalar `mul!`; it never builds the dense lifted
Hamiltonian. Inputs are preserved, overlapping input/output storage is rejected,
and dimensions are checked before application. Counters record lifted calls and
columns and the corresponding scalar calls and columns. The prototype is serial
CPU code and allocates component scratch on each application.

The preconditioner has diagonal `repeat(Tkin .+ 1 Ha; inner=ncomp)`. It is positive
and spin independent; the solver applies its inverse with `ldiv!`. Exact in-place
preconditioning is supported, while other overlapping views are rejected.

## FFT, occupations, and density

The FFT adapters transform the periodic Bloch part
`u(r)=sum_G c_G exp(2πi G⋅r)/sqrt(Ω)`, without the `exp(2πi k⋅r)` factor. The flat
real-grid axis follows `vec(DFTK.r_vectors(basis))`. Total orbital normalization
is `sum(component,G, abs2(Psi)) = dvol*sum(component,r, abs2(u)) = 1`; individual
components are not independently normalized. The forward transform is a
projection onto the selected k point's spherical plane-wave subspace.

Spatial weights sum to one, independently of occupation capacity. The restricted
eight-electron, zero-temperature helper requires a positive global gap. Scalar
orbitals have capacity two and four occupied states; explicit spinors have
capacity one and eight occupied states. Auxiliary states are empty. This helper
does not call DFTK's `spin_polarization=:none` occupation rule for spinors and does
not solve metallic occupations.

The density is `R[a,b,r]=sum(k,state, w*f*u[a]*conj(u[b]))`, with `n=tr(R)` and
`m=(2real(R12),-2imag(R12),R11-R22)`. Here `m` is Pauli spin density, not a magnetic
moment. The synthetic local action is `v*I+B⋅sigma`, with upper-right
`Bx-i*By` and lower-left `Bx+i*By`. Global SU(2) commutation is asserted only for
the scalar lift, not for a fixed nonzero Pauli field or SOC.

## Fixed-Hamiltonian experiment and acceptance

The planned Si solve uses eight scalar target states plus three auxiliaries,
then sixteen spinor target states plus six auxiliaries at each of eight k points.
The spinor initial spaces are general complex random matrices, orthonormalized
as complete component-plus-G columns, using seeds 53001 through 53008. Scalar
and spinor eigensolver tolerances are `1e-10 Ha`; iteration limits are 150 and
300 respectively, with at least one spinor iteration. No scalar eigenvector or
duplicated spectrum is supplied as the spinor solution. The doubled scalar
spectrum is only a comparison reference after the iterative solve.

Thresholds and norm definitions are declared in [tolerances.toml](tolerances.toml).
Default algebra errors use `norm(error)/max(norm(reference),1)` with threshold
`1e-11`. FFT tests use the stricter true relative error, except when the reference
norm is below `1e-12`, where they use absolute error. Synthetic density tests use
relative errors for nonzero references and absolute errors for zero identities;
normalization checks use absolute deviation from one. Target-column
orthogonality uses the Frobenius norm of `X'X-I` (`1e-9`). Each target residual is
recomputed explicitly as the Euclidean norm of `H*x-lambda*x` (`1e-9 Ha`), even
when solver history reports a locked state. The spectrum gate is `1e-8 Ha`.
Density L2 norms are `sqrt(dvol)` times the grid Frobenius norm. The charge-density
comparison divides by the scalar final-H density norm; the Pauli-density ratio
divides by the measured spinor charge-density norm. Both denominators must be
positive, with no artificial floor; both thresholds are `1e-7`. Integrated
electron-count error is at most `1e-8`.

The occupied expectation `sum(k,state, w*f*real(dot(x,H*x)))` is compared between
scalar and spinor representations (`1e-7 Ha/cell`). It is a fixed-Hamiltonian
one-body expectation, not the DFT total energy. The native scalar SCF total
energy is reported separately, without replacing it by an eigenvalue sum or
applying a second pseudopotential reference correction. Runtime success and
measured values belong to the run records and Phase 5A review, not this design
description. Synthetic tests do not establish physical Si validation.

## Verified frozen interfaces

DFTK is pinned to `2f51b91213e26726fb9c6a17e5fae235a1412d01` by the unchanged
source lock. The implementation relies on these inspected source interfaces:

- [Hamiltonian.jl, lines 67–74 and 137–195](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/terms/Hamiltonian.jl#L67):
  scalar block `size`/`eltype` and matrix `mul!`, including local, kinetic, and
  nonlocal application. Only scalar-sized blocks cross this boundary.
- [fft.jl, lines 70–77, 99–110, and 151–182](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/fft.jl#L70):
  physical normalization, spherical-grid mapping, and the allocating forward
  transform's protected input. [PlaneWaveBasis.jl, lines 403–404 and 668–683](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/PlaneWaveBasis.jl#L668)
  supplies per-k G vectors and transform forwarding.
- [diag_lobpcg_hyper.jl, lines 5–17](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/eigen/diag_lobpcg_hyper.jl#L5):
  direct generic-operator solver entry point, explicit convergence count and
  iteration reporting. The scalar high-level k-block wrapper is not used for
  the doubled row dimension.

The unchanged workbench Manifest selects LOBPCGEigensolver 0.1.1, tree
`8c62b4ea551cffbe8faeb2019e96539d79c0e38e`. Its inspected
`src/lobpcg_impl.jl:385–411,487–488` uses generic block `mul!` and in-place
`ldiv!`; `src/utilities.jl:65` supplies the existing no-op `precondprep!` fallback.
No solver algorithm is copied into the workbench. The source inspection is
checked separately by the small synthetic iterative-solver test.
