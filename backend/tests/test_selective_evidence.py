import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from selective_evidence import measurements,fit_linear,linear_output,selective,choose_threshold
from run_selective import hashes,BUNDLE,sha
from app.ccare.engine import local_state
from app.ccare.research import constraint_envelope
from app.ccare.schemas import TurnRequest,State

class SelectiveEvidenceTests(unittest.TestCase):
    def model(self):
        return fit_linear([{'split':'train','label':l,'text':t} for l,t in
            [('supported','先听我说'),('contradicted','给我建议'),('insufficient','不确定')]])
    def test_zero_coverage_is_not_zero_error(self):
        r=measurements(['supported','insufficient'],['abstain','abstain'])
        self.assertEqual(r['coverage'],0)
        self.assertIsNone(r['selective_error_rate'])
        self.assertEqual(r['clarification_count'],2)
        self.assertEqual(r['unnecessary_clarifications_under_labels'],1)
    def test_abstention_and_insufficient_are_different(self):
        r=measurements(['supported','insufficient','contradicted'],['abstain','insufficient','supported'])
        self.assertAlmostEqual(r['coverage'],2/3)
        self.assertEqual(r['selective_error_rate'],.5)
        self.assertEqual(r['confusion_gold_rows']['supported']['abstain'],1)
    def test_train_only_and_deterministic_linear_fit(self):
        self.assertEqual(self.model(),self.model())
        self.assertEqual(linear_output(self.model(),'先听我说')[0],'supported')
        with self.assertRaises(ValueError):fit_linear([{'split':'test','text':'x','label':'supported'}])
    def test_unknown_features_and_attribution_request_clarification(self):
        for text in ['XYZ','朋友说先听我说','以前先听我说','更正先听我说']:
            self.assertEqual(selective(self.model(),text,0)['action'],'clarify')
    def test_infeasible_dev_selection_reports_failure_not_all_reject(self):
        threshold,_,feasible=choose_threshold(self.model(),[{'split':'dev','text':'XYZ','label':'supported'}])
        self.assertFalse(feasible)
        self.assertEqual(threshold,0)
    def test_abstention_cannot_clear_independent_safety(self):
        req=TurnRequest(message='我不知道怎么办，爸爸正在掐我。')
        self.assertEqual(selective(self.model(),req.message,0)['prediction'],'abstain')
        self.assertEqual(local_state(req).risk,'urgent')
        self.assertEqual(constraint_envelope(req,State()).allowed,['safety'])
    def test_frozen_method_and_models_match(self):
        m=json.loads((BUNDLE/'frozen/manifest.json').read_text())
        self.assertEqual(m['hashes'],hashes())
        for name,digest in m['models'].items():self.assertEqual(sha(BUNDLE/'frozen'/name),digest)
