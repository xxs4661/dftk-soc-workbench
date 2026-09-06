# Phase 6B: common data, full Hamiltonian and orbital energy

This workbench prototype composes the unchanged Phase 5A component layout with
Phase 6A FR projectors. It performs fixed-density solves and current-orbital
energy checks only. It does not call SCF or add native DFTK SOC support. The
implementation and analysis received material Codex AI assistance; numerical
acceptance remains subject to human review.

The [fixed configuration](phase6b.toml) is specific to the prescribed Mg
integration fixture and original B0 Si scalar regression. Input paths and hashes
come from the frozen source lock/B0 case. Use a fresh Julia process in
`environment/workbench` with the previously instantiated locked dependency cache:

```sh
julia --startup-file=no --project=environment/workbench tests/fr_integration/runtests.jl .work/phase6b/NEW_TEST_ID
julia --startup-file=no --project=environment/workbench scripts/run_fr_integration.jl .work/phase6b/NEW_RUN_ID
```

Set Julia, BLAS and OpenMP threads to one, and `JULIA_LOAD_PATH=@:@stdlib`.
An existing evidence directory is refused. Raw orbitals/densities stay under
ignored `.work`. No dependency installation or resolution is part of these commands.
The driver checks the actual loaded source identity before constructing models.

## Common data and source identity

`load_bound_psp` reads verified bytes, parses once, and issues a bundle binding
actual common/channel/parsed objects. An identity registry and full snapshots
reject copied hash labels, replaced objects and changed source arrays. The exact
raw PP_HEADER is retained; PPIO normalizes functional whitespace in its parsed
representation ([fixed parser](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/file/upf2.jl#L149)).
The real-FR and synthetic-scalar-limit entry modes remain distinct.

`CommonPspData` implements only required interfaces for its own type. It has no
native scalar projectors: attempts to use its native AtomicNonlocal path are
explicitly rejected. The original DFTK SOC guard and original parsed has_so
remain intact.

The adapter retains each full common radial grid independently of beta support:

- `PP_LOCAL / 2` is the local potential in Ha.
- `PP_RHOATOM / (4π)` is `r² n_valence`, used in the l=0 Hankel transform.
- `PP_NLCC` is actual `n_core`; its Fourier integrand is `r² n_core`.
- Absence of Mg NLCC remains absence; Si's core is added inside native Xc once.
- Real local/core interpolation uses actual finite source values. No real-space
  valence-density `r²/r²` interface is introduced at the origin.

The reused frozen low-level interfaces are
[PspUpf local Fourier](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/pseudo/PspUpf.jl#L235),
[Hankel](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/common/hankel.jl#L1)
and its physical-grid quadrature, and the finite correction
`alpha = 4π integral r*(r*V_local_Ha+Z) dr`.
The local G=0 component is zero. The separate
[PspCorrection](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/terms/psp_correction.jl#L1)
is `N_e sum_atoms(alpha)/Omega`, with a Noop Hamiltonian contribution.
There is no extra eigenvalue-reference shift or repeated constant compensation.
These calls reuse small frozen interfaces; no PspUpf implementation is copied.

## Full operator and energy

The model explicitly has six terms: Kinetic, AtomicLocal, Ewald, PspCorrection,
Hartree and Xc. It never uses the convenience model that automatically inserts
AtomicNonlocal. Actual model and instantiated term/XC identities are checked.

Each k block has `ComponentOperator(H_common,2) + V_NL_FR`. The issued context
binds the basis, fractional k, actual G order, FFT mappings, atom order, cell and
pseudopotential data. Swapping equal-sized k blocks is rejected. Both scalar
HamiltonianBlock variants are supported via their common interfaces; no real
plane-wave matrix is materialized. Iterative calls check live object/grid
identity; complete P/D and source snapshots are checked at construction and
energy boundaries. Public mutable buffers are not intended for concurrent edits.

For capacity-one spinor occupations, the unchanged Phase 5A FFT/density helpers
produce R/n/m. Six common energies use spatial factors `[Xup Xdown]`, occupations
`[f;f]`, and explicit valence n. Component columns are not individually normalized.
The full spinor FR term is added once. Independent `P_up' Xup` and `P_down' Xdown`
contractions resolve diagonal and cross-spin energy contributions.

The full native
[GGA potential](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/terms/xc.jl#L94)
includes gradient/divergence terms and native NLCC ownership. Extracting
`vxc = total_local_potential - AtomicLocal - vHartree` retains those terms for
the double-counting identity. Its valence-density integral is checked against
actual occupied `H_full[n_X]` actions, never old `H[n_ref]` eigenvalues.

Only three Mg k points are solved at the fixed analytic n_ref. Constructing
H[n_X] for energy and finite differences never feeds n_X to another eigensolve.
The lowest N_e states per k have prescribed diagnostic occupations, without a
global ground-state filling claim. The fixed orbital rotation and three step
sizes are not varied after results are observed. General complex energy fixtures
are clearly distinct from the solved orbitals and from a physical ground state.

See the [review report](../../results/phase6b-review.md) for actual execution,
source hashes, failures, numerical values and remaining limits.
