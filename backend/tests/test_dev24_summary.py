import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from summarize_dev24 import summarize

class Dev24SummaryTests(unittest.TestCase):
    def fixture(self,out,usage):
        rows=[{'case_id':f'case{i}','arm':arm,'reply':'','status':'not_run','calls':[],'elapsed_ms':0} for i in range(24) for arm in ('strong_single','strong_multi','ccare')]
        rows[0].update(status='failed',calls=[{'wire_attempted':True,'usage':usage,'http_status':200,'model':'fixture'}])
        (out/'outputs.json').write_text(json.dumps(rows));(out/'plan.json').write_text(json.dumps({'items':[{'case_id':r['case_id'],'arm':r['arm']} for r in rows]}))
    def test_unknown_usage_is_not_reported_as_bill_or_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);self.fixture(out,None);r=summarize(out)
            self.assertEqual(r['planned_outputs'],72);self.assertEqual(r['total']['unknown_usage_calls'],1)
            self.assertIsNone(r['actual_bill_cny']);self.assertIsNone(r['expert_scores'])
    def test_peak_rate_arithmetic_and_missing_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);self.fixture(out,{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110});r=summarize(out)
            self.assertEqual(r['peak_estimate_cny_known'],'0.00028')
            rows=json.loads((out/'outputs.json').read_text());(out/'outputs.json').write_text(json.dumps(rows[:-1]))
            with self.assertRaises(ValueError):summarize(out)
