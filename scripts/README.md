# Workbench scripts

- Phase 7G: `replay_public_independent.py` uses only new standard-library/NumPy readers and formulas; `run_cross_env_replay.py` runs frozen R and independent I separately on the declared Linux host. [Fixed plan and commands](../benchmarks/mg-soc-public-replay-v1/README.md). First Linux run completed: **I PASS/0, R FAIL/1**, CI failure retained for two predeclared density hashes; 380 I gates and 47 Linux synthetic tests PASS. [Actual receipt](../results/mg-soc-public-replay/linux/README.md).
- `run_orbital_energy_audit.py`: authenticated original G40/A/B extraction → density/kinetic gates → frozen FR only → signed ledger; requires existing NumPy and frozen Julia. `check_orbital_energy.py --all --legacy-python python3.9`: offline public Q coefficient/FR replay and full historical chain, no numerical solver. See [case](../benchmarks/mg-soc-wavefunction-energy-v1/README.md).

Use the [workbench environment](../environment/workbench/README.md), not a modified DFTK
Project. All expected source commits and the default Mg checksum come from
[`config/sources.lock`](../config/sources.lock).

- `fetch_sources.sh [--source-cache DIR]`: clone missing fixed sources; preserve and refuse
  existing dirty or wrong-version checkouts. A cache is a parent directory containing
  `DFTK.jl` and `PseudoPotentialIO.jl`, not a package download cache.
- `bootstrap_dftk.sh`: instantiate the saved workbench Manifest and check loaded identity
  in a new Julia process. It never changes the dependency resolution intentionally.
- `python3 scripts/run_recorded.py tests`: check actual environment identity and run the
  workbench Julia tests. These are not upstream DFTK tests.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_recorder*.py' -v`:
  original subprocess/log tests plus synthetic recorder protocol/publication regressions.
  Synthetic workers do not validate Julia, environments or pseudopotentials.
- `python3 tests/test_cli.py`: fresh-process CLI checks, including real Mg information
  mode. Requires the environment and the ignored Mg sample.
- `run_upf_inspection.sh [UPF_PATH]`: explicitly run **fr-nc** acceptance. With no argument,
  read the Mg path, provenance and SHA-256 from the source lock and verify the hash first.
- `run_dftk_minimal.sh`: optionally run upstream `:minimal` after the same identity checks.
  It uses `allow_reresolve=false`; missing test dependencies cause failure instead of a
  silent dependency upgrade. Phase 4A did not rerun this upstream selection.
- `collect_environment.sh`: legacy optional host inventory in ignored `.work/environment-inventory/`;
  its old reports remain history.

Every recorded invocation has a unique `results/runs/<run_id>/` with JSON, worker log
and a summary referencing the run ID, input checksum and Manifest checksum. These
transient directories are ignored; selected sanitized evidence is committed under
case-oriented `results/` entries after explicit whitelist export. Historical inspection
bytes remain at `results/upf-acceptance/phase3-inspection.json` and in Git history.
The initial marker is non-passing, so interrupted or early-failed runs cannot inherit
another run's PASS. There is no shared "latest PASS" file.

The Python recorder replaces the old shell pipelines: it separately checks the worker
exit, output sanitization, JSON structure and log/result writes. Human-readable logs go
to stderr/the run log; stdout contains one JSON object (except help). If storage itself
fails, the command exits nonzero and emits the failure JSON on stdout when possible.
Schema 2 is checked against the requested action before accepting worker output.
Strict inspection requires environment/parse/metadata PASS and EXPECTED_SOC_REJECTION;
identity, tests and minimal require their matching worker action and no UPF stages.
Protocol contradictions return 9; valid worker failures retain their failure codes.
JSON and summary are prepared before writing, and the authoritative result JSON is
published last. Rendering or writing failures produce a fresh ERROR record; failure
to persist that record is explicitly reported on stderr and in the stdout JSON.

## Acceptance contract

The low-level Julia worker requires `--mode fr-nc` or `--mode inspect`. The recorder is
the durable entry point; direct worker calls are useful for CLI/environment tests.
Information mode can return `INFO_ONLY`/0 after parsing; it does not set metadata or
construction checks to PASS. Strict mode only returns 0 after metadata acceptance and
the exact locked DFTK SOC guard. JSON separately reports `parse_status`,
`metadata_validation_status`, `dftk_construction_status`, `overall_status` and reasons.

| Exit | Meaning |
| --- | --- |
| 0 | Strict acceptance, successful requested check, information-only result, or help |
| 2 | Invalid arguments |
| 3 | Parser/type failure |
| 4 | Metadata fails or format variant is unsupported |
| 5 | Unexpected DFTK exception or unexpected construction success |
| 6 | Environment identity/dependency mismatch |
| 7 | Missing prerequisite or blocked bootstrap |
| 8 | Default input checksum mismatch |
| 9 | Unexpected worker termination, test failure, filtering/JSON/log/I/O failure |

Mapping uses parsed source indices, never record positions. PseudoPotentialIO's locked
v2 parser uses a beta's explicit index, falling back to its tag only when the attribute
is absent or `*`; relativistic-beta parsing does not have that fallback. It also prunes
all-zero ordinary betas without renumbering the source IDs. Missing parsed indices and
count mismatches after pruning are explicitly UNSUPPORTED, not claims that all such
physical pseudopotentials are invalid. Explicitly indexed reordering is accepted.

`j` uses absolute tolerance `1e-10` and zero relative tolerance, solely for decimal
roundoff; no rounding into allowed values is performed. Repeated `(l,j)` radial channels
are allowed; a partner `j` branch is not required. PP_RELWFC is not required for the
nonlocal-beta acceptance performed here. See the pinned source citations and test
results in [UPF acceptance evidence](../results/upf-acceptance/README.md).


## Scientific entry points and public offline review

| Purpose | Entry point / instructions |
| --- | --- |
| Matched scalar Si run and parse/compare | `run_scalar_baseline.py`, `parse_qe_baseline.py`, `compare_scalar_baseline.py`; [Si case](../benchmarks/si-sr-lda/README.md) |
| Independent reference integral and limited sensitivity | `inspect_si_reference.py`, `analyze_si_sensitivity.py`; [fixed matrix](../benchmarks/si-sr-lda/phase4c/README.md) |
| No-SOC fixed-potential / SCF spinors | [spinor prototype](../prototypes/spinor/README.md) |
| Angular/radial FR projectors | [FR projector conventions](../prototypes/relativistic/CONVENTIONS.md) |
| Full Hamiltonian / energy at fixed density | [FR integration](../prototypes/fr_integration/README.md) |
| Charge-only SOC SCF / comparison | `run_soc_scf.jl`, `compare_soc_scf.jl`; [SOC prototype](../prototypes/soc_scf/README.md) |
| First QE SOC run, parser and comparison | `run_qe_soc.py`, `parse_qe_soc.py`, `compare_qe_soc.py`; [fixed Mg case](../benchmarks/mg-soc-qe-v1/README.md) |
| Bounded QE SOC diagnostics | `run_qe_soc_diagnostics.py`, `parse_qe_soc_diagnostics.py`, `compare_qe_soc_diagnostics.py`; [fixed slots and source prerequisites](../benchmarks/mg-soc-qe-diagnostics-v1/README.md) |
| Diagnostics plus unchanged old publication checks | `python3.12 scripts/check_qe_soc_diagnostics.py --all --legacy-python python3.9`; [evidence](../results/mg-soc-qe-diagnostics/README.md) |
| Read bound existing density arrays; no model or solve | `run_density_hartree_audit.py`, `extract_soc_density.jl`, `parse_qe_charge_density.py`; [fixed read-only plan](../benchmarks/mg-soc-density-hartree-v1/README.md) |
| Complete public Fourier/Hartree arithmetic and old checks | `python3.12 scripts/check_density_hartree.py --all --legacy-python python3.9`; [array evidence](../results/mg-soc-density-hartree/README.md) |
| QE SOC offline native replay | `python3.12 scripts/check_qe_soc_evidence.py` |
| QE SOC input preparation only | `prepare_soc_qe_input.py` (Python 3.12+); [checklist](../benchmarks/mg-soc-fermi/checklist.md) |
| Public-only verification, no scientific run | `python3.9 scripts/check_publication.py` |

The `curate_*_evidence.py` helpers export explicit existing source fields or check
published arithmetic. Their check modes never start Julia/QE or load private raw
arrays. Export is publication work, not a new scientific result. Do not copy whole
run directories into results. Exact historical scalar replay uses Python 3.9;
newer Python summation differences are not repaired by changing algorithms or
loosening assertions. Current [status and NOT_RUN limits](../docs/status.md) apply.

The combined publication check uses Python 3.9 for exact historical scalar
arithmetic and `python3.12` on PATH for standard-library TOML in the prototype
checks (`--modern-python PATH` selects an existing Python 3.11+ interpreter).
It installs no packages or environments.

Phase 7A synthetic/adapter tests:

```sh
python3.12 -m unittest discover -s tests -p 'test_qe_soc_*.py' -v
```

They perform no physical QE solve. The real runner requires
an existing executable and exact UPF bytes; it creates an isolated run and never
automatically retries. `--refine-from .work/phase7a/<scf_run_id>` permits one
explicit warning-triggered bands refinement in copied scratch; original SCF E/F
remain authoritative. A standalone process receipt distinguishes solver exit from
parser failure. Native stderr warnings remain public even when XML is finite.

The current publication checker verifies the old UPF exporter from the fixed
`ac22a64421c4a5444a399477b9a3215dbd913487` Git object. Its `--export-upf` now refuses
to refresh frozen evidence; reproduce old export only from that historical checkout.

Phase 7B uses `test_qe_soc_diagnostics_*.py` for directed synthetic contracts;
its native evidence checker is public-only. I36 completion is initialization, not
SCF success. Fixed-density bands never provide new E/F. Slot claims prevent
unannounced repeats, and historical charge/wfc snapshots are protected by hashes.

Phase 7C uses `test_density*.py`, `test_qe_charge_density.py` and the small
`test_soc_density_fft.jl` synthetic array suite. The extractor authenticates
historical bytes before Serialization, reads A/B before G40, and refuses existing
output directories. It starts no SCF, eigensolve or QE program. The public checker
requires only complete gzip CSV coefficients and standard-library Python;
n_in/real-array extraction checks retain their separate runner-reported scope.

## Fixed historical-density energy audit

- `python3.12 scripts/check_energy_reference.py --all --legacy-python python3.9`: public saved-table/ledger replay, chaining unchanged older checks; no independent XC execution.
- `python3.12 scripts/run_energy_reference_audit.py --julia julia`: authorized fixed-density reproduction with the existing frozen depot and authenticated private sources, unique run_id, no solver.
- `audit_energy_ledger.py`, `compare_energy_reference.py`, `audit_local_g0.py`, and `evaluate_common_energy_terms.jl`: bounded new dictionary/algebra/radial/static-term components.

Read the [plan](../benchmarks/mg-soc-energy-reference-v1/README.md) and
[energy audit report](../results/mg-soc-energy-reference/README.md) for commands,
source restoration, predeclared gates, failure records and evidence limits.

## Bound QE local-potential audit

- `python_numpy scripts/check_qe_local_potential.py --all --legacy-python python3.9`: complete public NumPy FFT/registration/integral/precision replay; chains frozen predecessors. Use an existing NumPy environment; no installation.
- `run_qe_local_postprocess.py P2` then `P0`: exactly-once authorized slots using committed preparation, real source/build checks and independent copies. Completed claims prohibit numerical retries.
- `extract_saved_local_field.jl REQUEST.json NEW_IGNORED_DIR`: authenticate the saved Phase7D container before reading local/density arrays; frozen FFT only, no new model/XC.
- `parse_qe_filplot.py`, `replay_qe_local_fields.py`, `compare_qe_local_potential.py`: bounded native format, full public transforms and signed algebra.

See the [Phase7E contract](../benchmarks/mg-soc-qe-local-potential-v1/README.md)
and [evidence](../results/mg-soc-qe-local-potential/README.md). Synthetic tests
are in `test_qe_filplot.py`, `test_qe_local_*.py` and
`test_saved_local_field.jl`; synthetic workers are not physical calculations.
