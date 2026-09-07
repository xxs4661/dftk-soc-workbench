# Local-potential finite reference and quadrature conventions

This is a bounded audit of the same hash-bound Mg UPF, not a new potential or an
adjustment to historical E/F. No QE local-potential array or runtime table is
extracted. QE source statements below describe the **qe-7.5 tag**; the installed
binary's exact source commit remains unconfirmed.

## Data and units

The source lock identifies `.work/pseudos/Mg.upf`, SHA-256
`19b117bfa920945bffaee91eefbcfbf9fd44e035f3708b965aae59aabf3be256`.
Read-only metadata inspection before numerical evaluation found 1510 points,
`PP_R=0,0.01,...,15.09` bohr and `PP_RAB=0.01` throughout. The header says Mg,
NC, full relativistic, has_so=true, Z=10, PBESOL, no core correction. These
metadata do not constitute a newly executed finite integral.

The [UPF specification](https://pseudopotentials.quantum-espresso.org/home/unified-pseudopotential-format)
assigns bohr to radii and Ry to `PP_LOCAL`; `PP_RAB` is the index-coordinate
integration Jacobian. The limited reader verifies the original SHA before XML
parsing, declared/actual sizes, strictly increasing radii, positive Jacobians
and finite values. Raw UPF/radial arrays are not published.

Use `V_Ha=PP_LOCAL/2` once and form the finite integrand
`f(r)=r² V_Ha(r)+Zr`. Integrate this combined finite quantity; do not integrate
the divergent Coulomb Fourier zero mode separately. `alpha=4π∫f(r)dr` has units
Ha bohr³, `C=nat*alpha/Omega` has units Ha, and the neutral-model bookkeeping
candidate is `Pc=N_e*C`. The cell/atom/electron factors are independently tested.

## Frozen DFTK path and independent r-space rule

The locked [PspUpf input conversion](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/pseudo/PspUpf.jl#L110-L119)
divides the local samples by two. Its [local Fourier evaluator](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/pseudo/PspUpf.jl#L229-L242)
sets G=0 to zero. The separate [finite correction](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/pseudo/PspUpf.jl#L308-L315)
uses the supplied local radial range, and [PspCorrection](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/terms/psp_correction.jl#L26-L35)
multiplies the atom-summed finite term by the electron count from atoms divided
by cell volume. The unchanged workbench [common adapter](../../prototypes/fr_integration/common_data.jl)
uses its full local grid, independently of beta cutoff, and evaluates the same
frozen correction rule. The new Julia receipt records the actual constants.

The independent Python route integrates the unique quadratic interpolant on
successive triples of actual r nodes. It uses Newton divided differences and
integrates that polynomial analytically. When one final interval remains, its
trapezoid is used, as predeclared in the plan. The second diagnostic is the
composite trapezoid over **all** native intervals. Neither r-space rule multiplies
by PP_RAB: interval lengths already supply dr. No equally spaced formula is
applied blindly to nonuniform r. No node is resampled or removed.

The full integral ends at r=15.09 bohr, not a projector cutoff. Endpoint and tail
integrand diagnostics are saved; the finite-part interpretation outside the
provided range assumes the Coulomb tail. No tail patch is added. The two fixed
rules' difference is method sensitivity, **not a strict error bound**.

## Conditional QE tagged G=0 prediction

The [UPF reader](https://github.com/QEF/q-e/blob/qe-7.5/upflib/read_upf_new.f90#L263-L275)
and [internal grid adapter](https://github.com/QEF/q-e/blob/qe-7.5/upflib/upf_to_internal.f90#L40-L43)
preserve the actual r/rab samples. [read_pseudo](https://github.com/QEF/q-e/blob/qe-7.5/Modules/read_pseudo.f90#L174-L188)
selects the first radius greater than 10 bohr, then limits the selected one-based
node count to an odd value. In these actual arrays the first such index is 1002
(r=10.01); the resulting tagged `msh` is **1001**, including r=0 through r=10.00.
This is a source-and-data-derived range, not a fitted choice or a radius scan.

Only after ordinary periodic/unmodified Coulomb conditions are certified, the
third route applies the standard odd-node Simpson weights to `f_i*PP_RAB_i` on
those 1001 nodes. [The tagged Simpson interface](https://github.com/QEF/q-e/blob/qe-7.5/upflib/simpsn.f90#L13-L44)
supplies the Jacobian once and closed endpoint weights 1/3. The actual affine
r grid and matching PP_RAB must pass independent checks. Unsupported grid
families receive NOT_ESTABLISHED rather than a guessed Jacobian interpretation.
This is a standard quadrature implementation, not a translation of QE kernels.

The ordinary periodic [G=0 table entry](https://github.com/QEF/q-e/blob/qe-7.5/upflib/vloc_mod.f90#L150-L164)
is the **unscreened** finite alpha/Omega, initially in Ry. By contrast, the
[short-range q→0 entry](https://github.com/QEF/q-e/blob/qe-7.5/upflib/vloc_mod.f90#L131-L147)
uses `r²V+Z*r*erf(r)` in Ha notation. They are different objects: over 0..∞,
`alpha_unscreened-alpha_screened=4πZ∫r*erfc(r)dr=πZ` for this unit-erf convention.
The synthetic tests distinguish them; no extra real-UPF screened integral is
performed. [Interpolation selects the finite G=0 entry directly](https://github.com/QEF/q-e/blob/qe-7.5/upflib/vloc_mod.f90#L199-L207).
The [caller](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/init_vloc.f90#L41-L70)
distinguishes ordinary periodic from ESM/2D-modified Coulomb cases. No nonzero-G
interpolation table is implemented or scanned here.

`N_e*(C_D-C_Q_pred)` may be reported as a signed convention/quadrature candidate.
It is not a runtime measurement or causal proof and is never added to or
subtracted from stored E/F. `Lbar_D=AtomicLocal_D+Pc_D` is a named bookkeeping
combination, not an extra term to add a second time. The synthetic gauge test
uses V→V+c, L→L+N*c and Pc→Pc−N*c to verify this distinction.

The Python-only public checker can replay saved scalar bookkeeping, not rerun
these radial integrals from hashes. Re-execution requires obtaining the exact
source-locked UPF locally. The full new radial/field outputs stay in the local
incremental archive, with no claim of offsite backup.
