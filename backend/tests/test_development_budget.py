import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from app.ccare.cny_ledger import CNYLedger,BudgetError,LIMIT_APPROVAL
from app.ccare.smoke import POLICY as OLD
from price_refresh import refresh,NEW_POLICY
from development_budget import approve_400,DevelopmentLedger,APPROVAL,POLICY,frozen_scope
from batch_evaluation import reserve_all

class DevelopmentBudgetTests(unittest.TestCase):
    def seed(self,path):
        ledger=CNYLedger(path,OLD,clock=lambda:OLD.verified_at+1)
        for i in range(20):
            if i==4:ledger.approve_cumulative_50(LIMIT_APPROVAL)
            ledger.reserve(f'prior{i}',f'{i:064x}',400);ledger.dispatch(f'prior{i}')
            ledger.settle(f'prior{i}',{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2})
        before=ledger.snapshot()['attempts'];refresh(path,clock=lambda:NEW_POLICY.verified_at+1)
        return before
    def test_migration_preserves_twenty_and_batch_within_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'offline.db';before=self.seed(path)
            approve_400(path,APPROVAL,clock=lambda:NEW_POLICY.verified_at+1)
            ledger=DevelopmentLedger(path,clock=lambda:NEW_POLICY.verified_at+1)
            self.assertEqual(ledger.snapshot()['attempts'],before)
            planned,run_id,_=frozen_scope();reserve_all(ledger,run_id,planned)
            self.assertEqual(ledger.snapshot()['reserved_cny'],'394.866176')
            self.assertEqual(len(ledger.snapshot()['attempts']),188)
            with self.assertRaises(BudgetError):reserve_all(ledger,run_id,planned)
            with self.assertRaises(BudgetError):ledger.dispatch('prior0')
    def test_unauthorized_or_fresh_ledger_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'offline.db'
            with self.assertRaises(BudgetError):CNYLedger(path,POLICY)
            with self.assertRaises(BudgetError):approve_400(path,'wrong')
            with self.assertRaises(BudgetError):DevelopmentLedger(path)
    def test_scope_and_expiry_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'offline.db';self.seed(path);approve_400(path,APPROVAL,clock=lambda:NEW_POLICY.verified_at+1)
            ledger=DevelopmentLedger(path,clock=lambda:NEW_POLICY.verified_at+1)
            planned,run_id,_=frozen_scope();planned['split']='candidate_holdout'
            with self.assertRaises(BudgetError):ledger.authorize_batch(planned,run_id)
            with self.assertRaises(BudgetError):DevelopmentLedger(path,clock=lambda:NEW_POLICY.expires_at+1)
