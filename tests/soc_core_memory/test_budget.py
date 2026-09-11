"""Synthetic budget-ledger mutations, no geometry/context generation."""
import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('budget9a',ROOT/'benchmarks/soc-core-memory-v1/budget.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Budget(unittest.TestCase):
    def fixture(self):
        g=dict(nk=216,ng_max=2138,sum_ng=457287,fft_size=[48]*3,projectors_per_k=72,target_states=24,solver_columns=30)
        terms=m.known_terms(g)
        return dict(geometry=g,accounting_terms={k:dict(bytes=v) for k,v in terms.items()},
            known_terms_plus_retained_allowances_subtotal_bytes=sum(terms.values()),hard_limit_bytes=8*1024**3,
            margin_bytes=2*1024**3,original_legacy_estimate=dict(total_bytes=12614633984),status='INSUFFICIENT_EVIDENCE',
            new_estimated_peak_bytes=None,subtotal_is_upper_bound=False,unpriced_or_unbounded=['synthetic missing native bound'],
            DFTK_K6_SCF='NOT_RUN',DFTK_K6_context_created=False)
    def test_incomplete_is_not_green(self):
        r=m.replay(self.fixture());self.assertEqual(r['subtotal_bytes'],6788850928);self.assertEqual(r['status'],'INSUFFICIENT_EVIDENCE')
    def test_smaller_margin_rejected(self):
        d=self.fixture();d['margin_bytes']//=2
        with self.assertRaises(ValueError):m.replay(d)
    def test_unjustified_bound_rejected(self):
        d=self.fixture();d['status']='ESTIMATED_WITHIN_LIMIT'
        with self.assertRaises(ValueError):m.replay(d)
    def test_missing_term_rejected(self):
        d=self.fixture();del d['accounting_terms']['three_common_H_local_potential_sets']
        with self.assertRaises(ValueError):m.replay(d)
    def test_recorded_value_recomputed(self):
        d=self.fixture();d['accounting_terms']['one_retained_P_set']['bytes']//=2
        with self.assertRaises(ValueError):m.replay(d)
if __name__=='__main__':unittest.main()
