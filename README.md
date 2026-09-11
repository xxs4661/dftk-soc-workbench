# DFTK SOC workbench

An experimental plane-wave spin–orbit coupling workbench for researchers studying
norm-conserving pseudopotentials, spinor operators and numerical agreement between
electronic-structure codes. It implements nonmagnetic, **charge-only SOC** using
fully relativistic NC-UPF data and a frozen DFTK environment. Mg and diamond Si
provide concrete test cases, with Quantum ESPRESSO comparisons and public
numerical evidence.

This is a separate research workbench, not an official DFTK SOC feature or a
stable package for arbitrary materials. You can inspect the mathematics, call
the existing matrix core and replay specified public results without running a
new material calculation.

## What is implemented

- FR channel parsing, spin-angular projectors and a matrix-free nonlocal action
  with independent angular and dense-matrix references.
- Two-component wavefunctions, charge-density construction, capacity-one
  Fermi–Dirac occupations and a charge-only self-consistent energy loop.
- A reusable `SOCKernels` matrix core with explicit ownership and workspace
  interfaces, connected to the DFTK adapter and exercised by a real Si SCF and
  its own-final-density Γ spectrum.
- Fixed-input Si/QE spectral comparisons and Mg density, Hartree, local-potential
  and orbital-energy audits, with distinct public and runner-reported evidence.

The [capability table](docs/status.md) separates implemented functions, numerical
comparisons, sensitivity, replay coverage and open work.

## Representative validation

| Question | Recorded observation | Scope and main limitation |
| --- | --- | --- |
| Does the Si calculation resolve an SOC split at Γ? | Workbench / QE fixed-window splits: **47.4576 / 47.4576 meV**. The same-density spin-trace control removes the resolved six-state split. | [Si spectra and corrected status](results/si-soc-splitting/status-correction/README.md): fixed-window checks pass; occupation saturation and complete manifold interpretation remain under review. The control is not a separate scalar-UPF calculation. |
| How sensitive is that statistic to settings? | Increasing the SCF k-point grid from 2³ to 4³ changes it by about **+0.3315 meV** in both programs, above the declared 0.1 meV observation window. | [Limited paired sensitivity](results/si-soc-sensitivity/README.md): tested cutoff and temperature changes stay within that window; a few directions do not establish convergence. |
| What does a denser QE reference show? | 4³→6³: **+0.04713 meV**; 6³→8³: **+0.00862 meV**. | [QE-only trend](results/si-soc-k-reference/README.md): DFTK 6³/8³ were not run, so these are not new dense-grid cross-code comparisons. |
| Does the extracted core preserve the existing calculation? | A fresh Si SCF and Γ calculation meet the original energy, density and all-24-level regression limits. | [Core endpoint regression](results/soc-core-memory/completion/README.md): comparison against the earlier workbench, not a new QE pair or a measured overall speedup. |

Small differences under one fixed input are not estimates of absolute physical
accuracy. Raw values, warnings and the original comparison thresholds remain in
the linked records.

## Start here

**Review public results** with Git history and an existing Python 3.12:

```sh
python3.12 -B scripts/review.py core-regression
```

This read-only entry runs the original strict checker in a fixed, clean
historical snapshot outside your checkout. It recomputes public energy/spectrum
arithmetic and checks provenance; it does not rerun SOC SCF, recover private
arrays or certify convergence. It preserves nonzero exits and scientific review
flags. No automatic downloads or dependency installation occur.

**Call the numerical core** using Julia (tested with 1.12.7):

```sh
julia --startup-file=no --project=@stdlib examples/soc_kernels.jl
```

The existing example uses small synthetic complex matrices and Julia's standard
library. It checks a nonlocal action against a dense oracle and compares two
expectation contractions. No DFTK, UPF or registered workbench package is needed.
[Getting started](docs/getting-started.md) explains prerequisites and invocation
from another directory; [reproduction scopes](docs/reproducibility.md) cover
historical checks and the additional requirements of native experiments.

## Limits that matter for research

Magnetic noncollinear XC, forces/stress, USPP/PAW, GPU/automatic differentiation
and MLP are outside the validated implementation. The tested path is CPU
Float64/ComplexF64. Full physical convergence and Si manifold interpretation
are not established. DFTK dense-k memory remains insufficiently bounded;
static allocation reductions do not establish an overall SCF speedup.

Mg's independent Linux public replay passed its numerical contract while the
original checker failed two derived-density hashes. That is not a Linux SOC SCF
run. QE warnings and unresolved IEEE origins remain documented, and the Mg
orbital audit does not independently measure QE's native nonlocal energy.

## Find the implementation and evidence

- [Methods and conventions](docs/methods.md) → spinors, projectors, density and energy.
- [Core interfaces and ownership](docs/soc-core-runtime.md) → [`src/SOCKernels.jl`](src/SOCKernels.jl) and its adapter.
- [Results](results/README.md) · [Case inputs](benchmarks/README.md) · [Commands](scripts/README.md).
- [Frozen environment](environment/workbench/README.md) · [Historical snapshots](docs/history.md).
- [Contributing and reporting problems](CONTRIBUTING.md) · [Open integration questions](docs/soc-upstream-risks.md).

The repository owner is **xxs4661**. The workbench uses the [MIT license](LICENSE);
third-party software and pseudopotentials retain their own terms. Cite
[DFTK SOC workbench](https://github.com/xxs4661/dftk-soc-workbench) with the actual
commit used, and cite the DFTK, QE and pseudopotential work relevant to your study.
Substantial AI assistance supported planning, implementation and review; the
[disclosure](docs/ai-assistance.md) explains the division of work and human
responsibility.
