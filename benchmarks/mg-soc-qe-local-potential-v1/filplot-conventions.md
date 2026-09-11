# Restricted QE 7.5 filplot contract

The parser implements a file format, not a translation of QE's numerical
algorithms. These references describe the official `qe-7.5` tag; they do not
establish the installed executable's exact source commit. Executable, JLL,
artifact and historical-input bindings belong to the run receipts.

## Native record layout

[The tagged writer](https://github.com/QEF/q-e/blob/qe-7.5/Modules/plot_io.f90#L55-L68)
emits a title (possibly blank), eight integers
`nr1x nr2x nr3x nr1 nr2 nr3 nat ntyp`, then `ibrav` and six `celldm`
values. For `ibrav=0`, the next three lines are **columns** `at(:,i)`.
Next come `gcutm dual ecut plot_num`, indexed species with valence charge,
and indexed atoms with three `tau` components and species index. Header
formats include `F16.8` for `celldm`, `F20.10` for the cutoffs, `F5.2`
for valence charge and `F15.9` for atom positions; the lattice columns use
list-directed output.

The payload format is `5(1pe17.9)`, containing exactly
`nr1x * nr2x * nr3` values. The final allocation dimension `nr3x` does
not extend the file payload. The parser checks every token, then removes
only first/second-axis padding. Physical zero-based index `(i,j,k)` maps to
`i + nr1x*(j + nr2x*k)`; the first index is fastest. The
[native array indexing](https://github.com/QEF/q-e/blob/qe-7.5/PP/src/wfck2r.f90#L243-L250)
and [grid origin/periodicity handling](https://github.com/QEF/q-e/blob/qe-7.5/PP/src/chdens_module.f90#L1130-L1189)
support the physical coordinates `(i/nr1,j/nr2,k/nr3)`. No repeated endpoint
is integrated; endpoint extension is a separate plotting operation.

The [restart reader](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/pw_restart_new.f90#L1270-L1280)
normalizes both `at` and `tau` by `alat`, with `alat=celldm(1)` in bohr.
Thus lattice columns and Cartesian atom positions are respectively
`alat*at(:,i)` and `alat*tau(:,atom)`. Printed header intervals are checked
against the bound high-precision XML geometry. Integration uses that XML
geometry, not the rounded header determinant. An arithmetic allowance of
eight Float64 ulps of the expected component covers XML product rounding;
it is not added to the reported print interval.

## Quantities and reconstruction scope

[INPUT_PP](https://www.quantum-espresso.org/Doc/INPUT_PP.html#idm29) defines
potentials in Rydberg energy units and densities integrating to electron
number. The [selected branches](https://github.com/QEF/q-e/blob/qe-7.5/PP/src/punch_plot.f90#L73-L107)
take `rho%of_r(:,1)` for plot 0 and `vltot` for plot 2. The former is
electron/bohr³ without a spin or k-point factor; the latter is converted
from Ry to Ha exactly once, by division by two. The requested plot 0
uses `spin_component=0`; that request is bound by its input receipt because
filplot does not contain a spin-component field.

[postproc](https://github.com/QEF/q-e/blob/qe-7.5/PP/src/postproc.f90#L161-L169)
does not require wavefunctions for these two selections.
[read_file_new/post_xml_init](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/read_file_new.f90#L184-L402)
reads XML, re-reads UPF, restores charge, and rebuilds local/core and HXC
potentials. [init_vloc](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/init_vloc.f90#L43-L71)
recreates the local-potential tables;
[setlocal](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/setlocal.f90#L67-L96)
assembles the ionic potential including its native zero mode. Consequently
the status is `QE_PP_RECONSTRUCTION_BOUND_TO_HISTORICAL_G40`, not an
extraction of G40's historical in-memory field or private `tab_vloc(0)`.
Normal postprocessing potential/XC work is included in this scope.

## Decimal evidence and restrictions

For a token with exponent `e` and `d` digits after the decimal point, its
nearest-rounding halfwidth is `0.5 * 10^(e-d)`, independent of its sign.
This also applies to zero, E/D exponents and header tokens. Raw spellings
are retained, and potential halfwidths receive the same `/2` conversion.
These intervals describe output quantization only, not reconstruction,
Fourier truncation, floating-point or physical error. Shared-potential
uncertainties must be propagated with their correlations intact downstream.

Only explicit `ibrav=0`, plot 0/2, finite tokens and bounded dimensions are
supported. Missing/extra fields, malformed numeric data, duplicated indices,
unsupported geometry and mismatched requested headers fail explicitly.
Format success alone establishes neither historical provenance nor P0
pointwise registration. Synthetic fixtures exercise a sheared noncubic
cell, padding, a nonzero mean and complex Fourier phases; they are not
physical QE runs or usable pseudopotentials.
