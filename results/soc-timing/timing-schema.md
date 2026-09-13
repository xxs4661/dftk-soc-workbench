# Timing and stop semantics

See the [versioned timing boundaries and clock definitions](../../benchmarks/soc-timing-v1/timing-schema.md),
[declared plan](../../benchmarks/soc-timing-v1/plan.md), and [actual results](README.md).

The raw callback/checkpoint k label may be the last observed k (8/64) even outside
a k_total ancestor. It is retained verbatim; per-k wall attribution follows the
parent span tree. Whole-map writes are not assigned to that last k.

Container self time is measured but its internal cause is unclassified. The
monitor-minus-worker-span difference has different timing boundaries; neither
quantity is assigned to GC, native libraries or physical disk flushing.

The two completed map caps exercise real runtime closure. User cancellation and
wall-time expiration were exercised with synthetic subprocesses, not deliberately
triggered in these scientific runs. No resume support is certified.
