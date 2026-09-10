# Evidence and documentation

Current explanations describe the software as it exists now. The root README,
capability table, user guides and top-level navigation may be rewritten when
capabilities or presentation change. Scientific case inputs, execution code
identities, results, native warnings and recorded failures describe a particular
experiment and must not be backfilled to match a newer page.

## What a result needs

A scientific claim needs its input and units, exact execution identity, declared
comparison method and tolerances, necessary numerical data, and limitations.
Publish enough numerical information and replay code to check the claim. Retain
native warnings and meaningful failed experiments as well as successful ones.
A successful process or a PASS summary does not by itself establish physical
convergence, cross-code agreement or an accepted upstream design.

Distinguish three forms of evidence:

- **Raw identity:** a hash binds the original bytes read by an execution.
- **Public projection identity:** a separate hash binds the selected, sanitized
  or compressed public representation. It need not equal the raw hash.
- **Recomputed numbers:** replay evaluates the stated arithmetic from available
  data under its recorded floating-point contract. This is different from either
  byte identity or a new electronic-structure calculation.

Array-dependent measurements remain runner-reported when their necessary source
arrays are not public. Say which arrays and acquisition steps would be required
for independent repetition. Synthetic functions and matrices establish numerical
properties of a test, not a real pseudopotential or material prediction.

## Current pages and historical snapshots

Use one canonical dataset and one main explanation for each result; other pages
link to them. Do not copy numerical packs to simplify navigation. Existing case
reports, plans, datasets and their paths are historical records. An authorized
new result or corrected interpretation gets a distinct version and references
its predecessor.

Some old checkers bind documentation bytes or the entire Git tree. Run them in
their fixed, clean snapshots with the original exit semantics. Do not broaden an
old allowlist, change a recorded hash or suppress a failed checker to let current
documentation pass. [Reproduction scopes](reproducibility.md) and the
[history index](history.md) identify these boundaries.

## What belongs outside the repository

Large raw arrays, original save directories, private inputs, repetitive process
transcripts, agent handoffs and complete operational backup manifests normally
belong in ignored local storage and a verified repository-external archive.
Existing public operational files that are replay dependencies remain available;
this curation does not delete them. A same-machine backup is not an off-site copy.
Before removing unique data, classify its dependencies, preserve it and its Git
identity, verify hashes and perform an actual restore.

Use an explicit file/field selection for publication. Do not commit credentials,
private machine paths, package caches, unlicensed UPF payloads or upstream source
copies. Keep frozen dependency and input records intact. Licensing, interpretation
and the accuracy of AI-assisted work remain the contributor's responsibility.
