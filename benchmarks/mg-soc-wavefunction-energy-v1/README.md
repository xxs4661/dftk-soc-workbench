# Original G40 orbital / energy audit (Phase 7F)

This is a static audit of exactly the original G40 SCF wavefunctions and the
original Phase 6C A/B endpoints, all `HISTORICAL_REUSED`. No calculation of a new
self-consistent state, eigenstate, occupation, XC or potential is allowed.
[plan.json](plan.json) freezes sources, actual header findings, units and gates
before coefficient extraction. The accepted base is
`28e67d4aca41e11b38a6364503e2dbacc0dd1ee4`.

## Source and format contract

The original G40 three files match the Phase 7B archive manifest and save
snapshot; A/B checkpoint, endpoint and map receipts match the Phase 7C bound
archives. All 29 current original files are also compared to those external
copies before extraction. Archive locations in public data are labels and
relative paths. These are same-machine backups, not offsite copies.

Official QE `qe-7.5` source locators and read-content hashes are in
`plan.format_source`. Installed exact source commit is NOT_CONFIRMED. The
[writer](https://github.com/QEF/q-e/blob/qe-7.5/Modules/io_base.f90) and
[producer](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/pw_restart_new.f90)
define records containing ik, Cartesian k, ispin, logical gamma flag, scale;
ngw, igwx, npol, nbnd; three reciprocal columns; native integer G; then one
complex coefficient record per band. Up precedes down in separate NG blocks.
Actual format is uniquely little-endian, four-byte markers, I4/L4, ComplexF64;
npol=2, nbnd=24, ispin=1, gamma=false, scale=1. Unsupported encodings fail.

`ngw` is the maximum original global G index; `igwx` is the compact selected
count. Their values are (2777,2777), (2925,2770), (2944,2770). The latter match
XML npw. Neither full inversion symmetry nor G=0 is imposed on nonzero-k
wavefunction sets. Both k and reciprocal columns are already in bohr^-1, with
2π included. Match ik, physical k, lattice and each integer G, never energy or
file name alone. DFTK's exact original G enumeration is restored only with its
static Kpoint constructor and compared to historical Serialization hashes.
No Model or term initialization is needed. A bijection is mandatory for FR.

[XML construction](https://github.com/QEF/q-e/blob/qe-7.5/Modules/qexsd_init.f90)
writes original f=wg/wk and eigenvalues in Ha. Spatial weights multiply these
capacity-one spinor occupations once. Preserve all 24 states, including exact
zero and tiny occupations, without a new chemical potential. Original XML
nsym=1/no symmetry, NC/no augmentation and nonmagnetic settings bound the
[saved charge](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/sum_band.f90).
The final printed energies use output charge; the saved orbitals originated
from the original input Hamiltonian. Its full residual remains NOT_AVAILABLE.
A weighted XML band sum only checks bookkeeping.

## Predeclared mathematics and stopping gates

Columns of A are direct vectors, B=2π A^-T, Ω=|det A|=1000 bohr³.
q=B m+k_cart. Each original state has Σ(G,σ)|c|²=1. On the zero-origin 40³
mesh, u=ifft(C) Ngrid/√Ω; n=Σ(k,n) wk f (|u↑|²+|u↓|²).
Compare A/B to their unchanged n_out, Q to all 22119 actual saved density G.
Independently check the 17 predeclared Fourier probes by finite coefficient
correlations nbar(g)=Σ wk f c(m+g)conj(c(m))/Ω. Prove actual G-G product
support fits 40³; count/report modes outside Q support rather than silently
filtering. Nyquist and finite-representation limitations stay explicit.

T_direct=Σ wk f |c|² |q|²/2. The independent path integrates
Σα |ifft(i qα c) Ngrid/√Ω|² dvol/2, retaining the k contribution.
Only after identity, mapping, occupations, norm/Gram, density and both kinetic
paths pass may the frozen FR operator be constructed once for each of three k.
Retain every radial column and off-diagonal D entry. Evaluate both P D P† action
and y†D y, y=P†X, including up/down cross terms. A/B must restore their
historical T and NL separately. Q is labeled
`DFTK_FROZEN_FR_NONLOCAL_EXPECTATION_ON_QE_G40_ORBITALS`; independent native
QE nonlocal energy is NOT_MEASURED.

All thresholds are in `plan.thresholds`: exact hashes/bijections/roundtrip;
1e-12 duality/k; 1e-10 Ha cutoff allowance; 1e-9 norm and Gram Frobenius;
1e-8 electrons; 1e-9 Ha direct-gradient and A/B T/NL restoration;
1e-10 Ha action-projection; Q density max1e-10 e/bohr³ and nonzero relative
L2 1e-9; A/B density relative L2 1e-9 and node max1e-10;
correlations1e-11 e/bohr³; synthetic normalized1e-12;
ledger1e-10 Ha plus participating print intervals. No cross-code physical
agreement threshold or post-hoc fitting is defined. A failed dependency blocks
later evaluation; original arrays and failed receipts remain unchanged.

## Signed ledger and precision

Reuse prior O_Q=E-H-XC-Ewald and the P2 *reconstructed* potential, not an
original SCF memory potential. L_saved and L_wfc use the same P2 field.
Let K_S^hist=T_S^hist+NL_S^hist, K_S^new=T_S+N_D[S], K_Q^inD=T_Q+N_D[Q].
Record response=K_S^new-K_Q^inD, J_Q=K_Q^inD+L_wfc-O_Q,
deltaL=L_saved-L_wfc, drift_S=K_S^new-K_S^hist. Then
R_old=response+J_Q+deltaL-drift_S, with any historical summation drift explicit.
O_Q-L_wfc-T_Q is `DERIVED_NL_SHAPED_REMAINDER_NOT_DIRECT_QE_NL`.
No historical E/F correction and no percentage-based attribution is made.

Propagate the original P2 per-node print halfwidth uV:
uL=dvol Σ |n_wfc|uV and uDeltaL=dvol Σ |n_saved-n_wfc|uV.
Use correlated cancellation before forming bounds, not independent RSS.
XML tokens retain their last printed digit halfwidth. These are print-precision
diagnostics, not physical error bounds or confidence levels.

## Reproduction and evidence scope

Execution will use `scripts/run_orbital_energy_audit.py` with the existing
NumPy runtime and frozen Julia environment. `scripts/check_orbital_energy.py`
will replay public Q density, direct/gradient kinetic and frozen FR contractions,
plus published A/B contractions and the signed ledger, without .work or UPF.
Extracting original A/B arrays remains a runner-layer claim with bound hashes;
regenerating P separately requires obtaining the locked UPF and frozen checkout.

The explicitly requested canonical public NPZ contains every Q coefficient,
G, f, eigenvalue and geometry at original Float64 precision, with per-array
expanded-byte manifests. Estimated complete public numerical evidence is about
11 MB before compression (6.39 MB Q coefficients plus 4.26 MB P), not duplicate
raw files. A/B X, raw saves and process logs remain external. Synthetic fixtures
are protocol/mathematical tests, never physical pseudopotential evidence.
