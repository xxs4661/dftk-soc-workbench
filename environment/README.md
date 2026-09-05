# Environment records

Reproducible numerical comparisons require the software, hardware, and execution context to be recorded independently of input files.

- [`codex-environment.md`](codex-environment.md) records the environment observed while Phase 1 was created.
- [`local-macos-template.md`](local-macos-template.md) is a checklist for a future local benchmark environment.
- [`dftk-development-notes.md`](dftk-development-notes.md) summarizes development and testing instructions at the locked DFTK commit.

Phase 2's observed host facts are generated in [`../results/environment-summary.md`](../results/environment-summary.md).

Do not record usernames, absolute home-directory paths, tokens, credential-helper output, or other secrets. Use **pending verification** for information that cannot be observed safely.

Phase 4A uses the dedicated, versioned [workbench environment](workbench/README.md), including its Pkg-generated Manifest and runtime identity checks. Earlier environment summaries remain historical records.
