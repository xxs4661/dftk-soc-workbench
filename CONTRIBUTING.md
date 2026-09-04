# Contributing

This workbench is in a design and validation-planning stage. Contributions should remain small, evidence-based, reproducible, and clearly separated from claims about completed functionality.

## Boundaries

- Do not represent SOC as implemented or validated until the relevant implementation and acceptance tests exist and have been reviewed.
- Do not represent a workbench proposal as an architecture accepted by DFTK maintainers.
- Do not copy or translate Quantum ESPRESSO source code. QE may be used as a numerical reference through documented inputs and outputs.
- Do not redistribute pseudopotential files unless their license explicitly permits redistribution.
- Do not commit credentials, authentication output, private data, downloaded source trees, package caches, large generated files, or raw calculation directories.
- Do not modify upstream repositories as part of a workbench-only task. Upstream interaction requires a separately reviewed and explicitly authorized contribution.

## Documentation and provenance

Use **proposal**, **hypothesis**, or **open question** for undecided architectural statements. Use **pending verification** when evidence is unavailable. Record source revisions and pseudopotential SHA-256 checksums in [`config/sources.lock`](config/sources.lock) before relying on them in a benchmark.

Small sanitized logs and Markdown reports may be committed when they help reproduce a result. Raw outputs belong outside version control.

## Change workflow

1. Create a focused branch from the intended base commit.
2. Keep one scientific or infrastructure concern per commit where practical.
3. Update documentation and source records alongside a change.
4. Run the validation checks listed below.
5. Explain assumptions, numerical tolerances, and unresolved questions in the change description.

Do not force-push, rewrite shared history, or amend commits in an automated workflow.

## Validation checklist

- Check internal relative links.
- Run `git diff --check`.
- Search for credentials, absolute home-directory paths, and unsupported completion or agreement claims.
- Confirm that no UPF file or raw QE save directory is tracked.
- Confirm that the worktree contains only intended changes.
- For future numerical work, record executable versions, inputs, convergence parameters, source revisions, and pseudopotential identifiers and checksums.

## AI-assisted contributions

Disclose material AI assistance. The contributor remains responsible for understanding the change, executing and interpreting tests, checking provenance, and responding to review.
