# Physical cases and reproduction

| Case | Frozen inputs and commands | Evidence |
| --- | --- | --- |
| Si SR-LDA, two atoms, B0 | [Si baseline](si-sr-lda/README.md) | [Scalar comparison](../results/scalar-si-baseline/README.md) |
| Si C1/C2/C3, limited cutoff/k sensitivity | [Three fixed cases](si-sr-lda/phase4c/README.md) | [Reference and sensitivity](../results/scalar-si-sensitivity/README.md) |
| No-SOC spinor / FR operator / energy fixtures | [Prototype entry points](../scripts/README.md) | [Scientific index](../results/README.md) |
| Mg charge-only SOC and matching QE input | [Parameters](mg-soc-fermi/parameters.json), [QE checklist](mg-soc-fermi/checklist.md) | [A/B SCF](../results/mg-soc-scf/README.md); QE **PREPARED_NOT_EXECUTED** |

The [frozen environment](../environment/workbench/README.md) and recorded UPF hashes
are prerequisites for physical reproduction. UPF bytes are acquired separately
under their licenses. Si uses SR-LDA with NLCC; Mg uses the recorded FR-PBEsol
family and is not an LDA/LSDA numerical benchmark. No case establishes complete
physical convergence. Public offline arithmetic checks require neither UPF
files nor new SCF/QE runs; see [results](../results/README.md).
