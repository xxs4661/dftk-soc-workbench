# Fixed-density energy reference audit

This plan was saved before the new evaluations. [plan.json](plan.json) binds the
accepted base, historical files, physical settings, evaluation budget and gates.
[Energy conventions](energy-conventions.md) and [local reference conventions](local-reference-conventions.md)
define the source interpretation. A original n_out is primary; B is auxiliary;
G40 is the original successful QE SCF. All three SCFs are HISTORICAL_REUSED.
New values are NEW_POSTPROCESSING_OF_HISTORICAL_STATES.

The three primary inputs are A original n_out, B original n_out, and the complete
saved QE finite Fourier series evaluated on the original zero-origin 40³ grid.
A/B public-series reconstructions receive one additional same-source evaluation
each. Five XC calls maximum; no new SCF, eigensolve, occupancy update, QE/pp.x
numerical execution, wavefunction analysis or parameter scan.

The frozen [common adapter](../../prototypes/fr_integration/common_data.jl)
provides the same Mg local data. Construct only the static basis and AtomicLocal,
Xc, Ewald and PspCorrection objects. Do not invoke build_context, a complete
Hamiltonian, or energy_snapshot(X,f). In the fixed
[DFTK XC source](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/terms/xc.jl),
xc_potential_real includes Vρ minus the GGA divergence term. Record the actual
DispatchFunctional backend, versions, external parameters and thresholds before
interpreting output; the name LibxcDensities alone does not identify dispatch.
For the frozen CPU Float64 path the dispatch is expected to select Libxc; verify
it in the new process. Gradients use the existing full-grid iG FFT and real-part
inverse convention, including native Nyquist treatment. No threshold is changed.

Authenticate A/B checkpoint bytes, Julia production version and the frozen
Phase 7C prior binding before Julia Serialization deserialization. Only density
and required metadata are accessed. Check the public gzip byte hashes before
lossless decompression; bind the decompressed transfer independently. Keep complex
inverse transforms until imaginary, Fourier roundtrip, phase-point and electron
count gates pass. Record original support, full real-space range and negative
counts. Zero-initialized FFT storage evaluates the explicit finite series; it
does not prove unsaved physical modes vanish or independently recover QE's native
real-space array. Preserve the earlier NOT_ASSESSED statement in its own scope.

Use native historical Hartree in the complete signed energy ledger. Keep the
Phase 7C reconstruction roundoff separate. Split historical XC differences into
the DFTK density response and the residual at Q_rep; report the latter's remaining
representation/backend limits. Use full GGA vxc for Ixc and the first-order
response; never replace it by Vρ. Report actual ΔN without subtracting means.

DFTK native local G=0 is zero; Pc is separately counted once. L+Pc is only a
bookkeeping combination. Local density response is checked both on the real grid
and through the full complex Fourier inner product, with the same native DFTK
field. No authenticated QE local-potential array is available: NOT_EXTRACTED.
Separate QE kinetic/nonlocal values are NOT_AVAILABLE; the residual remains a
signed derived combination, not a measured SOC error.

Only one fixed radial diagnostic is allowed: the original full-grid DFTK Pc,
independent piecewise nonuniform quadratic integration (last unmatched interval
trapezoid), and full-grid trapezoid sensitivity. A conditional tagged-QE
Jacobian Simpson prediction requires proven range and endpoint semantics;
finite alpha must not be confused with a screened short-range q→0 table value.
Differences are diagnostics, not rigorous error bounds or empirical corrections.

Public evidence references existing endpoints, G40 and full Fourier packs.
New potential/gradient arrays and full process records remain local and in a
verified incremental archive. Python replay checks source hashes, saved tables,
signed algebra and declared gates; it does not independently execute XC or
recompute new field inner products without their local arrays. Re-evaluation
requires the frozen Julia environment and exact authenticated private inputs.
No full historical backup or environment rebuild is part of this task.
