"""Public-only integrity negatives and synthetic replay tolerances; no raw input."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import check_density_hartree as checker

ROOT=Path(__file__).resolve().parents[1]


class DensityPublicTests(unittest.TestCase):
    def public_copy(self, directory):
        plan=checker.load(ROOT/checker.PLAN)
        evidence=checker.load(ROOT/checker.RESULTS/'evidence.json')
        files=set(plan['source_evidence_sha256']) | set(plan['frozen_environment_sha256']) | \
              set(evidence['public_sha256']) | set(evidence['verifier_sha256']) | \
              {checker.PLAN,checker.RESULTS+'/evidence.json'}
        for name in files:
            target=directory/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/name,target)
        return evidence

    def test_modified_public_coefficient_bytes_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.public_copy(root)
            p=root/checker.RESULTS/'dftk-nout.csv.gz';raw=bytearray(p.read_bytes());raw[-10]^=1;p.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'Bound public file changed'):
                checker.check(root)

    def test_wrong_original_run_id_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);e=self.public_copy(root)
            e['sources']['A']['run_id']='synthetic-wrong-run'
            (root/checker.RESULTS/'evidence.json').write_text(json.dumps(e))
            with self.assertRaisesRegex(ValueError,'source ID'):
                checker.check(root)

    def test_unbound_raw_hash_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);e=self.public_copy(root)
            e['sources']['G40']['raw_sha256']='0'*64
            (root/checker.RESULTS/'evidence.json').write_text(json.dumps(e))
            with self.assertRaisesRegex(ValueError,'raw density source hash'):
                checker.check(root)

    def test_public_package_gzip_time_and_full_rows(self):
        import gzip
        for name,rows in [('dftk-nout.csv.gz',64000),('qe-rho.csv.gz',22119)]:
            raw=(ROOT/checker.RESULTS/name).read_bytes()
            self.assertEqual(int.from_bytes(raw[4:8],'little'),0)
            csv=gzip.decompress(raw)
            self.assertNotIn(b'\r',csv)
            self.assertEqual(len(csv.splitlines()),rows+1)

    def test_synthetic_replay_accepts_last_bit_not_material_change(self):
        checker.equivalent({'value_ha':28.0},{'value_ha':28.0+1e-14})
        with self.assertRaises(ValueError):
            checker.equivalent({'value_ha':28.0},{'value_ha':28.0+1e-7})

    def test_synthetic_replay_rejects_missing_data_and_nonfinite(self):
        for value in ({}, {'value':float('nan')}, {'value':'1'}):
            with self.assertRaises(ValueError):
                checker.equivalent({'value':1.0},value)


if __name__=='__main__':
    unittest.main()
