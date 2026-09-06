"""Synthetic preparation-protocol tests; no Julia, SCF, or physical UPF validation."""

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("prepare_soc_qe_input", ROOT / "scripts/prepare_soc_qe_input.py")
prep = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prep)

# Header-only synthetic XML exercises preparation metadata checks. It has no
# radial functions/projectors and is not a pseudopotential for calculations.
SYNTHETIC_HEADER = b'''<UPF><PP_HEADER element="Mg" pseudo_type="NC" relativistic="full"
 has_so="T" core_correction="F" functional="PBESOL" z_valence="10"/></UPF>'''


class PreparationProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-qe-preparation-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for rel in (prep.CONFIG, prep.PREVIOUS_CONFIG):
            dest = self.root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((ROOT / rel).read_bytes())
        self.config = tomllib.loads((self.root / prep.CONFIG).read_text())
        self.previous = tomllib.loads((self.root / prep.PREVIOUS_CONFIG).read_text())
        self.config_hash = prep.digest((self.root / prep.CONFIG).read_bytes())
        self.pseudo_hash = prep.digest(SYNTHETIC_HEADER)
        (self.root / "synthetic-header.xml").write_bytes(SYNTHETIC_HEADER)
        (self.root / "config").mkdir()
        (self.root / prep.LOCK).write_text(
            '[pseudopotentials]\nfile_name="Mg.upf"\nlocal_path="synthetic-header.xml"\n'
            f'file_sha256="{self.pseudo_hash}"\n')
        self.a, self.b = self.record("A"), self.record("B")
        self.output = self.root / "prepared"
        self.a_path, self.b_path, self.c_path = (self.root / name for name in ("a.json", "b.json", "comparison.json"))
        self.write_records()

    def record(self, label):
        mg = self.config["mg"]
        return {
            "fixture_scope": "SYNTHETIC: no actual calculation",
            "schema_version": 1, "phase": "6C", "label": label, "run_id": "synthetic-" + label,
            **{key: "PASS" for key in prep.SUCCESS_FIELDS}, "config_sha256": self.config_hash,
            "temperature_ha": .001, "smearing": "FermiDirac", "final": {"target_states": 24},
            "input": {**prep.header_from_bytes(SYNTHETIC_HEADER), "sha256": self.pseudo_hash},
            "basis": {"lattice_bohr": [[10., 0., 0.], [0., 10., 0.], [0., 0., 10.]],
                      "positions_fractional": mg["positions_fractional"], "ecut_ha": 15., "n_electrons": 10,
                      "kpoints": [{"coordinate_fractional": k, "weight_spatial": w}
                                  for k, w in zip(mg["kpoints"], mg["kweights"])]},
        }

    def write_records(self, target=24):
        self.a_path.write_text(json.dumps(self.a))
        self.b_path.write_text(json.dumps(self.b))
        self.comparison = {
            "fixture_scope": "SYNTHETIC: no actual comparison",
            "two_initial_states_comparison_status": "PASS", "common_target_states": target,
            "config_sha256": self.config_hash,
            "runs": {label: {"run_id": run["run_id"], "result_sha256": prep.digest(path.read_bytes())}
                     for label, run, path in (("A", self.a, self.a_path), ("B", self.b, self.b_path))},
        }
        self.c_path.write_text(json.dumps(self.comparison))

    def prepare(self):
        return prep.prepare(self.root, self.a_path, self.b_path, self.c_path, self.output)

    def reject(self, text):
        with self.assertRaisesRegex((ValueError, KeyError, TypeError), text):
            self.prepare()
        self.assertFalse(self.output.exists(), "Failed preparation must not publish a directory")

    def test_synthetic_success_publishes_one_input_without_execution_or_upf(self):
        result = self.prepare()
        self.assertEqual({p.name for p in self.output.iterdir()}, {"qe.in", "parameters.json", "checklist.md"})
        self.assertEqual(result["qe_soc_input_status"], "PREPARED_NOT_EXECUTED")
        self.assertEqual(result["qe_soc_benchmark_status"], "NOT_RUN")
        self.assertEqual(result["qe_input_sha256"], prep.digest((self.output / "qe.in").read_bytes()))
        text = (self.output / "qe.in").read_text()
        for token in ("nbnd = 24", "noncolin = .true.", "lspinorb = .true.",
                      "starting_magnetization(1) = 0.0", "degauss = 0.002", "ecutwfc = 30.0",
                      "ecutrho = 120.0", "nosym = .true.", "noinv = .true.", "no_t_rev = .true.",
                      "pseudo_dir = './pseudo'", "outdir = './scratch'"):
            self.assertIn(token, text)
        self.assertNotIn("nspin", text)
        self.assertNotIn("input_dft", text)
        self.assertNotIn(str(self.root), text + (self.output / "parameters.json").read_text())
        points = text.split("K_POINTS crystal\n3\n")[1].splitlines()
        self.assertEqual(len(points), 3)
        self.assertEqual([list(map(float, row.split()[:3])) for row in points], self.config["mg"]["kpoints"])
        self.assertAlmostEqual(sum(float(row.split()[3]) for row in points), 1.)

    def test_final_common_target_is_not_initial_count_or_doubled(self):
        for target in (24, 32, 40, 48):
            with self.subTest(target=target):
                self.a["final"]["target_states"] = target
                self.b["final"]["target_states"] = target
                self.write_records(target)
                self.output = self.root / f"prepared-{target}"
                self.assertEqual(self.prepare()["nbnd"], target)

    def test_public_parameters_do_not_copy_extra_run_metadata(self):
        self.comparison["runs"]["A"]["private_workspace"] = str(self.root)
        self.c_path.write_text(json.dumps(self.comparison))
        parameters = self.prepare()
        self.assertEqual(set(parameters["runs"]["A"]), {"run_id", "result_sha256"})
        self.assertNotIn(str(self.root), (self.output / "parameters.json").read_text())

    def test_every_required_worker_stage_must_pass(self):
        for field in prep.SUCCESS_FIELDS:
            with self.subTest(field=field):
                original = self.a[field]
                self.a[field] = "FAIL"
                self.write_records()
                self.reject(field)
                self.a[field] = original

    def test_missing_stage_is_not_success(self):
        del self.a["density_closure_status"]
        self.write_records()
        self.reject("density_closure_status")

    def test_comparison_requires_pass(self):
        for status in ("DIFFERENT_SOLUTIONS", "NOT_RUN", "BLOCKED"):
            with self.subTest(status=status):
                self.comparison["two_initial_states_comparison_status"] = status
                self.c_path.write_text(json.dumps(self.comparison))
                self.reject("comparison has not passed")

    def test_edited_result_invalidates_comparison_hash(self):
        self.a["unrelated_field"] = 1
        self.a_path.write_text(json.dumps(self.a))
        self.reject("comparison does not bind")

    def test_comparison_run_identity_must_match(self):
        self.comparison["runs"]["A"]["run_id"] = "some-other-run"
        self.c_path.write_text(json.dumps(self.comparison))
        self.reject("comparison does not bind")

    def test_reused_run_id_is_rejected(self):
        self.b["run_id"] = self.a["run_id"]
        self.write_records()
        self.reject("distinct runs")

    def test_mismatched_common_target_is_rejected(self):
        self.b["final"]["target_states"] = 32
        self.write_records()
        self.reject("final target differs")

    def test_invalid_target_count_is_rejected(self):
        for target in (16, 25, 56, True, "24"):
            with self.subTest(target=target):
                self.write_records(target)
                self.reject("Invalid final common target")

    def test_schema_and_run_label_are_checked(self):
        for field, value in (("schema_version", 999), ("schema_version", True), ("phase", "6B"), ("label", "B")):
            with self.subTest(field=field, value=value):
                self.a = self.record("A")
                self.a[field] = value
                self.write_records()
                self.reject("schema|phase/label")

    def test_worker_configuration_hash_must_match_actual_file(self):
        self.a["config_sha256"] = "0" * 64
        self.write_records()
        self.reject("configuration hash")

    def test_comparison_configuration_hash_must_match_actual_file(self):
        self.comparison["config_sha256"] = "0" * 64
        self.c_path.write_text(json.dumps(self.comparison))
        self.reject("configuration hash")

    def test_physical_model_and_input_metadata_are_checked(self):
        changes = [("temperature_ha", .002), ("smearing", "Gaussian"),
                   ("input.sha256", "0" * 64), ("input.functional", "LDA"),
                   ("input.has_so", False), ("input.nlcc_present", True), ("input.z_valence", 8),
                   ("basis.ecut_ha", 30.), ("basis.n_electrons", 8),
                   ("basis.positions_fractional", [[0., 0., 0.]])]
        for dotted, value in changes:
            with self.subTest(field=dotted):
                self.a = self.record("A")
                keys = dotted.split(".")
                dest = self.a if len(keys) == 1 else self.a[keys[0]]
                dest[keys[-1]] = value
                self.write_records()
                self.reject("differs|wrong")

    def test_missing_or_wrong_nested_types_are_rejected(self):
        for key in ("input", "basis", "final"):
            for value in (None, [], "bad"):
                with self.subTest(key=key, value=value):
                    self.a = self.record("A")
                    self.a[key] = value
                    self.write_records()
                    self.reject("object|target")

    def test_kpoint_count_coordinates_and_weights_are_checked(self):
        for kind in ("missing", "duplicate", "weight"):
            with self.subTest(kind=kind):
                self.a = self.record("A")
                points = self.a["basis"]["kpoints"]
                if kind == "missing":
                    points.pop()
                elif kind == "duplicate":
                    points[1] = copy.deepcopy(points[0])
                else:
                    points[0]["weight_spatial"] = 2 / 3
                self.write_records()
                self.reject("k points|k coordinates|k weight")

    def test_nonfinite_json_is_rejected(self):
        self.a["temperature_ha"] = float("nan")
        self.write_records()
        self.reject("Nonfinite JSON")

    def test_frozen_geometry_change_is_rejected(self):
        raw = (self.root / prep.CONFIG).read_text().replace("cell_side_bohr = 10.0", "cell_side_bohr = 11.0")
        (self.root / prep.CONFIG).write_text(raw)
        self.reject("Frozen Phase 6B")

    def test_actual_input_hash_is_checked_again(self):
        (self.root / "synthetic-header.xml").write_bytes(SYNTHETIC_HEADER + b"\n")
        self.reject("Actual Mg SHA-256")

    def test_header_failure_never_becomes_physical_validation(self):
        with self.assertRaisesRegex(ValueError, "PBESOL"):
            prep.header_from_bytes(SYNTHETIC_HEADER.replace(b"PBESOL", b"PBE"))
        with self.assertRaisesRegex(ValueError, "NLCC"):
            prep.header_from_bytes(SYNTHETIC_HEADER.replace(b'core_correction="F"', b'core_correction="T"'))

    def test_existing_evidence_is_not_overwritten(self):
        self.prepare()
        before = {path.name: path.read_bytes() for path in self.output.iterdir()}
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.prepare()
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.output.iterdir()})

    def test_checklist_construction_failure_does_not_publish(self):
        with mock.patch.object(prep, "render_checklist", side_effect=ValueError("synthetic rendering failure")):
            self.reject("synthetic rendering failure")

    def test_checklist_write_failure_does_not_publish(self):
        original = Path.write_text
        def failing(path, *args, **kwargs):
            if path.name == "checklist.md":
                raise OSError("synthetic disk failure")
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, "write_text", failing):
            with self.assertRaisesRegex(OSError, "synthetic disk failure"):
                self.prepare()
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob(".qe-prepare-*")))


if __name__ == "__main__":
    unittest.main()
