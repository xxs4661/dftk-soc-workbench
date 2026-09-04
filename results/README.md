# Results

No SOC or cross-code scientific results are reported. Phase 2 adds reproducibility evidence for the development environment and the smallest appropriate upstream DFTK test selection:

- [`environment-summary.md`](environment-summary.md): observed host and tool information
- [`minimal-test-summary.md`](minimal-test-summary.md): actual command, exit code, status, and log link

Future committed results should be small, sanitized, reviewable summaries such as convergence tables, selected eigenvalues, SOC splittings, tolerances, and pass/fail invariants. Every report must link to its benchmark inputs and environment record and identify exact source revisions and pseudopotential SHA-256 checksums.

Raw or large output belongs outside Git. Do not commit pseudopotential payloads, wavefunctions, QE `.save` directories, package caches, or downloaded source trees. See [`logs/`](logs/README.md) for the sanitized-log policy.
