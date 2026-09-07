"""Synthetic protocol fixtures only; these are not QE or physical calculations."""
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from parse_qe_soc_diagnostics import parse_qe_soc_diagnostics, native_warnings, IEEE_FLAGS
from parse_qe_soc import QeSocParseError
from test_qe_soc_parser import synthetic_xml, synthetic_stdout_spectrum, SYNTHETIC_STDOUT, put


def diagnostic_case(slot):
    case = json.loads((ROOT / 'benchmarks/mg-soc-qe-diagnostics-v1/plan.json').read_text())
    expected = case['slots'][slot]
    case['qe'].update(calculation=expected['calculation'], diagonalization=expected['solver'],
                      diago_thr_init_ry=expected['diago_thr_init_ry'])
    for name in ('diago_david_ndim', 'diago_cg_maxiter'):
        if name in expected:
            case['qe'][name] = expected[name]
    case['verified_pseudo_sha256'] = case['pseudo']['sha256']
    return case


def diagnostic_xml(slot):
    root = synthetic_xml()
    case = diagnostic_case(slot)
    expected = case['slots'][slot]
    root.find('input/control_variables/calculation').text = expected['calculation']
    put(root.find('input/control_variables'), 'nstep', 0 if slot == 'I36' else 1)
    ctl = root.find('input/electron_control')
    ctl.find('diago_thr_init').text = str(expected['diago_thr_init_ry'])
    put(ctl, 'diagonalization', 'cg' if expected['solver'] == 'cg' else 'davidson')
    put(ctl, 'diago_cg_maxiter', 200 if expected['solver'] == 'cg' else 20)
    for name in ('fft_grid', 'fft_smooth'):
        root.find('output/basis_set/' + name).attrib.update(
            dict(zip(('nr1', 'nr2', 'nr3'), map(str, expected['fft_grid']))))
    for block, count in zip(root.findall('output/band_structure/ks_energies'), (2777, 2770, 2770)):
        block.find('npw').text = str(count)
    if slot == 'I36':
        output = root.find('output')
        for child in list(output):
            if child.tag != 'basis_set': output.remove(child)
        root.remove(root.find('step'))
        root.find('exit_status').text = '255'
    return root


def diagnostic_stdout(slot, root=None):
    root = diagnostic_xml(slot) if root is None else root
    n = 40 if slot.endswith('40') else 36
    grids = f'Dense grid: 100 G-vectors FFT dimensions: ({n}, {n}, {n})\nSmooth grid: 100 G-vectors FFT dimensions: ({n}, {n}, {n})\n'
    if slot == 'I36':
        return 'Synthetic initialization fixture only.\nProgram PWSCF v.7.5\n' + grids
    bands = slot.startswith(('C', 'D'))
    spectrum = synthetic_stdout_spectrum(root, occupations=not bands)
    counts = iter(int(x.text) for x in root.findall('output/band_structure/ks_energies/npw'))
    spectrum = re.sub(r'\(100 PWs\)', lambda m: f'({next(counts)} PWs)', spectrum)
    header = SYNTHETIC_STDOUT.split('End of self-consistent calculation')[0]
    end = SYNTHETIC_STDOUT.split('the Fermi energy', 1)[1]
    banner = 'CG style diagonalization\n' if slot.startswith('C') else 'Davidson diagonalization with overlap\n'
    if bands:
        header = header.replace('ethr = 1.00E-10', 'ethr = 1.00E-13')
        end = re.sub(r'convergence has been achieved[^\n]*\n', '', end)
        header += 'The potential is recalculated from file :\n./scratch/mg_soc_qe_v1.save/charge-density\nStarting wfcs from file\nBand Structure Calculation\n'
    boundary = 'End of band structure calculation' if bands else 'End of self-consistent calculation'
    return header + grids + banner + boundary + '\n' + spectrum + 'the Fermi energy' + end


class QeSocDiagnosticsParserTests(unittest.TestCase):
    def parse(self, slot='D36', xml=None, stdout=None, stderr='', case=None, code=0):
        root = diagnostic_xml(slot) if xml is None else xml
        output = diagnostic_stdout(slot) if stdout is None else stdout
        case = diagnostic_case(slot) if case is None else case
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            x, s, e = folder/'synthetic.xml', folder/'synthetic.stdout', folder/'synthetic.stderr'
            x.write_text(ET.tostring(root, encoding='unicode') if not isinstance(root, str) else root)
            s.write_text(output); e.write_text(stderr)
            return parse_qe_soc_diagnostics(x, s, e, case, slot, code)

    def test_all_five_numeric_slots_use_real_new_case_and_preserve_core(self):
        for slot in ('D36', 'C36', 'G40', 'D40', 'C40'):
            with self.subTest(slot=slot):
                result = self.parse(slot)
                self.assertEqual(result['execution_status'], 'PASS')
                self.assertEqual(result['case'], 'mg-soc-qe-diagnostics-v1')
                self.assertEqual(result['slot'], slot)
                self.assertEqual(sum(len(k['eigenvalues_ha']) for k in result['kpoints']), 72)
                self.assertEqual(result['electrons'], 10)
                self.assertEqual(result['occupation_capacity'], 1)
                self.assertEqual(result['individual_eigenvector_residual_status'], 'NOT_AVAILABLE')
                if slot != 'G40':
                    self.assertIsNone(result['energy'])
                    self.assertEqual(result['energy_semantics_status'], 'NOT_APPLICABLE_SPECTRUM_ONLY')

    def test_actual_cg_xml_and_stdout_are_both_required(self):
        xml = diagnostic_xml('C36'); xml.find('input/electron_control/diagonalization').text = 'davidson'
        with self.assertRaisesRegex(ValueError, 'diagonalization'): self.parse('C36', xml)
        output = diagnostic_stdout('C36').replace('CG style diagonalization', 'Davidson diagonalization')
        with self.assertRaisesRegex(ValueError, 'diagonalization'): self.parse('C36', stdout=output)

    def test_cg_iteration_ceiling_actual_not_only_request(self):
        xml = diagnostic_xml('C36'); xml.find('input/electron_control/diago_cg_maxiter').text = '20'
        with self.assertRaisesRegex(ValueError, 'ceiling'): self.parse('C36', xml)

    def test_requested_solver_cannot_override_slot_contract(self):
        case = diagnostic_case('C36'); case['slots']['C36']['solver'] = 'david'; case['qe']['diagonalization'] = 'david'
        with self.assertRaisesRegex(ValueError, 'six-slot'): self.parse('C36', case=case)

    def test_reject_old_case_and_unknown_slot(self):
        case = diagnostic_case('D36'); case['case'] = 'mg-soc-qe-v1'
        with self.assertRaisesRegex(ValueError, 'Phase 7B'): self.parse(case=case)
        with self.assertRaisesRegex(ValueError, 'Phase 7B'):
            parse_qe_soc_diagnostics(None, None, None, diagnostic_case('D36'), 'D48')

    def test_wrong_requested_algorithm_control_is_rejected(self):
        case = diagnostic_case('D36'); case['qe']['diago_david_ndim'] = 4
        with self.assertRaisesRegex(ValueError, 'algorithm'): self.parse(case=case)

    def test_native_david_workspace_not_invented_as_xml_observation(self):
        record = self.parse()['algorithm_control_evidence']['diago_david_ndim']
        self.assertEqual(record['requested'], 2)
        self.assertEqual(record['native_status'], 'NOT_EXPOSED_IN_QEXSD')

    def test_actual_threshold_ry_not_hartree_conversion(self):
        xml = diagnostic_xml('D36'); xml.find('input/electron_control/diago_thr_init').text = '5e-14'
        with self.assertRaisesRegex(ValueError, 'diago_thr_init'): self.parse(xml=xml)

    def test_reported_ethr_required_separately_from_input(self):
        with self.assertRaisesRegex(ValueError, 'ethr'):
            self.parse(stdout=diagnostic_stdout('D36').replace('ethr = 1.00E-13', 'ethr = 1.00E-10'))

    def test_hard40_smooth36_rejected(self):
        xml = diagnostic_xml('D40'); xml.find('output/basis_set/fft_smooth').attrib.update(nr1='36', nr2='36', nr3='36')
        with self.assertRaisesRegex(ValueError, 'hard/smooth'): self.parse('D40', xml)

    def test_both_actual_grids36_do_not_satisfy40_request(self):
        xml = diagnostic_xml('D40')
        for name in ('fft_grid', 'fft_smooth'):
            xml.find('output/basis_set/' + name).attrib.update(nr1='36', nr2='36', nr3='36')
        with self.assertRaisesRegex(ValueError, 'hard/smooth'): self.parse('D40', xml)

    def test_bands_requires_both_native_file_read_markers(self):
        for marker in ('Starting wfcs from file', 'The potential is recalculated from file'):
            with self.subTest(marker=marker), self.assertRaisesRegex(ValueError, 'file potential'):
                self.parse(stdout=diagnostic_stdout('D36').replace(marker, 'missing marker'))

    def test_bands_rejects_atomic_fallback_or_scf_iteration(self):
        for marker in ('Starting wfcs are atomic + random', 'iteration # 1 ecut=30 Ry'):
            with self.subTest(marker=marker), self.assertRaisesRegex(ValueError, 'fell back'):
                self.parse(stdout=diagnostic_stdout('D36') + '\n' + marker)

    def test_native_counts_are_mapped_by_coordinate(self):
        xml = diagnostic_xml('D36'); parent = xml.find('output/band_structure')
        nodes = parent.findall('ks_energies')
        for node in nodes: parent.remove(node)
        for node in nodes[::-1]: parent.append(node)
        result = self.parse(xml=xml, stdout=diagnostic_stdout('D36', xml))
        self.assertEqual(result['requested_to_xml_kpoint_indices'], [2, 1, 0])
        self.assertEqual(result['kpoints'][2]['npw'], 2777)

    def test_equal_count_does_not_excuse_missing_requested_kpoint(self):
        xml = diagnostic_xml('D36'); xml.findall('output/band_structure/ks_energies/k_point')[2].text = '.125 .0625 -.1875'
        with self.assertRaisesRegex(ValueError, 'Duplicate'): self.parse(xml=xml)

    def test_wrong_spatial_count_rejected_even_if_stdout_agrees(self):
        xml = diagnostic_xml('D36'); xml.find('output/band_structure/ks_energies/npw').text = '2770'
        with self.assertRaisesRegex(ValueError, 'spatial plane-wave'):
            self.parse(xml=xml, stdout=diagnostic_stdout('D36', xml))

    def test_nan_one_of_72_cannot_pass(self):
        xml = diagnostic_xml('D36'); values = xml.find('output/band_structure/ks_energies/eigenvalues')
        tokens = values.text.split(); tokens[-1] = 'NaN'; values.text = ' '.join(tokens)
        with self.assertRaises(ValueError): self.parse(xml=xml)

    def test_malformed_stdout_or_missing_stderr_is_not_success(self):
        with self.assertRaises(QeSocParseError): self.parse(stdout='JOB DONE.')
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(QeSocParseError):
                parse_qe_soc_diagnostics(None, Path(directory)/'missing', Path(directory)/'missing2', diagnostic_case('D36'), 'D36')

    def test_warning_flags_complete_and_never_cleared_by_exit_zero(self):
        stderr = 'first line\nNote: ' + ' '.join(IEEE_FLAGS) + '\nunclassified native note\n'
        result = self.parse(stderr=stderr)
        warning = result['warning_diagnostics']
        self.assertEqual(warning['stderr_lines'], stderr.splitlines())
        self.assertTrue(all(v['reported'] and v['stderr'] and not v['stdout'] for v in warning['ieee_flags'].values()))
        self.assertEqual(warning['ieee_localization_status'], 'NOT_LOCALIZED')
        self.assertEqual(result['execution_status'], 'PASS')
        self.assertEqual(warning['ieee_warning_status'], 'REPORTED')

    def test_unconverged_warning_retained_independent_of_finite_spectrum(self):
        result = self.parse(stdout=diagnostic_stdout('D36') + '\nc_bands: 2 eigenvalues not converged\n')
        self.assertTrue(result['warning_diagnostics']['eigenvalues_not_converged'])
        self.assertEqual(result['native_solver_warning_status'], 'UNCONVERGED_WARNING')
        self.assertEqual(len(result['warning_diagnostics']['c_bands_lines']), 1)

    def test_c_bands_profile_lines_are_not_warning_evidence(self):
        output = ('     Called by c_bands:\n'
                  '     c_bands      :      0.52s CPU      0.54s WALL (       1 calls)\n'
                  '     c_bands      :      0.01s CPU      0.02s WALL (       1 call)\n'
                  '---- Real-time Memory Report at c_bands before calling an iterative solver\n')
        warning = native_warnings(output, '', 0)
        self.assertEqual(warning['warning_lines'], [])
        self.assertEqual(warning['c_bands_lines'], [])
        self.assertFalse(warning['eigenvalues_not_converged'])
        warning = native_warnings(output + '     c_bands: 2 eigenvalues not converged\n', '', 0)
        self.assertEqual(len(warning['c_bands_lines']), 1)
        self.assertEqual(warning['c_bands_lines'][0]['line'], 5)
        self.assertTrue(warning['eigenvalues_not_converged'])

    def test_absent_report_is_not_ieee_absence_certificate(self):
        record = native_warnings('', '', 0)
        self.assertEqual(record['ieee_warning_status'], 'NOT_REPORTED')
        self.assertEqual(record['ieee_localization_status'], 'NOT_LOCALIZED')
        self.assertFalse(any(v['reported'] for v in record['ieee_flags'].values()))

    def test_failed_process_not_hidden_by_valid_native_output(self):
        with self.assertRaisesRegex(ValueError, 'process'): self.parse(code=1)

    def test_fatal_native_error_cannot_be_hidden_by_exit_zero(self):
        for line in ('Error in routine c_bands (1): fatal fixture', ' %%%%%%%%%%%%%',
                     'Program received signal SIGSEGV', 'MPI_ABORT invoked', 'ERROR STOP 1'):
            with self.subTest(line=line), self.assertRaisesRegex(ValueError, 'Native fatal'):
                self.parse(stderr=line)
        warning = native_warnings('', 'Error in routine synthetic (1)', 0)
        self.assertEqual(warning['fatal_native_lines'][0]['stream'], 'stderr')

    def test_initialization_supported_build_return_codes_not_scf_success(self):
        for code in (0, 255):
            with self.subTest(code=code):
                result = self.parse('I36', code=code)
                self.assertEqual(result['numerical_solve_status'], 'NOT_RUN')
                self.assertIsNone(result['energy']); self.assertIsNone(result['kpoints'])
                self.assertEqual(result['initialization_evidence']['xml_exit_status'], 255)

    def test_initialization_requires_internal255_and_nstep0(self):
        for path, value in (('exit_status', '0'), ('input/control_variables/nstep', '1')):
            xml = diagnostic_xml('I36'); xml.find(path).text = value
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'config-init'): self.parse('I36', xml)

    def test_initialization_xml_supplies_smooth_grid_when_stdout_omits_it(self):
        output = '\n'.join(line for line in diagnostic_stdout('I36').splitlines() if not line.startswith('Smooth'))
        result = self.parse('I36', stdout=output)
        self.assertEqual(result['fft_grid'], [36]*3)
        self.assertEqual(result['fft_smooth_grid'], [36]*3)
        self.assertEqual(result['fft_control_status'], 'PASS')
        self.assertEqual(result['initialization_fft_evidence']['stdout'], {'dense': [36]*3})
        self.assertEqual(result['initialization_fft_evidence']['xml']['smooth'], [36]*3)
        self.assertEqual(result['numerical_solve_status'], 'NOT_RUN')

    def test_initialization_wrong_xml_smooth_or_disagreeing_stdout_rejected(self):
        xml = diagnostic_xml('I36')
        xml.find('output/basis_set/fft_smooth').set('nr1', '40')
        with self.assertRaisesRegex(ValueError, 'hard/smooth'): self.parse('I36', xml)
        with self.assertRaisesRegex(ValueError, 'grid differs'):
            self.parse('I36', stdout=diagnostic_stdout('I36').replace('Smooth grid: 100 G-vectors FFT dimensions: (36, 36, 36)', 'Smooth grid: 100 G-vectors FFT dimensions: (40, 40, 40)'))

    def test_initialization_refuses_scf_or_bands_numerical_markers(self):
        for marker in ('iteration # 1', 'Band Structure Calculation', 'ethr = 1.00E-13'):
            with self.subTest(marker=marker), self.assertRaisesRegex(ValueError, 'numerical-solve'):
                self.parse('I36', stdout=diagnostic_stdout('I36') + marker)

    def test_initialization_unknown_exit_not_success(self):
        with self.assertRaisesRegex(ValueError, 'Initialization process'): self.parse('I36', code=1)

    def test_initialization_nonfinite_summary_or_missing_xml_not_scf_pass(self):
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            self.parse('I36', stdout=diagnostic_stdout('I36') + '\nunit-cell volume = NaN')
        with tempfile.TemporaryDirectory() as directory:
            s, e = Path(directory)/'synthetic.stdout', Path(directory)/'synthetic.stderr'
            s.write_text(diagnostic_stdout('I36')); e.write_text('')
            with self.assertRaisesRegex(QeSocParseError, 'config-init status unavailable'):
                parse_qe_soc_diagnostics(None, s, e, diagnostic_case('I36'), 'I36', 0)


if __name__ == '__main__':
    unittest.main()
