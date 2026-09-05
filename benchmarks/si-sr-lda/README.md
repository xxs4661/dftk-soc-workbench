# Si scalar-relativistic LDA baseline

[case.json](case.json) is the sole source of geometry, explicit k points,
cutoffs, electronic settings and XC selection for the paired inputs. Its lattice
vectors are rows; the DFTK generator must transpose them into columns, while QE
prints the vectors as rows. The lattice constant is a prescribed test input,
not a calculated equilibrium value or a new measurement.

This is one smoke benchmark. Execution and input comparability have separate
statuses; numerical agreement requires review and the convergence study is
`NOT_RUN`. It does not implement or validate SOC. The scalar input remains
ineligible for the independent strict FR-NC acceptance tool.

## Pseudopotential and retrieval

The selected `Si.upf` is from `dojo.nc.sr.lda.v0_4_1.standard.upf`, distributed
by PseudoLibrary v0.2.1 and indexed by
[PseudoPotentialData v0.3.2](https://github.com/JuliaMolSim/PseudoPotentialData.jl/blob/v0.3.2/Artifacts.toml).
The input SHA-256, archive SHA-256, source URL, artifact tree hash and header
summary are recorded in `case.json`. The inspected UPF 2.0.1 header declares NC,
scalar relativity, no spin-orbit data, four valence electrons, and NLCC. The
file contains its `PP_NLCC` radial data. Neither the payload nor package caches
belong in version control.

The existing cache can supply the identical file if its input hash is checked.
To retrieve it without adding packages or changing the workbench environment,
run from the repository root (downloads stay under `.work/`):

```sh
python3 - <<'PY'
import hashlib, io, json, tarfile, urllib.request
from pathlib import Path
p = json.loads(Path('benchmarks/si-sr-lda/case.json').read_text())['pseudo']
target = Path(p['local_path'])
if target.exists():
    assert hashlib.sha256(target.read_bytes()).hexdigest() == p['sha256']
else:
    target.parent.mkdir(parents=True, exist_ok=True)
    archive = urllib.request.urlopen(p['source_url']).read()
    assert hashlib.sha256(archive).hexdigest() == p['source_archive_sha256']
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as bundle:
        members = [m for m in bundle.getmembers()
                   if m.isfile() and Path(m.name).name == p['filename']]
        assert len(members) == 1
        payload = bundle.extractfile(members[0]).read()
    assert hashlib.sha256(payload).hexdigest() == p['sha256']
    with target.open('xb') as output:
        output.write(payload)
print('Verified input:', target, p['sha256'])
PY
```

## Exact XC and NLCC

The raw header declaration is `SLA  PW   NOGX NOGC`: Slater exchange and
Perdew–Wang 1992 correlation, with no gradient terms. The calculation retains
that declaration in QE without forcing `input_dft`. QE 7.5 maps this to internal
indices `(1, 4, 0, 0)`; its unpolarized correlation driver calls the PW routine
with the original PW parameters. DFTK uses the explicit identifiers `lda_x`
and `lda_c_pw` (Libxc IDs 1 and 12). The latter uses `a = 0.031091`, matching
QE's unpolarized PW routine; `lda_c_pw_mod` (ID 13, `a = 0.0310907`) is a
distinct variant and is not selected. This statement concerns the specific
nonmagnetic calculation, not every spin-polarized implementation.

The inspected sources are:

- [Pinned PseudoPotentialIO UPF name mapping](https://github.com/JuliaMolSim/PseudoPotentialIO.jl/blob/fec942781560c391f20214ba4cd85fb2431deb84/src/data/upf_functionals.jl#L1).
- [QE 7.5 functional names and references](https://github.com/QEF/q-e/blob/qe-7.5/Modules/funct.f90#L102),
  [unpolarized correlation dispatch](https://github.com/QEF/q-e/blob/qe-7.5/XClib/qe_drivers_lda_lsda.f90#L184),
  and [PW parameterization](https://github.com/QEF/q-e/blob/qe-7.5/XClib/qe_funct_corr_lda_lsda.f90#L328).
- [Libxc 7.0.0 PW and modified-PW parameters](https://gitlab.com/libxc/libxc/-/blob/7.0.0/src/lda_c_pw.c#L19).
- [Pinned DFTK functional selection](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/standard_models.jl#L220)
  and [pseudopotential loading](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/pseudo/PspUpf.jl).

`pseudo.dftk_rcut_bohr = null` requests DFTK's `rcut = nothing`: retain the
available radial grid rather than apply a new radial cutoff. NLCC stays active
in both programs. Each run must verify the actual input bytes, parsed header,
loaded environment and QE output; source documentation is not execution
evidence. The installed QE binary's source commit is not inferred from its
version label.

Energy comparison uses Ha internally (`1 Ha = 2 Ry`). The eV presentation uses
the [CODATA 2022 Hartree conversion](https://physics.nist.gov/cuu/pdf/wall_2022.pdf),
`1 Ha = 27.211386245981 eV`. Program-specific text-output rounding and constants
do not redefine the XML energy units.

## Run and inspect

From the repository root, with the frozen workbench sources/environment already
available and the Si file obtained above:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p '*baseline*.py' -v
python3 scripts/run_scalar_baseline.py --julia-depot /path/to/existing/workbench/cache
```

The cache path is supplied at invocation time, never stored in `case.json` or the
frozen environment. `--pw-x` overrides `PW_X`, then PATH discovery. This small
runner supports native executables and the existing simple `qe-jll` launcher;
it refuses an unrecognized script wrapper rather than guessing its binary.
The JLL launcher uses its existing Julia environment, separately from DFTK's
frozen workbench project. No installation or dependency update is performed.

`--prepare-only NEW_DIRECTORY` generates `qe.in` and `dftk-input.json` without
claiming a calculation. An executed run uses a unique `.work/scalar-baseline/`
subdirectory: new QE scratch, one checked UPF copy shared by both engines,
input hashes, current identity, commands, complete stdout/stderr and result JSON.
The engines execute sequentially with one CPU process/thread. Failure returns
nonzero and leaves that invocation's result; no previous success is substituted.

DFTK converges eight bands plus three auxiliary bands, then diagonalizes the same
final SCF Hamiltonian once. The total energy remains the SCF energy. Saved DFTK
residuals are solver-reported values; zero slots can belong to already locked
states and do not claim independently recomputed exact-zero residuals.
QE uses full accuracy for empty states. Its individual residual norms are not
available in these outputs. The two SCF tolerances measure different quantities.

`comparison.json` and `eigenvalues.csv` retain raw spectra and differences plus
one global HOMO reference per program; there is no per-k-point shift or total
energy correction. Numerical agreement remains `REVIEW_REQUIRED` until reviewed;
`convergence_study_status` remains `NOT_RUN`. Selected published evidence and its
raw/redacted SHA-256 manifest are linked from the
[Phase 4B report](../../results/phase4b-review.md).
