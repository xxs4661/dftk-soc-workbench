# Charge-only Mg SOC self-consistency

Two independent initial densities reached the declared engineering gates for one Mg FR-NC PBEsol case. This is a restricted workbench prototype; numerical review remains **REVIEW_REQUIRED**. QE SOC comparison is **NOT_RUN**; its input is only **PREPARED_NOT_EXECUTED**.

The cell has one ten-valence-electron Mg in a 10 bohr cube, Ecut=15 Ha, Gamma and the explicit opposite k pair, each with spatial weight 1/3. Actual FFT is 40×40×40. Electronic tau=0.001 Ha uses one global Fermi root and capacity one per physical spinor state; only charge density feeds back.

| Recorded quantity | A | B |
| --- | ---: | ---: |
| All density maps, including one additional closure | 191 | 191 |
| Physical target states per k | 24 | 24 |
| Unmixed final density L2 | 1.6542346674852517e-09 | 1.6537267865203399e-09 |
| Internal E / Ha per cell | -57.325987985147734 | -57.32598798514773 |
| S/kB | 1.2426050669902275e-34 | 1.2426050665736324e-34 |
| -TS / Ha per cell | -1.2426050669902276e-37 | -1.2426050665736325e-37 |
| F / Ha per cell | -57.325987985147734 | -57.32598798514773 |

The table is generated and checked against the canonical endpoints. The tiny nonzero entropy is retained even though Float64 F equals E. No real occupations were far enough from zero/one for the logarithmic stationarity diagnostic (0 checked, 72 excluded per run). Fractional-occupation stationarity and 24→48 expansion are synthetic-test coverage; real expansion was not triggered.

- Canonical data: [A endpoint](A/endpoint.json), [A all 191 maps](A/maps.csv), [B endpoint](B/endpoint.json), [B all 191 maps](B/maps.csv), [comparison](comparison.json).
- Near-native source streams: [A engine output](A/engine.log), [B engine output](B/engine.log); all original map lines and closure are retained, not regenerated from a PASS summary.
- [Case provenance](evidence.json) binds the original run IDs, exact executed source hashes, settings, original source fields, validation scopes and each run's start/end environment checks. The shared [environment identity](../shared/environment.json) and frozen [configuration](../../prototypes/soc_scf/phase6c.toml) each have one authority.

Formal eigenvalues/f come from the actual closure solve H[n_in]. The full H[n_out] action, old-lambda residuals and Rayleigh/f feedback are separate diagnostics, not another diagonalization. All 24 states at each of three k points retain both solve-H and own-density residual vectors. The seven-term E uses the same X/f/n_out; physical-spinor entropy enters once.

Public-only offline check (Python ≥3.11, standard library; no Julia, UPF, cache, SCF or QE):

```sh
python3 scripts/curate_soc_evidence.py check
```

This recomputes energy/DC/F algebra for every map, endpoint weighted counts and entropy, Gamma/opposite-k spectra and A/B raw spectral and E/F differences. It checks reported residual thresholds and hash-chain continuity, but cannot recreate densities or orbitals from hashes. Density differences, Pauli norms, Gram/H residuals, TR actions and energy contractions remain **runner-reported measurements requiring arrays or physical rerun**. Reassociated sums can differ in their last bits; original values are never replaced.

The [SCF entry](../../prototypes/soc_scf/README.md) describes physical rerunning with the frozen environment and exact licensed UPF. The [prepared QE input](../../benchmarks/mg-soc-fermi/qe.in) is not an execution result. No cutoff/k/temperature convergence, unique ground state, noncollinear magnetic XC, upstream-native SOC, GPU/AD or independent expert validation is claimed. The next scientific gate is the first independent QE SOC E/F comparison.
