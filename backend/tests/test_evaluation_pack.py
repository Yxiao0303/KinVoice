"""Data QA only: no predictions, scoring or tuning on candidate cases."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from validate_evaluation_pack import rows, validate, validate_rows

class EvaluationPackTests(unittest.TestCase):
    def test_frozen_pack_and_blank_forms(self):
        result=validate()
        self.assertEqual(result['candidate_holdout'],36)
        self.assertEqual(result['algorithm_predictions'],0)
        self.assertEqual(result['ratings'],0)
    def test_reject_evidence_offset_corruption(self):
        data=copy.deepcopy(rows());data[0]['key_evidence'][0]['start']+=1
        with self.assertRaises(AssertionError):validate_rows(data)
    def test_reject_template_family_leakage(self):
        data=copy.deepcopy(rows())
        for r in data:
            if r['family_id']=='T01_shared_album':r['template_family_id']=data[0]['template_family_id']
        with self.assertRaises(AssertionError):validate_rows(data)
    def test_reject_invented_expert_provenance(self):
        data=copy.deepcopy(rows());data[-1]['review_status']='expert_approved'
        with self.assertRaises(AssertionError):validate_rows(data)
