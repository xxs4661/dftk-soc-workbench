# Verification and preservation

The four new diagnostics and both same-map comparisons are complete. Current
public replay exits 0; strict optimization acceptance exits 1 because both
performance goals were missed. The numerical execution commit remains
`761e09d8fe99f99fcccb0f1b10704916d336ccb8`.

The new raw-run archive contains 271 files / 1,616,279,399 bytes. Every file's
source-before, copy-stream, source-after and archived SHA-256 agrees. A finite
actual restore checked 55 files / 534,338,793 bytes, including each task's
`map-001.bin` and source/environment/control text. Original files remain in place.

- Raw manifest SHA-256: `0765a9b4760dd3966c56a4800ced780ea700f1f97793301ce293b44c1ba296d6`.
- Restore manifest SHA-256: `cd62f1c2ecd857bf4daa7ae1dcc0b25773db466516559d7af31b6c014d96a7bd`.
- Scope: same-machine repository-external backup; byte integrity only, not verified resumability.
- No binary checkpoint was deserialized for archiving or restoration.

An independent clean clone of result candidate
`2dc3381088de664f2352b228eecb72fe7a7c17ae` (tree
`054324856fad298b215851ba39ef934d57079c65`) completed these checks:

| Actual command or check | Exit / outcome |
|---|---|
| `python3.12 -B benchmarks/soc-boundary-v1/replay.py` | 0; record/arithmetic consistency |
| Same command with `--strict` | 1; both performance targets NOT MET |
| Boundary driver/replay, legacy timing driver/analysis and researcher-entry Python suites | 93 tests; 0 |
| `python3.12 -B scripts/review.py core-regression` | 0; fixed historical public replay |
| `julia --startup-file=no --project=@stdlib examples/soc_kernels.jl` | 0; synthetic matrix example |
| `git diff --check d9e19af HEAD` | 0 |

The clone remained clean. Historical occupation/manifold/physical-review and
performance/budget limitations remain in the researcher replay output. None of
these commands executes a new material SCF.

The previously misplaced historical extra checker was separately rerun in a clean
fixed `e40def9dcfd243131adae1ce16d8b22815560a87` clone:
`python3.12 -B -m unittest discover -s tests -p test_soc_extra_replay.py -v`.
All 20 tests passed, exit 0. The earlier wrong-tree exit 1 remains preserved;
the checker and its historical hashes were not edited.

Current navigation and exact filename casing, decompressed public JSON privacy,
frozen-source scope and clean upstream checkouts passed the final local check.
Numerical/adapter sources have no changes after execution E. Only new results
and current explanatory navigation were added after measurement.

The final exact-commit clone and supplemental code/log archive receipts are kept
outside Git to avoid a self-referential receipt commit. They must be executed and
verified before the branch-only push; their actual commit and outcome are reported
with the delivery.
