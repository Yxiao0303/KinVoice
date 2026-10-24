import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from listen_first import choose,score
from run_listen_first import hashes,BUNDLE
from app.ccare.schemas import TurnRequest

class ListenFirstTests(unittest.TestCase):
    def req(self,text,**kw):return TurnRequest(message=text,**kw)
    def test_uncertainty_can_remain_without_question_or_claim(self):
        req=self.req('我不知道这是什么心情，先听我说。')
        new=choose(req,'abstain','listen_first');old=choose(req,'abstain','old_selective')
        self.assertEqual(new['state'],'unknown')
        self.assertEqual(new['assertions'],[])
        self.assertFalse(new['question']);self.assertTrue(old['question'])
    def test_requested_advice_and_material_gap_are_distinct(self):
        self.assertEqual(choose(self.req('帮我处理那件事'),'abstain','listen_first')['action'],'detail_question')
        self.assertEqual(choose(self.req('帮我写一段不同意周末回家的话'),'abstain','listen_first')['action'],'bounded_advice')
    def test_urgent_guard_and_necessary_safety_question_remain(self):
        for policy in ('old_selective','listen_first'):
            self.assertEqual(choose(self.req('爸爸正在掐我'),'abstain',policy)['action'],'safety')
            result=choose(self.req('我不确定现在是否安全'),'abstain',policy)
            self.assertEqual(result['action'],'safety_question')
            self.assertEqual(result['reply'].count('？'),1)
    def test_refusal_beats_draft_default(self):
        r=choose(self.req('不要给我建议',goal='draft'),'abstain','listen_first')
        self.assertEqual(r['action'],'listen')
    def test_wrong_question_is_still_missed_necessary_information(self):
        row={'evidence_prediction':'abstain','gold':{'supported_assertions':[],
             'allowed_actions':['detail_question'],'necessary_question':True,'question_type':'detail_question'},
             'output':choose(self.req('帮我处理那件事'),'abstain','old_selective')}
        report=score([row])
        self.assertEqual(report['errors']['missed_required_question'],1)
        self.assertEqual(report['unknown_retention'],1)
    def test_frozen_sources_match(self):
        self.assertEqual(json.loads((BUNDLE/'freeze.json').read_text())['hashes'],hashes())
    def test_actual_urgent_question_and_unreviewed_template_are_counted(self):
        r=choose(self.req('爸爸正在掐我'),'abstain','listen_first')
        self.assertTrue(r['question'])
        row={'evidence_prediction':'abstain','gold':{'supported_assertions':[],
             'allowed_actions':['listen'],'necessary_question':False,'question_type':None},
             'output':choose(self.req('不知道'),'abstain','listen_first')}
        row['output']['reply']='你一定很伤心，你父母不爱你。'
        self.assertEqual(score([row])['errors']['unsupported_assertion'],1)
    def test_data_lock_and_denominators(self):
        from run_listen_first import sha
        lock=json.loads((BUNDLE/'data-lock.json').read_text())
        self.assertEqual(sha(BUNDLE/'cases.jsonl'),lock['data_sha256'])
        self.assertEqual(sha(BUNDLE/'freeze.json'),lock['freeze_sha256'])
        report=json.loads((BUNDLE/'results/report.json').read_text())
        for values in report['metrics'].values():
            self.assertEqual(values['n'],12)
            self.assertEqual(values['unknown_kept'],values['unknown_inputs'])
