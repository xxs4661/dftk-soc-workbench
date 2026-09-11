# Mg QE SOC: restricted solver and FFT diagnostics

The [plan](plan.json) is fixed before execution, based on accepted
`9d49ca88bfe3c4add0e6c80c1376f006d065e306`. This case preserves every physical
field of the [first comparison](../mg-soc-qe-v1/README.md), including its corrected
PBEsol index metadata. It authorizes five numerical solves and one initialization
check, in this order:

| Slot/input | Source | Change from the frozen 7A SCF input |
| --- | --- | --- |
| [I36](I36.in) | fresh scratch | `nstep=0`; initialization only |
| [D36](D36.in) | independent copy of original Q36 SCF | bands, file potential/wfc, david, threshold 1e-13 Ry, ndim 2 |
| [C36](C36.in) | another copy of the same original Q36 SCF | bands, file potential/wfc, cg, threshold 1e-13 Ry, maxiter 200 |
| [G40](G40.in) | fresh scratch | only hard and smooth FFT dimensions explicitly 40³ |
| [D40](D40.in) | independent copy of G40 SCF | G40 grid plus D36 bands controls |
| [C40](C40.in) | another copy of the same G40 SCF | G40 grid plus C36 bands controls |

All inputs retain the original prefix `mg_soc_qe_v1`; each receives an isolated,
unique run directory. Within each D/C pair only the solver and its own control
field differ. The generator checks exact input differences against frozen 7A
bytes. `restart_mode='from_scratch'` begins a new bands action while the explicit
file initialization loads the copied potential and orbitals. Source hashes,
independent file inodes and post-run charge hashes bind the experiment locally.
Public XML cannot substitute for the full original `.save`.

Run the directed tests before the sequential slots:

```sh
python3.12 -m unittest discover -s tests -p 'test_qe_soc_diagnostics_*.py' -v
python3.12 scripts/run_qe_soc_diagnostics.py I36
python3.12 scripts/run_qe_soc_diagnostics.py D36
python3.12 scripts/run_qe_soc_diagnostics.py C36
python3.12 scripts/run_qe_soc_diagnostics.py G40
python3.12 scripts/run_qe_soc_diagnostics.py D40
python3.12 scripts/run_qe_soc_diagnostics.py C40
```

Physical reruns require the licensed UPF, original saved charge/wfc, the exact
existing QE launcher/binary/libraries, and a local preparation receipt binding
these sources. No downloads, installation, automatic retries or source recovery
from public XML are performed by the runner. Claims remain after a failed slot.
Use the explicit source checklist in the result report when preparing another
authorized reproduction; do not erase claims to repeat a numerical failure.

The source preparation command is `run_qe_soc_diagnostics.py --prepare`, with
`--historical-runs`, `--raw-manifest`, `--archive-data`, `--pw-x` and
`--dependency-receipt` pointing to the existing audited local inputs. The last
receipt must come from a fresh JLL identity audit: actual binary hash, successful
probe exit, actual library path→hash map and active QE Project/Manifest paths and
hashes. A matching version alone does not supply that evidence. Full probe and
receipt are in the execution archive; the public evidence lists their sanitized
identities. Preparation refuses to replace a previous receipt, and execution
rejects a missing dependency baseline. This is a same-environment reproduction
checklist, not an installer or portable environment reconstruction claim.

The predeclared same-density D/C filter is maximum raw difference ≤1e-7 Ha
over all 72 levels, with no eigensolver unconverged warnings. It is an engineering
stability observation, not a residual certificate or an agreement threshold.
I36 can use the QE 7.5 initialization exit convention (0 or 255 depending on
the build), but must not enter SCF or a full bands solve. IEEE flags remain
independent unresolved evidence. G40 includes grid and self-consistent-density
response; equal FFT sizes do not imply equal Hamiltonians or convergence.

The [result report](../../results/mg-soc-qe-diagnostics/README.md) will distinguish
new execution, historical reuse, failures, fixed-density binding and unresolved
scientific differences. No DFTK rerun or next-stage development is part of this case.
