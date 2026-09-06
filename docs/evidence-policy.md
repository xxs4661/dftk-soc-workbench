# Evidence and maintenance policy

Public results must support a scientific or tool claim with its concrete input,
execution code identity, original run ID, units, declared thresholds and limits.
Keep complete necessary data and adverse results, including independent initial
states, references and parameter settings. A PASS label or checksum cannot
replace the data required for offline review.

Use one canonical dataset per case and a single complete capability table in
[status.md](status.md). Shared environments and identical data use path/hash
references; independent runs keep their own identity-check receipts. Summaries
must be derived from or checked against the canonical data. Preserve the
independence of mathematical reference implementations. Mark array-dependent
claims as runner-reported when arrays are not public, and provide reproduction
commands. Synthetic tests are never real pseudopotential or physical evidence.

Raw runs, large arrays, local process logs, prompts and handoffs belong in ignored
working directories and a separately verified external archive. Publication is
an explicit file/field whitelist, not a recursive copy of a run directory. Before
removal, classify dependencies and unique claims, back up actual data and Git refs,
verify hashes and perform a restore. Missing unique evidence blocks its removal.
Do not overwrite historical outputs or disguise a historical run as a new run.

Freeze existing source locks, environments, input bytes and thresholds. Register a
new reviewed case/version separately when scientific scope changes; do not edit
old records to describe a new environment. Never refresh hashes to bypass a failed
identity check. Obtain pseudopotentials under their licenses without publishing
unverified payloads. Do not copy or translate QE algorithms.

Complete a change by updating affected entry points and status in the same change,
checking links, public evidence and relevant tests, and stating NOT_RUN items.
Do not mechanically refresh unrelated dates. No external validation means no
claim of external agreement. Updating documentation does not authorize merging
main; after review the owner integrates through a separate explicit action.
