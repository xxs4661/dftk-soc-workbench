# First Mg SOC QE comparison

This new Phase 7A package fixes one QE 7.5 SOC SCF against the already public
[Phase 6C A/B endpoints](../../results/mg-soc-scf/README.md), marked
HISTORICAL_REUSED. A is the predeclared primary reference; B is auxiliary.
The [old preparation](../mg-soc-fermi/checklist.md) remains historical
PREPARED_NOT_EXECUTED. [Results and limits](../../results/mg-soc-qe-comparison/README.md)
refer to the new run only.

[case.json](case.json) fixes the model, parser gates and comparison rules before
execution; [qe.in](qe.in) is its hash-bound native input. Relative to the old
preparation, only the case prefix/comment and `diago_full_acc=.true.`,
`diago_thr_init=1d-10` are new. The latter is QE's initial eigenvalue iteration
threshold in Ry, not a measured eigenvector residual. Full accuracy applies the
occupied-state diagonalization accuracy to empty states too. Default QE FFT
selection is retained and its realized grid is reported separately.

One Mg, 10 bohr cubic cell, fractional position (0.17,0.23,0.31), full NC PBEsol
with no NLCC, 10 electrons, 24 capacity-one spinor states, three explicit points
Γ/k± at equal spatial weights; 15 Ha cutoff, FD tau=0.001 Ha. No `nspin` or
`input_dft` override is used. This Mg input is not an LDA/LSDA baseline.

Acquire the exact ignored `.work/pseudos/Mg.upf` from the recorded source in
[historical evidence](../../results/mg-soc-scf/evidence.json). The SHA-256 is
`19b117bfa920945bffaee91eefbcfbf9fd44e035f3708b965aae59aabf3be256`.
No UPF bytes are distributed here. With an already installed QE launcher:

```sh
python3.12 scripts/run_qe_soc.py
```

This starts one real SCF in a unique `.work/phase7a/<run_id>` and no DFTK run.
`--pw-x PATH` or `PW_X` selects an existing launcher; `--pseudo PATH` selects
input bytes subject to the same checksum. It installs nothing and retries
nothing automatically. A process receipt remains separate from parser success.
The authoritative initial marker is non-passing; raw `.save` and wavefunctions
remain local. Public offline verification starts no solver:

```sh
python3.12 scripts/check_qe_soc_evidence.py
```

The primary spectrum summary covers the lowest 16 states; all 24 at all three
points are also published. Each engine gets one global sampled HOMO reference,
applicable only to occupations within 1e-8 of endpoints. Occupied grouping uses
the named historical reference f>=0.5; QE classification agreement is explicit.
Raw energy/spectra and the chosen references are retained; no fitted constants
or total-energy corrections are permitted. Agreement is REVIEW_REQUIRED and
physical cutoff/k/temperature convergence is NOT_ESTABLISHED.

The preserved `case.predeclared.json` contains an incorrect QE correlation index
in descriptive metadata. Current `case.json` corrects only that index (1 to 4)
using the fixed QE PBEsol table; the actual native input had correctly selected
PBESOL, and all physical inputs/tolerances are unchanged.

The single warning-triggered follow-up uses [qe-bands.in](qe-bands.in), copied
SCF scratch and the same physical settings. Reproduction, when warranted by the
same warning, uses:

```sh
python3.12 scripts/run_qe_soc.py --refine-from .work/phase7a/<scf_run_id>
```

Replace the run ID before execution. E/F always remain from the SCF.
