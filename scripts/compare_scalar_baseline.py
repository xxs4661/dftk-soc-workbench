#!/usr/bin/env python3
"""Check paired Si inputs before comparing raw and globally referenced energies."""
import argparse
import csv
import itertools
import json
import math
from pathlib import Path
import sys

# CODATA 2022: https://physics.nist.gov/cuu/pdf/factors_2022.pdf
HARTREE_EV = 27.211386245981


def energy_to_ha(value, unit):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError('Energy must be finite')
    unit = unit.removesuffix('/cell')
    if unit not in ('Ha', 'Ry', 'eV'):
        raise ValueError('Unsupported energy unit')
    return value / {'Ha': 1, 'Ry': 2, 'eV': HARTREE_EV}[unit]


def validate_case(case):
    # Supported PW92 mapping, independently documented in the case README.
    xc = case['xc']
    if (xc['upf_functional'].split() != ['SLA','PW','NOGX','NOGC'] or
            xc['dftk_identifiers'] != ['lda_x','lda_c_pw'] or
            xc['qe_internal_indices'] != [1,4,0,0] or xc['libxc_ids'] != [1,12]):
        raise ValueError('Unsupported or inconsistent case XC mapping')
    electrons = case['electrons']
    if any(electrons[key] != value for key, value in
           [('n_electrons', 8), ('n_bands', 8), ('n_occupied', 4), ('spin_degeneracy', 2)]):
        raise ValueError('Si case requires eight electrons, eight scalar bands and four occupied bands')
    requested_kpoint_count(case)


def requested_kpoint_count(case):
    """The request, never the output, defines the expected 8/64-point grid.

    Historical B0 has no count field; its explicit input list remains authoritative.
    New cases also declare n_kpoints, which must agree with that list.
    """
    points = case['kpoints']
    count = case.get('n_kpoints', len(points))
    if type(count) is not int or count not in (8, 64) or len(points) != count:
        raise ValueError('Requested k-point count must be 8 or 64 and match the explicit list')
    axis = (0, -.5) if count == 8 else (0, .25, -.5, -.25)
    expected = [{'coordinate_fractional': list(p)} for p in itertools.product(axis, repeat=3)]
    match_kpoints(expected, points)
    for point in points:
        check_close(point['weight_spatial'], 1 / count, 'Requested spatial weight', tol=1e-12)
    return count


def lattice_columns(vectors):
    """Matrix rows for a DFTK matrix whose columns are the listed cell vectors."""
    if len(vectors) != 3 or any(len(row) != 3 for row in vectors):
        raise ValueError('Cell must contain three three-component vectors')
    return [list(row) for row in zip(*vectors)]


def volume(v):
    a, b, c = v
    return abs(a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0]))


def same_point(a, b, tolerance=1e-8):
    if len(a) != 3 or len(b) != 3 or not all(math.isfinite(x) for x in [*a, *b]):
        raise ValueError('Invalid fractional coordinate')
    return all(abs((x-y)-round(x-y)) <= tolerance for x, y in zip(a, b))


def match_kpoints(expected, actual):
    if len(expected) != len(actual):
        raise ValueError('Missing or extra k points')
    matches, used = [], set()
    for point in expected:
        candidates = [i for i, candidate in enumerate(actual)
                      if same_point(point['coordinate_fractional'], candidate['coordinate_fractional'])]
        if len(candidates) != 1 or candidates[0] in used:
            raise ValueError('Missing, duplicate or ambiguous k point')
        used.add(candidates[0])
        matches.append(actual[candidates[0]])
    return matches


def finite_tree(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('Nonfinite data')
    if isinstance(value, dict):
        for item in value.values():
            finite_tree(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            finite_tree(item)


def check_close(a, b, name, tol=1e-9):
    if not math.isfinite(a) or not math.isfinite(b) or abs(a-b) > tol:
        raise ValueError(name + ' mismatch')


def validate_result(case, result, code):
    finite_tree(result)
    if result['execution_status'] != 'PASS' or result['converged'] is not True or result['exit_code'] != 0:
        raise ValueError(code + ' did not execute and converge')
    if result['pseudo_sha256'] != case['pseudo']['sha256']:
        raise ValueError(code + ' pseudopotential checksum mismatch')
    if result['n_bands'] != case['electrons']['n_bands']:
        raise ValueError(code + ' compared band count mismatch')
    check_close(result['n_electrons'], case['electrons']['n_electrons'], 'Electron count')
    check_close(result['ecut_ha'], case['cutoffs']['dftk_ecut_ha'], 'Wavefunction cutoff')
    for actual, expected in zip(result['lattice_vectors_bohr'], case['geometry']['lattice_vectors_bohr']):
        if len(actual) != 3:
            raise ValueError('Lattice vector dimensions mismatch')
        for x, y in zip(actual, expected):
            check_close(x, y, 'Lattice')
    if len(result['lattice_vectors_bohr']) != 3:
        raise ValueError('Missing lattice vectors')
    positions = result['positions_fractional']
    expected_positions = case['geometry']['positions_fractional']
    if len(positions) != len(expected_positions) or not all(same_point(x, y) for x, y in zip(positions, expected_positions)):
        raise ValueError('Atomic geometry mismatch')
    if result['atom_symbols'] != case['geometry']['species']:
        raise ValueError('Atomic species mismatch')
    if code == 'DFTK':
        if result['xc_raw'] != case['xc']['dftk_identifiers']:
            raise ValueError('DFTK functional mismatch')
        if result['pseudo']['nlcc'] != case['pseudo']['nlcc'] or not result['xc_backend']['core_density_present']:
            raise ValueError('DFTK NLCC mismatch')
        model = result['input_settings']
        if model['spin_polarization'] != 'none' or model['temperature_ha'] != 0 or model['symmetry_operations'] != 1:
            raise ValueError('DFTK spin/temperature/symmetry mismatch')
        if result['environment']['status'] != 'PASS' or not result['diagonalization']['converged']:
            raise ValueError('DFTK identity or target-band diagonalization failed')
    else:
        # QE also prints higher-order XC indices; those must all remain zero.
        if result['xc_indices'][:4] != case['xc']['qe_internal_indices'] or any(result['xc_indices'][4:]):
            raise ValueError('QE actual exchange/correlation parametrization mismatch')
        if result['nlcc'] != case['pseudo']['nlcc']:
            raise ValueError('QE NLCC mismatch')
        check_close(result['ecutrho_ha'], energy_to_ha(case['cutoffs']['qe_ecutrho_ry'], 'Ry'), 'Density cutoff')
        model = result['input_model']
        if model['nspin'] != 1 or any(model[x] for x in ('lsda','noncolin','spinorbit')) or model['occupations'] != 'fixed':
            raise ValueError('QE spin/occupation mismatch')
        if not all(model[x] for x in ('nosym','noinv','diago_full_acc')):
            raise ValueError('QE symmetry or diagonalization mismatch')
    points = match_kpoints(case['kpoints'], result['kpoints'])
    electron_sum = 0.0
    nb, no = case['electrons']['n_bands'], case['electrons']['n_occupied']
    for expected, point in zip(case['kpoints'], points):
        check_close(point['weight_spatial'], expected['weight_spatial'], 'Spatial weight')
        energies, occ = point['eigenvalues_ha'], point['occupations']
        if len(energies) != nb or len(occ) != nb:
            raise ValueError('Missing eigenvalues or occupations')
        for i, number in enumerate(occ):
            check_close(number, 2 if i < no else 0, 'Fixed occupation')
        if energies != sorted(energies):
            raise ValueError('Eigenvalues are not ordered; occupations cannot be associated safely')
        electron_sum += point['weight_spatial'] * sum(occ)
    check_close(sum(p['weight_spatial'] for p in points), 1, 'Spatial weight sum')
    check_close(electron_sum, case['electrons']['n_electrons'], 'Integrated electron count')
    energy_to_ha(result['energy_ha'], 'Ha')
    check_close(energy_to_ha(result['energy_raw']['value'], result['energy_raw']['unit']),
                result['energy_ha'], 'Raw/normalized total energy', tol=1e-12)
    if max(p['eigenvalues_ha'][no-1] for p in points) > min(p['eigenvalues_ha'][no] for p in points):
        raise ValueError('Global occupied/empty levels violate the fixed zero-temperature model')
    return points


def statistics(values):
    return {'max_abs_ha': max(abs(x) for x in values),
            'rms_ha': math.sqrt(sum(x*x for x in values)/len(values)),
            'max_abs_ev': max(abs(x) for x in values)*HARTREE_EV,
            'rms_ev': math.sqrt(sum(x*x for x in values)/len(values))*HARTREE_EV}


def compare(case, dftk, qe):
    """No fitted shifts: each code uses exactly one sampled global HOMO reference."""
    validate_case(case)
    dp, qp = validate_result(case, dftk, 'DFTK'), validate_result(case, qe, 'QE')
    no = case['electrons']['n_occupied']
    refs = {name: max(p['eigenvalues_ha'][no-1] for p in points)
            for name, points in [('DFTK', dp), ('QE', qp)]}
    rows = []
    for ik, (d, q) in enumerate(zip(dp, qp)):
        for ib, (de, qe_value) in enumerate(zip(d['eigenvalues_ha'], q['eigenvalues_ha'])):
            shifted_d, shifted_q = de-refs['DFTK'], qe_value-refs['QE']
            rows.append({'kpoint_index': ik+1, 'k_fractional': case['kpoints'][ik]['coordinate_fractional'],
                         'band': ib+1, 'occupation': d['occupations'][ib],
                         'dftk_ha': de, 'qe_ha': qe_value, 'delta_ha': de-qe_value,
                         'dftk_global_reference_ha': shifted_d, 'qe_global_reference_ha': shifted_q,
                         'global_reference_delta_ha': shifted_d-shifted_q})
    summary = {}
    for name, group in [('all',rows),('occupied',[r for r in rows if r['occupation']>0]),
                        ('empty',[r for r in rows if r['occupation']==0])]:
        summary[name] = {'raw':statistics([r['delta_ha'] for r in group]),
                         'global_reference':statistics([r['global_reference_delta_ha'] for r in group])}
    gaps = {}
    for name, points in [('DFTK', dp), ('QE', qp)]:
        lumo = min(p['eigenvalues_ha'][no] for p in points)
        gaps[name] = {'sampled_homo_ha':refs[name], 'sampled_lumo_ha':lumo,
                      'sampled_grid_gap_ha':lumo-refs[name], 'sampled_grid_gap_ev':(lumo-refs[name])*HARTREE_EV}
    delta, nat = dftk['energy_ha']-qe['energy_ha'], len(case['geometry']['species'])
    totals = {name:{'ha_cell':result['energy_ha'],'ha_atom':result['energy_ha']/nat,
                    'ev_atom':result['energy_ha']/nat*HARTREE_EV,'raw':result['energy_raw']}
              for name,result in [('DFTK',dftk),('QE',qe)]}
    totals['delta_DFTK_minus_QE']={'ha_cell':delta,'abs_ha_cell':abs(delta),
                                  'ha_atom':delta/nat,'ev_atom':delta/nat*HARTREE_EV}
    return {'schema_version':1,'execution_status':'PASS','input_comparability_status':'PASS',
            'numerical_agreement_status':'REVIEW_REQUIRED','convergence_study_status':'NOT_RUN',
            'total_energy':totals,'global_references_ha':refs,'global_reference_delta_ha':refs['DFTK']-refs['QE'],
            'eigenvalue_summary':summary,'sampled_grid_gaps':gaps,'eigenvalues':rows,
            'hartree_ev':HARTREE_EV,'conversion_source':'https://physics.nist.gov/cuu/pdf/factors_2022.pdf',
            'delta_convention':'DFTK minus QE; no total-energy correction or fitted shift'}


def save_comparison(directory, result):
    (directory/'comparison.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    with (directory/'eigenvalues.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=result['eigenvalues'][0].keys())
        writer.writeheader(); writer.writerows(result['eigenvalues'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case',type=Path); parser.add_argument('dftk',type=Path)
    parser.add_argument('qe',type=Path); parser.add_argument('output',type=Path)
    args=parser.parse_args()
    try:
        result=compare(*[json.loads(p.read_text()) for p in (args.case,args.dftk,args.qe)])
        args.output.mkdir(parents=True,exist_ok=False)
        save_comparison(args.output,result)
    except (ValueError,KeyError,OSError) as error:
        print('Scalar comparison failed: '+str(error),file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    sys.exit(main())
