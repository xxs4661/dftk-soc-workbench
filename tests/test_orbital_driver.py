"""Phase 7F driver protocol tests; no real WFC decode or Julia invocation.

The small accepted public XML is read as historical evidence. Coefficient
transport tests use an explicitly synthetic parser stub, never real orbitals.
"""
import argparse
import contextlib
import copy
import decimal
import io
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import run_orbital_energy_audit as driver
from orbital_evidence import load_state_metadata,write_state_metadata


class OrbitalDriverTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.plan=driver.read(ROOT/driver.PLAN)
        self.public_xml=ROOT/'results/mg-soc-qe-diagnostics/G40/qe.xml'

    def tearDown(self):
        self.temp.cleanup()

    def install_xml(self,change=None):
        """A private synthetic XML fixture derived from the documented record."""
        tree=ET.parse(self.public_xml)
        if change is not None:change(tree)
        plan=copy.deepcopy(self.plan)
        row=plan['sources']['G40']['files']['scratch/mg_soc_qe_v1.save/data-file-schema.xml']
        path=self.root/'.work/phase7b'/row['path'];path.parent.mkdir(parents=True,exist_ok=True)
        tree.write(path,encoding='utf-8',xml_declaration=True)
        row['sha256']=driver.sha(path)
        planpath=self.root/driver.PLAN;planpath.parent.mkdir(parents=True,exist_ok=True)
        driver.write(planpath,plan)
        return plan,path

    def test_public_original_xml_preserves_all_occupations_and_eigenvalue_tokens(self):
        points,a,b,receipt=driver.original_xml(ROOT,self.plan,xml_path=self.public_xml)
        bs=ET.parse(self.public_xml).find('output/band_structure')
        self.assertEqual(len(points),3)
        self.assertEqual(receipt['capacity'],1)
        for point,node,tokens in zip(points,bs.findall('ks_energies'),receipt['native_tokens']):
            f=node.findtext('occupations').split();e=node.findtext('eigenvalues').split()
            self.assertEqual(tokens['occupations'],f)
            self.assertEqual(tokens['eigenvalues_ha'],e)
            self.assertEqual(point['occupations'].tobytes(),np.array(f,dtype=np.float64).tobytes())
            self.assertEqual(point['eigenvalues'].tobytes(),np.array(e,dtype=np.float64).tobytes())
            self.assertEqual(len(point['occupations']),24)
            self.assertGreater(np.count_nonzero(point['occupations']==0),0)
        self.assertLess(np.max(abs(a.T@b/(2*math.pi)-np.eye(3))),1e-12)

    def test_original_xml_capacity_one_and_weighted_eband_arithmetic(self):
        points,_,_,receipt=driver.original_xml(ROOT,self.plan,xml_path=self.public_xml)
        electrons=math.fsum(p['weight']*float(f) for p in points for f in p['occupations'])
        eband=math.fsum(p['weight']*float(f)*float(e) for p in points for f,e in zip(p['occupations'],p['eigenvalues']))
        self.assertLessEqual(abs(electrons-10),1e-8)
        self.assertLessEqual(abs(eband-receipt['eband_ha']),1e-10+receipt['eband_print_halfwidth_ha'])
        self.assertGreater(abs(2*eband-receipt['eband_ha']),1)

    def test_token_print_interval_does_not_round_away_product_uncertainty(self):
        _,_,_,receipt=driver.original_xml(ROOT,self.plan,xml_path=self.public_xml)
        with decimal.localcontext() as context:
            context.prec=100
            D=decimal.Decimal
            half=lambda token:D(5).scaleb(D(token).as_tuple().exponent-1)
            exact=half(receipt['eband_token_ha'])
            for block in receipt['native_tokens']:
                w=abs(D(block['weight']));uw=half(block['weight'])
                for ft,et in zip(block['occupations'],block['eigenvalues_ha']):
                    f,e=abs(D(ft)),abs(D(et));uf,ue=half(ft),half(et)
                    exact+=(w+uw)*(f+uf)*(e+ue)-w*f*e
            self.assertGreaterEqual(D.from_float(receipt['eband_print_halfwidth_ha']),exact)

    def test_synthetic_tiny_occupations_and_signed_zero_are_not_resolved_again(self):
        def change(tree):
            occupations=tree.find('output/band_structure/ks_energies/occupations')
            fields=occupations.text.split();fields[-1]='4.9406564584124654e-324';fields[-2]='-0.0'
            occupations.text=' '.join(fields)
        plan,path=self.install_xml(change)
        points,_,_,_=driver.original_xml(self.root,plan)
        self.assertEqual(points[0]['occupations'][-1],np.nextafter(0.,1.))
        self.assertTrue(np.signbit(points[0]['occupations'][-2]))

    def test_source_sha_fails_before_xml_reader(self):
        plan,path=self.install_xml()
        plan['sources']['G40']['files']['scratch/mg_soc_qe_v1.save/data-file-schema.xml']['sha256']='0'*64
        with mock.patch.object(driver.ET,'parse') as reader:
            with self.assertRaisesRegex(ValueError,'SHA256'):
                driver.original_xml(self.root,plan)
            reader.assert_not_called()
        path.unlink()
        with self.assertRaises(FileNotFoundError):driver.original_xml(self.root,plan)

    def test_actual_ks_count_must_match_three_declared_slots(self):
        def change(tree):
            bs=tree.find('output/band_structure');bs.remove(bs.findall('ks_energies')[-1])
        plan,_=self.install_xml(change)
        with self.assertRaises(ValueError):driver.original_xml(self.root,plan)

    def test_wrong_original_k_slot_weight_and_capacity_are_rejected(self):
        def wrong_k(tree):tree.find('output/band_structure/ks_energies/k_point').text='0.2 0.0 0.0'
        def wrong_weight(tree):tree.find('output/band_structure/ks_energies/k_point').set('weight','0.5')
        def wrong_f(tree):
            node=tree.find('output/band_structure/ks_energies/occupations');fields=node.text.split();fields[0]='2.0';node.text=' '.join(fields)
        for change in (wrong_k,wrong_weight,wrong_f):
            with self.subTest(change=change.__name__):
                plan,_=self.install_xml(change)
                with self.assertRaises(ValueError):driver.original_xml(self.root,plan)

    def test_q_state_to_primitive_transport_is_complete_without_real_wfc_decode(self):
        def change(tree):
            for node in tree.findall('output/band_structure/ks_energies/npw'):node.text='4'
        plan,_=self.install_xml(change)
        millers=[[0,0,0],[1,0,0],[0,1,0],[0,0,1]]
        coefficients=np.array([[[complex(.01*(1+s+g+n),-.02*(s-g+n)) for n in range(24)] for g in range(4)] for s in range(2)],dtype=np.complex128)
        seen=[]
        def synthetic_parser(path,expected):
            seen.append((path,expected))
            return {'miller':copy.deepcopy(millers),'coefficients':coefficients.tolist(),
                    'source_sha256':expected['source_sha256'],'scope':'SYNTHETIC_UNNORMALIZED_FORMAT_FIXTURE'}
        with mock.patch.object(driver,'parse_wfc',side_effect=synthetic_parser):
            state=driver.q_state(self.root,plan)
        self.assertEqual([item[1]['ik'] for item in seen],[1,2,3])
        self.assertTrue(all(item[1]['npw']==4 and item[1]['nbnd']==24 for item in seen))
        self.assertEqual(state['fft_size'],[40,40,40])
        metadata=write_state_metadata(state,self.root/'synthetic-Q')
        restored=load_state_metadata(metadata,expected_sha256=driver.sha(metadata))
        for original,decoded in zip(state['kpoints'],restored['kpoints']):
            for name in ('millers','coefficients','occupations','eigenvalues','k_cart'):
                self.assertEqual(original[name].tobytes(order='C'),decoded[name].tobytes(order='C'))
        self.assertFalse(restored['raw_metadata']['normalization_applied'])

    def bound_source_fixture(self):
        run=self.plan['sources']['G40']['run_id'];directory=self.root/'.work/phase7b'/run
        directory.mkdir(parents=True,exist_ok=True);receipt=directory/'result.json'
        driver.write(receipt,dict(slot='G40',run_id=run,execution_status='PASS',exit_code=0,process_exit_code=0))
        source=self.root/'source.txt';source.write_text('SYNTHETIC SOURCE BINDING ONLY\n')
        plan={'source_sha256':{'source.txt':driver.sha(source)},'sources':{'G40':{'run_id':run}},
              'original_binding':{'files':[dict(current=str(receipt.relative_to(self.root)),sha256=driver.sha(receipt),bytes=receipt.stat().st_size)]}}
        return plan,source,receipt

    def test_source_validation_rejects_wrong_hash_missing_and_wrong_bytes(self):
        plan,source,_=self.bound_source_fixture()
        self.assertTrue(driver.validate_sources(self.root,plan))
        source.write_text('DIFFERENT SYNTHETIC SOURCE\n')
        with self.assertRaisesRegex(ValueError,'SHA256'):driver.validate_sources(self.root,plan)
        source.unlink()
        with self.assertRaises(FileNotFoundError):driver.validate_sources(self.root,plan)
        plan,_,_=self.bound_source_fixture();plan['original_binding']['files'][0]['bytes']+=1
        with self.assertRaisesRegex(ValueError,'byte count'):driver.validate_sources(self.root,plan)

    def test_original_g40_receipt_cannot_be_replaced_with_bands_or_failed_run(self):
        for key,value in [('slot','D40'),('run_id','SYNTHETIC_OTHER_RUN'),('execution_status','FAIL'),('process_exit_code',1)]:
            with self.subTest(key=key):
                plan,_,path=self.bound_source_fixture();receipt=driver.read(path);receipt[key]=value;driver.write(path,receipt)
                plan['original_binding']['files'][0].update(sha256=driver.sha(path),bytes=path.stat().st_size)
                with self.assertRaisesRegex(ValueError,'original G40 SCF'):driver.validate_sources(self.root,plan)

    def child_fixture(self,child,process_code=0):
        planpath=self.root/driver.PLAN;planpath.parent.mkdir(parents=True,exist_ok=True)
        driver.write(planpath,{'synthetic':True,'identity':{'environment':{'status':'PASS','fixture':'SYNTHETIC_CHILD_PROTOCOL_ONLY'}}})
        script=self.root/'scripts/extract_orbital_nonlocal.jl';script.parent.mkdir(parents=True,exist_ok=True);script.write_text('# synthetic worker identity only\n')
        directory=self.root/'driver';directory.mkdir(exist_ok=True)
        payload=dict(schema_version=1,phase='7F',stage='extract',execution_status='PASS',exit_code=0,
                     plan_sha256=driver.sha(planpath),source_preservation_status='PASS',environment_recheck_status='PASS',
                     environment={'status':'PASS','fixture':'SYNTHETIC_CHILD_PROTOCOL_ONLY'},executed_script_sha256=driver.sha(script))
        payload.update(child)
        def no_julia(command,**kwargs):
            out=Path(command[-1]);out.mkdir(exist_ok=True);driver.write(out/'metadata.json',payload)
            return SimpleNamespace(returncode=process_code)
        return directory,payload,no_julia

    def test_child_zero_exit_requires_consistent_full_metadata(self):
        for change in [{'execution_status':'FAIL'},{'schema_version':999},{'stage':'nonlocal'},
                       {'plan_sha256':'0'*64},{'source_preservation_status':'FAIL'},
                       {'environment_recheck_status':'FAIL'},{'exit_code':False},{'schema_version':True},
                       {'environment':None},{'environment':{'status':'FAIL'}},{'executed_script_sha256':'0'*64}]:
            with self.subTest(change=change):
                directory,_,fake=self.child_fixture(change)
                with mock.patch.object(driver,'ROOT',self.root),mock.patch.object(driver.subprocess,'run',side_effect=fake):
                    with self.assertRaises((ValueError,RuntimeError)):
                        driver.julia_stage(argparse.Namespace(julia='SYNTHETIC_NEVER_EXECUTED'),directory,'extract',{})

    def test_child_valid_metadata_and_nonzero_process_preservation(self):
        directory,payload,fake=self.child_fixture({})
        with mock.patch.object(driver,'ROOT',self.root),mock.patch.object(driver.subprocess,'run',side_effect=fake):
            self.assertEqual(driver.julia_stage(argparse.Namespace(julia='SYNTHETIC_NEVER_EXECUTED'),directory,'extract',{}),payload)
        directory,_,fake=self.child_fixture({},process_code=7)
        with mock.patch.object(driver,'ROOT',self.root),mock.patch.object(driver.subprocess,'run',side_effect=fake):
            with self.assertRaisesRegex(RuntimeError,'exit 7'):
                driver.julia_stage(argparse.Namespace(julia='SYNTHETIC_NEVER_EXECUTED'),directory,'extract',{})
        self.assertEqual(driver.read(directory/'extract-process.json')['exit_code'],7)

    def test_request_help_and_invalid_arguments_do_not_execute(self):
        for argv,code in [(['--help'],0),(['--unknown-request'],2)]:
            with self.subTest(argv=argv),mock.patch.object(driver,'execute') as execute:
                with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as caught:driver.main(argv)
                self.assertEqual(caught.exception.code,code);execute.assert_not_called()

    def test_existing_result_refused_without_running_callback(self):
        directory=self.root/'old-run';directory.mkdir();old=b'{"execution_status":"PASS","historical":true}\n'
        (directory/'result.json').write_bytes(old);callback=mock.Mock(side_effect=AssertionError('Must not run'))
        with contextlib.redirect_stdout(io.StringIO()):code=driver.recorded_run(directory,callback,run_id='synthetic-existing')
        self.assertEqual(code,2);callback.assert_not_called();self.assertEqual((directory/'result.json').read_bytes(),old)


if __name__=='__main__':unittest.main()
