# Original-wavefunction energy audit

**PASS for the declared finite static audit; REVIEW_REQUIRED for scientific
interpretation.** One new postprocessing run
`20260907T173343831194Z-80727713` used only the original G40 SCF wavefunctions
and original A/B checkpoints. No new SCF, eigen/occupation solve, QE/pp or XC
was executed. Historical E/F and frozen scientific code are unchanged.

Read the [review](../phase7f-review.md), [source/formula plan](../../benchmarks/mg-soc-wavefunction-energy-v1/README.md),
[execution receipt](execution.json), [checks](state-checks.json),
[nonlocal contractions](nonlocal-checks.json) and [signed comparison](comparison.json).
The [evidence manifest](evidence.json) binds all numerical files and the executed
code. Previous density, P2 and energy evidence is referenced by path/hash.

| Quantity, Ha/cell | A | B | Original Q (G40) |
| --- | ---: | ---: | ---: |
| Direct original-orbital kinetic | 29.075984450811465 | 29.07598445081151 | 29.07598791063465 |
| Frozen workbench FR expectation | -14.214054510747257 | -14.214054510747609 | -14.214055437803232 |
| T minus original A/B T | -3.553e-15 | -3.553e-15 | No independent native QE T field |
| FR minus original A/B FR | 0 | +1.776e-15 | **Not native QE NL** |

Q restores all 22119 saved density coefficients (max5.2042e-18 e/bohr³,
nonzero relative L2 4.5225e-16). All 21421 possible same-k orbital product
modes lie inside that saved support and fit 40³ without Nyquist ambiguity.
This establishes the complete **finite orbital-product representation**, not
unknown physical Fourier content outside the calculation. The direct kinetic
and covariant-gradient integral differ by1.066e-14 Ha. A/B n_out max node errors
are1.333e-15 e/bohr³; all original 24 bands and occupations are retained.

For A−Q, ΔT=-0.094146585 meV/cell and ΔN_D=+0.025226478 meV/cell,
so the same-evaluator orbital/occupation response is−0.068920107 meV/cell.
The cross-source combination J_Q=+4.1404e-10 Ha has token-print halfwidth
1.91369e-8 Ha. The local saved-versus-orbital-density integral differs at
Float64 roundoff scale. Explicit same-source and historical grouping drifts
recompose the original Phase7E remainder to8.01e-15 Ha. Tiny J is neither a
direct native-QE-NL measurement nor identification of a scientific bug.

## Public numerical representation

- [qe-orbitals.npz](qe-orbitals.npz): complete original three-k/24-state Q
  coefficients, native G, f, eigenvalues, weights, physical k and lattice.
  Each `kN_coefficients` has shape `(2,NG,24)`: up/down, native G row, band.
  `kN_millers` is `(NG,3)`; matrices named `*_columns` contain vectors as columns.
- [nonlocal-operator.npz](nonlocal-operator.npz): one rectangular P per k in
  authenticated A G order, interleaved spin rows `(up_G1,down_G1,up_G2,...)`,
  common full16×16 D, native integer G and per-state up/down amplitudes.
  All16 radial/angular columns, off-diagonal D and spin interference are retained;
  column labels and channel metadata are in `nonlocal-checks.json`.
- Both use fixed little-endian Float64/ComplexF64/Int64, C-order expanded-byte
  hashes, lossless compression and `allow_pickle=False`. Compressed numerical
  payload totals8,638,331 bytes. No raw native WFC/UPF/A/B X is published.

The public checker replays Q norm/Gram, density, 17 independent coefficient
correlations, direct/gradient T, the Miller permutation, P/D action and complex
projected contractions. A/B source X extraction and original-density/T recovery
remain **RUNNER_REPORTED**; their published per-state scalar sums and projected
contractions are replayed. Recreating P from the UPF is a different test requiring
the exact separately acquired UPF and frozen Julia checkout. Neither hashes alone
nor public projected amplitudes reconstruct private A/B X.

```sh
python_numpy scripts/check_orbital_energy.py --all --legacy-python python3.9
```

Use an existing NumPy runtime (tested Python3.12.14/NumPy2.3.5); no installation,
network, private data, .work or Julia is needed for public replay. Historical
scalar arithmetic retains its recorded Python3.9 behavior. To reproduce the new
measurement layer, restore only the bound historical files to the relative paths
in the plan, acquire the locked checkout/UPF and use the frozen Julia environment:

```sh
JULIA_LOAD_PATH=@:@stdlib JULIA_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python_numpy scripts/run_orbital_energy_audit.py --julia julia
```

Set JULIA_DEPOT_PATH to the existing locked package cache when required. The
runner creates a unique ignored run and refuses missing/mismatched sources.
It never replaces missing originals with a new calculation. Review the explicit
public-file whitelist before publication; complete raw/transfer/process evidence
is held in a verified repository-external same-machine archive, not offsite.

**NOT_MEASURED:** independent native QE NL. **NOT_AVAILABLE:** original Q
H[n_in] residual. **NOT_ESTABLISHED:** physical convergence and causal attribution.
**NOT_LOCALIZED:** IEEE origin. The two P2/P0 calls belong to historical Phase7E,
not this phase. Stop for review; no next scientific stage has started.
