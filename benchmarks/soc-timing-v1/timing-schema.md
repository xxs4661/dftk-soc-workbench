# Timing boundaries (schema 1)

Timing is off by default (`diagnostics=nothing`). The short diagnostic driver
explicitly enables it only for T-B0-TIMED and T-K4-TIMED. Observations contain
scalars, identifiers and strings, never Hamiltonians, orbitals or density arrays.

Julia spans use the local `time_ns()` origin; parent supervision uses Python
monotonic elapsed time and independently checks elapsed UTC for conservative
deadlines across machine sleep. Their raw counter origins are never subtracted.
UTC timestamps associate processes and requests, not nested span arithmetic.
The actual tested interpreters are Julia 1.12.7 and Python 3.12.14.

Each row records run_id, pid, span_id, parent_span (0 means no parent), name,
map_index (0 outside a map), k_index (0 outside a k solve), start_offset_ns,
end_offset_ns, inclusive_ns, exclusive_ns, calls and status. Self time subtracts
only direct serial children. Never sum an inclusive parent with its children.
COMPLETE, DIAGNOSTIC_COMPLETED, STOPPED and ERROR spans have observed ends.
DIAGNOSTIC_COMPLETED records the exact two-map stop, not SCF convergence.
A missing end after process
termination is incomplete/truncated; no zero duration may be substituted.

`map_total` begins before controller density checks and ends after the map,
residual/mixing and output callback (or while propagating its stop/error).
`map_compute` includes the actual SOC map. `hamiltonian_build`,
`orbital_density`, `energy_snapshot`, `thermal_energy_checks` and
`self_density_closure_checks` retain the actual nested work, including repeated
H/density evaluation inside the existing energy function. This instrumentation
does not separately isolate every Hartree/XC/native-library operation.

`k_total` covers initial subspace/QR/preconditioner, the guarded eigensolver,
explicit Hx/residual/Gram checks and guarded progress/checkpoint output. Boundary
and callback fingerprint spans distinguish checks from the guarded body.
`global_fd_tail_check` covers the global ensemble and band completeness checks.
Output spans measure serialization/buffering and write calls; absent an fsync
measurement these are not physical disk flush latencies. Scalar timing batches
are written at safe boundaries, outside matvecs. Output overhead and untimed
process/driver portions must remain explicit in the result rather than being
assigned to GC, I/O or hashing by subtraction.

The old per-k `elapsed_seconds` expression remains in its original position:
after initial subspace/preconditioner setup, before guarded LOBPCG, through the
explicit eigen checks and early record fields. It excludes the subsequent Gram
field, callback guards and saves. It is inclusive and uses historical `time()`;
it is not a pure solver timer and is not added to the new spans.

Startup/loading/context, first map, subsequent map and shutdown are separate.
Map 2 is not asserted fully warm. REF has no segmented numerical spans. A pair
of cold processes cannot establish statistical instrumentation overhead, and
these B0/K4 proportions cannot reconstruct the old K6 uninstrumented time.

Technical behavior checked against the local interpreter and official references:
[Julia time_ns](https://docs.julialang.org/en/v1/base/base/#Base.time_ns),
[Julia script SIGINT](https://docs.julialang.org/en/v1/base/c/#Base.exit_on_sigint),
[Python process exits](https://docs.python.org/3.12/library/subprocess.html),
[Python monotonic clocks](https://docs.python.org/3.12/library/time.html).
No sampling/allocation profiler or forced collection is used; the distinction
from profiling is described in the [Julia manual](https://docs.julialang.org/en/v1/manual/profile/).
