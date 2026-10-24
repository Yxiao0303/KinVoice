import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from app.ccare.cny_ledger import CNYLedger,BudgetError,LIMIT_APPROVAL
from app.ccare.smoke import POLICY
from app.ccare.web_budget import WEB_POLICY,WebBudgetProvider
from app.ccare.provider import Completion,ProviderUnavailable

U={'prompt_tokens':10,'completion_tokens':2,'total_tokens':12}

class BudgetIncreaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'fees.db'
        self.ledger=CNYLedger(self.path,POLICY,clock=lambda:POLICY.verified_at+1)
        for i in range(4):
            self.ledger.reserve(f'prior:{i}','a'*64,400);self.ledger.dispatch(f'prior:{i}');self.ledger.settle(f'prior:{i}',U)
    def tearDown(self):self.tmp.cleanup()
    def test_approved_increase_preserves_history_and_audit(self):
        before=self.ledger.snapshot()['attempts']
        self.ledger.approve_cumulative_50(LIMIT_APPROVAL)
        reopened=CNYLedger(self.path,WEB_POLICY,clock=lambda:POLICY.verified_at+2)
        self.assertEqual(reopened.snapshot()['attempts'],before)
        self.assertEqual(reopened.snapshot()['reserved_cny'],'8.401408')
        self.assertEqual(reopened.snapshot()['remaining_reservable_cny'],'41.598592')
        with reopened.transaction() as db:
            audit=db.execute('SELECT * FROM authorization_changes').fetchall()
            self.assertEqual(len(audit),1)
            self.assertEqual(audit[0]['approval'],LIMIT_APPROVAL)
    def test_unapproved_or_empty_new_authorization_rejected(self):
        with self.assertRaises(BudgetError):self.ledger.approve_cumulative_50('unapproved')
        with self.assertRaises(BudgetError):CNYLedger(Path(self.tmp.name)/'new.db',WEB_POLICY)
        self.assertEqual(self.ledger.snapshot()['policy']['max_cny'],'10.00')
    def test_inflight_increase_rejected(self):
        ledger=CNYLedger(Path(self.tmp.name)/'pending.db',POLICY,clock=lambda:POLICY.verified_at+1)
        ledger.reserve('pending','b'*64,400);ledger.dispatch('pending')
        with self.assertRaises(BudgetError):ledger.approve_cumulative_50(LIMIT_APPROVAL)
    def test_web_cap_and_pre_dispatch_reservation(self):
        self.ledger.approve_cumulative_50(LIMIT_APPROVAL)
        ledger=self.ledger
        class Fixture:
            async def complete(self,*args,**kwargs):
                assert any(a['phase']=='dispatched' for a in ledger.snapshot()['attempts'])
                return Completion('fixture',U,'offline',200)
        wrapped=WebBudgetProvider(ledger,Fixture())
        for _ in range(9):asyncio.run(wrapped.complete([{'role':'user','content':'synthetic'}],max_tokens=400,json_mode=False))
        with self.assertRaises(ProviderUnavailable):asyncio.run(wrapped.complete([],max_tokens=400))
        self.assertEqual(ledger.snapshot()['reserved_cny'],'27.304576')
        with self.assertRaises(BudgetError):WebBudgetProvider(ledger,Fixture())
        resumed=WebBudgetProvider(ledger,Fixture(),resume=True)
        self.assertEqual(resumed.calls,9)
        with self.assertRaises(ProviderUnavailable):asyncio.run(resumed.complete([],max_tokens=400))
