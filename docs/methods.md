# Numerical methods and conventions

The workbench combines two-component orbitals and a fully relativistic,
norm-conserving nonlocal operator with frozen DFTK common terms. The implemented
SCF feedback uses charge density only. This page describes that implementation;
[current capabilities](status.md) separates its validation from the remaining
physical and integration questions.

## Representation, density and occupations

Energies use Hartree and lengths use bohr. An orbital is stored as
`Psi[component, G, state]`, flattened with row
`component + ncomp*(G - 1)`. Each k point has its own plane-wave list. For two
components the order is up, down; scalar component lifting therefore corresponds
to `kron(H_scalar, I_2)` in the flattened layout.

The [FFT adapter](../prototypes/spinor/fft.jl) produces the periodic Bloch part,
with fractional coordinates in the exponential:

$$
u_{kn\sigma}(r)=\Omega^{-1/2}\sum_G c_{kn\sigma G}e^{2\pi iG\cdot r}.
$$

The full Bloch factor is omitted from this transform. Reciprocal normalization
is over **both** components together and equals the real-grid norm with volume
element `basis.dvol`. Kinetic and projector evaluations use the Cartesian
wavevector $q=B(G+k)$, where the reciprocal lattice $B$ includes $2\pi$ once.

For spatial weights $w_k$ summing to one, the
[density accumulator](../prototypes/spinor/density.jl) evaluates

$$
R_{ab}(r)=\sum_{kn}w_k f_{kn}u_{kna}(r)u_{knb}(r)^*,\qquad
n=\operatorname{tr}R,
$$

$$
\boldsymbol m=(2\operatorname{Re}R_{12},-2\operatorname{Im}R_{12},R_{11}-R_{22}).
$$

Spinor states have capacity one: $0\le f_{kn}\le1$ and
$N_e=\sum_{kn}w_k f_{kn}$. There is no extra spin degeneracy factor or separate
normalization of each component. The Pauli density is retained as a diagnostic;
charge-only XC feedback is not magnetic noncollinear XC.

At finite electronic temperature $\tau=k_BT$ in Ha, the
[ensemble layer](../prototypes/soc_scf/ensemble.jl) solves one global chemical
potential for $f_{kn}=[1+\exp((\epsilon_{kn}-\mu)/\tau)]^{-1}$. It does not solve
separate electron counts at each k point or discard small nonzero occupations.

## Relativistic nonlocal operator

The [channel loader](../prototypes/relativistic/channels.jl) binds parsed beta
records to explicit spin-orbit metadata. Source indices are not assumed to be
array positions. Several radial projectors may share $(l,j)$; their Hermitian
coupling matrix may be non-diagonal or indefinite. An association the parser
cannot establish is rejected as unsupported, without declaring every such UPF
physically invalid.

The stored UPF beta array is $b_{\rm raw}(r)=r\beta(r)$. The implemented Hartree
convention uses $b=b_{\rm raw}/2$ and $D=2D_{\rm raw}$, together, with radial transform

$$
F_l(q)=4\pi\int r\,b(r)j_l(qr)\,dr.
$$

Integration uses the actual radial mesh and validated projector support. The
implementation combines $F_l(q)/q^l$ with solid spin-angular functions, so the
origin is evaluated by its finite limit. It does not assign a direction to the
zero vector. Projector columns carry atom, $l,j,m_j$ and radial labels:

$$
P_{\sigma G,a ljm_j\nu}(k)=
\frac{e^{-iq\cdot R_a}}{\sqrt\Omega}(-i)^l
\frac{F_{l\nu}(q)}{q^l}\,\mathcal Y_{ljm_j,\sigma}(q),
\qquad V_{\rm NL}=PDP^\dagger.
$$

Here $\mathcal Y$ is the degree-$l$ solid spin-angular function. The action uses
rectangular products, and its occupied energy is
$E_{\rm NL}=\sum_{kn}w_kf_{kn}\operatorname{Re}(c_{kn}^\dagger PDP^\dagger c_{kn})$.
The [pure matrix implementation](../src/soc_kernels/nonlocal.jl) needs no UPF or
DFTK object. [Historical conventions](../prototypes/relativistic/CONVENTIONS.md)
specify the harmonic/CG phases, ordering and independent ladder-projector and
Gaussian radial references. That document preserves the earlier development
scope; its then-deferred integration is now implemented.

## Common terms and energy bookkeeping

The [integration adapter](../prototypes/fr_integration/hamiltonian.jl) lifts the
scalar common Hamiltonian and adds the FR operator once. It excludes native
scalar nonlocal terms and leaves upstream DFTK's SOC rejection check intact.
The [energy calculation](../prototypes/fr_integration/energy.jl) contains exactly
Kinetic, AtomicLocal, AtomicNonlocalFR, Hartree, Xc, Ewald and PspCorrection.
Common terms use the two orbital components as spatial factors; they do not
refill them as independent scalar states. Native NLCC is included once in XC,
including the full GGA contribution; Hartree uses valence charge.

The [local-potential adapter](../prototypes/fr_integration/common_data.jl)
converts UPF local potentials from Ry to Ha. Its $G=0$ local coefficient is zero;
the finite radial term is accounted for separately:

$$
\alpha_s=4\pi\int[r^2V_{\rm loc,s}^{\rm Ha}(r)+Z_s r]dr,
\qquad E_{\rm PspCorrection}=N_e\frac{\sum_a\alpha_{s(a)}}{\Omega}.
$$

This correction contributes to energy, not the Hamiltonian action. It is not an
empirical shift to apply again to total energies or spectra. The
[energy-reference audit](../results/mg-soc-energy-reference/README.md) records the conventions
and limits of cross-code comparisons.

Writing $s=S/k_B=-\sum_{kn}w_k[f\ln f+(1-f)\ln(1-f)]$, the free energy is
$F=E-\tau s$. The [SCF controller](../prototypes/soc_scf/scf.jl) distinguishes
$H[n_{\rm in}]$ eigenvalues, orbital density $n_{\rm out}$, and energy evaluated
from those orbitals. Final closure and fixed-potential spectra retain their
actual density/occupation bindings; an eigenvalue sum is not the total energy.

## Controls and interpretation

The [spin-trace control](../prototypes/crystal_soc/SpinTrace.jl) replaces only the
nonlocal term by two identical spin blocks of
$W=(P_\uparrow DP_\uparrow^\dagger+P_\downarrow DP_\downarrow^\dagger)/2$ at the
same density. It retains both radial/j branches. This is a diagnostic, not an
independent scalar-pseudopotential SCF calculation. Time reversal uses
$i\sigma_yK$ with $k\mapsto-k$; full SOC need not commute with a spin-only rotation.
For actual Si spectra, consult the
[occupation and manifold interpretation](../results/si-soc-splitting/status-correction/README.md)
alongside the fixed-window splitting comparisons.
