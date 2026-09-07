# Physical cases and reproduction

| Case | Frozen inputs and commands | Evidence |
| --- | --- | --- |
| Si SR-LDA, two atoms, B0 | [Si baseline](si-sr-lda/README.md) | [Scalar comparison](../results/scalar-si-baseline/README.md) |
| Si C1/C2/C3, limited cutoff/k sensitivity | [Three fixed cases](si-sr-lda/phase4c/README.md) | [Reference and sensitivity](../results/scalar-si-sensitivity/README.md) |
| No-SOC spinor / FR operator / energy fixtures | [Prototype entry points](../scripts/README.md) | [Scientific index](../results/README.md) |
| Historical Mg charge-only SOC and prepared QE input | [Parameters](mg-soc-fermi/parameters.json), [QE checklist](mg-soc-fermi/checklist.md) | [A/B SCF](../results/mg-soc-scf/README.md); QE **PREPARED_NOT_EXECUTED** |
| First executed Mg QE SOC comparison | [New fixed case and commands](mg-soc-qe-v1/README.md) | [SCF/refined spectra, E/F and unresolved differences](../results/mg-soc-qe-comparison/README.md) |
| Bounded Mg QE solver/FFT diagnostics | [Six predeclared inputs](mg-soc-qe-diagnostics-v1/README.md) | [Same-density D/C, grid control and IEEE limitations](../results/mg-soc-qe-diagnostics/README.md) |
| Existing Mg density/Hartree audit; no new solves | [Bound source plan, Fourier formulas and gates](mg-soc-density-hartree-v1/README.md) | [Complete coefficients and signed support decomposition](../results/mg-soc-density-hartree/README.md) |

[Phase 7E local-potential plan](mg-soc-qe-local-potential-v1/README.md) fixes
exactly P2 then P0 from independently copied original G40 saves and reads the
bound Phase 7D DFTK local field. Its [results](../results/mg-soc-qe-local-potential/README.md)
separate pp reconstruction, direct integrals and derived ledger remainders.
The completed local claims forbid rerunning either pp slot.

The [frozen environment](../environment/workbench/README.md) and recorded UPF hashes
are prerequisites for physical reproduction. UPF bytes are acquired separately
under their licenses. Si uses SR-LDA with NLCC; Mg uses the recorded FR-PBEsol
family and is not an LDA/LSDA numerical benchmark. No case establishes complete
physical convergence. Public offline arithmetic checks require neither UPF
files nor new SCF/QE runs; see [results](../results/README.md).

## Existing-density energy audit

[Mg fixed-density plan](mg-soc-energy-reference-v1/README.md) binds existing
A/B/G40 sources, five allowed common-term calls and one fixed radial diagnostic.
[Results](../results/mg-soc-energy-reference/README.md) preserve all prior SCFs as
HISTORICAL_REUSED; no new solver, physical setting or dependency is introduced.
