# Prepared Mg SOC QE input

Status: **PREPARED_NOT_EXECUTED**. QE SOC benchmark: **NOT RUN**.
This directory contains one input and its provenance; no UPF or QE output.

- A/B runs: `20260906T151940Z-A-270110aa` / `20260906T153016Z-B-62835d43`.
- Input: `Mg.upf`, SHA-256 `19b117bfa920945bffaee91eefbcfbf9fd44e035f3708b965aae59aabf3be256`; Mg NC/full/SOC,
  PBEsol, 10 valence electrons, no NLCC. Place those verified bytes in
  `./pseudo/Mg.upf` before a future run from this directory. `./scratch` is relative.
- One atom in a 10 bohr cubic cell at (0.17, 0.23, 0.31); Gamma and the explicit
  opposite k pair retain weight 1/3 each. `nosym` preserves the supplied list;
  `noinv` and `no_t_rev` disable the corresponding reduction operations.
- `nbnd=24` is the successful A/B common count of explicit
  spinor states. Capacity is one, not a scalar spin-degeneracy multiplier.
- `ecutwfc=30 Ry=15 Ha`; `ecutrho=120 Ry`. QE chooses its FFT grid: record the
  actual grid and any difference from the workbench in the later benchmark.
- Fermi-Dirac `degauss=0.002 Ry=0.001 Ha`; omit `nspin`. `noncolin` and `lspinorb`
  are true. Zero starting magnetization imposes QE's nonmagnetic time-reversal
  mode (`domag=false`); it does not calculate magnetization. The workbench instead
  retains measured Pauli-density diagnostics. No `input_dft` override is used:
  verify the actual QE-reported functional against the PBESOL header.
- Future electronic settings: `conv_thr=1e-10 Ry`, `electron_maxstep=400`,
  `mixing_beta=0.1`, default diagonalizer. These are declared preparation choices,
  not claims of matched algorithms, convergence, or physical cutoff convergence.
- Before any scientific comparison, record the actual executable/version/hash,
  environment, input/output hashes, loaded UPF, actual k points/weights, electron
  count, bands, smearing, FFT grid, and final convergence/eigenpair diagnostics.
- Compare both internal energy E and free energy F=E-tau*S. QE's documented output
  convention labels `total energy` as F and the smearing contribution as -TS;
  independently verify the actual future version's output/XML labels, signs and
  units. Do not reuse the scalar eight-electron parser or fit an arbitrary offset.

Parameter authority: [QE 7.5 input documentation](https://www.quantum-espresso.org/Doc/INPUT_PW.html),
[fixed 7.5 documentation](https://gitlab.com/QEF/q-e/-/raw/qe-7.5/PW/Doc/INPUT_PW.def). Energy-label explanation:
[QE developer reply](https://lists.quantum-espresso.org/pipermail/users/2021-January/046830.html).

The next scientific gate is the first independent QE SOC comparison. Preparation
does not satisfy it; no additional internal validation round is required first.
