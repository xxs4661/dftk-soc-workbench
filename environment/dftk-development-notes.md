# DFTK development notes

These notes summarize instructions observed in DFTK at locked commit `2f51b91213e26726fb9c6a17e5fae235a1412d01`. Paths below are relative to the root of that DFTK checkout. The linked views are pinned to the same commit.

## Supported Julia version

[`README.md`](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/README.md) states that Julia 1.10 or newer is required. [`Project.toml`](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/Project.toml) independently records `julia = "1.10"` in `[compat]`. The Phase 2 environment uses Julia 1.12.7, which satisfies that declared compatibility bound.

## Recommended development workflow

[`AGENTS.md`](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/AGENTS.md) recommends opening the source project with `julia --project`, loading `Revise` before `DFTK`, and keeping one persistent Julia session alive while iterating. This avoids paying package loading and compilation costs after every change. A feature should first be exercised on a deliberately small system, and the full test suite should not be used for each iteration.

Phase 2 does not edit the fetched source. Its scripts use an isolated depot under the ignored `.work/` directory and a detached checkout at the locked commit.

## Test method and smallest documented command

[`test/runtests.jl`](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/test/runtests.jl) and [`test/runtests_parser.jl`](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/test/runtests_parser.jl) implement tag-based selection through `TestItemRunner`. `AGENTS.md` documents this minimal sanity command:

```bash
julia --project -e 'import Pkg; Pkg.test("DFTK"; test_args=["minimal"])'
```

The Phase 2 harness uses that exact `Pkg.test` method, with explicit project/depot paths and nonessential presentation flags. Each `test_args` tag must be a separate list element; the dash-joined form is only for `DFTK_TEST_ARGS`. Test-item files must not be included as standalone scripts because their relative setup-module imports are resolved by `TestItemRunner`.

For a still smaller targeted iteration in an already prepared persistent development session, `AGENTS.md` documents `TestItemRunner.run_tests("test/"; filter=...)` by test name, file, or tag. That workflow requires the test environment and persistent-session setup; the self-contained Phase 2 harness therefore uses the documented `:minimal` package-test selection.

## Julia compilation latency

`AGENTS.md` warns that `using DFTK`, a first SCF calculation, and package-test precompilation can each take several minutes. A silent process for less than about five minutes is not by itself evidence of a hang. Process completion and exit status remain authoritative.

## AI-assisted contribution rules

[`CONTRIBUTING.md`](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/CONTRIBUTING.md) welcomes AI-assisted contributions only when contributors:

- disclose what the AI did, what the human did, and the model used;
- contribute real research, testing, design, or other value;
- fully understand the code and can demonstrate that it works as intended; and
- acknowledge AI assistance in discussions rather than using unacknowledged AI-written posts.

This workbench does not open or comment on any upstream issue or pull request in Phase 2.

## Code and testing conventions relevant to later work

From `AGENTS.md` at the locked commit:

- Keep code aligned with the mathematical structure, readable, short, and simple; explain non-obvious physics or numerical details with focused inline comments.
- Prefer a 92-character line length, explicit named-tuple syntax `(; key=value)`, `=` for range loops, `in` for collection loops, braced `where {T}`, explicit keyword arguments, and `_` prefixes for internal helpers.
- Use atomic units, reduced-coordinate conventions, column lattice vectors, and the existing Unicode names consistently.
- Use `zeros_like`, `similar`, and DFTK device-transfer helpers rather than hard-coding CPU or GPU array types.
- Distinguish the full FFT-grid G-vector cube used for densities from the k-point-specific spherical G-vector set used for wavefunctions.
- Reduce k-point sums through DFTK's MPI-aware helpers.
- Wrap expensive operations with DFTK timing helpers, but never use the global timer inside a threaded region.
- Test items use `@testitem` with tags and setup modules. Run a focused item or tag while iterating, then the documented minimal sanity selection before considering broader CI coverage.
- The upstream main branch is `master`; any future upstream interaction would use a fork, a focused branch, and a separately authorized pull request.

No additional `AGENTS.md` exists below `test/` at this locked commit.
