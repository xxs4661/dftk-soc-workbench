"""Opt-in, read-only return observation for the frozen Phase 7G reference run.

The runner sets this directory as R-only PYTHONPATH. No frozen function is
replaced, no numerical operation is repeated, and callback errors never escape
into R. These snapshots are diagnostics, not an independent implementation.
"""
import atexit
import hashlib
import json
import os
from pathlib import Path
import sys


class ReturnObserver:
    def __init__(self, source_root, output):
        self.source_root = Path(source_root).resolve()
        self.output = Path(output).resolve()
        self.targets = {
            (str(self.source_root / "scripts/audit_orbital_kinetics.py"), "evaluate_orbitals"): "orbitals",
            (str(self.source_root / "scripts/compare_orbital_energy.py"), "compare_arrays"): "local_arrays",
            (str(self.source_root / "scripts/compare_orbital_energy.py"), "evaluate_comparison"): "comparison",
        }
        self.function_names = {name for _, name in self.targets}
        self.captures = []
        self.files = []
        self.errors = []
        self.installed = False
        self.ended = False

    def _error(self, phase, error):
        # Do not inspect arbitrary frames, exception arguments or environment.
        row = {"phase": phase, "error_type": type(error).__name__}
        self.errors.append(row)
        try:
            print("Phase7G observer failure: " + phase + ": " + row["error_type"],
                  file=sys.stderr, flush=True)
        except BaseException:
            pass

    def _bytes(self, name, data):
        with (self.output / name).open("xb") as stream:
            stream.write(data)
        self.files.append({"name": name, "bytes": len(data),
                           "sha256": hashlib.sha256(data).hexdigest()})

    def _json(self, name, value):
        self._bytes(name, (json.dumps(value, indent=2, allow_nan=False) + "\n").encode())

    def _array(self, name, value, numpy_module):
        # np.save only serializes a value that the original function produced.
        # No conversion, normalization, FFT, reduction or input write occurs.
        if value.dtype.str != "<f8" or len(value.shape) != 1:
            raise ValueError("Unexpected observed density representation")
        path = self.output / name
        with path.open("xb") as stream:
            numpy_module.save(stream, value, allow_pickle=False)
        data = path.read_bytes()
        self.files.append({"name": name, "bytes": len(data),
                           "sha256": hashlib.sha256(data).hexdigest(),
                           "dtype": value.dtype.str, "shape": list(value.shape),
                           "data_C_sha256": hashlib.sha256(value.tobytes(order="C")).hexdigest()})

    def start(self):
        try:
            if self.output == self.source_root or self.source_root in self.output.parents:
                raise ValueError("Observer output must be outside the baseline")
            if sys.getprofile() is not None:
                raise RuntimeError("Existing profiler must not be replaced")
            self.output.mkdir(parents=True, exist_ok=True)
            self._json("r-observer-activated.json", {
                "schema_version": 1, "status": "ACTIVATED",
                "mechanism": "sys.setprofile return events; no function replacement",
                "scope": "SAME_IMPLEMENTATION_OBSERVATION_NOT_INDEPENDENT_REPLAY",
                "capture_points": sorted(self.targets.values()),
            })
            sys.setprofile(self.profile)
            self.installed = True
        except BaseException as error:
            self._error("activation", error)
        return self

    def profile(self, frame, event, result):
        if event != "return":
            return
        name = frame.f_code.co_name
        if name not in self.function_names:
            return
        kind = self.targets.get((os.path.realpath(frame.f_code.co_filename), name))
        # Python emits return(None) when unwinding an exception. Do not alter it
        # or mistake it for a completed report. Unreached stages remain absent.
        if kind is None or not isinstance(result, dict):
            return
        try:
            if kind in self.captures:
                raise ValueError("Duplicate observed return")
            if kind == "orbitals":
                self._json("r-orbitals-report.json", result["report"])
                self._array("r-n-wfc.npy", result["density_real"], frame.f_globals["np"])
            elif kind == "local_arrays":
                self._array("r-n-saved.npy", frame.f_locals["ns"], frame.f_globals["np"])
                self._json("r-comparison-core.json", result)
            else:
                self._json("r-comparison.json", result)
            self.captures.append(kind)
        except BaseException as error:
            self._error(kind, error)

    def finish(self):
        if self.ended:
            return
        self.ended = True
        try:
            if self.installed and sys.getprofile() == self.profile:
                sys.setprofile(None)
            self._json("r-observer-status.json", {
                "schema_version": 1, "ended": True,
                "status": "FAIL" if self.errors or not self.installed else "OBSERVATION_FINISHED",
                "scope": "SAME_IMPLEMENTATION_OBSERVATION_NOT_INDEPENDENT_REPLAY",
                "captures": self.captures,
                "not_captured": sorted(set(self.targets.values()) - set(self.captures)),
                "files": list(self.files), "errors": self.errors,
                "reference_exit_status": "RECORDED_BY_PARENT_FROM_UNMODIFIED_SUBPROCESS_RETURN_CODE",
            })
        except BaseException as error:
            self._error("finalization", error)


_source_root = os.environ.get("PHASE7G_OBSERVER_SOURCE_ROOT")
_output = os.environ.get("PHASE7G_OBSERVER_OUTPUT")
if _source_root and _output:
    _observer = ReturnObserver(_source_root, _output).start()
    atexit.register(_observer.finish)
elif _source_root or _output:
    # An incomplete opt-in is a separate observer failure, not a changed R exit.
    print("Phase7G observer failure: incomplete configuration", file=sys.stderr)
