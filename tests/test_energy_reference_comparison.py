"""Synthetic signed splitting; no real XC or pseudopotential evidence."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from compare_energy_reference import split_response,close

class EnergySplitting(unittest.TestCase):
    def test_xc_signed_recombination(self):
        r=split_response(-7.0,-7.1,-6.9)
        self.assertAlmostEqual(r['density_response_in_D_ha'],.1)
        self.assertAlmostEqual(r['evaluation_residual_at_Q_rep_ha'],-.2)
        self.assertAlmostEqual(r['historical_difference_ha'],-.1)
        self.assertAlmostEqual(r['recombination_error_ha'],0)
    def test_first_order_not_added_to_energy(self):
        r=split_response(-7.,-7.1,-6.9,.09)
        self.assertAlmostEqual(r['curvature_remainder_ha'],.01)
        self.assertAlmostEqual(r['historical_difference_ha'],-.1)
    def test_zero_density_response_does_not_erase_residual(self):
        r=split_response(3.,3.,2.)
        self.assertEqual(r['density_response_in_D_ha'],0)
        self.assertEqual(r['evaluation_residual_at_Q_rep_ha'],1)
    def test_nonfinite_or_wrong_gate_rejected(self):
        for a,b in [(float('nan'),0),(1.,float('inf')),(1.,0)]:
            with self.assertRaises(ValueError): close(a,b,1e-11,'synthetic')
    def test_zero_absolute_error(self):
        self.assertEqual(close(0.,0.,1e-11,'zero'),0)

if __name__=='__main__':unittest.main()
