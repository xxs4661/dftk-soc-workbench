# Scripts

Phase 2 provides four reproducible shell entry points:

- [`fetch_sources.sh`](fetch_sources.sh) obtains the user's DFTK fork and upstream PseudoPotentialIO at immutable commits under the ignored `.work/` directory.
- [`collect_environment.sh`](collect_environment.sh) records a small, non-secret host summary.
- [`bootstrap_dftk.sh`](bootstrap_dftk.sh) instantiates and precompiles DFTK with an isolated ignored Julia depot.
- [`run_dftk_minimal.sh`](run_dftk_minimal.sh) executes DFTK's documented `:minimal` package-test selection and saves a timestamped, sanitized, concise log. Its complete sanitized transcript uses the ignored `.raw` suffix so dependency and iteration noise is not committed.

Run them from the repository root in that order. Each script returns nonzero on a required-step failure. Bootstrap and test statuses distinguish successful execution from failure or a missing prerequisite.

Scripts should perform one reproducible task, expose their inputs, fail clearly, and avoid hidden downloads. They must never print credentials or commit package caches, pseudopotential payloads, raw QE save directories, downloaded source trees, or large generated outputs.

Every future script should document:

- required executable versions;
- expected working directory and inputs;
- generated files and whether they are safe to commit;
- deterministic settings or seeds where relevant; and
- a small verification command or invariant.

Numerical automation must read or update the provenance described in [`../config/README.md`](../config/README.md).
