import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from listen_first_v2 import choose_v2
from app.ccare.schemas import TurnRequest
from price_refresh import refresh,RefreshedLedger,NEW_POLICY
from app.ccare.cny_ledger import CNYLedger,BudgetError,LIMIT_APPROVAL
from app.ccare.smoke import POLICY

class Oct26ResearchTests(unittest.TestCase):
    def test_seen_twelve_are_development_regressions_only(self):
        path=Path(__file__).resolve().parents[2]/'research/listen-first-v1/cases.jsonl'
        for line in path.read_text().splitlines():
            row=json.loads(line)
            with self.subTest(case=row['case_id']):
                out=choose_v2(TurnRequest.model_validate(row['request']))
                self.assertIn(out['action'],row['gold']['allowed_actions'])
                self.assertEqual(out['state'],'unknown')
    def test_resolved_other_does_not_erase_new_user_danger(self):
        text='朋友说她不确定是否安全，但她已经安全到校。我不知道现在是否安全。'
        self.assertEqual(choose_v2(TurnRequest(message=text))['action'],'safety_question')
        self.assertEqual(choose_v2(TurnRequest(message=text+'爸爸正在掐我。'))['action'],'safety')
    def test_new_explicit_request_after_prior_negation(self):
        req=TurnRequest(message='不是要你帮我写信。但现在请给我一些表达边界的具体建议。')
        self.assertEqual(choose_v2(req)['action'],'bounded_advice')
    def test_refresh_preserves_history_and_reopens_with_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'ledger.db';old=CNYLedger(p,POLICY,clock=lambda:POLICY.verified_at+1)
            old.reserve('prior','a'*64);old.dispatch('prior');old.settle('prior',{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12})
            old.approve_cumulative_50(LIMIT_APPROVAL);before=old.snapshot()['attempts']
            refresh(p,clock=lambda:NEW_POLICY.verified_at+1)
            new=RefreshedLedger(p,clock=lambda:NEW_POLICY.verified_at+1)
            self.assertEqual(new.snapshot()['attempts'],before)
            self.assertEqual(new.policy.max_cny,'50.00')
            with self.assertRaises(BudgetError):old.reserve('stale','b'*64)
    def test_new_file_refresh_and_expired_refresh_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(BudgetError):RefreshedLedger(Path(tmp)/'missing.db')
            with self.assertRaises(BudgetError):refresh(Path(tmp)/'missing.db')
    def test_same_clause_new_risk_survives_resolved_other(self):
        req=TurnRequest(message='朋友说她不知道是否安全，但她已经安全到校，我不知道现在是否安全。')
        self.assertEqual(choose_v2(req)['action'],'safety_question')
    def test_three_arm_mock_uses_matching_multi_caps_and_actual_reservation(self):
        import asyncio
        from three_arm import ArmProvider,execute
        from app.ccare.config import Settings
        from app.ccare.provider import Completion
        class Fixture:
            async def complete(self,messages,**params):
                text='{}' if '识别成人亲子冲突' in messages[0]['content'] else '{"safe":true,"violations":[]}' if params.get('json_mode') else '我在听，你可以按自己的节奏说。'
                return Completion(text,{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12},'offline-fixture',200)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'fees.db';old=CNYLedger(path,POLICY,clock=lambda:POLICY.verified_at+1)
            old.reserve('history','a'*64);old.dispatch('history');old.settle('history',{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2})
            old.approve_cumulative_50(LIMIT_APPROVAL);refresh(path,clock=lambda:NEW_POLICY.verified_at+1)
            ledger=RefreshedLedger(path,clock=lambda:NEW_POLICY.verified_at+1)
            config=Settings(_env_file=None,api_key='',mode='disabled',max_tokens=400).model_copy(update={'mode':'remote','model':'offline-fixture'})
            req=TurnRequest(message='虚构案例，我不知道现在是什么心情，先听我说。',eligible=True,external_consent=True)
            for arm,count in [('strong_single',1),('strong_multi',3),('ccare',3)]:
                wrapped=ArmProvider(ledger,Fixture(),arm)
                result=asyncio.run(execute(req,arm,config,wrapped))
                self.assertEqual(result['status'],'remote');self.assertEqual(len(wrapped.records),count)
                self.assertTrue(all(r['status']=='completed' for r in wrapped.records))
            self.assertEqual(len(ledger.snapshot()['attempts']),8)
    def test_refresh_halted_or_unsettled_history_is_not_unblocked(self):
        from app.ccare.web_budget import WEB_POLICY
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'fees.db';ledger=CNYLedger(path,POLICY,clock=lambda:POLICY.verified_at+1)
            ledger.reserve('old','a'*64);ledger.dispatch('old');ledger.settle('old',{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2})
            ledger.approve_cumulative_50(LIMIT_APPROVAL)
            ledger.reserve('pending','b'*64)
            with self.assertRaises(BudgetError):refresh(path,clock=lambda:NEW_POLICY.verified_at+1)
            self.assertEqual(ledger.snapshot()['policy']['version'],WEB_POLICY.version)
    def test_invalid_json_freezes_shared_budget_without_retry(self):
        import asyncio
        from three_arm import ArmProvider
        from app.ccare.provider import Completion
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'fees.db';old=CNYLedger(path,POLICY,clock=lambda:POLICY.verified_at+1)
            old.reserve('history','a'*64);old.dispatch('history');old.settle('history',{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2})
            old.approve_cumulative_50(LIMIT_APPROVAL);refresh(path,clock=lambda:NEW_POLICY.verified_at+1)
            ledger=RefreshedLedger(path,clock=lambda:NEW_POLICY.verified_at+1)
            class Invalid:
                calls=0
                async def complete(self,*args,**kwargs):
                    self.calls+=1
                    return Completion('not JSON',{'prompt_tokens':2,'completion_tokens':2,'total_tokens':4},'fixture',200)
            fixture=Invalid();wrapped=ArmProvider(ledger,fixture,'ccare')
            with self.assertRaises(ValueError):asyncio.run(wrapped.complete([{'role':'system','content':'check'}],max_tokens=400,json_mode=True))
            with self.assertRaises(BudgetError):asyncio.run(wrapped.complete([],max_tokens=400))
            self.assertEqual(fixture.calls,1)
            self.assertEqual(ledger.snapshot()['halted'],'provider_failure')
