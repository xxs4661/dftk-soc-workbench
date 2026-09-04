# Quantum ESPRESSO benchmark inputs

This directory is reserved for future QE input files and concise run instructions. QE is an independent numerical reference; its source will not be copied or translated.

Inputs should pin the QE version or commit, executable build details, pseudopotential identifier and SHA-256 checksum, lattice and positions, energy cutoffs, explicit k-points, occupations, smearing, XC functional, convergence thresholds, and relativistic/noncollinear flags. Any comparison must document unit conversions and band-matching rules.

Do not commit pseudopotential payloads, `.save` directories, wavefunctions, charge-density binaries, temporary XML, mixing files, or large raw output. Small sanitized logs may be placed under [`../../results/logs/`](../../results/logs/README.md).
