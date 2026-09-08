"""Synthetic CI contract checks; no public numerical packages are read."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_cross_env_replay as replay


class CrossEnvironmentContractTests(unittest.TestCase):
    def test_reference_failure_survives_other_successes(self):
        # Packaging/upload succeeds after these receipts. Its successful exit
        # cannot replace the reference process failure.
        numerical_exit = replay.aggregate_exit(0, 1, 0, 0)
        upload_exit = 0
        self.assertEqual(numerical_exit, 1)
        self.assertEqual(upload_exit, 0)
        for codes in [(3, 0, 0, 0), (0, 0, 4, 0), (0, 0, 0, 5), (0, -9, 0, 0)]:
            with self.subTest(codes=codes):
                self.assertNotEqual(replay.aggregate_exit(*codes), 0)
        self.assertEqual(replay.aggregate_exit(0, 0, 0, 0), 0)

    def test_missing_required_exit_cannot_pass(self):
        for index in range(4):
            codes = [0, 0, 0, 0]
            codes[index] = None
            with self.subTest(missing_index=index):
                self.assertNotEqual(replay.aggregate_exit(*codes), 0)

    def test_only_exact_declared_density_hash_paths_are_candidates(self):
        old, new = "a" * 64, "b" * 64
        for key in ("n_wfc", "n_saved"):
            path = "comparison.local_state.field_fingerprints." + key
            row, = replay.field_differences(new, old, path)
            self.assertEqual(row["classification"], "PREDECLARED_DERIVED_DENSITY_HASH")
            self.assertFalse(row["frozen_close_pass"])
        rejected = ["comparison.local_state.field_fingerprints.V_Qpp",
                    "comparison.local_state.field_fingerprints.uV",
                    "comparison.local_state.field_fingerprints.n_wfc.extra",
                    "state-checks.Q.input_array_fingerprints.coefficients.sha256",
                    "comparison.source_sha256.input", "comparison.status", "comparison.units"]
        for path in rejected:
            with self.subTest(path=path):
                row, = replay.field_differences(new, old, path)
                self.assertNotEqual(row["classification"], "PREDECLARED_DERIVED_DENSITY_HASH")
                self.assertFalse(row["frozen_close_pass"])
        version, = replay.field_differences("unexpected", "2.3.5", "state-checks.Q.backend.numpy_version")
        self.assertEqual(version["classification"], "ENVIRONMENT_VERSION_MISMATCH_NOT_EXEMPT")

    def test_hash_type_and_encoding_changes_are_not_exempt(self):
        path = "comparison.local_state.field_fingerprints.n_wfc"
        for new in (None, ["b" * 64], {"sha256": "b" * 64}, "malformed", "B" * 64, True):
            with self.subTest(new=new):
                rows = replay.field_differences(new, "a" * 64, path)
                self.assertTrue(rows)
                self.assertTrue(all(row["classification"] != "PREDECLARED_DERIVED_DENSITY_HASH"
                                    and not row["frozen_close_pass"] for row in rows))

    def test_numeric_deltas_and_structure_remain_visible(self):
        row, = replay.field_differences(1.0 + 5e-12, 1.0, "comparison.Q.J_Q_ha")
        self.assertEqual(row["classification"], "DERIVED_NUMERIC")
        self.assertTrue(row["frozen_close_pass"])
        self.assertGreater(row["absolute_difference"], 0)
        over, = replay.field_differences(1.0 + 5e-8, 1.0, "comparison.Q.J_Q_ha")
        self.assertFalse(over["frozen_close_pass"])
        for new, old in [({"extra": 1}, {}), ([1, 2], [1]), (True, 1)]:
            self.assertTrue(all(not r["frozen_close_pass"]
                                for r in replay.field_differences(new, old, "comparison.synthetic")))

    def test_nonfinite_numbers_fail_even_when_identical(self):
        for new, old in [(float("inf"), float("inf")), (-float("inf"), -float("inf")),
                         (float("nan"), 0.0), (0.0, float("nan"))]:
            with self.subTest(new=new, old=old):
                rows = replay.field_differences(new, old, "comparison.synthetic")
                self.assertTrue(rows)
                self.assertTrue(all(not row["frozen_close_pass"] for row in rows))
                # Failure evidence itself must remain serializable.
                json.dumps(rows, allow_nan=False)

    def test_reference_reason_is_bound_to_exact_observed_hash_failure(self):
        old, new = "a" * 64, "b" * 64
        path = "comparison.local_state.field_fingerprints.n_wfc"
        row, = replay.field_differences(new, old, path)
        reason = "Replay differs: " + str((new, old))[:200]
        stdout = json.dumps({"status": "FAIL", "reason": reason}) + "\n"
        self.assertTrue(replay.reference_failure_matches_hashes(1, stdout, [row]))
        for code in (0, 2, -9, None):
            with self.subTest(exit_code=code):
                self.assertFalse(replay.reference_failure_matches_hashes(code, stdout, [row]))
        for text in (json.dumps({"status": "FAIL", "reason": "Unrelated failure"}),
                     json.dumps({"status": "PASS", "reason": reason}),
                     json.dumps({"status": "FAIL", "reason": "Replay differs: " + str((old, new))}),
                     json.dumps({"status": "FAIL", "reason": reason + " unrelated suffix"}),
                     stdout + stdout, "not JSON"):
            with self.subTest(stdout=text):
                self.assertFalse(replay.reference_failure_matches_hashes(1, text, [row]))
        other, = replay.field_differences(new, old, "comparison.local_state.field_fingerprints.uV")
        self.assertFalse(replay.reference_failure_matches_hashes(1, stdout, [other]))
        self.assertFalse(replay.reference_failure_matches_hashes(1, stdout, []))

    def make_source(self, root):
        source = root / "source"
        source.mkdir()
        relative = "results/synthetic/public.bin"
        path = source / relative
        path.parent.mkdir(parents=True)
        path.write_bytes(b"ABC")
        plan = {"input_commit": "a" * 40,
                "input_sha256": {relative: hashlib.sha256(b"ABC").hexdigest()},
                "input_bytes": {relative: 3}}
        return source, path, plan

    def test_source_single_byte_mutation_fails_before_and_after(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, path, plan = self.make_source(Path(temporary))
            with mock.patch.object(replay, "git", return_value=plan["input_commit"]):
                before = replay.input_snapshot(source, plan)
                self.assertEqual(before, plan["input_sha256"])
                path.write_bytes(b"ABD")
                # The same helper guards both initial identity and final check.
                for _ in range(2):
                    with self.assertRaisesRegex(ValueError, "identity mismatch"):
                        replay.input_snapshot(source, plan)

    def test_source_missing_wrong_commit_and_symlink_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, path, plan = self.make_source(root)
            with mock.patch.object(replay, "git", return_value="b" * 40):
                with self.assertRaisesRegex(ValueError, "commit"):
                    replay.input_snapshot(source, plan)
            path.unlink()
            with mock.patch.object(replay, "git", return_value=plan["input_commit"]):
                with self.assertRaisesRegex(ValueError, "unsafe"):
                    replay.input_snapshot(source, plan)
                outside = root / "outside.bin"
                outside.write_bytes(b"ABC")
                path.symlink_to(outside)
                with self.assertRaisesRegex(ValueError, "unsafe"):
                    replay.input_snapshot(source, plan)

    def test_raw_child_failure_and_output_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = [sys.executable, "-B", "-c",
                       "import sys;sys.stdout.buffer.write(b'synthetic stdout\\n');"
                       "sys.stderr.buffer.write(b'synthetic stderr\\n');sys.exit(7)"]
            result = replay.run_command(command, root, root / "child", dict(os.environ))
            self.assertEqual(result["exit_code"], 7)
            self.assertTrue(result["completed"])
            self.assertEqual((root / "child/stdout.txt").read_bytes(), b"synthetic stdout\n")
            self.assertEqual((root / "child/stderr.txt").read_bytes(), b"synthetic stderr\n")
            self.assertEqual(json.loads((root / "child/process.json").read_text())["exit_code"], 7)


if __name__ == "__main__":
    unittest.main()
