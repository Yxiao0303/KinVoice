"""Small synthetic development regressions, not independent effect evaluation."""
import asyncio
import unittest

from app.ccare.config import Settings
from app.ccare.engine import Engine, local_state, output_violations
from app.ccare.policy import validate_state, decide
from app.ccare.reviews import apply_reviews, digest
from app.ccare.schemas import State, TurnRequest

OLD = '我有些伤心。'


def revoked_request(current='我想先听听。'):
    return TurnRequest(message_id='current', message=current,
        history=[{'message_id':'old','role':'user','content':OLD}],
        reviews=[dict(field='emotion',value='sad',action='revoke',revision=1,
            source_message_id='old',source_digest=digest(OLD),source_text=OLD)])


def apply(req, state):
    links=validate_state(req,state)
    apply_reviews(req,state,links,local_state(req))
    return state,decide(req,state,links)


class RevocationSemanticDevelopmentTests(unittest.TestCase):
    def test_synonyms_negation_reported_and_temporal_claims_are_not_resurrected(self):
        state,decision=apply(revoked_request(),State(emotion='sad',evidence=['伤心']))
        cases = [
            '你现在很失落。', '听起来你的心情很低落。', '你仍然感到委屈。',
            '你并不伤心。', '你不是不伤心。',
            '朋友说你现在很伤心。', '你以前伤心，现在仍然如此。',
            '我不会再用“伤心”描述你，但你现在很失落。',
            '我不会不再用“伤心”描述你。',
        ]
        for output in cases:
            with self.subTest(output=output):
                self.assertIn('revoked_emotion_reference',output_violations(output,decision,state))

    def test_neutral_support_and_explicit_revocation_acknowledgement_allowed(self):
        state,decision=apply(revoked_request(),State(emotion='sad',evidence=['伤心']))
        for output in ['我会按你现在的表达理解，你可以慢慢说。',
                       '我不会再用“伤心”描述你。你可以纠正我的理解。']:
            with self.subTest(output=output):
                self.assertNotIn('revoked_emotion_reference',output_violations(output,decision,state))

    def test_ambiguous_third_party_mentions_remain_conservatively_blocked(self):
        state,decision=apply(revoked_request(),State(emotion='sad',evidence=['伤心']))
        # This rule cannot establish quotation attribution from State alone.
        self.assertIn('revoked_emotion_reference',output_violations('妈妈很伤心。',decision,state))

    def test_new_current_supported_emotion_supersedes_old_revocation(self):
        state,decision=apply(revoked_request('我现在很生气。'),State(emotion='angry',evidence=['生气']))
        self.assertEqual(state.emotion,'angry')
        self.assertNotIn('revoked_emotion_reference',output_violations('你说现在很生气。',decision,state))

    def test_negated_quoted_historical_input_cannot_reactivate_old_emotion(self):
        for current in ['我现在并不伤心。','朋友说她很伤心。','昨天我很伤心。']:
            with self.subTest(current=current):
                state,_=apply(revoked_request(current),State(emotion='sad',evidence=['伤心']))
                self.assertEqual(state.emotion,'unknown')

    def test_new_urgent_risk_after_revocation_is_zero_call_safety_route(self):
        class NoCalls:
            async def complete(self,*args,**kwargs):
                raise AssertionError('independent urgent route must not call provider')
        for current in ['我现在想死。','爸爸正在掐我。']:
            with self.subTest(current=current):
                result=asyncio.run(Engine(Settings(_env_file=None),NoCalls()).respond(revoked_request(current)))
                self.assertEqual(result.mode,'safety_template')
                self.assertEqual(result.model_calls,0)
                self.assertEqual(result.state.risk,'urgent')

    def test_risk_revocation_cannot_clear_current_guard(self):
        text='爸爸正在掐我。'
        req=TurnRequest(message_id='current',message=text,reviews=[
            dict(field='risk',value='urgent',action='revoke',revision=1,source_message_id='current',
                 source_digest=digest(text),source_text=text)])
        result=asyncio.run(Engine(Settings(_env_file=None)).respond(req))
        self.assertEqual(result.mode,'safety_template')
        self.assertTrue(result.review_outcomes[0]['independent_guard_preserved'])
