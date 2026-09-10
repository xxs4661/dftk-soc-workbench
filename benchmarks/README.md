# Physical cases and reproduction

- [SOC core continuation](soc-core-memory-v1/resume/README.md): unchanged Si B0
  inputs, explicit static inheritance and once-only SCF attempt 2 / Gamma attempt 1.
  [Both new endpoints and original regression gates passed](../results/soc-core-memory/completion/README.md).
  Performance remains HISTORICAL_REUSED and time/K6/physical review limits remain;
  clean public-clone replay returned 0/0; incremental archive restore verified 185/185 files. The original core-memory
  case summary below retains its earlier partial-delivery scope.


- [SOC core memory v1](soc-core-memory-v1/README.md): authenticated historical B0/K4 static pairs passed; the sole new B0 attempt failed at parser entry and Gamma is blocked; [current status](../results/soc-core-memory/README.md).

- [Si QE k-grid reference](si-soc-k-reference-v1/README.md): frozen K6/K8 inputs and four-slot plan; [current status](../results/si-soc-k-reference/README.md). Four prescribed QE slots completed once; finite trends and limits are in the linked result. No new DFTK context or worker.

- [mg-soc-public-replay-v1](mg-soc-public-replay-v1/README.md): executed fixed Linux public replay; **I PASS/0, R FAIL/1** for predeclared density fingerprints, CI failure retained; [results](../results/mg-soc-public-replay/linux/README.md).
- [mg-soc-wavefunction-energy-v1](mg-soc-wavefunction-energy-v1/README.md): original G40/A/B static audit; plan and fixed engineering gates; no new SCF/QE/XC.

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
under their licenses. The historical scalar Si case uses SR-LDA with NLCC; the new Si SOC case
uses its separately authenticated FR-NC-PBE source and NLCC. Mg uses the recorded FR-PBEsol
family and is not an LDA/LSDA numerical benchmark. No case establishes complete
physical convergence. Public offline arithmetic checks require neither UPF
files nor new SCF/QE runs; see [results](../results/README.md).

## Existing-density energy audit

[Mg fixed-density plan](mg-soc-energy-reference-v1/README.md) binds existing
A/B/G40 sources, five allowed common-term calls and one fixed radial diagnostic.
[Results](../results/mg-soc-energy-reference/README.md) preserve all prior SCFs as
HISTORICAL_REUSED; no new solver, physical setting or dependency is introduced.

- [Si SOC splitting v1](si-soc-splitting-v1/README.md): authenticated source and fixed five-slot matrix, now executed once each with numerical splitting/null gates passing and explicit review limitations; [current results](../results/si-soc-splitting/README.md).

- [Si SOC finite sensitivity](si-soc-sensitivity-v1/README.md): E40/T05/K4,
  each relative to historical B0; [12 executed slots and finite responses](../results/si-soc-sensitivity/README.md).
  K4 exceeds the 0.1 meV observation window despite matching code responses.
