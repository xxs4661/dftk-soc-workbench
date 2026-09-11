#!/usr/bin/env python3
"""Small independent Phase 7G formulas, using only NumPy and the standard library.

No production comparator, density, orbital parser, or projection helper is used.
Inputs use lattice and reciprocal *columns*, c[spin, G, band], physical f, and
spatial w.  Every band is retained.  These formulas reapply published P/D; they
do not generate an operator or reconstruct unpublished A/B orbitals.

Validation here rejects malformed mathematical inputs.  The runner owns the
predeclared numerical thresholds and comparisons to historical observations.
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np


def _finite(value: Any, name: str) -> np.ndarray:
    result = np.asarray(value)
    if result.dtype.kind not in "fciu" or not np.all(np.isfinite(result)):
        raise ValueError(f"{name}: expected finite numeric array")
    return result


def _millers(value: Any, name: str) -> np.ndarray:
    result = _finite(value, name)
    if result.ndim != 2 or result.shape[1] != 3 or result.dtype.kind not in "iu":
        raise ValueError(f"{name}: expected integer (NG, 3)")
    if len(result) == 0 or np.max(np.abs(result.astype(np.float64))) > 1_000_000:
        raise ValueError(f"{name}: empty or unreasonable integer support")
    if len(set(map(tuple, result.tolist()))) != len(result):
        raise ValueError(f"{name}: duplicate Miller triple")
    return result


def _grid(shape: Any) -> tuple[int, int, int]:
    if len(shape) != 3 or any(not isinstance(n, (int, np.integer)) or n < 2 for n in shape):
        raise ValueError("FFT grid must contain three positive integer dimensions")
    if int(np.prod(shape)) > 8_000_000:
        raise ValueError("FFT grid exceeds the bounded replay size")
    return tuple(int(n) for n in shape)


def _indices(millers: np.ndarray, shape: tuple[int, int, int]) -> tuple[np.ndarray, ...]:
    reduced = np.remainder(millers, np.asarray(shape))
    if len(np.unique(reduced, axis=0)) != len(millers):
        raise ValueError("integer support aliases on the requested FFT grid")
    return tuple(reduced[:, i] for i in range(3))


def derived_array_hash(array: np.ndarray) -> str:
    """Receipt only: new derived hashes are not original-input identity tests."""
    return hashlib.sha256(np.ascontiguousarray(array).tobytes(order="C")).hexdigest()


def product_support(miller_sets: list[np.ndarray]) -> np.ndarray:
    """Enumerate actual same-k G-G' without an NG-by-NG density matrix."""
    support: set[tuple[int, int, int]] = set()
    for raw in miller_sets:
        g = _millers(raw, "product support").astype(np.int64, copy=False)
        # The chunk controls memory; every input pair is still enumerated.
        for start in range(0, len(g), 24):
            differences = (g[start:start + 24, None, :] - g[None, :, :]).reshape(-1, 3)
            support.update(map(tuple, np.unique(differences, axis=0).tolist()))
    return np.asarray(sorted(support), dtype=np.int64).reshape(-1, 3)


def _k_arrays(kpoint: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, np.ndarray]:
    g = _millers(kpoint["millers"], "orbital Millers")
    c = _finite(kpoint["coefficients"], "orbital coefficients")
    f = _finite(kpoint["occupations"], "physical occupations")
    k = _finite(kpoint["k_cart"], "Cartesian k")
    weight = float(kpoint["weight"])
    if c.ndim != 3 or c.shape[:2] != (2, len(g)) or f.shape != (c.shape[2],):
        raise ValueError("expected c[2, NG, band] and one physical occupation per band")
    if c.shape[2] == 0 or k.shape != (3,):
        raise ValueError("empty bands or malformed Cartesian k")
    if np.any(f < -1e-12) or np.any(f > 1 + 1e-12):
        raise ValueError("physical spinor capacity is one")
    if not np.isfinite(weight) or weight < 0:
        raise ValueError("invalid spatial k weight")
    if "eigenvalues" in kpoint and _finite(kpoint["eigenvalues"], "eigenvalues").shape != f.shape:
        raise ValueError("one original eigenvalue is required per band")
    return g, c, f, weight, k


def density_from_series(millers: np.ndarray, coefficients: np.ndarray, fft_shape: Any) -> np.ndarray:
    """Finite saved density series with nbar convention, retaining its imaginary part."""
    shape = _grid(fft_shape)
    g = _millers(millers, "saved density Millers")
    coefficients = _finite(coefficients, "saved density coefficients")
    if coefficients.shape != (len(g),):
        raise ValueError("one saved density coefficient is required per Miller triple")
    reciprocal = np.zeros(shape, dtype=np.complex128)
    reciprocal[_indices(g, shape)] = coefficients
    return np.fft.ifftn(reciprocal) * int(np.prod(shape))


def direct_correlations(state: dict[str, Any], modes: np.ndarray) -> np.ndarray:
    """Non-FFT sum of c(G+K) conj(c(G)), with f and w each used once."""
    modes = _millers(modes, "correlation probes")
    volume = abs(float(np.linalg.det(_finite(state["lattice_columns"], "lattice"))))
    if volume <= 0:
        raise ValueError("nonpositive cell volume")
    values = np.zeros(len(modes), dtype=np.complex128)
    for kpoint in state["kpoints"]:
        g, c, f, weight, _ = _k_arrays(kpoint)
        positions = {tuple(vector): index for index, vector in enumerate(g.tolist())}
        for mode_index, mode in enumerate(modes):
            lower = []
            upper = []
            for gi, vector in enumerate(g):
                target = positions.get(tuple((vector + mode).tolist()))
                if target is not None:
                    lower.append(gi)
                    upper.append(target)
            if lower:
                band_values = np.sum(c[:, upper, :] * np.conj(c[:, lower, :]), axis=(0, 1))
                values[mode_index] += weight * np.dot(f, band_values) / volume
    return values


def audit_q_state(
    state: dict[str, Any], fft_shape: Any, density_millers: np.ndarray,
    density_coefficients: np.ndarray, probe_modes: np.ndarray,
    cutoff_ha: float, expected_electrons: float,
    original_common_millers: np.ndarray | None = None,
) -> dict[str, Any]:
    """Stream every k/band through density and covariant-gradient FFTs.

    Returns JSON-ready ``summary`` plus the complex ``rho``, ``rho_hat``,
    ``rho_saved``, and exact integer ``product_millers`` needed by later checks.
    No array in ``state`` is modified or renormalized.
    """
    shape = _grid(fft_shape)
    lattice = _finite(state["lattice_columns"], "lattice")
    reciprocal = _finite(state["reciprocal_columns"], "reciprocal lattice")
    if lattice.shape != (3, 3) or reciprocal.shape != (3, 3):
        raise ValueError("cell matrices must be 3 by 3 with basis vectors in columns")
    volume = abs(float(np.linalg.det(lattice)))
    if volume <= 0:
        raise ValueError("singular lattice")
    duality = float(np.linalg.norm(lattice.T @ reciprocal / (2 * np.pi) - np.eye(3)))
    ngrid = int(np.prod(shape))
    dvol = volume / ngrid
    fft_scale = ngrid / np.sqrt(volume)
    rho = np.zeros(shape, dtype=np.complex128)
    occupation_electrons = 0.0
    orbital_electrons = 0.0
    kinetic_direct = 0.0
    kinetic_gradient = 0.0
    state_records = []
    all_norm_errors = []
    all_gram_errors = []
    miller_sets = []
    for k_index, kpoint in enumerate(state["kpoints"]):
        g, c, f, weight, k_cart = _k_arrays(kpoint)
        miller_sets.append(g)
        index = _indices(g, shape)
        q = g @ reciprocal.T + k_cart
        kinetic_factors = np.sum(q * q, axis=1) / 2
        norms = np.sum(np.abs(c) ** 2, axis=(0, 1))
        flat = c.reshape(2 * len(g), c.shape[2])
        gram = flat.conj().T @ flat
        gram_error = float(np.linalg.norm(gram - np.eye(c.shape[2]), ord="fro"))
        all_gram_errors.append(gram_error)
        all_norm_errors.extend(np.abs(norms - 1).tolist())
        occupation_electrons += weight * float(np.sum(f))
        orbital_electrons += weight * float(np.dot(f, norms))
        direct_by_band = []
        gradient_by_band = []
        for band in range(c.shape[2]):
            direct = float(np.sum(np.abs(c[:, :, band]) ** 2 * kinetic_factors[None, :]))
            gradient = 0.0
            for spin in range(2):
                buffer = np.zeros(shape, dtype=np.complex128)
                buffer[index] = c[spin, :, band]
                u = np.fft.ifftn(buffer) * fft_scale
                rho += (weight * f[band]) * (u * np.conj(u))
                for axis in range(3):
                    buffer[index] = 1j * q[:, axis] * c[spin, :, band]
                    derivative = np.fft.ifftn(buffer) * fft_scale
                    gradient += 0.5 * dvol * float(np.sum(np.abs(derivative) ** 2))
            direct_by_band.append(direct)
            gradient_by_band.append(gradient)
            kinetic_direct += weight * f[band] * direct
            kinetic_gradient += weight * f[band] * gradient
        state_records.append({
            "k_index": k_index, "bands": c.shape[2], "plane_waves": len(g),
            "weight": weight, "occupations": f.tolist(), "norms": norms.tolist(),
            "gram_frobenius": gram_error,
            "k_cart": k_cart.tolist(), "k_fractional": np.linalg.solve(reciprocal, k_cart).tolist(),
            "max_plane_wave_kinetic_ha": float(np.max(kinetic_factors)),
            "cutoff_excess_ha": max(0.0, float(np.max(kinetic_factors)) - cutoff_ha),
            "kinetic_unweighted_ha": direct_by_band,
            "gradient_kinetic_unweighted_ha": gradient_by_band,
            "zero_occupation_bands": int(np.count_nonzero(f == 0)),
        })
    support = product_support(miller_sets)
    _indices(support, shape)  # Prove distinct products do not alias each other.
    saved_g = _millers(density_millers, "saved density Millers")
    saved_values = _finite(density_coefficients, "saved density coefficients")
    if saved_values.shape != (len(saved_g),):
        raise ValueError("saved density shape mismatch")
    spectrum = np.fft.fftn(rho) / ngrid
    differences = spectrum[_indices(saved_g, shape)] - saved_values
    nonzero = np.any(saved_g != 0, axis=1)
    reference_l2 = float(np.linalg.norm(saved_values[nonzero]))
    error_l2 = float(np.linalg.norm(differences[nonzero]))
    saved_set = set(map(tuple, saved_g.tolist()))
    missing = sorted(set(map(tuple, support.tolist())) - saved_set)
    probes = _millers(probe_modes, "correlation probes")
    correlated = direct_correlations(state, probes)
    probe_fft = spectrum[_indices(probes, shape)]
    saved_lookup = {tuple(vector): value for vector, value in zip(saved_g.tolist(), saved_values)}
    probe_saved_pairs = [(value, saved_lookup[tuple(mode)]) for mode, value in zip(probes.tolist(), correlated)
                         if tuple(mode) in saved_lookup]
    integral_electrons = np.sum(rho) * dvol
    saved_rho = density_from_series(saved_g, saved_values, shape)
    summary = {
        "volume_bohr3": volume, "fft_shape": list(shape),
        "reciprocal_duality_frobenius": duality,
        "kpoints": state_records, "total_states": sum(item["bands"] for item in state_records),
        "weight_sum": sum(item["weight"] for item in state_records),
        "norm_max_error": max(all_norm_errors), "gram_max_frobenius": max(all_gram_errors),
        "electrons_occupations": occupation_electrons,
        "electrons_orbital_norms": orbital_electrons,
        "electrons_real_space": float(integral_electrons.real),
        "electrons_real_space_imaginary": float(integral_electrons.imag),
        "electrons_max_error": max(abs(occupation_electrons - expected_electrons),
                                   abs(orbital_electrons - expected_electrons),
                                   float(abs(integral_electrons - expected_electrons))),
        "rho_imaginary_max": float(np.max(np.abs(rho.imag))),
        "rho_min_real": float(np.min(rho.real)),
        "saved_rho_imaginary_max": float(np.max(np.abs(saved_rho.imag))),
        "rho_derived_sha256": derived_array_hash(rho),
        "rho_real_derived_sha256": derived_array_hash(rho.real),
        "rho_hat_derived_sha256": derived_array_hash(spectrum),
        "saved_density_modes_checked": len(saved_g), "product_support_count": len(support),
        "product_support_missing_saved_count": len(missing),
        "product_support_missing_saved_modes": [list(item) for item in missing],
        "density_coefficient_max_error": float(np.max(np.abs(differences))),
        "density_nonzero_error_l2": error_l2,
        "density_nonzero_reference_l2": reference_l2,
        "density_nonzero_relative_l2": error_l2 / reference_l2 if reference_l2 else None,
        "probe_modes": probes.tolist(), "probe_count": len(probes),
        "probe_correlation_real": correlated.real.tolist(),
        "probe_correlation_imag": correlated.imag.tolist(),
        "probe_fft_max_error": float(np.max(np.abs(correlated - probe_fft))),
        "probe_saved_modes_checked": len(probe_saved_pairs),
        "probe_saved_max_error": max((float(abs(a - b)) for a, b in probe_saved_pairs), default=None),
        "kinetic_direct_ha": float(kinetic_direct), "kinetic_gradient_ha": float(kinetic_gradient),
        "kinetic_path_difference_ha": float(kinetic_gradient - kinetic_direct),
    }
    if original_common_millers is not None:
        common = _millers(original_common_millers, "original common density support")
        mask = np.ones(shape, dtype=bool)
        mask[_indices(common, shape)] = False
        summary["outside_original_common_support_l2"] = float(np.linalg.norm(spectrum[mask]))
        summary["outside_original_common_support_max"] = float(np.max(np.abs(spectrum[mask])))
        summary["outside_original_common_support_interpretation"] = (
            "Finite orbital product coefficients outside the historical common support; "
            "this does not assert unknown physical modes vanish."
        )
    return {"summary": summary, "rho": rho, "rho_hat": spectrum, "rho_saved": saved_rho,
            "product_millers": support}


def _operator_d(raw: Any) -> np.ndarray:
    d = _finite(raw, "published D")
    if d.ndim != 2 or d.shape[0] != d.shape[1] or d.shape[0] == 0:
        raise ValueError("published D must be a nonempty square matrix")
    return d


def _projection_terms(up: np.ndarray, down: np.ndarray, d: np.ndarray) -> dict[str, np.ndarray]:
    if up.shape != down.shape or up.ndim != 2 or up.shape[0] != len(d):
        raise ValueError("up/down projection amplitude dimensions disagree with D")
    total = up + down
    up_term = np.sum(np.conj(up) * (d @ up), axis=0)
    down_term = np.sum(np.conj(down) * (d @ down), axis=0)
    cross_term = 2 * np.real(np.sum(np.conj(up) * (d @ down), axis=0))
    projected = np.sum(np.conj(total) * (d @ total), axis=0)
    return {"projected": projected, "up": up_term, "down": down_term, "cross": cross_term}


def audit_nonlocal(state: dict[str, Any], published: dict[str, Any],
                   return_amplitudes: bool = False) -> dict[str, Any]:
    """Apply full published D after strict row mapping.

    Optional ``_amplitudes`` are transient complex arrays for the runner to
    compare with the published amplitudes, then remove before JSON publication.
    """
    d = _operator_d(published["D"])
    if len(state["kpoints"]) != len(published["kpoints"]):
        raise ValueError("orbital/operator k count mismatch")
    totals = dict.fromkeys(("projected", "action", "up", "down", "cross"), 0.0)
    records = []
    amplitudes = []
    max_imaginary = 0.0
    max_state_path_error = 0.0
    max_spin_error = 0.0
    for k_index, (kpoint, operator) in enumerate(zip(state["kpoints"], published["kpoints"])):
        g, c, f, weight, _ = _k_arrays(kpoint)
        pg = _millers(operator["millers"], "P row Millers")
        p = _finite(operator["P"], "published P")
        if p.shape != (2 * len(pg), len(d)):
            raise ValueError("P must use interleaved spin rows and every published projector")
        lookup = {tuple(vector): i for i, vector in enumerate(g.tolist())}
        if set(lookup) != set(map(tuple, pg.tolist())):
            raise ValueError("Q and P Miller sets do not form a strict bijection")
        order = np.asarray([lookup[tuple(vector)] for vector in pg.tolist()], dtype=np.int64)
        x = np.empty((2 * len(pg), c.shape[2]), dtype=np.complex128)
        x[0::2] = c[0, order, :]
        x[1::2] = c[1, order, :]
        y_up = p[0::2].conj().T @ x[0::2]
        y_down = p[1::2].conj().T @ x[1::2]
        if return_amplitudes:
            amplitudes.append({"up": y_up, "down": y_down})
        terms = _projection_terms(y_up, y_down, d)
        # Separate action contraction, never a (2NG)-square operator.
        action = np.sum(np.conj(x) * (p @ (d @ (p.conj().T @ x))), axis=0)
        terms["action"] = action
        max_state_path_error = max(max_state_path_error, float(np.max(np.abs(action - terms["projected"]))))
        split = terms["up"] + terms["down"] + terms["cross"]
        max_spin_error = max(max_spin_error, float(np.max(np.abs(terms["projected"] - split))))
        max_imaginary = max(max_imaginary, *(float(np.max(np.abs(value.imag))) for value in terms.values()))
        for name, values in terms.items():
            totals[name] += weight * float(np.dot(f, values.real))
        records.append({"k_index": k_index, "q_indices_in_p_order": order.tolist(),
                        "bands": len(f), "weight": weight, "occupations": f.tolist(),
                        **{f"{name}_unweighted_ha": values.real.tolist() for name, values in terms.items()}})
    result = {
        "scope": "Published frozen DFTK FR operator expectation on original QE orbitals",
        "projectors": len(d), "D_hermiticity_frobenius": float(np.linalg.norm(d - d.conj().T)),
        "kpoints": records, **{f"{key}_ha": float(value) for key, value in totals.items()},
        "path_difference_ha": float(totals["action"] - totals["projected"]),
        "spin_decomposition_difference_ha": float(totals["projected"] - totals["up"] - totals["down"] - totals["cross"]),
        "max_state_path_error_ha": max_state_path_error,
        "max_state_spin_decomposition_error_ha": max_spin_error,
        "max_imaginary_expectation_ha": max_imaginary,
    }
    if return_amplitudes:
        result["_amplitudes"] = amplitudes
    return result


def audit_projected_endpoint(kpoints: list[dict[str, Any]], published_d: np.ndarray) -> dict[str, Any]:
    """A/B projected amplitudes only; scalar-table comparisons belong to the runner.

    Each kpoint contains up/down[projector, band], occupations[band], and weight.
    Optional ``kinetic``/``nonlocal`` arrays are the published unweighted scalar
    tables, not recomputed orbital observables.
    """
    d = _operator_d(published_d)
    totals = dict.fromkeys(("projected", "up", "down", "cross"), 0.0)
    scalar_totals = dict.fromkeys(("kinetic", "nonlocal"), 0.0)
    scalar_counts = dict.fromkeys(scalar_totals, 0)
    rows = []
    max_imaginary = 0.0
    for k_index, kpoint in enumerate(kpoints):
        up = _finite(kpoint["up"], "published A/B up projections")
        down = _finite(kpoint["down"], "published A/B down projections")
        f = _finite(kpoint["occupations"], "published A/B occupations")
        weight = float(kpoint["weight"])
        terms = _projection_terms(up, down, d)
        if f.shape != terms["projected"].shape or np.any(f < -1e-12) or np.any(f > 1 + 1e-12):
            raise ValueError("A/B physical occupations or band count are invalid")
        if not np.isfinite(weight) or weight < 0:
            raise ValueError("invalid A/B spatial weight")
        record = {"k_index": k_index, "bands": len(f), "weight": weight,
                  "occupations": f.tolist()}
        for name, values in terms.items():
            totals[name] += weight * float(np.dot(f, values.real))
            max_imaginary = max(max_imaginary, float(np.max(np.abs(values.imag))))
            record[f"{name}_unweighted_ha"] = values.real.tolist()
        for name in scalar_totals:
            if name in kpoint:
                values = _finite(kpoint[name], f"published A/B {name} scalar table")
                if values.shape != f.shape:
                    raise ValueError("published scalar table band count mismatch")
                scalar_totals[name] += weight * float(np.dot(f, values))
                scalar_counts[name] += len(f)
                record[f"{name}_scalar_unweighted_ha"] = values.tolist()
        rows.append(record)
    return {"scope": "SCALAR_AND_PROJECTED_ONLY", "kpoints": rows,
            **{f"{name}_ha": value for name, value in totals.items()},
            **{f"{name}_scalar_ha": scalar_totals[name] for name in scalar_totals if scalar_counts[name]},
            "scalar_states_checked": scalar_counts,
            "spin_decomposition_difference_ha": totals["projected"] - totals["up"] - totals["down"] - totals["cross"],
            "max_imaginary_expectation_ha": max_imaginary}


def shared_potential_integral(
    fields: list[np.ndarray], coefficients: list[float], potential: np.ndarray,
    halfwidth: np.ndarray, dvol: float,
) -> dict[str, float]:
    """Combine repeated uses of one printed potential before interval propagation."""
    potential = _finite(potential, "native P2 potential in Ha")
    halfwidth = _finite(halfwidth, "native P2 halfwidth in Ha")
    if potential.shape != halfwidth.shape or np.any(halfwidth < 0) or dvol <= 0:
        raise ValueError("potential/halfwidth shape or volume is invalid")
    if len(fields) != len(coefficients) or not fields:
        raise ValueError("one algebraic coefficient is required per field")
    combined = np.zeros(potential.shape, dtype=np.complex128)
    for field, coefficient in zip(fields, coefficients):
        field = _finite(field, "density field")
        if field.shape != potential.shape or not np.isfinite(coefficient):
            raise ValueError("field shape or algebraic coefficient is invalid")
        combined += coefficient * field
    value = dvol * np.sum(combined * potential)
    return {"value_ha": float(value.real), "imaginary_ha": float(value.imag),
            "halfwidth_ha": float(dvol * np.sum(np.abs(combined) * halfwidth))}


def local_ledger(
    rho_wfc: np.ndarray, rho_saved: np.ndarray, potential: np.ndarray,
    halfwidth: np.ndarray, volume: float, kinetic_ha: float, nonlocal_ha: float,
    history: dict[str, float],
) -> dict[str, Any]:
    """Replay the explicitly signed ledger without fitting or replacing any term.

    Required history keys: O_Q, O_Q_halfwidth, S_response, drift_S,
    historical_O_grouping_drift, saved_local_replay_drift.  R_old is optional
    and used only for a difference after the independent arithmetic is done.
    """
    dvol = volume / np.asarray(potential).size
    wfc = shared_potential_integral([rho_wfc], [1.0], potential, halfwidth, dvol)
    saved = shared_potential_integral([rho_saved], [1.0], potential, halfwidth, dvol)
    delta = shared_potential_integral([rho_saved, rho_wfc], [1.0, -1.0], potential, halfwidth, dvol)
    oq = float(history["O_Q"])
    oq_halfwidth = float(history["O_Q_halfwidth"])
    if not all(np.isfinite(value) for value in (kinetic_ha, nonlocal_ha, oq, oq_halfwidth)) or oq_halfwidth < 0:
        raise ValueError("non-finite historical scalar or negative interval")
    j = kinetic_ha + nonlocal_ha + wfc["value_ha"] - oq
    nl_shaped = oq - kinetic_ha - wfc["value_ha"]
    # Add the signed leaves once.  A parent subtotal is never another addend.
    leaves = {
        "S_response": float(history["S_response"]), "J_Q": j,
        "delta_L": delta["value_ha"], "minus_drift_S": -float(history["drift_S"]),
        "historical_O_grouping_drift": float(history["historical_O_grouping_drift"]),
        "minus_saved_local_replay_drift": -float(history["saved_local_replay_drift"]),
    }
    if not all(np.isfinite(value) for value in leaves.values()):
        raise ValueError("non-finite historical ledger term")
    reconstructed = sum(leaves.values())
    result = {
        "L_wfc": wfc, "L_saved": saved, "delta_L": delta,
        "local_subtraction_difference_ha": saved["value_ha"] - wfc["value_ha"] - delta["value_ha"],
        "J_Q_ha": j, "J_Q_halfwidth_ha": wfc["halfwidth_ha"] + oq_halfwidth,
        "NL_shaped_remainder_ha": nl_shaped,
        "J_plus_NL_shaped_minus_NL_ha": j + nl_shaped - nonlocal_ha,
        "signed_leaves_ha": leaves, "R_old_reconstructed_ha": reconstructed,
        "uncertainty_scope": "Printed-token halfwidth only; excludes floating reduction error and physical convergence",
    }
    if "R_old" in history:
        result["R_old_difference_ha"] = reconstructed - float(history["R_old"])
    return result
