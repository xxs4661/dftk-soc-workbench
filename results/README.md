# Scientific results

This index separates material comparisons, mathematical checks and implementation
regressions. Case reports, native warnings and numerical files retain their
original identities. A successful replay verifies its stated public-data scope;
it does not rerun SCF or establish physical convergence.

For an executable starting point, see [public reproduction](../docs/reproducibility.md).
The [history index](../docs/history.md) identifies the clean snapshots required by
older checkers. [Current capabilities](../docs/status.md) describes supported use.

## Silicon SOC spectra and sensitivity

The two-atom diamond Si case uses one authenticated fully relativistic NC-PBE
pseudopotential with NLCC. Workbench and QE solve the nonmagnetic, charge-only
SOC problem; their fixed-density probes use each program's own final density.

| Question | Recorded result and evidence | Interpretation |
| --- | --- | --- |
| Does SOC resolve the fixed Γ valence window? | [Full spectra and same-density spin-trace control](si-soc-splitting/README.md): Δ = 47.4576152 meV (workbench), 47.4576124 meV (QE). | Fixed-window structure and splitting comparison pass. The [occupation-aware assessment](si-soc-splitting/status-correction/README.md) retains manifold interpretation as **REVIEW_REQUIRED**. |
| Does removing the spin-dependent nonlocal action restore the degeneracy? | The same-density control's six-state width is about 1.63×10⁻¹² eV; see [canonical comparison](si-soc-splitting/comparison.json). | A spin-trace operator diagnostic, not a separate scalar-pseudopotential calculation. |
| How sensitive is Δ to the selected settings? | [Paired cutoff, temperature and k-grid changes](si-soc-sensitivity/README.md): E40/T05 changes fall within the declared 0.1 meV window; K4 raises Δ by about 0.331506 meV in both programs. | Agreement between programs does not make the k-grid change small. These are three finite checks, not a convergence study. |
| Does the denser QE sequence change that picture? | [Historical QE K6/K8 reference](si-soc-k-reference/README.md): K4→K6 and K6→K8 changes are +0.0471284 and +0.0086212 meV. | Both are within the observation window. That QE-only matrix contained no workbench K6/K8 runs; its values do not establish cross-code agreement or full convergence. |
| Does the workbench reproduce the same-input QE K6 splitting? | [K6 resource outcome](soc-extra/README.md): a two-map pilot completed, but the single formal SCF attempt stopped under the fixed resource-headroom rule, **FAIL / native 1 / outer 1**. | No converged workbench K6 state: Γ BLOCKED_PARENT, D−QE splitting and K4→K6 response comparisons NOT_ASSESSED. QE is historical reuse; workbench K8 remains NOT_RUN. |

Raw spectra and single-global-reference diagnostics remain available. No fitted
potential offset or empirical total-energy correction was applied. QE warnings,
FD diagnostics and uncomputed irreducible representations remain explicit in the
case reports. [Fixed snapshots](../docs/history.md#silicon-spectra-and-sensitivity)
keep the original numerical and corrected-status checks distinct.

## Magnesium cross-code comparison and energy reference

Mg uses the recorded FR-PBEsol family; it is not an LDA/LSDA benchmark. The
[charge-only A/B SCFs](mg-soc-scf/README.md) and
[independent QE comparison](mg-soc-qe-comparison/README.md) supply the states for
the following audits. Their remaining differences are retained rather than
removed by fitting an energy constant.

| Evidence | What can be checked |
| --- | --- |
| [Solver and FFT controls](mg-soc-qe-diagnostics/README.md) | Same-saved-density solver comparisons, explicit grid control and the observed scope of native IEEE warnings. Their cause remains unlocalized. |
| [Density and Hartree](mg-soc-density-hartree/README.md) | Full published Fourier coefficients, electron counts, common/noncommon support and each native Hartree reconstruction. |
| [Energy ledger and common terms](mg-soc-energy-reference/README.md) | Signed energy bookkeeping, finite G=0 terms, density response and evaluation differences. |
| [Local-potential reconstruction](mg-soc-qe-local-potential/README.md) | Bound pp.x P2/P0 fields, direct integrals and propagated native print precision; these are reconstructed fields, not the old SCF in-memory potential. |
| [Original-orbital audit](mg-soc-wavefunction-energy/README.md) | Full public Q coefficients, kinetic sums and the frozen workbench nonlocal operator acting on Q orbitals. A/B replay is limited to published per-state and projected data. |
| [Linux public replay](mg-soc-public-replay/linux/README.md) | Independent path **I PASS/0**, frozen path **R FAIL/1** on derived density fingerprints; the failed CI result remains recorded. No Linux SOC SCF was run. |

The workbench nonlocal expectation on QE orbitals is not an independent QE
native nonlocal energy. Derived energy combinations do not identify separate
operators or uniquely locate an error. See the
[Mg snapshots and replay scopes](../docs/history.md#magnesium-comparison-and-audits).

## Representation, operators and energy consistency

| Validation layer | Evidence and limit |
| --- | --- |
| Input acceptance | [FR-NC metadata and recorder checks](upf-acceptance/README.md) distinguish valid metadata from the frozen upstream DFTK SOC rejection. |
| Scalar reference | [Matched Si SR-LDA baseline](scalar-si-baseline/README.md) and [finite reference/cutoff/k checks](scalar-si-sensitivity/README.md); a different source family from SOC Si. |
| Spinor representation | [No-SOC fixed-H and SCF checks](spinor-no-soc/README.md) recover the scalar problem within their declared contracts. |
| FR nonlocal operator | [Projector tests](relativistic-projectors/README.md) cover channels, spin-angular conventions, degeneracy and time reversal. Synthetic tests are labeled separately from material evidence. |
| Full Hamiltonian and energy | [Fixed-density integration checks](fr-hamiltonian-energy/README.md) connect operator action and orbital energy, preceding the material SCFs. |

[Methods](../docs/methods.md) links these conventions to their implementations;
[early review snapshots](../docs/history.md#representation-and-initial-validation)
preserve the original reports and historical test counts.

## Core allocation and endpoint regression

The [static core measurements](soc-core-memory/README.md) compare the old and new
implementations on authenticated B0/K4 inputs. Five warmed samples per operation
and separate cold costs are public. FR-24 median allocation is about 0.153% of
the reference; complete-pipeline ratios are about 30.8% (B0) and 27.4% (K4).
These allocation results do not establish an overall speedup:
**PERFORMANCE_REVIEW_REQUIRED** remains the timing conclusion.

The [completed Si SCF and own-density Γ regression](soc-core-memory/completion/README.md)
meets the original new-versus-old workbench energy, density and spectrum gates.
It is an actual endpoint calculation, not a new QE pair. The initial parser
failure remains in the [earlier partial report](soc-core-memory/README.md).
Private-array differences and observed memory ownership are runner-reported;
public replay checks their recorded scalar arithmetic and published endpoints.
Occupation/manifold and physical convergence limits are unchanged. Use the
[completed snapshot](../docs/history.md#core-allocation-and-endpoint-regression)
for strict replay of that original completed regression.

The [supplementary validation](soc-extra/README.md) retains the completed core
after finite B0/K4 profiling and passes a fresh B0 SCF/own-density Γ regression.
Each of four profiled operations retains one warmup and all five samples; no
optimization candidate was attempted and no overall speedup is established.
The K6 pilot completed two full maps, but the subsequent formal SCF stopped
when sampled peak plus fixed remaining growth exceeded the 8 GiB screen.
This was not sampled RSS reaching 8 GiB, and the pilot is not a converged SCF.
The new record separates cumulative allocations, retained storage, resource
observations and execution outcomes; native Linux SCF/Γ remains NOT_RUN.
