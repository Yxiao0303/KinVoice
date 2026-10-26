"""Seen synthetic development controls; no new trained-model evaluation."""
import unittest
from app.ccare.student import respond_student,RuleStudentJudge
from app.ccare.student_schemas import StudentRequest,StudentProfile

def req(current,history):
    return StudentRequest(message_id='u:99',message=current,student=StudentProfile(adult_confirmed=True),history=[{'message_id':f'u:{i+1}','role':'user','content':s} for i,s in enumerate(history)])
def field(event,name='student_subject'):return next(c for c in event.claims if c.field==name)
class StudentCorrectionsTests(unittest.TestCase):
    def test_original_seen_counterexample_and_followup(self):
        original='这次考试后妈妈说我不努力。';correction='那句话是我爸说的。'
        for request in [req(correction,[original]),req('继续。',[original,correction])]:
            r=respond_student(request);old,new=r.student_judgment.events[:2]
            self.assertFalse(old.active);self.assertNotIn(old.event_id,r.student_judgment.basis_event_ids)
            self.assertEqual(field(new).value,'father');self.assertEqual(field(new).status,'confirmed')
            self.assertTrue(field(new).supersedes.startswith(old.event_id))
            self.assertEqual(field(new).evidence[0].quote,correction)
            self.assertEqual(field(new,'student_pressure').value,'unknown')
        class UncertainJudge:
            def extract(self,request):
                j=RuleStudentJudge().extract(request)
                c=field(j.events[0]);c.value='unknown';c.status='unknown';c.evidence=[]
                return j
        r=respond_student(req(correction,[original]),judge=UncertainJudge())
        self.assertFalse(r.student_judgment.events[0].active)
        self.assertEqual(field(r.student_judgment.events[1]).value,'father')
    def test_multiple_messages_are_not_bound_by_recency(self):
        r=respond_student(req('那句话是我爸说的。',['妈妈说我不努力。','老师说我缺交作业。']))
        self.assertTrue(all(e.active for e in r.student_judgment.events[:2]))
        self.assertFalse(r.student_judgment.events[-1].active)
        self.assertIn('未能唯一绑定',''.join(r.student_judgment.uncertainties))
    def test_exact_quote_selects_one_subject_not_other_event(self):
        r=respond_student(req('“不努力”是爸爸说的。',['妈妈说我不努力。','老师说我缺交作业。']))
        a,b,c=r.student_judgment.events
        self.assertFalse(a.active);self.assertTrue(b.active);self.assertEqual(field(b).value,'teacher');self.assertEqual(field(c).value,'father')
    def test_multi_event_message_and_duplicate_quotes_remain_unresolved(self):
        for history in [['妈妈说我不努力。爸爸说我应该加课。'],['妈妈说我不努力。','老师说我不努力。']]:
            r=respond_student(req('“不努力”是爸爸说的。',history))
            self.assertTrue(all(e.active for e in r.student_judgment.events[:-1]))
            self.assertFalse(r.student_judgment.events[-1].active)
    def test_denial_third_party_hypothetical_are_not_corrections(self):
        for text in ['那句话不是我爸说的。','我不是说那句话是我爸说的。','朋友说“那句话是我爸说的”。','如果那句话是我爸说的呢？']:
            r=respond_student(req(text,['妈妈说我不努力。']))
            self.assertTrue(r.student_judgment.events[0].active)
            self.assertEqual(field(r.student_judgment.events[0]).value,'mother')
            self.assertEqual(field(r.student_judgment.events[-1]).value,'unknown')
    def test_ui_revision_beats_text_and_revocation_never_resurrects(self):
        request=req('那句话是我爸说的。',['妈妈说我不努力。']);r=respond_student(request)
        for action,value in [('correct','teacher'),('revoke','father')]:
            target=next(t for t in r.review_targets if t['field']=='student_subject')
            body=request.model_dump();body['reviews']=[target|{'action':action,'value':value,'revision':1}]
            result=respond_student(StudentRequest.model_validate(body))
            self.assertFalse(result.student_judgment.events[0].active)
            self.assertEqual(field(result.student_judgment.events[1]).value,'teacher' if action=='correct' else 'unknown')
        target=next(t for t in r.review_targets if t['field']=='student_event')
        body=request.model_dump();body['reviews']=[target|{'action':'revoke','revision':1}]
        result=respond_student(StudentRequest.model_validate(body))
        self.assertFalse(any(e.active for e in result.student_judgment.events))
    def test_unrelated_and_new_risk_not_cleared(self):
        for request in [req('那句话是我爸说的。',['妈妈说我不努力。','室友正在掐我。']),req('那句话是我爸说的。爸爸正在掐我。',['妈妈说我不努力。'])]:
            self.assertEqual(respond_student(request).strategy,'safety')
