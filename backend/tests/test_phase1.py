import asyncio
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from app.ccare.engine import Engine, local_state
from app.ccare.policy import decide, validate_state
from app.ccare.schemas import State, TurnRequest
from app.ccare.semantics import RuleSemanticJudge
import test_ccare
from test_ccare import configuration
import test_policy_integration
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from benchmark_ccare import load_cases, summarize, BudgetProvider, execute, CONDITIONS
from app.ccare.provider import Completion, ProviderUnavailable, RemoteProvider
import httpx

class SemanticTests(unittest.TestCase):
    def test_conservative_semantic_branches(self):
        judge = RuleSemanticJudge()
        for text, expected in [('我很难过','supported'),('我不是很难过','contradicted'),
            ('老师说“我很难过”','insufficient'),('假如我很难过','insufficient'),
            ('我不是不难过','insufficient'),('我很难过才怪','insufficient'),('以前我很难过','insufficient')]:
            self.assertEqual(judge.assess('emotion','sad',text),expected)

    def test_located_quote_does_not_prove_emotion(self):
        req=TurnRequest(message='我不是很难过')
        state=State(emotion='sad',evidence=['很难过'])
        links=validate_state(req,state)
        self.assertEqual(state.emotion,'unknown')
        self.assertTrue(state.needs_clarification)
        self.assertEqual(state.assessments[0].verdict,'contradicted')
        self.assertEqual(links[0].message_id,'current:0')

    def test_current_correction_and_quoted_refusal(self):
        for message in ['老师说“不要给我建议”','并非不要给我建议','不要给我建议，但现在我想写段话']:
            self.assertEqual(decide(TurnRequest(message=message,goal='draft'),State()).selected,'draft')
        req=TurnRequest(message='不要给我建议',goal='draft')
        self.assertEqual(decide(req,State()).selected,'listen')

    def test_semantic_uncertainty_cannot_disable_crisis_guard(self):
        req=TurnRequest(message='朋友说“我想死”')
        self.assertEqual(RuleSemanticJudge().assess('risk','urgent',req.message),'insufficient')
        self.assertEqual(decide(req,local_state(req)).selected,'safety')

class BenchmarkTests(unittest.IsolatedAsyncioTestCase):
    def test_synthetic_contract_and_denominator(self):
        cases=load_cases(Path(__file__).resolve().parents[2]/'data/development/family_stress_v1.jsonl')
        self.assertEqual(len(cases),9)
        summary=summarize([{'status':'failed','model_calls':1},{'status':'dry_run','model_calls':0}])
        self.assertEqual(summary['samples'],2)
        self.assertTrue(all(v=='unavailable' for v in summary['expert_metrics'].values()))
        self.assertIsNone(summary['cost'])

    async def test_budget_never_exceeds_authorized_calls(self):
        class Fake:
            async def complete(self,*a,**k): return Completion('fixture')
        provider=BudgetProvider(Fake(),1)
        await provider.complete([])
        with self.assertRaises(ProviderUnavailable): await provider.complete([])
        self.assertEqual(provider.calls,1)
        self.assertIsNone(provider.records[0]['usage'])

    async def test_every_condition_executes_with_mock_only(self):
        cases=load_cases(Path(__file__).resolve().parents[2]/'data/development/family_stress_v1.jsonl')
        class Fake:
            async def complete(self,messages,**kwargs):
                if '仅返回JSON' in messages[0]['content']:
                    return Completion('{"safe":true,"violations":[]}' if '候选' in messages[0]['content'] else '{}')
                return Completion('我先听你说。')
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            for condition in CONDITIONS:
                provider=BudgetProvider(Fake(),5)
                reply,status,failure=await execute(cases[0],condition,configuration(tmp,'remote'),provider)
                self.assertTrue(reply)
                self.assertIsNone(failure,condition)
                self.assertLessEqual(provider.calls,5)

class ProviderEdgeTests(unittest.IsolatedAsyncioTestCase):
    config = test_policy_integration.ProviderContractTests.config
    async def test_empty_invalid_json_timeout_and_connection_are_sanitized(self):
        original=httpx.AsyncClient
        responses=[httpx.Response(200,text='private invalid json'),httpx.Response(200,json={'choices':[{'message':{'content':''}}]})]
        for response in responses:
            with patch('app.ccare.provider.httpx.AsyncClient',side_effect=lambda **kw: original(transport=httpx.MockTransport(lambda r:response),**kw)):
                with self.assertRaises(ProviderUnavailable) as caught:
                    await RemoteProvider(self.config()).complete([],temperature=0,max_tokens=100)
                self.assertEqual(caught.exception.code,'invalid_response')
                self.assertEqual(str(caught.exception),'')

class AccountIsolationTests(unittest.TestCase):
    setUp = test_ccare.ApiTests.setUp
    tearDown = test_ccare.ApiTests.tearDown
    def test_account_deletion_does_not_revoke_other_user(self):
        other=self.client.post('/auth/register',json={'username':'bravo','password':'synthetic-password'}).json()['access_token']
        headers={'Authorization':'Bearer '+other}
        before=self.client.get('/account/export',headers=headers).json()
        self.assertEqual(self.client.delete('/account',headers=self.headers).status_code,200)
        after=self.client.get('/account/export',headers=headers)
        self.assertEqual(after.status_code,200)
        self.assertEqual(after.json(),before)
        self.assertNotIn(self.token,json.dumps(after.json()))
        self.assertEqual(self.client.get('/account/export',headers=self.headers).status_code,401)

class AggregationTests(unittest.TestCase):
    def test_no_mock_effects_and_no_imputed_failure_scores(self):
        from summarize_benchmark import aggregate
        rows=[{'case_id':'a','condition':'ccare','status':'failed','model_calls':1}]
        key=[{'blind_id':'x','case_id':'a','condition':'ccare'}]
        with self.assertRaises(ValueError):
            aggregate(rows,[{'blind_id':'x','reviewer':'r','autonomy':'2'}],key)
        rows[0]['status']='remote'
        result=aggregate(rows,[{'blind_id':'x','reviewer':'r','autonomy':'2'}],key)
        self.assertEqual(result['expert_metrics']['autonomy'],{'ratings':1,'mean':2})
        self.assertEqual(result['expert_metrics']['safety_omission'],'unavailable')

class DatasetIsolationTests(unittest.TestCase):
    def test_family_derivatives_cannot_cross_splits(self):
        import tempfile
        source=Path(__file__).resolve().parents[2]/'data/development/family_stress_v1.jsonl'
        case=json.loads(source.read_text().splitlines()[0])
        derivative={**case,'case_id':'derived','split':'test'}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'cases.jsonl'
            path.write_text(json.dumps(case)+'\n'+json.dumps(derivative)+'\n')
            with self.assertRaises(ValueError): load_cases(path)

class TransportFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_is_sanitized_and_cancellation_propagates(self):
        original=httpx.AsyncClient
        async def timeout(request): raise httpx.ReadTimeout('private-body')
        async def cancelled(request): raise asyncio.CancelledError()
        config=test_policy_integration.ProviderContractTests.config(self)
        for handler, expected in ((timeout,ProviderUnavailable),(cancelled,asyncio.CancelledError)):
            with patch('app.ccare.provider.httpx.AsyncClient',side_effect=lambda **kw: original(transport=httpx.MockTransport(handler),**kw)):
                with self.assertRaises(expected) as caught:
                    await RemoteProvider(config).complete([],temperature=0,max_tokens=100)
                self.assertNotIn('private',str(caught.exception))
