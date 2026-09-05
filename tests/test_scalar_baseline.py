"""Synthetic comparison/protocol fixtures only; not QE or DFTK SCF evidence."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import compare_scalar_baseline as comparison
import run_scalar_baseline as runner


def case_fixture():
    return json.loads((ROOT/'benchmarks/si-sr-lda/case.json').read_text())


def result_fixture(case, engine):
    # Deliberately artificial eigenvalues: this tests formulas, never physics.
    kpoints=[]
    for index, point in enumerate(case['kpoints']):
        values=[-1.0+0.1*band+0.01*index+(0.5 if band>=4 else 0) for band in range(8)]
        kpoints.append(dict(point,eigenvalues_ha=values,occupations=[2]*4+[0]*4,
                            occupations_raw=([1]*4+[0]*4 if engine=='QE' else [2]*4+[0]*4),
                            weight_raw=(.25 if engine=='QE' else .125),npw=100))
    result={'schema_version':1,'code':engine,'execution_status':'PASS','converged':True,'exit_code':0,
            'pseudo_sha256':case['pseudo']['sha256'],'n_bands':8,'n_electrons':8,'ecut_ha':30,
            'lattice_vectors_bohr':case['geometry']['lattice_vectors_bohr'],
            'positions_fractional':case['geometry']['positions_fractional'],
            'atom_symbols':['Si','Si'],'kpoints':kpoints,'energy_ha':-10.0,
            'energy_raw':{'value':-10.0,'unit':'Ha'},'fft_grid':[20,20,20]}
    if engine=='DFTK':
        result.update(xc_raw=case['xc']['dftk_identifiers'],pseudo={'nlcc':True},
                      xc_backend={'core_density_present':True},environment={'status':'PASS'},
                      diagonalization={'converged':True},input_settings={
                          'spin_polarization':'none','temperature_ha':0,'symmetry_operations':1})
    else:
        result.update(xc_indices=[1,4,0,0],nlcc=True,ecutrho_ha=120,input_model={
            'nspin':1,'lsda':False,'noncolin':False,'spinorbit':False,'occupations':'fixed',
            'nosym':True,'noinv':True,'diago_full_acc':True})
    return result


class ScalarBaselineTests(unittest.TestCase):
    def test_unit_conversion_direction(self):
        self.assertEqual(comparison.energy_to_ha(60,'Ry'),30)
        self.assertAlmostEqual(comparison.energy_to_ha(comparison.HARTREE_EV,'eV'),1)
        self.assertEqual(comparison.energy_to_ha(-12,'Ha'),-12)
        self.assertEqual(comparison.energy_to_ha(-8,'Ry'),-4)
        for invalid in (float('nan'),float('inf')):
            with self.assertRaises(ValueError):
                comparison.energy_to_ha(invalid,'Ha')

    def test_nonsymmetric_cell_is_transposed_only_for_dftk(self):
        vectors=[[2,1,0],[0,3,1],[1,0,4]]
        expected=[[2,0,1],[1,3,0],[0,1,4]]
        self.assertEqual(comparison.lattice_columns(vectors),expected)
        self.assertEqual(comparison.volume(vectors),25)
        self.assertEqual(comparison.volume(expected),25)
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            case=case_fixture(); case['geometry']['lattice_vectors_bohr']=vectors
            source=directory/'source.json'; source.write_text(json.dumps(case))
            output=directory/'paired'; output.mkdir()
            runner.make_inputs(source,output)
            dftk=json.loads((output/'dftk-input.json').read_text())
            self.assertEqual(dftk['lattice_matrix_bohr'],expected)
            self.assertIn('CELL_PARAMETERS bohr\n2 1 0\n0 3 1\n1 0 4\n',(output/'qe.in').read_text())

    def test_generated_input_records_exact_source_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)
            source=ROOT/'benchmarks/si-sr-lda/case.json'
            case,identity=runner.make_inputs(source,output)
            self.assertEqual(identity['case_sha256'],runner.sha256(source))
            self.assertEqual(json.loads((output/'dftk-input.json').read_text())['source_case_sha256'],identity['case_sha256'])
            qe=(output/'qe.in').read_text()
            self.assertNotIn('input_dft',qe)
            self.assertIn('K_POINTS crystal\n8\n',qe)
            self.assertIn("occupations='fixed'",qe)
            self.assertAlmostEqual(identity['volume_bohr3'],10.26**3/4)

    def test_kpoint_reordering_is_matched_by_coordinate(self):
        case=case_fixture()
        points=result_fixture(case,'DFTK')['kpoints']
        reordered=list(reversed(points))
        self.assertEqual(comparison.match_kpoints(case['kpoints'],reordered),points)

    def test_kpoint_integer_reciprocal_equivalence(self):
        case=case_fixture(); points=result_fixture(case,'DFTK')['kpoints']
        for p in points:
            p['coordinate_fractional']=[x+1 for x in p['coordinate_fractional']]
        self.assertEqual(len(comparison.match_kpoints(case['kpoints'],points)),8)

    def test_missing_duplicate_and_wrong_kpoints_rejected(self):
        case=case_fixture(); points=result_fixture(case,'DFTK')['kpoints']
        for bad in (points[:-1],points[:-1]+[points[0]]):
            with self.assertRaises(ValueError):
                comparison.match_kpoints(case['kpoints'],bad)
        bad=copy.deepcopy(points); bad[0]['coordinate_fractional']=[.123,0,0]
        with self.assertRaises(ValueError):
            comparison.match_kpoints(case['kpoints'],bad)

    def test_space_weights_and_spin_occupation_count(self):
        case=case_fixture(); d=result_fixture(case,'DFTK'); q=result_fixture(case,'QE')
        self.assertEqual(sum(p['weight_spatial']*sum(p['occupations']) for p in d['kpoints']),8)
        self.assertEqual(sum(p['weight_raw']*sum(p['occupations_raw']) for p in q['kpoints']),8)
        comparison.compare(case,d,q)
        q['kpoints'][0]['weight_spatial']=.25
        with self.assertRaises(ValueError):
            comparison.compare(case,d,q)

    def test_no_scf_convergence_despite_zero_exit_is_rejected(self):
        case=case_fixture(); d=result_fixture(case,'DFTK'); q=result_fixture(case,'QE')
        d['converged']=False
        with self.assertRaises(ValueError):
            comparison.compare(case,d,q)

    def test_missing_bands_nan_and_nonfixed_occupations_rejected(self):
        case=case_fixture(); d=result_fixture(case,'DFTK')
        for field,value in [('eigenvalues_ha',[0]),('eigenvalues_ha',[float('nan')]*8),('occupations',[1]*8)]:
            q=result_fixture(case,'QE'); q['kpoints'][0][field]=value
            with self.assertRaises(ValueError):
                comparison.compare(case,d,q)

    def test_checksum_mismatch_blocks_comparison_and_input_read(self):
        case=case_fixture(); d=result_fixture(case,'DFTK'); q=result_fixture(case,'QE')
        q['pseudo_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'checksum'):
            comparison.compare(case,d,q)
        with tempfile.TemporaryDirectory() as temp:
            invalid=Path(temp)/'synthetic-checksum-only.txt'
            invalid.write_text('Not a pseudopotential; checksum-failure fixture only')
            with self.assertRaisesRegex(ValueError,'checksum'):
                runner.check_pseudo(invalid,case)

    def test_xc_nlcc_and_geometry_mismatch_cannot_look_comparable(self):
        case=case_fixture(); d=result_fixture(case,'DFTK')
        for field,value in [('xc_indices',[1,1,0,0]),('nlcc',False),('positions_fractional',[[0,0,0],[.3,.3,.3]])]:
            q=result_fixture(case,'QE'); q[field]=value
            with self.assertRaises(ValueError):
                comparison.compare(case,d,q)

    def test_single_global_reference_retains_relative_kpoint_offsets(self):
        case=case_fixture(); d=result_fixture(case,'DFTK'); q=result_fixture(case,'QE')
        for i,p in enumerate(d['kpoints']):
            p['eigenvalues_ha']=[value+.2+.01*i for value in p['eigenvalues_ha']]
        d['energy_ha']=-9.5
        d['energy_raw']['value']=-9.5
        result=comparison.compare(case,d,q)
        reference=result['global_reference_delta_ha']
        self.assertAlmostEqual(reference,.27)
        self.assertAlmostEqual(result['eigenvalues'][0]['global_reference_delta_ha'],-.07)
        for row in result['eigenvalues']:
            self.assertAlmostEqual(row['global_reference_delta_ha'],row['delta_ha']-reference)
        self.assertEqual(result['total_energy']['delta_DFTK_minus_QE']['ha_cell'],.5)
        self.assertEqual(result['numerical_agreement_status'],'REVIEW_REQUIRED')
        self.assertEqual(result['convergence_study_status'],'NOT_RUN')

    def test_constant_spectrum_offset_does_not_shift_total_energy(self):
        case=case_fixture(); d=result_fixture(case,'DFTK'); q=result_fixture(case,'QE')
        for p in d['kpoints']:
            p['eigenvalues_ha']=[x+.25 for x in p['eigenvalues_ha']]
        d['energy_ha']=-9
        d['energy_raw']['value']=-9
        result=comparison.compare(case,d,q)
        self.assertAlmostEqual(result['eigenvalue_summary']['all']['raw']['max_abs_ha'],.25)
        self.assertLess(result['eigenvalue_summary']['all']['global_reference']['max_abs_ha'],1e-15)
        self.assertEqual(result['total_energy']['delta_DFTK_minus_QE']['ha_cell'],1)

    def test_inconsistent_case_xc_mapping_is_rejected(self):
        case=case_fixture(); case['xc']['dftk_identifiers']=['lda_x','lda_c_pz']
        with self.assertRaisesRegex(ValueError,'XC mapping'):
            comparison.compare(case,result_fixture(case,'DFTK'),result_fixture(case,'QE'))

    def test_raw_and_normalized_energy_must_agree(self):
        case=case_fixture(); d=result_fixture(case,'DFTK'); q=result_fixture(case,'QE')
        q['energy_raw']={'value':-10,'unit':'Ry'}
        with self.assertRaisesRegex(ValueError,'Raw/normalized'):
            comparison.compare(case,d,q)

    def test_global_band_overlap_breaks_fixed_occupation_model(self):
        case=case_fixture(); d=result_fixture(case,'DFTK'); q=result_fixture(case,'QE')
        d['kpoints'][0]['eigenvalues_ha']=[x+10 for x in d['kpoints'][0]['eigenvalues_ha']]
        with self.assertRaisesRegex(ValueError,'zero-temperature'):
            comparison.compare(case,d,q)

    def test_qe_higher_order_xc_indices_must_be_zero(self):
        case=case_fixture(); d=result_fixture(case,'DFTK'); q=result_fixture(case,'QE')
        q['xc_indices']=[1,4,0,0,0,0,0]
        comparison.compare(case,d,q)
        q['xc_indices'][-1]=1
        with self.assertRaisesRegex(ValueError,'parametrization'):
            comparison.compare(case,d,q)

    def test_failed_new_run_never_uses_old_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); old=root/'.work/scalar-baseline/old'
            old.mkdir(parents=True)
            history=old/'result.json'; history.write_text('{"execution_status":"PASS"}\n')
            before=history.read_bytes()
            # Only missing configuration is exercised; no Julia or QE can start.
            with patch.object(runner,'ROOT',root), contextlib.redirect_stdout(io.StringIO()):
                code=runner.run_case(root/'missing-case.json')
            self.assertNotEqual(code,0)
            self.assertEqual(history.read_bytes(),before)
            new=[p for p in (root/'.work/scalar-baseline').iterdir() if p!=old]
            self.assertEqual(len(new),1)
            data=json.loads((new[0]/'result.json').read_text())
            self.assertNotEqual(data['execution_status'],'PASS')
            self.assertNotEqual(data['exit_code'],0)
            self.assertEqual(data['commands'],[])


if __name__=='__main__':
    unittest.main()
