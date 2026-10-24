import json
from pathlib import Path
import sys
import tempfile
import unittest
from app.ccare.learned_evidence import fit,predict,LearnedListenAdapter
from app.ccare.research import Claim,constraint_envelope
from app.ccare.schemas import TurnRequest,State
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from train_evidence import load_data,metrics

class LearnedEvidenceTests(unittest.TestCase):
    def model(self):
        return fit([{'split':'train','label':label,'text':text} for label,text in
            [('supported','只想倾听'),('contradicted','需要建议'),('insufficient','不确定')]])
    def test_fits_and_roundtrips_real_counts_without_test_data(self):
        model=self.model()
        self.assertEqual(model['counts']['supported']['倾听'],1)
        self.assertEqual(predict(json.loads(json.dumps(model)),'只想倾听'),'supported')
        with self.assertRaises(ValueError):fit([{'split':'test','label':'supported','text':'秘密测试'}])
    def test_family_and_template_leakage_rejected(self):
        base=dict(case_id='a',family_id='f',template_id='t',split='train',label='supported',synthetic=True,review_status='unreviewed')
        for field in ('family_id','template_id'):
            second=base|{'case_id':'b','split':'test','family_id':'other','template_id':'other',field:base[field]}
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/'data';p.write_text(json.dumps(base)+'\n'+json.dumps(second))
                with self.assertRaises(ValueError):load_data(p)
    def test_adapter_is_narrow_and_cannot_authorize_unsafe_strategy(self):
        req=TurnRequest(message='爸爸正在掐我',message_id='now')
        adapter=LearnedListenAdapter(self.model())
        result=adapter.assess(req,Claim(field='emotion',value='sad',message_id='now',quote=req.message))
        self.assertEqual(result.verdict,'insufficient')
        self.assertEqual(constraint_envelope(req,State()).allowed,['safety'])
    def test_metrics_keep_all_labels_and_errors(self):
        result=metrics(['supported','contradicted','insufficient'],['supported']*3)
        self.assertEqual(result['n'],3)
        self.assertAlmostEqual(result['accuracy'],1/3)
        self.assertAlmostEqual(result['macro_f1'],1/6)
    def test_saved_artifact_matches_report_and_frozen_sources(self):
        import hashlib
        from train_evidence import BUNDLE,hashes
        report=json.loads((BUNDLE/'artifacts/report.json').read_text())
        self.assertEqual(hashlib.sha256((BUNDLE/'artifacts/model.json').read_bytes()).hexdigest(),report['model_sha256'])
        self.assertEqual(hashes(),json.loads((BUNDLE/'freeze.json').read_text()))
        self.assertEqual(report['samples'],{'train':24,'dev':6,'test':6})
