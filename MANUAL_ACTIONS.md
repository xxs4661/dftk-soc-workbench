# Manual actions

## Required for Phase 1

None at handoff. The public workbench repository and the public DFTK fork were created successfully. No upstream issue or pull request was created or modified.

## Required before later numerical phases

These are explicitly documented future values, not Phase 1 blockers:

- Verify and record the exact Quantum ESPRESSO release or commit used for reference calculations. Current value: **pending verification**.
- Select fully relativistic norm-conserving UPF files, verify their redistribution terms, and record exact family identifiers, source URLs, and SHA-256 checksums. Current values: **pending verification**.
- Re-run the local environment inventory outside restricted execution if the QE executable cannot initialize, and record its version. Current value: **pending verification**.
- Decide whether the repository owner wants a legal name rather than the GitHub login in the MIT notice. The current documented assumption is that `xxs4661` is the copyright holder because no legal name was available from the configured GitHub profile.

Do not commit pseudopotential files unless their licenses explicitly permit redistribution.
