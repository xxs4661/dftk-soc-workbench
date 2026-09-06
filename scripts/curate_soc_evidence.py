#!/usr/bin/env python3
"""Curate the two existing Mg runs; check public evidence without Julia or .work.

Python >=3.11, standard library only. Export requires the verified original
Phase 6C files and never executes a scientific calculation. Check is portable.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib

SNAPSHOT = "8658992afa936f6cdb1a8055699ae9aa47b32297"
RUNS = {"A": "20260906T151940Z-A-270110aa", "B": "20260906T153016Z-B-62835d43"}
COMPARE = "20260906T154035Z-compare-f24619d0"
OLD = Path("results/phase6c")
DEST = Path("results/mg-soc-scf")
ENV = Path("results/shared/environment.json")
CONFIG = Path("prototypes/soc_scf/phase6c.toml")
TERMS = {"Kinetic", "AtomicLocal", "AtomicNonlocalFR", "Hartree", "Xc", "Ewald", "PspCorrection"}
TEXT = {"map_role", "status", "next_density_source", "failure_reason", "n_in_sha256",
        "n_out_sha256", "n_next_sha256", "mu_selection_rule", "band_status",
        "occupation_stationarity_status"}
MAP_TOP = ("map_index", "map_role", "status", "alpha", "density_candidate", "closure_checks_passed",
           "next_density_source", "unmixed_residual_l2", "mixed_step_l2", "actual_next_step_l2")
MAP_DIAG = ("target_states", "max_input_h_residual_ha", "max_gram_norm", "max_self_density_h_residual_ha",
            "max_self_rayleigh_residual_ha", "internal_energy_ha", "entropy_dimensionless", "entropy_energy_ha",
            "free_energy_ha", "free_energy_arithmetic_error_ha", "orbital_electron_count",
            "pauli_density_relative_l2", "energy_terms_ha", "magnetization_integral")
ROOT_FIELDS = ("mu_ha", "electron_residual", "electrons_per_k_unweighted", "electrons_per_k_weighted",
               "occupation_minimum", "occupation_maximum", "numerical_plateau", "mu_selection_rule",
               "highest_two", "iterations")
DC_FIELDS = ("band_expectation_ha", "integral_n_vxc_ha", "double_counting_difference_ha",
             "energy_term_sum_difference_ha")
SOLVER_FIELDS = ("k_index", "target_states", "auxiliary_states", "ng", "converged", "iterations",
                 "solver_n_matvec", "explicit_residuals_ha", "orthogonality_frobenius")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def selected_map(raw):
    """Explicit scientific-column whitelist; all 191 source records are retained."""
    d = raw["diagnostics"]
    row = {k: raw[k] for k in MAP_TOP}
    row["failure_reason"] = raw.get("failure_reason", "")
    for name in ("n_in", "n_out", "n_next"):
        for field in ("sha256", "electron_count"):
            row[name + "_" + field] = raw[name][field]
    row.update({k: d[k] for k in MAP_DIAG})
    row.update({k: d["occupations"][k] for k in ROOT_FIELDS})
    row.update({k: d["energy_checks"][k] for k in DC_FIELDS})
    row["occupation_stationarity_status"] = d["occupation_stationarity"]["status"]
    row["occupation_stationarity_checked_states"] = d["occupation_stationarity"]["checked_states"]
    row["band_status"] = d["band_completeness"]["status"]
    row["rayleigh_occupation_max_difference"] = d["rayleigh_occupations"]["max_occupation_difference"]
    attempts = d["band_attempts"]
    records = [r for a in attempts for r in a["per_k"]]
    row["band_attempt_targets"] = [a["target"] for a in attempts]
    row["solve_count"] = len(records)
    row["sum_solver_iterations"] = sum(r["iterations"] for r in records)
    row["sum_solver_n_matvec"] = sum(r["solver_n_matvec"] for r in records)
    row["max_solver_iterations"] = max(r["iterations"] for r in records)
    return row


def read_maps(path):
    with Path(path).open(newline="") as stream:
        return [{k: v if k in TEXT else json.loads(v) for k, v in row.items()}
                for row in csv.DictReader(stream)]


def endpoint(raw):
    """Near-native final payload; only large repeated solver/debug fields are cut."""
    result = {k: v for k, v in raw["final"].items() if k != "diagnostics"}
    d = raw["final"]["diagnostics"]
    omitted = {"band_attempts", "potential_sha256", "potential_norm", "potential_change_norm",
               "probe_action_sha256", "probe_action_norm"}
    result["diagnostics"] = {k: v for k, v in d.items() if k not in omitted}
    last = d["band_attempts"][-1]
    result["solver_records"] = [{k: r[k] for k in SOLVER_FIELDS} for r in last["per_k"]]
    require([r["eigenvalues_ha"] for r in last["per_k"]] == result["eigenvalues_ha"],
            "Final solve and formal eigenvalues disagree")
    result["time_reversal"] = raw["time_reversal"]
    return result


def source(root, relative, published=True):
    value = {"path": str(relative), "sha256": sha(root / relative), "bytes": (root / relative).stat().st_size}
    if published:
        value["commit"] = SNAPSHOT
        value["blob"] = subprocess.check_output(
            ["git", "rev-parse", f"{SNAPSHOT}:{relative}"], cwd=root, text=True).strip()
        historical = subprocess.check_output(["git", "cat-file", "blob", value["blob"]], cwd=root)
        require((root/relative).read_bytes() == historical,
                f"Published source bytes differ from accepted snapshot: {relative}")
    return value


def close(a, b, atol, message):
    require(math.isfinite(a) and math.isfinite(b) and abs(a-b) <= atol, message)


def seven_term_check(terms, E, band, nvxc, atol):
    require(set(terms) == TERMS, "Seven internal-energy terms changed")
    summed = math.fsum(terms.values())
    dc = band - terms["Hartree"] - nvxc + terms["Xc"] + terms["Ewald"] + terms["PspCorrection"]
    close(summed, E, atol, "Seven-term energy sum differs")
    close(dc, E, atol, "Occupied-H double-counting algebra differs")
    return summed-E, dc-E


def render_readme(a, b):
    da, db = a["diagnostics"], b["diagnostics"]
    lines = ["# Charge-only Mg SOC self-consistency", "",
        "Two independent initial densities reached the declared engineering gates for one Mg FR-NC PBEsol case. "
        "This is a restricted workbench prototype; numerical review remains **REVIEW_REQUIRED**. "
        "QE SOC comparison is **NOT_RUN**; its input is only **PREPARED_NOT_EXECUTED**.", "",
        "The cell has one ten-valence-electron Mg in a 10 bohr cube, Ecut=15 Ha, Gamma and the explicit opposite k pair, "
        "each with spatial weight 1/3. Actual FFT is 40×40×40. Electronic tau=0.001 Ha uses one global Fermi root "
        "and capacity one per physical spinor state; only charge density feeds back.", "",
        "| Recorded quantity | A | B |", "| --- | ---: | ---: |",
        f"| All density maps, including one additional closure | {a['map_count']} | {b['map_count']} |",
        f"| Physical target states per k | {a['target_states']} | {b['target_states']} |",
        f"| Unmixed final density L2 | {a['unmixed_residual_l2']} | {b['unmixed_residual_l2']} |"]
    for title, key in (("Internal E / Ha per cell", "internal_energy_ha"),
                       ("S/kB", "entropy_dimensionless"), ("-TS / Ha per cell", "entropy_energy_ha"),
                       ("F / Ha per cell", "free_energy_ha")):
        lines.append(f"| {title} | {da[key]} | {db[key]} |")
    lines += ["", "The table is generated and checked against the canonical endpoints. "
        "The tiny nonzero entropy is retained even though Float64 F equals E. "
        "No real occupations were far enough from zero/one for the logarithmic stationarity diagnostic "
        "(0 checked, 72 excluded per run). Fractional-occupation stationarity and 24→48 expansion are synthetic-test coverage; "
        "real expansion was not triggered.", "",
        "- Canonical data: [A endpoint](A/endpoint.json), [A all 191 maps](A/maps.csv), "
        "[B endpoint](B/endpoint.json), [B all 191 maps](B/maps.csv), [comparison](comparison.json).",
        "- Near-native source streams: [A engine output](A/engine.log), [B engine output](B/engine.log); "
        "all original map lines and closure are retained, not regenerated from a PASS summary.",
        "- [Case provenance](evidence.json) binds the original run IDs, exact executed source hashes, "
        "settings, original source fields, validation scopes and each run's start/end environment checks. "
        "The shared [environment identity](../shared/environment.json) and frozen "
        "[configuration](../../prototypes/soc_scf/phase6c.toml) each have one authority.", "",
        "Formal eigenvalues/f come from the actual closure solve H[n_in]. The full H[n_out] action, "
        "old-lambda residuals and Rayleigh/f feedback are separate diagnostics, not another diagonalization. "
        "All 24 states at each of three k points retain both solve-H and own-density residual vectors. "
        "The seven-term E uses the same X/f/n_out; physical-spinor entropy enters once.", "",
        "Public-only offline check (Python ≥3.11, standard library; no Julia, UPF, cache, SCF or QE):", "",
        "```sh", "python3 scripts/curate_soc_evidence.py check", "```", "",
        "This recomputes energy/DC/F algebra for every map, endpoint weighted counts and entropy, "
        "Gamma/opposite-k spectra and A/B raw spectral and E/F differences. It checks reported residual thresholds "
        "and hash-chain continuity, but cannot recreate densities or orbitals from hashes. "
        "Density differences, Pauli norms, Gram/H residuals, TR actions and energy contractions remain "
        "**runner-reported measurements requiring arrays or physical rerun**. Reassociated sums can differ in their "
        "last bits; original values are never replaced.", "",
        "The [SCF entry](../../prototypes/soc_scf/README.md) describes physical rerunning with the frozen environment "
        "and exact licensed UPF. The [prepared QE input](../../benchmarks/mg-soc-fermi/qe.in) is not an execution result. "
        "No cutoff/k/temperature convergence, unique ground state, noncollinear magnetic XC, upstream-native SOC, "
        "GPU/AD or independent expert validation is claimed. The next scientific gate is the first independent QE SOC E/F comparison.", ""]
    return "\n".join(lines)


def check(root, *, dataset=None):
    """Recompute public scalar/vector arithmetic; never attest unavailable arrays."""
    root = Path(root)
    data = root / DEST if dataset is None else Path(dataset)
    e = read(data / "evidence.json")
    require(sha(root/e["export"]["script"]) == e["export"]["script_sha256"], "Curated extractor/checker identity differs")
    require(sha(root / ENV) == e["environment"]["sha256"], "Shared environment hash differs")
    require(sha(root / CONFIG) == e["settings"]["sha256"], "Frozen settings hash differs")
    settings = tomllib.loads((root / CONFIG).read_text())
    threshold = settings["thresholds"]
    tau, ne = settings["ensemble"]["tau_ha"], e["basis"]["n_electrons"]
    weights = [k["weight_spatial"] for k in e["basis"]["kpoints"]]
    require(set(e["runs"]) == {"A", "B"} and sum(weights) == 1 and ne == 10, "Case/run identity differs")
    require([e["runs"][label]["initial"]["seed"] for label in ("A","B")] == [63001,64001], "Independent initial seeds changed")
    require(e["runs"]["A"]["initial"]["summary"]["sha256"] != e["runs"]["B"]["initial"]["summary"]["sha256"], "Independent initial density reports changed")
    for name, digest in e["public_sha256"].items():
        require(sha(data / name) == digest, f"Canonical evidence hash differs: {name}")
    output = {"status": "PASS", "scope": "Offline public-data arithmetic only; no SCF/QE or array reconstruction",
              "array_dependent_status": "RUNNER_REPORTED_REQUIRES_ARRAYS_OR_PHYSICAL_RERUN", "runs": {}}
    ends = {}
    for label in ("A", "B"):
        rows = read_maps(data / label / "maps.csv")
        require([r["map_index"] for r in rows] == list(range(1,192)), "Must retain all 191 maps")
        require([r["map_role"] for r in rows] == ["iteration"]*190+["closure"], "Closure history changed")
        require([r["status"] for r in rows] == ["CONTINUE"]*189+["CANDIDATE","PASS"], "Statuses changed")
        require(all(a["n_next_sha256"] == b["n_in_sha256"] for a,b in zip(rows, rows[1:])), "Reported hash chain broken")
        errors = []
        for r in rows:
            require(r["alpha"] == .1 and r["target_states"] == 24 and r["band_attempt_targets"] == [24], "Physical settings changed")
            require(r["solve_count"] == 3 and r["occupation_stationarity_checked_states"] == 0, "Actual scope differs")
            require(r["occupation_stationarity_status"] == "NO_RESOLVABLE_PARTIAL_OCCUPATIONS", "Saturated-state scope lost")
            require(r["band_status"] == "PASS" and max(map(max,r["highest_two"])) <= 1e-10, "Band-tail diagnostic failed")
            close(sum(r["electrons_per_k_weighted"]), ne, 1e-12, "Global recorded k shares differ")
            for field in ("n_in_electron_count", "n_out_electron_count", "n_next_electron_count", "orbital_electron_count"):
                close(r[field], ne, threshold["electron_count_abs"], "Recorded electron count fails")
            require(r["max_input_h_residual_ha"] <= threshold["residual_ha"] and r["max_gram_norm"] <= threshold["gram_norm"], "Recorded solver gate failed")
            require(abs(r["electron_residual"]) <= 1e-12, "Root residual failed")
            errors.append(seven_term_check(r["energy_terms_ha"], r["internal_energy_ha"], r["band_expectation_ha"],
                                           r["integral_n_vxc_ha"], threshold["energy_abs_ha"]))
            close(r["entropy_energy_ha"], -tau*r["entropy_dimensionless"], 1e-12*abs(r["entropy_energy_ha"]), "Entropy sign/value differs")
            close(r["free_energy_ha"], r["internal_energy_ha"]+r["entropy_energy_ha"],
                  1e-12*max(1,abs(r["free_energy_ha"]),abs(r["internal_energy_ha"])), "F arithmetic differs")
        last = rows[-1]
        require(last["unmixed_residual_l2"] <= threshold["density_fixedpoint_l2"] and last["closure_checks_passed"], "Recorded closure fails")
        x = read(data / label / "endpoint.json"); ends[label] = x
        d = x["diagnostics"]
        require(x["map_count"] == 191 and x["target_states"] == 24, "Endpoint count differs")
        require(x["n_in_sha256"] == last["n_in_sha256"] and x["n_out_sha256"] == last["n_out_sha256"], "Endpoint/map hash binding differs")
        for name in MAP_DIAG:
            require(d[name] == last[name], f"Endpoint/map scalar differs: {name}")
        eigen, occ = x["eigenvalues_ha"], x["occupations"]
        require(len(eigen) == len(occ) == len(x["solver_records"]) == 3, "Three k blocks required")
        entropy = 0.0
        for k, (levels, f, sr) in enumerate(zip(eigen, occ, x["solver_records"])):
            require(len(levels) == len(f) == len(sr["explicit_residuals_ha"]) == 24, "All 24 states must remain")
            require(levels == sorted(levels) and all(math.isfinite(v) for v in levels), "Invalid raw spectrum")
            require(all(math.isfinite(v) and 0 <= v <= 1 for v in f), "Invalid capacity-one occupations")
            require(sr["converged"] is True and sr["iterations"] > 0 and sr["auxiliary_states"] == 6, "Actual solver record differs")
            require(max(sr["explicit_residuals_ha"]) <= threshold["residual_ha"], "Recorded per-state solve residual failed")
            for fi in f:
                if 0 < fi < 1:
                    entropy -= weights[k]*(fi*math.log(fi)+(1-fi)*math.log1p(-fi))
            for key in ("self_density_h_old_lambda_residuals_ha", "self_density_h_rayleigh_residuals_ha", "self_density_h_rayleigh_values_ha"):
                require(len(d[key][k]) == 24 and all(math.isfinite(v) for v in d[key][k]), "Own-density state array incomplete")
        close(sum(w*sum(f) for w,f in zip(weights,occ)), ne, 1e-12, "Endpoint weighted occupation count differs")
        close(entropy, d["entropy_dimensionless"], 1e-12*abs(entropy), "Physical spinor entropy differs (tiny nonzero values retained)")
        paired_gamma = max(abs(eigen[0][i]-eigen[0][i+1]) for i in range(0,24,2))
        paired_pm = max(abs(a-b) for a,b in zip(eigen[1],eigen[2]))
        tr = x["time_reversal"]
        require(paired_gamma == tr["gamma_kramers_max_ha"] and paired_pm == tr["plus_minus_spectrum_max_ha"], "Recorded TR spectrum difference differs")
        require(paired_gamma <= threshold["kramers_ha"] and paired_pm <= threshold["time_reversed_spectrum_ha"], "Recorded spectral TR gate failed")
        for key, maximum_key in (("self_density_h_old_lambda_residuals_ha", "max_self_density_h_residual_ha"),
                                  ("self_density_h_rayleigh_residuals_ha", "max_self_rayleigh_residual_ha")):
            maximum = max(map(max,d[key]))
            require(maximum == d[maximum_key] and maximum <= threshold["self_density_residual_ha"], "Reported own-density residual gate differs")
        rqf = d["rayleigh_occupations"]["occupations"]
        rqf_difference = max(abs(a-b) for fa,fb in zip(occ,rqf) for a,b in zip(fa,fb))
        require(rqf_difference == d["rayleigh_occupations"]["max_occupation_difference"] and
                rqf_difference <= threshold["self_rayleigh_occupation_abs"], "Rayleigh occupation diagnostic differs")
        require(d["pauli_density_relative_l2"] <= threshold["pauli_density_relative"], "Reported Pauli gate failed")
        nl = d["nonlocal_decomposition"]
        close(nl["up_ha"]+nl["down_ha"]+nl["cross_ha"],nl["full_ha"],1e-11,"Reported FR interference decomposition differs")
        output["runs"][label] = {"maps": len(rows), "closure_maps": 1, "target_states": 24,
            "solve_count": sum(r["solve_count"] for r in rows),
            "solver_iterations": sum(r["sum_solver_iterations"] for r in rows),
            "solver_n_matvec": sum(r["sum_solver_n_matvec"] for r in rows),
            "recomputed_max_term_sum_error_ha": max(abs(v[0]) for v in errors),
            "recomputed_max_dc_error_ha": max(abs(v[1]) for v in errors),
            "recomputed_endpoint_entropy_dimensionless": entropy,
            "internal_energy_ha": d["internal_energy_ha"], "entropy_energy_ha": d["entropy_energy_ha"],
            "free_energy_ha": d["free_energy_ha"], "gamma_spectrum_max_ha": paired_gamma,
            "plus_minus_spectrum_max_ha": paired_pm}
    comparison = read(data / "comparison.json")
    c = comparison["recorded_comparison"]
    A,B = ends["A"],ends["B"]
    differences = [max(abs(a-b) for a,b in zip(ea[:16],eb[:16])) for ea,eb in zip(A["eigenvalues_ha"],B["eigenvalues_ha"])]
    require(c["kpoint_mapping_b_for_a"] == [1,2,3], "Expected matching physical k coordinates")
    require(differences == [r["max_abs_difference_ha"] for r in c["spectra_by_k"]], "A/B raw spectral comparison differs")
    require(max(differences) == c["max_raw_eigenvalue_difference_ha"], "A/B spectrum maximum differs")
    for prefix in ("internal_energy", "free_energy"):
        diff = abs(A["diagnostics"][prefix+"_ha"]-B["diagnostics"][prefix+"_ha"])
        require(diff == c[prefix+"_abs_difference_ha"], "A/B energy comparison differs")
    diagnostic = c["diagnostic_only"]
    f_difference = max(abs(a-b) for fa,fb in zip(A["occupations"],B["occupations"]) for a,b in zip(fa,fb))
    require(f_difference == diagnostic["shared_state_occupation_max_difference"], "A/B occupation difference differs")
    require(abs(A["mu_ha"]-B["mu_ha"]) == diagnostic["mu_abs_difference_ha"], "Recorded mu diagnostic differs")
    require(abs(A["diagnostics"]["entropy_dimensionless"]-B["diagnostics"]["entropy_dimensionless"]) ==
            diagnostic["entropy_abs_difference_dimensionless"], "A/B entropy diagnostic differs")
    require((data/"README.md").read_text() == render_readme(A,B), "README scientific values differ from canonical endpoints")
    output["max_raw_lowest16_difference_ha"] = max(differences)
    output["array_dependent_original_density_relative_l2"] = c["density_relative_l2"]
    return output


def export(root):
    """Export once from verified sources; verify field equality before publication."""
    root = Path(root)
    require(not (root/DEST).exists(), "Refusing an existing curated dataset")
    env = read(root/ENV)
    stage = Path(tempfile.mkdtemp(prefix=".mg-soc-curation-", dir=root/"results"))
    try:
        e = {"schema_version": 1, "case": "mg-soc-scf", "source_phase": "6C", "publication_snapshot": SNAPSHOT,
             "environment": {"path": str(ENV), "sha256": sha(root/ENV)},
             "settings": {"path": str(CONFIG), "sha256": sha(root/CONFIG), "commit": SNAPSHOT},
             "predeclaration": read(root/OLD/"preflight/settings-before-tests.json"),
             "runs": {}, "sources": {}, "public_sha256": {},
             "array_dependent_claims": "Density L2, Pauli density, Gram, H residuals/TR action and energy contractions are original runner measurements. Public hashes bind reported records; they do not reconstruct arrays.",
             "offline_arithmetic_scope": "Recompute all map energy/DC/F algebra and recorded gates, final physical-spinor entropy/weighted count, raw spectra and A/B E/F. No independent array-based validation.",
             "historical_combined_status": read(root/OLD/"status.json")}
        exported_ends = {}
        for label,rid in RUNS.items():
            old = root/OLD/rid; rawdir = root/".work/phase6c"/rid
            raw = read(rawdir/"result.json"); compact = read(old/"result.compact.json")
            require(raw["environment"] == raw["final_environment"] == env, "Run environment differs from shared authority")
            require(raw["run_id"] == rid and raw["exit_code"] == 0, "Unexpected original run")
            if label == "A":
                e.update({k: raw[k] for k in ("input", "basis", "parallelism", "executed_source_sha256", "workbench_head_at_execution", "base_commit")})
            else:
                require(all(raw[k] == e[k] for k in ("input", "basis", "parallelism", "executed_source_sha256", "workbench_head_at_execution", "base_commit")), "A/B shared identity differs")
            cmd = read(old/"command.json")
            e["runs"][label] = {k: raw[k] for k in ("run_id", "label", "started_utc", "finished_utc", "exit_code", "execution_status", "initial", "checkpoint_sha256")}
            e["runs"][label]["command"] = cmd["command"]
            e["runs"][label]["environment_checks"] = [
                {"boundary": which, "status": raw[field]["status"], "environment_ref": e["environment"],
                 "source_field": field, "run_id": rid,
                 "time_scope": "Bound by recorded run start/end, no separate check timestamp was recorded"}
                for which,field in (("start","environment"),("end","final_environment"))]
            e["sources"][label] = {"raw_result": source(root,rawdir.relative_to(root)/"result.json",False),
                "raw_maps": source(root,rawdir.relative_to(root)/"maps.jsonl",False),
                "published_endpoint": source(root,OLD/rid/"result.compact.json"),
                "published_maps": source(root,OLD/rid/"maps.csv"),
                "published_solvers": source(root,OLD/rid/"solvers.csv"),
                "engine_log": source(root,OLD/rid/"run.log"), "command": source(root,OLD/rid/"command.json")}
            target = stage/label; target.mkdir()
            rawmaps = [json.loads(line) for line in (rawdir/"maps.jsonl").read_text().splitlines()]
            rows = [selected_map(r) for r in rawmaps]
            # Independently bind every overlapping scientific column to the
            # previously published 191-row source, whose Git blob is checked.
            with (old/"maps.csv").open(newline="") as stream:
                original_rows = list(csv.DictReader(stream))
            require(len(original_rows) == len(rows) == 191, "Original public/raw map count differs")
            for original, row in zip(original_rows, rows):
                for k in set(original).intersection(row):
                    cell = original[k]
                    previous = cell if k in TEXT else (cell == "True" if cell in ("True","False") else json.loads(cell))
                    require(previous == row[k], f"Original public/raw map value differs: {k}")
            with (target/"maps.csv").open("w",newline="") as stream:
                writer = csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator="\n"); writer.writeheader()
                for row in rows:
                    writer.writerow({k:v if k in TEXT else json.dumps(v,separators=(",",":"),allow_nan=False) for k,v in row.items()})
            require(read_maps(target/"maps.csv") == rows, "Every selected map field must round-trip exactly")
            final = endpoint(raw); write(target/"endpoint.json",final)
            exported_ends[label] = final
            require(read(target/"endpoint.json") == final, "Every endpoint field must round-trip exactly")
            # The old public final is a strict subset of the raw final; its
            # remaining scientific fields must not change while enriching it.
            for k,v in compact["final"].items():
                if k != "diagnostics": require(final[k] == v, "Old endpoint value changed")
            for k,v in compact["final"]["diagnostics"].items():
                if k in final["diagnostics"]: require(final["diagnostics"][k] == v, "Old diagnostic value changed")
            shutil.copyfile(old/"run.log",target/"engine.log")
        c = read(root/OLD/COMPARE/"comparison.json")
        require(c.pop("comparison_environment") == env, "Comparison environment differs")
        for label in RUNS:
            require(c["runs"][label]["result_sha256"] == e["sources"][label]["raw_result"]["sha256"], "Original raw-result binding differs")
        write(stage/"comparison.json", {"recorded_comparison": c, "environment_ref": e["environment"],
            "public_recomputation": ["spectra_by_k", "max_raw_eigenvalue_difference_ha", "internal_energy_abs_difference_ha", "free_energy_abs_difference_ha", "diagnostic_only"],
            "runner_reported_requires_arrays_or_rerun": ["density_absolute_l2", "density_relative_l2"],
            "note": "The original comparison's prepared-input BLOCKED stage predates preparation; current combined historical status is separate."})
        e["sources"]["comparison"] = source(root,OLD/COMPARE/"comparison.json")
        e["comparison_check"] = {"run_id":COMPARE,"finished_utc":c["finished_utc"],"status":"PASS","environment_ref":e["environment"]}
        latest = "20260906T153037Z-tests-2afdc3e7"
        tests = read(root/OLD/latest/"test-result.json")
        regression6b = read(root/OLD/"20260906T151424Z-regression6b-0083f6a9/test-result.json")
        regression5b_log = (root/OLD/"20260906T151532Z-regression5b-0967b49d/run.log").read_text()
        previous_counts = [int(m[0]) for m in re.findall(r"\|\s+(\d+)\s+(\d+)\s+[\d.]+s", regression5b_log)]
        require(previous_counts == [544,228], "Historical regression counts differ")
        qe_log = (root/OLD/"preflight/qe-preparation-tests-attempt-3.log").read_text()
        qe_count = int(re.search(r"Ran (\d+) tests",qe_log)[1])
        require(qe_count == 24 and qe_log.rstrip().endswith("OK"), "Historical QE protocol tests differ")
        e["validation"] = {"final_new_tests": {k:tests[k] for k in ("run_id","started_utc","finished_utc","test_counts","scope","test_source_sha256","integration","ensemble","temperature")},
            "affected_regressions": [{"run_id":regression6b["run_id"],"test_counts":regression6b["test_counts"]},
                                     {"run_id":"20260906T151532Z-regression5b-0967b49d","passed_counts":previous_counts}],
            "qe_preparation_protocol_tests":qe_count,
            "scope":"Historical workbench tests, not newly executed by curation and not physical SCF or QE"}
        for rel in (OLD/latest/"test-result.json", OLD/"20260906T151424Z-regression6b-0083f6a9/run.log",
                    OLD/"20260906T151532Z-regression5b-0967b49d/run.log", OLD/"preflight/qe-preparation-tests-attempt-3.log"):
            e["sources"][str(rel)] = source(root,rel)
        e["export"] = {"script":"scripts/curate_soc_evidence.py","script_sha256":sha(root/"scripts/curate_soc_evidence.py"),
            "rule":"Explicit selections in selected_map/endpoint; exact JSON numeric equality and CSV round-trip checks. Original logs are byte-preserved. Source final solver residuals: /final/diagnostics/band_attempts/0/per_k.",
            "arithmetic":"Historical values are preserved. Offline reassociated Python sums can differ in last bits and are checked against original declared thresholds, never written over originals."}
        (stage/"README.md").write_text(render_readme(exported_ends["A"],exported_ends["B"]))
        for p in stage.rglob("*"):
            if p.is_file(): e["public_sha256"][str(p.relative_to(stage))] = sha(p)
        write(stage/"evidence.json",e)
        require(read(stage/"evidence.json") == e, "Every selected provenance field must round-trip exactly")
        verified = check(root,dataset=stage)
        stage.rename(root/DEST)
        return verified
    except Exception:
        # Keep a failed staging directory for inspection; never publish PASS.
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("export","check"))
    parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    print(json.dumps(export(args.root) if args.action=="export" else check(args.root),indent=2,allow_nan=False))


if __name__ == "__main__":
    main()
