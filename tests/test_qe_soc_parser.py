"""Synthetic parser fixtures only; no real QE, Julia, UPF or physical calculation."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from parse_qe_soc import parse_qe_soc,QeSocParseError,energy_to_ha,HARTREE_EV,QE_HARTREE_EV
from parse_qe_baseline import parse_qe


def synthetic_case():
    case=json.loads((ROOT/'benchmarks/mg-soc-qe-v1/case.json').read_text())
    case['verified_pseudo_sha256']=case['pseudo']['sha256']
    return case


def put(parent,tag,value=None,**attrs):
    node=ET.SubElement(parent,tag,attrs)
    node.text=None if value is None else str(value)
    return node


def synthetic_xml():
    """Invented numerical values; no physical pseudopotential or solver output."""
    case=synthetic_case()
    root=ET.Element('qes:espresso',{'xmlns:qes':'http://www.quantum-espresso.org/ns/qes/qes-1.0','Units':'Hartree atomic units'})
    info=put(root,'general_info');put(info,'xml_format',NAME='QEXSD',VERSION='25.05.21');put(info,'creator',NAME='PWSCF',VERSION='7.5')
    inp=put(root,'input');ctl=put(inp,'control_variables');put(ctl,'calculation','scf');put(ctl,'restart_mode','from_scratch')
    species=put(put(inp,'atomic_species'),'species',name='Mg');put(species,'starting_magnetization',0)
    spin=put(inp,'spin')
    for name,value in [('lsda','false'),('noncolin','true'),('spinorbit','true')]:put(spin,name,value)
    sym=put(inp,'symmetry_flags')
    for name in ('nosym','noinv','no_t_rev'):put(sym,name,'true')
    bands=put(inp,'bands');put(bands,'occupations','smearing');put(bands,'tot_charge',0);put(bands,'smearing','fd',degauss='.001')
    ctl=put(inp,'electron_control');put(ctl,'diago_full_acc','true')
    for name,value in [('diago_thr_init',1e-10),('conv_thr',5e-11),('max_nstep',400),('mixing_beta',.1)]:put(ctl,name,value)
    basis=put(inp,'basis');put(basis,'ecutwfc',15);put(basis,'ecutrho',60)
    step=put(root,'step');put(put(step,'total_energy'),'etot',-999)
    out=put(root,'output');scf=put(put(out,'convergence_info'),'scf_conv')
    for name,value in [('convergence_achieved','true'),('n_scf_steps',4),('scf_error',1e-12)]:put(scf,name,value)
    mag=put(out,'magnetization')
    for name,value in [('lsda','false'),('noncolin','true'),('spinorbit','true'),('do_magnetization','false'),('absolute',0)]:put(mag,name,value)
    structure=put(out,'atomic_structure',nat='1',alat='10');cell=put(structure,'cell')
    for i,row in enumerate(case['geometry']['lattice_vectors_bohr'],1):put(cell,'a'+str(i),' '.join(map(str,row)))
    atoms=put(structure,'atomic_positions');put(atoms,'atom','1.7 2.3 3.1',name='Mg')
    basis=put(out,'basis_set');rec=put(basis,'reciprocal_lattice')
    for i,row in enumerate(['1 0 0','0 1 0','0 0 1'],1):put(rec,'b'+str(i),row)
    for name in ['fft_grid','fft_smooth']:put(basis,name,nr1='32',nr2='32',nr3='32')
    put(basis,'ecutwfc',15);put(basis,'ecutrho',60)
    put(put(put(out,'atomic_species'),'species',name='Mg'),'pseudo_file','Mg.upf')
    put(put(out,'dft'),'functional','PBESOL')
    energy=put(out,'total_energy');put(energy,'etot',-20.1);put(energy,'demet',-.1)
    bands=put(out,'band_structure')
    for name,value in [('lsda','false'),('noncolin','true'),('spinorbit','true'),('occupations_kind','smearing'),('nelec',10),('nbnd',24),('nks',3),('fermi_energy',0)]:put(bands,name,value)
    put(bands,'smearing','fd',degauss='.001')
    for p in case['kpoints']:
        block=put(bands,'ks_energies');put(block,'k_point',' '.join(map(str,p['coordinate_fractional'])),weight=str(p['weight_spatial']))
        put(block,'eigenvalues',' '.join(str((i-10)*.2) for i in range(24)),size='24')
        put(block,'occupations',' '.join(map(str,[1]*10+[0]*14)),size='24');put(block,'npw',100)
    put(root,'exit_status',0);put(root,'closed')
    return root


SYNTHETIC_STDOUT='''Synthetic parser fixture, not a QE execution.
Program PWSCF v.7.5
Exchange-correlation= SLA PW PSX PSC ( 1 4 10 8 0 0 0 )
PseudoPot. # 1 for Mg read from file:
./pseudo/Mg.upf
Pseudo is Norm-conserving, Zval = 10.0
ethr = 1.00E-10
! total energy = -1998.00000000 Ry
End of self-consistent calculation
the Fermi energy is 0.000000 ev
! total energy = -40.20000000 Ry
smearing contrib. (-TS) = -0.20000000 Ry
internal energy E=F+TS = -40.00000000 Ry
convergence has been achieved in 4 iterations
JOB DONE.
'''


def synthetic_stdout_spectrum(root=None,occupations=True):
    root=synthetic_xml() if root is None else root
    lines=[]
    for block in root.findall('output/band_structure/ks_energies'):
        point=block.find('k_point');raw=[float(x) for x in point.text.split()]
        lines.append('k = '+' '.join(f'{x:.4f}' for x in raw)+' (100 PWs) bands (ev):\n')
        energies=[float(x)*QE_HARTREE_EV for x in block.find('eigenvalues').text.split()]
        lines+=[' '.join(f'{v:.4f}' for v in energies[j:j+8]) for j in range(0,24,8)]
        lines.append('')
        if occupations:
            lines.append('occupation numbers')
            f=[float(x) for x in block.find('occupations').text.split()]
            lines+=[' '.join(f'{v:.4f}' for v in f[j:j+8]) for j in range(0,24,8)]
            lines.append('')
    return '\n'.join(lines)+'\n'


SYNTHETIC_STDOUT=SYNTHETIC_STDOUT.replace('the Fermi energy',synthetic_stdout_spectrum()+'the Fermi energy')


class QeSocParserTests(unittest.TestCase):
    def parse(self,xml=None,stdout=SYNTHETIC_STDOUT,case=None,code=0,calculation='scf'):
        xml=synthetic_xml() if xml is None else xml
        case=synthetic_case() if case is None else case
        with tempfile.TemporaryDirectory() as temp:
            x=Path(temp)/'synthetic.xml';s=Path(temp)/'synthetic.stdout'
            x.write_text(ET.tostring(xml,encoding='unicode') if not isinstance(xml,str) else xml);s.write_text(stdout)
            return parse_qe_soc(x,s,case,code,calculation)

    def mutate(self,path,value):
        root=synthetic_xml();root.find(path).text=str(value);return root

    def test_valid_synthetic_soc_core_contract(self):
        d=self.parse();self.assertEqual(d['execution_status'],'PASS');self.assertEqual(d['electrons'],10)
        self.assertEqual(d['occupation_capacity'],1);self.assertEqual(d['electron_sum_normalized'],10)
        self.assertEqual(d['kpoints'][0]['occupations'],[1]*10+[0]*14)
        self.assertEqual(d['energy']['free_ha'],-20.1);self.assertEqual(d['energy']['internal_ha'],-20)
        self.assertEqual(d['energy']['entropy_ha'],-.1)

    def test_scalar_or_disabled_soc_rejected(self):
        for path,value in [('input/spin/noncolin','false'),('output/band_structure/spinorbit','false'),('output/magnetization/noncolin','false'),('input/spin/lsda','true')]:
            with self.subTest(path=path),self.assertRaisesRegex(ValueError,'SOC/noncolin'):self.parse(self.mutate(path,value))

    def test_charge_only_actual_domag_and_starting_magnetization(self):
        for path,value in [('output/magnetization/do_magnetization','true'),('output/magnetization/absolute',.01),('input/atomic_species/species/starting_magnetization',.1)]:
            with self.subTest(path=path),self.assertRaises(ValueError):self.parse(self.mutate(path,value))

    def test_documented_zero_starting_field_omission_requires_actual_domag_false(self):
        root=synthetic_xml();species=root.find('input/atomic_species/species')
        species.remove(species.find('starting_magnetization'))
        d=self.parse(root);self.assertIn('omission',d['input_model']['starting_magnetization_evidence'])
        root.find('output/magnetization/do_magnetization').text='true'
        with self.assertRaisesRegex(ValueError,'do_magnetization'):self.parse(root)

    def test_wrong_element_and_pseudo_file(self):
        for path,attr,value in [('output/atomic_structure/atomic_positions/atom','name','Si'),('output/atomic_species/species','name','Si')]:
            xml=synthetic_xml();xml.find(path).set(attr,value)
            with self.subTest(path=path),self.assertRaises(ValueError):self.parse(xml)
        with self.assertRaises(ValueError):self.parse(self.mutate('output/atomic_species/species/pseudo_file','wrong.upf'))

    def test_electron_count_eight_two_and_valence_drift(self):
        for ne in (8,2,10.00001):
            with self.subTest(ne=ne),self.assertRaisesRegex(ValueError,'electron'):self.parse(self.mutate('output/band_structure/nelec',ne))
        with self.assertRaisesRegex(ValueError,'valence10'):self.parse(stdout=SYNTHETIC_STDOUT.replace('Zval = 10.0','Zval = 8.0'))

    def test_capacity_doubling_and_weight_divide_hacks_fail(self):
        root=synthetic_xml()
        root.find('output/band_structure/ks_energies/occupations').text=' '.join(map(str,[2]*10+[0]*14))
        with self.assertRaisesRegex(ValueError,'capacity one'):self.parse(root)
        root=synthetic_xml()
        for p in root.findall('output/band_structure/ks_energies/k_point'):p.set('weight',str(2/3))
        with self.assertRaisesRegex(ValueError,'weight'):self.parse(root)
        c=synthetic_case();c['electrons']['occupation_capacity']=2
        with self.assertRaises(ValueError):self.parse(case=c)

    def test_missing_and_wrong_actual_hash_receipt(self):
        for value in (None,'0'*64):
            c=synthetic_case();c['verified_pseudo_sha256']=value
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'SHA-256'):self.parse(case=c)
        c=synthetic_case();c['pseudo']['sha256']=c['verified_pseudo_sha256']='a'*64
        with self.assertRaisesRegex(ValueError,'SHA-256'):self.parse(case=c)

    def test_xc_nlcc_and_tau_mismatch(self):
        with self.assertRaisesRegex(ValueError,'XC'):self.parse(self.mutate('output/dft/functional','PBE'))
        with self.assertRaisesRegex(ValueError,'XC'):self.parse(stdout=SYNTHETIC_STDOUT.replace('1 4 10 8','1 1 3 4'))
        with self.assertRaisesRegex(ValueError,'NLCC'):self.parse(stdout=SYNTHETIC_STDOUT.replace('Norm-conserving,','Norm-conserving + core correction,'))
        root=synthetic_xml();root.find('output/band_structure/smearing').set('degauss','.002')
        with self.assertRaisesRegex(ValueError,'tau'):self.parse(root)

    def test_reordered_kpoints_match_by_coordinates(self):
        root=synthetic_xml();bands=root.find('output/band_structure');points=bands.findall('ks_energies')
        for p in points:bands.remove(p)
        for p in points[::-1]:bands.append(p)
        d=self.parse(root);self.assertEqual(d['requested_to_xml_kpoint_indices'],[2,1,0])
        self.assertEqual(d['kpoints'][0]['coordinate_fractional'],[-.125,-.0625,.1875])

    def test_modulo_integer_points_accepted_and_duplicates_rejected(self):
        root=synthetic_xml();root.find('output/band_structure/ks_energies/k_point').text='1 0 0'
        self.assertEqual(self.parse(root)['requested_to_xml_kpoint_indices'],[0,1,2])
        root.find('output/band_structure/ks_energies/k_point').text='.125 .0625 -.1875'
        with self.assertRaisesRegex(ValueError,'Duplicate'):self.parse(root)

    def test_missing_kpoint_and_wrong_negative_partner(self):
        root=synthetic_xml();bands=root.find('output/band_structure');bands.remove(bands.findall('ks_energies')[-1])
        with self.assertRaisesRegex(ValueError,'Missing'):self.parse(root)
        root=synthetic_xml();root.findall('output/band_structure/ks_energies/k_point')[-1].text='-.125 -.0625 -.1875'
        with self.assertRaisesRegex(ValueError,'Missing'):self.parse(root)

    def test_reciprocal_alat_2pi_and_atom_coordinates(self):
        root=synthetic_xml();root.find('output/basis_set/reciprocal_lattice/b1').text='6.283185307179586 0 0'
        with self.assertRaisesRegex(ValueError,'duality'):self.parse(root)
        root=synthetic_xml();root.find('output/atomic_structure').set('alat','1')
        with self.assertRaisesRegex(ValueError,'duality'):self.parse(root)
        with self.assertRaisesRegex(ValueError,'position'):self.parse(self.mutate('output/atomic_structure/atomic_positions/atom','.17 .23 .31'))

    def test_hartree_rydberg_ev_conversion_is_explicit(self):
        self.assertEqual(energy_to_ha(2,'Ry'),1);self.assertEqual(energy_to_ha(HARTREE_EV,'eV'),1)
        self.assertEqual(energy_to_ha(1,'Ha'),1)
        with self.assertRaisesRegex(ValueError,'unit'):energy_to_ha(1,'unknown')
        root=synthetic_xml();root.set('Units','Rydberg atomic units')
        with self.assertRaisesRegex(ValueError,'units'):self.parse(root)
        with self.assertRaisesRegex(ValueError,'precision'):self.parse(self.mutate('output/total_energy/etot',-40.2))

    def test_diagonalization_xml_ry_exception_and_conv_thr_ha(self):
        d=self.parse();self.assertEqual(d['input_model']['diago_thr_init_ry'],1e-10)
        self.assertEqual(d['input_model']['conv_thr_ha'],5e-11)
        for path,value in [('input/electron_control/diago_thr_init',5e-11),('input/electron_control/conv_thr',1e-10)]:
            with self.subTest(path=path),self.assertRaisesRegex(ValueError,'electron_control'):self.parse(self.mutate(path,value))

    def test_positive_entropy_sign_and_energy_double_counting_fail(self):
        with self.assertRaisesRegex(ValueError,'sign'):self.parse(self.mutate('output/total_energy/demet',.1))
        with self.assertRaisesRegex(ValueError,'precision'):self.parse(stdout=SYNTHETIC_STDOUT.replace('-40.20000000','-40.00000000'))
        with self.assertRaisesRegex(ValueError,'precision'):self.parse(stdout=SYNTHETIC_STDOUT.replace('-0.20000000','-0.10000000'))

    def test_native_zero_entropy_retains_rounding_and_small_entropy(self):
        for demet in (0.,-1e-14):
            root=self.mutate('output/total_energy/demet',demet)
            d=self.parse(root,stdout=SYNTHETIC_STDOUT.replace('-0.20000000','0.00000000').replace('E=F+TS = -40.00000000','E=F+TS = -40.20000000'))
            self.assertEqual(d['energy']['entropy_ha'],demet)
            self.assertFalse(d['native_stdout']['entropy_energy']['displayed_zero_is_exact_zero_claim'])
            self.assertGreater(d['native_stdout']['entropy_energy']['half_last_digit'],0)

    def test_mu_platform_is_not_forced_to_homo_or_other_program(self):
        d=self.parse(self.mutate('output/band_structure/fermi_energy',.01),stdout=SYNTHETIC_STDOUT.replace('0.000000 ev',f'{.01*QE_HARTREE_EV:.6f} ev'))
        self.assertEqual(d['fermi_energy_ha'],.01)

    def test_exit_zero_job_done_without_convergence_fails(self):
        with self.assertRaisesRegex(ValueError,'convergence'):self.parse(stdout=SYNTHETIC_STDOUT.replace('convergence has been achieved','convergence NOT achieved'))
        with self.assertRaisesRegex(ValueError,'not converged'):self.parse(self.mutate('output/convergence_info/scf_conv/convergence_achieved','false'))
        with self.assertRaisesRegex(ValueError,'code zero'):self.parse(code=1)

    def test_truncated_logs_xml_missing_fields_and_schema_block(self):
        for xml,stdout in [('<qes:espresso',SYNTHETIC_STDOUT),(None,SYNTHETIC_STDOUT.replace('JOB DONE.',''))]:
            with self.subTest(xml=xml),self.assertRaises(QeSocParseError) as caught:self.parse(xml,stdout)
            self.assertEqual(caught.exception.status,'BLOCKED')
        root=synthetic_xml();root.find('general_info/xml_format').set('VERSION','999')
        with self.assertRaisesRegex(ValueError,'Unsupported'):self.parse(root)
        root=synthetic_xml();root.find('output/total_energy').remove(root.find('output/total_energy/demet'))
        with self.assertRaisesRegex(ValueError,'missing'):self.parse(root)

    def test_nonfinite_and_missing_bands_do_not_fallback(self):
        for path in ('output/total_energy/etot','output/total_energy/demet','output/band_structure/fermi_energy'):
            with self.subTest(path=path),self.assertRaisesRegex(ValueError,'nonfinite'):self.parse(self.mutate(path,'NaN'))
        for value in (' '.join(['NaN']+['0']*23),' '.join(['0']*23)):
            with self.subTest(value=value),self.assertRaises(ValueError):self.parse(self.mutate('output/band_structure/ks_energies/eigenvalues',value))

    def test_final_output_and_energy_selected_not_intermediate(self):
        self.assertEqual(self.parse()['energy']['free_ha'],-20.1)
        root=synthetic_xml();final=copy.deepcopy(root.find('output'));final.find('total_energy/etot').text='NaN';root.append(final)
        with self.assertRaisesRegex(ValueError,'nonfinite'):self.parse(root)

    def test_scf_and_nscf_never_mix_energy(self):
        with self.assertRaisesRegex(ValueError,'mismatch'):self.parse(self.mutate('input/control_variables/calculation','nscf'))
        with self.assertRaisesRegex(ValueError,'Only SCF'):self.parse(calculation='nscf')

    def test_native_precision_warning_retained_without_fake_residual(self):
        d=self.parse(stdout=SYNTHETIC_STDOUT.replace('ethr =','Threshold (ethr) on eigenvalues was too large:\nethr ='))
        self.assertEqual(d['eigenvalue_precision_status'],'WARNING_REVIEW_REQUIRED')
        self.assertEqual(len(d['warnings']),1)
        self.assertIsNone(d['precision']['individual_eigenvector_residuals_ha'])

    def test_positive_nonsymmetric_cell_converts_raw_cartesian_coordinates(self):
        case=synthetic_case();case['geometry']['lattice_vectors_bohr']=[[10.,2.,0.],[0.,10.,1.],[0.,0.,10.]]
        root=synthetic_xml();reciprocal=[[1.,0.,0.],[-.2,1.,0.],[.02,-.1,1.]]
        for i,row in enumerate(case['geometry']['lattice_vectors_bohr'],1):
            root.find('output/atomic_structure/cell/a'+str(i)).text=' '.join(map(str,row))
        for i,row in enumerate(reciprocal,1):
            root.find('output/basis_set/reciprocal_lattice/b'+str(i)).text=' '.join(map(str,row))
        root.find('output/atomic_structure/atomic_positions/atom').text='1.7 2.64 3.33'
        for node,p in zip(root.findall('output/band_structure/ks_energies/k_point'),case['kpoints']):
            frac=p['coordinate_fractional'];raw=[sum(frac[i]*reciprocal[i][j] for i in range(3)) for j in range(3)]
            node.text=' '.join(map(str,raw))
        stdout=SYNTHETIC_STDOUT.replace(synthetic_stdout_spectrum(),synthetic_stdout_spectrum(root))
        d=self.parse(root,case=case,stdout=stdout)
        self.assertNotEqual(d['kpoints'][1]['coordinate_raw'],d['kpoints'][1]['coordinate_fractional'])
        for p,q in zip(d['kpoints'],case['kpoints']):
            for x,y in zip(p['coordinate_fractional'],q['coordinate_fractional']):self.assertAlmostEqual(x,y,places=13)

    def test_zero_occupation_electron_loss_and_negative_occupation_fail(self):
        for f in ([0]*24,[-1e-5]+[1]*9+[0]*14):
            root=self.mutate('output/band_structure/ks_energies/occupations',' '.join(map(str,f)))
            with self.subTest(f=f[0]),self.assertRaisesRegex(ValueError,'capacity|miscount'):self.parse(root)

    def test_each_kpoint_needs_all_twentyfour_occupations_and_bands(self):
        for tag in ('occupations','eigenvalues'):
            for index in (0,1,2):
                root=synthetic_xml();root.findall('output/band_structure/ks_energies/'+tag)[index].text=' '.join(['0']*23)
                with self.subTest(tag=tag,index=index),self.assertRaisesRegex(ValueError,'size'):self.parse(root)
        with self.assertRaisesRegex(ValueError,'count'):self.parse(self.mutate('output/band_structure/nbnd',48))

    def test_last_stdout_nan_never_reuses_earlier_finite_energy(self):
        bad=SYNTHETIC_STDOUT.replace('! total energy = -40.20000000 Ry','! total energy = -40.20000000 Ry\n! total energy = NaN Ry')
        with self.assertRaisesRegex(ValueError,'nonfinite'):self.parse(stdout=bad)

    def test_warnings_do_not_supply_fake_scf_convergence(self):
        bad=SYNTHETIC_STDOUT.replace('convergence has been achieved in 4 iterations','warning: convergence NOT achieved')
        with self.assertRaisesRegex(ValueError,'convergence'):self.parse(stdout=bad)

    def test_declared_vector_shape_and_missing_entropy_are_not_inferred(self):
        root=synthetic_xml();root.find('output/band_structure/ks_energies/eigenvalues').set('size','48')
        with self.assertRaisesRegex(ValueError,'size'):self.parse(root)
        with self.assertRaisesRegex(ValueError,'contribution'):
            self.parse(stdout=SYNTHETIC_STDOUT.replace('smearing contrib. (-TS) = -0.20000000 Ry',''))

    def test_every_stdout_eigenvalue_crosschecked_in_ev(self):
        d=self.parse();self.assertEqual(d['precision']['stdout_spectrum_check']['matched_eigenvalues'],72)
        self.assertEqual(d['precision']['stdout_spectrum_check']['occupation_fields_checked'],72)
        wrong=SYNTHETIC_STDOUT.replace('-54.4228','-54.5228',1)
        with self.assertRaisesRegex(ValueError,'precision'):self.parse(stdout=wrong)

    def test_stdout_spectrum_duplicate_and_wrong_plane_wave_count(self):
        wrong=SYNTHETIC_STDOUT.replace('k = 0.1250 0.0625 -0.1875','k = 0.0000 0.0000 0.0000')
        with self.assertRaisesRegex(ValueError,'duplicate'):self.parse(stdout=wrong)
        with self.assertRaisesRegex(ValueError,'plane-wave'):self.parse(stdout=SYNTHETIC_STDOUT.replace('(100 PWs)','(200 PWs)',1))

    def test_native_internal_energy_cannot_add_entropy_twice(self):
        wrong=SYNTHETIC_STDOUT.replace('E=F+TS = -40.00000000','E=F+TS = -40.40000000')
        with self.assertRaisesRegex(ValueError,'precision'):self.parse(stdout=wrong)

    def bands_fixture(self):
        root=synthetic_xml();root.find('input/control_variables/calculation').text='bands'
        root.find('output/convergence_info/scf_conv/convergence_achieved').text='false'
        root.find('output/total_energy/etot').text='NaN' # Ignored stale energy, never published as new E/F.
        stdout=SYNTHETIC_STDOUT.split('End of self-consistent calculation')[0].split('! total energy')[0]
        stdout+='End of band structure calculation\n'+synthetic_stdout_spectrum(occupations=False)+'JOB DONE.\n'
        return root,stdout

    def test_bands_spectrum_cannot_publish_its_stale_energy_or_scf_status(self):
        root,stdout=self.bands_fixture();d=self.parse(root,stdout,calculation='bands')
        self.assertIsNone(d['energy']);self.assertIsNone(d['scf'])
        self.assertEqual(d['energy_semantics_status'],'NOT_APPLICABLE_SPECTRUM_ONLY')
        self.assertEqual(d['chemical_potential_source'],'INHERITED_FROM_SCF_NOT_RESOLVED')
        self.assertEqual(d['occupations_source'],'RECOMPUTED_AT_INHERITED_SCF_CHEMICAL_POTENTIAL')
        self.assertEqual(d['precision']['stdout_spectrum_check']['matched_eigenvalues'],72)

    def test_bands_optional_missing_f_and_mu_have_no_scf_fallback(self):
        root,stdout=self.bands_fixture();bands=root.find('output/band_structure')
        bands.remove(bands.find('fermi_energy'))
        for block in bands.findall('ks_energies'):block.remove(block.find('occupations'))
        d=self.parse(root,stdout,calculation='bands')
        self.assertIsNone(d['fermi_energy_ha']);self.assertIsNone(d['electron_sum_normalized'])
        self.assertEqual(d['occupation_availability'],'NOT_AVAILABLE')
        self.assertTrue(all(p['occupations'] is None for p in d['kpoints']))

    def test_scf_cannot_be_passed_as_bands_even_if_job_done(self):
        with self.assertRaisesRegex(ValueError,'boundary'):self.parse(calculation='bands')
        root,stdout=self.bands_fixture()
        with self.assertRaisesRegex(ValueError,'convergence'):self.parse(root,stdout,calculation='scf')

    def test_scalar_parser_still_rejects_soc_fixture(self):
        with tempfile.TemporaryDirectory() as temp:
            x=Path(temp)/'synthetic.xml';x.write_text(ET.tostring(synthetic_xml(),encoding='unicode'))
            with self.assertRaisesRegex(ValueError,'scalar'):
                parse_qe(x,SYNTHETIC_STDOUT,0,expected_n_kpoints=8)


if __name__=='__main__':unittest.main()
