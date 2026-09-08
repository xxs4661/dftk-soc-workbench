"""Synthetic Si-format/protocol tests; none of these arrays are physical results."""
import copy
import itertools
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from si_soc_comparison import (CASE, LATTICE, POSITIONS, PROBES, SCF_POINTS,
    HARTREE_EV, parse_si_qe, compare_spectra, analyze_gamma, _contract)
from parse_qe_soc import QE_HARTREE_EV


def case():
    value = json.loads((ROOT/'benchmarks/si-soc-splitting-v1/case.json').read_text())
    value['verified_pseudo_sha256'] = value['pseudo']['sha256']
    value['binding'] = {
        'D': {'scf_run_id': 'synthetic-d-scf', 'density_sha256': 'd'*64,
              'spectrum_run_id': 'synthetic-d-spectrum', 'null_run_id': 'synthetic-d-null'},
        'Q': {'scf_run_id': 'synthetic-q-scf', 'density_sha256': 'e'*64,
              'spectrum_run_id': 'synthetic-q-spectrum'}}
    return value


def levels(offset=0., null=False):
    # Deliberately arbitrary synthetic splitting 31 meV, not experimental44.
    ev = [-2., -2.] + ([-.031]*2+[0.]*4 if not null else [0.]*6)
    ev += [1.+i*.2 for i in range(8) for _ in range(2)]
    return [x/HARTREE_EV+offset for x in ev]


def receipt(label, *, null=False, offset=0.):
    c = case()
    binding = c['binding'][label]
    points = [PROBES[0]] if null else PROBES
    return {'schema_version': 1, 'case': CASE, 'kind': 'null' if null else 'spectrum',
            'code': 'DFTK' if label == 'D' else 'QE', 'execution_status': 'PASS', 'process_exit_code': 0,
            'run_id': binding['null_run_id' if null else 'spectrum_run_id'],
            'source_scf_run_id': binding['scf_run_id'], 'density_source_sha256': binding['density_sha256'],
            'pseudo_sha256': c['pseudo']['sha256'], 'physical_operator': 'spin_trace_null' if null else 'full_soc',
            'n_electrons': 8, 'n_bands': 24, 'occupation_capacity': 1, 'fermi_energy_ha': .6/HARTREE_EV+offset,
            'kpoints': [{'coordinate_fractional': list(p), 'eigenvalues_ha': levels(offset, null),
                         'residuals_ha': [1e-12]*24, 'gram_frobenius': 1e-12} for p in points],
            'precision': {'diago_thr_init_ry': 1e-13, 'ethr_history_ry': [1e-13]},
            'warning_evidence': {'eigenvalues_not_converged': False, 'ieee_localization_status': 'NOT_LOCALIZED'}}


def put(parent, tag, value=None, **attributes):
    node = ET.SubElement(parent, tag, attributes)
    node.text = None if value is None else str(value)
    return node


def fixture(kind='scf'):
    """Invented native-format fixture, independent of real source/radial data."""
    c = case()
    root = ET.Element('qes:espresso', {'xmlns:qes': 'http://www.quantum-espresso.org/ns/qes/qes-1.0',
                                    'Units': 'Hartree atomic units'})
    info = put(root, 'general_info')
    put(info, 'xml_format', NAME='QEXSD', VERSION='25.05.21')
    put(info, 'creator', NAME='PWSCF', VERSION='7.5')
    inp = put(root, 'input')
    ctl = put(inp, 'control_variables')
    for name, value in {'calculation': 'scf' if kind == 'scf' else 'bands', 'restart_mode': 'from_scratch',
                        'verbosity': 'high', 'disk_io': 'low', 'forces': 'false', 'stress': 'false'}.items():
        put(ctl, name, value)
    sp = put(put(inp, 'atomic_species'), 'species', name='Si')
    put(sp, 'pseudo_file', 'Si_r.upf'); put(sp, 'starting_magnetization', 0)
    for parent in (put(inp, 'spin'),):
        for name, value in {'lsda': 'false', 'noncolin': 'true', 'spinorbit': 'true'}.items():
            put(parent, name, value)
    sym = put(inp, 'symmetry_flags')
    for name in ('nosym', 'noinv', 'no_t_rev'): put(sym, name, 'true')
    bands = put(inp, 'bands')
    put(bands, 'occupations', 'smearing'); put(bands, 'tot_charge', 0)
    put(bands, 'smearing', 'fd', degauss='.001')
    electron = put(inp, 'electron_control')
    for name, value in {'diago_full_acc': 'true', 'diago_thr_init': 1e-10 if kind == 'scf' else 1e-13,
                        'conv_thr': 5e-13, 'mixing_beta': .3, 'max_nstep': 200,
                        'diagonalization': 'davidson' if kind == 'scf' else 'cg', 'diago_cg_maxiter': 300}.items():
        put(electron, name, value)
    out = put(root, 'output')
    mag = put(out, 'magnetization')
    for name, value in {'lsda': 'false', 'noncolin': 'true', 'spinorbit': 'true',
                        'do_magnetization': 'false', 'absolute': 0}.items(): put(mag, name, value)
    structure = put(out, 'atomic_structure', nat='2', alat='10.26')
    cell = put(structure, 'cell')
    for i, row in enumerate(LATTICE, 1): put(cell, 'a'+str(i), ' '.join(map(str, row)))
    atoms = put(structure, 'atomic_positions')
    for pos in POSITIONS:
        cartesian = [sum(pos[i]*LATTICE[i][j] for i in range(3)) for j in range(3)]
        put(atoms, 'atom', ' '.join(map(str, cartesian)), name='Si')
    ib, ob = put(inp, 'basis'), put(out, 'basis_set')
    for basis in (ib, ob):
        put(basis, 'ecutwfc', 30); put(basis, 'ecutrho', 120)
        for grid in ('fft_grid', 'fft_smooth'): put(basis, grid, nr1='48', nr2='48', nr3='48')
    reciprocal = put(ob, 'reciprocal_lattice')
    for i, row in enumerate([[-1, 1, 1], [1, -1, 1], [1, 1, -1]], 1):
        put(reciprocal, 'b'+str(i), ' '.join(map(str, row)))
    put(put(put(out, 'atomic_species'), 'species', name='Si'), 'pseudo_file', 'Si_r.upf')
    put(put(out, 'dft'), 'functional', 'PBE')
    bands = put(out, 'band_structure')
    points = SCF_POINTS if kind == 'scf' else PROBES
    for name, value in {'lsda': 'false', 'noncolin': 'true', 'spinorbit': 'true', 'occupations_kind': 'smearing',
                        'nbnd': 24, 'nelec': 8, 'nks': len(points), 'fermi_energy': .3/HARTREE_EV}.items():
        put(bands, name, value)
    put(bands, 'smearing', 'fd', degauss='.001')
    for p in points:
        k = put(bands, 'ks_energies')
        raw = [sum(p[i]*([-1, 1, 1], [1, -1, 1], [1, 1, -1])[i][j] for i in range(3)) for j in range(3)]
        put(k, 'k_point', ' '.join(map(str, raw)), weight=str(1/len(points)))
        put(k, 'npw', 100)
        put(k, 'eigenvalues', ' '.join(map(str, levels())), size='24')
        put(k, 'occupations', ' '.join(map(str, [1]*8+[0]*16)), size='24')
    energy = put(out, 'total_energy')
    put(energy, 'etot', -9.); put(energy, 'demet', 0.)
    scf = put(put(out, 'convergence_info'), 'scf_conv')
    put(scf, 'convergence_achieved', 'true'); put(scf, 'n_scf_steps', 2); put(scf, 'scf_error', 1e-14)
    put(root, 'exit_status', 0); put(root, 'closed')
    return root


def stdout_for(xml, kind='scf'):
    lines = ['Synthetic fixture, not actual QE/Si evidence.', 'Program PWSCF v.7.5',
             'PseudoPot. # 1 for Si read from file:', './pseudo/Si_r.upf',
             'Pseudo is Norm-conserving + core correction, Zval = 4.0',
             'Exchange-correlation = SLA PW PBX PBC ( 1 4 3 4 0 0 0 )',
             'Starting wfcs are 8 randomized atomic wfcs + 16 random wfcs']
    if kind == 'scf':
        for i in (1, 2):
            lines += [f'iteration # {i}', 'Davidson diagonalization with overlap', 'ethr = 1.00E-10',
                      'total energy = -18.00000000 Ry', 'estimated scf accuracy < 2.0E-14 Ry']
        lines += ['End of self-consistent calculation']
    else:
        lines += ['The potential is recalculated from file :', 'Band Structure Calculation',
                  'CG style diagonalization', 'ethr = 1.00E-13', 'End of band structure calculation']
    for k in xml.findall('output/band_structure/ks_energies'):
        raw = [float(x) for x in k.find('k_point').text.split()]
        lines += ['k = '+' '.join(f'{x:.8f}' for x in raw)+' (100 PWs) bands (ev):', '']
        values = [float(x)*QE_HARTREE_EV for x in k.find('eigenvalues').text.split()]
        lines += [' '.join(f'{v:.6f}' for v in values[i:i+8]) for i in range(0, len(values), 8)]
        occ = k.find('occupations')
        if occ is not None:
            lines += ['', 'occupation numbers']
            tokens = occ.text.split()
            lines += [' '.join(tokens[i:i+8]) for i in range(0, len(tokens), 8)]
        lines += ['']
    if kind == 'scf':
        lines += [f'the Fermi energy is {.3*QE_HARTREE_EV/HARTREE_EV:.8f} ev',
                  '! total energy = -18.00000000 Ry', 'smearing contrib. (-TS) = 0.00000000 Ry',
                  'internal energy E=F+TS = -18.00000000 Ry', 'convergence has been achieved in 2 iterations']
    lines += ['JOB DONE.']
    return '\n'.join(lines)+'\n'


class SiParserTests(unittest.TestCase):
    def parse(self, xml=None, *, kind='scf', stdout=None, stderr='', code=0, cfg=None):
        xml = fixture(kind) if xml is None else xml
        stdout = stdout_for(xml, kind) if stdout is None else stdout
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'synthetic.xml'
            path.write_text(ET.tostring(xml, encoding='unicode'))
            return parse_si_qe(path, stdout, stderr, kind=kind, case=case() if cfg is None else cfg, process_exit_code=code)

    def test_scf_eight_points_two_atoms_nlcc_pbe(self):
        d = self.parse()
        self.assertEqual((d['n_electrons'], d['n_atoms'], d['n_bands']), (8, 2, 24))
        self.assertEqual(len(d['kpoints']), 8); self.assertEqual(d['electron_sum'], 8)
        self.assertEqual(d['scf']['iterations'], 2); self.assertEqual(len(d['scf']['trace']), 2)
        self.assertEqual(d['energy']['internal_ha'], -9); self.assertTrue(d['nlcc'])

    def test_spectrum_three_points_has_no_new_energy_or_scf(self):
        d = self.parse(kind='spectrum')
        self.assertEqual(len(d['kpoints']), 3); self.assertIsNone(d['energy']); self.assertIsNone(d['scf'])
        self.assertIsNone(d['electron_sum']); self.assertEqual(d['precision']['diago_thr_init_ry'], 1e-13)

    def test_nonorthogonal_coordinate_reordering_and_modulo(self):
        xml = fixture(); bands = xml.find('output/band_structure')
        nodes = bands.findall('ks_energies')
        for node in nodes: bands.remove(node)
        for node in reversed(nodes): bands.append(node)
        self.assertEqual(self.parse(xml)['requested_to_xml_indices'], list(reversed(range(8))))

    def test_k_missing_duplicate_wrong_weight_wrong_expected_count(self):
        for mode in ('missing', 'duplicate', 'weight', 'count'):
            xml = fixture(); band = xml.find('output/band_structure'); ks = band.findall('ks_energies')
            if mode == 'missing': band.remove(ks[-1])
            if mode == 'duplicate': ks[-1].find('k_point').text = ks[0].find('k_point').text
            if mode == 'weight': ks[0].find('k_point').set('weight', '.25')
            if mode == 'count': band.find('nks').text = '3'
            with self.subTest(mode=mode), self.assertRaises(ValueError): self.parse(xml)

    def test_wrong_electron_band_capacity_and_core_added_to_electrons(self):
        for path, value in [('nelec', '10'), ('nelec', '12'), ('nbnd', '12')]:
            xml = fixture(); xml.find('output/band_structure/'+path).text = value
            with self.subTest(path=path, value=value), self.assertRaises(ValueError): self.parse(xml)
        xml = fixture(); xml.find('output/band_structure/ks_energies/occupations').text = ' '.join(['2']*24)
        with self.assertRaisesRegex(ValueError, 'capacity'): self.parse(xml)

    def test_nlcc_missing_pbesol_wrong_source_and_mg_defaults_rejected(self):
        xml = fixture(); native = stdout_for(xml)
        for old, new in [('+ core correction', ''), ('Zval = 4.0', 'Zval = 10.0'),
                         ('1 4 3 4', '1 4 10 8'), ('./pseudo/Si_r.upf', './pseudo/Mg.upf')]:
            with self.subTest(new=new), self.assertRaises(ValueError): self.parse(xml, stdout=native.replace(old, new))
        c = case(); c['verified_pseudo_sha256'] = 'f'*64
        with self.assertRaisesRegex(ValueError, 'UPF'): self.parse(cfg=c)
        c = case(); c['electrons']['n_electrons'] = 10
        with self.assertRaises(ValueError): self.parse(cfg=c)

    def test_exact_fft_geometry_xc_spin_controls(self):
        for path, value in [('input/spin/spinorbit', 'false'), ('input/symmetry_flags/noinv', 'false'),
                            ('output/dft/functional', 'PBESOL'), ('input/basis/ecutwfc', '15'),
                            ('input/electron_control/diagonalization', 'cg'),
                            ('output/magnetization/do_magnetization', 'true')]:
            xml = fixture(); xml.find(path).text = value
            with self.subTest(path=path), self.assertRaises(ValueError): self.parse(xml)
        xml = fixture(); xml.find('input/basis/fft_grid').set('nr1', '40')
        with self.assertRaisesRegex(ValueError, 'FFT'): self.parse(xml)
        xml = fixture(); xml.find('output/atomic_structure').set('nat', '1')
        with self.assertRaisesRegex(ValueError, 'two atoms'): self.parse(xml)

    def test_failure_exit_truncated_output_no_stale_completion(self):
        for code in (1, 9, -15, True):
            with self.subTest(code=code), self.assertRaises(ValueError): self.parse(code=code)
        native = stdout_for(fixture())
        with self.assertRaises(ValueError): self.parse(stdout=native.replace('JOB DONE.', ''))
        with self.assertRaises(ValueError): self.parse(stdout=native.replace('has been achieved', 'NOT achieved'))

    def test_spectrum_cannot_reuse_file_wfc_or_feedback(self):
        native = stdout_for(fixture('spectrum'), 'spectrum')
        for changed in [native.replace('Starting wfcs are 8 randomized atomic wfcs + 16 random wfcs', 'Starting wfcs from file'),
                        native+'iteration # 1\n', native.replace('The potential is recalculated from file :', '')]:
            with self.subTest(changed=changed[-30:]), self.assertRaises(ValueError): self.parse(kind='spectrum', stdout=changed)

    def test_warnings_are_not_cleared_by_zero_exit(self):
        native = stdout_for(fixture('spectrum'), 'spectrum')+'c_bands: 1 eigenvalues not converged\n'
        d = self.parse(kind='spectrum', stdout=native, stderr='Note: IEEE_INVALID_FLAG IEEE_UNDERFLOW_FLAG\n')
        self.assertEqual(d['execution_status'], 'PASS')
        self.assertEqual(d['eigensolver_status'], 'EIGENSOLVER_REVIEW_REQUIRED')
        self.assertTrue(d['warning_evidence']['ieee_flags']['IEEE_INVALID_FLAG']['reported'])

    def test_bands_placeholder_energy_is_ignored_and_kind_mixing_rejected(self):
        xml = fixture('spectrum'); xml.find('output/total_energy/etot').text = '-999999'
        self.assertIsNone(self.parse(xml, kind='spectrum')['energy'])
        with self.assertRaises(ValueError): self.parse(fixture(), kind='spectrum')

    def test_nonfinite_and_native_print_corruption_rejected(self):
        xml = fixture(); native = stdout_for(xml)
        xml.find('output/band_structure/ks_energies/eigenvalues').text = ' '.join(['NaN']*24)
        with self.assertRaises(ValueError): self.parse(xml, stdout=native)
        with self.assertRaises(ValueError): self.parse(stdout=native.replace('bands (ev):\n\n-2.', 'bands (ev):\n\n-3.', 1))


class SiComparisonTests(unittest.TestCase):
    def compare(self, d=None, q=None, n=None, cfg=None):
        return compare_spectra(receipt('D') if d is None else d, receipt('Q') if q is None else q,
                               receipt('D', null=True) if n is None else n, case() if cfg is None else cfg)

    def test_fixed_groups_and_successful_synthetic_split_null(self):
        out = self.compare()
        for key in ('splitting_comparison_status', 'manifold_assignment_status', 'spin_trace_control_status'):
            self.assertEqual(out[key], 'PASS')
        self.assertAlmostEqual(out['D_gamma']['delta_so_ev'], .031)
        self.assertEqual(out['D_null_gamma']['six_state_width_ev'], 0)
        self.assertEqual(out['numerical_review_status'], 'REVIEW_REQUIRED')

    def test_global_shift_invariance_single_reference_all_probes(self):
        out = self.compare(d=receipt('D', offset=5.4))
        self.assertAlmostEqual(out['delta_so_D_minus_Q_ev'], 0)
        self.assertEqual(out['splitting_comparison_status'], 'PASS')
        for p in out['spectra']:
            self.assertLess(p['max_abs_referenced_ev'], 1e-12)
            self.assertAlmostEqual(p['raw_D_minus_Q_ha'][0], 5.4)

    def test_per_point_shift_is_visible_never_fitted(self):
        d = receipt('D')
        for p in d['kpoints'][1:]: p['eigenvalues_ha'] = [v+.01 for v in p['eigenvalues_ha']]
        out = self.compare(d=d)
        self.assertAlmostEqual(out['spectra'][1]['global_referenced_D_minus_Q_ha'][0], .01)
        d['per_k_shift'] = [.0, .01, .01]
        with self.assertRaisesRegex(ValueError, 'Fitting'): self.compare(d=d)

    def test_hardcoded_experiment_or_any_fitting_flag_rejected(self):
        for name in ('fitted_shift', 'per_band_shift', 'experimental_target_ev', 'energy_correction_ha'):
            d = receipt('D'); d[name] = .044
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Fitting'): self.compare(d=d)

    def test_wrong_group_quartet_not_replaced_by_doublet(self):
        d = receipt('D'); d['kpoints'][0]['eigenvalues_ha'][6:8] = [.001/HARTREE_EV]*2
        out = self.compare(d=d)
        self.assertEqual(out['D_gamma']['multiplet_structure_status'], 'MISMATCH')
        self.assertNotEqual(out['splitting_comparison_status'], 'PASS')

    def test_missing_state_twelve_duplicate_representation_or_nan_rejected(self):
        for mode in ('missing', 'twelve', 'nan'):
            d = receipt('D')
            if mode == 'missing': d['kpoints'][0]['eigenvalues_ha'].pop()
            if mode == 'twelve':
                d['n_bands'] = 12  # scalar provenance cannot become spinor by duplicating values.
                d['kpoints'][0]['eigenvalues_ha'] = sorted(d['kpoints'][0]['eigenvalues_ha'][:12]*2)
            if mode == 'nan': d['kpoints'][0]['eigenvalues_ha'][3] = float('nan')
            with self.subTest(mode=mode), self.assertRaises(ValueError): self.compare(d=d)

    def test_zero_soc_and_split_mismatch_are_not_pass(self):
        d = receipt('D')
        for p in d['kpoints']: p['eigenvalues_ha'] = levels(null=True)
        self.assertEqual(self.compare(d=d)['splitting_comparison_status'], 'MISMATCH')
        d = receipt('D')
        for p in d['kpoints']: p['eigenvalues_ha'][2:4] = [-.035/HARTREE_EV]*2
        self.assertEqual(self.compare(d=d)['splitting_comparison_status'], 'MISMATCH')

    def test_isolation_failure_does_not_change_window(self):
        d = receipt('D'); d['kpoints'][0]['eigenvalues_ha'][:2] = [-.04/HARTREE_EV]*2
        out = self.compare(d=d)
        self.assertEqual(out['manifold_assignment_status'], 'MANIFOLD_ASSIGNMENT_REVIEW_REQUIRED')
        self.assertEqual(out['D_gamma']['fixed_state_indices_one_based']['split_off'], [3, 4])

    def test_gamma_occupation_extra_diagnostic_does_not_suppress_statistics(self):
        d = receipt('D'); d['fermi_energy_ha'] = 0.
        out = self.compare(d=d)
        self.assertEqual(out['gamma_occupation_diagnostic_status'], 'REVIEW_REQUIRED')
        self.assertAlmostEqual(out['D_gamma']['delta_so_ev'], .031)
        d['fermi_energy_ha'] = .3/HARTREE_EV
        out = self.compare(d=d)
        self.assertEqual(out['gamma_occupation_diagnostic_status'], 'REVIEW_REQUIRED')
        self.assertEqual(out['splitting_comparison_status'], 'PASS')

    def test_null_is_not_zero_nl_or_only_offdiagonal_deletion(self):
        for wrong in ('zero_nl', 'delete_offdiagonal', 'scalar_upf'):
            n = receipt('D', null=True); n['physical_operator'] = wrong
            with self.subTest(wrong=wrong), self.assertRaisesRegex(ValueError, 'operator'): self.compare(n=n)
        n = receipt('D', null=True); n['kpoints'][0]['eigenvalues_ha'] = levels()
        self.assertEqual(self.compare(n=n)['spin_trace_control_status'], 'MISMATCH')

    def test_stale_current_run_and_wrong_final_density_are_rejected(self):
        for key, value in [('run_id', 'old-success'), ('source_scf_run_id', 'old-density'),
                           ('density_source_sha256', '0'*64), ('pseudo_sha256', '0'*64)]:
            d = receipt('D'); d[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.compare(d=d)
        c = case(); del c['binding']['D']
        with self.assertRaises((KeyError, ValueError)): self.compare(cfg=c)

    def test_nonzero_worker_exit_even_if_pass_is_rejected(self):
        for code in (1, 9, -15, True):
            q = receipt('Q'); q['process_exit_code'] = code
            with self.subTest(code=code), self.assertRaises(ValueError): self.compare(q=q)

    def test_scf_and_null_cannot_replace_full_spectrum(self):
        for kind in ('scf', 'null'):
            d = receipt('D'); d['kind'] = kind
            with self.subTest(kind=kind), self.assertRaises(ValueError): self.compare(d=d)

    def test_negative_partner_mapping_and_whole_spectrum_preserved(self):
        d = receipt('D'); d['kpoints'] = d['kpoints'][::-1]
        out = self.compare(d=d)
        self.assertEqual(len(out['spectra']), 3)
        self.assertTrue(all(len(p['D_raw_ha']) == 24 for p in out['spectra']))
        d['kpoints'][0]['coordinate_fractional'] = PROBES[1]
        with self.assertRaises(ValueError): self.compare(d=d)

    def test_residual_gram_and_qe_unconverged_are_separate_gates(self):
        d = receipt('D'); d['kpoints'][0]['residuals_ha'][23] = 1e-7
        out = self.compare(d=d)
        self.assertEqual(out['D_precision']['D_full']['status'], 'MISMATCH')
        q = receipt('Q'); q['warning_evidence']['eigenvalues_not_converged'] = True
        self.assertEqual(self.compare(q=q)['Q_eigensolver_status'], 'EIGENSOLVER_REVIEW_REQUIRED')
        q['precision']['ethr_history_ry'] = [1e-10]
        with self.assertRaises(ValueError): self.compare(q=q)

    def test_no_empirical_total_energy_correction(self):
        d, q = receipt('D'), receipt('Q')
        d['energy'] = {'internal_ha': -8}; q['energy'] = {'internal_ha': -9}
        before = copy.deepcopy((d, q))
        self.compare(d=d, q=q)
        self.assertEqual((d, q), before)


if __name__ == '__main__':
    unittest.main()
