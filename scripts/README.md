# Workbench scripts

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
- `collect_environment.sh`: legacy optional host inventory; its old reports remain history.

Every recorded invocation has a unique `results/runs/<run_id>/` with JSON, worker log
and a summary referencing the run ID, input checksum and Manifest checksum. These
transient directories are ignored; selected sanitized evidence is committed under
`results/phase4a/`. Historical `results/upf-inspection.json` and earlier logs are untouched.
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
results in [the Phase 4A review](../results/phase4a-review.md).
