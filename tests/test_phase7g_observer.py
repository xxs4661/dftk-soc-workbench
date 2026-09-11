"""Synthetic return-observer tests; no physical arrays or numerical replay."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import types
import unittest


SPEC = importlib.util.spec_from_file_location(
    "phase7g_test_observer", Path(__file__).resolve().parents[1] /
    "scripts/phase7g_observer/sitecustomize.py")
OBSERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OBSERVER)


class SyntheticArray:
    dtype = types.SimpleNamespace(str="<f8")
    shape = (2,)

    def tobytes(self, order):
        assert order == "C"
        return struct.pack("<2d", 1.0, -2.0)


class SyntheticNumpy:
    @staticmethod
    def save(stream, value, allow_pickle):
        assert allow_pickle is False
        stream.write(b"synthetic serialization witness\n" + value.tobytes(order="C"))


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "baseline"
        self.output = Path(self.temp.name) / "output"
        self.observer = OBSERVER.ReturnObserver(self.root, self.output)

    def tearDown(self):
        self.observer.finish()
        self.temp.cleanup()

    def function(self, filename, text, **values):
        namespace = dict(values, np=SyntheticNumpy)
        exec(compile(text, str(self.root / "scripts" / filename), "exec"), namespace)
        return namespace

    def test_returns_and_only_explicit_snapshots(self):
        density = SyntheticArray()
        report = {"synthetic": True, "nested": {"value": 7}}
        original = {"report": report, "density_real": density, "unpublished_secret": "excluded"}
        f = self.function("audit_orbital_kinetics.py",
                          "def evaluate_orbitals():\n    return original\n", original=original)
        self.observer.start()
        self.assertIs(f["evaluate_orbitals"](), original)
        report["nested"]["value"] = 9
        self.observer.finish()
        snapshot = json.loads((self.output / "r-orbitals-report.json").read_text())
        self.assertEqual(snapshot["nested"]["value"], 7)
        self.assertNotIn("unpublished_secret", snapshot)
        self.assertEqual(self.observer.captures, ["orbitals"])
        self.assertIsNone(sys.getprofile())

    def test_local_and_final_comparison_are_distinct(self):
        core = {"synthetic": True, "field_fingerprints": {"n_saved": "example"}}
        f = self.function("compare_orbital_energy.py",
                          "def compare_arrays():\n    ns = density\n    return core\n"
                          "def evaluate_comparison():\n    result = compare_arrays()\n"
                          "    result['source_sha256'] = {'synthetic': 'later'}\n    return result\n",
                          density=SyntheticArray(), core=core)
        self.observer.start()
        self.assertIs(f["evaluate_comparison"](), core)
        self.observer.finish()
        earlier = json.loads((self.output / "r-comparison-core.json").read_text())
        final = json.loads((self.output / "r-comparison.json").read_text())
        self.assertNotIn("source_sha256", earlier)
        self.assertEqual(final["source_sha256"], {"synthetic": "later"})
        self.assertEqual(self.observer.captures, ["local_arrays", "comparison"])

    def test_original_exception_is_unchanged(self):
        error = ValueError("synthetic original failure")
        f = self.function("audit_orbital_kinetics.py",
                          "def evaluate_orbitals():\n    raise error\n", error=error)
        self.observer.start()
        with self.assertRaises(ValueError) as caught:
            f["evaluate_orbitals"]()
        self.assertIs(caught.exception, error)
        self.assertEqual(self.observer.captures, [])
        self.assertEqual(self.observer.errors, [])

    def test_snapshot_failure_does_not_change_return(self):
        original = {"report": {"synthetic": True}, "density_real": SyntheticArray()}
        f = self.function("audit_orbital_kinetics.py",
                          "def evaluate_orbitals():\n    return original\n", original=original)
        self.observer.start()
        (self.output / "r-orbitals-report.json").write_text("retained prior content")
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertIs(f["evaluate_orbitals"](), original)
        self.observer.finish()
        self.assertIn("FileExistsError", stderr.getvalue())
        self.assertEqual((self.output / "r-orbitals-report.json").read_text(), "retained prior content")
        self.assertEqual(json.loads((self.output / "r-observer-status.json").read_text())["status"], "FAIL")

    def test_wrong_source_and_non_return_events_are_ignored(self):
        f = self.function("unrelated.py", "def evaluate_orbitals():\n    return {'private': 'excluded'}\n")
        self.observer.start()
        f["evaluate_orbitals"]()
        self.observer.finish()
        self.assertEqual(self.observer.captures, [])
        self.assertEqual({p.name for p in self.output.iterdir()},
                         {"r-observer-activated.json", "r-observer-status.json"})

    def test_input_root_is_never_an_output_destination(self):
        self.observer = OBSERVER.ReturnObserver(self.root, self.root / "forbidden-output")
        with contextlib.redirect_stderr(io.StringIO()):
            self.observer.start()
            self.observer.finish()
        self.assertFalse((self.root / "forbidden-output").exists())
        self.assertIsNone(sys.getprofile())

    def test_opt_in_startup_preserves_subprocess_failure(self):
        scripts = self.root / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "audit_orbital_kinetics.py").write_text(
            "from types import SimpleNamespace\n"
            "class Array:\n"
            "    dtype = SimpleNamespace(str='<f8')\n"
            "    shape = (1,)\n"
            "    def tobytes(self, order): return b'synthetic bytes'\n"
            "class Numpy:\n"
            "    def save(self, stream, value, allow_pickle):\n"
            "        assert allow_pickle is False\n"
            "        stream.write(value.tobytes('C'))\n"
            "np = Numpy()\n"
            "def evaluate_orbitals():\n"
            "    return {'report': {'synthetic': True}, 'density_real': Array()}\n")
        (scripts / "check_orbital_energy.py").write_text(
            "import json, sys\n"
            "from audit_orbital_kinetics import evaluate_orbitals\n"
            "evaluate_orbitals()\n"
            "print(json.dumps({'status': 'FAIL', 'reason': 'synthetic retained failure'}))\n"
            "sys.exit(23)\n")
        observer_path = str(Path(OBSERVER.__file__).resolve().parent)
        env = dict(os.environ, PYTHONPATH=observer_path, PYTHONNOUSERSITE="1",
                   PYTHONDONTWRITEBYTECODE="1", PHASE7G_OBSERVER_SOURCE_ROOT=str(self.root),
                   PHASE7G_OBSERVER_OUTPUT=str(self.output))
        child = subprocess.run([sys.executable, "-B", "scripts/check_orbital_energy.py"],
                               cwd=self.root, env=env, capture_output=True, check=False)
        self.assertEqual(child.returncode, 23)
        self.assertEqual(json.loads(child.stdout),
                         {"status": "FAIL", "reason": "synthetic retained failure"})
        self.assertEqual(child.stderr, b"")
        status = json.loads((self.output / "r-observer-status.json").read_text())
        self.assertEqual(status["status"], "OBSERVATION_FINISHED")
        self.assertEqual(status["captures"], ["orbitals"])
        self.assertEqual(status["not_captured"], ["comparison", "local_arrays"])
        # This test used a child observer; the inactive fixture must not write
        # another status over the retained child receipt during tearDown.
        self.observer.ended = True


if __name__ == "__main__":
    unittest.main()
