# Si SOC QE k-grid reference — Phase 8C

Preparation only; no Phase 8C numerical slot has run. The [plan](plan.json), [allowed differences](allowed-differences.json), [source index](sources.json), [resource plan](resource-plan.json) and [replay contract](replay-contract.json) are fixed before execution.

K6 and K8 each allow one QE SCF and one own-density Γ solve, in that order. Cases inherit unchanged K4 metadata; inherited DFTK fields are reference only and do not authorize a DFTK worker. K6 is not a superset of K4; K8 contains K4/B0 but not K6. All full point lists use integer axes and 17 significant digits.

The original DFTK budget exceeds 8 GiB at K6/K8; no DFTK run will test that estimate. QE has a separate dimensional resource envelope and monitored 8 GiB cap. See [geometry](resource-geometry.json); this is Python geometry, not a DFTK context or numerical result.

Runtime commands and final public-native replay will be documented with the implementation. B0/K4 remain authenticated HISTORICAL_REUSED, physical convergence NOT_ESTABLISHED and new-grid cross-code comparison NOT_ASSESSED.
