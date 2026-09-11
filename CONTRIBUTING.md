# Contributing

DFTK SOC workbench is an experimental research project. Contributions that make
its numerical conventions, evidence or small interfaces easier to verify are
welcome. Start with [current capabilities](docs/status.md),
[methods](docs/methods.md) and the [core interface](docs/soc-core-runtime.md).
The repository owner, **xxs4661**, is responsible for this project and its review.

## Discussing a problem or design

Use this repository's [issue tracker](https://github.com/xxs4661/dftk-soc-workbench/issues)
for a reproducible bug report or a proposed change. Include the commit, relevant
command, dependency versions, expected behavior and actual output. Identify
whether the example is synthetic, public-data replay or a material calculation.
Keep native warnings and failing checks, and remove credentials and private paths.
A small reproducer is more useful than a complete private execution directory.

Discuss changes to representation, occupations, energy conventions or supported
materials before implementing them. A proposal here does not imply that DFTK
maintainers have accepted the design; [integration questions](docs/soc-upstream-risks.md)
remain open.

## Making a change

Keep changes focused and explain their scientific or usability purpose. Update
current documentation with the implementation. Numerical changes should state
the affected convention, the independent reference used, the test inputs and
tolerances, and any change in measured behavior. Avoid tests that only repeat
the same implementation. Do not change a tolerance or dependency solely to turn
a failure into success.

Run the checks relevant to the change. For the public review entry:

```sh
python3.12 -B -m unittest discover -s tests -p 'test_review.py' -v
python3.12 -B scripts/review.py core-regression
```

For the existing numerical matrix interface:

```sh
julia --startup-file=no --project=@stdlib examples/soc_kernels.jl
```

The example is synthetic. Neither command runs a new material SCF. Follow the
[reproduction guide](docs/reproducibility.md) for other fixed public checks and
[environment instructions](environment/workbench/README.md) for tests that
require DFTK. Check local links and `git diff --check`. Report the actual commands,
exits and missing prerequisites; old upstream test counts are not new test runs.
The historical experiment launchers are restricted research records, not a
ready-made submission route for arbitrary materials.

## Evidence, licensing and attribution

Scientific input, execution identity, result and warning files are versioned
historical evidence. Add a separately identified result rather than overwriting
an old one. Current explanatory pages can be edited directly; run checkers that
bind their old bytes in the appropriate historical snapshot. The
[evidence policy](docs/evidence-policy.md) distinguishes these responsibilities.

Contributions must be compatible with the repository's [MIT license](LICENSE).
Check the terms of third-party data and software before redistribution; UPF
payloads and upstream source copies are not included here. Cite relevant methods
and software. Disclose material AI assistance and verify its output: contributors
remain responsible for correctness, provenance and licensing. See the project's
[AI assistance disclosure](docs/ai-assistance.md).
