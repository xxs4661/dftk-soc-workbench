"""Finite Si K6 engineering admission; this module never launches a worker.

Predictions, sampled observations and scientific success are separate.  The
unchanged historical budget is input evidence, not an extra execution gate.
"""
from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import math
from pathlib import Path
import platform
import re
import shutil
import subprocess

GIB = 1024**3
MIB = 1024**2
LIMIT_BYTES = 8 * GIB
WARNING_BYTES = 7 * GIB
RUNTIME_MARGIN_BYTES = 2 * GIB
UNOBSERVED_MARGIN_BYTES = GIB
HISTORY_400_BYTES = 512 * MIB
SERIALIZATION_BYTES = GIB
CAPACITY_BYTES = 64 * MIB
DISK_RESERVE_BYTES = 10 * GIB
# One first-map, latest and final checkpoint, all per-k latest solves, native
# logs and an ordinary incremental archive plus restore allowance.  A failure
# cannot consume this reserve silently: disk is checked again before each slot.
REQUIRED_FREE_DISK_BYTES = 24 * GIB
SOURCES = {
    'results/soc-core-memory/memory-budget.json': '87db0af845b707e0575b6ed0ac989872c8ba72c83e4693382af1d6b05f474c0e',
    'results/soc-core-memory/completion/OPT-B0-SCF/resource.json': '6cebb2cac91ced8ef288686c60962e4b807a38104ae338d05e099aa9e03277e9',
    'results/soc-core-memory/completion/OPT-B0-SCF/worker.json': 'cd7457c4af7e14289c32626fe46a4533857c60abb816f24dc6d43884b58a7bbe',
    'benchmarks/si-soc-k-reference-v1/resource-geometry.json': '60d1cfa53ce2051fad10bc0369f6abe5133834ecb2b81987015d21f9d7be3775',
    'benchmarks/si-soc-k-reference-v1/K6/case.json': 'e63471b90f7673524beabd7a240f069619bac807884bc0d60e7d37f5c598fc03',
    'scripts/si_qe_reference_evidence.py': '1c7480df90296ba4ee8fbb99d4d17f8bfbbfe4fa17c50b88ae33ab8378a06314',
}
GEOMETRY = dict(nk=216, sum_ng=457287, max_ng=2138,
                projectors_per_k=72, fft_size=[48, 48, 48])
BUFFER_SOURCES = {
    'base/iobuffer.jl': '730edfc92371ac494a39bb27c91f07227bf43bd21006a327ecaadf6f4ea5976b',
    'base/array.jl': '156389c374e625ae52bee0bb53057f61728716ed34d7b63680486316ea171dca',
}
FFT_LIFETIME_SOURCES = {
    'DFTK_commit': '2f51b91213e26726fb9c6a17e5fae235a1412d01',
    'src/terms/Hamiltonian.jl': '89bee8e28abb90fa8cbaeceadf4aae38269059efb28152423e53666dd5fd4df8',
    'src/terms/hartree.jl': 'f0dc3ef175bb74d374ffb0ed74140f29c5c87048d01b67c2c0bb026cfa1d7e48',
    'src/terms/xc.jl': '1c60dd1969d843345fbab554ab541819787ec7c96435a1b04f8a6abe948b194b',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, name, *, positive=False):
    require(type(value) is int and value >= (1 if positive else 0),
            name + ' must be a ' + ('positive' if positive else 'nonnegative') + ' integer')
    return value


def bound_sources(root):
    root = Path(root).resolve()
    values = {}
    for relative, expected in SOURCES.items():
        p = root / relative
        require(p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root),
                'Missing or aliased resource source: ' + relative)
        raw = p.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected,
                'Resource source hash differs: ' + relative)
        if p.suffix == '.json':
            values[relative] = json.loads(raw)
    return values


def geometry(root):
    """Re-enumerate only K6 using the unchanged public integer-G enumerator.

    This is geometry arithmetic, not DFTK context construction. The actual
    native context must separately reproduce these counts before either map.
    """
    values = bound_sources(root)
    old = values['benchmarks/si-soc-k-reference-v1/resource-geometry.json']['profiles']['K6']
    case = values['benchmarks/si-soc-k-reference-v1/K6/case.json']
    spec = importlib.util.spec_from_file_location('extra_frozen_geometry',
                                                Path(root) / 'scripts/si_qe_reference_evidence.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate_explicit_grid(6, case['kpoints'])
    rows = [module.wave_sphere(6, p) for p in itertools.product((0, 1, 2, -3, -2, -1), repeat=3)]
    counts = [r['ng'] for r in rows]
    require(counts == old['ng_in_declared_order'], 'Independent K6 counts differ from historical geometry')
    require([r['canonical_integer_G_sha256'] for r in rows] == old['G_list_sha256_in_declared_order'],
            'Independent K6 G lists differ from historical geometry')
    require(sum(counts) == GEOMETRY['sum_ng'] and max(counts) == GEOMETRY['max_ng'],
            'K6 sum/max NG changed')
    return dict(status='GEOMETRY_VERIFIED_NOT_NATIVE_CONTEXT', **GEOMETRY,
                ng_in_declared_order=counts,
                maximum_G_difference=max(max(r['max_same_k_difference_component']) for r in rows),
                source_sha256=SOURCES.copy(),
                scope='Reused frozen integer-G geometry routine; no orbital, density or numerical context')


def inferred_buffer_capacity(payload_bytes):
    """Julia1.12.7 default Memory-backed IOBuffer, monotonic writes, bytes.

    Bound the last growth by overallocation(final_length); the default initial
    capacity is32. No seek/overwrite/truncate or alternative IO backend is
    covered. This is an inferred active-buffer capacity, not observed RSS.
    """
    n = integer(payload_bytes, 'serialization_payload_bytes', positive=True)
    return max(32, n + 3 * (1 << (n.bit_length() * 7 // 8)) + n // 8)


def _observed_allowances(observed):
    history = HISTORY_400_BYTES
    serial = SERIALIZATION_BYTES
    if observed is not None:
        require(type(observed) is dict, 'Pilot lifecycle must be an object')
        h = integer(observed.get('history_bytes'), 'history_bytes', positive=True)
        n = integer(observed.get('history_map_count'), 'history_map_count', positive=True)
        require(n in (1, 2), 'Only one/two completed pilot maps may be extrapolated')
        largest = integer(observed.get('max_record_bytes'), 'max_record_bytes', positive=True)
        payload = integer(observed.get('serialization_payload_bytes'), 'serialization_payload_bytes', positive=True)
        capacity = integer(observed.get('serialization_buffer_capacity_bytes'),
                           'serialization_buffer_capacity_bytes', positive=True)
        require(capacity >= payload, 'Serialization capacity is smaller than its payload')
        evidence = observed.get('serialization_capacity_evidence')
        require(evidence in ('MEASURED_ACTIVE_BUFFER', 'INFERRED_FROM_FROZEN_BUFFER_GROWTH'),
                'Serialization capacity needs an explicit measured/inferred evidence class')
        if evidence == 'INFERRED_FROM_FROZEN_BUFFER_GROWTH':
            require(observed.get('serialization_capacity_source_sha256') == BUFFER_SOURCES and
                    observed.get('julia_version') == '1.12.7', 'Unbound Julia buffer-growth source/version')
            require(capacity == inferred_buffer_capacity(payload), 'Inferred capacity does not use the frozen bound')
        # At least twice the observed per-map graph, including headers/capacity.
        # The largest observed record protects against a small first map.
        history = max(history, 2 * max(math.ceil(h / n), largest) * 400)
        # Keep at least 25% above the measured/inferred active buffer capacity. Dead
        # buffers/allocator slack remain within the separate unchanged runtime
        # reserve; this is not a proof of prompt GC or a continuous RSS bound.
        serial = max(serial, math.ceil(1.25 * capacity))
    return history, serial


def engineering_budget(root, *, maps=400, observed=None):
    require(type(maps) is int and maps in (2, 400), 'Only two-map/full-400-map budgets are allowed')
    values = bound_sources(root)
    old = values['results/soc-core-memory/memory-budget.json']
    terms = {k: integer(v['bytes'], k, positive=True) for k, v in old['accounting_terms'].items()}
    require(terms['runtime_library_margin_unchanged'] == RUNTIME_MARGIN_BYTES,
            'Original 2 GiB runtime reserve changed')
    require(sum(terms.values()) == 6788850928 == old['known_terms_plus_retained_allowances_subtotal_bytes'],
            'Historical accounting subtotal changed')
    original_terms = terms.copy()
    # The legacy24-state real tensor is not allocated by the owned density
    # path. Its actual14 buffers have already been included explicitly above.
    # Three H generations each share one single-thread scalar FFT scratch over
    # all k; price overlapping field transforms and nonzero unknown staging.
    nr = 48**3
    terms.pop('frozen_broad_FFT_allowance_retained')
    terms['native_scalar_H_fft_scratch_three_generations'] = 3 * 16 * nr
    terms['two_common_traversals_complex_field_transforms'] = 2 * (2 + 4 + 3) * 16 * nr
    terms['additional_unobserved_native_FFT_staging'] = 64 * MIB
    history, serial = _observed_allowances(observed)
    terms.update(history_diagnostics=math.ceil(history * maps / 400),
                 callback_serialization_active_buffer=serial,
                 container_and_dictionary_extra_capacity=CAPACITY_BYTES)
    # Constructor precedes retained SCF orbital/history graphs. Retain the
    # full FFT/field allowances, original runtime margin and explicit per-k
    # assembly allowance. Do not sum mutually different lifecycle phases.
    constructor_names = ('one_retained_P_set', 'one_retained_D_per_k', 'kinetic_vectors',
        'live_padded_G_and_mapping', 'copied_G_mapping_device_snapshots',
        'both_inverse_mapping_tables', 'core_nonlocal_workspace', 'core_component_workspace',
        'core_full_H_staging', 'core_density_FFT_workspace', 'native_scalar_H_fft_scratch_three_generations',
        'two_common_traversals_complex_field_transforms', 'additional_unobserved_native_FFT_staging',
        'frozen_broad_field_allowance_retained', 'runtime_library_margin_unchanged',
        'container_and_dictionary_extra_capacity')
    construction = {k: terms[k] for k in constructor_names}
    construction['per_k_P_assembly_and_transfer_transients'] = 64 * MIB
    map_bytes = sum(terms.values())
    peak = max(map_bytes, sum(construction.values()))
    return dict(schema_version=1, status='ESTIMATE_WITHIN_LIMIT' if peak < LIMIT_BYTES else 'RESOURCE_BLOCKED',
                maps=maps, estimated_peak_bytes=peak, estimated_peak_gib=peak / GIB,
                process_group_limit_bytes=LIMIT_BYTES, warning_bytes=WARNING_BYTES,
                terms_bytes=terms, construction_terms_bytes=construction,
                original_accounting_terms_bytes=original_terms,
                construction_estimate_bytes=sum(construction.values()), map_estimate_bytes=map_bytes,
                history_400_bytes=history, serialization_allowance_bytes=serial,
                evidence_level='ENGINEERING_ESTIMATE_NOT_PEAK_BOUND', source_sha256=SOURCES.copy(),
                fft_lifetime_sources=FFT_LIFETIME_SOURCES.copy(),
                original_B0_sampled_peak_bytes=values['results/soc-core-memory/completion/OPT-B0-SCF/resource.json']['peak_aggregate_rss_bytes'],
                outstanding_uncertainty=['JIT/native allocator and unreachable buffers within unchanged 2 GiB reserve',
                    'Later history shape and serialization capacity need pilot observations',
                    'Sampling can miss short-lived peaks; no OS hard isolation'],
                fft_replacement_basis='Owned runtime density uses the separately inventoried14 buffers; DFTK2f51b9 Hamiltonian.jl shares one FFT scratch per H generation/thread; hartree.jl and xc.jl field transforms separately priced;64MiB unknown FFT staging retained',
                scope='Original budget preserved as evidence; one legacy tensor allowance replaced by owned-path lifecycle accounting, no RSS subtraction or changed legacy coefficient')


def _host_ok(host):
    require(type(host) is dict, 'Current host preflight is required')
    require(host.get('status') == 'ELIGIBLE' and host.get('severe_pressure') is False,
            'Host resource preflight is unavailable or blocked')
    require(integer(host.get('free_disk_bytes'), 'free_disk_bytes') >= REQUIRED_FREE_DISK_BYTES,
            'Insufficient free space for checkpoints, increment, restore and reserve')
    require(host.get('active_numerical_processes') == [], 'Another numerical worker is active')


def pilot_eligibility(root, *, host):
    try:
        _host_ok(host)
        budget = engineering_budget(root, maps=2)
        require(budget['estimated_peak_bytes'] < LIMIT_BYTES, 'Construction/two maps exceed the 8 GiB estimate')
        return dict(status='PILOT_ELIGIBLE', native_exit_code=None, budget=budget,
                    scope='Permission to consume the one diagnostic slot; not formal SCF admission or success')
    except (OSError, ValueError, KeyError, TypeError) as error:
        return dict(status='RESOURCE_BLOCKED', native_exit_code=None, reason=str(error))


def formal_admission(root, pilot, *, host):
    try:
        _host_ok(host)
        require(type(pilot) is dict and pilot.get('status') == 'PILOT_COMPLETED_NOT_SCF_CONVERGED',
                'Completed diagnostic pilot required; SCF PASS is not its protocol')
        n = integer(pilot.get('completed_maps'), 'completed_maps', positive=True)
        require(n in (1, 2), 'Pilot used more than the authorized two maps')
        require(type(pilot.get('native_exit_code')) is int and pilot['native_exit_code'] == 0 and
                type(pilot.get('recorder_exit_code')) is int and pilot['recorder_exit_code'] == 0,
                'Pilot native/recorder execution failed or not run')
        g = pilot.get('geometry')
        require(type(g) is dict and g == GEOMETRY and
                all(type(g[k]) is int for k in ('nk', 'sum_ng', 'max_ng', 'projectors_per_k')) and
                type(g['fft_size']) is list and all(type(x) is int for x in g['fft_size']),
                'Native K6 geometry/projector count or type differs')
        r = pilot.get('resource')
        require(type(r) is dict and r.get('status') == 'PASS' and r.get('owned_process_cleanup_status') == 'PASS',
                'Pilot resource/cleanup failed')
        require(type(r.get('native_exit_code')) is int and r['native_exit_code'] == 0 and
                r.get('limit_bytes') == LIMIT_BYTES, 'Pilot monitor used another limit or native exit')
        require(integer(r.get('nonempty_samples'), 'nonempty_samples', positive=True) > 0,
                'Pilot has no process RSS observations')
        peak = integer(r.get('peak_aggregate_rss_bytes'), 'peak_aggregate_rss_bytes', positive=True)
        require(peak < LIMIT_BYTES, 'Pilot reached 8 GiB')
        o = pilot.get('lifecycle')
        require(type(o) is dict and o.get('history_map_count') == n, 'Pilot history/map observation missing')
        budget = engineering_budget(root, maps=400, observed=o)
        require(budget['estimated_peak_bytes'] < LIMIT_BYTES, 'Observed history/buffer growth makes full engineering estimate exceed 8 GiB')
        uncovered_history = max(0, budget['history_400_bytes'] - o['history_bytes'])
        uncovered_serial = max(0, budget['serialization_allowance_bytes'] - o['serialization_buffer_capacity_bytes'])
        # Parent final checkpoint and output records can grow after the pilot;
        # retain 128 MiB even though the pilot observes representative writing.
        later_output = 128 * MIB
        extrapolated = peak + uncovered_history + uncovered_serial + later_output + UNOBSERVED_MARGIN_BYTES
        require(extrapolated < LIMIT_BYTES, 'Pilot peak plus later growth/writeout and 1 GiB fluctuation margin exceeds 8 GiB')
        require(peak < WARNING_BYTES, 'Pilot reached 7 GiB warning; no full-run growth headroom certified')
        return dict(status='PROVISIONAL_GO_WITH_MONITORING', native_exit_code=None,
                    engineering=budget, pilot_peak_bytes=peak, observational_estimate_bytes=extrapolated,
                    remaining_growth_bytes=extrapolated - peak,
                    observational_terms_bytes=dict(pilot_peak=peak, uncovered_history=uncovered_history,
                        uncovered_serialization=uncovered_serial, later_output=later_output,
                        unobserved_fluctuation_margin=UNOBSERVED_MARGIN_BYTES),
                    scope='Two independent engineering screens; monitored execution admission, not a proven peak bound or SCF success')
    except (OSError, ValueError, KeyError, TypeError) as error:
        return dict(status='RESOURCE_BLOCKED', native_exit_code=None, reason=str(error))


def _command(argv):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    require(p.returncode == 0, 'Read-only host query failed: ' + argv[0] + ' ' + p.stderr.strip())
    return p.stdout


def host_pressure():
    """Read host pressure, never allocate test memory or terminate a process.

    macOS uses the reported system-wide free percentage and, when available,
    the kernel pressure level. Linux uses MemAvailable and memory PSI full.
    These declared operational warning indicators are not memory guarantees.
    """
    try:
        name = platform.system()
        if name == 'Darwin':
            out = _command(['/usr/bin/memory_pressure', '-Q'])
            found = re.search(r'System-wide memory free percentage:\s*(\d+)%', out)
            require(found is not None, 'Missing macOS memory-pressure percentage')
            free = int(found[1])
            require(0 <= free <= 100, 'Invalid system-wide free percentage')
            level = None
            try:
                level = int(_command(['/usr/sbin/sysctl', '-n', 'kern.memorystatus_vm_pressure_level']).strip())
            except (ValueError, OSError, subprocess.SubprocessError):
                pass
            return dict(status='KNOWN', severe=free <= 5 or level == 4,
                        system_wide_free_percent=free, kernel_pressure_level=level,
                        criterion='Kernel critical level 4 or system-wide free percentage <=5%; operational indicator')
        if name == 'Linux':
            text = Path('/proc/meminfo').read_text()
            fields = {m[0]: int(m[1]) * 1024 for m in re.findall(r'^(MemTotal|MemAvailable):\s+(\d+) kB$', text, re.M)}
            require(set(fields) == {'MemTotal', 'MemAvailable'} and fields['MemTotal'] > 0, 'Missing Linux available memory')
            psi = Path('/proc/pressure/memory').read_text()
            found = re.search(r'^full avg10=([0-9.]+)', psi, re.M)
            require(found is not None, 'Missing Linux memory PSI full average')
            full = float(found[1])
            require(math.isfinite(full) and full >= 0, 'Invalid Linux memory PSI')
            free = 100 * fields['MemAvailable'] / fields['MemTotal']
            return dict(status='KNOWN', severe=free <= 5 or full >= 10,
                        available_percent=free, full_avg10_percent=full,
                        criterion='MemAvailable <=5% or full memory PSI avg10 >=10%; operational indicator')
        raise ValueError('No declared host-pressure reader for ' + name)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        return dict(status='UNKNOWN', severe=None, reason=str(error))


def process_table():
    out = _command(['ps', '-axo', 'pid=,ppid=,pgid=,rss=,command='])
    rows = []
    for line in out.splitlines():
        values = line.split(None, 4)
        require(len(values) == 5 and all(x.isdecimal() for x in values[:4]), 'Unparseable process table')
        rows.append(dict(zip(('pid', 'ppid', 'pgid', 'rss_kib'), map(int, values[:4])), command=values[4]))
    require(rows, 'Empty process table')
    return rows


def active_numerical_processes(rows):
    matches = []
    for row in rows:
        command = row['command']
        executable = Path(command.split(None, 1)[0]).name
        if ((executable.startswith('julia') and any(s in command for s in
                ('run_si_soc.jl', 'run_soc_scf.jl', 'measure.jl', 'soc-extra-v1/'))) or
                executable in ('pw.x', 'pp.x')):
            matches.append(dict(pid=row['pid'], pgid=row['pgid'], executable=executable))
    return matches


def host_preflight(root, archive_root=None):
    try:
        rows = process_table()
        active = active_numerical_processes(rows)
        pressure = host_pressure()
        require(pressure['status'] == 'KNOWN', 'Host pressure unavailable: ' + pressure.get('reason', 'unknown'))
        free = shutil.disk_usage(root).free
        archive_free = shutil.disk_usage(archive_root or root).free
        if platform.system() == 'Darwin':
            total = int(_command(['/usr/sbin/sysctl', '-n', 'hw.memsize']).strip())
        else:
            total = int(re.search(r'^MemTotal:\s+(\d+)', Path('/proc/meminfo').read_text(), re.M)[1]) * 1024
        require(total > 0, 'Invalid host physical memory')
        ok = not pressure['severe'] and not active and min(free, archive_free) >= REQUIRED_FREE_DISK_BYTES and total >= LIMIT_BYTES
        return dict(status='ELIGIBLE' if ok else 'RESOURCE_BLOCKED', severe_pressure=pressure['severe'],
                    pressure=pressure, free_disk_bytes=min(free, archive_free), total_memory_bytes=total,
                    active_numerical_processes=active, process_table_available=True,
                    reason=None if ok else 'Pressure, existing numerical worker, physical memory or disk preflight blocked',
                    scope='Current read-only host snapshot; sampled monitoring must continue during execution')
    except (ValueError, OSError, TypeError, subprocess.SubprocessError) as error:
        return dict(status='INSUFFICIENT_EVIDENCE', severe_pressure=None, reason=str(error),
                    native_exit_code=None)


def monitor_decision(rss_bytes, *, remaining_growth_bytes=None, pressure=None):
    try:
        integer(rss_bytes, 'rss_bytes')
        if pressure is None:
            pressure = host_pressure()
        require(type(pressure) is dict and pressure.get('status') == 'KNOWN' and type(pressure.get('severe')) is bool,
                'Host-pressure observation unavailable')
        if pressure['severe'] or rss_bytes >= LIMIT_BYTES:
            return dict(status='RESOURCE_LIMIT', reason='Severe host pressure or sampled group RSS >=8 GiB')
        if rss_bytes >= WARNING_BYTES:
            if remaining_growth_bytes is None:
                return dict(status='STOP_AT_SAFE_BOUNDARY', reason='7 GiB warning without a priced remaining-growth estimate')
            integer(remaining_growth_bytes, 'remaining_growth_bytes')
            if rss_bytes + remaining_growth_bytes >= LIMIT_BYTES:
                return dict(status='STOP_AT_SAFE_BOUNDARY', reason='7 GiB warning plus declared remaining growth reaches8 GiB')
            return dict(status='WARNING', reason='7 GiB warning; priced growth remains below8 GiB, retain warning')
        return dict(status='CONTINUE', reason=None)
    except (ValueError, TypeError, KeyError) as error:
        return dict(status='MONITORING_UNAVAILABLE', reason=str(error))
