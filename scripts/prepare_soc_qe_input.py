#!/usr/bin/env python3
"""Prepare one QE 7.5 Mg SOC input after both Phase 6C solutions pass.

Requires Python >= 3.11 (standard-library tomllib; no package installation).
This program neither invokes QE nor copies a pseudopotential. Its unit tests use
synthetic result records solely to exercise the preparation protocol.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
import tomllib
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path("prototypes/soc_scf/phase6c.toml")
PREVIOUS_CONFIG = Path("prototypes/fr_integration/phase6b.toml")
LOCK = Path("config/sources.lock")
QE_DOC = "https://www.quantum-espresso.org/Doc/INPUT_PW.html"
QE_FIXED_DOC = "https://gitlab.com/QEF/q-e/-/raw/qe-7.5/PW/Doc/INPUT_PW.def"
ENERGY_DOC = "https://lists.quantum-espresso.org/pipermail/users/2021-January/046830.html"
SUCCESS_FIELDS = (
    "execution_status", "soc_scf_execution_status", "global_occupation_status",
    "band_completeness_diagnostic_status", "density_closure_status",
    "energy_and_free_energy_status", "time_reversal_status",
)
PHYSICAL_KEYS = (
    "cell_side_bohr", "positions_fractional", "ecut_ha", "kpoints",
    "kweights", "xc_identifiers", "symmetries",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    raw = Path(path).read_bytes()
    def reject_constant(value):
        raise ValueError(f"Nonfinite JSON value {value}")
    value = json.loads(raw, parse_constant=reject_constant)
    require(type(value) is dict, "A result must be a JSON object")
    return value, digest(raw)


def near(actual, expected, label):
    """Compare the small, prescribed numeric geometry without coercing types."""
    if isinstance(expected, list):
        require(type(actual) is list and len(actual) == len(expected), f"{label}: wrong shape")
        for a, b in zip(actual, expected):
            near(a, b, label)
    else:
        require(type(actual) in (int, float) and math.isfinite(actual), f"{label}: invalid number")
        require(abs(actual - expected) <= 1e-13, f"{label}: value differs from request")


def header_from_bytes(raw):
    """Only audit the existing input header; this is not an UPF validator."""
    header = ET.fromstring(raw).find("PP_HEADER")
    require(header is not None, "Mg UPF is missing PP_HEADER")
    h = header.attrib
    require(h.get("element", "").strip() == "Mg", "Expected Mg header")
    require(h.get("pseudo_type", "").strip() == "NC", "Expected NC header")
    require(h.get("relativistic", "").strip() == "full", "Expected full relativistic header")
    require(h.get("has_so", "").strip().lower() in ("t", "true", ".true."), "Expected has_so=true")
    require(h.get("core_correction", "").strip().lower() in ("f", "false", ".false."), "Expected Mg without NLCC")
    require(h.get("functional", "").strip().upper() == "PBESOL", "Expected PBESOL header")
    near(float(h.get("z_valence", "nan")), 10.0, "Header valence")
    return {"element": "Mg", "pseudo_type": "NC", "relativistic": "full",
            "has_so": True, "nlcc_present": False, "functional": "PBESOL", "z_valence": 10}


def validate_requests(a, b, comparison, result_hashes, config, previous, config_hash, pseudo_hash):
    """Validate this single Phase 6C action, including its successful evidence."""
    require(config.get("phase") == "6C" and previous.get("phase") == "6B", "Wrong configuration phase")
    mg = config["mg"]
    for key in PHYSICAL_KEYS:
        require(mg[key] == previous["mg"][key], f"Frozen Phase 6B Mg setting changed: {key}")
    near(mg["cell_side_bohr"], 10.0, "cell side")
    near(mg["positions_fractional"], [[.17, .23, .31]], "atomic positions")
    near(mg["ecut_ha"], 15.0, "Ecut")
    near(mg["kpoints"], [[0., 0., 0.], [.125, .0625, -.1875], [-.125, -.0625, .1875]], "k points")
    near(mg["kweights"], [1 / 3] * 3, "k weights")
    require(mg["xc_identifiers"] == ["gga_x_pbe_sol", "gga_c_pbe_sol"], "XC differs from PBEsol")
    require(mg["symmetries"] is False and mg["expected_has_nlcc"] is False, "Unexpected symmetry/NLCC request")
    near(mg["expected_header_valence"], 10, "Requested header valence")
    ensemble = config["ensemble"]
    near(ensemble["tau_ha"], .001, "temperature")
    require(ensemble["smearing"] == "FermiDirac" and ensemble["capacity_per_spinor_state"] == 1,
            "Expected capacity-one Fermi-Dirac ensemble")
    require(type(comparison) is dict, "Comparison must be an object")
    require(comparison.get("two_initial_states_comparison_status") == "PASS", "A/B comparison has not passed")
    require(comparison.get("config_sha256") == config_hash, "Comparison configuration hash mismatch")
    require(a.get("run_id") != b.get("run_id"), "A and B must be distinct runs")
    target = comparison.get("common_target_states")
    solver = config["solver"]
    allowed = range(solver["initial_target_states"], solver["max_target_states"] + 1, solver["target_increment"])
    require(type(target) is int and target in allowed, "Invalid final common target count")
    for label, run in (("A", a), ("B", b)):
        require(type(run) is dict and type(run.get("schema_version")) is int and run["schema_version"] == 1,
                f"{label}: unsupported result schema")
        require(run.get("phase") == "6C" and run.get("label") == label, f"{label}: wrong phase/label")
        require(type(run.get("run_id")) is str and bool(run["run_id"]), f"{label}: missing run ID")
        for field in SUCCESS_FIELDS:
            require(run.get(field) == "PASS", f"{label}: {field} has not passed")
        require(run.get("config_sha256") == config_hash, f"{label}: configuration hash mismatch")
        recorded = comparison["runs"][label]
        require(recorded["run_id"] == run["run_id"] and recorded["result_sha256"] == result_hashes[label],
                f"{label}: comparison does not bind this result")
        require(type(run.get("final")) is dict and type(run["final"].get("target_states")) is int
                and run["final"]["target_states"] == target, f"{label}: final target differs")
        near(run.get("temperature_ha"), .001, f"{label}: temperature")
        require(run.get("smearing") == "FermiDirac", f"{label}: wrong smearing")
        inp = run.get("input")
        require(type(inp) is dict, f"{label}: missing input object")
        require(inp.get("sha256") == pseudo_hash and inp.get("element") == "Mg", f"{label}: input identity differs")
        require(inp.get("functional") == "PBESOL" and inp.get("has_so") is True
                and inp.get("nlcc_present") is False and inp.get("relativistic") == "full",
                f"{label}: input metadata differs")
        near(inp.get("z_valence"), 10, f"{label}: input valence")
        basis = run.get("basis")
        require(type(basis) is dict, f"{label}: missing basis object")
        near(basis.get("lattice_bohr"), [[10., 0., 0.], [0., 10., 0.], [0., 0., 10.]], f"{label}: lattice")
        near(basis.get("positions_fractional"), mg["positions_fractional"], f"{label}: positions")
        near(basis.get("ecut_ha"), 15., f"{label}: Ecut")
        near(basis.get("n_electrons"), 10., f"{label}: electrons")
        kpoints = basis.get("kpoints")
        require(type(kpoints) is list and len(kpoints) == 3, f"{label}: expected three spatial k points")
        for actual, k, w in zip(kpoints, mg["kpoints"], mg["kweights"]):
            require(type(actual) is dict, f"{label}: invalid k point object")
            near(actual.get("coordinate_fractional"), k, f"{label}: k coordinates")
            near(actual.get("weight_spatial"), w, f"{label}: k weight")
    return target


def render_input(config, target):
    mg = config["mg"]
    number = lambda x: format(x, ".17g")
    lines = [
        "! PREPARED_NOT_EXECUTED: one future QE 7.5 SOC SCF; no benchmark result.",
        "&CONTROL", " calculation = 'scf',", " restart_mode = 'from_scratch',",
        " prefix = 'mg_soc_fermi',", " pseudo_dir = './pseudo',", " outdir = './scratch',",
        " verbosity = 'high',", "/", "&SYSTEM", " ibrav = 0, nat = 1, ntyp = 1,",
        f" nbnd = {target},", " ecutwfc = 30.0, ecutrho = 120.0,",
        " noncolin = .true., lspinorb = .true.,", " starting_magnetization(1) = 0.0,",
        " nosym = .true., noinv = .true., no_t_rev = .true.,",
        " occupations = 'smearing', smearing = 'fermi-dirac', degauss = 0.002,",
        "/", "&ELECTRONS", " conv_thr = 1.0d-10, electron_maxstep = 400, mixing_beta = 0.1,",
        "/", "ATOMIC_SPECIES", "Mg 24.305 Mg.upf", "CELL_PARAMETERS bohr",
        "10.0 0.0 0.0", "0.0 10.0 0.0", "0.0 0.0 10.0", "ATOMIC_POSITIONS crystal",
        "Mg " + " ".join(map(number, mg["positions_fractional"][0])), "K_POINTS crystal", "3",
    ]
    lines.extend(" ".join(map(number, [*k, w])) for k, w in zip(mg["kpoints"], mg["kweights"]))
    return "\n".join(lines) + "\n"


def render_checklist(parameters):
    return f"""# Prepared Mg SOC QE input

Status: **PREPARED_NOT_EXECUTED**. QE SOC benchmark: **NOT RUN**.
This directory contains one input and its provenance; no UPF or QE output.

- A/B runs: `{parameters['runs']['A']['run_id']}` / `{parameters['runs']['B']['run_id']}`.
- Input: `Mg.upf`, SHA-256 `{parameters['input']['sha256']}`; Mg NC/full/SOC,
  PBEsol, 10 valence electrons, no NLCC. Place those verified bytes in
  `./pseudo/Mg.upf` before a future run from this directory. `./scratch` is relative.
- One atom in a 10 bohr cubic cell at (0.17, 0.23, 0.31); Gamma and the explicit
  opposite k pair retain weight 1/3 each. `nosym` preserves the supplied list;
  `noinv` and `no_t_rev` disable the corresponding reduction operations.
- `nbnd={parameters['nbnd']}` is the successful A/B common count of explicit
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

Parameter authority: [QE 7.5 input documentation]({QE_DOC}),
[fixed 7.5 documentation]({QE_FIXED_DOC}). Energy-label explanation:
[QE developer reply]({ENERGY_DOC}).

The next scientific gate is the first independent QE SOC comparison. Preparation
does not satisfy it; no additional internal validation round is required first.
"""


def prepare(root, run_a_path, run_b_path, comparison_path, output_dir):
    root, output_dir = Path(root), Path(output_dir)
    require(not output_dir.exists(), "Output directory already exists; refusing to replace prior evidence")
    a, ah = read_json(run_a_path)
    b, bh = read_json(run_b_path)
    comparison, ch = read_json(comparison_path)
    config_raw = (root / CONFIG).read_bytes()
    previous_raw = (root / PREVIOUS_CONFIG).read_bytes()
    lock_raw = (root / LOCK).read_bytes()
    config, previous, lock = (tomllib.loads(raw.decode()) for raw in (config_raw, previous_raw, lock_raw))
    pseudo = lock["pseudopotentials"]
    require(pseudo["file_name"] == "Mg.upf", "Source lock must select Mg.upf")
    pseudo_raw = (root / pseudo["local_path"]).read_bytes()
    require(digest(pseudo_raw) == pseudo["file_sha256"], "Actual Mg SHA-256 differs from source lock")
    header = header_from_bytes(pseudo_raw)
    hashes = {"A": ah, "B": bh}
    target = validate_requests(a, b, comparison, hashes, config, previous, digest(config_raw), digest(pseudo_raw))
    qe_input = render_input(config, target)
    parameters = {
        "schema_version": 1, "phase": "6C", "qe_soc_input_status": "PREPARED_NOT_EXECUTED",
        "qe_soc_benchmark_status": "NOT_RUN", "qe_documentation_version": "7.5",
        "qe_execution": "NOT_RUN",
        "runs": {label: {key: comparison["runs"][label][key] for key in ("run_id", "result_sha256")}
                 for label in ("A", "B")}, "comparison_sha256": ch,
        "config_sha256": digest(config_raw), "phase6b_config_sha256": digest(previous_raw),
        "source_lock_sha256": digest(lock_raw), "input": {**header, "file_name": "Mg.upf", "sha256": digest(pseudo_raw)},
        "qe_input_sha256": digest(qe_input.encode("ascii")), "nbnd": target,
        "n_electrons": 10, "capacity_per_spinor_state": 1, "temperature_ha": .001,
        "degauss_ry": .002, "ecutwfc_ry": 30., "ecutrho_ry": 120.,
        "geometry": {key: config["mg"][key] for key in PHYSICAL_KEYS},
        "qe_solver_preparation": {"conv_thr_ry": 1e-10, "electron_maxstep": 400, "mixing_beta": .1,
                                  "diagonalization": "QE default"},
        "portable_paths": {"pseudo_dir": "./pseudo", "outdir": "./scratch"},
        "documentation": [QE_DOC, QE_FIXED_DOC, ENERGY_DOC],
    }
    # Build and validate all necessary bytes before publishing the directory.
    outputs = {"qe.in": qe_input, "parameters.json": json.dumps(parameters, indent=2, allow_nan=False) + "\n",
               "checklist.md": render_checklist(parameters)}
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".qe-prepare-", dir=output_dir.parent))
    try:
        for name, content in outputs.items():
            (staging / name).write_text(content, encoding="utf-8")
        require(not output_dir.exists(), "Output directory appeared during preparation")
        staging.rename(output_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return parameters


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-a", required=True, type=Path)
    parser.add_argument("--run-b", required=True, type=Path)
    parser.add_argument("--comparison", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        prepared = prepare(ROOT, args.run_a, args.run_b, args.comparison, args.output_dir)
    except (ValueError, KeyError, TypeError, OSError, ET.ParseError) as exc:
        print(json.dumps({"qe_soc_input_status": "BLOCKED", "qe_soc_benchmark_status": "NOT_RUN",
                          "reason": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"qe_soc_input_status": prepared["qe_soc_input_status"],
                      "qe_soc_benchmark_status": "NOT_RUN", "nbnd": prepared["nbnd"],
                      "qe_input_sha256": prepared["qe_input_sha256"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
