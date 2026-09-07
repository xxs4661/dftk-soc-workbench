"""Existing NumPy backend tests with analytic fields and independent filplot writer."""
import copy
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import replay_qe_local_fields as R
import compare_qe_local_potential as C
from compare_density_hartree import write_coefficients_gzip
from test_qe_local_potential_comparison import fixture


def probes(size):
    core=[(0,0,0),(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1),
          (1,1,-1),(-1,-1,1),(0,1,1),(0,-1,-1),(1,-1,1),(-1,1,-1),
          (1,2,1),(-1,-2,-1),(1,1,2),(-1,-1,-2)]
    return [list(m) for m in core]


def parsed(values,widths,plot,size):
    return {'parse_status':'PASS','expected_validation_status':'PASS','plot_num':plot,
        'unit':'Ha' if plot==2 else 'electron/bohr^3','unit_scale':.5 if plot==2 else 1,
        'grid':list(size),'values':list(values),'halfwidths':list(widths)}


def run_fixture(f,*,original=None):
    return R.replay_fields(f['densities'],f['potentials'],parsed(f['v']['Qpp'],f['widths'],2,f['size']),
        parsed(f['p0'],f['rho_widths'],0,f['size']),physical={'fft_size':list(f['size']),'lattice_vectors_bohr':f['lattice']},
        historical=f['history'],probes=probes(f['size']),thresholds=C.DEFAULT_THRESHOLDS,original_fields=original)


def write_native(path,values,plot,size,*,padding=False):
    """Independent small documented filplot fixture writer, not a parser inverse.

    Payload uses 17 significant digits here to isolate layout/FFT contracts;
    separate native parser tests cover the actual 1pe17.9 token formatting.
    """
    nx,ny,nz=size;allocated=(nx+1,ny+1,nz+2) if padding else size
    ax,ay,az=allocated
    lines=['synthetic periodic field, not a physical pseudopotential',
        f'{ax} {ay} {az} {nx} {ny} {nz} 1 1',
        '0 1.00000000000000000E+00 0 0 0 0 0',
        '3.00000000000000000E+00 0 0','0 4.00000000000000000E+00 0','0 0 5.00000000000000000E+00',
        f'1.00000000000000000E+00 4.00000000000000000E+00 3.00000000000000000E+01 {plot}',
        '1 Mg 1.00000000000000000E+01','1 0 0 0 1']
    payload=[]
    for k in range(nz):
        for j in range(ay):
            for i in range(ax):
                value=values[i+nx*(j+ny*k)] if i<nx and j<ny else 9876.
                payload.append(f'{value*(2 if plot==2 else 1):.17E}')
    lines+=[' '.join(payload[i:i+5]) for i in range(0,len(payload),5)]
    Path(path).write_text('\n'.join(lines)+'\n')


class ReplayTests(unittest.TestCase):
    def test_non_cubic_analytic_inverse_and_direct_phase(self):
        f=fixture()
        for key in ('A','B','Q'):
            field,workspace,checks=R.coefficients_to_field(f['densities'][key],f['size'],complete=key!='Q',tolerance=1e-11)
            self.assertLess(max(abs(x-y) for x,y in zip(field,f['arrays'][key])),1e-14)
            direct=R.direct_modes(field,f['size'],probes(f['size']))
            for m,z in direct.items():self.assertLess(abs(z-f['densities'][key].get(m,0)),1e-14)
            self.assertEqual(checks['coefficient_roundtrip']['status'],'PASS')

    def test_full_replay_and_exact_all_node_uncertainty(self):
        f=fixture();out=run_fixture(f)
        self.assertEqual(out['p0_phase_status'],'PASS')
        self.assertEqual(len(out['p0_phase_checks']),17)
        self.assertEqual(out['comparison']['local_energy_decomposition_status'],'PASS_ALGEBRA')
        self.assertEqual(out['density_integral_source'],'PUBLIC_FINITE_SERIES_RECONSTRUCTION')
        expected=f['volume']/len(f['arrays']['Q'])*math.fsum(abs(n)*u for n,u in zip(f['arrays']['Q'],f['widths']))
        self.assertAlmostEqual(out['pointwise']['quantization']['u_L_Q_ha'],expected,delta=1e-20)
        self.assertEqual(out['backend']['numpy_version'],np.__version__)
        support=out['support_diagnostics']
        self.assertEqual(support['full_export_G_count'],120)
        self.assertEqual(support['qe_saved_G_count'],5)
        self.assertEqual(support['outside_qe_saved_G_count'],115)
        self.assertEqual(support['P2']['status'],'COMPATIBLE_WITH_PRINT_NOISE_BOUND')
        self.assertTrue(support['all_native_modes_retained'])

    def test_original_arrays_remain_explicit_and_not_mutated(self):
        f=fixture();original={'n_'+k:list(f['arrays'][k]) for k in ('A','B','Q')};original['V_D']=f['v']['D'][:]
        original['n_A'][0]+=1e-14;before=copy.deepcopy(original)
        out=run_fixture(f,original=original)
        self.assertEqual(out['density_integral_source'],'ORIGINAL_ARCHIVED_ARRAYS')
        self.assertGreater(out['original_vs_public_reconstruction']['A']['max_abs'],0)
        self.assertEqual(original,before)

    def test_original_wrong_field_is_not_substituted(self):
        f=fixture();original={'n_'+k:list(f['arrays'][k]) for k in ('A','B','Q')};original['V_D']=f['v']['D'][:]
        original['V_D'][0]+=.1
        with self.assertRaisesRegex(ValueError,'archived D potential'):run_fixture(f,original=original)

    def test_printed_P0_phase_gate_includes_quantization(self):
        f=fixture();f['p0']=[x+2e-8 for x in f['arrays']['Q']];f['rho_widths']=[3e-8]*120
        out=run_fixture(f);zero=out['p0_phase_checks'][0]
        self.assertGreater(zero['absolute_difference'],1e-11)
        self.assertEqual(zero['status'],'PASS')
        self.assertAlmostEqual(zero['token_halfwidth_allowance'],3e-8,delta=1e-20)

    def test_wrong_phase_P0_blocks_comparison(self):
        f=fixture();f['p0']=f['p0'][1:]+f['p0'][:1]
        out=run_fixture(f)
        self.assertEqual(out['p0_phase_status'],'FAIL')
        self.assertEqual(out['comparison']['comparisons'],{})
        self.assertEqual(out['comparison']['local_same_density_integration_status'],'BLOCKED_P0_REGISTRATION')
        self.assertAlmostEqual(out['pointwise']['means_ha']['Qpp'],.4,delta=1e-14)

    def test_canonical_Q_mean_removal_unit_factor_or_transpose_rejected(self):
        for action in ('mean','factor','transpose'):
            f=fixture()
            if action=='mean':f['potentials']['Qpp'][(0,0,0)]=0j
            if action=='factor':f['potentials']['Qpp']={m:2*z for m,z in f['potentials']['Qpp'].items()}
            if action=='transpose':f['v']['Qpp']=list(reversed(f['v']['Qpp']))
            with self.assertRaisesRegex(ValueError,'Native P2'):run_fixture(f)

    def test_input_units_and_full_probe_set_are_required(self):
        f=fixture();p2=parsed(f['v']['Qpp'],f['widths'],2,f['size']);p2['unit_scale']=1
        kwargs=dict(physical={'fft_size':list(f['size']),'lattice_vectors_bohr':f['lattice']},historical=f['history'],probes=probes(f['size']),thresholds=C.DEFAULT_THRESHOLDS)
        with self.assertRaisesRegex(ValueError,'units'):
            R.replay_fields(f['densities'],f['potentials'],p2,parsed(f['p0'],f['rho_widths'],0,f['size']),**kwargs)
        with self.assertRaisesRegex(ValueError,'17'):R.direct_modes(f['v']['D'],f['size'],probes(f['size'])[:-1])

    def test_native_padding_is_removed_without_losing_first_axis_order(self):
        f=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'synthetic.pp';write_native(path,f['v']['Qpp'],2,f['size'],padding=True)
            p=R.parse_qe_filplot(path,expected_plot_num=2,expected={'grid':list(f['size']),'unit':'Ha'})
            self.assertEqual(p['physical_count'],120);self.assertGreater(p['padding_count_excluded'],0)
            self.assertEqual(p['values'],f['v']['Qpp'])
            c,_=R.field_to_coefficients(p['values'],f['size'])
            self.assertLess(max(abs(c[m]-f['potentials']['Qpp'][m]) for m in c),1e-15)

    def test_public_replay_uses_only_bound_public_files_no_work_directory(self):
        f=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for relative in R.PUBLIC_SOURCES.values():(root/relative).parent.mkdir(parents=True,exist_ok=True)
            write_coefficients_gzip(root/R.PUBLIC_SOURCES['dftk_density'],{'A_out':f['densities']['A'],'B_out':f['densities']['B']})
            write_coefficients_gzip(root/R.PUBLIC_SOURCES['qe_density'],{'QE':f['densities']['Q']})
            for key in ('ledger','common','radial'):(root/R.PUBLIC_SOURCES[key]).write_text(json.dumps(f['history'][key]))
            potential=root/'potential.csv.gz';write_coefficients_gzip(potential,{'V_D':f['potentials']['D'],'V_Qpp':f['potentials']['Qpp']})
            p2=root/'P2.pp';p0=root/'P0.pp';write_native(p2,f['v']['Qpp'],2,f['size']);write_native(p0,f['arrays']['Q'],0,f['size'])
            expected={'grid':list(f['size']),'lattice_columns_bohr':f['lattice'],'positions_cartesian_bohr':[[0.,0,0]],
                'species':[{'symbol':'Mg','z_valence':10}],'atom_species_indices':[1],'cutoffs':{'gcutm':1.,'dual':4.,'ecut_ry':30.}}
            plan={'physical':{'fft_size':list(f['size']),'lattice_vectors_bohr':f['lattice']},'filplot_expected':expected,
                'direct_fourier_miller_points':probes(f['size']),'thresholds':dict(C.DEFAULT_THRESHOLDS,extractor_alias_unused=1e-12),
                'source_sha256':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in R.PUBLIC_SOURCES.values()}}
            out=R.replay(root,plan,potential,p2,p0)
            self.assertEqual(out['p0_phase_status'],'PASS')
            self.assertEqual(out['comparison']['local_energy_decomposition_status'],'PASS_ALGEBRA')
            self.assertFalse((root/'.work').exists())
            (root/R.PUBLIC_SOURCES['ledger']).write_text('{}')
            with self.assertRaisesRegex(ValueError,'Changed frozen public source'):R.replay(root,plan,potential,p2,p0)


if __name__=='__main__':unittest.main()
