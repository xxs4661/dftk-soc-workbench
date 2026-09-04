# DFTK minimal-test summary

**Status:** PASS

| Field | Value |
| --- | --- |
| Command | `JULIA_DEPOT_PATH=.work/julia-depot julia --startup-file=no --color=no --project=.work/DFTK.jl -e 'import Pkg; Pkg.test("DFTK"; test_args=["minimal"])'` |
| Exit code | `0` |
| Started at UTC | `2026-09-04T17:05:54Z` |
| Ended at UTC | `2026-09-04T17:21:27Z` |
| DFTK commit | `2f51b91213e26726fb9c6a17e5fae235a1412d01` |
| Test selection | Upstream test items tagged `:minimal`; not the full suite |
| Upstream test summary | `1387 passed / 1387 total` |
| Upstream reported test time | `8m16.0s` |
| Sanitized log | [`results/logs/dftk-minimal-20260904T170554Z.log`](logs/dftk-minimal-20260904T170554Z.log) |
| Committed log scope | First 20 and final 200 lines of 4,022 sanitized lines; the omitted middle was dependency setup and SCF iteration output |

The documented minimal test command executed and exited successfully. This does not represent a full-suite result.
