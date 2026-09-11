#!/usr/bin/env python3
"""Independent, standard-library arithmetic on stored periodic density coefficients.

All coefficients are nbar_m in electron/bohr^3, indexed by actual integer Miller
vectors, with exp(+i q.r) reconstruction. Direct vectors are supplied as three
columns, q = 2*pi*A^(-T)m. No density adjustment, missing-mode zero fill, G+k,
k weight, spin factor, Ry conversion, native Hartree call or scientific process
is used here. math.fsum is used for real reductions. Synthetic tests supply
analytic references independently of this implementation.
"""
from __future__ import annotations

import csv
import gzip
import io
import math
import os
from pathlib import Path
import re
import struct
import tempfile

ZERO = (0, 0, 0)
TOLERANCES = {
    "reciprocal_identity_abs": 1e-12,
    "electron_abs": 1e-8,
    "zero_imag_electrons_abs": 1e-10,
    "conjugacy_relative_l2": 1e-10,
    "self_hartree_abs_ha": 1e-8,
    "energy_identity_abs_ha": 1e-10,
}
SHELL_UPPER_HA = (1.0, 5.0, 15.0, 30.0, 60.0, math.inf)
MAX_MODES = 1_000_000
MAX_CSV_BYTES = 256_000_000


def _finite(value, label):
    if isinstance(value, bool):
        raise ValueError(label + " must be a finite Float64-compatible number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(label + " must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(label + " is nonfinite")
    return result


def _miller(m):
    if not isinstance(m, (tuple, list)) or len(m) != 3:
        raise ValueError("Miller vector must contain three exact integers")
    if any(type(i) is not int or abs(i) > MAX_MODES for i in m):
        raise ValueError("Miller vector must contain bounded exact integers; G+k is unsupported")
    return tuple(m)


def _fft_size(size):
    if not isinstance(size, (tuple, list)) or len(size) != 3:
        raise ValueError("fft_size must have three integer dimensions")
    if any(type(n) is not int or n < 2 or n > 4096 for n in size):
        raise ValueError("Unsupported FFT dimension")
    return tuple(size)


def validate_coefficients(coefficients):
    if not isinstance(coefficients, dict) or not 1 <= len(coefficients) <= MAX_MODES:
        raise ValueError("Coefficients must be a nonempty bounded Miller-to-complex dictionary")
    out = {}
    for raw, value in coefficients.items():
        m = _miller(raw)
        if m in out:
            raise ValueError("Duplicate Miller vector")
        try:
            z = complex(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Invalid complex coefficient") from exc
        if not math.isfinite(z.real) or not math.isfinite(z.imag):
            raise ValueError("Nonfinite complex coefficient")
        out[m] = z
    if ZERO not in out:
        raise ValueError("Missing G=0; a missing mode is not a zero-valued present mode")
    return out


def _dot(a, b):
    return math.fsum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def reciprocal_geometry(lattice_vectors_bohr):
    """Input outer sequence contains the three columns of A, not matrix rows."""
    if len(lattice_vectors_bohr) != 3 or any(len(v) != 3 for v in lattice_vectors_bohr):
        raise ValueError("Expected three three-component direct lattice vectors")
    a = tuple(tuple(_finite(x, "lattice component") for x in v) for v in lattice_vectors_bohr)
    determinant = _dot(a[0], _cross(a[1], a[2]))
    if not math.isfinite(determinant) or determinant == 0:
        raise ValueError("Singular or nonfinite cell")
    b = tuple(tuple(2*math.pi*x/determinant for x in v) for v in
              (_cross(a[1], a[2]), _cross(a[2], a[0]), _cross(a[0], a[1])))
    error = max(abs(_dot(a[i], b[j])/(2*math.pi) - (i == j)) for i in range(3) for j in range(3))
    if not math.isfinite(error) or error > TOLERANCES["reciprocal_identity_abs"]:
        raise ValueError("Reciprocal duality check failed")
    return {"direct_vectors_bohr": [list(v) for v in a],
            "reciprocal_vectors_bohr_inv": [list(v) for v in b],
            "volume_bohr3": abs(determinant), "signed_determinant_bohr3": determinant,
            "reciprocal_identity_max_abs": error,
            "convention": "Outer lists are lattice columns; A^T B = 2*pi I"}


def q_cartesian(m, geometry):
    m = _miller(m)
    b = geometry["reciprocal_vectors_bohr_inv"]
    q = tuple(math.fsum(b[j][i]*m[j] for j in range(3)) for i in range(3))
    if not all(math.isfinite(x) for x in q):
        raise ValueError("Nonfinite Cartesian reciprocal vector")
    return q


def _q2(m, geometry):
    q = q_cartesian(m, geometry)
    value = _dot(q, q)
    if m != ZERO and (not math.isfinite(value) or value <= 0):
        raise ValueError("Invalid nonzero reciprocal norm")
    return value


def _abs2(z):
    return z.real*z.real + z.imag*z.imag


def _norm2(coefficients, modes):
    value = math.fsum(_abs2(coefficients[m]) for m in modes)
    if not math.isfinite(value):
        raise ValueError("Nonfinite squared norm")
    return value


def _status(error, tolerance):
    return "PASS" if abs(error) <= tolerance else "FAIL"


def orthonormal_to_nbar(coefficients, volume_bohr3):
    volume = _finite(volume_bohr3, "volume")
    if volume <= 0:
        raise ValueError("Volume must be positive")
    return {m: z/math.sqrt(volume) for m, z in validate_coefficients(coefficients).items()}


def hartree_potential(coefficients, geometry):
    c = validate_coefficients(coefficients)
    # G=0 is branched before evaluating a reciprocal denominator.
    return {m: (0j if m == ZERO else 4*math.pi*z/_q2(m, geometry)) for m, z in c.items()}


def hartree_energy(coefficients, geometry, modes=None):
    c = validate_coefficients(coefficients)
    selected = sorted(set(c) if modes is None else set(modes))
    if not set(selected) <= c.keys():
        raise ValueError("Missing Hartree mode; no zero filling is permitted")
    result = 2*math.pi*geometry["volume_bohr3"]*math.fsum(
        _abs2(c[m])/_q2(m, geometry) for m in selected if m != ZERO)
    if not math.isfinite(result):
        raise ValueError("Nonfinite Hartree energy")
    return result


def nyquist_modes(modes, fft_size):
    size = _fft_size(fft_size)
    return {m for m in modes if any(n % 2 == 0 and i % n == n//2 for i, n in zip(m, size))}


def _bin_map(coefficients, fft_size):
    size = _fft_size(fft_size)
    bins = {}
    for m in coefficients:
        if any(abs(i) > n//2 for i, n in zip(m, size)):
            raise ValueError("Native Miller vector outside declared FFT representable range")
        key = tuple(i % n for i, n in zip(m, size))
        if key in bins:
            raise ValueError("Two native Miller vectors alias the same FFT bin")
        bins[key] = m
    return bins


def conjugacy_report(coefficients, fft_size, *, modular):
    c = validate_coefficients(coefficients)
    size = _fft_size(fft_size)
    bins = _bin_map(c, size)
    residuals = []
    missing = []
    for m in sorted(c):
        opposite = tuple(-i for i in m)
        partner = bins.get(tuple(i % n for i, n in zip(opposite, size))) if modular else opposite
        if partner is None or partner not in c:
            missing.append(m)
        else:
            residuals.append((m, c[m]-c[partner].conjugate()))
    denom = _norm2(c, (m for m in c if m != ZERO))
    numer = math.fsum(_abs2(z) for m, z in residuals if m != ZERO)
    relative = math.sqrt(numer/denom) if denom else (0.0 if numer == 0 else None)
    max_m, max_z = max(residuals, key=lambda row: abs(row[1])) if residuals else (None, 0j)
    status = "FAIL" if missing else ("PASS" if relative is not None and relative <= TOLERANCES["conjugacy_relative_l2"] else "FAIL")
    return {"status": status, "pairing": "modulo_fft_grid" if modular else "strict_integer_negative",
            "missing_partner_count": len(missing), "missing_partner_examples": [list(m) for m in missing[:12]],
            "normalized_l2": relative, "normalization": "native nonzero coefficient squared norm; zero/zero residual is zero",
            "max_abs_electron_per_bohr3": abs(max_z), "maximum_m": list(max_m) if max_m is not None else None}


def _support_report(c, geometry, fft_size):
    bins = _bin_map(c, fft_size)
    modes = sorted(c)
    boundary = sorted(nyquist_modes(c, fft_size))
    farthest = max(modes, key=lambda m: _q2(m, geometry))
    return {"count": len(modes), "nonzero_count": len(modes)-1, "zero_count": 1,
            "unique_integer_modes": True, "unique_fft_bins": True,
            "complete_fft_grid": len(bins) == math.prod(fft_size),
            "fft_size": list(fft_size), "miller_min": [min(m[i] for m in modes) for i in range(3)],
            "miller_max": [max(m[i] for m in modes) for i in range(3)],
            "max_q_bohr_inv": math.sqrt(_q2(farthest, geometry)), "max_q_m": list(farthest),
            "nyquist_representative_count": len(boundary), "nyquist_examples": [list(m) for m in boundary[:12]],
            "nyquist_policy": "Keep every native representative in native sums; never add its aliased opposite"}


def dataset_report(coefficients, geometry, fft_size, *, expected_electrons=10.0,
                   historical_hartree_ha=None, require_complete_fft=False):
    c = validate_coefficients(coefficients)
    fft_size = _fft_size(fft_size)
    volume = geometry["volume_bohr3"]
    expected = _finite(expected_electrons, "expected electron count")
    if expected <= 0:
        raise ValueError("Expected electron count must be positive")
    support = _support_report(c, geometry, fft_size)
    ne = volume*c[ZERO].real
    zimag = volume*c[ZERO].imag
    epot = hartree_potential(c, geometry)
    energy = hartree_energy(c, geometry)
    alternate = volume/2*math.fsum((c[m].conjugate()*epot[m]).real for m in sorted(c))
    err = energy-alternate
    modular = conjugacy_report(c, fft_size, modular=True)
    strict = conjugacy_report(c, fft_size, modular=False)
    nonzero2 = _norm2(c, (m for m in c if m != ZERO))
    source_diff = None if historical_hartree_ha is None else energy-_finite(historical_hartree_ha, "historical Hartree")
    gates = {"electron_count_status": _status(ne-expected, TOLERANCES["electron_abs"]),
             "zero_imaginary_status": _status(zimag, TOLERANCES["zero_imag_electrons_abs"]),
             "discrete_conjugacy_status": modular["status"],
             "reciprocal_support_status": "FAIL" if require_complete_fft and not support["complete_fft_grid"] else "PASS",
             "independent_energy_sum_status": _status(err, TOLERANCES["energy_identity_abs_ha"]),
             "self_hartree_reconstruction_status": "NOT_ASSESSED" if source_diff is None else _status(source_diff, TOLERANCES["self_hartree_abs_ha"])}
    return {**gates, "engineering_status": "FAIL" if "FAIL" in gates.values() else "PASS",
            "electron_count": ne, "expected_electrons": expected, "electron_count_difference": ne-expected,
            "zero_imaginary_electrons": zimag, "support": support,
            "modular_conjugacy": modular, "strict_conjugacy": strict,
            "native_nonzero_density_coefficient_norm": math.sqrt(nonzero2),
            "native_nonzero_density_l2_electron_bohr_minus_3_over_2": math.sqrt(volume*nonzero2),
            "native_hartree_ha": energy, "native_half_n_vh_ha": alternate,
            "independent_energy_sum_difference_ha": err,
            "historical_hartree_ha": historical_hartree_ha,
            "self_hartree_difference_ha": source_diff,
            "self_hartree_absolute_difference_ha": None if source_diff is None else abs(source_diff),
            "hartree_scope": "Electron-electron periodic Hartree only, native nonzero support, zero mean potential; not total electrostatics"}


def common_support(left, right, fft_left, fft_right):
    l = validate_coefficients(left); r = validate_coefficients(right)
    _bin_map(l, fft_left); _bin_map(r, fft_right)
    intersection = set(l) & set(r) - {ZERO}
    ambiguous = intersection & (nyquist_modes(l, fft_left) | nyquist_modes(r, fft_right))
    common = intersection - ambiguous
    missing_opposites = sorted(m for m in common if tuple(-i for i in m) not in common)
    return {"common": common, "ambiguous": ambiguous,
            "left_exclusive": set(l)-common-{ZERO}, "right_exclusive": set(r)-common-{ZERO},
            "missing_opposites": missing_opposites}


def iter_common_differences(left, right, geometry, fft_left, fft_right):
    """Complete complex differences, without materializing a duplicate data package."""
    support = common_support(left, right, fft_left, fft_right)
    if support["missing_opposites"]:
        raise ValueError("Unambiguous common support is not closed under strict -m")
    for m in sorted(support["common"]):
        delta = left[m]-right[m]
        q = q_cartesian(m, geometry)
        vdelta = delta*(4*math.pi/_dot(q, q))
        yield {"m": list(m), "q_bohr_inv": list(q), "left": [left[m].real, left[m].imag],
               "right": [right[m].real, right[m].imag], "delta_nbar": [delta.real, delta.imag],
               "delta_vh_ha": [vdelta.real, vdelta.imag]}


def _difference_metrics(left, right, modes, geometry, *, potential=False):
    modes = sorted(modes)
    volume = geometry["volume_bohr3"]
    factors = {m: 4*math.pi/_q2(m, geometry) if potential else 1.0 for m in modes}
    lv = {m: left[m]*factors[m] for m in modes}
    rv = {m: right[m]*factors[m] for m in modes}
    delta = {m: lv[m]-rv[m] for m in modes}
    numer = _norm2(delta, modes); denom = _norm2(rv, modes)
    maximum = None
    if modes:
        m = max(modes, key=lambda key: abs(delta[key]))
        maximum = {"m": list(m), "q_bohr_inv": list(q_cartesian(m, geometry)),
                   "left_real": lv[m].real, "left_imag": lv[m].imag,
                   "right_real": rv[m].real, "right_imag": rv[m].imag,
                   "difference_real": delta[m].real, "difference_imag": delta[m].imag,
                   "abs_difference": abs(delta[m])}
    return {"status": "MEASURED" if modes else "NOT_APPLICABLE_EMPTY_COMMON_SUPPORT",
            "mode_count": len(modes), "projected_l2": math.sqrt(volume*numer),
            "projected_l2_unit": "Ha bohr^(3/2)" if potential else "electron bohr^(-3/2)",
            "relative_l2": math.sqrt(numer/denom) if denom else None,
            "relative_l2_status": "MEASURED" if denom else "NOT_APPLICABLE_ZERO_REFERENCE_FLUCTUATION",
            "reference_nonzero_coefficient_norm_squared": denom,
            "denominator_scope": "Only right coefficients on this common nonzero set; no G=0 and no max(...,1)",
            "maximum": maximum, "coefficient_unit": "Ha" if potential else "electron/bohr^3"}


def _energy_parts(left, right, common, lex, rex, geometry):
    omega = geometry["volume_bohr3"]
    lc = hartree_energy(left, geometry, common); rc = hartree_energy(right, geometry, common)
    le = hartree_energy(left, geometry, lex); re_ = hartree_energy(right, geometry, rex)
    ordered = sorted(common)
    linear = 2*math.pi*omega*math.fsum(2*(right[m].conjugate()*(left[m]-right[m])).real/_q2(m, geometry) for m in ordered)
    quadratic = 2*math.pi*omega*math.fsum(_abs2(left[m]-right[m])/_q2(m, geometry) for m in ordered)
    return {"left_common_ha": lc, "right_common_ha": rc, "common_difference_ha": lc-rc,
            "left_exclusive_ha": le, "right_exclusive_ha": re_,
            "common_linear_cross_term_ha": linear, "common_nonnegative_quadratic_ha": quadratic,
            "common_cross_decomposition_difference_ha": (lc-rc)-math.fsum([linear, quadratic]),
            "native_difference_from_parts_ha": math.fsum([lc, -rc, le, -re_])}


def compare_coefficients(left, right, geometry, fft_left, fft_right):
    l = validate_coefficients(left); r = validate_coefficients(right)
    sup = common_support(l, r, fft_left, fft_right)
    common, lex, rex = sup["common"], sup["left_exclusive"], sup["right_exclusive"]
    parts = _energy_parts(l, r, common, lex, rex, geometry)
    native_diff = hartree_energy(l, geometry)-hartree_energy(r, geometry)
    parts["native_difference_ha"] = native_diff
    parts["support_decomposition_difference_ha"] = native_diff-parts["native_difference_from_parts_ha"]
    parts["support_decomposition_status"] = _status(parts["support_decomposition_difference_ha"], TOLERANCES["energy_identity_abs_ha"])
    parts["cross_decomposition_status"] = _status(parts["common_cross_decomposition_difference_ha"], TOLERANCES["energy_identity_abs_ha"])
    # Fixed half-open/closed shells: lower < |q|^2/2 <= upper, with zero excluded.
    shell_rows = []
    lower = 0.0
    cumulative = []
    for upper in SHELL_UPPER_HA:
        belong = lambda m: lower < _q2(m, geometry)/2 <= upper
        cs = {m for m in common if belong(m)}; ls = {m for m in lex if belong(m)}; rs = {m for m in rex if belong(m)}
        ep = _energy_parts(l, r, cs, ls, rs, geometry)
        cumulative.append(ep["native_difference_from_parts_ha"])
        shell_rows.append({"lower_exclusive_ha": lower, "upper_inclusive_ha": upper if math.isfinite(upper) else None,
                           "upper_is_infinity": not math.isfinite(upper), "common_count": len(cs),
                           "left_exclusive_count": len(ls), "right_exclusive_count": len(rs),
                           **ep, "cumulative_signed_native_difference_ha": math.fsum(cumulative)})
        lower = upper
    parts["shell_native_sum_difference_ha"] = native_diff-math.fsum(cumulative)
    parts["shell_sum_status"] = _status(parts["shell_native_sum_difference_ha"], TOLERANCES["energy_identity_abs_ha"])
    fractions = {}
    for label, c in [("left", l), ("right", r)]:
        den = _norm2(c, (m for m in c if m != ZERO)); num = _norm2(c, common)
        fractions[label] = {"native_nonzero_coefficient_norm": math.sqrt(den),
                            "common_nonzero_coefficient_norm": math.sqrt(num),
                            "common_norm_fraction": math.sqrt(num/den) if den else None,
                            "status": "MEASURED" if den else "NOT_APPLICABLE_ZERO_NATIVE_FLUCTUATION",
                            "scope": "Norm coverage only, not physical precision/correctness"}
    support_status = "PASS" if not sup["missing_opposites"] else "FAIL"
    native_difference = None
    if set(l) == set(r):
        delta = {m: l[m]-r[m] for m in l}
        native_difference = {
            "status": "MEASURED_ON_IDENTICAL_NATIVE_SUPPORT", "mode_count_including_zero": len(l),
            "density_l2_including_zero": math.sqrt(geometry["volume_bohr3"]*_norm2(delta, sorted(delta))),
            "density_l2_unit": "electron bohr^(-3/2)",
            "scope": "Full identical native support, including original Nyquist representatives; no absent-mode zero fill",
        }
    return {"common_G_density_comparison_status": "MEASURED" if common and support_status == "PASS" else "UNRESOLVED",
            "reciprocal_support_status": support_status, "common_nonzero_count": len(common),
            "literal_intersection_nonzero_count": len(common)+len(sup["ambiguous"]),
            "nyquist_ambiguous_common_count": len(sup["ambiguous"]),
            "nyquist_ambiguous_examples": [list(m) for m in sorted(sup["ambiguous"])[:12]],
            "common_missing_strict_negative_count": len(sup["missing_opposites"]),
            "common_missing_strict_negative_examples": [list(m) for m in sup["missing_opposites"][:12]],
            "left_exclusive_nonzero_count": len(lex), "right_exclusive_nonzero_count": len(rex),
            "exclusive_scope": "Native support outside unambiguous common set, including retained Nyquist boundary representatives",
            "density": _difference_metrics(l, r, common, geometry),
            "hartree_potential": _difference_metrics(l, r, common, geometry, potential=True),
            "potential_source": "Independent Poisson construction from stored density; native potential not extracted",
            "norm_coverage": fractions, "hartree_decomposition": parts, "shells": shell_rows,
            "identical_native_support_density_difference": native_difference,
            "full_cross_code_realspace_density_status": "NOT_ASSESSED",
            "complex_difference_replay": "iter_common_differences on complete canonical coefficients; no amplitude-only or fitted phase comparison"}


def analyze_density_hartree(datasets, lattice_vectors_bohr, fft_sizes, *,
                            historical_hartree_ha=None, expected_electrons=10.0,
                            state_bindings=None, historical_total_energies_ha=None):
    """Pure offline report. Missing sources stay BLOCKED; cross-code sizes are measured.

    A_in/B_in are optional local diagnostics. Source hashes/run binding and raw
    n_out-n_in norm checks belong to the separate extraction/recording layer.
    """
    allowed = {"A_out", "B_out", "QE", "A_in", "B_in"}
    if not isinstance(datasets, dict) or not datasets or not set(datasets) <= allowed:
        raise ValueError("Unknown or missing density dataset labels")
    geometry = reciprocal_geometry(lattice_vectors_bohr)
    h = historical_hartree_ha or {}; states = state_bindings or {}; totals = historical_total_energies_ha or {}
    sources = {}; cleaned = {key: validate_coefficients(c) for key, c in datasets.items()}
    for label, c in cleaned.items():
        if label not in fft_sizes:
            raise ValueError("Missing declared FFT grid for " + label)
        sources[label] = dataset_report(c, geometry, fft_sizes[label], expected_electrons=expected_electrons,
            historical_hartree_ha=h.get(label), require_complete_fft=label != "QE")
        sources[label]["density_state_binding_status"] = states.get(label, "NOT_PROVIDED_BY_EXTRACTION")
    comparisons = {}
    for left, right in [("A_out", "QE"), ("B_out", "QE"), ("A_out", "B_out"), ("A_out", "A_in"), ("B_out", "B_in")]:
        name = left + "_minus_" + right
        if left not in cleaned or right not in cleaned:
            comparisons[name] = {"common_G_density_comparison_status": "BLOCKED_MISSING_SOURCE"}
            continue
        report = compare_coefficients(cleaned[left], cleaned[right], geometry, fft_sizes[left], fft_sizes[right])
        report["left"] = left; report["right"] = right
        if left in totals and right in totals:
            diff = _finite(totals[left], "historical total")-_finite(totals[right], "historical total")
            report["historical_total_energy_difference_ha"] = diff
            report["other_energy_terms_undecomposed_difference_ha"] = diff-report["hartree_decomposition"]["native_difference_ha"]
            report["residual_scope"] = "Remaining undecomposed energy-term difference; not attributed to SOC/nonlocal/radial error"
        if right.endswith("_in"):
            report["public_replay_scope"] = "Only replayable if corresponding complete n_in coefficients are published; otherwise local-array diagnostic"
        comparisons[name] = report
    fail = any(s["engineering_status"] == "FAIL" for s in sources.values())
    fail |= any(c.get("reciprocal_support_status") == "FAIL" or any(v == "FAIL" for k, v in c.get("hartree_decomposition", {}).items() if k.endswith("status")) for c in comparisons.values())
    return {"schema_version": 1, "derivation_status": "NEW_EXTRACTION_FROM_HISTORICAL_ARRAYS",
            "geometry": geometry, "thresholds": dict(TOLERANCES), "sources": sources, "comparisons": comparisons,
            "engineering_status": "FAIL" if fail else "PASS",
            "numerical_agreement_status": "REVIEW_REQUIRED", "physical_convergence_status": "NOT_ESTABLISHED",
            "residual_attribution_status": "NOT_ESTABLISHED", "ieee_warning_origin_status": "NOT_LOCALIZED",
            "new_scf_status": "NOT_RUN", "new_eigensolve_status": "NOT_RUN",
            "full_cross_code_realspace_density_status": "NOT_ASSESSED",
            "summation": "Float64 complex inputs, real math.fsum reductions; no correction, filtering or missing-mode zero fill",
            "source_binding_scope": "Raw-file/run/state certification is separate from public coefficient arithmetic replay"}


def write_coefficients_gzip(path, datasets_same_support):
    """Canonical UTF-8/LF CSV, repr(Float64), fixed gzip mtime and no filename."""
    if not isinstance(datasets_same_support, dict) or not datasets_same_support:
        raise ValueError("No coefficient datasets")
    names = sorted(datasets_same_support)
    if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", n) for n in names):
        raise ValueError("Invalid dataset column name")
    data = {n: validate_coefficients(datasets_same_support[n]) for n in names}
    modes = sorted(data[names[0]])
    if any(set(data[n]) != set(modes) for n in names):
        raise ValueError("Shared-G CSV requires exactly identical native supports")
    text = io.StringIO(newline="")
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(["m1", "m2", "m3"] + [n+s for n in names for s in ("_real", "_imag")])
    for m in modes:
        writer.writerow(list(m) + [repr(v) for n in names for v in (data[n][m].real, data[n][m].imag)])
    raw = text.getvalue().encode("utf-8")
    if len(raw) > MAX_CSV_BYTES:
        raise ValueError("Canonical CSV exceeds size bound")
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode="wb", filename="", mtime=0, compresslevel=9) as stream:
        stream.write(raw)
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    # Build and validate every byte before publishing this data file.
    expected = read_coefficients_gzip_bytes(compressed.getvalue())
    if set(expected) != set(data) or any(set(expected[n]) != set(data[n]) for n in names):
        raise ValueError("Canonical coefficient round-trip support failed")
    for n in names:
        for m, z in data[n].items():
            decoded = expected[n][m]
            if struct.pack("!dd", decoded.real, decoded.imag) != struct.pack("!dd", z.real, z.imag):
                raise ValueError("Canonical coefficient Float64 bit-pattern round-trip failed")
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".coefficients-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(compressed.getvalue())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"rows": len(modes), "datasets": names, "encoding": "UTF-8/LF CSV in deterministic gzip; Float64 repr round-trip",
            "gzip_mtime": 0, "support_policy": "All native modes retained, including exact-zero coefficients and Nyquist representatives"}


def read_coefficients_gzip_bytes(payload):
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as stream:
            raw = stream.read(MAX_CSV_BYTES+1)
        if len(raw) > MAX_CSV_BYTES or b"\r" in raw:
            raise ValueError("Oversize or non-LF coefficient CSV")
        reader = csv.reader(io.StringIO(raw.decode("utf-8"), newline=""))
        header = next(reader)
        if header[:3] != ["m1", "m2", "m3"] or len(header) < 5 or (len(header)-3) % 2:
            raise ValueError("Unexpected coefficient CSV columns")
        names = []
        for i in range(3, len(header), 2):
            name = header[i].removesuffix("_real")
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name) or header[i:i+2] != [name+"_real", name+"_imag"] or name in names:
                raise ValueError("Invalid or duplicate coefficient dataset columns")
            names.append(name)
        out = {n: {} for n in names}
        for count, row in enumerate(reader, 1):
            if count > MAX_MODES or len(row) != len(header):
                raise ValueError("Coefficient CSV row length/count invalid")
            m = tuple(int(v) for v in row[:3])
            if any(str(i) != v for i, v in zip(m, row[:3])):
                raise ValueError("Noncanonical integer Miller token")
            _miller(m)
            for j, name in enumerate(names):
                if m in out[name]:
                    raise ValueError("Duplicate Miller vector in CSV")
                out[name][m] = complex(_finite(row[3+2*j], "real coefficient"), _finite(row[4+2*j], "imaginary coefficient"))
        return {name: validate_coefficients(data) for name, data in out.items()}
    except (OSError, EOFError, UnicodeError, StopIteration, csv.Error) as exc:
        raise ValueError("Invalid or truncated gzip coefficient CSV") from exc


def read_coefficients_gzip(path):
    path = Path(path)
    if path.stat().st_size > MAX_CSV_BYTES:
        raise ValueError("Compressed coefficient file exceeds size bound")
    return read_coefficients_gzip_bytes(path.read_bytes())
