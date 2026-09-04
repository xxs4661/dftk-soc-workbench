# Manual actions

## Required for Phase 1

None at handoff. The public workbench repository and the public DFTK fork were created successfully. No upstream issue or pull request was created or modified.

## Required for Phase 2

None. Source acquisition, environment collection, bootstrap, and the upstream DFTK `:minimal` test selection all executed successfully.

The restricted local execution context did not permit the CPU and memory `sysctl` queries, and `pw.x -version` did not return normally. These missing optional inventory fields did not block DFTK bootstrap or testing; the local template includes the exact commands for collecting them later from an unrestricted terminal.

## Required for Phase 3

No action is required to reproduce the source inspection or the recorded local runtime inspection. The selected fully relativistic Mg NC-UPF was resolved through the installed PseudoPotentialData ecosystem, inspected under `.work/pseudos/`, and was not committed.

Before redistributing that UPF, a human must positively verify and document its data-license terms. Package source licensing alone is not treated as permission to redistribute the artifact.

## Required before later numerical phases

These are explicitly documented future values, not Phase 1 blockers:

- Verify and record the exact Quantum ESPRESSO release or commit used for reference calculations. Current value: **pending verification**.
- Before any numerical benchmark, confirm that the inspected Mg file and family are appropriate for the intended material and calculation. The Phase 3 family identifier, source URL, and checksum are recorded; redistribution permission remains **not verified**.
- Re-run the local environment inventory outside restricted execution if the QE executable cannot initialize, and record its version. Current value: **pending verification**.
- Decide whether the repository owner wants a legal name rather than the GitHub login in the MIT notice. The current documented assumption is that `xxs4661` is the copyright holder because no legal name was available from the configured GitHub profile.

Do not commit pseudopotential files unless their licenses explicitly permit redistribution.
