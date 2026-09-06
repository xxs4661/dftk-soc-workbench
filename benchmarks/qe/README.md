# Quantum ESPRESSO reference cases

[Scalar Si](../si-sr-lda/README.md) has actual paired QE 7.5 evidence.
[Mg SOC](../mg-soc-fermi/checklist.md) has a prepared input only:
**PREPARED_NOT_EXECUTED**, with the first SOC E/F comparison **NOT_RUN**.
This directory does not contain another input set. QE algorithms are not copied
or translated; exact builds, inputs, units and band matching belong to each case.

Publish only whitelisted small numerical evidence under the [scientific index](../../results/README.md).
UPF payloads, wavefunctions, density binaries, caches and raw save directories stay
outside version control. Small actual XML outputs retained for offline parsing
are distinct from complete QE save directories.
