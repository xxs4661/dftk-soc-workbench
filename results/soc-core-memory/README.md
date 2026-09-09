# SOC core and memory audit — Phase 9A

Current status: **IMPLEMENTED_STATIC_TESTS_IN_PROGRESS**. The fixed-base REF-B0
and REF-K4 suites completed. Formal CORE suites and the two new endpoint slots
are **NOT_RUN** at this preparation commit; this is not an optimization PASS.

The [frozen plan](../../benchmarks/soc-core-memory-v1/README.md) binds the exact
base, historical source arrays, four suites, five samples and hard gates.
[Runtime design](../../docs/soc-core-runtime.md) describes ownership and checks;
[standalone synthetic example](../../examples/soc_kernels.jl) needs no repository
history or physical input. Physical formulas, dependencies and old results stay
unchanged. Only an explicit `soc-core` backend selects the new implementation.

New Si B0 SCF and its own final-density Gamma spectrum are permitted only after
static identity, equivalence, allocation and resource gates pass. DFTK K6/K8,
QE/pp, CI and new materials are NOT_RUN. Historical physical convergence and
occupation/manifold reviews are unchanged. Full arrays remain in the verified
private increment; public arithmetic must not be described as a new kernel run.
