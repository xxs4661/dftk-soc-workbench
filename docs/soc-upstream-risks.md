# Open integration questions

This is a separate experimental workbench using frozen DFTK and PseudoPotentialIO
checkouts. It has completed Mg/Si calculations and a real Si regression through
its reusable core. It has not added an official DFTK SOC API or obtained an
upstream architecture decision. The original DFTK SOC constructor guard remains
in place. The [methods](methods.md) and [runtime interface](soc-core-runtime.md)
describe the implementation that exists today.

| Integration area | Current constraint | Question for future design work |
| --- | --- | --- |
| Wavefunction and density representation | Explicit spinor flattening; scalar DFTK density bridge carries charge only. | How should public wavefunction, occupation and noncollinear density interfaces relate? |
| Pseudopotential data | FR channels and common NC/NLCC data are bound to one source using workbench authentication and registries. | Which common data, parsing and ownership contracts belong in a native interface? |
| Numerical ownership | Copied kernel inputs, mutable reusable workspaces and an owned runtime session separate source validation from repeated actions. | How should cache lifetimes, concurrency and solver ownership fit the host execution model? |
| Types and devices | Validated CPU Float64/ComplexF64 path; no established AD/GPU support. | Which operations and mutations need different abstractions for other number types or devices? |
| Solver integration | Prescribed SCF/FD contracts and case-bound drivers, with no arbitrary-material API. | Which parts can be separated from research orchestration without losing validation? |
| Resource and accuracy validation | Static allocation reductions and Si endpoint equivalence are measured; timing remains under review and K6 memory is not bounded. | What representative workloads and error contracts should gate a broader implementation? |

Magnetic noncollinear XC, forces/stress and USPP/PAW need their own mathematical
and numerical work. Existing SOC agreement and small internal regression errors
do not establish these capabilities. No change of physical formula or upstream
source is implied by this list.

The [SOC RFC](../rfc/soc-v1.md) is a historical proposal; use the
[history index](history.md) to distinguish its scope from later implementation.
Any upstream discussion, implementation proposal or publication is a separate
human decision. No maintainer endorsement is claimed.
