# Reproducible environment

Use the dedicated [workbench Julia environment](workbench/README.md). Its
Project/Manifest/checksums and [source lock](../config/sources.lock) are frozen;
relative checkout paths support relocation after fetching the locked sources.

The [shared recorded identity](../results/shared/environment.json) captures actual
loaded Julia/source identity. Case evidence retains independent run check receipts
and case-specific QE binary/launch identity. These historical records are not a
claim that a reader's current environment matches; run the identity check in a new
Julia process before physical reproduction.

[DFTK development notes](dftk-development-notes.md) describe the pinned upstream
workflow. [The host checklist](local-macos-template.md) is a template, not a measured
machine report. Do not publish usernames, private absolute paths or credentials.
For public-only offline review use Python 3.9; the QE-input preparer needs Python
3.12+ for `tomllib`. No environment or package versions were changed by curation.

The combined publication check uses Python 3.9 for exact historical scalar
arithmetic and `python3.12` on PATH for standard-library TOML in the prototype
checks (`--modern-python PATH` selects an existing Python 3.11+ interpreter).
It installs no packages or environments.
