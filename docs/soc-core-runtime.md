# Optional scoped SOC runtime

`FRIntegration.owned_runtime(ctx; max_rhs=30)` consumes a freshly issued legacy
context after its existing source, atom, k/G/FFT, P/D, XC and common-term checks.
The original context and pseudopotential types remain unchanged. Existing calls
continue to use the legacy implementation unless this conversion is requested.

The runtime owns the original rectangular P/D data and one maximum-size serial
workspace. It never keeps a second all-k P set. Source and context certificates
move from the old strong global registries into the runtime; another legacy
context sharing the same source prevents transfer. No runtime, Hamiltonian or
density is registered globally. `runtime_fr_blocks(rt)` provides core-action
handles; `rt.fr_blocks` continues to identify the original issued objects for
strict certificate checks.

The numerical module `SOCKernels` receives matrices, layouts, weights,
occupations and workspace storage. It performs no source discovery, Git/file
access or Serialization. The adapter performs deep validation at conversion,
map/solver/callback boundaries, density and potential replacement, final output
and close. `runtime_boundary!(rt, event; ham=nothing)` checks original certificates
and actual kinetic, local, Hartree, core and current Hamiltonian storage, including
Fourier multipliers. A replaced potential increments the generation and invalidates
old Hamiltonian handles. Per-action checks cover live generation, local dimensions,
aliasing and finite inputs/scales; they do not traverse all k points or registries.

Runtime storage is private by API convention, not a Julia memory security
sandbox. During a numerical scope, callers must not mutate or retain writable
borrowed aliases or make nested/concurrent calls. Sequential outside mutation is
rejected at the next declared boundary. Callbacks execute at explicit boundaries;
the SCF adapter also checks exposed numerical payloads. The source arrays and
physical formulas are never repaired, clipped, symmetrized or renormalized.

The full action stages common and FR products in two shared buffers, then uses
the original `alpha*(common + FR) + beta*Y` order. It writes Y only after the
complete finite-value check and does not read Y when beta is zero. Buffer capacity
is shared across k points and 1/24/30 RHS requests, and its full cost belongs in
the memory measurement. The FFT adapter lends its density accumulator only
within the adapter call; public/SCF R/n/m results are copied into independent
owned arrays. The second density recovery in the energy evaluation and all seven
energy terms and independent nonlocal decomposition checks remain present.

Use `close_runtime!(rt)` in a `finally` block. Close checks the final boundary and
unconditionally clears the owned context, certificates, Hamiltonian references and
workspace, including when that check fails. It is idempotent. A failed close is an
error, even though cleanup completes; preserve the original callback/worker cause
if another exception was already being handled. Keep only `runtime_summary(rt)`
and canonical plain numerical arrays in records and checkpoints, never runtime,
Hamiltonian, certificate or workspace objects.

This interface description makes no performance or scientific-equivalence claim.
Those require the separate fixed-base REF, candidate CORE, and authorized B0
execution records. Synthetic/static interface tests are not new physical SCF or
upstream DFTK tests. The legacy historical scientific limits remain unchanged.
