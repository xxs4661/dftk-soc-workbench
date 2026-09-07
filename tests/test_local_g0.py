"""Synthetic finite-domain integrands only; these are not physical UPF files.

Exact polynomial, gauge and index-Jacobian identities use absolute tolerance
1e-11 (also the stated relative tolerance for nonzero references). A final
unpaired trapezoid's known truncation term is tested explicitly, not labelled
as exact quadratic integration. No Mg integration or native package is run.
"""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SPEC=importlib.util.spec_from_file_location('audit_local_g0',Path(__file__).resolve().parents[1]/'scripts/audit_local_g0.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)
EPS=1e-11


class RadialMathTests(unittest.TestCase):
    def test_nonuniform_quadratic_analytic_odd_nodes(self):
        r=[0,.07,.31,.9,1.7]; y=[2-3*x+.4*x*x for x in r]
        upper=r[-1]; exact=2*upper-1.5*upper**2+.4*upper**3/3
        self.assertAlmostEqual(M.integrate_nonuniform_quadratic(r,y),exact,delta=EPS)
        # Blind equal-index Simpson omits actual nonuniform interval geometry.
        wrong=M.integrate_index_simpson(y,[1]*len(y))
        self.assertGreater(abs(wrong-exact),.1)

    def test_final_unmatched_interval_has_declared_trapezoid(self):
        r=[0,.1,.4,1.];y=[.3*x*x for x in r]
        exact=.1;last_h=.6
        expected_error=.3*last_h**3/6
        self.assertAlmostEqual(M.integrate_nonuniform_quadratic(r,y)-exact,expected_error,delta=EPS)
        self.assertAlmostEqual(M.integrate_nonuniform_quadratic(r,[2*x+3 for x in r]),4.,delta=EPS)

    def test_trapezoid_linear_exact_and_quadratic_error(self):
        r=[0,.1,.4,1.]
        self.assertAlmostEqual(M.integrate_trapezoid(r,[2*x+3 for x in r]),4,delta=EPS)
        error=sum((b-a)**3/6 for a,b in zip(r,r[1:]))
        self.assertAlmostEqual(M.integrate_trapezoid(r,[x*x for x in r])-1/3,error,delta=EPS)

    def test_rab_once_on_nonuniform_coordinate_mapping(self):
        # r=t^2, t=1..5 has dr/di=2t. f(r)=r gives transformed 2t^3,
        # so closed Simpson in index coordinates is exactly integrable.
        t=[1,2,3,4,5];r=[x*x for x in t];rab=[2*x for x in t]
        expected=(r[-1]**2-r[0]**2)/2
        self.assertAlmostEqual(M.integrate_index_simpson(r,rab),expected,delta=EPS)
        self.assertAlmostEqual(M.integrate_nonuniform_quadratic(r,r),expected,delta=EPS)
        missing=M.integrate_index_simpson(r,[1]*len(r))
        doubled=M.integrate_index_simpson([v*j for v,j in zip(r,rab)],rab)
        self.assertGreater(abs(missing-expected),100)
        self.assertGreater(abs(doubled-expected),100)

    def test_Ry_to_Ha_and_finite_integrand_origin(self):
        r=[0,.07,.31,.9,1.7];z=3;vry=[4]*len(r)
        x,vha,f=M.finite_integrand(r,vry,z)
        self.assertEqual(vha,[2]*len(r));self.assertEqual(f[0],0)
        for ri,fi in zip(r,f):self.assertAlmostEqual(fi,2*ri*ri+z*ri,delta=EPS)
        exact=4*math.pi*(2*r[-1]**3/3+z*r[-1]**2/2)
        actual=4*math.pi*M.integrate_nonuniform_quadratic(x,f)
        self.assertAlmostEqual(actual,exact,delta=EPS)
        wrong=4*math.pi*M.integrate_nonuniform_quadratic(r,[4*ri*ri+z*ri for ri in r])
        self.assertGreater(abs(wrong-exact),1)

    def test_atoms_volume_electrons_are_separate_factors(self):
        one=M.reference_factors(2,1,100,3,3)
        two=M.reference_factors(2,2,100,6,3)
        big=M.reference_factors(2,2,200,6,3)
        self.assertAlmostEqual(one['C_ha'],.02,delta=EPS)
        self.assertAlmostEqual(one['Pc_neutral_candidate_ha'],.06,delta=EPS)
        self.assertAlmostEqual(two['C_ha'],2*one['C_ha'],delta=EPS)
        self.assertAlmostEqual(two['Pc_neutral_candidate_ha'],4*one['Pc_neutral_candidate_ha'],delta=EPS)
        self.assertAlmostEqual(big['Pc_neutral_candidate_ha'],two['Pc_neutral_candidate_ha']/2,delta=EPS)
        with self.assertRaises(ValueError):M.reference_factors(2,2,100,3,3)

    def test_invalid_arrays_and_index_endpoint_policy_rejected(self):
        for r,y in [([0,1,1],[1,2,3]),([0,2,1],[1,2,3]),([-1,0,1],[1,2,3]),([0,1,2],[1,math.nan,3]),([0,1],[1,2])]:
            with self.assertRaises(ValueError):M.integrate_nonuniform_quadratic(r,y)
        with self.assertRaises(ValueError):M.integrate_index_simpson([1]*4,[1]*4)
        with self.assertRaises(ValueError):M.integrate_index_simpson([1]*3,[0,1,1])

    def test_full_grid_rule_does_not_consume_RAB(self):
        r=[0,.07,.31,.9,1.7];v=[4]*5
        normal=M.analyze_local_reference(r,v,[.1]*5,3,n_atoms=1,volume_bohr3=100,n_electrons=3)
        different=M.analyze_local_reference(r,v,[.7]*5,3,n_atoms=1,volume_bohr3=100,n_electrons=3)
        self.assertEqual(normal['primary_full_native_grid'],different['primary_full_native_grid'])
        self.assertFalse(normal['primary_full_native_grid']['rab_used'])
        self.assertFalse(normal['trapezoid_full_native_grid']['rab_used'])
        self.assertEqual(normal['qe_tagged_prediction']['status'],'NOT_ESTABLISHED')


class TaggedRangeAndBookkeepingTests(unittest.TestCase):
    def test_tagged_radial_endpoint_and_Jacobian_proof(self):
        # Synthetic affine metadata, not real Mg values or a UPF file.
        r=[i*.01 for i in range(1510)];rab=[.01]*1510
        proof=M.qe_tagged_range(r,rab,ordinary_periodic=True)
        self.assertEqual(proof['msh_points'],1001)
        self.assertEqual(proof['first_index_beyond_10_bohr'],1002)
        self.assertEqual(proof['integration_upper_bohr'],10.)
        self.assertEqual(proof['source_point_count'],1510)
        self.assertEqual(M.qe_tagged_range(r,rab,ordinary_periodic=None)['status'],'NOT_ESTABLISHED')

    def test_wrong_or_unproved_Jacobian_is_not_guessed(self):
        r=[i*.01 for i in range(1510)]
        wrong=M.qe_tagged_range(r,[.0001]*1510,ordinary_periodic=True)
        self.assertEqual(wrong['status'],'NOT_ESTABLISHED')
        r2=[float(i*i) for i in range(5)]
        self.assertEqual(M.qe_tagged_range(r2,[1,2,4,6,8],ordinary_periodic=True)['status'],'NOT_ESTABLISHED')

    def test_tagged_integral_and_full_mesh_have_separate_ranges(self):
        # Constant finite-domain potential, no physical/Coulomb-tail claim.
        r=[float(i) for i in range(15)];vry=[0]*15;rab=[1]*15
        result=M.analyze_local_reference(r,vry,rab,2,n_atoms=1,volume_bohr3=100,n_electrons=2,ordinary_periodic=True)
        self.assertEqual(result['primary_full_native_grid']['integration_upper_bohr'],14)
        self.assertEqual(result['qe_tagged_prediction']['range_proof']['integration_upper_bohr'],10)
        self.assertAlmostEqual(result['primary_full_native_grid']['alpha_ha_bohr3_per_atom'],4*math.pi*14**2,delta=EPS)
        self.assertAlmostEqual(result['qe_tagged_prediction']['alpha_ha_bohr3_per_atom'],4*math.pi*10**2,delta=EPS)
        self.assertEqual(result['qe_native_local_potential_status'],'NOT_EXTRACTED')
        self.assertFalse(result['applied_energy_correction'])

    def test_unscreened_finite_alpha_is_not_screened_zero_entry(self):
        # Independent exact integral: integral_0^R r erfc(r) dr =
        # R² erfc(R)/2 + erf(R)/4 - R exp(-R²)/(2 sqrt(pi)).
        radius=8.;z=3.
        integral=radius**2*math.erfc(radius)/2+math.erf(radius)/4-radius*math.exp(-radius**2)/(2*math.sqrt(math.pi))
        self.assertAlmostEqual(4*math.pi*z*integral,math.pi*z,delta=EPS)
        finite_alpha=5.;screened=finite_alpha-math.pi*z
        self.assertGreater(abs(finite_alpha-screened),1)
        # Substitution would spuriously change Pc although neither is fitted.
        correct=M.reference_factors(finite_alpha,1,1000,3,3)
        wrong=M.reference_factors(screened,1,1000,3,3)
        self.assertAlmostEqual(correct['Pc_neutral_candidate_ha']-wrong['Pc_neutral_candidate_ha'],3*math.pi*z/1000,delta=EPS)

    def test_gauge_constant_local_integral_and_compensating_Pc(self):
        density=[.02,.03,.04,.01];potential=[-2,1,-1,4];dvol=100
        ne=dvol*sum(density);shift=.3
        local=dvol*sum(n*v for n,v in zip(density,potential));pc=.7
        shifted=dvol*sum(n*(v+shift) for n,v in zip(density,potential))
        self.assertAlmostEqual(shifted-local,ne*shift,delta=EPS)
        audit=M.gauge_bookkeeping(local,pc,ne,shift)
        self.assertAlmostEqual(audit['local_after_ha'],shifted,delta=EPS)
        self.assertAlmostEqual(audit['combined_before_ha'],audit['combined_after_ha'],delta=EPS)
        self.assertGreater(abs((shifted+pc+ne*shift)-(local+pc)),1)

    def test_actual_native_constant_receipt_identity_and_failures(self):
        r=[0,.1,.4,.7,1.];vry=[0]*5;alpha=4*math.pi
        constants={'psp_correction_ha':2*alpha/100,'n_electrons_from_atoms_actual':2,'model_ne':2,'volume_bohr3':100,'natoms':1,'alpha_from_common_native':alpha,'psp_local_fourier_G0':0}
        result=M.analyze_local_reference(r,vry,[.1]*5,2,n_atoms=1,volume_bohr3=100,n_electrons=2,dftk_constants=constants)
        self.assertEqual(result['dftk_bookkeeping']['status'],'PASS')
        self.assertAlmostEqual(result['dftk_bookkeeping']['independent_primary_minus_native_Pc_ha'],0,delta=EPS)
        bad=dict(constants,psp_correction_ha=constants['psp_correction_ha']*2)
        failed=M.analyze_local_reference(r,vry,[.1]*5,2,n_atoms=1,volume_bohr3=100,n_electrons=2,dftk_constants=bad)
        self.assertEqual(failed['dftk_bookkeeping']['status'],'FAIL')
        with self.assertRaises(ValueError):M.analyze_local_reference(r,vry,[.1]*5,2,n_atoms=1,volume_bohr3=100,n_electrons=2,dftk_constants=dict(constants,volume_bohr3=200))
        json.dumps(result,allow_nan=False)

    def test_source_hash_checked_before_XML_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'synthetic.txt';p.write_bytes(b'synthetic non-UPF bytes')
            with self.assertRaisesRegex(ValueError,'SHA-256 mismatch before parsing'):
                M.read_bound_local_upf(p,'0'*64)
            self.assertEqual(p.read_bytes(),b'synthetic non-UPF bytes')


class ReceiptTests(unittest.TestCase):
    XML=b'<espresso><general_info><creator VERSION="7.5"/></general_info><input/></espresso>'

    def test_periodic_default_proof_is_explicit_and_conservative(self):
        good=M.qe_periodic_context('&SYSTEM\n nat=1,\n/',self.XML)
        self.assertTrue(good['ordinary_periodic'])
        self.assertIn('tagged default',good['assume_isolated'])
        self.assertIn('not an extracted runtime',good['source_scope'])
        for text in ["&SYSTEM\n assume_isolated='2D',\n/", "&SYSTEM\n esm_bc='pbc',\n/", '&SYSTEM\n/\n&SYSTEM\n/']:
            self.assertEqual(M.qe_periodic_context(text,self.XML)['status'],'NOT_ESTABLISHED')
        self.assertEqual(M.qe_periodic_context('&SYSTEM\n/',self.XML.replace(b'7.5',b'7.4'))['status'],'NOT_ESTABLISHED')

    def fixture(self,root):
        # Recorder-protocol fixture only: no UPF or scientific array is created.
        sha='a'*64
        files={'config/sources.lock':('[pseudopotentials]\nelement="Mg"\nfile_sha256="'+sha+'"\nlocal_path=".work/pseudos/Mg.upf"\n').encode(),
            'benchmarks/mg-soc-qe-diagnostics-v1/G40.in':b'&SYSTEM\n nat=1,\n/',
            'results/mg-soc-qe-diagnostics/G40/qe.xml':self.XML}
        for name,data in files.items():
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        plan={'schema_version':1,'case':'mg-soc-energy-reference-v1','pseudo_sha256':sha,
            'pseudo_path':'.work/pseudos/Mg.upf','source_sha256':{k:hashlib.sha256(v).hexdigest() for k,v in files.items()},
            'source_bytes':{k:len(v) for k,v in files.items()},
            'physical':{'nlcc':False,'volume_bohr3':1000,'atoms':1,'expected_electrons':10}}
        pp=root/'benchmarks/mg-soc-energy-reference-v1/plan.json';pp.parent.mkdir(parents=True,exist_ok=True)
        pp.write_text(json.dumps(plan))
        common={'schema_version':1,'execution_status':'PASS','exit_code':0,'run_id':'synthetic-receipt-only',
            'plan_sha256':hashlib.sha256(pp.read_bytes()).hexdigest(),
            'constants':{'source_sha256':sha,'nlcc':False,'volume_bohr3':1000,'natoms':1,'model_ne':10,
                'n_electrons_from_atoms_actual':10,'psp_correction_ha':.4,'alpha_from_common_native':40,'psp_local_fourier_G0':0}}
        return common

    def test_bound_wrapper_forwards_only_locked_inputs_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);common=self.fixture(root)
            with mock.patch.object(M,'audit_bound_upf',return_value={'qe_tagged_prediction':{}}) as calc:
                out=M.build_local_g0_audit(root,common)
            calc.assert_called_once_with(root.resolve()/'.work/pseudos/Mg.upf','a'*64,n_atoms=1,volume_bohr3=1000,
                n_electrons=10,dftk_constants=common['constants'],ordinary_periodic=True)
            self.assertEqual(out['run_id'],'synthetic-receipt-only')
            self.assertEqual(out['plan_sha256'],common['plan_sha256'])
            self.assertEqual(out['qe_tagged_prediction']['periodic_context_proof']['input_source']['path'],
                'benchmarks/mg-soc-qe-diagnostics-v1/G40.in')

    def test_wrapper_rejects_bad_worker_or_model_before_any_integral(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);common=self.fixture(root)
            variants=[dict(common,execution_status='FAIL'),dict(common,exit_code=1),dict(common,exit_code=False),
                dict(common,plan_sha256='0'*64),dict(common,constants=None),
                dict(common,constants=dict(common['constants'],source_sha256='b'*64)),
                dict(common,constants=dict(common['constants'],model_ne=20)),
                dict(common,constants=dict(common['constants'],psp_correction_ha=math.nan))]
            with mock.patch.object(M,'audit_bound_upf') as calc:
                for bad in variants:
                    with self.assertRaises(ValueError):M.build_local_g0_audit(root,bad)
                calc.assert_not_called()

    def test_wrapper_rejects_changed_source_before_any_integral(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);common=self.fixture(root)
            (root/'config/sources.lock').write_text('changed source lock')
            with mock.patch.object(M,'audit_bound_upf') as calc:
                with self.assertRaisesRegex(ValueError,'Plan-bound source changed'):
                    M.build_local_g0_audit(root,common)
                calc.assert_not_called()

    def test_wrapper_does_not_turn_unproved_QE_context_into_prediction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);common=self.fixture(root)
            with mock.patch.object(M,'qe_periodic_context',return_value={'status':'NOT_ESTABLISHED','ordinary_periodic':False}), \
                 mock.patch.object(M,'audit_bound_upf',return_value={'qe_tagged_prediction':{'status':'NOT_ESTABLISHED'}}) as calc:
                out=M.build_local_g0_audit(root,common)
            self.assertFalse(calc.call_args.kwargs['ordinary_periodic'])
            self.assertEqual(out['qe_tagged_prediction']['status'],'NOT_ESTABLISHED')


if __name__=='__main__':unittest.main()
