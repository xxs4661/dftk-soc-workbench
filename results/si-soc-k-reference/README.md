# Si QE k-grid reference trend — Phase 8C

Preparation and Python implementation are in progress; formal slots NOT_RUN. The [fixed plan](../../benchmarks/si-soc-k-reference-v1/plan.json) authorizes exactly Q6-SCF → Q6-GAMMA → Q8-SCF → Q8-GAMMA, once each. B0/K4 are authenticated HISTORICAL_REUSED.

DFTK K6/K8 remain NOT_RUN, new-grid cross-code comparison NOT_ASSESSED, physical convergence NOT_ESTABLISHED. The original DFTK budget exceeds the unchanged 8 GiB limit at K6/K8; the separate QE planning budget is below that limit. Runtime memory/disk and full source/build checks must pass before any slot.

Public-native replay after results exist: `python3.12 -B scripts/si_qe_reference_evidence.py replay`. It reads only committed native gzip text, complete endpoint tables and historical public references; no UPF, private arrays, Julia or QE.
