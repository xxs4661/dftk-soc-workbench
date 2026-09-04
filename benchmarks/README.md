# Benchmarks

This directory will hold small, matched DFTK and Quantum ESPRESSO benchmark inputs and human-readable metadata. No numerical benchmark has been run in Phase 1.

The planned progression is:

1. scalar-relativistic baseline;
2. independent cutoff and k-point convergence;
3. fully relativistic QE reference;
4. future DFTK spinor/SOC calculation; and
5. comparison of eigenvalues and SOC splittings with declared tolerances.

Use [`dftk/`](dftk/README.md) and [`qe/`](qe/README.md) for code-specific inputs. Put small sanitized summaries in [`../results/`](../results/README.md). Do not commit pseudopotential files, `.save` directories, wavefunctions, raw mixing files, or large outputs.

Each benchmark must record the physical system, units, lattice, positions, electron count and occupations, XC functional, relativistic mode, cutoffs, k-points, convergence thresholds, smearing, source revisions, executable versions, and exact pseudopotential identifiers and SHA-256 checksums.
