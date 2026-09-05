#!/usr/bin/env python3
"""Independently integrate the finite local-potential reference from raw UPF arrays.

This is not an SCF or a total-energy correction. No DFTK/PseudoPotentialIO
routine or spectral data is used. UPF 2.0.1 PP_R is in bohr and PP_LOCAL in Ry:
https://pseudopotentials.quantum-espresso.org/home/unified-pseudopotential-format
See 'Field specifications', PP_MESH and PP_LOCAL. We convert V_Ry / 2 to Ha.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
UPF_UNITS_SOURCE = 'https://pseudopotentials.quantum-espresso.org/home/unified-pseudopotential-format'


def finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Expected a finite real number')
    return float(value)


def checked_samples(coordinates, values):
    if len(coordinates) != len(values) or len(coordinates) < 2:
        raise ValueError('Integration needs at least two paired samples')
    x = [finite_number(value) for value in coordinates]
    y = [finite_number(value) for value in values]
    if any(b <= a for a, b in zip(x, x[1:])):
        raise ValueError('Radial coordinates must increase strictly')
    return x, y


def trapezoid(coordinates, values):
    x, y = checked_samples(coordinates, values)
    return math.fsum((b-a)*(ya+yb)/2 for a, b, ya, yb in zip(x, x[1:], y, y[1:]))


def quadratic_integral(coordinates, values):
    """Integrate local quadratic interpolants on the actual (possibly uneven) grid.

    Consecutive three-point panels cover two intervals each. If one interval
    remains, integrate the quadratic through the final three points on that
    interval alone. A two-point input uses the trapezoid. The coefficients are
    divided differences in the local coordinate t = r-r0, not equal-step
    Simpson weights. Thus every quadratic is integrated exactly on either
    even or odd numbers of intervals, up to floating-point arithmetic.
    """
    x, y = checked_samples(coordinates, values)
    if len(x) == 2:
        return trapezoid(x, y)

    def panel(index, lower=0.0):
        h0, h1 = x[index+1]-x[index], x[index+2]-x[index+1]
        upper = h0+h1
        slope = (y[index+1]-y[index])/h0
        quadratic = ((y[index+2]-y[index+1])/h1-slope)/upper
        linear = slope-quadratic*h0
        return (y[index]*(upper-lower) + linear*(upper**2-lower**2)/2
                + quadratic*(upper**3-lower**3)/3)

    parts = [panel(i) for i in range(0, len(x)-2, 2)]
    if len(x) % 2 == 0:
        parts.append(panel(len(x)-3, x[-2]-x[-3]))
    return math.fsum(parts)


def reference_from_arrays(radii_bohr, local_potential_ry, z_valence, n_atoms, volume_bohr3):
    """Return alpha and C from raw radial data, with integration diagnostics only."""
    radii, potential_ry = checked_samples(radii_bohr, local_potential_ry)
    z = finite_number(z_valence)
    volume = finite_number(volume_bohr3)
    if radii[0] != 0:
        raise ValueError('Supported grid must start at r=0; the missing inner interval is not guessed')
    if z <= 0 or volume <= 0 or isinstance(n_atoms, bool) or not isinstance(n_atoms, int) or n_atoms <= 0:
        raise ValueError('Positive valence, integer atom count and cell volume are required')
    # Cancel the Coulomb part pointwise before integration, including the origin.
    # Never integrate r^2 Vloc and Zr separately over an infinite interval.
    integrand = [r*r*(v/2)+z*r for r, v in zip(radii, potential_ry)]
    integral = quadratic_integral(radii, integrand)
    alpha = 4*math.pi*integral
    c = n_atoms*alpha/volume
    trap_alpha = 4*math.pi*trapezoid(radii, integrand)
    coarsened = []
    for stride in (2, 3, 4):
        indices = list(range(0, len(radii), stride))
        if indices[-1] != len(radii)-1:
            indices.append(len(radii)-1)
        trial = 4*math.pi*quadratic_integral(
            [radii[i] for i in indices], [integrand[i] for i in indices])
        coarsened.append({'stride': stride, 'points': len(indices), 'alpha_ha_bohr3': trial,
                          'C_ha': n_atoms*trial/volume, 'delta_C_from_full_ha': n_atoms*(trial-alpha)/volume})
    tail_start = max(0, len(radii)-100)
    tail_alpha = 4*math.pi*quadratic_integral(radii[tail_start:], integrand[tail_start:])
    steps = [b-a for a, b in zip(radii, radii[1:])]
    return {
        'alpha_ha_bohr3': alpha, 'C_ha': c,
        'formula': 'alpha = 4*pi*integral_0^R [r^2*(Vloc_Ry/2)+Z*r] dr; C = n_atoms*alpha/volume',
        'n_atoms': n_atoms, 'z_valence': z, 'volume_bohr3': volume,
        'units': {'r': 'bohr', 'Vloc_input': 'Ry', 'Vloc_integrated': 'Ha',
                  'integrand': 'Ha*bohr^2', 'alpha': 'Ha*bohr^3', 'C': 'Ha'},
        'grid': {'points': len(radii), 'r_min_bohr': radii[0], 'r_max_bohr': radii[-1],
                 'step_min_bohr': min(steps), 'step_max_bohr': max(steps),
                 'requested_radial_truncation': None, 'integration_limit': 'last actual PP_R value'},
        'quadrature': {
            'primary': 'Piecewise quadratic interpolation on actual coordinates; final single interval uses final three-point quadratic',
            'secondary': 'Composite trapezoid on the same full grid',
            'trapezoid_alpha_ha_bohr3': trap_alpha, 'trapezoid_C_ha': n_atoms*trap_alpha/volume,
            'quadratic_minus_trapezoid_C_ha': n_atoms*(alpha-trap_alpha)/volume,
            'coarsening_checks': coarsened,
            'interpretation': 'Method/coarsening sensitivity diagnostics, not strict error bounds'},
        'tail': {
            'start_bohr': radii[tail_start], 'end_bohr': radii[-1], 'points': len(radii)-tail_start,
            'signed_alpha_ha_bohr3': tail_alpha, 'signed_C_ha': n_atoms*tail_alpha/volume,
            'integrand_final_ha_bohr2': integrand[-1],
            'integrand_max_abs_ha_bohr2': max(abs(value) for value in integrand[tail_start:]),
            'max_abs_rV_plus_Z': max(abs(r*v/2+z) for r, v in zip(radii[tail_start:], potential_ry[tail_start:])),
            'beyond_grid': 'Not integrated or fitted; the finite-grid tail is reported without assuming it is exactly zero'},
        'spectral_data_used': False, 'dftk_correction_called': False,
        'scf_total_energy_modified': False,
    }


def cell_volume(vectors):
    if len(vectors) != 3 or any(len(row) != 3 for row in vectors):
        raise ValueError('Cell must contain three vectors with three components')
    a, b, c = [[finite_number(x) for x in row] for row in vectors]
    return abs(a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0]))


def inspect_file(upf_path, case_path):
    case_bytes = case_path.read_bytes()
    case = json.loads(case_bytes)
    payload = upf_path.read_bytes()
    checksum = hashlib.sha256(payload).hexdigest()
    if checksum != case['pseudo']['sha256']:
        raise ValueError('UPF SHA-256 differs from the prescribed Si case')
    tree = ET.fromstring(payload)
    if tree.tag != 'UPF' or tree.attrib.get('version') != '2.0.1':
        raise ValueError('Only the selected UPF 2.0.1 format is supported')
    header = tree.find('PP_HEADER')
    if header is None:
        raise ValueError('Missing PP_HEADER')
    h = header.attrib
    if (h.get('element') != 'Si' or h.get('pseudo_type') != 'NC' or h.get('relativistic') != 'scalar'
            or h.get('has_so', '').lower() not in ('f', 'false')):
        raise ValueError('This reference inspection requires the scalar Si NC input')

    def array(tag):
        nodes = tree.findall(tag)
        if len(nodes) != 1 or nodes[0].text is None:
            raise ValueError('Missing or ambiguous radial array: '+tag)
        values = [float(token.replace('D', 'E').replace('d', 'e')) for token in nodes[0].text.split()]
        if len(values) != int(nodes[0].attrib['size']) or len(values) != int(h['mesh_size']):
            raise ValueError('Radial array size differs from its declaration')
        return values

    radii, potential_ry = array('PP_MESH/PP_R'), array('PP_LOCAL')
    species = case['geometry']['species']
    z = float(h['z_valence'])
    if species != ['Si', 'Si'] or z != 4 or case['electrons']['n_electrons'] != len(species)*z:
        raise ValueError('This inspection requires the neutral two-Si, eight-electron case')
    if case['pseudo']['dftk_rcut_bohr'] is not None:
        raise ValueError('This inspection requires the full available radial grid')
    result = reference_from_arrays(radii, potential_ry, z, len(species),
                                   cell_volume(case['geometry']['lattice_vectors_bohr']))
    result.update(schema_version=1, reference_inspection_status='PASS',
                  input_filename=upf_path.name, input_sha256=checksum,
                  case_sha256=hashlib.sha256(case_bytes).hexdigest(), upf_version=tree.attrib['version'],
                  units_source=UPF_UNITS_SOURCE,
                  scope='Independent finite local-potential radial integral only; no numerical agreement or SCF claim')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, default=ROOT/'benchmarks/si-sr-lda/case.json')
    parser.add_argument('--upf', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        case = json.loads(args.case.read_text())
        upf = args.upf or ROOT/case['pseudo']['local_path']
        result = inspect_file(upf, args.case)
        encoded = json.dumps(result, indent=2, allow_nan=False)+'\n'
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as output:
            output.write(encoded)
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as error:
        print('Independent Si reference inspection failed: '+str(error), file=sys.stderr)
        return 1
    print(json.dumps({'reference_inspection_status': 'PASS', 'alpha_ha_bohr3': result['alpha_ha_bohr3'],
                      'C_ha': result['C_ha']}, allow_nan=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
