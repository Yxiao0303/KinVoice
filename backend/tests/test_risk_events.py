import asyncio,unittest
from app.ccare.schemas import TurnRequest,ReviewEntry
from app.ccare.reviews import digest
from app.ccare.risk_events import bind_risk_events
from app.ccare.engine import local_state,Engine
from app.ccare.config import Settings

class RiskEventTests(unittest.TestCase):
    def request(self,message='朋友已经安全到家。',history=None,reviews=None):
        return TurnRequest(message_id='now',message=message,history=history or [{'message_id':'old','role':'user','content':'朋友说“爸爸正在掐我”。'}],reviews=reviews or [])
    def test_same_subject_same_single_event_resolves_only_that_span(self):
        req=self.request();event=bind_risk_events(req)[0]
        self.assertEqual(event.status,'resolved');self.assertEqual(local_state(req).risk,'unknown')
        self.assertEqual(event.evidence.message_id,'old');self.assertEqual(event.update_evidence.message_id,'now')
        self.assertEqual(event.event_id,bind_risk_events(req)[0].event_id)
        self.assertEqual(req.history[0].content[event.evidence.start:event.evidence.end],event.evidence.quote)
        self.assertEqual(event.source_digest,digest(req.history[0].content))
    def test_new_danger_and_independent_self_harm_override_resolution(self):
        for text in ['朋友已经安全到家。爸爸正在掐我。','朋友已经安全到家，但我刚吃了一整瓶安眠药。','朋友说“爸爸又正在掐我”。']:
            with self.subTest(text=text):self.assertEqual(local_state(self.request(text)).risk,'urgent')
        req=self.request(history=[{'message_id':'old','role':'user','content':'朋友说“爸爸正在掐我”。我想死。'}])
        self.assertEqual(bind_risk_events(req)[0].status,'resolved');self.assertEqual(local_state(req).risk,'urgent')
    def test_different_named_friends_do_not_merge(self):
        req=self.request('朋友小林已经安全到家。',[
            {'message_id':'a','role':'user','content':'朋友小林说“爸爸正在掐我”。'},
            {'message_id':'b','role':'user','content':'朋友小周说“爸爸正在打我”。'}])
        self.assertEqual([e.status for e in bind_risk_events(req)],['resolved','active'])
        self.assertEqual(local_state(req).risk,'urgent')
    def test_ambiguous_pronoun_keeps_pending_and_one_proportionate_question(self):
        req=self.request('她已经安全到家。');state=local_state(req)
        self.assertEqual(state.risk,'unknown');self.assertTrue(state.needs_clarification)
        self.assertEqual(bind_risk_events(req)[0].status,'pending_resolution')
        class Never:
            async def complete(self,*a,**k):raise AssertionError('no paid model')
        settings=Settings(_env_file=None,mode='disabled',api_key='').model_copy(update={'mode':'remote'})
        result=asyncio.run(Engine(settings,Never()).respond(req))
        self.assertEqual(result.strategy,'clarify');self.assertEqual(result.reply.count('？'),1)
        self.assertEqual(result.model_calls,0);self.assertEqual(result.state.risk,'unknown')
    def test_two_same_subject_events_need_provenance_and_keep_other_active(self):
        old='朋友说“爸爸正在掐我”。'
        history=[{'message_id':'a','role':'user','content':old},{'message_id':'b','role':'user','content':'朋友说“爸爸正在打我”。'}]
        req=self.request(history=history)
        self.assertTrue(all(e.status=='pending_resolution' for e in bind_risk_events(req)))
        review=ReviewEntry(field='risk',value='unknown',action='correct',source_message_id='a',source_text=old,source_digest=digest(old),revision=1)
        req=self.request(history=history,reviews=[review])
        self.assertEqual([e.status for e in bind_risk_events(req)],['resolved','active'])
        self.assertEqual(local_state(req).risk,'urgent')
    def test_review_alone_never_clears_and_withdrawing_update_restores_guard(self):
        old='朋友说“爸爸正在掐我”。'
        rev=ReviewEntry(field='risk',value='unknown',action='revoke',source_message_id='old',source_text=old,source_digest=digest(old),revision=1)
        self.assertEqual(local_state(self.request('先听我说。',reviews=[rev])).risk,'urgent')
        current='朋友已经安全到家。'
        update=ReviewEntry(field='risk',value='unknown',action='revoke',source_message_id='now',source_text=current,source_digest=digest(current),revision=1)
        self.assertEqual(local_state(self.request(reviews=[update])).risk,'urgent')
    def test_other_generic_friend_and_assistant_text_cannot_prove_resolution(self):
        req=self.request(history=[{'message_id':'a','role':'user','content':'朋友说“爸爸正在掐我”。'}, {'message_id':'b','role':'user','content':'另一位朋友给我打了电话。'}])
        self.assertEqual(bind_risk_events(req)[0].status,'pending_resolution')
        req=self.request('先听我说。',history=[{'role':'user','content':'朋友说“爸爸正在掐我”。'},{'role':'assistant','content':'朋友已经安全到家。'}])
        self.assertEqual(local_state(req).risk,'urgent')
    def test_unique_ids_and_digest_validation_prevent_forged_source(self):
        old='朋友说“爸爸正在掐我”。'
        with self.assertRaises(ValueError):self.request(reviews=[ReviewEntry(field='risk',value='unknown',action='correct',source_message_id='wrong',source_text=old,source_digest=digest(old),revision=1)])
    def test_resolution_survives_next_turn_and_new_event_reopens(self):
        history=[{'message_id':'a','role':'user','content':'朋友说“爸爸正在掐我”。'},
                 {'message_id':'b','role':'user','content':'朋友已经安全到家。'}]
        req=self.request('谢谢，我想聊点别的。',history)
        self.assertEqual(local_state(req).risk,'unknown');self.assertEqual(bind_risk_events(req)[0].status,'resolved')
        self.assertEqual(bind_risk_events(req)[0].update_evidence.source,'history')
        req=self.request('朋友说“爸爸正在打我”。',history)
        self.assertEqual(local_state(req).risk,'urgent')
        history.append({'message_id':'c','role':'user','content':'朋友说“爸爸正在打我”。'})
        req=self.request('我暂时不知道后续。',history)
        self.assertEqual([e.status for e in bind_risk_events(req)],['resolved','active'])
        self.assertEqual(local_state(req).risk,'urgent')
    def test_revoked_historical_resolution_is_not_replayed(self):
        update='朋友已经安全到家。'
        history=[{'message_id':'a','role':'user','content':'朋友说“爸爸正在掐我”。'}, {'message_id':'b','role':'user','content':update}]
        rev=ReviewEntry(field='risk',value='unknown',action='revoke',source_message_id='b',source_text=update,source_digest=digest(update),revision=2)
        self.assertEqual(local_state(self.request('我更正之前的说法。',history,reviews=[rev])).risk,'urgent')
    def test_old_risk_confirmation_cannot_resurrect_resolved_event(self):
        old='朋友说“爸爸正在掐我”。'
        rev=ReviewEntry(field='risk',value='urgent',action='confirm',source_message_id='old',source_text=old,source_digest=digest(old),revision=1)
        req=self.request(reviews=[rev])
        result=asyncio.run(Engine(Settings(_env_file=None,mode='demo',api_key='')).respond(req))
        self.assertEqual(result.state.risk,'unknown')
        self.assertEqual(result.review_outcomes[0]['status'],'superseded')
    def test_many_scoped_events_keep_audit_but_bound_state_assessments(self):
        req=self.request('她已经安全到家。',history=[{'role':'user','content':'朋友说“爸爸正在掐我”。'*31}])
        self.assertEqual(len(bind_risk_events(req)),31)
        state=local_state(req)
        self.assertEqual(state.risk,'unknown');self.assertEqual(len(state.assessments),30)
