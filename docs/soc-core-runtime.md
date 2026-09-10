# Core interfaces and runtime ownership

[`SOCKernels`](../src/SOCKernels.jl) is a serial CPU module for matrix actions,
expectations and density accumulation. Include the file directly; it is not a
registered package. The complete [synthetic example](../examples/soc_kernels.jl)
runs with Julia's standard library:

```sh
julia --startup-file=no --project=@stdlib examples/soc_kernels.jl
```

The core takes arrays and explicit workspaces, with no source discovery, UPF
parsing, Git/file access or checkpoint serialization. The DFTK adapter supplies
identity checks. [Methods](methods.md) defines the physical conventions.

## Matrix actions and expectations

After including the module and `using .SOCKernels`, these interfaces are available.
`X` has orbital columns, `f` one occupation per column, and `weight` one spatial
k-point weight.

| Interface | Contract |
| --- | --- |
| `NonlocalData(P, D; labels=nothing)` | Copies rectangular P, Hermitian column-space D and optional column labels. |
| `NonlocalWorkspace(max_rows, max_projectors, max_rhs)` | Two projector-space buffers and one staged output buffer. |
| `nonlocal_action!(Y, data, X, ws, alpha=1, beta=0)` | `Y = alpha * P * D * P' * X + beta * Y`; another overload takes P, D separately. |
| `nonlocal_expectation(data, X, f, weight, ws)` | Occupied expectation from full-space action. |
| `projected_nonlocal_energy(data, X, f, weight, ws; initial_total=0.0)` | Projector-space expectation; carry-in preserves ordered accumulation across k points. |
| `ComponentWorkspace(max_ng, max_rhs, ncomp)` | Contiguous component scratch and staged interleaved output. |
| `component_action!(Y, scalar_mul!, X, ncomp, ws, alpha=1, beta=0)` | Same scalar callback for each component, row `component+ncomp*(G-1)`. |
| `workspace_stats(ws)` / `reset_workspace_counters!(ws)` | Inspect/reset counters without changing numerical data. |

Actions accept finite `Float64`/`ComplexF64` input and `ComplexF64` output, as
vectors or matrices. Capacities are positive and fixed: active RHS counts such
as 30 → 1 → 24 can reuse scratch; exceeding capacity fails. D can be indefinite
and non-diagonal and is never symmetrized. Nonlocal expectations use finite
capacity-one occupations and nonnegative spatial weight.

Output must not alias inputs, operator storage or scratch. Actions stage and
validate before copying to Y; shape/alias/nonfinite/overflow failures leave Y
unchanged. With beta zero, old Y is not read. Scratch may be partially changed.

`scalar_mul!(output, input)` is a trusted synchronous callback: fill every
output, preserve input, retain no scratch aliases. The caller protects scalar
operator/external state; callback side effects are outside the core's protection.
Workspaces permit no nested or concurrent use. Owned Julia arrays remain mutable.

## Density and FFT storage

`DensityWorkspace(ncomp, nr)` supports scalar (one component, capacity two) or
spinor (two components, capacity one) density. Generic component lifting permits
other component counts; that does not extend density physics.

Use `reset_density!(ws)`, then `accumulate_density!(ws, u, weight, f)` on
(component, grid, state) arrays, then `finish_density!(ws)`. Returned R/n/m
arrays **borrow workspace storage** until reset/reuse; m is `nothing` for scalar
density. Copy retained results. Failure invalidates the accumulation until reset.
`validate_weights(weights, nk)` checks the spatial sum; nothing renormalizes
weights or solves occupations.

The DFTK-backed
[`SpinorPrototype.OrbitalDensityWorkspace`](../prototypes/spinor/fft.jl) takes
`(max_ng, nr, fft_size, ncomp=2)` and transforms one physical state at a time.
`SpinorPrototype.orbital_density!(ws, basis, X, weights, f)` uses actual k/G/FFT
mappings and also returns borrowed arrays. In contrast,
`FRIntegration.context_orbital_density(rt, X, f)` copies them for independent
SCF/energy results.

## DFTK integration runtime

[`FRIntegration.owned_runtime(ctx; max_rhs=30)`](../prototypes/fr_integration/runtime.jl)
is opt-in conversion of a freshly issued, validated integration context, not a
general material loader or SOC SCF entry. Legacy types/default dispatch remain.

The runtime owns issued P/D data and certificates with one maximum serial
workspace across k points, without a second all-k P set or global runtime/H/density
registry. Transfer fails when another legacy context shares its source.
`runtime_fr_blocks(rt)` returns core-action handles.

`runtime_boundary!(rt, event; ham=nothing)` checks source/context certificates,
grid, common storage and current H at explicit boundaries. Actions check live
generation, dimensions, aliasing and finiteness. A replaced potential invalidates
old H handles. Do not mutate or retain writable borrowed storage within a scope.
The full H stages common and FR actions in two shared buffers before publishing
`alpha*(common + FR) + beta*Y`.

Call `close_runtime!(rt)` in `finally`. It validates the final boundary and clears
context, certificates, H references and scratch even on failure; repeated close
is safe. Retain cleanup errors and any earlier execution cause. Save only
`runtime_summary(rt)` and owned numerical arrays in records/checkpoints.

[Allocation measurements](../results/soc-core-memory/README.md) and
[real Si SCF/Γ regression](../results/soc-core-memory/completion/README.md)
support those measured cases. They do not establish overall speedup, complete
native-memory bounds or DFTK K6/K8 feasibility.
