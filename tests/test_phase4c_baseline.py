"""Phase 4C input tests and HISTORICAL_REUSED B0 compatibility checks.

No Julia/QE process is launched. Mutated cases and identity records are synthetic
negative fixtures. B0 XML/log/JSON are published historical evidence; reparsing
them does not constitute a new SCF calculation.
"""
import contextlib
import copy
import io
import itertools
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import compare_scalar_baseline as comparison
from parse_qe_baseline import parse_qe
import run_scalar_baseline as runner

B0 = ROOT / "results/scalar-si-baseline/B0"
BASE_CASE = ROOT / "benchmarks/si-sr-lda/case.json"
C3_CASE = ROOT / "benchmarks/si-sr-lda/phase4c/C3.json"


def read_json(path):
    return json.loads(path.read_text())


class Phase4CRequestedInputTests(unittest.TestCase):
    def test_requested_eight_and_sixty_four_point_grids(self):
        for path, count, axis in ((BASE_CASE, 8, (0, -.5)),
                                  (C3_CASE, 64, (0, .25, -.5, -.25))):
            with self.subTest(count=count):
                case = read_json(path)
                self.assertEqual(comparison.requested_kpoint_count(case), count)
                self.assertEqual({tuple(p["coordinate_fractional"]) for p in case["kpoints"]},
                                 set(itertools.product(axis, repeat=3)))
                self.assertTrue(all(p["weight_spatial"] == 1 / count for p in case["kpoints"]))
                self.assertEqual(sum(p["weight_spatial"] for p in case["kpoints"]), 1)

    def test_generator_retains_eight_electrons_and_bands_for_both_grids(self):
        for source, count in ((BASE_CASE, 8), (C3_CASE, 64)):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                case, identity = runner.make_inputs(source, directory)
                generated = read_json(directory / "dftk-input.json")
                self.assertEqual(generated["electrons"]["n_electrons"], 8)
                self.assertEqual(generated["electrons"]["n_bands"], 8)
                self.assertEqual(generated["electrons"]["n_occupied"], 4)
                self.assertEqual(generated["kpoints"], case["kpoints"])
                self.assertEqual(generated["source_case_sha256"], runner.sha256(source))
                self.assertEqual(identity["dftk_input_sha256"], runner.sha256(directory / "dftk-input.json"))
                qe = (directory / "qe.in").read_text()
                self.assertIn("nat=2, ntyp=1, nbnd=8", qe)
                self.assertIn("occupations='fixed'", qe)
                lines = qe.split("K_POINTS crystal\n", 1)[1].splitlines()
                self.assertEqual(int(lines[0]), count)
                self.assertEqual(len(lines[1:]), count)
                expected = [[*p["coordinate_fractional"], p["weight_spatial"]] for p in case["kpoints"]]
                self.assertEqual([list(map(float, line.split())) for line in lines[1:]], expected)

    def test_missing_requested_c3_point_is_rejected(self):
        case = read_json(C3_CASE)
        case["kpoints"].pop()
        with self.assertRaisesRegex(ValueError, "count"):
            comparison.requested_kpoint_count(case)

    def test_duplicate_requested_c3_point_is_rejected(self):
        case = read_json(C3_CASE)
        case["kpoints"][-1] = copy.deepcopy(case["kpoints"][0])
        with self.assertRaisesRegex(ValueError, "duplicate|ambiguous"):
            comparison.requested_kpoint_count(case)

    def test_modulo_integer_duplicate_c3_point_is_rejected(self):
        case = read_json(C3_CASE)
        case["kpoints"][-1]["coordinate_fractional"] = [1, 0, 0]
        with self.assertRaisesRegex(ValueError, "duplicate|ambiguous"):
            comparison.requested_kpoint_count(case)

    def test_reordered_integer_equivalent_requested_c3_grid_is_valid(self):
        case = read_json(C3_CASE)
        case["kpoints"].reverse()
        for point in case["kpoints"]:
            point["coordinate_fractional"] = [x + 1 for x in point["coordinate_fractional"]]
        self.assertEqual(comparison.requested_kpoint_count(case), 64)

    def test_nonuniform_c3_weights_fail_even_with_correct_total(self):
        case = read_json(C3_CASE)
        case["kpoints"][0]["weight_spatial"] += 1 / 128
        case["kpoints"][1]["weight_spatial"] -= 1 / 128
        self.assertEqual(sum(p["weight_spatial"] for p in case["kpoints"]), 1)
        with self.assertRaisesRegex(ValueError, "spatial weight"):
            comparison.requested_kpoint_count(case)

    def test_declared_count_must_match_requested_list_and_supported_type(self):
        for count in (8, 63, 65, 64.0, "64", True, None):
            with self.subTest(count=count):
                case = read_json(C3_CASE)
                case["n_kpoints"] = count
                with self.assertRaisesRegex(ValueError, "count"):
                    comparison.requested_kpoint_count(case)

    def test_c3_does_not_allow_more_electrons_or_target_bands(self):
        for field, value in (("n_electrons", 64), ("n_bands", 64),
                             ("n_occupied", 8), ("spin_degeneracy", 1)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                case = read_json(C3_CASE)
                case["electrons"][field] = value
                source = Path(temp) / "synthetic-invalid-case.json"
                source.write_text(json.dumps(case))
                with self.assertRaisesRegex(ValueError, "eight electrons"):
                    runner.make_inputs(source, Path(temp))

    def test_bad_c3_request_records_new_failure_without_starting_any_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = root / ".work/scalar-baseline/synthetic-old-success"
            old.mkdir(parents=True)
            history = old / "result.json"
            history.write_text('{"execution_status":"PASS","fixture":"synthetic marker"}\n')
            before = history.read_bytes()
            case = read_json(C3_CASE)
            case["n_kpoints"] = 8  # A 64-point list may not override its requested count.
            source = root / "synthetic-invalid-c3.json"
            source.write_text(json.dumps(case))
            with patch.object(runner, "ROOT", root), patch.object(runner, "run_command") as worker:
                with contextlib.redirect_stdout(io.StringIO()):
                    code = runner.run_case(source)
                worker.assert_not_called()
            self.assertNotEqual(code, 0)
            self.assertEqual(history.read_bytes(), before)
            new = [path for path in old.parent.iterdir() if path != old]
            self.assertEqual(len(new), 1)
            record = read_json(new[0] / "result.json")
            self.assertEqual(record["execution_status"], "FAIL")
            self.assertEqual(record["input_comparability_status"], "FAIL")
            self.assertNotEqual(record["exit_code"], 0)
            self.assertEqual(record["commands"], [])
            self.assertFalse((new[0] / "comparison.json").exists())


class HistoricalB0ReuseTests(unittest.TestCase):
    """HISTORICAL_REUSED only: exact replay of parsers/generators, SCF NOT RUN."""

    def reparse(self):
        result = parse_qe(B0 / "qe-data-file-schema.xml", (B0 / "qe.stdout").read_text(),
                          0, expected_n_kpoints=8)
        # The runner binds this separately checked file identity; it is not an XML field.
        result["pseudo_sha256"] = read_json(B0 / "case.json")["pseudo"]["sha256"]
        return result

    def test_historical_reused_b0_qe_reparse_is_exactly_unchanged(self):
        self.assertEqual(self.reparse(), read_json(B0 / "qe-result.json"))

    def test_historical_reused_b0_comparison_is_exactly_unchanged(self):
        actual = comparison.compare(read_json(B0 / "case.json"),
                                    read_json(B0 / "dftk-result.json"), self.reparse())
        self.assertEqual(actual, read_json(B0 / "comparison.json"))

    def test_historical_reused_b0_generated_inputs_are_byte_identical(self):
        self.assertEqual(BASE_CASE.read_bytes(), (B0 / "case.json").read_bytes())
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            runner.make_inputs(BASE_CASE, output)
            for name in ("case.json", "dftk-input.json", "qe.in"):
                with self.subTest(name=name):
                    self.assertEqual((output / name).read_bytes(), (B0 / name).read_bytes())

    def test_historical_eight_point_xml_cannot_satisfy_a_sixty_four_point_request(self):
        with self.assertRaisesRegex(ValueError, "requested configuration"):
            parse_qe(B0 / "qe-data-file-schema.xml", (B0 / "qe.stdout").read_text(),
                     0, expected_n_kpoints=64)


class Phase4CReferenceIdentityTests(unittest.TestCase):
    """Identity comparisons use historical structure; mutations are synthetic negatives."""

    def setUp(self):
        self.reference = read_json(B0 / "result.json")
        self.environment = copy.deepcopy(self.reference["environment"])
        self.qe = copy.deepcopy(self.reference["qe_identity"])

    def test_matching_reference_identity_is_accepted(self):
        self.assertIsNone(runner.check_reference_environment(self.environment, self.qe, self.reference))

    def test_changed_manifest_project_lock_or_julia_is_rejected(self):
        for field in ("manifest_sha256", "project_sha256", "source_lock_sha256", "julia_version"):
            with self.subTest(field=field):
                environment = copy.deepcopy(self.environment)
                environment[field] = "synthetic changed identity"
                with self.assertRaisesRegex(runner.PrerequisiteError, field):
                    runner.check_reference_environment(environment, self.qe, self.reference)

    def test_changed_loaded_package_identity_is_rejected(self):
        for name in ("dftk", "pseudopotentialio"):
            for field in ("uuid", "version", "commit", "worktree_status"):
                with self.subTest(package=name, field=field):
                    environment = copy.deepcopy(self.environment)
                    environment["packages"][name][field] = "synthetic changed package"
                    with self.assertRaisesRegex(runner.PrerequisiteError, name + "." + field):
                        runner.check_reference_environment(environment, self.qe, self.reference)

    def test_changed_qe_binary_launcher_runner_or_jll_is_rejected(self):
        for field in ("binary_sha256", "launcher_sha256", "runner_sha256", "jll_version", "jll_uuid"):
            with self.subTest(field=field):
                qe = copy.deepcopy(self.qe)
                qe[field] = "synthetic changed executable identity"
                with self.assertRaisesRegex(runner.PrerequisiteError, field):
                    runner.check_reference_environment(self.environment, qe, self.reference)


if __name__ == "__main__":
    unittest.main()
