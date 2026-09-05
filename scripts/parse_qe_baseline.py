#!/usr/bin/env python3
"""Read the final QEXSD result for this nonmagnetic, fixed-occupation Si case.

This is an output-format adapter, not a translation of QE algorithms. Units and
weight conventions are documented in the tagged QE format writers cited below.
Unsupported formats and incomplete calculations raise ValueError; callers must
record the failure and must not substitute a previous calculation's XML.
"""
import argparse
from decimal import Decimal
import json
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


FORMAT_SOURCES = {
    "xml_units_and_version": "https://github.com/QEF/q-e/blob/qe-7.5/Modules/qexsd.f90#L53-L55",
    "xml_units_declaration": "https://github.com/QEF/q-e/blob/qe-7.5/Modules/qexsd.f90#L128-L136",
    "energy_structure_convergence": "https://github.com/QEF/q-e/blob/qe-7.5/PW/src/pw_restart_new.f90",
    "convergence_xml_field": "https://github.com/QEF/q-e/blob/qe-7.5/Modules/qes_write_module.f90#L2779-L2800",
    "eigenvalues_occupations_kpoints": "https://github.com/QEF/q-e/blob/qe-7.5/Modules/qexsd_init.f90#L1159-L1274",
    "nonmagnetic_weight_degeneracy": "https://github.com/QEF/q-e/blob/qe-7.5/PW/src/setup.f90#L647-L675",
}
def require(parent, path):
    element = parent.find(path)
    if element is None:
        raise ValueError("QE XML missing " + path)
    return element


def text(parent, path):
    value = require(parent, path).text
    if value is None or not value.strip():
        raise ValueError("QE XML empty " + path)
    return value.strip()


def finite(value):
    number = float(value.replace("D", "E").replace("d", "e"))
    if not math.isfinite(number):
        raise ValueError("QE output contains a nonfinite number")
    return number


def vector(element, size=None):
    values = [finite(value) for value in (element.text or "").split()]
    if not values or (size is not None and len(values) != size):
        raise ValueError("QE XML vector size mismatch: " + element.tag)
    if "size" in element.attrib and int(element.attrib["size"]) != len(values):
        raise ValueError("QE XML declared vector size disagrees with data")
    return values


def boolean(parent, path):
    value = text(parent, path).lower()
    if value not in ("true", "false", "1", "0"):
        raise ValueError("QE XML invalid boolean: " + path)
    return value in ("true", "1")


def positive_int(value):
    number = int(value)
    if number < 1:
        raise ValueError("QE XML requires a positive integer")
    return number


def dot(left, right):
    return sum(a * b for a, b in zip(left, right))


def parse_qe(xml_path, stdout_text, exit_code):
    """Return finite, normalized final SCF data; reject missing/failed evidence."""
    try:
        return _parse_qe(xml_path, stdout_text, exit_code)
    except (KeyError, TypeError, ArithmeticError) as error:
        raise ValueError("QE result has malformed required fields") from error


def _parse_qe(xml_path, stdout_text, exit_code):
    if type(exit_code) is not int or exit_code != 0:
        raise ValueError("QE process did not exit normally with code 0")
    if "JOB DONE." not in stdout_text:
        raise ValueError("QE stdout is incomplete: missing JOB DONE")
    convergence_messages = re.findall(
        r"convergence\s+(has been achieved|NOT achieved)", stdout_text,
        flags=re.IGNORECASE,
    )
    if not convergence_messages or convergence_messages[-1].lower() != "has been achieved":
        raise ValueError("QE stdout does not report final SCF convergence")
    try:
        root = ET.parse(xml_path).getroot()
    except (ET.ParseError, OSError) as error:
        raise ValueError("QE final XML is missing or truncated") from error
    if root.tag != "{http://www.quantum-espresso.org/ns/qes/qes-1.0}espresso":
        raise ValueError("Unsupported QE XML namespace/root")
    if root.attrib.get("Units") != "Hartree atomic units":
        raise ValueError("QE XML does not declare the supported Hartree units")
    # Namespace removal is local to this parsed tree; queries stay explicit and
    # never search intermediate <step> records for a convenient converged value.
    for element in root.iter():
        element.tag = element.tag.split("}")[-1]
    xml_format = require(root, "general_info/xml_format")
    if (xml_format.get("NAME"), xml_format.get("VERSION")) != ("QEXSD", "25.05.21"):
        raise ValueError("Unsupported QE XML format/version")
    if int(text(root, "exit_status")) != 0:
        raise ValueError("QE XML reports a nonzero exit_status")
    require(root, "closed")
    creator = require(root, "general_info/creator")
    version = creator.get("VERSION")
    versions = re.findall(r"Program\s+PWSCF\s+v\.([^\s]+)", stdout_text)
    if not versions or version != versions[-1] or creator.get("NAME") != "PWSCF":
        raise ValueError("QE XML creator and actual stdout version disagree")
    outputs = root.findall("output")
    if not outputs:
        raise ValueError("QE XML missing final output")
    output = outputs[-1]
    scf = require(output, "convergence_info/scf_conv")
    if not boolean(scf, "convergence_achieved"):
        raise ValueError("QE final XML reports SCF not converged")
    scf_steps = positive_int(text(scf, "n_scf_steps"))
    scf_error = finite(text(scf, "scf_error"))
    if scf_error < 0:
        raise ValueError("QE SCF error must be nonnegative")

    input_xml = require(root, "input")
    if text(input_xml, "control_variables/calculation") != "scf":
        raise ValueError("QE total energy must come from the SCF calculation")
    bands = require(output, "band_structure")
    spin_flags = {name: boolean(bands, name) for name in ("lsda", "noncolin", "spinorbit")}
    if any(spin_flags.values()):
        raise ValueError("QE result is outside the nonmagnetic scalar case")
    if any(boolean(input_xml, "spin/" + name) for name in spin_flags):
        raise ValueError("QE input spin settings disagree with the scalar case")
    occupations_kind = text(bands, "occupations_kind")
    if occupations_kind != "fixed" or text(input_xml, "bands/occupations") != "fixed":
        raise ValueError("QE occupations must be fixed")
    nosym = boolean(input_xml, "symmetry_flags/nosym")
    noinv = boolean(input_xml, "symmetry_flags/noinv")
    if not nosym or not noinv:
        raise ValueError("QE must disable spatial and inversion k-point reduction")
    if not boolean(input_xml, "electron_control/diago_full_acc"):
        raise ValueError("QE empty states lack requested full diagonalization accuracy")
    n_electrons = finite(text(bands, "nelec"))
    n_bands = positive_int(text(bands, "nbnd"))
    n_kpoints = positive_int(text(bands, "nks"))
    if n_bands != 8 or n_kpoints != 8 or abs(n_electrons - 8) > 1e-8:
        raise ValueError("QE must report 8 electrons, 8 scalar bands and 8 k points")

    structure = require(output, "atomic_structure")
    n_atoms = positive_int(structure.attrib["nat"])
    alat = finite(structure.attrib["alat"])
    if alat <= 0:
        raise ValueError("QE alat must be positive")
    lattice = [vector(require(structure, "cell/a" + str(i)), 3) for i in (1, 2, 3)]
    reciprocal = [vector(require(output, "basis_set/reciprocal_lattice/b" + str(i)), 3)
                  for i in (1, 2, 3)]
    # The XML's b_i and k points use 2π/alat, unlike its bohr cell vectors.
    # Verify their duality before converting either atoms or reciprocal points.
    for i, a in enumerate(lattice):
        for j, b in enumerate(reciprocal):
            if abs(dot(a, b) / alat - (i == j)) > 1e-9:
                raise ValueError("QE actual direct/reciprocal lattices are inconsistent")
    atoms = require(structure, "atomic_positions").findall("atom")
    if len(atoms) != n_atoms:
        raise ValueError("QE atom count does not match actual positions")
    positions_cartesian = [vector(atom, 3) for atom in atoms]
    positions = [[dot(position, b) / alat for b in reciprocal]
                 for position in positions_cartesian]
    eigenblocks = bands.findall("ks_energies")
    if len(eigenblocks) != n_kpoints:
        raise ValueError("QE missing k-point eigenvalue blocks")
    kpoints = []
    for block in eigenblocks:
        k_element = require(block, "k_point")
        k_cartesian = vector(k_element, 3)
        weight = finite(k_element.attrib["weight"])
        values = vector(require(block, "eigenvalues"), n_bands)
        occupations = vector(require(block, "occupations"), n_bands)
        if weight <= 0 or any(abs(value - (index < 4)) > 1e-8
                              for index, value in enumerate(occupations)):
            raise ValueError("QE raw weights/occupations violate the fixed scalar model")
        kpoints.append({
            "coordinate_fractional": [dot(a, k_cartesian) / alat for a in lattice],
            "coordinate_raw": k_cartesian, "weight_raw": weight,
            "weight_spatial": weight / 2, "occupations_raw": occupations,
            "occupations": [2 * value for value in occupations],
            "eigenvalues_ha": values, "npw": positive_int(text(block, "npw")),
        })
    if abs(sum(k["weight_raw"] for k in kpoints) - 2) > 1e-8:
        raise ValueError("QE nonmagnetic raw k-point weights must sum to 2")
    electron_sum_raw = sum(k["weight_raw"] * sum(k["occupations_raw"]) for k in kpoints)
    electron_sum = sum(k["weight_spatial"] * sum(k["occupations"]) for k in kpoints)
    if any(abs(value - n_electrons) > 1e-8 for value in (electron_sum_raw, electron_sum)):
        raise ValueError("QE raw or normalized weights/occupations miscount electrons")

    energy = finite(text(output, "total_energy/etot"))
    energy_tokens = re.findall(r"!\s+total energy\s*=\s*(\S+)\s+Ry", stdout_text)
    if not energy_tokens:
        raise ValueError("QE stdout missing the final total energy in Ry")
    last_token = energy_tokens[-1].replace("D", "E").replace("d", "e")
    energy_ry = finite(last_token)
    # Half a last printed digit is the text rounding limit, not an agreement
    # tolerance between the two DFT codes. The XML retains more precision.
    text_half_digit_ry = float(Decimal(10) ** Decimal(last_token).as_tuple().exponent) / 2
    if abs(energy - energy_ry / 2) > text_half_digit_ry / 2 + 1e-12:
        raise ValueError("QE final XML and stdout total energies disagree beyond text precision")
    grid = require(output, "basis_set/fft_grid")
    fft_grid = [positive_int(grid.attrib["nr" + str(i)]) for i in (1, 2, 3)]
    smooth_grid = output.find("basis_set/fft_smooth")
    fft_smooth = None if smooth_grid is None else [
        positive_int(smooth_grid.attrib["nr" + str(i)]) for i in (1, 2, 3)]
    species = require(output, "atomic_species").findall("species")
    if len(species) != 1 or species[0].get("name") != "Si" or text(species[0], "pseudo_file") != "Si.upf":
        raise ValueError("QE XML must identify the selected Si.upf species")
    pseudo_reads = re.findall(r"PseudoPot\.\s*#\s*\d+\s+for\s+Si\s+read from file:\s*(\S+)", stdout_text)
    if len(pseudo_reads) != 1 or Path(pseudo_reads[0]).name != "Si.upf":
        raise ValueError("QE stdout does not identify the selected Si.upf read")
    pseudo_summaries = re.findall(r"Pseudo is\s+([^\n,]+),\s*Zval\s*=\s*(\S+)", stdout_text)
    if len(pseudo_summaries) != 1:
        raise ValueError("QE stdout lacks an unambiguous pseudopotential summary")
    pseudo_description, zvalence = pseudo_summaries[0]
    pseudo_description = " ".join(pseudo_description.split())
    zvalence = finite(zvalence)
    if pseudo_description != "Norm-conserving + core correction" or abs(zvalence - 4) > 1e-8:
        raise ValueError("QE must report NC, core correction and valence 4 for this Si input")
    fermi = bands.find("fermi_energy")
    diagonalization = re.findall(r"ethr\s*=\s*([^\s,]+)", stdout_text)
    if not diagonalization:
        raise ValueError("QE stdout lacks diagonalization threshold evidence")
    diagonalization_threshold = finite(diagonalization[-1])
    if diagonalization_threshold <= 0:
        raise ValueError("QE final diagonalization threshold must be positive")
    xc_declarations = re.findall(
        r"Exchange-correlation\s*=\s*([^\n]+)\s*\(([\d\s]+)\)", stdout_text
    )
    if not xc_declarations:
        raise ValueError("QE stdout missing actual exchange/correlation indices")
    xc_name, xc_numbers = xc_declarations[-1]
    xc_indices = [int(value) for value in xc_numbers.split()]
    if len(xc_indices) < 4:
        raise ValueError("QE exchange/correlation index declaration is incomplete")
    return {
        "schema_version": 1, "code": "QE", "execution_status": "PASS",
        "converged": True, "exit_code": exit_code, "version": version,
        "energy_ha": energy, "energy_raw": {"value": energy, "unit": "Ha", "field": "output/total_energy/etot"},
        "energy_ry_stdout": energy_ry, "stdout_energy_half_digit_ry": text_half_digit_ry,
        "lattice_vectors_bohr": lattice, "alat_bohr": alat,
        "positions_fractional": positions, "positions_cartesian_bohr": positions_cartesian,
        "atom_symbols": [atom.attrib["name"] for atom in atoms], "n_atoms": n_atoms,
        "kpoints": kpoints, "n_electrons": n_electrons, "n_bands": n_bands,
        "electron_sum_raw": electron_sum_raw, "electron_sum_normalized": electron_sum,
        "fft_grid": fft_grid, "fft_smooth_grid": fft_smooth,
        "ecut_ha": finite(text(output, "basis_set/ecutwfc")),
        "ecutrho_ha": finite(text(output, "basis_set/ecutrho")),
        "xc_raw": text(output, "dft/functional"),
        "xc_stdout": xc_name.strip(), "xc_indices": xc_indices,
        "pseudo_files": [text(species_entry, "pseudo_file") for species_entry in species],
        "pseudo_type": "NC", "nlcc": True, "z_valence": zvalence,
        "pseudo_stdout_description": pseudo_description,
        "pseudo_evidence": "QE stdout PseudoPot file read and Pseudo is summary; matched XML atomic_species",
        "input_model": {"nspin": 1, **spin_flags, "occupations": occupations_kind,
                        "nosym": nosym, "noinv": noinv, "diago_full_acc": True},
        "scf": {"iterations": scf_steps, "error_ha": scf_error,
                "convergence_evidence": "Final output/convergence_info/scf_conv/convergence_achieved plus final stdout convergence report",
                "diagonalization_threshold_last_ry": diagonalization_threshold,
                "diagonalization_residuals": None,
                "residual_note": "QE XML/stdout do not report individual eigenvector residual norms"},
        "fermi_energy_ha": None if fermi is None else finite(fermi.text or ""),
        "fermi_energy_definition": "QE fixed-occupation XML: highest occupied level (HOMO/VBMax), when present",
        "metadata_units": {"xml_format": dict(xml_format.attrib), "xml_energy": "Ha",
                           "xml_positions": "bohr", "xml_cell": "bohr",
                           "xml_kpoint_and_reciprocal_vectors": "Cartesian, 2*pi/alat",
                           "raw_weights": "include identical-spin degeneracy 2; sum 2",
                           "raw_occupations": "per spin, 0 or 1; XML wg/wk",
                           "normalization": "spatial_weight=raw_weight/2; occupation=2*raw_occupation"},
        "format_sources": FORMAT_SOURCES,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xml", type=Path)
    parser.add_argument("stdout", type=Path)
    parser.add_argument("--exit-code", type=int, required=True)
    args = parser.parse_args()
    try:
        result = parse_qe(args.xml, args.stdout.read_text(), args.exit_code)
        print(json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, KeyError, OSError) as error:
        print("QE parse failed: " + str(error), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
