import json
import unittest
from unittest.mock import patch

import httpx
from pydantic import ValidationError

from app.ccare.config import Settings
from app.ccare.engine import Engine, local_state, output_violations
from app.ccare.policy import decide, locate, validate_state
from app.ccare.provider import Completion, ProviderUnavailable, RemoteProvider
from app.ccare.schemas import State, TurnRequest


class EvidencePolicyTests(unittest.TestCase):
    def test_current_evidence_has_exact_offsets(self):
        req = TurnRequest(message='我现在很难过，但不想听建议')
        evidence = locate(req, '很难过', 'state')
        self.assertEqual(req.message[evidence.start:evidence.end], evidence.quote)
        self.assertEqual(evidence.source, 'current')

    def test_assistant_history_is_not_evidence(self):
        req = TurnRequest(message='你好', history=[{'role':'assistant','content':'很难过'}])
        with self.assertRaises(ValueError):
            locate(req, '很难过', 'state')

    def test_old_intent_cannot_override_current_choice(self):
        req = TurnRequest(message='现在我希望写段话', goal='draft', history=[{'role':'user','content':'我只想倾听'}])
        state = State(support_intent='listen', intent_evidence=['我只想倾听'])
        with self.assertRaises(ValueError):
            validate_state(req, state)

    def test_model_intent_without_evidence_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_state(TurnRequest(message='你好'), State(support_intent='draft'))

    def test_refusal_overrides_model_and_interface(self):
        req = TurnRequest(message='不要给我建议', goal='draft')
        policy = decide(req, State(support_intent='draft'))
        self.assertEqual(policy.allowed, ['listen'])
        self.assertEqual(policy.selected, 'listen')
        self.assertIn('current_refusal', policy.reasons)

    def test_contact_restriction_beats_model_draft_intent(self):
        req = TurnRequest(message='爸爸打我，我想准备表达', goal='listen')
        policy = decide(req, State(family_unsafe=True, support_intent='draft'))
        self.assertNotIn('draft', policy.allowed)
        self.assertEqual(policy.selected, 'listen')

    def test_local_evidence_keeps_risk_outside_first_200_chars(self):
        req = TurnRequest(message='背景内容'*100+'爸爸打我')
        state = local_state(req)
        self.assertTrue(state.family_unsafe)
        self.assertIn('爸爸打我', state.evidence[0])

    def test_new_emergency_regressions_route_to_template(self):
        for message in ['我刚吃了一整瓶安眠药', '我今晚准备从这个世界消失，东西已经准备好了']:
            req = TurnRequest(message=message)
            self.assertEqual(decide(req, local_state(req)).selected, 'safety')

    def test_post_generation_rules_reject_advice_after_refusal(self):
        req = TurnRequest(message='不要给我建议')
        self.assertIn('unsolicited_advice', output_violations('建议你去联系妈妈', decide(req, State()), State()))

    def test_post_generation_rules_reject_parent_contact_when_unsafe(self):
        state = State(family_unsafe=True)
        req = TurnRequest(message='爸爸打我', goal='clarify')
        self.assertIn('unsafe_family_contact', output_violations('你可以主动联系爸爸', decide(req, state), state))


class ProviderContractTests(unittest.IsolatedAsyncioTestCase):
    def config(self):
        return Settings(_env_file=None, mode='remote', provider_kind='deepseek', api_key='synthetic-never-send',
                        api_base='https://api.deepseek.com', model='deepseek-flash', provider_label='DeepSeek',
                        provider_privacy_url='https://example.org/privacy')

    async def test_deepseek_non_thinking_json_mode_and_usage(self):
        captures = []
        def handler(request):
            captures.append(json.loads(request.content))
            return httpx.Response(200,json={'model':'returned-version','choices':[{'finish_reason':'stop','message':{'content':'{"safe":true,"violations":[]}'}}], 'usage':{'total_tokens':20,'prompt_cache_hit_tokens':5}})
        original = httpx.AsyncClient
        with patch('app.ccare.provider.httpx.AsyncClient',side_effect=lambda **kwargs: original(transport=httpx.MockTransport(handler),**kwargs)):
            result = await RemoteProvider(self.config()).complete([{'role':'user','content':'Return JSON'}],temperature=0,max_tokens=200,json_mode=True)
        self.assertEqual(captures[0]['thinking'], {'type':'disabled'})
        self.assertEqual(captures[0]['response_format'], {'type':'json_object'})
        self.assertEqual(result.model, 'returned-version')
        self.assertEqual(result.usage['prompt_cache_hit_tokens'], 5)

    async def test_provider_failures_are_actionable_without_secrets(self):
        original = httpx.AsyncClient
        for status,code in [(401,'invalid_key'),(402,'insufficient_balance'),(429,'rate_limited')]:
            with patch('app.ccare.provider.httpx.AsyncClient',side_effect=lambda **kwargs: original(transport=httpx.MockTransport(lambda r: httpx.Response(status,text='private-body-secret')),**kwargs)):
                with self.assertRaises(ProviderUnavailable) as caught:
                    await RemoteProvider(self.config()).complete([],temperature=0,max_tokens=200)
                self.assertEqual(caught.exception.code,code)
                self.assertEqual(str(caught.exception),'')

    async def test_truncated_response_never_reaches_engine(self):
        original = httpx.AsyncClient
        with patch('app.ccare.provider.httpx.AsyncClient',side_effect=lambda **kwargs: original(transport=httpx.MockTransport(lambda r: httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'partial'}}]})),**kwargs)):
            with self.assertRaises(ProviderUnavailable) as caught:
                await RemoteProvider(self.config()).complete([],temperature=0,max_tokens=200)
        self.assertEqual(caught.exception.code,'incomplete_output')

    async def test_deepseek_key_cannot_be_sent_to_a_different_host(self):
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, **{**self.config().model_dump(), 'api_base':'https://other.example/v1'})

    async def test_invalid_config_does_not_print_key(self):
        with self.assertRaises(ValidationError) as caught:
            Settings(_env_file=None, **{**self.config().model_dump(), 'api_key':'do-not-expose-this-key', 'api_base':'http://invalid.example'})
        self.assertNotIn('do-not-expose-this-key', str(caught.exception))
        self.assertNotIn('synthetic-never-send', repr(self.config()))

    async def test_malformed_choice_fails_closed(self):
        original = httpx.AsyncClient
        with patch('app.ccare.provider.httpx.AsyncClient',side_effect=lambda **kwargs: original(transport=httpx.MockTransport(lambda r: httpx.Response(200,json={'choices':['not-an-object']})),**kwargs)):
            with self.assertRaises(ProviderUnavailable) as caught:
                await RemoteProvider(self.config()).complete([],temperature=0,max_tokens=200)
        self.assertEqual(caught.exception.code,'invalid_response')

    async def test_stages_report_actual_model_usage_and_policy(self):
        outputs = [json.dumps({'emotion':'sad','evidence':['很难过'],'support_intent':'listen','intent_evidence':['不要给我建议']},ensure_ascii=False),'我听到你的难过了。愿意的话可以继续说。','{"safe":true,"violations":[]}']
        class Fixture:
            async def complete(self,*args,**kwargs):
                return Completion(outputs.pop(0),{'total_tokens':9},'fixture-version')
        req = TurnRequest(message='很难过，不要给我建议',goal='draft',eligible=True,external_consent=True)
        result = await Engine(self.config(),Fixture()).respond(req)
        self.assertEqual(result.mode,'remote')
        self.assertEqual(result.decision.allowed,['listen'])
        self.assertEqual([x.stage for x in result.stages],['state','generate','verify'])
        self.assertTrue(all(x.model=='fixture-version' for x in result.stages))
        self.assertEqual(sum(u['total_tokens'] for u in result.usage),27)

    async def test_remote_false_cannot_remove_local_family_guard(self):
        outputs = ['{"family_unsafe":false}', '我先听你说。', '{"safe":true,"violations":[]}']
        class Fixture:
            async def complete(self,*args,**kwargs): return Completion(outputs.pop(0))
        result = await Engine(self.config(),Fixture()).respond(TurnRequest(message='爸爸打我',goal='draft',eligible=True,external_consent=True))
        self.assertEqual(result.strategy,'listen')
        self.assertNotIn('draft',result.decision.allowed)
        self.assertTrue(any(e.purpose=='local_guard' for e in result.decision.evidence))
