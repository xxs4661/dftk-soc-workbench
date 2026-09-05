"""Synthetic parser fixtures only: these are not QE/DFTK calculation evidence."""
import itertools
import copy
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from parse_qe_baseline import parse_qe


def synthetic_xml():
    """Minimal invented format records with no physical pseudopotential data."""
    root = ET.Element("qes:espresso", {
        "xmlns:qes": "http://www.quantum-espresso.org/ns/qes/qes-1.0",
        "Units": "Hartree atomic units",
    })

    def put(parent, tag, value=None, **attributes):
        element = ET.SubElement(parent, tag, attributes)
        element.text = None if value is None else str(value)
        return element

    info = put(root, "general_info")
    put(info, "xml_format", NAME="QEXSD", VERSION="25.05.21")
    put(info, "creator", NAME="PWSCF", VERSION="7.5")
    inputs = put(root, "input")
    put(put(inputs, "control_variables"), "calculation", "scf")
    spin = put(inputs, "spin")
    for flag in ("lsda", "noncolin", "spinorbit"):
        put(spin, flag, "false")
    put(put(inputs, "bands"), "occupations", "fixed")
    symmetry = put(inputs, "symmetry_flags")
    put(symmetry, "nosym", "true")
    put(symmetry, "noinv", "true")
    put(put(inputs, "electron_control"), "diago_full_acc", "true")
    # An intermediate converged result must not override the final output.
    step = put(root, "step")
    put(put(step, "total_energy"), "etot", -99)
    output = put(root, "output")
    convergence = put(put(output, "convergence_info"), "scf_conv")
    put(convergence, "convergence_achieved", "true")
    put(convergence, "n_scf_steps", 4)
    put(convergence, "scf_error", "1e-12")
    structure = put(output, "atomic_structure", nat="2", alat="1")
    cell = put(structure, "cell")
    reciprocal = put(put(output, "basis_set"), "reciprocal_lattice")
    # Nonsymmetric direct-lattice rows and their reciprocal duals expose errors
    # hidden by the actual Si primitive cell's symmetric matrix.
    for index, (a, b) in enumerate(zip(
        ("2 1 0", "0 3 1", "0 0 4"),
        ("0.5 0 0", "-0.1666666666666667 0.3333333333333333 0",
         "0.04166666666666667 -0.08333333333333333 0.25")), 1):
        put(cell, "a" + str(index), a)
        put(reciprocal, "b" + str(index), b)
    atoms = put(structure, "atomic_positions")
    put(atoms, "atom", "0 0 0", name="Si")
    put(atoms, "atom", "0.5 1 1.25", name="Si")
    basis = output.find("basis_set")
    put(basis, "fft_grid", nr1="10", nr2="12", nr3="14")
    put(basis, "ecutwfc", 30)
    put(basis, "ecutrho", 120)
    put(put(put(output, "atomic_species"), "species", name="Si"), "pseudo_file", "Si.upf")
    put(put(output, "dft"), "functional", "SLA PW NOGX NOGC")
    put(put(output, "total_energy"), "etot", -10)
    bands = put(output, "band_structure")
    for flag in ("lsda", "noncolin", "spinorbit"):
        put(bands, flag, "false")
    put(bands, "occupations_kind", "fixed")
    put(bands, "nelec", 8)
    put(bands, "nbnd", 8)
    put(bands, "nks", 8)
    for x, y, z in itertools.product((0, -0.5), repeat=3):
        block = put(bands, "ks_energies")
        cartesian = (x / 2 - y / 6 + z / 24, y / 3 - z / 12, z / 4)
        put(block, "k_point", " ".join(map(str, cartesian)), weight="0.25")
        put(block, "eigenvalues", "-1 -0.5 -0.3 -0.2 0.1 0.2 0.3 0.4", size="8")
        put(block, "occupations", "1 1 1 1 0 0 0 0", size="8")
        put(block, "npw", 99)
    put(root, "exit_status", 0)
    put(root, "closed")
    return root


SYNTHETIC_STDOUT = """Synthetic parser fixture, not a real calculation.
Program PWSCF v.7.5
Exchange-correlation= SLA PW NOGX NOGC ( 1 4 0 0 0 0 0 )
PseudoPot. # 1 for Si read from file:
Si.upf
Pseudo is Norm-conserving + core correction, Zval = 4.0
ethr = 1.00E-12
! total energy = -198.00000000 Ry
convergence has been achieved
! total energy = -20.00000000 Ry
convergence has been achieved
JOB DONE.
"""


class QeBaselineParserTests(unittest.TestCase):
    def parse(self, root=None, stdout=SYNTHETIC_STDOUT, code=0):
        root = synthetic_xml() if root is None else root
        xml = ET.tostring(root, encoding="unicode") if not isinstance(root, str) else root
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.xml"
            path.write_text(xml)
            return parse_qe(path, stdout, code)

    def test_final_output_and_last_text_energy_exclude_intermediate_values(self):
        result = self.parse()
        self.assertEqual(result["energy_ha"], -10)
        self.assertEqual(result["energy_ry_stdout"], -20)
        self.assertEqual(result["execution_status"], "PASS")
        self.assertAlmostEqual(result["stdout_energy_half_digit_ry"], 5e-9)

    def test_last_output_record_is_selected_without_searching_for_success(self):
        root = synthetic_xml()
        final = copy.deepcopy(root.find("output"))
        final.find("convergence_info/scf_conv/convergence_achieved").text = "false"
        root.insert(list(root).index(root.find("exit_status")), final)
        with self.assertRaisesRegex(ValueError, "not converged"):
            self.parse(root)

    def test_cartesian_output_conversion_uses_actual_nonsymmetric_cell(self):
        result = self.parse()
        for actual, expected in zip(result["kpoints"], itertools.product((0, -0.5), repeat=3)):
            for value, target in zip(actual["coordinate_fractional"], expected):
                self.assertAlmostEqual(value, target)
        for value in result["positions_fractional"][1]:
            self.assertAlmostEqual(value, 0.25)

    def test_raw_and_normalized_electrons_both_eight(self):
        result = self.parse()
        self.assertEqual(sum(k["weight_raw"] for k in result["kpoints"]), 2)
        self.assertEqual(sum(k["weight_spatial"] for k in result["kpoints"]), 1)
        self.assertEqual(result["kpoints"][0]["occupations_raw"], [1] * 4 + [0] * 4)
        self.assertEqual(result["kpoints"][0]["occupations"], [2] * 4 + [0] * 4)
        self.assertEqual(result["electron_sum_raw"], 8)
        self.assertEqual(result["electron_sum_normalized"], 8)

    def test_spin_degeneracy_not_inferred_from_renormalization(self):
        root = synthetic_xml()
        for element in root.findall("output/band_structure/ks_energies/k_point"):
            element.set("weight", "0.125")
        with self.assertRaisesRegex(ValueError, "weights must sum to 2"):
            self.parse(root)

    def test_illegal_fixed_occupations_rejected(self):
        root = synthetic_xml()
        root.find("output/band_structure/ks_energies/occupations").text = "2 2 2 2 0 0 0 0"
        with self.assertRaisesRegex(ValueError, "weights/occupations"):
            self.parse(root)

    def test_exit_zero_and_job_done_do_not_prove_scf_convergence(self):
        root = synthetic_xml()
        root.find("output/convergence_info/scf_conv/convergence_achieved").text = "false"
        with self.assertRaisesRegex(ValueError, "not converged"):
            self.parse(root)

    def test_internal_parameter_name_is_not_an_xml_convergence_field(self):
        root = synthetic_xml()
        root.find("output/convergence_info/scf_conv/convergence_achieved").tag = "scf_has_converged"
        with self.assertRaisesRegex(ValueError, "missing convergence_achieved"):
            self.parse(root)

    def test_final_unconverged_text_cannot_reuse_prior_convergence(self):
        with self.assertRaisesRegex(ValueError, "final SCF convergence"):
            self.parse(stdout=SYNTHETIC_STDOUT.replace("JOB DONE.", "convergence NOT achieved\nJOB DONE."))

    def test_nonzero_process_rejected_even_with_converged_data(self):
        with self.assertRaisesRegex(ValueError, "process did not exit"):
            self.parse(code=1)

    def test_missing_xml_and_truncated_xml_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "missing or truncated"):
                parse_qe(Path(directory) / "absent.xml", SYNTHETIC_STDOUT, 0)
        xml = ET.tostring(synthetic_xml(), encoding="unicode")
        with self.assertRaisesRegex(ValueError, "missing or truncated"):
            self.parse(root=xml[:-20])

    def test_truncated_stdout_rejected(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.parse(stdout=SYNTHETIC_STDOUT.replace("JOB DONE.", ""))

    def test_missing_eigenvalues_rejected(self):
        root = synthetic_xml()
        block = root.find("output/band_structure/ks_energies")
        block.remove(block.find("eigenvalues"))
        with self.assertRaisesRegex(ValueError, "missing eigenvalues"):
            self.parse(root)

    def test_nonfinite_eigenvalues_rejected(self):
        root = synthetic_xml()
        root.find("output/band_structure/ks_energies/eigenvalues").text = "NaN -0.5 -0.3 -0.2 0.1 0.2 0.3 0.4"
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            self.parse(root)

    def test_final_nan_text_energy_does_not_reuse_prior_value(self):
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            self.parse(stdout=SYNTHETIC_STDOUT.replace("JOB DONE.", "! total energy = NaN Ry\nJOB DONE."))

    def test_final_nan_diagonalization_does_not_reuse_prior_value(self):
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            self.parse(stdout=SYNTHETIC_STDOUT.replace("JOB DONE.", "ethr = NaN\nJOB DONE."))

    def test_wrong_xml_units_rejected(self):
        root = synthetic_xml()
        root.set("Units", "Rydberg")
        with self.assertRaisesRegex(ValueError, "Hartree units"):
            self.parse(root)

    def test_unknown_xml_format_rejected(self):
        root = synthetic_xml()
        root.find("general_info/xml_format").set("VERSION", "999")
        with self.assertRaisesRegex(ValueError, "format/version"):
            self.parse(root)

    def test_incomplete_band_count_rejected(self):
        root = synthetic_xml()
        root.find("output/band_structure/ks_energies/eigenvalues").text = "-1 -0.5 -0.3"
        with self.assertRaisesRegex(ValueError, "vector size"):
            self.parse(root)

    def test_empty_state_accuracy_evidence_required(self):
        root = synthetic_xml()
        root.find("input/electron_control/diago_full_acc").text = "false"
        with self.assertRaisesRegex(ValueError, "full diagonalization accuracy"):
            self.parse(root)

    def test_nlcc_and_species_are_reported_from_actual_worker_fields(self):
        result = self.parse()
        self.assertTrue(result["nlcc"])
        self.assertEqual(result["z_valence"], 4)
        self.assertEqual(result["pseudo_type"], "NC")
        self.assertEqual(result["pseudo_files"], ["Si.upf"])

    def test_missing_core_correction_not_filled_from_case_defaults(self):
        with self.assertRaisesRegex(ValueError, "core correction"):
            self.parse(stdout=SYNTHETIC_STDOUT.replace(" + core correction", ""))

    def test_unrelated_pseudopotential_not_accepted_by_filename_guess(self):
        with self.assertRaisesRegex(ValueError, "selected Si.upf read"):
            self.parse(stdout=SYNTHETIC_STDOUT.replace("Si.upf", "Other.upf"))


if __name__ == "__main__":
    unittest.main()
