# Phase 7E: bound local-potential postprocessing

This finite audit fixes [the plan](plan.json), [build identity](identity.json),
[P2 input](P2.in), [P0 input](P0.in) and [native format](filplot-conventions.md)
before either numerical invocation. Only P2 then P0 are authorized, once each,
in independent ordinary copies of the original G40 save. No new SCF,
eigensolve, independent XC evaluation or parameter scan is permitted.

The original G40 run is `20260907T112107073262Z-G40-3f9731a6`; the DFTK
saved-field producer is `20260907T144446657126Z-8fa3b4d2`. Both are
`HISTORICAL_REUSED`, bound to prior public evidence and verified original
same-machine archives. The raw G40 XML, charge, UPF and complete source tree
remain read-only. Only XML, charge and UPF are required by these pp selections;
the unchanged XML also resolves a same-hash ordinary copy at `pseudo/Mg.upf`.

P2 reconstructs `vltot` through the existing JLL product. Normal pp initialization
can evaluate local, Hartree and XC potentials. This is not extraction of the
historical SCF memory or private `tab_vloc(0)`. The installed binary's exact QE
source commit remains unconfirmed; the official tag documents the conventions.

All 64000 physical nodes and Fourier representatives, including G=0 and
Nyquist, enter the integrals. A is primary and B auxiliary. Raw fields remain
unshifted. Mean subtraction appears only as the explicit diagnostic partition
in the plan; actual electron counts and DFTK mean remain in its G=0 term.
The historical E/F ledger is immutable. Its post-local remainder is a derived
combination, not independently measured QE kinetic/nonlocal energy.

Per-token decimal halfwidths propagate through every relevant mean/integral.
The P0 companion must register at every original node and the fixed 17 complex
modes. Failure blocks same-density interpretation; insufficient print precision
is reported without an additional export. There is no cross-code residual
acceptance threshold. Numerical review remains required; physical convergence
and the historical IEEE warning origin remain unestablished.

Public replay uses complete potential coefficients, native P0/P2 tokens and
the prior density coefficient packs. Its full FFT backend is the existing
NumPy 2.3.5 / Python 3.12.14 environment, explicitly selected by the caller;
the Julia saved-field reader independently uses the frozen DFTK FFTW path.
No package installation or dependency update is part of this task.
