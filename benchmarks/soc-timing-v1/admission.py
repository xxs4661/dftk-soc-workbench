"""Read-only B0/K4 geometry and conservative two-map admission; no contexts."""
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path

GIB = 1024**3
LIMIT = 8 * GIB
WARNING = 7 * GIB
GROWTH = 2 * GIB


def admission(root, profile):
    root = Path(root)
    if profile not in ('B0', 'K4'):
        raise ValueError('Only the new B0/K4 short diagnostics are admitted')
    p = root / 'scripts/si_qe_reference_evidence.py'
    spec = importlib.util.spec_from_file_location('timing_geometry', p)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    n = 2 if profile == 'B0' else 4
    rows = [module.wave_sphere(n, q) for q in itertools.product(module.axis(n), repeat=3)]
    nk, total, maximum = len(rows), sum(r['ng'] for r in rows), max(r['ng'] for r in rows)
    nr = 48**3
    # Retain the old Si route's coefficients, including the broad FFT and
    # runtime allowances; do not subtract measured static allocations/RSS.
    terms = dict(retained_orbitals_and_solver=16*2*maximum*30*(12*nk+60),
                 projectors_and_snapshots=16*2*maximum*72*nk*4 + 16*72*72*nk,
                 bounded_fft_workspaces=16*2*nr*24*8,
                 density_core_local_fields=8*nr*100,
                 runtime_library_margin=2*GIB,
                 serialization_allowance=GIB,
                 two_map_history_allowance=(512*1024**2*2+399)//400,
                 container_capacity_allowance=64*1024**2)
    # These are explicit engineering allowances, not a formal RSS bound.
    estimate = sum(terms.values())
    budget_path = root/'results/soc-core-memory/memory-budget.json'
    old = json.loads(budget_path.read_text())
    observed = old['completed_static_observations']['CORE-'+profile]
    empirical = observed['sampled_peak_rss_bytes'] + GROWTH
    return dict(schema_version=1, profile=profile,
                status='ELIGIBLE_WITH_MONITORING' if max(estimate, empirical) < LIMIT else 'RESOURCE_BLOCKED',
                nk=nk, sum_ng=total, max_ng=maximum, fft_size=[48,48,48],
                terms_bytes=terms, engineering_estimate_bytes=estimate,
                historical_static_peak_bytes=observed['sampled_peak_rss_bytes'],
                historical_run_id=observed['run_id'], historical_execution_commit=observed['execution_commit'],
                historical_source_sha256=hashlib.sha256(budget_path.read_bytes()).hexdigest(),
                historical_peak_plus_fixed_reserve_bytes=empirical,
                limit_bytes=LIMIT, warning_bytes=WARNING, remaining_growth_bytes=GROWTH,
                estimate_scope='Conservative original geometry coefficients plus explicit output/history allowances; not an absolute peak bound',
                unknown='Transient compiler/native allocations and collection timing; priced reserves are not measurements',
                monitoring_rule='max(cumulative process-group RSS peak, authenticated worker highwater) + fixed growth >= limit requests stop; hard limit/pressure independent')
