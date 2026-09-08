"""Small synthetic-only tests of the independent Phase 7G mathematical path."""

import copy
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import independent_orbital_math as independent


def synthetic_state():
    lattice = np.array([[2., 1., 0.], [0., 3., 0.], [0., 0., 4.]])
    # Written explicitly so the tilted-cell test can detect a transposed basis.
    reciprocal = np.array([[np.pi, 0., 0.], [-np.pi / 3, 2 * np.pi / 3, 0.],
                           [0., 0., np.pi / 2]])
    g = np.array([[1, 1, 0], [-1, 0, 1]], dtype=np.int64)
    c = np.array([[[np.sqrt(.3)], [np.sqrt(.4) * np.exp(.37j)]],
                  [[np.sqrt(.2) * 1j], [np.sqrt(.1) * np.exp(-.71j)]]])
    return {"lattice_columns": lattice, "reciprocal_columns": reciprocal,
            "kpoints": [{"millers": g, "coefficients": c,
                         "occupations": np.array([.6]), "eigenvalues": np.array([2.]),
                         "k_cart": np.array([.2, -.1, .3]), "weight": .25}]}


def synthetic_density(state):
    kpoint = state["kpoints"][0]
    c = kpoint["coefficients"][:, :, 0]
    delta = kpoint["millers"][1] - kpoint["millers"][0]
    modes = np.array([[0, 0, 0], delta, -delta], dtype=np.int64)
    correlation = .15 / 24 * (c[0, 1] * c[0, 0].conjugate() + c[1, 1] * c[1, 0].conjugate())
    return modes, np.array([.15 / 24, correlation, correlation.conjugate()])


def synthetic_operator():
    return {"D": np.array([[2., 1. + .5j], [1. - .5j, -1.]]),
            "kpoints": [{"millers": np.array([[-1, 0, 1], [1, 1, 0]], dtype=np.int64),
                         "P": np.array([[1. + 1j, .2], [.3j, -.5], [.7, 1j], [1., .4 - .2j]])}]}


class IndependentMathSyntheticTests(unittest.TestCase):
    def test_tilted_cell_nonzero_k_complex_density_and_gradient(self):
        state = synthetic_state()
        modes, coefficients = synthetic_density(state)
        before = copy.deepcopy(state)
        result = independent.audit_q_state(state, (9, 9, 9), modes, coefficients, modes,
                                           cutoff_ha=20., expected_electrons=.15,
                                           original_common_millers=np.zeros((1, 3), dtype=np.int64))
        summary = result["summary"]
        self.assertLess(summary["reciprocal_duality_frobenius"], 1e-14)
        self.assertLess(summary["density_coefficient_max_error"], 1e-15)
        self.assertLess(summary["probe_fft_max_error"], 1e-15)
        self.assertEqual(summary["probe_saved_modes_checked"], 3)
        self.assertLess(summary["probe_saved_max_error"], 1e-15)
        self.assertLess(summary["electrons_max_error"], 1e-14)
        self.assertEqual(summary["product_support_count"], 3)
        self.assertEqual(summary["product_support_missing_saved_count"], 0)
        self.assertGreater(summary["outside_original_common_support_l2"], 0)
        q0 = np.array([np.pi + .2, np.pi / 3 - .1, .3])
        q1 = np.array([-np.pi + .2, np.pi / 3 - .1, np.pi / 2 + .3])
        expected_t = .15 * (.5 * np.dot(q0, q0) + .5 * np.dot(q1, q1)) / 2
        self.assertAlmostEqual(summary["kinetic_direct_ha"], expected_t, places=13)
        self.assertAlmostEqual(summary["kinetic_gradient_ha"], expected_t, places=13)
        for field in ("coefficients", "millers", "occupations", "eigenvalues", "k_cart"):
            np.testing.assert_array_equal(state["kpoints"][0][field], before["kpoints"][0][field])

    def test_all_bands_capacity_and_spatial_weight_once(self):
        state = synthetic_state()
        kpoint = state["kpoints"][0]
        c = np.zeros((2, 2, 3), dtype=np.complex128)
        c[0, 0, 0] = c[1, 0, 1] = c[0, 1, 2] = 1
        kpoint.update(coefficients=c, occupations=np.array([1., .4, 0.]),
                      eigenvalues=np.array([1., 2., 3.]), weight=.3)
        second = copy.deepcopy(kpoint)
        second.update(weight=.7, k_cart=np.array([-.2, .1, 0.]))
        state["kpoints"].append(second)
        modes, _ = synthetic_density(synthetic_state())
        coefficients = np.array([1.4 / 24, 0, 0], dtype=np.complex128)
        summary = independent.audit_q_state(state, (9, 9, 9), modes, coefficients, modes,
                                             20., 1.4)["summary"]
        self.assertEqual(summary["total_states"], 6)
        self.assertEqual(summary["kpoints"][0]["zero_occupation_bands"], 1)
        self.assertLess(summary["electrons_max_error"], 1e-14)
        self.assertEqual(summary["gram_max_frobenius"], 0.)
        self.assertEqual(len(summary["kpoints"][1]["kinetic_unweighted_ha"]), 3)
        state["kpoints"][0]["occupations"][0] = 2
        with self.assertRaisesRegex(ValueError, "capacity is one"):
            independent.direct_correlations(state, modes)

    def test_nonorthogonal_zero_occupation_band_is_still_checked(self):
        state = synthetic_state()
        kpoint = state["kpoints"][0]
        kpoint["coefficients"] = np.repeat(kpoint["coefficients"], 2, axis=2)
        kpoint["occupations"] = np.array([.6, 0.])
        kpoint["eigenvalues"] = np.array([1., 2.])
        modes, coefficients = synthetic_density(synthetic_state())
        summary = independent.audit_q_state(state, (9, 9, 9), modes, coefficients, modes,
                                             20., .15)["summary"]
        self.assertLess(summary["norm_max_error"], 1e-14)
        self.assertAlmostEqual(summary["gram_max_frobenius"], np.sqrt(2), places=14)

    def test_complex_correlation_has_correct_orientation_and_conjugation(self):
        state = synthetic_state()
        modes, coefficients = synthetic_density(state)
        actual = independent.direct_correlations(state, modes)
        np.testing.assert_allclose(actual, coefficients, atol=1e-16, rtol=1e-14)
        self.assertGreater(abs(actual[1].imag), 1e-4)
        self.assertGreater(abs(actual[1] - actual[1].conjugate()), 1e-4)

    def test_strict_miller_permutation_interleaving_and_non_diagonal_d(self):
        state = synthetic_state()
        published = synthetic_operator()
        result = independent.audit_nonlocal(state, published)
        self.assertEqual(result["kpoints"][0]["q_indices_in_p_order"], [1, 0])
        c = state["kpoints"][0]["coefficients"][:, :, 0]
        x = np.array([c[0, 1], c[1, 1], c[0, 0], c[1, 0]])
        p = published["kpoints"][0]["P"]
        d = published["D"]
        # A tiny dense synthetic oracle is safe; the actual implementation never
        # constructs a plane-wave-square matrix.
        oracle = .15 * np.vdot(x, (p @ d @ p.conj().T) @ x).real
        self.assertAlmostEqual(result["projected_ha"], oracle, places=14)
        self.assertLess(result["max_state_path_error_ha"], 1e-14)
        self.assertLess(result["max_state_spin_decomposition_error_ha"], 1e-14)
        self.assertGreater(abs(result["cross_ha"]), .001)
        wrong_blocked_x = np.array([c[0, 1], c[0, 0], c[1, 1], c[1, 0]])
        wrong_no_conjugate = p.T @ x
        self.assertGreater(abs(.15 * np.vdot(wrong_blocked_x, (p @ d @ p.conj().T) @ wrong_blocked_x).real - oracle), .001)
        self.assertGreater(abs(.15 * np.vdot(wrong_no_conjugate, d @ wrong_no_conjugate).real - oracle), .001)
        diagonal_only = .15 * np.vdot(p.conj().T @ x, np.diag(np.diag(d)) @ (p.conj().T @ x)).real
        self.assertGreater(abs(diagonal_only - oracle), .001)

    def test_miller_mismatch_duplicates_and_one_sided_reordering(self):
        state = synthetic_state()
        published = synthetic_operator()
        correct = independent.audit_nonlocal(state, published)["projected_ha"]
        incorrect = copy.deepcopy(published)
        incorrect["kpoints"][0]["P"] = incorrect["kpoints"][0]["P"][[2, 3, 0, 1]]
        self.assertGreater(abs(independent.audit_nonlocal(state, incorrect)["projected_ha"] - correct), .001)
        incorrect["kpoints"][0]["millers"][0] = [7, 0, 0]
        with self.assertRaisesRegex(ValueError, "strict bijection"):
            independent.audit_nonlocal(state, incorrect)
        incorrect["kpoints"][0]["millers"][0] = incorrect["kpoints"][0]["millers"][1]
        with self.assertRaisesRegex(ValueError, "duplicate Miller"):
            independent.audit_nonlocal(state, incorrect)

    def test_retained_complex_up_down_amplitudes_have_source_spin_phases(self):
        state, published = synthetic_state(), synthetic_operator()
        result = independent.audit_nonlocal(state, published, return_amplitudes=True)
        c = state["kpoints"][0]["coefficients"][:, :, 0]
        p = published["kpoints"][0]["P"]
        expected_up = p[0].conjugate() * c[0, 1] + p[2].conjugate() * c[0, 0]
        expected_down = p[1].conjugate() * c[1, 1] + p[3].conjugate() * c[1, 0]
        np.testing.assert_allclose(result["_amplitudes"][0]["up"][:, 0], expected_up, rtol=1e-14, atol=1e-14)
        np.testing.assert_allclose(result["_amplitudes"][0]["down"][:, 0], expected_down, rtol=1e-14, atol=1e-14)
        self.assertGreater(np.max(np.abs(expected_down.imag)), .1)
        self.assertNotIn("_amplitudes", independent.audit_nonlocal(state, published))

    def test_equal_occupation_subspace_rotation_preserves_projection_energy(self):
        random = np.random.default_rng(4711)
        up = random.normal(size=(2, 3)) + 1j * random.normal(size=(2, 3))
        down = random.normal(size=(2, 3)) + 1j * random.normal(size=(2, 3))
        d = synthetic_operator()["D"]
        kpoint = {"up": up, "down": down, "occupations": np.array([.7, .7, 0.]),
                  "weight": .4, "kinetic": np.array([1., 2., 30.]), "nonlocal": np.array([3., 4., 50.])}
        result = independent.audit_projected_endpoint([kpoint], d)
        rotation = np.array([[1, 1j, 0], [1j, 1, 0], [0, 0, np.sqrt(2)]]) / np.sqrt(2)
        rotated = dict(kpoint, up=up @ rotation, down=down @ rotation)
        changed = independent.audit_projected_endpoint([rotated], d)
        self.assertAlmostEqual(result["projected_ha"], changed["projected_ha"], places=13)
        self.assertAlmostEqual(result["cross_ha"], changed["cross_ha"], places=13)
        self.assertAlmostEqual(result["kinetic_scalar_ha"], .84, places=14)
        self.assertAlmostEqual(result["nonlocal_scalar_ha"], 1.96, places=14)
        self.assertEqual(result["scalar_states_checked"], {"kinetic": 3, "nonlocal": 3})
        self.assertEqual(result["scope"], "SCALAR_AND_PROJECTED_ONLY")

    def test_actual_product_support_and_fft_alias_rejection(self):
        g = np.array([[0, 0, 0], [2, 1, -1], [-1, 2, 1]], dtype=np.int64)
        result = independent.product_support([g])
        expected = {(0, 0, 0), (2, 1, -1), (-2, -1, 1), (-1, 2, 1),
                    (1, -2, -1), (3, -1, -2), (-3, 1, 2)}
        self.assertEqual(set(map(tuple, result)), expected)
        with self.assertRaisesRegex(ValueError, "aliases"):
            independent.density_from_series(np.array([[0, 0, 0], [4, 0, 0]]), np.ones(2), (4, 4, 4))

    def test_density_finite_series_preserves_significant_imaginary_part(self):
        rho = independent.density_from_series(np.array([[0, 0, 0], [1, 1, 0]]),
                                              np.array([1., 1j]), (5, 5, 5))
        self.assertGreater(np.max(np.abs(rho.imag)), .5)
        with self.assertRaisesRegex(ValueError, "finite"):
            independent.density_from_series(np.array([[0, 0, 0]]), np.array([np.nan]), (5, 5, 5))

    def test_shared_printed_potential_combines_coefficients_before_halfwidth(self):
        a = np.array([1., 2., 3.])
        b = np.array([1.1, 1.9, 3.])
        potential = np.array([2., -3., 5.])
        width = np.array([.01, .02, .01])
        canceled = independent.shared_potential_integral([a, a], [1, -1], potential, width, .5)
        self.assertEqual(canceled["value_ha"], 0.)
        self.assertEqual(canceled["halfwidth_ha"], 0.)
        delta = independent.shared_potential_integral([b, a], [1, -1], potential, width, .5)
        self.assertAlmostEqual(delta["value_ha"], .25, places=14)
        self.assertAlmostEqual(delta["halfwidth_ha"], .0015, places=14)
        separate = independent.shared_potential_integral([a], [1], potential, width, .5)["halfwidth_ha"]
        separate += independent.shared_potential_integral([b], [1], potential, width, .5)["halfwidth_ha"]
        self.assertLess(delta["halfwidth_ha"], separate / 10)

    def test_ledger_complements_signed_leaves_and_no_parent_double_count(self):
        rho = np.array([1., 2., 3.])
        saved = np.array([1.1, 1.9, 3.])
        history = {"O_Q": 2., "O_Q_halfwidth": .03, "S_response": .2,
                   "drift_S": .1, "historical_O_grouping_drift": .04,
                   "saved_local_replay_drift": .02}
        result = independent.local_ledger(rho, saved, np.array([2., -3., 5.]),
                                          np.array([.01, .02, .01]), 1.5, 3., .4, history)
        self.assertAlmostEqual(result["L_wfc"]["value_ha"], 5.5, places=14)
        self.assertAlmostEqual(result["J_Q_ha"], 6.9, places=14)
        self.assertAlmostEqual(result["J_Q_halfwidth_ha"], .07, places=14)
        self.assertAlmostEqual(result["NL_shaped_remainder_ha"], -6.5, places=14)
        self.assertAlmostEqual(result["J_plus_NL_shaped_minus_NL_ha"], 0., places=14)
        self.assertAlmostEqual(result["R_old_reconstructed_ha"], 7.27, places=14)
        self.assertEqual(len(result["signed_leaves_ha"]), 6)

    def test_derived_last_bit_changes_receipt_without_input_identity_claim(self):
        original = np.array([1., 2., 3.])
        perturbed = original.copy()
        perturbed[0] = np.nextafter(perturbed[0], np.inf)
        self.assertNotEqual(independent.derived_array_hash(original), independent.derived_array_hash(perturbed))
        a = independent.shared_potential_integral([original], [1], np.ones(3), np.zeros(3), 1.)
        b = independent.shared_potential_integral([perturbed], [1], np.ones(3), np.zeros(3), 1.)
        self.assertLessEqual(abs(a["value_ha"] - b["value_ha"]), 1e-14)
        np.testing.assert_array_equal(original, [1., 2., 3.])

    def test_read_only_synthetic_inputs_work_without_mutation(self):
        state = synthetic_state()
        published = synthetic_operator()
        modes, coefficients = synthetic_density(state)
        arrays = [state["lattice_columns"], state["reciprocal_columns"], published["D"],
                  published["kpoints"][0]["millers"], published["kpoints"][0]["P"], modes, coefficients]
        arrays += [value for value in state["kpoints"][0].values() if isinstance(value, np.ndarray)]
        fingerprints = [independent.derived_array_hash(value) for value in arrays]
        for value in arrays:
            value.flags.writeable = False
        independent.audit_q_state(state, (9, 9, 9), modes, coefficients, modes, 20., .15)
        independent.audit_nonlocal(state, published)
        self.assertEqual(fingerprints, [independent.derived_array_hash(value) for value in arrays])


if __name__ == "__main__":
    unittest.main()
