# DFTK benchmark inputs

This directory is reserved for future DFTK input files and concise run instructions. Phase 1 does not modify or vendor DFTK source code and contains no SOC implementation.

Begin with a scalar-relativistic baseline that mirrors the physical and numerical choices in [`../qe/`](../qe/README.md). A later spinor path may be added only after its interfaces exist and its status is stated accurately.

Inputs should pin the DFTK commit, Julia version, project dependencies, pseudopotential identifier and SHA-256 checksum, cutoff, explicit k-points, occupations, XC functional, convergence thresholds, and requested observables. Keep `Manifest.toml`, downloaded packages, pseudopotential files, and large calculation outputs outside version control.
