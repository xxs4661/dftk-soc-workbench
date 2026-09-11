# Frozen workbench environment

This environment supports the DFTK-backed adapters and tests without adding
dependencies to upstream projects. The
[public review and synthetic core example](../../docs/getting-started.md)
do not require it.

## Dependencies and setup

Use existing Julia **1.12.7**, Git and Python installations.
[Project.toml](Project.toml) declares DFTK, PseudoPotentialIO, JSON3 and the
standard libraries used by workbench tools/tests. The Pkg-generated
[Manifest](Manifest.toml) fixes the dependency resolution:

| Package | Version | Checkout relative to repository root |
| --- | --- | --- |
| DFTK | 0.8.0 | `.work/DFTK.jl` |
| PseudoPotentialIO | 0.3.3 | `.work/PseudoPotentialIO.jl` |

Required commits are in [sources.lock](../../config/sources.lock). Manifest
paths are relative to this environment. Fetch the checkouts **before**
instantiation, from the repository root:

```sh
bash scripts/fetch_sources.sh
bash scripts/bootstrap_dftk.sh
```

Fetch obtains locked checkouts; bootstrap instantiates the saved Manifest and
runs an identity check in a fresh Julia worker. Network access may be needed
for sources, packages and artifacts. No add/develop/update or new resolution
is part of this procedure.

For locally available source Git repositories, replace fetch with:

```sh
bash scripts/fetch_sources.sh --source-cache /path/to/source-cache
```

The cache must contain repositories named DFTK.jl and PseudoPotentialIO.jl. They
are cloned into this workbench's own `.work`; the cache is not a runtime path.
Existing dirty or wrong-commit checkouts are rejected and preserved.

You may set `JULIA_DEPOT_PATH` to an existing download cache. Otherwise the
recorder uses `.work/julia-depot`. It sets `JULIA_LOAD_PATH=@:@stdlib` and disables
the Julia startup file. Experiment-specific thread/resource settings remain
in case records; setup alone does not reproduce those executions.

## Check the actual loaded identity

Repeat the identity check without instantiation or material calculation:

```sh
python3 scripts/run_recorded.py identity
```

Each invocation writes a unique `results/runs/<run_id>/result.json`, summary
and worker log, including early failures. The check records active project,
Manifest checksum, Julia version, actual pathof locations, package versions/UUIDs,
loaded checkout commits and worktree states. It compares real paths before
sanitizing output; a correct commit in another directory is insufficient.

[checksums.toml](checksums.toml) binds Project, Manifest and source lock.
Missing sources, changed fingerprints, mismatched Julia, dirty checkouts and
initialization/compatibility errors are non-passing. Do not refresh fingerprints
or upgrade packages to bypass them. A deliberate change needs a separately
reviewed, Pkg-generated resolution. MPI initialization may fail in a restricted
process sandbox; that remains an environment failure.

The [original environment report](https://github.com/xxs4661/dftk-soc-workbench/blob/a37de03c6ddcaa154b43b4d349affcf2a77cafa7/results/phase4a-review.md) records
creation/rebuilding of this resolution, not a new-machine validation.
UPF payloads and QE builds have separate case-specific provenance; bootstrap
neither obtains them nor runs SCF/QE. Consult the
[reproduction guide](../../docs/reproducibility.md) before experimental use.
