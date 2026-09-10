# Getting started

There are two small, working interfaces to explore: review a published regression
from public data, or run the existing synthetic matrix-core example. Neither
performs a new material SCF calculation. Use a full Git clone of
[this repository](https://github.com/xxs4661/dftk-soc-workbench); the review entry
needs its historical objects, which a source ZIP or shallow clone does not supply.

## Review the published core regression

With Git and an existing **Python 3.12.x** interpreter, run from the repository root:

```sh
python3.12 -B scripts/review.py core-regression
```

Omitting `core-regression` selects the same review. The
[wrapper](../scripts/review.py) creates an independent temporary clone outside
your repository, checks out the fixed
[published snapshot](https://github.com/xxs4661/dftk-soc-workbench/tree/e98552ccfb96fb27e07c9816559856d133b58310),
and runs its original strict completion checker. It leaves your branch and index
unchanged, removes its own temporary clone, and does not fetch or install anything.

The terminal shows the original exit code, completion state and retained review
qualifications. A zero exit verifies the stated public records and arithmetic,
including the recorded SCF/Γ endpoints. It does not rerun those endpoints, recover
private orbital arrays, establish physical convergence, or turn outstanding
performance questions into a PASS. Child-checker failures retain their exit and
diagnostics. Python 3.12.14 is the recorded historical Python version; other minor
versions are not accepted by this entry.

To retain full checker output and preparation metadata, choose a **new directory
outside the repository**, whose parent already exists:

```sh
python3.12 -B scripts/review.py core-regression --log-dir /path/to/new-review-log
```

The [reproduction guide](reproducibility.md) explains this scope and other
snapshot-specific reviews. Source and public-projection hashes authenticate
different bytes; a reported measurement is only independently recomputable when
its required numerical data are public.

## Run the numerical core example

Use an existing **Julia 1.12.7** installation. The example needs only Julia's
standard library, not the workbench environment, a pseudopotential or QE:

```sh
julia --startup-file=no --project=@stdlib examples/soc_kernels.jl
```

The [example](../examples/soc_kernels.jl) constructs complex synthetic matrices,
applies $PDP^\dagger$ with a nontrivial row mapping, and checks the action and
occupied expectation against dense/direct references. It prints those two
differences and fails if a check exceeds its declared tolerance. It is not a
material calculation or a registered Julia package.

The source includes are relative to the script itself. From another working
directory, replace the placeholder below with your clone's absolute path:

```sh
julia --startup-file=no --project=@stdlib /path/to/dftk-soc-workbench/examples/soc_kernels.jl
```

See [methods](methods.md) for the representation and energy conventions and
[core interfaces](soc-core-runtime.md) for workspace ownership, capacities and
callback requirements.

## Work with the DFTK adapters

Follow the [frozen environment setup](../environment/workbench/README.md) when
working on the DFTK-backed adapters or their tests. Fetch the locked source
checkouts before instantiating the saved Manifest, then inspect the environment
identity result. This larger environment is unnecessary for the two entries above.

The [case directory](../benchmarks/README.md) records the actual Mg/Si inputs and
experimental launchers. Those launchers enforce case, source, execution-identity
and sometimes one-shot restrictions; some reproductions also require private raw
arrays. They are not a general material-input API. New calculations need a
separately specified input, source and validation design, without recreating old
authorization records. Start a design discussion using the
[contribution guide](../CONTRIBUTING.md), and check the
[current limits](status.md) before choosing a research use.
