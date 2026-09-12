"""Synthetic public-record tests only; no physical worker or private data."""
import copy
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'benchmarks/soc-extra-v1/plan.json').is_file())
DRAFT=Path(os.environ.get('SOC_EXTRA_REPLAY_TEST_FILE',ROOT/'benchmarks/soc-extra-v1/replay.py'))
loader=importlib.machinery.SourceFileLoader('extra_stop_replay_draft',str(DRAFT))
spec=importlib.util.spec_from_loader(loader.name,loader)
REPLAY=importlib.util.module_from_spec(spec);loader.exec_module(REPLAY)


class ResourceStopReplay(unittest.TestCase):
    def fixture(self):
        execution='a'*40;run='SYNTHETIC-K6-SCF';raw='b'*64
        source={'benchmarks/soc-extra-v1/plan.json':b'synthetic plan',
                'benchmarks/soc-extra-v1/resources.py':b'synthetic resource policy'}
        peak=7447937024;growth=2021087414;limit=8*1024**3
        stop=dict(schema_version=1,status='STOP_AT_SAFE_BOUNDARY',run_id=run,
            execution_commit=execution,sampled_peak_bytes=peak,fixed_remaining_growth_bytes=growth,
            projected_screen_bytes=peak+growth,limit_bytes=limit,excess_screen_bytes=peak+growth-limit,
            plan_sha256=hashlib.sha256(source['benchmarks/soc-extra-v1/plan.json']).hexdigest(),
            resources_source_sha256=hashlib.sha256(source['benchmarks/soc-extra-v1/resources.py']).hexdigest())
        resource=dict(status='PASS',native_exit_code=1,peak_aggregate_rss_bytes=peak,limit_bytes=limit,
            extra_policy=dict(safe_boundary_stop_requested=True,remaining_growth_bytes=growth,stop_bytes=limit))
        worker=dict(action='X-K6-SCF',execution_commit=execution,run_id=run+'-dftk',
            execution_status='FAIL',exit_code=1,peak_rss_bytes=7528939520)
        scf=dict(status='FAIL',run_id=run,native_exit_code=1,recorder_exit_code=1,
            worker=worker,resource=resource,admission=dict(remaining_growth_bytes=growth))
        data=dict(execution_commit=execution,slots={'X-K6-SCF':scf,
            'X-K6-GAMMA':dict(status='BLOCKED_PARENT',native_exit_code=None,worker=None)},
            resource_guard_review=dict(stop_request=stop,raw_stop_request_sha256=raw))
        descriptor=dict(path='synthetic-stop.json.gz',raw_sha256=raw)
        return data,descriptor,source

    def invoke(self,data,descriptor,source,artifact_stop=None):
        stop=data['resource_guard_review']['stop_request'] if artifact_stop is None else artifact_stop
        with patch.object(REPLAY,'artifact',return_value=json.dumps(stop).encode()), \
             patch.object(REPLAY,'git',side_effect=lambda root,command,ref:source[ref.split(':',1)[1]]):
            return REPLAY.audit_resource_stop(Path('.'),descriptor,data)

    def test_absence_compatible_only_without_stop_flag(self):
        data,descriptor,source=self.fixture();del data['resource_guard_review']
        data['slots']['X-K6-SCF']['resource']['extra_policy']['safe_boundary_stop_requested']=False
        self.assertEqual(REPLAY.audit_resource_stop(Path('.'),None,data)['status'],'NOT_ASSESSED')
        data['slots']['X-K6-SCF']['resource']['extra_policy']['safe_boundary_stop_requested']=True
        with self.assertRaisesRegex(ValueError,'missing'):REPLAY.audit_resource_stop(Path('.'),None,data)

    def test_valid_review_preserves_failed_science_and_distinct_rss(self):
        data,descriptor,source=self.fixture();before=copy.deepcopy(data)
        result=self.invoke(data,descriptor,source)
        self.assertEqual(result['status'],'GROWTH_SCREEN_FAILED')
        self.assertEqual(result['native_exit_code'],1)
        self.assertEqual(result['scf_execution_status'],'FAIL')
        self.assertEqual(result['projected_screen_bytes'],9469024438)
        self.assertEqual(result['excess_screen_bytes'],879089846)
        self.assertNotEqual(result['sampled_peak_bytes'],result['native_highwater_bytes'])
        self.assertEqual(data,before)

    def test_semantic_contradictions_are_rejected(self):
        cases=(('sum',lambda d:d['resource_guard_review']['stop_request'].__setitem__('projected_screen_bytes',9469024437)),
               ('growth',lambda d:d['slots']['X-K6-SCF']['admission'].__setitem__('remaining_growth_bytes',1)),
               ('run',lambda d:d['resource_guard_review']['stop_request'].__setitem__('run_id','other')),
               ('source',lambda d:d['resource_guard_review']['stop_request'].__setitem__('plan_sha256','c'*64)),
               ('gamma',lambda d:d['slots']['X-K6-GAMMA'].__setitem__('native_exit_code',0)),
               ('scf',lambda d:d['slots']['X-K6-SCF'].__setitem__('status','PASS')),
               ('bool',lambda d:d['resource_guard_review']['stop_request'].__setitem__('limit_bytes',True)))
        for label,mutate in cases:
            with self.subTest(label=label):
                data,descriptor,source=self.fixture();mutate(data)
                with self.assertRaises(ValueError):self.invoke(data,descriptor,source)

    def test_artifact_and_original_hash_bindings_are_required(self):
        data,descriptor,source=self.fixture();different=copy.deepcopy(data['resource_guard_review']['stop_request']);different['run_id']='other'
        with self.assertRaisesRegex(ValueError,'artifact differs'):self.invoke(data,descriptor,source,different)
        descriptor['raw_sha256']='d'*64
        with self.assertRaisesRegex(ValueError,'hash references differ'):self.invoke(data,descriptor,source)


if __name__=='__main__':unittest.main(verbosity=2)
