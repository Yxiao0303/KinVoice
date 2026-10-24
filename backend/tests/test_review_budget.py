"""Fictional regression coverage for review propagation and matched envelopes."""
import asyncio
import json
from pathlib import Path
import sys
import unittest
from pydantic import ValidationError
import test_ccare
from app.ccare.engine import Engine, local_state
from app.ccare.policy import decide, validate_state
from app.ccare.provider import Completion, ProviderUnavailable
from app.ccare.reviews import apply_reviews, digest
from app.ccare.schemas import State, TurnRequest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from benchmark_ccare import BudgetProvider, EvaluationEngine, OfflineFixtureProvider, load_cases, execute, CONDITIONS
from benchmark_budget import SampleLimits, SampleProvider

OLD = '我很难过，想写段话'

def entry(field='emotion', value='sad', action='confirm', revision=1, source=OLD):
    return dict(field=field, value=value, action=action, revision=revision,
                source_digest=digest(source), source_text=source)

def reviewed(entries, current='继续说', history=None):
    return TurnRequest(message=current, history=history or [{'role':'user','content':OLD}],
                       reviews=entries, goal='draft', external_consent=True)

class ReviewTests(unittest.TestCase):
    def apply(self, req):
        state=State(emotion='sad',evidence=[OLD],support_intent='unknown')
        links=validate_state(req,state)
        outcomes=apply_reviews(req,state,links,local_state(req))
        return state,links,outcomes

    def test_confirm_correct_revoke_and_idempotent_replay(self):
        state,_,_=self.apply(reviewed([entry()]))
        self.assertEqual(state.emotion,'sad')
        self.assertEqual(state.assessments[-1].origin,'confirmed')
        corrected=entry(value='angry',action='correct',revision=2)
        revoked=entry(value='angry',action='revoke',revision=3)
        state,_,_=self.apply(reviewed([corrected,entry(),corrected]))
        self.assertEqual(state.emotion,'angry')
        # An out-of-order older confirmation cannot override the latest tombstone.
        req=reviewed([revoked,entry(),corrected])
        for _ in range(2):
            state,links,_=self.apply(req)
            self.assertEqual(state.emotion,'unknown')
            self.assertTrue(state.needs_clarification)
            self.assertEqual(links,[])
            self.assertEqual(state.evidence,[])

    def test_conflict_and_foreign_or_assistant_source_rejected(self):
        for kwargs in [dict(reviews=[entry(),entry(value='angry')]),
                       dict(reviews=[entry(source='OTHER_SYNTHETIC_PRIVATE')]),
                       dict(reviews=[entry(revision=0)]),
                       dict(reviews=[entry()],history=[{'role':'assistant','content':OLD}])]:
            with self.assertRaises(ValidationError):
                TurnRequest(message='继续',history=kwargs.pop('history',[{'role':'user','content':OLD}]),**kwargs)

    def test_newer_current_words_supersede_old_review(self):
        req=reviewed([entry(action='revoke')],current='我现在很生气')
        state=State(emotion='angry',evidence=['生气'])
        links=validate_state(req,state)
        outcomes=apply_reviews(req,state,links,local_state(req))
        self.assertEqual(state.emotion,'angry')
        self.assertEqual(outcomes[0]['status'],'superseded')
        req=reviewed([entry(field='support_intent',value='listen')],current='现在我想写段话')
        state=State()
        outcomes=apply_reviews(req,state,[],local_state(req))
        self.assertEqual(decide(req,state).selected,'draft')
        self.assertEqual(outcomes[0]['status'],'superseded')

    def test_revocation_changes_later_policy_but_not_current_refusal(self):
        req=reviewed([entry(field='support_intent',value='listen',action='revoke')])
        state=State(support_intent='listen')
        apply_reviews(req,state,[],local_state(req))
        self.assertEqual(decide(req,state).selected,'draft')
        req=reviewed([entry(field='support_intent',value='draft')],current='不要给我建议')
        state=State()
        apply_reviews(req,state,[],local_state(req))
        self.assertEqual(decide(req,state).selected,'listen')

class ReviewEngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_remote_estimate_cannot_resurrect_withdrawn_historical_claim(self):
        class Fake:
            def __init__(self): self.generated=None
            async def complete(self,messages,**kwargs):
                system=messages[0]['content']
                if '识别成人亲子冲突' in system:
                    return Completion(json.dumps({'emotion':'sad','evidence':[OLD]},ensure_ascii=False))
                if kwargs.get('json_mode'): return Completion('{"safe":true,"violations":[]}')
                self.generated=json.loads(messages[1]['content'])
                return Completion('我先听你说。')
        provider=Fake()
        result=await Engine(test_ccare.configuration('/tmp/unused','remote'),provider).respond(reviewed([entry(action='revoke')]))
        self.assertEqual(result.state.emotion,'unknown')
        self.assertEqual(result.state.assessments[-1].origin,'unknown')
        self.assertEqual(provider.generated['state']['emotion'],'unknown')
        self.assertEqual(result.review_outcomes[0]['status'],'revoke')

    async def test_safety_and_family_guards_survive_corrections_and_revocations(self):
        for message in ['我想死','我刚吃了一整瓶安眠药','爸爸正在掐我']:
            req=TurnRequest(message='继续',history=[{'role':'user','content':message}],
                reviews=[entry(field='risk',value='ordinary',action='correct',source=message)])
            result=await Engine(test_ccare.configuration('/tmp/unused','demo')).respond(req)
            self.assertEqual(result.mode,'safety_template')
            self.assertEqual(result.model_calls,0)
            self.assertTrue(result.review_outcomes[0]['independent_guard_preserved'])
        message='爸爸打我'
        req=TurnRequest(message='现在我想写段话',history=[{'role':'user','content':message}],goal='draft',
            reviews=[entry(field='family_unsafe',value='false',action='revoke',source=message)])
        result=await Engine(test_ccare.configuration('/tmp/unused','demo')).respond(req)
        self.assertNotIn('draft',result.decision.allowed)
        self.assertTrue(result.state.family_unsafe)

class ReviewPrivacyTests(unittest.TestCase):
    setUp=test_ccare.ApiTests.setUp
    tearDown=test_ccare.ApiTests.tearDown
    def test_review_not_persisted_exported_or_available_to_another_account(self):
        req=reviewed([entry()]).model_dump()
        req['eligible']=True
        result=self.client.post('/support/turn',headers=self.headers,json=req)
        self.assertEqual(result.status_code,200)
        exported=self.client.get('/account/export',headers=self.headers).text
        self.assertNotIn(OLD,exported)
        other=self.client.post('/auth/register',json={'username':'second','password':'synthetic-password'}).json()['access_token']
        other_result=self.client.post('/support/turn',headers={'Authorization':'Bearer '+other},json={'message':'你好','eligible':True}).json()
        self.assertEqual(other_result['review_outcomes'],[])
        import sqlite3
        with sqlite3.connect(self.config.auth_db) as db:
            self.assertNotIn(OLD,'\n'.join(db.iterdump()))
        # A different account cannot refer to a source it has not supplied.
        invalid={**req,'history':[]}
        invalid_result=self.client.post('/support/turn',headers={'Authorization':'Bearer '+other},json=invalid)
        self.assertEqual(invalid_result.status_code,422)
        self.assertNotIn(OLD,invalid_result.text)

    def test_public_api_does_not_accept_ablation_switches(self):
        result=self.client.post('/support/turn',headers=self.headers,json={
            'message':'不要给我建议','eligible':True,'intent_constraints':False,'condition':'without_intent'})
        self.assertEqual(result.status_code,422)

class BudgetTests(unittest.IsolatedAsyncioTestCase):
    def wrapper(self, *, limits=None, single=False, fixture=None):
        return SampleProvider(BudgetProvider(fixture or OfflineFixtureProvider(),100),limits or SampleLimits(),single=single)

    async def test_equal_envelope_distinct_slot_plans_and_atomic_limits(self):
        multi=self.wrapper()
        for _ in range(5): await multi.complete([{'role':'user','content':'虚构'}],max_tokens=400)
        self.assertEqual(multi.output_reserved,2000)
        with self.assertRaises(ProviderUnavailable): await multi.complete([],max_tokens=400)
        self.assertEqual(multi.calls,5)
        single=self.wrapper(single=True)
        await single.complete([],max_tokens=2000)
        with self.assertRaises(ProviderUnavailable): await single.complete([],max_tokens=1)
        self.assertEqual(single.calls,1)
        self.assertEqual(single.report()['limits'],multi.report()['limits'])
        self.assertEqual(single.output_reserved,multi.output_reserved)
        self.assertIsNone(single.records[0]['usage'])
        self.assertIsNone(single.report()['cost'])

    async def test_input_budget_is_utf8_bytes_not_characters(self):
        provider=self.wrapper(limits=SampleLimits(max_input_bytes=1024))
        with self.assertRaises(ProviderUnavailable) as caught:
            await provider.complete([{'role':'user','content':'虚'*500}],max_tokens=400)
        self.assertEqual(caught.exception.code,'sample_input_budget_exhausted')
        self.assertEqual(provider.calls,0)
        self.assertEqual(provider.output_reserved,0)

    async def test_failure_cancel_and_excess_reported_usage_keep_reservations(self):
        class Failed:
            async def complete(self,*args,**kwargs): raise ProviderUnavailable('rate_limited')
        class Cancelled:
            async def complete(self,*args,**kwargs): raise asyncio.CancelledError()
        class Over:
            async def complete(self,*args,**kwargs): return Completion('fixture',{'completion_tokens':401})
        for fixture,error in [(Failed(),ProviderUnavailable),(Cancelled(),asyncio.CancelledError),(Over(),ProviderUnavailable)]:
            provider=self.wrapper(fixture=fixture)
            with self.assertRaises(error): await provider.complete([],max_tokens=400)
            self.assertEqual(provider.calls,1)
            self.assertEqual(provider.output_reserved,400)
            self.assertIsNotNone(provider.records[0]['failure'])

    async def test_global_exhaustion_does_not_count_unattempted_sample_call(self):
        provider=SampleProvider(BudgetProvider(OfflineFixtureProvider(),0),SampleLimits())
        with self.assertRaises(ProviderUnavailable): await provider.complete([],max_tokens=400)
        self.assertEqual(provider.calls,0)

    async def test_multi_rewrite_has_five_slots_and_rejection_stays_in_denominator(self):
        case=load_cases(Path(__file__).resolve().parents[2]/'data/development/family_stress_v1.jsonl')[0]
        class Rejecting:
            async def complete(self,messages,**kwargs):
                return Completion('{"safe":false,"violations":["fixture"]}' if kwargs.get('json_mode') else 'fixture')
        config=test_ccare.configuration('/tmp/unused','remote').model_copy(update={'max_tokens':400})
        provider=self.wrapper(fixture=Rejecting())
        _,status,failure=await execute(case,'strong_multi',config,provider)
        self.assertEqual((status,failure),('failed','verification_rejected'))
        self.assertEqual(provider.calls,5)
        self.assertEqual(provider.output_reserved,2000)

class AblationTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_ablations_do_not_patch_shared_engine_or_inputs(self):
        req=TurnRequest(message='不要给我建议，爸爸打我',goal='draft',external_consent=True)
        original=req.model_dump()
        class Fixture:
            async def complete(self,messages,**kwargs):
                await asyncio.sleep(0)
                if '识别成人亲子冲突' in messages[0]['content']: return Completion('{}')
                return Completion('{"safe":true,"violations":[]}' if kwargs.get('json_mode') else '我先听你说。')
        config=test_ccare.configuration('/tmp/unused','remote')
        full=Engine(config,Fixture())
        family=EvaluationEngine(config,Fixture(),'without_family')
        intent=EvaluationEngine(config,Fixture(),'without_intent')
        results=await asyncio.gather(full.respond(req),family.respond(req),intent.respond(req))
        self.assertEqual(req.model_dump(),original)
        self.assertIn('family_contact_restricted',results[0].decision.reasons)
        self.assertNotIn('family_contact_restricted',results[1].decision.reasons)
        self.assertNotIn('current_refusal',results[2].decision.reasons)
        state=State(family_unsafe=True)
        decision=decide(req,state)
        text='建议你主动联系爸爸'
        self.assertIn('unsafe_family_contact',full.check_output(text,decision,state))
        self.assertNotIn('unsafe_family_contact',family.check_output(text,decision,state))
        self.assertNotIn('unsolicited_advice',intent.check_output(text,decision,state))
        self.assertNotIn('家庭不安全时不建议接触家长。',family.generation_rules())
        self.assertNotIn('检查是否尊重指定策略及家庭安全。',family.verification_rules())

    async def test_evidence_ablation_is_instance_local_and_acute_guard_always_active(self):
        config=test_ccare.configuration('/tmp/unused','remote')
        req=TurnRequest(message='你好')
        full=Engine(config,OfflineFixtureProvider())
        ablated=EvaluationEngine(config,OfflineFixtureProvider(),'without_evidence')
        with self.assertRaises(ValueError): full.validate_estimate(req,State(emotion='sad',evidence=['不存在']))
        self.assertEqual(ablated.validate_estimate(req,State(emotion='sad',evidence=['不存在'])),[])
        for condition in ('ccare','without_intent','without_family','without_evidence'):
            result=await EvaluationEngine(config,OfflineFixtureProvider(),condition).respond(TurnRequest(message='我刚吃了一整瓶安眠药'))
            self.assertEqual(result.mode,'safety_template')
            self.assertEqual(result.model_calls,0)

class ReviewIdentityTests(unittest.TestCase):
    def test_repeated_identical_message_does_not_inherit_old_tombstone(self):
        op={**entry(action='revoke'),'source_message_id':'u:1'}
        req=TurnRequest(message=OLD,message_id='u:2',history=[{'role':'user','content':OLD,'message_id':'u:1'}],reviews=[op])
        state=State(emotion='sad',evidence=[OLD])
        links=validate_state(req,state)
        self.assertEqual(links[0].message_id,'u:2')
        outcomes=apply_reviews(req,state,links,local_state(req))
        self.assertEqual(state.emotion,'sad')
        self.assertEqual(outcomes[0]['status'],'superseded')

    def test_conflicting_older_revisions_not_hidden_by_newest_and_duplicate_ids_rejected(self):
        with self.assertRaises(ValidationError): reviewed([entry(revision=3),entry(value='sad'),entry(value='angry')])
        with self.assertRaises(ValidationError):
            TurnRequest(message='current',message_id='u:1',history=[{'role':'user','content':OLD,'message_id':'u:1'}])

class BenchmarkCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_preserves_all_rows_and_unknown_failure_usage(self):
        import argparse
        import tempfile
        from unittest.mock import patch
        from benchmark_ccare import run
        entered=asyncio.Event()
        async def wait(*args,**kwargs):
            entered.set()
            await asyncio.Event().wait()
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'run'
            args=argparse.Namespace(dataset=str(Path(__file__).resolve().parents[2]/'data/development/family_stress_v1.jsonl'),
                output=output,live=False,mock=True,call_budget=None,sample_input_bytes=96000,sample_output_tokens=2000)
            # Wrap SystemExit so the event loop is not terminated by the child task.
            async def execute_run():
                try: await run(args)
                except SystemExit as exc: return exc.code
            with patch('benchmark_ccare.OfflineFixtureProvider.complete',new=wait):
                task=asyncio.create_task(execute_run())
                await asyncio.wait_for(entered.wait(),2)
                task.cancel()
                self.assertEqual(await task,130)
            rows=[json.loads(line) for line in (output/'results.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows),63)
            self.assertTrue(any(r['outcome_status']=='cancelled' for r in rows))
            self.assertTrue(any(r['outcome_status']=='skipped' for r in rows))
            call=next(record for row in rows for record in row['calls'])
            self.assertIsNone(call['usage'])
            self.assertEqual(call['failure'],'cancelled_or_timeout')

class BillingReadinessTests(unittest.IsolatedAsyncioTestCase):
    def test_missing_usage_unknown_and_reasoning_not_double_counted(self):
        from app.ccare.billing import usage_estimate, live_readiness
        usage={'prompt_tokens':20,'prompt_cache_hit_tokens':5,'prompt_cache_miss_tokens':15,
               'completion_tokens':10,'total_tokens':30,'completion_tokens_details':{'reasoning_tokens':7}}
        estimate=usage_estimate(usage)
        self.assertEqual(estimate['estimated_usd'],'0.00001653')
        self.assertEqual(estimate['estimated_cny'],'0.0001102')
        self.assertIsNone(estimate['actual_cny'])
        self.assertFalse(estimate['cny_cap_enforced'])
        self.assertIsNone(usage_estimate(None)['estimated_usd'])
        self.assertIsNone(usage_estimate({**usage,'total_tokens':5})['estimated_usd'])
        self.assertFalse(live_readiness()['live_enabled'])

    async def test_deepseek_payload_and_numeric_usage_only(self):
        import httpx
        from unittest.mock import patch
        from app.ccare.provider import RemoteProvider
        config=test_ccare.configuration('/tmp/unused','remote').model_copy(update={
            'provider_kind':'deepseek','api_base':'https://api.deepseek.com','model':'deepseek-flash'})
        captures=[]
        def handler(request):
            captures.append(json.loads(request.content))
            return httpx.Response(200,json={'model':'deepseek-flash','choices':[{'finish_reason':'stop',
                'message':{'content':'{}','reasoning_content':'PRIVATE_REASONING_NOT_RETURNED'}}],
                'usage':{'prompt_tokens':3,'completion_tokens':2,'total_tokens':5,
                         'completion_tokens_details':{'reasoning_tokens':1,'private_text':'NOT_RETURNED'}}})
        original=httpx.AsyncClient
        with patch('app.ccare.provider.httpx.AsyncClient',side_effect=lambda **kw:original(transport=httpx.MockTransport(handler),**kw)):
            result=await RemoteProvider(config).complete([{'role':'user','content':'Return JSON'}],temperature=0,max_tokens=400,json_mode=True)
        self.assertEqual(captures[0]['thinking'],{'type':'disabled'})
        self.assertEqual(captures[0]['response_format'],{'type':'json_object'})
        self.assertNotIn('tools',captures[0])
        self.assertNotIn('reasoning_effort',captures[0])
        self.assertEqual(result.usage['completion_tokens_details'],{'reasoning_tokens':1})
        self.assertNotIn('PRIVATE_REASONING',str(result))

    async def test_live_benchmark_remains_zero_call_blocked_even_with_budget(self):
        from argparse import Namespace
        from unittest.mock import patch
        from benchmark_ccare import run
        with patch('benchmark_ccare.RemoteProvider') as provider:
            with self.assertRaises(SystemExit) as caught: await run(Namespace(live=True))
            self.assertEqual(caught.exception.code,2)
            provider.assert_not_called()

class FailedUsageTests(unittest.IsolatedAsyncioTestCase):
    async def test_truncated_output_retains_billable_usage_without_response_body(self):
        import httpx
        from unittest.mock import patch
        from app.ccare.provider import RemoteProvider
        usage={'prompt_tokens':20,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':20,
               'completion_tokens':400,'total_tokens':420,'completion_tokens_details':{'reasoning_tokens':30}}
        def handler(request):
            return httpx.Response(200,json={'model':'deepseek-flash','usage':usage,
                'choices':[{'finish_reason':'length','message':{'content':'PRIVATE_TRUNCATED'}}]})
        config=test_ccare.configuration('/tmp/unused','remote').model_copy(update={
            'provider_kind':'deepseek','api_base':'https://api.deepseek.com','model':'deepseek-flash'})
        original=httpx.AsyncClient
        with patch('app.ccare.provider.httpx.AsyncClient',side_effect=lambda **kw:original(transport=httpx.MockTransport(handler),**kw)):
            sample=SampleProvider(BudgetProvider(RemoteProvider(config),5),SampleLimits())
            result=await Engine(config.model_copy(update={'max_tokens':400}),sample).respond(TurnRequest(message='虚构普通冲突',external_consent=True))
        self.assertEqual(result.mode,'safe_fallback')
        self.assertEqual(result.usage,[usage])
        self.assertEqual(result.stages[0].usage,usage)
        self.assertEqual(sample.records[0]['failure'],'incomplete_output')
        self.assertIsNotNone(sample.records[0]['billing']['estimated_usd'])
        self.assertNotIn('PRIVATE_TRUNCATED',result.model_dump_json())

class SecretAliasTests(unittest.TestCase):
    def test_deepseek_secret_binding_alias_is_supported_without_printing_value(self):
        from unittest.mock import patch
        from app.ccare.config import Settings
        with patch.dict('os.environ',{'DEEPSEEK_API_KEY':'synthetic-placeholder-never-send'},clear=True):
            config=Settings(_env_file=None,mode='disabled')
        self.assertTrue(bool(config.api_key))
        self.assertNotIn('synthetic-placeholder-never-send',repr(config))
