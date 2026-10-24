import json
import unittest
from app.ccare.research import (Claim, ContextRuleBaseline, StringPresenceBaseline,
    StructuredSemanticAdapter, StructuredStrategyAdapter, constraint_envelope)
from app.ccare.schemas import TurnRequest, State

class ResearchAdaptersTests(unittest.TestCase):
    def req(self, text, **kw):
        return TurnRequest(message=text, message_id='now', **kw)
    def claim(self, quote, **kw):
        return Claim(field='emotion', value='sad', message_id='now', quote=quote, **kw)

    def test_presence_does_not_claim_entailment(self):
        req=self.req('我并不难过');claim=self.claim('难过')
        self.assertTrue(StringPresenceBaseline().assess(req,claim)['located'])
        self.assertIsNone(StringPresenceBaseline().assess(req,claim)['semantic_verdict'])
        self.assertEqual(ContextRuleBaseline().assess(req,claim).verdict,'contradicted')

    def test_developer_counterexamples_and_positive_controls(self):
        for text, expected in [('我难过','supported'),('我并不难过','contradicted'),
            ('朋友说“我难过”','insufficient'),('以前我难过','insufficient'),
            ('我不是不难过','insufficient'),('假如我难过呢','insufficient')]:
            with self.subTest(text=text):
                self.assertEqual(ContextRuleBaseline().assess(self.req(text),self.claim('难过')).verdict, expected)

    def test_speaker_and_current_intent_gates_cannot_be_overridden(self):
        raw='{"verdict":"supported","reason":"direct","quote":"不要建议"}'
        for role, field, expected in [('assistant','emotion','speaker'),('user','support_intent','historical')]:
            req=self.req('今天先讨论课程',history=[{'role':role,'message_id':'old','content':'不要建议'}])
            claim=Claim(field=field,value='listen' if field=='support_intent' else 'sad',message_id='old',quote='不要建议')
            self.assertEqual(StructuredSemanticAdapter().parse(req,claim,raw).reason,expected)

    def test_structured_response_is_not_confidence_or_truth(self):
        adapter=StructuredSemanticAdapter();req=self.req('我心里堵得慌');claim=self.claim('堵得慌')
        self.assertEqual(ContextRuleBaseline().assess(req,claim).verdict,'insufficient')
        raw={'verdict':'supported','reason':'direct','quote':'堵得慌'}
        self.assertEqual(adapter.parse(req,claim,json.dumps(raw)).verdict,'supported')
        # This only validates a supplied model verdict, not its semantic accuracy.
        for changes in ({'confidence':.99},{'quote':'不存在'}, {'quote':''}):
            with self.assertRaises(ValueError): adapter.parse(req,claim,json.dumps(raw|changes))
        self.assertIn('说话人',adapter.messages(req,claim)[0]['content'])

    def test_selector_rejects_constraint_escape_and_invented_basis(self):
        req=self.req('不要给我建议',goal='draft');state=State()
        adapter=StructuredStrategyAdapter()
        for raw in ['{"selected":"draft","basis":["current_refusal"]}',
                    '{"selected":"listen","basis":["expert_approved"]}']:
            with self.assertRaises(ValueError): adapter.parse(req,state,raw)
        self.assertEqual(adapter.parse(req,state,'{"selected":"listen","basis":["current_refusal"]}').allowed,['listen'])

    def test_independent_risk_and_family_protection(self):
        for text, forbidden in [('我刚吃了一整瓶安眠药','listen'),('爸爸打我，我想写段话','draft')]:
            req=self.req(text,goal='draft');envelope=constraint_envelope(req,State())
            self.assertNotIn(forbidden,envelope.allowed)
            with self.assertRaises(ValueError):
                StructuredStrategyAdapter().parse(req,State(),json.dumps({'selected':forbidden,'basis':envelope.reasons}))

    def test_history_does_not_override_current_intent(self):
        req=self.req('现在我想写段话',history=[{'role':'user','content':'不要建议'}])
        self.assertEqual(constraint_envelope(req,State()).selected,'draft')
        req=self.req('不要建议',goal='draft')
        state=State(support_intent='draft')
        self.assertEqual(constraint_envelope(req,state).selected,'listen')

    def test_conflicting_evidence_abstains_and_newer_turn_supersedes(self):
        from app.ccare.research import reduce_field, EvidenceVerdict
        req=self.req('我不知道这算不算伤心',history=[{'message_id':'old','role':'user','content':'我难过'}])
        old=Claim(field='emotion',value='sad',message_id='old',quote='难过')
        now=self.claim('伤心')
        supported=EvidenceVerdict(verdict='supported',reason='direct',quote='难过')
        insufficient=EvidenceVerdict(verdict='insufficient',reason='ambiguous')
        self.assertEqual(reduce_field(req,'emotion',[(old,supported),(now,insufficient)]).value,'unknown')
        contradicted=EvidenceVerdict(verdict='contradicted',reason='negated',quote='伤心')
        self.assertEqual(reduce_field(req,'emotion',[(now,supported.model_copy(update={'quote':'伤心'})),(now,contradicted)]).status,'conflict')
        self.assertEqual(reduce_field(req,'emotion',[(old,supported)]).value,'sad')

    def test_risk_review_cannot_remove_independent_guard(self):
        from app.ccare.reviews import digest
        text='爸爸正在掐我。'
        req=self.req(text,reviews=[dict(field='risk',value='urgent',action='revoke',revision=1,
            source_message_id='now',source_digest=digest(text),source_text=text)])
        self.assertEqual(constraint_envelope(req,State()).allowed,['safety'])
