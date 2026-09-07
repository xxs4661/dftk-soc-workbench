# Phase 6A independent relativistic nonlocal prototype

This is a workbench proposal and verified operator prototype, with numerical
review still required. It does not add native DFTK support, perform SCF, or
establish a QE SOC benchmark. Material implementation and analysis used Codex
AI assistance. The frozen Phase 5B implementation and its claims are unchanged.

## Data and column identities

The unchanged `UpfValidation` module first validates explicit FR-NC metadata.
Source beta indices associate `PP_BETA` with `PP_RELBETA`. They are **not** D
matrix subscripts: PPIO collects beta records in document order and compresses
both betas and D when deleting all-zero records. This phase rejects pruned or
otherwise unprovable mappings as `UNSUPPORTED`, following Phase 4A. Missing
`PP_RELWFC` does not invalidate a nonlocal beta. See the frozen parser
[beta/D path](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/file/upf2.jl#L410)
and [relbeta path](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/file/upf2.jl#L542).

`RadialChannel` retains the source index, parsed position, relbeta index, l,
integer 2j, internal radial number, owned raw/internal arrays and declared cutoff.
Internal channels sort by `(l,2j,parsed_position)`. D is reordered using parsed
positions. Explicit original and internal mappings are public; full radial
arrays remain local. Original parsed objects are not mutated.

The single expanded label table is `(atom,l,2j,2mj,radial_projector)` plus a
channel-position pointer. Columns are ordered by atom, l, 2j, ascending 2mj,
then radial number. Both P and expanded D consume this table. Each atom has
`sum(2j+1)` columns over its radial betas. D connects radial indices only within
one atom/l/j/mj block. Multiple same-(l,j) radial functions and non-diagonal,
indefinite D blocks remain valid. Unsupported cross-(l,j) coupling is rejected,
never discarded. No extra degeneracy or positivity assumption is applied.

## Units, radial transform and origin

The production convention is `b_internal=PP_BETA_raw/2`, `D_internal=2D_raw`,
matching frozen [PspUpf.jl](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/pseudo/PspUpf.jl#L119).
PP_BETA stores r times beta. The alternative `b=raw`, `D=D_raw/2` gives the
same full operator; separate beta/D dimensions depend on the UPF paired gauge.
Both conventions convert the full Ry operator to Ha. Neither is a beta
normalization. Values and signs from real inputs are preserved.

For Cartesian q in bohr^-1, the full radial factor is
`F_l(q)=4π integral r*b_internal(r)*j_l(qr) dr`.
Production computes its modified form `F_l(q)/q^l` with a stable
`j_l(x)/x^l` kernel and multiplies it by a complex solid harmonic. Frozen
[Hankel semantics](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/common/hankel.jl#L1)
already contain 4π and q^-l. Neither factor is applied a second time.

One production radial path uses the frozen physical-grid Simpson/trapezoid
quadrature selected for the validated support grid. The frozen fast spherical
Bessel formula warns about small-argument cancellation; its Hankel limit guard
only covers q <= 10eps. Therefore the new kernel uses the convergent series
for `j_l(x)/x^l` at |x| <= 0.5, including successive x² corrections, and the
frozen elementary expression above that range. It does not clamp a neighborhood
to a constant or change upstream methods. The series term ratio is
`-x²/[2k(2l+2k+1)]`, beginning at `1/(2l+1)!!`;
see [DLMF 10.53](https://dlmf.nist.gov/10.53).

At q=0 the modified radial factor is finite. Complex solid harmonics are
polynomials, so l>0 full P entries are exactly zero and l=0 has its finite
limit. No zero-vector direction, division by zero, or NaN repair is used.
The physical r grid is validated, with its first/last point and support cutoff
reported. Any listed tail beyond cutoff must be exactly zero. There is no
extrapolation, additional truncation, PP_RAB multiplication, or renormalization.

The analytic reference uses `beta_l=r^l exp(-a r²)` and thus
`b_l=r^(l+1) exp(-a r²)`. Combining the
[spherical Bessel definition](https://dlmf.nist.gov/10.47#E3) with the
[Gaussian Bessel integral](https://dlmf.nist.gov/10.22#E51) gives
`F_l=4π sqrt(π) q^l exp(-q²/(4a))/(2^(l+2) a^(l+3/2))`.
Tests use the two predeclared grids in [phase6a.toml](phase6a.toml), with
`a*rmax²=100.8`. The extra real-Mg reference uses 256-bit elementary Bessel
recurrence and physical-grid trapezoids. That independent quadrature difference
is a sensitivity diagnostic, not a rigorous bound or a machine-precision gate.

## Angular, Fourier and spin conventions

Rows remain interleaved: `row=sigma+2*(G-1)`, spin order up/down, Pauli sigma_y
`[0 -i; i 0]`. Complex harmonics include the Condon–Shortley phase. With frozen
[real solid harmonics R](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/common/spherical_harmonics.jl#L34):

- m>0: `q^l Y_l,m=(-1)^m*(R_l,+m+i R_l,-m)/sqrt(2)`;
- negative-order partner, for m>0: `q^l Y_l,-m=(R_l,+m-i R_l,-m)/sqrt(2)`;
- m=0 is unchanged.

The independent point reference uses associated Legendre recurrence, including
the explicit Y00/Y10/Y11 checks, rather than only checking a unitary matrix.
CG coefficients use the phase convention specified in the request, including
the minus sign on the up component of j=l−1/2. Invalid m components are zero
without calling a harmonic outside its range. Integer 2j/2mj labels are checked
before use; floating input j is validated at absolute 1e-10, relative zero
before conversion. Supported l is restricted to 0..3.

`P=exp(-i q·R)/sqrt(Ω) * (-i)^l * (F/q^l) * solid_spin_angular(q)`.
The Fourier kernel is exp(-i q·r)/sqrt(Ω). With fractional p/R this phase is
exp(-2πi p·R); Cartesian conversion introduces 2π exactly once.

## Independent checks and operator contract

The independent reference forms orbital ladder matrices and `S=Pauli/2` in the
uncoupled m-major spin-interleaved basis. It obtains Pi± from L·S, and compares
them to CG `U_j U_j'`, with Jz/J² labels, orthogonality, trace and completeness.
A separate highest-weight/Jminus reference checks CG columns and their phase.
The second nonlocal kernel contracts independent uncoupled Y, ladder Pi_j,
radial factors and D directly. It never calls production P/CG. Real-Mg angular
comparison intentionally shares the production radial discretization; synthetic
Gaussian kernels and analytic radial tests supply separate radial evidence.

`FRNonlocalOperator` stores rectangular P and small D only, with vector/multiple
column actions `P*(D*(P'*X))`. It owns construction copies, explicitly rejects
aliases and incompatible output storage, and does not read Y for beta=0 in
`mul!`. Dimension and finite-value checks fail explicitly. No square plane-wave
matrix is constructed in production; dense matrices are confined to tiny probes.
The nonlocal expectation and the projector-coefficient contraction are checked
separately and may be negative. This is not a DFT total energy.

The synthetic scalar limit duplicates identical radial/D blocks into all j
branches and mj values. Real scalar Si supplies an additional artificial
degenerate model compared to the original DFTK nonlocal action on all eight B0
k points. It is not real FR Si and involves no SCF. Real-harmonic and complex/CG
columns have explicit unitary basis relations; their individual columns need not
match. Time reversal uses negative-q pairing and i sigma_y K, including T²=−I.
Spin-only SU(2) invariance is tested only in the synthetic degenerate limit.

## Deferred Phase 6B interfaces

Future integration would need a spinor nonlocal term in Hamiltonian application,
spinor projector/D provenance in the model, and a matching occupied nonlocal
energy callback. Phase 5B's scalar-factor energy bridge only covers spin-independent
spatial operators: spin-off-diagonal SOC contributions must use the full spinor
PDP† expectation, not independent up/down scalar sums. Local/Hartree/charge-only
XC terms and their density ownership require separate integration review.
No such integration, FR SCF, magnetic symmetry or QE SOC alignment is performed
here. All numerical conclusions remain `REVIEW_REQUIRED`.
