# Configuration and source records

This directory records the exact external references used by the workbench. [`sources.lock`](sources.lock) is intentionally human-readable so changes to scientific provenance remain reviewable.

Before adding a numerical benchmark, update the lock with:

- the DFTK and parser source commits actually tested;
- the Quantum ESPRESSO release or commit actually tested;
- each pseudopotential's exact family identifier and source;
- the SHA-256 checksum calculated from the exact local file;
- the pseudopotential licensing or redistribution reference; and
- the UTC time at which mutable upstream metadata was checked.

The words **pending verification** identify explicit future values. They must be resolved before results depending on those values are interpreted.

Do not store tokens, credentials, local absolute paths, pseudopotential payloads, or downloaded source trees here.
