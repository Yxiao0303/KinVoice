"""AI-synthetic/unreviewed development regression; no external models or holdout."""
import json,tempfile,unittest
from pathlib import Path
from fastapi.testclient import TestClient
from app.ccare.student_schemas import StudentRequest,StudentProfile
from app.ccare.student import respond_student,RuleStudentJudge,STAGES
from app.ccare.api import create_app
from app.ccare.config import Settings
from app.ccare.reviews import digest

ROOT=Path(__file__).resolve().parents[2]
def request(message='这次考试没考好，妈妈说我不努力。',**kw):
    return StudentRequest(message=message,message_id='u:1',student=StudentProfile(adult_confirmed=True),**kw)
def claim(result,field,index=0):
    return next(c for c in result.student_judgment.events[index].claims if c.field==field)
def review(result,field,action,value=None):
    t=next(t for t in result.review_targets if t['field']==field)
    return t|{'action':action,'value':value or t['value'],'revision':t['revision']+1}

class StudentP1Tests(unittest.TestCase):
    def test_versioned_development_cases(self):
        for case in map(json.loads,(ROOT/'research/student-p1-v1/development.jsonl').read_text().splitlines()):
            with self.subTest(case=case['id']):
                r=respond_student(request(case['message'],support=case['support']))
                self.assertEqual(r.strategy,case['expected_action']);self.assertEqual(r.model_calls,0)
                self.assertEqual(r.student_judgment.method,'conservative_rules_unvalidated')
                self.assertIn('离线规则',r.reply)
    def test_evidence_scope_unknown_and_no_diagnosis(self):
        r=respond_student(request())
        self.assertEqual(claim(r,'student_pressure').value,'academic_family')
        self.assertEqual(claim(r,'student_subject').value,'mother')
        self.assertEqual(claim(r,'student_impact').value,'unknown')
        self.assertEqual(r.state.risk,'unknown')
        self.assertEqual(r.student_judgment.need_origin,'user_choice')
        for e in r.student_judgment.events:
            for c in e.claims:
                for x in c.evidence:self.assertEqual(request().message[x.start:x.end],x.quote)
        for text in ['朋友说“我睡不着”。','以前我睡不着。','假如我睡不着呢？','我不是睡不着。']:
            self.assertEqual(claim(respond_student(request(text)),'student_impact').value,'unknown')
        self.assertEqual(claim(respond_student(request('我最近睡不着。')),'student_impact').value,'sleep')
    def test_source_bound_correction_and_event_revocation_propagation(self):
        original=request();r=respond_student(original)
        corrected=review(r,'student_subject','correct','father')
        follow=StudentRequest(message='继续这件事。',message_id='u:3',history=[{'message_id':'u:1','role':'user','content':original.message}],student=original.student,reviews=[corrected])
        r2=respond_student(follow)
        self.assertEqual(claim(r2,'student_subject').value,'father');self.assertEqual(claim(r2,'student_subject').status,'confirmed')
        tombstone=review(r2,'student_event','revoke')
        r3=respond_student(follow.model_copy(update={'reviews':[type(follow.reviews[0]).model_validate(corrected),type(follow.reviews[0]).model_validate(tombstone)]}))
        event=r3.student_judgment.events[0]
        self.assertFalse(event.active);self.assertNotIn(event.event_id,r3.student_judgment.basis_event_ids)
        self.assertTrue(all(c.value=='unknown' and c.status=='revoked' for c in event.claims))
        self.assertNotIn('爸爸',r3.reply);self.assertNotIn('妈妈',r3.reply)
    def test_revision_is_local_does_not_clear_unrelated_or_new_event(self):
        old=request('这次考试后妈妈批评我。');r=respond_student(old)
        revoke=review(r,'student_event','revoke')
        req=StudentRequest(message='今天另一件事是爸爸批评我。',message_id='u:3',history=[{'message_id':'u:1','role':'user','content':old.message}],student=old.student,reviews=[revoke])
        r=respond_student(req)
        self.assertFalse(r.student_judgment.events[0].active);self.assertTrue(r.student_judgment.events[1].active)
        self.assertEqual(claim(r,'student_subject',1).value,'father')
    def test_revocation_never_disables_independent_risk(self):
        old=request('爸爸正在掐我，先听我说。');r=respond_student(old)
        req=StudentRequest(message='我不想说了。',message_id='u:3',history=[{'message_id':'u:1','role':'user','content':old.message}],student=old.student,reviews=[review(r,'student_event','revoke')])
        self.assertEqual(respond_student(req).strategy,'safety')
    def test_forged_review_rejected_and_adapter_cannot_invent_provenance(self):
        r=respond_student(request());bad=review(r,'student_subject','correct','father');bad['source_digest']='0'*64
        with self.assertRaises(ValueError):request(reviews=[bad])
        class BadJudge:
            def extract(self,req):
                j=RuleStudentJudge().extract(req);j.events[0].claims[0].status='confirmed';return j
        bad=respond_student(request(),judge=BadJudge())
        self.assertEqual(bad.failure_code,'student_judgment_invalid');self.assertEqual(bad.mode,'safe_fallback')
        self.assertEqual(bad.student_judgment.events,[])
        safety=respond_student(request('爸爸正在掐我。'),judge=BadJudge())
        self.assertEqual(safety.strategy,'safety')
        self.assertTrue(safety.decision.evidence)
    def test_design_stage_conditioning_is_not_public_access(self):
        for stage in ('middle','high'):
            self.assertTrue(STAGES[stage]['design_only'])
            req=request().model_copy(update={'student':StudentProfile(stage=stage)})
            self.assertIn('仅适龄设计样例',respond_student(req).reply)
    def test_api_admission_privacy_and_no_provider_even_remote_config(self):
        class NeverProvider:
            async def complete(self,*a,**kw):raise AssertionError('student must not call provider')
        with tempfile.TemporaryDirectory() as tmp:
            cfg=Settings(_env_file=None,mode='remote',api_key='offline-never-used',api_base='https://offline.invalid',model='offline',provider_label='offline',provider_privacy_url='https://offline.invalid',auth_db=Path(tmp)/'auth.db')
            with TestClient(create_app(cfg,NeverProvider())) as client:
                token=client.post('/auth/register',json={'username':'student_fixture','password':'synthetic-password'}).json()['access_token'];headers={'Authorization':'Bearer '+token}
                body=request(eligible=True).model_dump()
                self.assertEqual(client.post('/support/student',json=body).status_code,401)
                for profile in [{'stage':'middle','adult_confirmed':True},{'stage':'high','adult_confirmed':True},{'stage':'university','adult_confirmed':False}]:
                    response=client.post('/support/student',headers=headers,json=body|{'student':profile})
                    self.assertEqual(response.status_code,403)
                response=client.post('/support/student',headers=headers,json=body)
                self.assertEqual(response.status_code,200);self.assertEqual(response.json()['model_calls'],0)
                self.assertEqual(client.post('/support/turn',headers=headers,json=body).status_code,422)
                self.assertEqual(client.get('/account/export',headers=headers).json()['conversations'],[])
                import sqlite3
                with sqlite3.connect(cfg.auth_db) as db:self.assertNotIn(body['message'],'\n'.join(db.iterdump()))
