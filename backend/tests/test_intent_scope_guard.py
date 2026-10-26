import json,unittest
from pathlib import Path
from app.ccare.intent_scope import scoped_current_intent
from app.ccare.policy import decide
from app.ccare.engine import local_state,output_violations
from app.ccare.schemas import TurnRequest,State

class IntentScopeGuardTests(unittest.TestCase):
    def decision(self,text,goal='listen',state=None,history=None):
        req=TurnRequest(message=text,goal=goal,history=history or [])
        return req,decide(req,state or local_state(req))
    def test_seen_real_case_now_has_listen_only_mask_without_inventing_emotion(self):
        p=Path(__file__).resolve().parents[2]/'research/three-arm-v1/case.json'
        req=TurnRequest.model_validate(json.loads(p.read_text())['request']);state=State()
        d=decide(req,state)
        self.assertEqual(d.allowed,['listen']);self.assertEqual(d.selected,'listen')
        self.assertEqual(state.emotion,'unknown');self.assertEqual(state.support_intent,'unknown')
        e=d.evidence[-1];self.assertEqual(req.message[e.start:e.end],e.quote)
    def test_attribution_and_past_do_not_poison_separate_current_directive(self):
        for text in ['朋友说“不要给我建议”。我现在只想倾听。',
                     '昨天我想写段话。先听我说，不要给我建议。',
                     '朋友说她很烦，先别给建议。我只想倾听。']:
            with self.subTest(text=text):self.assertEqual(self.decision(text,goal='draft')[1].allowed,['listen'])
    def test_quoted_historical_negated_or_hypothetical_preferences_are_not_current_refusals(self):
        for text in ['朋友说“不要给我建议”。','昨天我不要建议。','我不是不要给我建议。',
                     '朋友说不要给我建议。','我并非只想倾听。','如果我只想倾听呢？']:
            with self.subTest(text=text):self.assertEqual(scoped_current_intent(text).value,'unknown')
    def test_current_revision_and_next_turn_can_request_advice(self):
        for text in ['不要给我建议，但现在我想写段话。',
                     '先听我说。我改主意了，帮我写一段话。',
                     '不要建议，现在请给我一些表达边界的建议。','不要只听我说，帮我写一段话。']:
            req,d=self.decision(text)
            self.assertNotEqual(d.selected,'listen');self.assertNotEqual(d.allowed,['listen'])
        _,d=self.decision('帮我写一段话。',history=[{'role':'user','content':'不要给我建议'}])
        self.assertEqual(d.selected,'draft')
    def test_listen_now_advice_later_is_not_a_permanent_ban(self):
        for text in ['先听我说，然后再给建议。','先听我说完然后再给建议。','先听我说再帮我写段话。']:
            _,d=self.decision(text,goal='draft')
            self.assertEqual(d.allowed,['listen'])
        _,later=self.decision('现在请给我一些建议。')
        self.assertIn('clarify',later.allowed);self.assertEqual(later.selected,'clarify')
    def test_independent_safety_and_family_constraint_survive_current_intent(self):
        for text in ['爸爸正在掐我。不要给我建议。','我刚吃了一整瓶安眠药，先听我说。']:
            _,d=self.decision(text);self.assertEqual(d.allowed,['safety'])
        _,d=self.decision('爸爸监控我的手机，现在我想写段话。')
        self.assertNotIn('draft',d.allowed)
    def test_chosen_listen_alone_does_not_justify_removing_all_other_strategies(self):
        _,d=self.decision('我还没想清楚。')
        self.assertEqual(d.selected,'listen');self.assertNotEqual(d.allowed,['listen'])
    def test_output_checks_are_independent_of_correct_mask(self):
        _,d=self.decision('不要给我建议。')
        self.assertIn('unsolicited_advice',output_violations('建议你先给父母发消息。',d,State()))
    def test_evidence_points_to_current_directive_not_identical_quoted_words(self):
        text='朋友说“不要给我建议”。我现在不要给我建议。'
        req,d=self.decision(text)
        self.assertEqual(d.allowed,['listen'])
        self.assertGreater(d.evidence[-1].start,text.index('不要给我建议'))
        self.assertEqual(req.message[d.evidence[-1].start:d.evidence[-1].end],d.evidence[-1].quote)
    def test_quoted_revision_does_not_revoke_users_actual_refusal(self):
        _,d=self.decision('不要给我建议。朋友说“现在请帮我写段话”。')
        self.assertEqual(d.allowed,['listen'])
    def test_engine_rejects_bad_output_even_after_correct_mask(self):
        import asyncio
        from app.ccare.engine import Engine
        from app.ccare.config import Settings
        from app.ccare.provider import Completion
        class Fixture:
            calls=0
            async def complete(self,*args,**kwargs):
                self.calls+=1
                return Completion('{}' if kwargs.get('json_mode') else '建议你联系父母。',None,'offline')
        p=Fixture();config=Settings(_env_file=None,api_key='',mode='disabled').model_copy(update={'mode':'remote'})
        req=TurnRequest(message='昨天我想写信。现在先听我说，不要给我建议。',external_consent=True)
        result=asyncio.run(Engine(config,p,generation_attempts=1).respond(req))
        self.assertEqual(result.decision.allowed,['listen'])
        self.assertEqual(result.mode,'safe_fallback');self.assertEqual(p.calls,2)
    def test_unresolved_same_turn_conflict_does_not_authorize_unwanted_advice(self):
        state=State(support_intent='draft')
        _,d=self.decision('不要给我建议，帮我写一段话。',goal='draft',state=state)
        self.assertEqual(d.allowed,['listen'])
        self.assertEqual(state.emotion,'unknown')
