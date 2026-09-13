"""Synthetic arithmetic only; no material calculations."""
import copy
import hashlib
import gzip
import importlib.util
import json
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location('timing_'+name,ROOT/'benchmarks/soc-timing-v1'/f'{name}.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
C=load('compare')
R=load('replay')

class Comparison(unittest.TestCase):
    def setUp(self):
        self.record=dict(map_index=1,kpoints=[[a,b,c] for a in [0,-.5] for b in [0,-.5] for c in [0,-.5]],
                         eigenvalues_ha=[[i/10 for i in range(24)] for _ in range(8)],
                         internal_energy_ha=-8.,free_energy_ha=-8.01)
    def test_same_map(self):
        self.assertEqual(C.compare_values(self.record,self.record,[1.,2.],[1.,2.])['status'],'PASS')
    def test_original_energy_difference_is_not_removed(self):
        changed=copy.deepcopy(self.record);changed['internal_energy_ha']+=1e-6
        self.assertEqual(C.compare_values(self.record,changed,[1.,2.],[1.,2.])['status'],'FAIL')
    def test_common_level_shift_is_not_fitted(self):
        changed=copy.deepcopy(self.record);changed['eigenvalues_ha']=[[v+.01 for v in k] for k in changed['eigenvalues_ha']]
        self.assertEqual(C.compare_values(self.record,changed,[1.,2.],[1.,2.])['status'],'FAIL')
    def test_different_map_or_k_rejected(self):
        changed=copy.deepcopy(self.record);changed['map_index']=2
        with self.assertRaises(ValueError):C.compare_values(self.record,changed,[1.],[1.])
        changed=copy.deepcopy(self.record);changed['kpoints'][0]=[.25,0,0]
        with self.assertRaises(ValueError):C.compare_values(self.record,changed,[1.],[1.])
    def test_density_failure_and_nan(self):
        self.assertEqual(C.compare_values(self.record,self.record,[1.,2.],[1.,2.1])['status'],'FAIL')
        with self.assertRaises(ValueError):C.compare_values(self.record,self.record,[1.],[float('nan')])
    def test_wrong_source_receipt_cannot_enter_array_pair(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();area=root/'.work/soc-timing';area.mkdir(parents=True)
            for task in ('T-B0-REF','T-B0-TIMED'):
                run_id=task+'-synthetic';directory=area/'runs'/run_id;(directory/'worker').mkdir(parents=True)
                worker=dict(run_id=run_id,task_id=task,execution_commit='a'*40,source_commit='b'*40,
                            exit_code=0,execution_status='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED')
                raw=json.dumps(worker).encode();(directory/'worker/result.json').write_bytes(raw)
                outer=dict(worker,worker_result_sha256=hashlib.sha256(raw).hexdigest())
                (directory/'result.json').write_text(json.dumps(outer))
                (area/(task+'-accepted.json')).write_text(json.dumps(dict(run_id=run_id,directory=str(directory),execution_commit='a'*40)))
            with self.assertRaisesRegex(ValueError,'source identity'):C.pair(root)

class SpanArithmetic(unittest.TestCase):
    def row(self,i,parent,start,end,self_ns):
        return dict(run_id='synthetic',pid=12,span_id=i,parent_span=parent,name='example',
                    map_index=0,k_index=0,start_offset_ns=start,end_offset_ns=end,
                    inclusive_ns=end-start,exclusive_ns=self_ns,calls=1,status='COMPLETE')
    def test_nested_not_double_counted(self):
        rows=[self.row(1,0,0,100,60),self.row(2,1,10,50,40)]
        self.assertEqual(R.spans(rows)['synthetic']['attributed_exclusive_ns'],100)
    def test_diagnostic_stop_is_closed_without_claiming_convergence(self):
        row=self.row(1,0,0,100,100);row['status']='DIAGNOSTIC_COMPLETED'
        self.assertEqual(R.spans([row])['synthetic']['attributed_exclusive_ns'],100)
    def test_wrong_self_and_missing_parent(self):
        with self.assertRaises(ValueError):R.spans([self.row(1,0,0,100,100),self.row(2,1,10,50,40)])
        with self.assertRaises(ValueError):R.spans([self.row(2,1,10,50,40)])
    def test_duplicate_or_overlapping_children(self):
        x=self.row(1,0,0,100,100)
        with self.assertRaises(ValueError):R.spans([x,x])
        with self.assertRaises(ValueError):R.spans([self.row(1,0,0,100,10),self.row(2,1,10,60,50),self.row(3,1,50,90,40)])

class BatchControl(unittest.TestCase):
    def test_zero_entry_without_receipt_is_rejected(self):
        m=load('run')
        with self.assertRaises(ValueError):m.entry_contract(b'',0,{})
        with self.assertRaises(ValueError):m.entry_contract(b'{}',0,{'run_id':'synthetic'})
    def test_entry_loaded_source_and_no_context_are_required(self):
        m=load('run')
        route=dict(run_id='synthetic',task_id='T-B0-REF',execution_commit='a'*40,
                   source_commit=C.E0,case_sha256='b'*64,source_sha256={'source.jl':'c'*64})
        value=dict(route,execution_status='CHECK_ONLY_PASS',exit_code=0,check_only=True,
                   context_constructed=False,owned_runtime_constructed=False,formal_slot_reserved=False,
                   numerical_execution_status='NOT_RUN',environment={'status':'PASS'},
                   actual_method_sources={name:dict(relative_path='source.jl',source_sha256='c'*64)
                       for name in ['soc_scf','solve_soc_targets','controller']})
        self.assertEqual(m.entry_contract(json.dumps(value).encode(),0,route)['exit_code'],0)
        for key,changed in [('context_constructed',True),('source_commit','d'*40),
                            ('environment',{'status':'FAIL'}),('actual_method_sources',{})]:
            bad=dict(value);bad[key]=changed
            with self.subTest(key=key),self.assertRaises(ValueError):m.entry_contract(json.dumps(bad).encode(),0,route)
    def test_sleep_and_backward_calendar_do_not_extend_budget(self):
        m=load('run');batch=dict(started_epoch=1000,started_monotonic_ns=1000000000)
        self.assertEqual(m.remaining(batch,now_epoch=2000,now_ns=11000000000),2600)
        self.assertEqual(m.remaining(batch,now_epoch=900,now_ns=1001000000000),2600)
    def test_failed_owned_launch_keeps_locks(self):
        m=load('run')
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                with m.locks(Path(d),'synthetic-run') as lease:
                    lease['launched']=True
                    raise RuntimeError('Synthetic unconfirmed cleanup')
            self.assertTrue((Path(d)/'.work/soc-timing/active.json').exists())
    def test_before_launch_failure_releases_only_owned_locks(self):
        m=load('run')
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                with m.locks(Path(d),'synthetic-run'):
                    raise RuntimeError('Synthetic preparation failure')
            self.assertFalse((Path(d)/'.work/soc-timing/active.json').exists())


class PublicEvidenceContracts(unittest.TestCase):
    """Malformed public fixtures, never scientific/physical evidence."""
    def evidence(self, directory):
        execution='a'*40
        good='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED'
        data=dict(schema_version=1,phase='9A-timing-cancellation',
                  instrumentation_overhead_status='OVERHEAD_NOT_ESTABLISHED',runs=[])
        for task in ('T-B0-REF','T-B0-TIMED'):
            data['runs'].append(dict(task_id=task,run_id=task+'-synthetic',execution_commit=execution,
                source_commit=C.E0 if task=='T-B0-REF' else execution,case_sha256='c'*64,
                execution_status=good,native_exit_code=0,recorder_exit_code=0,completed_maps=2,
                runtime_closed=True,workspace_released=True,owned_process_cleanup_status='PASS',
                limit_bytes=8*1024**3,warning_bytes=7*1024**3))
        data['runs'].append(dict(task_id='T-K4-TIMED',execution_status='NOT_RUN',native_exit_code=None))
        pair=dict(status='PASS',execution_commit=execution,run_ids=[r['run_id'] for r in data['runs'][:2]],
                  maps=[dict(map_index=i,delta_E_ha=0.,delta_F_ha=0.,density_relative_l2=0.,
                             raw_level_max_abs_ha=0.,raw_level_rms_ha=0.) for i in (1,2)])
        return data,pair
    def write_evidence(self, directory, data, pair, mutate_package=None):
        (directory/'timing.csv').write_text('run_id,pid,span_id,parent_span,name,map_index,k_index,start_offset_ns,end_offset_ns,inclusive_ns,exclusive_ns,calls,status\n')
        (directory/'b0-equivalence.json').write_text(json.dumps(pair))
        package={task:[] for task in ('T-B0-REF','T-B0-TIMED','T-K4-TIMED')}
        for row in data['runs']:
            task=row['task_id']
            if not row['execution_status'].startswith(('NOT_RUN','BLOCKED')):
                package[task]=[dict({key:row[key] for key in
                    ('run_id','task_id','execution_commit','source_commit','case_sha256')},
                    map_index=imap,internal_energy_ha=-8.,free_energy_ha=-8.01,
                    kpoints=[[a,b,c] for a in (0,-.5) for b in (0,-.5) for c in (0,-.5)],
                    eigenvalues_ha=[[k+i/10 for i in range(24)] for k in range(8)],
                    occupations=[[.5 for _ in range(24)] for _ in range(8)]) for imap in (1,2)]
        if mutate_package:mutate_package(package)
        (directory/'map-spectra.json.gz').write_bytes(gzip.compress(json.dumps(package).encode(),mtime=0))
        data['public_files_sha256']={name:hashlib.sha256((directory/name).read_bytes()).hexdigest()
                                    for name in ('timing.csv','b0-equivalence.json','map-spectra.json.gz')}
        (directory/'runs.json').write_text(json.dumps(data))
    def test_current_qualified_pair_fixture(self):
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d);data,pair=self.evidence(directory);self.write_evidence(directory,data,pair)
            self.assertEqual(R.replay(directory)['b0_equivalence_status'],'PASS')
    def test_public_levels_and_energies_must_reproduce_stored_metrics(self):
        for field in ('delta_E_ha','delta_F_ha','raw_level_max_abs_ha','raw_level_rms_ha'):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as d:
                directory=Path(d);data,pair=self.evidence(directory)
                pair['maps'][0][field]=1e-15 # Within gate, but contradicts the actual public arrays.
                self.write_evidence(directory,data,pair)
                with self.assertRaisesRegex(ValueError,'Stored B0 metric differs'):R.replay(directory)
    def test_public_state_rows_match_coordinates_not_output_order(self):
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d);data,pair=self.evidence(directory)
            def permute(package):
                for rec in package['T-B0-TIMED']:
                    for key in ('kpoints','eigenvalues_ha','occupations'):rec[key].reverse()
            self.write_evidence(directory,data,pair,permute)
            value=R.replay(directory)['b0_public_energy_spectrum_replay']
            self.assertEqual(value['status'],'PASS')
            self.assertEqual(value['maps'][0]['raw_level_max_abs_ha'],0.)
    def test_public_map_identity_and_coordinates_are_required(self):
        for kind in ('identity','duplicate_k','wrong_band_count'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                directory=Path(d);data,pair=self.evidence(directory)
                def damage(package):
                    rec=package['T-B0-TIMED'][0]
                    if kind=='identity':rec['run_id']='old-run'
                    elif kind=='duplicate_k':rec['kpoints'][1]=rec['kpoints'][0]
                    else:rec['eigenvalues_ha'][0].pop()
                self.write_evidence(directory,data,pair,damage)
                with self.assertRaises(ValueError):R.replay(directory)
    def test_spectrum_package_requires_a_public_hash(self):
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d);data,pair=self.evidence(directory);self.write_evidence(directory,data,pair)
            data['public_files_sha256'].pop('map-spectra.json.gz')
            (directory/'runs.json').write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'not authenticated'):R.replay(directory)
    def test_duplicate_task_cannot_be_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d);data,pair=self.evidence(directory)
            data['runs'].append(copy.deepcopy(data['runs'][0]));self.write_evidence(directory,data,pair)
            with self.assertRaises(ValueError):R.replay(directory)
    def test_pair_pass_requires_two_completed_parents(self):
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d);data,pair=self.evidence(directory)
            data['runs'][0].update(execution_status='NOT_RUN',native_exit_code=None)
            self.write_evidence(directory,data,pair)
            with self.assertRaisesRegex(ValueError,'qualified diagnostics'):R.replay(directory)
    def test_pair_from_other_execution_or_runs_is_rejected(self):
        for field,value in [('execution_commit','b'*40),('run_ids',['old-ref','old-timed'])]:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as d:
                directory=Path(d);data,pair=self.evidence(directory);pair[field]=value
                self.write_evidence(directory,data,pair)
                with self.assertRaises(ValueError):R.replay(directory)
    def test_map_two_cannot_be_bound_as_map_one(self):
        # Use real small receipt files; replace only the private array reader.
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();area=root/'.work/soc-timing';area.mkdir(parents=True)
            for task in ('T-B0-REF','T-B0-TIMED'):
                run_id=task+'-synthetic';directory=area/'runs'/run_id;worker_dir=directory/'worker'
                worker_dir.mkdir(parents=True)
                worker=dict(run_id=run_id,task_id=task,execution_commit='a'*40,
                            source_commit=C.E0 if task=='T-B0-REF' else 'a'*40,
                            exit_code=0,execution_status='DIAGNOSTIC_COMPLETED_NOT_SCF_CONVERGED',
                            map_summaries_sha256={})
                for imap in (1,2):
                    record=dict(run_id=run_id,execution_commit=worker['execution_commit'],
                        source_commit=worker['source_commit'],map_index=2,
                        kpoints=[[a,b,c] for a in (0,-.5) for b in (0,-.5) for c in (0,-.5)],
                        eigenvalues_ha=[[i/10 for i in range(24)] for _ in range(8)],
                        internal_energy_ha=-8.,free_energy_ha=-8.01,
                        density_file=f'map-{imap:03d}-density.f64',density_file_sha256='c'*64)
                    name=f'map-{imap:03d}-summary.json';raw=json.dumps(record).encode()
                    (worker_dir/name).write_bytes(raw);worker['map_summaries_sha256'][name]=hashlib.sha256(raw).hexdigest()
                raw=json.dumps(worker).encode();(worker_dir/'result.json').write_bytes(raw)
                (directory/'result.json').write_text(json.dumps(dict(worker,worker_result_sha256=hashlib.sha256(raw).hexdigest())))
                (area/(task+'-accepted.json')).write_text(json.dumps(dict(run_id=run_id,
                    directory=str(directory),execution_commit='a'*40)))
            with patch.object(C,'density',return_value=[1.,2.]),self.assertRaisesRegex(ValueError,'Map summary index'):
                C.pair(root)

if __name__=='__main__':unittest.main()
