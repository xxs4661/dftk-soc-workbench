"""Synthetic energy records test bookkeeping only, never a physical calculation."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_energy_ledger import (assert_same_density_state, derived_row, endpoint_block,
    check_source_bindings, interval_check, interval_combination, parse_qe_energy, require_operator_measurement,
    signed_ledger, token_measurement)


def synthetic_stdout():
    return '''Program PWSCF v.7.5
 iteration # 1
 total energy = -80.00000000 Ry
 End of self-consistent calculation
! total energy = -8.30000000 Ry
 smearing contrib. (-TS) = -0.05000000 Ry
 internal energy E=F+TS = -8.25000000 Ry
 The total energy is F=E-TS. E is the sum of the following terms:
 one-electron contribution = -4.25000000 Ry
 hartree contribution = 4.00000000 Ry
 xc contribution = -2.00000000 Ry
 ewald contribution = -6.00000000 Ry
 convergence has been achieved in 2 iterations
 JOB DONE.
'''


def synthetic_xml():
    return '''<espresso Units="Hartree atomic units">
 <input><control_variables><calculation>scf</calculation><fcp>false</fcp><rism>false</rism></control_variables>
 <bands><tot_charge>0.0</tot_charge></bands><dft><functional>PBESOL</functional></dft></input>
 <output><convergence_info><scf_conv><convergence_achieved>true</convergence_achieved></scf_conv></convergence_info>
 <magnetization><do_magnetization>false</do_magnetization></magnetization>
 <total_energy>
 <etot>-4.150000000000000E+000</etot>
 <demet>-2.500000000000000E-002</demet>
 <ehart>2.000000000000000E+000</ehart>
 <etxc>-1.000000000000000E+000</etxc>
 <ewald>-3.000000000000000E+000</ewald>
 <eband>5.200000000000000E+000</eband>
 <vtxc>-1.800000000000000E+000</vtxc>
 </total_energy></output><exit_status>0</exit_status></espresso>'''


class TokenTests(unittest.TestCase):
    def test_ry_to_ha_and_f_entropy_sign(self):
        parsed = parse_qe_energy(synthetic_xml(),synthetic_stdout())
        self.assertAlmostEqual(parsed['E']['value_ha'],-4.125)
        self.assertAlmostEqual(parsed['native']['etot']['value_ha'],-4.15)
        self.assertAlmostEqual(parsed['native']['demet']['value_ha'],-.025)
        self.assertTrue(all(x['status']=='PASS' for x in parsed['stdout_crosschecks'].values()))

    def test_nonzero_entropy_opposite_sign_fails(self):
        parsed = parse_qe_energy(synthetic_xml().replace('-2.500000000000000E-002','2.500000000000000E-002'),synthetic_stdout())
        self.assertEqual(parsed['stdout_crosschecks']['minus_TS']['status'],'FAIL')
        self.assertEqual(parsed['stdout_crosschecks']['E_printed']['status'],'FAIL')

    def test_print_precision_decimal_and_exponent(self):
        row=token_measurement('-12.34567890','Ry')
        self.assertEqual(row['value_ha'],-6.17283945)
        self.assertEqual(row['quantization_half_width_ha'],2.5e-9)
        exponent=token_measurement('1.234D-03','Ha')
        self.assertEqual(exponent['quantization_half_width_ha'],5e-7)

    def test_printed_zero_not_exact_zero(self):
        row=token_measurement('0.00000000','Ry')
        self.assertEqual(row['quantization_interval_ha'],[-2.5e-9,2.5e-9])
        self.assertFalse(row['displayed_zero_is_exact_zero_claim'])

    def test_json_precision_is_recorded_token_not_print_uncertainty(self):
        row=token_measurement('1.0','Ha',printed=False)
        self.assertEqual(row['quantization_half_width_ha'],0.0)

    def test_token_intervals_propagate_absolute_coefficients(self):
        a,b=token_measurement('2.00000000','Ry'),token_measurement('0.1000','Ha')
        combo=interval_combination([a,b],[1,-2])
        self.assertEqual(combo['value_ha'],.8)
        self.assertEqual(combo['quantization_half_width_ha'],2.5e-9+1e-4)

    def test_interval_bound_does_not_use_widest_unrelated_token(self):
        a=token_measurement('2.00000000','Ry')
        fine=token_measurement('1.000000004','Ha')
        self.assertEqual(interval_check(a,fine)['status'],'FAIL')
        near=token_measurement('1.000000002','Ha')
        self.assertEqual(interval_check(a,near)['status'],'PASS')

    def test_invalid_units_and_nonfinite_tokens(self):
        for token,unit in [('NaN','Ha'),('Inf','Ry'),('1e999','Ha'),('1.0','eV')]:
            with self.subTest(token=token,unit=unit), self.assertRaises(ValueError):
                token_measurement(token,unit)


class EndpointTests(unittest.TestCase):
    def test_endpoint_not_earlier_iteration(self):
        block=endpoint_block(synthetic_stdout())
        self.assertEqual(block['fields']['F']['value_ha'],-4.15)
        self.assertEqual(block['start_line'],5)

    def test_last_complete_block_selected(self):
        stdout=synthetic_stdout().replace(' JOB DONE.','')+synthetic_stdout()
        block=endpoint_block(stdout)
        self.assertGreater(block['start_line'],15)

    def test_no_fallback_to_good_earlier_block(self):
        for tail in ['\nProgram PWSCF v.7.5\n', '\n iteration # 1\n',
                     '\n! total energy = NaN Ry\n','\n End of self-consistent calculation\n',
                     '\n convergence NOT achieved\n']:
            with self.subTest(tail=tail),self.assertRaises(ValueError):
                endpoint_block(synthetic_stdout()+tail)

    def test_missing_or_duplicate_component_rejected(self):
        for value in [synthetic_stdout().replace(' xc contribution = -2.00000000 Ry\n',''),
                      synthetic_stdout().replace(' xc contribution = -2.00000000 Ry\n',
                          ' xc contribution = -2.00000000 Ry\n xc contribution = -2.00000000 Ry\n')]:
            with self.assertRaises(ValueError): endpoint_block(value)

    def test_extra_energy_component_rejected(self):
        text=synthetic_stdout().replace(' convergence has',' Hubbard contribution = 0.10000000 Ry\n convergence has')
        with self.assertRaises(ValueError): endpoint_block(text)

    def test_final_token_unit_or_nan_never_falls_back(self):
        for token in ['NaN Ry','-2.00000000 Ha']:
            with self.assertRaises(ValueError):
                endpoint_block(synthetic_stdout().replace('-2.00000000 Ry',token))

    def test_xml_bands_failed_scf_wrong_units_rejected(self):
        for a,b in [('<calculation>scf','<calculation>bands'),('Hartree atomic units','Rydberg atomic units'),
                    ('<exit_status>0','<exit_status>1'),('<convergence_achieved>true','<convergence_achieved>false')]:
            with self.subTest(replacement=b),self.assertRaises(ValueError):
                parse_qe_energy(synthetic_xml().replace(a,b),synthetic_stdout())

    def test_extra_xml_energy_or_dft_field_rejected(self):
        for a,b in [('</total_energy>','<extra>0</extra></total_energy>'),
                    ('</dft>','<dftU>true</dftU></dft>')]:
            with self.assertRaises(ValueError): parse_qe_energy(synthetic_xml().replace(a,b),synthetic_stdout())


class LedgerTests(unittest.TestCase):
    def test_missing_original_source_refuses_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(FileNotFoundError):
                check_source_bindings(Path(temp),{'source_sha256':{'missing.json':'0'*64},'source_bytes':{'missing.json':1}})

    def test_source_byte_mutation_refuses_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'synthetic.json').write_bytes(b'{}')
            plan={'source_sha256':{'synthetic.json':hashlib.sha256(b'{}').hexdigest()},'source_bytes':{'synthetic.json':2}}
            check_source_bindings(root,plan)
            (root/'synthetic.json').write_bytes(b'[]')
            with self.assertRaisesRegex(ValueError,'differs from plan'): check_source_bindings(root,plan)

    def test_eband_is_not_one_electron(self):
        p=parse_qe_energy(synthetic_xml(),synthetic_stdout())
        self.assertEqual(p['O']['value_ha'],-2.125)
        self.assertNotEqual(p['native']['eband']['value_ha'],p['O']['value_ha'])
        bad=copy.deepcopy(p['native']['eband'])
        printed=next(x for x in p['rows'] if x['id']=='G40.stdout.O_printed')
        self.assertEqual(interval_check(bad,printed)['status'],'FAIL')

    def test_derived_cannot_be_measured_operator(self):
        row=parse_qe_energy(synthetic_xml(),synthetic_stdout())['O']
        self.assertIsNone(row['raw_token'])
        self.assertEqual(row['record_kind'],'DERIVED_COMBINATION')
        self.assertEqual(row['operator_measurement_status'],'NOT_A_DIRECT_OPERATOR_MEASUREMENT')
        with self.assertRaisesRegex(ValueError,'not a directly measured'): require_operator_measurement(row)

    def test_old_hamiltonian_state_cannot_replace_final_potential(self):
        p=parse_qe_energy(synthetic_xml(),synthetic_stdout())
        with self.assertRaisesRegex(ValueError,'Different input/output'):
            assert_same_density_state(p['native']['eband'],p['native']['vtxc'])
        self.assertEqual(p['cross_stage_diagnostic']['status'],'NOT_A_SAME_STATE_IDENTITY')
        self.assertGreater(abs(p['cross_stage_diagnostic']['O_ledger_minus_eband_minus_2H_minus_vtxc_ha']),1)
        self.assertTrue(all(c['status']=='PASS' for c in p['stdout_crosschecks'].values()))

    def test_signed_hartree_cancellation(self):
        d={'E':10.,'terms':dict(zip(('Kinetic','AtomicLocal','AtomicNonlocalFR','Hartree','Xc','Ewald','PspCorrection'),
                                  [4.,-2.,1.,3.,2.,1.,1.]))}
        q={'E':9.,'H':5.,'XC':1.,'Ew':1.,'O':2.}
        result=signed_ledger(d,q)
        self.assertEqual(result['delta_ha'],{'E':1.,'H':-2.,'XC':1.,'Ew':0.,'O':2.})
        self.assertEqual(result['R_after_H_ha'],3.)
        self.assertEqual(result['R_after_H_XC_Ew_ha'],2.)
        self.assertEqual(result['signed_closure_error_ha'],0.)

    def test_wrong_qe_one_electron_breaks_signed_closure(self):
        d={'E':7.,'terms':{k:1. for k in ('Kinetic','AtomicLocal','AtomicNonlocalFR','Hartree','Xc','Ewald','PspCorrection')}}
        with self.assertRaisesRegex(ValueError,'does not close'):
            signed_ledger(d,{'E':8.,'H':1.,'XC':1.,'Ew':1.,'O':11.})

    def test_dictionary_source_locations_tokens_and_hashes(self):
        p=parse_qe_energy(synthetic_xml(),synthetic_stdout())
        for row in p['rows']:
            if row['raw_token'] is not None:
                self.assertEqual(len(row['source']['sha256']),64)
                self.assertIsInstance(row['source']['line'],int)
                self.assertIn('quantization_interval_ha',row)
        self.assertEqual(p['native']['demet']['raw_token'],'-2.500000000000000E-002')


if __name__ == '__main__':
    unittest.main()
