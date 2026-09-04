# Scripts

No automation scripts are included in Phase 1.

Future scripts should perform one reproducible task, expose their inputs, fail clearly, and avoid hidden downloads. They must never print credentials or commit package caches, pseudopotential payloads, raw QE save directories, downloaded source trees, or large generated outputs.

Every future script should document:

- required executable versions;
- expected working directory and inputs;
- generated files and whether they are safe to commit;
- deterministic settings or seeds where relevant; and
- a small verification command or invariant.

Numerical automation must read or update the provenance described in [`../config/README.md`](../config/README.md).
