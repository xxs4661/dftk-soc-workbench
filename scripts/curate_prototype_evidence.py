#!/usr/bin/env python3
"""Deterministic public evidence selection; --check uses public files only.

Export reads an explicit whitelist from the accepted immutable Git snapshot.
Checks recompute table arithmetic, never SCF, eigenvectors, densities or UPF data.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tomllib

BASE = "8658992afa936f6cdb1a8055699ae9aa47b32297"
SELF = "scripts/curate_prototype_evidence.py"
ENVIRONMENT = "results/shared/environment.json"
CASES = ("spinor-no-soc", "relativistic-projectors", "fr-hamiltonian-energy")
SETTINGS = {"5A": "prototypes/spinor/tolerances.toml",
            "5B": "prototypes/spinor/phase5b.toml",
            "6A": "prototypes/relativistic/phase6a.toml",
            "6B": "prototypes/fr_integration/phase6b.toml"}
SOURCES = {
    "spinor-no-soc": ["results/phase5a/real-b0.json", "results/phase5b/real-abc.json",
        "results/phase5b/maps-A.jsonl", "results/phase5b/maps-B.jsonl",
        "results/phase5b/new-test-evidence.json", "results/phase5b/independent-energy-audit.json",
        "results/phase5a/real-b0.log", "results/phase5b/real-abc.log"],
    "relativistic-projectors": ["results/phase6a/real-mg-si.json",
        "results/phase6a/tests-final.json", "results/phase6a/independent-raw-audit.json",
        "results/phase6a/real-mg-si.log"],
    "fr-hamiltonian-energy": ["results/phase6b/real-mg-si.json",
        "results/phase6b/tests-final.json", "results/phase6b/phase6a-regression.json",
        "results/phase6b/attempts/gamma-key-error.json", "results/phase6b/real-mg-si.log",
        "results/phase6b-review.md"],
}
LOGS = {"spinor-no-soc": {"fixed-h-source.log": "results/phase5a/real-b0.log",
                          "scf-source.log": "results/phase5b/real-abc.log"},
        "relativistic-projectors": {"source.log": "results/phase6a/real-mg-si.log"},
        "fr-hamiltonian-energy": {"source.log": "results/phase6b/real-mg-si.log"}}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def select(obj, keys):
    """Strict whitelist: a missing requested field is an export error."""
    return {key: obj[key] for key in keys.split()}


def finite_tree(value):
    if isinstance(value, float):
        require(math.isfinite(value), "Non-finite public number")
    elif isinstance(value, dict):
        for child in value.values():
            finite_tree(child)
    elif isinstance(value, list):
        for child in value:
            finite_tree(child)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(actual, expected, message, atol=1e-12):
    require(math.isfinite(actual) and math.isfinite(expected), message + ": non-finite")
    require(abs(actual - expected) <= atol, message)


def source_record(path, data):
    # Git blob identity computed from actual original bytes, including the header.
    blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    return {"path": path, "commit": BASE, "blob_sha": blob,
            "sha256": digest(data), "bytes": len(data),
            "url": f"https://github.com/xxs4661/dftk-soc-workbench/blob/{BASE}/{path}"}


def settings_reference(root, phase, original):
    path = SETTINGS[phase]
    raw = (root / path).read_bytes()
    require(tomllib.loads(raw.decode()) == original, f"{phase}: recorded settings differ")
    return source_record(path, raw)


def receipt(root, obj, original_path, shared):
    record = select(obj, "run_id started_utc finished_utc base_commit workbench_head_at_execution "
                    "executed_source_sha256 exit_code execution_status numerical_review_status phase")
    env = obj.get("environment", obj.get("provenance", {}).get("environment"))
    require(env == shared, "Actual recorded environment does not match shared identity")
    record["environment_check"] = {"path": ENVIRONMENT,
        "sha256": digest((root / ENVIRONMENT).read_bytes()), "status": env["status"],
        "original_source": original_path, "original_field": "provenance.environment" if "provenance" in obj else "environment",
        "comparison": "All parsed identity fields equal; original run checked real paths before sanitization"}
    record["historical_statuses"] = {k: v for k, v in obj.items()
                                    if k.endswith("_status") and k not in record}
    return record


def compact_map(row, contexts):
    out = select(row, "map_index map_role status alpha density_candidate closure_checks_passed "
                 "unmixed_residual_l2 mixed_step_l2 actual_next_step_l2 next_density_source "
                 "n_in n_out n_mixed n_next")
    d = row["diagnostics"]
    out["diagnostics"] = select(d, "consumed_input_sha256 orbital_density_sha256 "
        "max_input_h_residual_ha max_orthogonality_frobenius max_self_density_h_residual_ha "
        "pauli_density_relative_l2 energy_total_ha energy_terms_ha energy_checks energy_density_source")
    out["diagnostics"]["potential"] = select(d["potential"],
        "change_norm probe_action_norm sha256 probe_action_sha256 probe_action_change_norm norm probe_seed")
    context = [select(k, "index ng dimension target_states auxiliary_states initial_seed initial_source")
               for k in d["per_k_summary"]]
    if context not in contexts:
        contexts.append(context)
    out["solver_context_index"] = contexts.index(context)  # Explicit zero-based table reference.
    out["diagnostics"]["per_k"] = [select(k,
        "index iterations solver_n_matvec orthogonality_frobenius explicit_residual_max_ha")
        for k in d["per_k_summary"]]
    require(contexts[out["solver_context_index"]] == context,
            "Per-map solver context did not round-trip exactly")
    # Strings constant across every map live once in the run's convention description.
    for key in ("density_source", "call_count_scope", "nlcc_source"):
        del out["diagnostics"]["energy_checks"][key]
    return out


def readme(case, d):
    """Scientific summary rendered from the same canonical data; checked bytewise."""
    common = """
## Review and reproduction

[evidence.json](evidence.json) is the canonical numerical source. Its provenance records
the original run IDs, execution HEAD/file hashes, fixed inputs and immutable source blobs.
Historical `REVIEW_REQUIRED` is preserved; AI-assisted arithmetic review is not external
expert certification. Current capabilities and limits are in [status](../../docs/status.md).

From the repository root, Python 3.11 or later runs public-data checks without Julia,
private arrays, SCF or QE:

```sh
python3.12 scripts/curate_prototype_evidence.py --check
```

This recomputes the retained tables and energy/spectral differences. Density, orbital,
operator-action and direct eigenvector-residual errors remain original runtime measurements
when their arrays are not public; a hash is not an independent numerical proof. Physical
reproduction requires the frozen environment and the licensed input at its recorded hash.
"""
    if case == "spinor-no-soc":
        a=d["fixed_h"];b=d["scf"]
        body=f"""# Spinor validation without SOC

Phase 5A run `{a['run']['run_id']}` lifted the same converged scalar Si Hamiltonian
into two components and solved 16 target states at each of eight k points. Both the spinor
and scalar target spectra, residuals, occupations and occupied-subspace diagnostics are retained.
The spinor fixed-H occupied expectation is **{a['fixed_h_band_energy']['spinor_expectation_ha_cell']} Ha/cell**;
it is a band expectation, not a DFT total energy. [Source log](fixed-h-source.log).

Phase 5B run `{b['run']['run_id']}` independently initialized spinor A/B,
then native scalar C. Both complete **53-map** histories survive, including candidate and
extra closure; no sparse sampling or hidden early residuals. [Source log](scf-source.log).

| Independent run | Total energy (Ha/cell) | Final density residual L2 |
|---|---:|---:|
| A | {b['runs']['A']['maps'][-1]['diagnostics']['energy_total_ha']} | {b['runs']['A']['maps'][-1]['unmixed_residual_l2']} |
| B | {b['runs']['B']['maps'][-1]['diagnostics']['energy_total_ha']} | {b['runs']['B']['maps'][-1]['unmixed_residual_l2']} |
| C native scalar | {b['runs']['C']['total_energy_ha_cell']} | {b['runs']['C']['density_residual_history'][-1]} |

All endpoint target eigenvalues/residuals and independent scalar references remain public.
All three nonstationary finite-difference steps retain both original side energies and the
independently evaluated central Hamiltonian derivative. Seven-term E uses the returned
orbitals' own density; the double-counting identity uses H[n_out], without a fitted shift.
Hartree and electron counts use valence density; NLCC enters native XC once.

[Layout and implementation](../../prototypes/spinor/README.md),
[energy conventions](../../prototypes/spinor/SCF-DESIGN.md),
[5A thresholds](../../prototypes/spinor/tolerances.toml),
[5B settings](../../prototypes/spinor/phase5b.toml).

These are no-SOC, charge-only LDA runs on the original Si input. Magnetic XC, QE SOC
comparison and physical cutoff/k convergence were not established. A native log's `-Inf`
energy-change display is log10(0), not an infinite total energy.
"""
    elif case == "relativistic-projectors":
        body=f"""# Relativistic nonlocal projectors

Run `{d['run']['run_id']}` used real Mg full-relativistic NC PBEsol data
for an algebraic 39-q probe and the real scalar Si input for an artificial complete
spin-degenerate limit. It was not a physical Mg SCF or a real FR Si benchmark.
Actual execution was `{d['run']['started_utc']}` to `{d['run']['finished_utc']}` UTC;
the run-ID label's time is not substituted for these recorded timestamps. [Source log](source.log).

The canonical evidence retains **7 angular (l,j) rows**, **56 Gaussian rows on two grids**,
**42 full-F and 42 modified-F real Mg quadrature rows**, and **8 Si action rows**.
The independent CG ladder and L·S projector/kernel references remain distinct from production:
[mathematical reference](../../tests/relativistic/angular_reference.jl),
[conventions](../../prototypes/relativistic/CONVENTIONS.md),
[fixed settings](../../prototypes/relativistic/phase6a.toml).

Maximum Gaussian normalized full-F error: **{max(x['normalized_error'] for x in d['synthetic']['gaussian'])}**.
Maximum real-Mg modified-F quadrature sensitivity: **{d['radial']['max_quadrature_sensitivity']}**.
These measure different things: the real-Mg difference is not a strict error bound. The two
independent trapezoidal sums follow different floating arithmetic routes and are both retained;
modified-F additionally carries the nonzero l>0 origin limit. Real Mg covers l=0,1; l=2,3 is synthetic.

The Mg spin-flip block norm is **{d['mg']['spin_flip_block_norm']}**, with imaginary norm
**{d['mg']['spin_flip_imaginary_norm']}**. Small signals remain visible alongside normalized errors.
Channel labels and raw/internal D, reciprocal coordinates, two-path energy and all operator
checks are retained. Public angular error rows permit table aggregation; they are not full
CG matrices. Original P/D/X/kernel readback did not recheck unretained translation/volume/multiatom states.
"""
    else:
        e=d['mg_energy'];fail=d['resolved_gamma_failure'];cor=d['historical_summary_correction']
        body=f"""# Full relativistic Hamiltonian and energy

Run `{d['run']['run_id']}` solved three fixed-density Mg k-point problems,
16 target states each. All **48 target eigenvalues and direct residuals**, seven energy terms,
spin decomposition and three +/- finite-difference steps remain in the canonical evidence.
The six common DFTK terms exclude native nonlocal; the full operator adds one FR nonlocal term.
[Source log](source.log), [implementation](../../prototypes/fr_integration/README.md),
[fixed settings](../../prototypes/fr_integration/phase6b.toml).

The energy of solved orbitals at their own n_X is **{e['from_solved_fixed_density_orbitals']['total_ha']} Ha/cell**.
It is not a self-consistent energy: n_X−n_ref L2 is **{e['n_X_minus_n_ref_l2']}**,
and the current-H expectation minus the old-reference eigenvalue sum is
**{e['current_H_expectation_minus_old_eigenvalue_sum_ha']} Ha**. These discrepancies are retained
because they establish why energy must use the orbitals' own density.

The general-complex fixture has nonlocal cross energy
**{e['general_complex_fixture']['nonlocal']['cross_ha']} Ha/cell**; the solved-orbital cross term is
**{e['from_solved_fixed_density_orbitals']['nonlocal']['cross_ha']} Ha/cell**. The independent full/diagonal/cross
values and nonzero spin-rotation response are retained, not only normalized errors.

The Si test uses the original real scalar input with synthetic complete degenerate j branches,
LDA/NLCC and no new Si SCF. Its recorded full-H action maximum is
**{d['si_scalar_limit']['action']['max_error']}**.

## Resolved defects and historical prose correction

Failed attempt `{fail['run_id']}` exited {fail['exit_code']}:
`{fail['failure_reason']}`. The signed-zero Gamma dictionary key stopped full-H checks after
the Si stage passed; Mg eigensolves were **{fail['fixed_density_eigensolve_status']}**. The later successful run
performed the three solves once, after the Gamma/T² regression fixed the key representation.
The failure receipt and executed source identity remain public.

The [historical report](https://github.com/xxs4661/dftk-soc-workbench/blob/{BASE}/results/phase6b-review.md)
displayed Si action error `{cor['historical_display']}`; the final JSON actually records
`{cor['canonical_value']}`. This page uses the latter without changing historical numerical data.
An earlier common-data rejection confused raw header whitespace with frozen-parser functional
normalization; current source-bound checks and regressions preserve the correct distinction.

This phase did not run SOC SCF, QE SOC, magnetic XC or physical convergence scans.
Diagnostic first-ten-per-k occupations did not establish global ground-state filling.
"""
    return body + common


def serialize_evidence(evidence):
    """One compact line per SCF map; other scientific sections remain indented."""
    if "scf" not in evidence:
        return json.dumps(evidence, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    display = dict(evidence)
    display["scf"] = dict(evidence["scf"])
    display["scf"]["runs"] = dict(evidence["scf"]["runs"])
    replacements = {}
    for name in ("A", "B"):
        display["scf"]["runs"][name] = dict(evidence["scf"]["runs"][name])
        token = "CURATED_MAP_ROWS_" + name
        display["scf"]["runs"][name]["maps"] = token
        replacements[json.dumps(token)] = "[\n          " + ",\n          ".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            for row in evidence["scf"]["runs"][name]["maps"]) + "\n        ]"
    rendered = json.dumps(display, indent=2, ensure_ascii=False, allow_nan=False)
    for token, rows in replacements.items():
        require(rendered.count(token) == 1, "Serialization marker collision")
        rendered = rendered.replace(token, rows)
    require(json.loads(rendered) == evidence, "Public serialization changed data")
    return rendered + "\n"


def export(root):
    root = Path(root)
    shared = json.loads((root / ENVIRONMENT).read_text())
    cache = {}
    def raw(path):
        if path not in cache:
            require(path in {p for ps in SOURCES.values() for p in ps}, "Source outside whitelist")
            cache[path] = subprocess.check_output(["git", "-C", str(root), "show", f"{BASE}:{path}"])
        return cache[path]
    def load(path):
        return json.loads(raw(path))
    output = {}
    a = load("results/phase5a/real-b0.json")
    b = load("results/phase5b/real-abc.json")
    fixed = select(a, "layout pseudo parallelism case basis scalar_scf scalar_reference "
        "spinor_occupations scalar_occupations fixed_h_band_energy spinor_kpoints density acceptance")
    fixed["run"] = receipt(root, a, SOURCES["spinor-no-soc"][0], shared)
    fixed["settings"] = settings_reference(root, "5A", a["predeclared_settings"])
    # Pairwise difference arrays are deterministic views of the two retained spectra.
    for k in fixed["spinor_kpoints"]:
        del k["spectrum_difference_ha"]
        del k["scalar_repeated_oracle_ha"]
    scf = select(b, "initialization finite_difference run_order")
    scf["run"] = receipt(root, b, SOURCES["spinor-no-soc"][1], shared)
    scf["settings"] = settings_reference(root, "5B", b["settings"])
    scf["input"] = {k: v for k, v in b["provenance"].items() if k not in ("environment", "base_commit")}
    scf["runs"] = {}
    for name in ("A", "B"):
        run = b["runs"][name]
        end = select(run, "status map_count initial_density_sha256 seed density")
        fd = run["final_map"]["diagnostics"]
        end["endpoint"] = select(fd, "per_k occupations self_density_h_rayleigh_residuals_ha "
            "self_density_h_rayleigh_values_ha rayleigh_note self_density_h_old_lambda_residuals_ha")
        rows = [json.loads(line) for line in raw(f"results/phase5b/maps-{name}.jsonl").splitlines()]
        contexts = []
        end["maps"] = [compact_map(row, contexts) for row in rows]
        end["solver_contexts"] = contexts
        end["solver_context_index_convention"] = "Zero-based index; every map's original context checked for exact equality before grouping"
        end["initial_solver_diagnostics"] = [select(k,
            "index initial_orthogonality_frobenius initial_component_norm_min "
            "initial_component_norm_max initial_imaginary_norm")
            for k in rows[0]["diagnostics"]["per_k_summary"]]
        scf["runs"][name] = end
    scf["runs"]["C"] = b["runs"]["C"]
    scf["comparison"] = select(b["comparison"], "status a_vs_b_density_relative_l2 gates")
    scf["comparison"]["density_checks"] = {name: {k: v for k, v in c.items()
        if "density" in k} for name, c in b["comparison"]["comparisons"].items()}
    synthetic = load("results/phase5b/new-test-evidence.json")
    # Controller fault messages are preserved by executable fixtures, not copied journals.
    output["spinor-no-soc"] = {"fixed_h": fixed, "scf": scf,
        "synthetic_energy_checks": synthetic["energy"],
        "limitations": ["5A tests a fixed scalar Hamiltonian lift; 5B independently executes charge-only spinor A/B SCF and native scalar C.",
            "No SOC in these runs, no magnetic XC, no QE SOC comparison or physical cutoff/k convergence.",
            "Density, occupied-subspace and explicit-vector residual norms are original runtime measurements. Public hashes do not reproduce absent orbitals/densities.",
            "E[orbitals,n_out] is the seven-term total; fixed-H band expectation is a different quantity. No Phase4C reference constant was applied.",
            "The native scalar log may show -Inf for log10 of zero energy change; total energies are finite."]}
    r = load("results/phase6a/real-mg-si.json")
    t = load("results/phase6a/tests-final.json")
    output["relativistic-projectors"] = select(r, "input metadata channel_provenance channels "
        "d_raw_parsed d_internal angular radial mg scalar_si original_dftk_constructor")
    output["relativistic-projectors"].update({"run": receipt(root, r, SOURCES["relativistic-projectors"][0], shared),
        "settings": settings_reference(root, "6A", r["settings"]),
        "synthetic": {"angular": t["angular"], "operator": t["operator"],
            "gaussian": t["channels_radial"]["gaussian"],
            "real_mg_full_F_quadrature": t["channels_radial"]["mg_radial"]},
        "test_receipt": select(t, "started_utc finished_utc exit_code execution_status settings_sha256 executed_source_sha256 scope"),
        "limitations": ["Real Mg PBEsol has l=0,1 channels; l=2,3 coverage is synthetic, not another physical input.",
            "The 39-q Mg kernel is an algebraic probe, not a physical Mg SCF or cross-k Hamiltonian.",
            "Gaussian analytic errors and real Mg two-quadrature sensitivity are distinct; the latter is not an error bound.",
            "Full-F and modified-F independent trapezoidal sums use different arithmetic routes; retain both original 42-row tables, including nonzero l>0 origin limits in modified-F.",
            "Seven angular error/trace rows permit table aggregation. Independent matrix-level verification uses the retained CG and L.S implementations; errors or hashes do not contain the matrices.",
            "Mg kernel/TR and Si action errors require original P/D/X/K or orbitals for independent array recomputation. Those binary artifacts remain local; this checker recomputes table arithmetic only.",
            "Original readback did not recompute unretained translation, volume and multiatom matrices.",
            "Run ID contains 164800 but actual execution began16:22:47.274UTC; timestamps remain the original recorded values."]})
    h = load("results/phase6b/real-mg-si.json")
    ht = load("results/phase6b/tests-final.json")
    failed = load("results/phase6b/attempts/gamma-key-error.json")
    hr = select(h, "input si_common eigensolves variational full_hamiltonian mg_reference_density "
        "parallelism spin_rotation spectrum_symmetry basis si_scalar_limit mg_energy raw_artifacts_sha256")
    hr.update({"run": receipt(root, h, SOURCES["fr-hamiltonian-energy"][0], shared),
        "settings": settings_reference(root, "6B", h["settings"]),
        "synthetic": select(ht, "common hamiltonian energy runtime"),
        "test_receipt": select(ht, "run_id started_utc finished_utc exit_code execution_status settings_sha256 executed_source_sha256 test_counts scope"),
        "regression_6a_receipt": select(load("results/phase6b/phase6a-regression.json"),
            "started_utc finished_utc exit_code execution_status settings_sha256 executed_source_sha256 scope"),
        "resolved_gamma_failure": select(failed, "run_id started_utc finished_utc exit_code execution_status "
            "failure_reason fixed_density_eigensolve_status full_hamiltonian_status scalar_limit_integration_status "
            "same_source_consistency_status workbench_head_at_execution executed_source_sha256"),
        "historical_summary_correction": {"original_path": "results/phase6b-review.md", "original_line": 134,
            "historical_display": "3.997e-17", "canonical_pointer": "/si_scalar_limit/action/max_error",
            "canonical_value": h["si_scalar_limit"]["action"]["max_error"],
            "note": "The old prose value differs from the final result. This curated summary uses the original final JSON; no scientific result is changed."},
        "limitations": ["Three actual fixed-density Mg eigensolves; no SOC SCF in this phase. Diagnostic first10-per-k occupations do not establish a global ground-state filling.",
            "Main energy is E[X,f] at the orbitals' own n_X, not at prescribed n_ref and not a self-consistent energy. The large density and old-H-band differences are retained.",
            "Native Si comparison is a synthetic complete scalar-degenerate FR construction using the real scalar Si input; no physical FR Si or new Si SCF.",
            "Small spin cross energies and spin rotation signals are retained alongside normalized errors.",
            "Gamma signed-zero mapping failure completed the Si stage but stopped before Mg eigensolves; the later successful run performed the three solves once. Regression covers the resolved key defect.",
            "Earlier common-data rejection confused raw header whitespace and frozen-parser functional normalization; the retained implementation/tests validate the normalized functional while retaining source binding.",
            "No QE SOC numerical reference, magnetic XC, physical parameter convergence or upstream native spinor support established here.",
            "Density, full-H action and eigenvector residual norms are original runtime-reported quantities; independent array revalidation needs local raw states or physical rerun."]})
    require(all(load("results/phase6b/phase6a-regression.json")[k] == t[k]
                for k in ("angular", "operator", "channels_radial")), "6A rerun numerical payload differs")
    output["fr-hamiltonian-energy"] = hr
    for case, evidence in output.items():
        evidence["schema_version"] = 1
        evidence["provenance"] = {"curation_base": BASE,
            "executed_version_note": "Historical execution HEAD and executed file hashes are preserved separately; curation is not a new numerical run.",
            "extractor": {"path": SELF, "sha256": digest((root / SELF).read_bytes())},
            "sources": [source_record(p, raw(p)) for p in SOURCES[case]],
            "selection": "Strict field whitelist; original numeric values copied without rounding or unit changes; duplicate views omitted only where retained inputs permit recomputation.",
            "source_logs": {name: digest(raw(p)) for name, p in LOGS[case].items()}}
        finite_tree(evidence)
        directory = root / "results" / case
        directory.mkdir(parents=True, exist_ok=True)
        for name, path in LOGS[case].items():
            (directory / name).write_bytes(raw(path))
        (directory / "evidence.json").write_text(serialize_evidence(evidence))
        (directory / "README.md").write_text(readme(case, evidence))
    return {case: {"sha256": digest((root / "results" / case / "evidence.json").read_bytes())}
            for case in CASES}


def check(root):
    """Public-files-only arithmetic and identity checks; no Git or private data."""
    root = Path(root)
    docs = {case: json.loads((root / "results" / case / "evidence.json").read_text()) for case in CASES}
    for case, d in docs.items():
        finite_tree(d)
        require((root / "results" / case / "README.md").read_text() == readme(case, d), "README differs from canonical numbers/conventions")
        require(d["schema_version"] == 1 and d["provenance"]["curation_base"] == BASE, "Wrong evidence schema/base")
        require(digest((root / SELF).read_bytes()) == d["provenance"]["extractor"]["sha256"], "Extractor identity changed")
        for name, expected in d["provenance"]["source_logs"].items():
            require(digest((root / "results" / case / name).read_bytes()) == expected, "Source log changed")
    s, r, h = (docs[x] for x in CASES)
    for d in (s["fixed_h"], s["scf"], r, h):
        ref = d["settings"]
        require(digest((root / ref["path"]).read_bytes()) == ref["sha256"], "Fixed settings changed")
        env = d["run"]["environment_check"]
        require(digest((root / env["path"]).read_bytes()) == env["sha256"] and env["status"] == "PASS", "Environment identity reference changed")
        require(d["run"]["execution_status"] == "PASS" and d["run"]["exit_code"] == 0, "Historical real run is not successful")
    report = {"status": "PASS", "scope": "Offline table arithmetic and source identity only; no SCF/QE/Julia or raw-array revalidation", "cases": {}}
    fixed = s["fixed_h"]
    require(len(fixed["spinor_kpoints"]) == 8, "5A k-point loss")
    scalar = fixed["scalar_reference"]["eigenvalues_with_auxiliary_ha"]
    pairmax = 0.0
    for k, ref in zip(fixed["spinor_kpoints"], scalar):
        require(len(k["eigenvalues_ha"]) == len(k["explicit_residuals_ha"]) == 16, "5A target loss")
        pairmax = max(pairmax, max(abs(e-ref[i//2]) for i,e in enumerate(k["eigenvalues_ha"])))
    fb = fixed["fixed_h_band_energy"]
    spinband = sum(k["weight_spatial"] * sum(e*f for e,f in zip(k["eigenvalues_ha"],occ))
                   for k,occ in zip(fixed["spinor_kpoints"],fixed["spinor_occupations"]["occupations"]))
    close(spinband, fb["spinor_occupied_eigenvalue_sum_ha_cell"], "5A band energy", 1e-14)
    mapsreport = {}
    b = s["scf"]
    require(b["run_order"] == ["A", "B", "C"] and set(b["runs"]) == {"A","B","C"}, "Independent run lost")
    require(b["runs"]["A"]["seed"] != b["runs"]["B"]["seed"], "Independent seeds lost")
    c = b["runs"]["C"]
    for name in ("A", "B"):
        run = b["runs"][name]; rows = run["maps"]
        require(len(rows) == run["map_count"] == 53, "A/B full history missing")
        require([x["map_index"] for x in rows] == list(range(1,54)), "Map order missing")
        require(rows[-1]["map_role"] == "closure" and rows[-1]["closure_checks_passed"], "Closure missing")
        for i,x in enumerate(rows):
            z = x["diagnostics"]
            context = run["solver_contexts"][x["solver_context_index"]]
            require(len(context) == len(z["per_k"]) == 8 and
                    [k["index"] for k in context] == [k["index"] for k in z["per_k"]],
                    "Per-map grouped solver context mismatch")
            require(x["n_in"]["sha256"] == z["consumed_input_sha256"] and x["n_out"]["sha256"] == z["orbital_density_sha256"], "Map ownership mismatch")
            if i:
                require(rows[i-1]["n_next"]["sha256"] == x["n_in"]["sha256"], "Feedback chain broken")
            close(x["mixed_step_l2"], x["alpha"]*x["unmixed_residual_l2"], "Mixed versus unmixed step", 1e-14)
            terms=z["energy_terms_ha"]
            require(set(terms) == {"Kinetic","AtomicLocal","AtomicNonlocal","Hartree","Xc","Ewald","PspCorrection"}, "Energy term loss")
            close(sum(terms.values()),z["energy_total_ha"],"5B seven terms",1e-12)
            ec=z["energy_checks"]
            dc=ec["band_expectation_ha"]-terms["Hartree"]-ec["integral_n_vxc_ha"]+terms["Xc"]+terms["Ewald"]+terms["PspCorrection"]
            close(dc,ec["double_counting_total_ha"],"5B double counting",1e-12)
        ks=run["endpoint"]["per_k"]
        require(len(ks)==8 and all(len(k["eigenvalues_ha"])==22 and len(k["explicit_residuals_ha"])==16 for k in ks),"5B endpoint target loss")
        spec=max(abs(e-c["eigenvalues_ha"][ik][i//2]) for ik,k in enumerate(ks) for i,e in enumerate(k["eigenvalues_ha"][:16]))
        close(spec,b["comparison"]["gates"][name+"_raw_spectrum_vs_scalar"]["measured"],"5B spectrum difference",1e-18)
        mapsreport[name]={"maps":len(rows),"hash_links":len(rows)-1,"final_unmixed_l2":rows[-1]["unmixed_residual_l2"],"raw_spectrum_max_ha":spec,"energy_ha":rows[-1]["diagnostics"]["energy_total_ha"]}
    fd5=[]
    require(len(b["finite_difference"]["steps"])==3,"5B finite-difference row loss")
    for x in b["finite_difference"]["steps"]:
        v=(x["energy_plus_ha_cell"]-x["energy_minus_ha_cell"])/(2*x["step_rad"])
        close(v,x["numeric_ha_per_rad"],"5B finite difference",0)
        fd5.append({"h_rad":x["step_rad"],"numeric_ha_per_rad":v,"absolute_error":abs(v-x["analytic_ha_per_rad"])})
    report["cases"][CASES[0]]={"fixed_h_spectrum_max_ha":pairmax,"fixed_h_band_eigenvalue_sum_ha":spinband,"A_B":mapsreport,"finite_difference":fd5}
    angular=r["angular"]["records"]
    require([(x["l"],x["two_j"]) for x in angular]==[(0,1),(1,1),(1,3),(2,3),(2,5),(3,5),(3,7)],"Angular rows lost")
    angularmax=max(v for x in angular for k,v in x.items() if k not in ("l","two_j","trace_projector"))
    close(angularmax,r["angular"]["max_error"],"Angular maximum",0)
    for x in angular:close(x["trace_projector"],x["two_j"]+1,"Angular projector trace",2e-15)
    cfg=tomllib.loads((root/r["settings"]["path"]).read_text())
    gaussian=r["synthetic"]["gaussian"]
    require(len(gaussian)==56,"Gaussian row loss")
    require({x["grid_points"] for x in gaussian}==set(cfg["gaussian"]["points"]),"Gaussian grid loss")
    for x in gaussian:
        a=cfg["gaussian"]["a_bohr_minus2"];l=x["l"];q=x["q"]
        analytic=q**l*4*math.pi*math.sqrt(math.pi)/(2.0**(l+2)*a**(l+1.5))*math.exp(-q*q/(4*a))
        close(analytic,x["analytic_F"],"Gaussian analytic formula",1e-13)
        error=abs(x["actual_F"]-x["analytic_F"])/max(abs(x["actual_F"]),abs(x["analytic_F"]),1)
        close(error,x["normalized_error"],"Gaussian error arithmetic",1e-30)
    radial=r["radial"]["values"];full=r["synthetic"]["real_mg_full_F_quadrature"]
    require(len(radial)==len(full)==42,"Real Mg quadrature row loss")
    for x,y in zip(radial,full):
        require(x["channel_position"]==y["channel_position"] and x["q_bohr_minus1"]==y["q"],"Radial association changed")
        close(x["F"],y["production_F"],"Production radial value changed",0)
        diff=x["F_over_q_l"]-x["trapezoidal_F_over_q_l"]
        close(diff,x["quadrature_difference"],"Modified radial difference",0)
        error=abs(diff)/max(abs(x["F_over_q_l"]),abs(x["trapezoidal_F_over_q_l"]),1)
        close(error,x["normalized_quadrature_difference"],"Modified radial normalized difference",1e-25)
        error=abs(y["production_F"]-y["independent_trapezoidal_F"])/max(abs(y["production_F"]),abs(y["independent_trapezoidal_F"]),1)
        close(error,y["quadrature_normalized_difference"],"Full radial normalized difference",1e-25)
    sensitivity=max(x["normalized_quadrature_difference"] for x in radial)
    close(sensitivity,r["radial"]["max_quadrature_sensitivity"],"Radial sensitivity maximum",0)
    require(len(r["scalar_si"]["rows"])==8,"Si scalar-limit k loss")
    report["cases"][CASES[1]]={"angular_rows":7,"angular_maximum":angularmax,"gaussian_rows":56,
        "gaussian_maximum":max(x["normalized_error"] for x in gaussian),"real_radial_rows_each":42,
        "real_modified_quadrature_sensitivity":sensitivity,"array_errors":"RUNTIME_REPORTED; not independently recomputed from hashes"}
    require(len(h["eigensolves"])==3,"Mg physical k loss")
    for k in h["eigensolves"]:require(len(k["eigenvalues_ha"])==len(k["explicit_residuals_ha"])==16,"Mg target loss")
    levels=[k["eigenvalues_ha"] for k in h["eigensolves"]]
    gamma=max(abs(levels[0][i]-levels[0][i+1]) for i in range(0,16,2));pm=max(abs(a-b) for a,b in zip(levels[1],levels[2]))
    close(gamma,h["spectrum_symmetry"]["gamma_kramers_max_ha"],"Gamma spectrum",0)
    close(pm,h["spectrum_symmetry"]["plus_minus_spectrum_max_ha"],"Paired-k spectrum",0)
    energies={}
    for name,x in [("Mg_solved_at_nX",h["mg_energy"]["from_solved_fixed_density_orbitals"]),("Mg_complex_fixture",h["mg_energy"]["general_complex_fixture"]),("Si_scalar_limit",h["si_scalar_limit"]["energy"])]:
        require(len(x["terms_ha"])==7,"FR energy term loss")
        close(sum(x["terms_ha"].values()),x["total_ha"],"FR total sum",1e-12)
        energies[name]=x["total_ha"]
    fd6=[]
    require(len(h["variational"]["samples"])==3,"FR finite-difference rows lost")
    for x in h["variational"]["samples"]:
        rec={"h_rad":x["h_rad"]}
        for q in ("total","nonlocal"):
            v=(x["plus_"+q+"_ha"]-x["minus_"+q+"_ha"])/(2*x["h_rad"])
            close(v,x["numeric_"+q+"_ha_per_rad"],"FR finite difference",0)
            rec[q+"_ha_per_rad"]=v
        fd6.append(rec)
    require(h["resolved_gamma_failure"]["exit_code"]!=0 and h["resolved_gamma_failure"]["fixed_density_eigensolve_status"]=="NOT_RUN","Failed attempt changed meaning")
    close(h["historical_summary_correction"]["canonical_value"],h["si_scalar_limit"]["action"]["max_error"],"Historical prose correction",0)
    report["cases"][CASES[2]]={"eigenpairs":48,"gamma_pair_max_ha":gamma,"paired_k_max_ha":pm,
        "energies_ha_cell":energies,"finite_difference":fd6,
        "si_full_action_reported_error":h["si_scalar_limit"]["action"]["max_error"]}
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check",action="store_true",help="Check public evidence only; no Git/private inputs")
    args=parser.parse_args()
    try:
        result=check(args.root) if args.check else export(args.root)
        print(json.dumps(result,indent=2,allow_nan=False))
    except (OSError,ValueError,KeyError,TypeError,subprocess.CalledProcessError) as error:
        print(json.dumps({"status":"FAIL","reason":str(error)}))
        return 1
    return 0


if __name__=="__main__":
    raise SystemExit(main())
