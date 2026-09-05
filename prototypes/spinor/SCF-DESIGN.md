# Phase 5B: restricted charge-only spinor SCF

This workbench prototype retains Phase 5A's component-interleaved layout and
scalar spatial operators. It adds an actual spinor density fixed point and a
seven-term orbital–density energy evaluation. It is not upstream DFTK spinor
support, SOC, a spin-dependent functional or noncollinear LSDA.

## Energy boundary

For each spatial k point, `chi=hcat(X[1:2:end,:],X[2:2:end,:])` and
`fchi=vcat(f,f)` are factors of a spatial density matrix. Their columns are
neither separate physical states nor separately normalized/orthogonalized.
The reciprocal electron count is `sum(k,c,n,w*f*norm(component)^2)`, not
`sum(k,n,w*fchi)`. The physical spinor capacity is one: eight occupied states,
sixteen targets and six empty auxiliaries at each of eight equally weighted k
points. No scalar capacity-two occupation function is called for these factors.

`energy_snapshot` reconstructs R/n/m from the supplied orbitals and occupations.
It accepts an optional expected density solely as a provenance check; this
argument cannot replace the actual orbital density. The valence n is converted
to `(Nx,Ny,Nz,1)` and passed to exactly one `energy_hamiltonian` traversal.
The only accepted terms are Kinetic, AtomicLocal, AtomicNonlocal, Hartree, Xc,
Ewald and PspCorrection, with the checked B0/default settings. Missing, repeated
or additional terms and altered XC/kinetic/Hartree settings are rejected.

The frozen DFTK commit is
`2f51b91213e26726fb9c6a17e5fae235a1412d01`. Inspected interfaces establish:

- `src/terms/kinetic.jl:40–58` sums weighted quadratic expectations without
  requiring factor columns to have unit norm or to be mutually orthogonal.
- `src/terms/nonlocal.jl:31–47` evaluates the corresponding weighted projector
  quadratic form, with the same factor property.
- `src/terms/local.jl:9–21` uses the explicit total density integral.
- `src/terms/hartree.jl:48–57` uses the total valence density; its existing
  linear `apply_kernel` supplies the same-density Hartree potential diagnostic.
- `src/terms/xc.jl:83–115,161–174` adds NLCC internally and returns the XC
  energy/potential. The bridge never adds core density to valence n. Hartree,
  electron counts and `integral(n*vxc)` therefore remain valence-only.
- `src/terms/ewald.jl:28–30` and `src/terms/psp_correction.jl:18–20` return one
  precomputed energy per physical cell and no Hamiltonian operator contribution.
- `src/terms/Hamiltonian.jl:200–227` traverses all terms once; lines 248–259
  expose the total local potential. With exactly these terms,
  `vxc=Vtotal−Vatomic−vH` recovers the XC potential without another XC evaluation.

Independent diagnostics apply the actual nonlocal operator to each component,
sum the kinetic expectations, integrate atomic local and half Hartree energies,
and check each per-cell constant once. Applying H at the orbitals' own n gives
the fixed-H band expectation and the double-counting check

`E = Eband − EH − integral(n*vxc) + Exc + EEwald + EPspCorrection`.

No Phase 4C reference constant is applied. A band expectation is separately
labelled and is not substituted for the DFT total energy. The first clearly
non-self-consistent map and the final map both retain these checks.

## Density map and endpoint

Each map constructs H[n_in], actually solves its 2NG component operator,
sets capacity-one occupations, reconstructs n_out/R/m and evaluates E[Psi,n_out].
No scalar SCF is called inside this loop. The first random ComplexF64 QR
subspace is independent for each run and k point; subsequent maps may reuse
only their own previous spinor orbitals. The measured Pauli m is retained,
while only n feeds the unpolarized LDA/Hartree potential.

The ordinary update is `n_mixed=(1−0.3)*n_in+0.3*n_out`. The convergence test is
the **unmixed** `sqrt(dvol)*norm(n_out−n_in)`, never the damped step. A candidate
triggers an extra real map from its output density. This closure map counts
against the same 200-map limit; failed closure outputs enter the next mixed
step. The final returned orbitals, density and energy belong to that closure
map, including the rebuilt H[n_out] check. Rayleigh quotients of H[n_out] are
diagnostics, not newly solved eigenvalues.

Every input/output/mixed/actual-next density has a hash, electron count, norm
and minimum. Potential hashes/changes, a fixed complex probe's H action, solver
iterations, operator counts, Gram errors and explicit target residuals establish
the actual feedback chain. No iterative density clipping, renormalization or
symmetrization is performed. Only the initial guess receives one documented
electron-count normalization. B's fixed cosine perturbation preserves the
discrete charge count and is built from the same initial guess, not A or C.

## Fixed settings and validation

[phase5b.toml](phase5b.toml) declares all thresholds before A/B/C. Norms include
the volume-weighted density norm, target Gram Frobenius norm, explicit
H[n_in] residual and endpoint H[n_out] residual. Negative density beyond
`64eps(Float64)*max(1,maximum(abs,n))` is rejected, never clipped.

The real driver runs A (guess, seed 54001), B (perturbed guess, seed 55001),
then one independent native scalar C (fresh guess, seed 0, density tolerance
1e-9). The historical B0 configuration and Phase 5A files are unchanged.
Afterwards, an occupied/empty pair at Gamma is rotated by 0.13 radians. For
the three fixed steps 1e-3, 3e-4 and 1e-4, both displaced states recompute
their own density and full energy; the analytic derivative instead applies
H at the center's orbital density. The center must be measurably nonstationary.

New tests include synthetic density-map failures, general complex energy
factors, partial component norms, NLCC/counting and density provenance checks,
unitary/SU(2) invariance, changed-potential probes and failure recording.
The unchanged 544 Phase 5A assertions are rerun. Synthetic orbital/function
tests do not count as A/B/C SCF evidence. Results and code were prepared with
Codex AI assistance and require repository-owner numerical/architecture review.
