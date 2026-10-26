"""Explicit cumulative-400 migration, scoped to one frozen 24-case batch.
Never invoked implicitly by the runner; preserves every old attempt/reservation.
"""
import hashlib,json,time
from dataclasses import replace
from pathlib import Path
from app.ccare.cny_ledger import CNYLedger,FeePolicy,BudgetError,LIMIT_APPROVAL
from app.ccare.web_budget import WEB_POLICY
from price_refresh import RefreshedLedger,NEW_POLICY,REVIEW
ROOT=Path(__file__).resolve().parents[1]
APPROVAL='kinvoice-dev24-cumulative400-20261026-confirmed'
DATA_SHA='d4cc4c592379796600c7df22f1f5f388f8381909ca85704d4bcc7ccc6f27b00a'
FREEZE=ROOT/'research/batch-evaluation-v5/freeze.json'

class BatchFeePolicy(FeePolicy):
    def validate(self,now):
        if self.max_cny!='400.00':raise BudgetError('batch_cap_mismatch')
        FeePolicy.validate(replace(self,max_cny='50.00'),now)

POLICY=BatchFeePolicy(**(NEW_POLICY.__dict__ | {'max_cny':'400.00'}))

def frozen_scope():
    from batch_evaluation import verify_freeze,load_cases,plan,digest
    verify_freeze()
    raw=(ROOT/'research/evaluation-pack-v1/development.jsonl').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise BudgetError('development_data_changed')
    planned=plan(load_cases('development'),'development')
    if planned['cases']!=24 or planned['max_calls']!=168:raise BudgetError('scope_changed')
    return planned,'batch-v5-development-'+digest(planned)[:8],hashlib.sha256(FREEZE.read_bytes()).hexdigest()

def approve_400(path,approval_reference,*,clock=time.time):
    if approval_reference!=APPROVAL:raise BudgetError('approval_reference_required')
    planned,run_id,freeze=frozen_scope()
    ledger=RefreshedLedger(path,clock=clock)
    POLICY.validate(clock())
    with ledger.transaction() as db:
        ledger.admit(db)
        count,total=db.execute('SELECT count(*),COALESCE(sum(held_nano),0) FROM attempts').fetchone()
        if count!=20 or total!=42007040000 or db.execute("SELECT 1 FROM attempts WHERE phase!='completed'").fetchone():raise BudgetError('original_twenty_settled_attempts_required')
        db.execute('CREATE TABLE IF NOT EXISTS batch_authorizations (approval TEXT PRIMARY KEY,run_id TEXT NOT NULL,plan_json TEXT NOT NULL,data_sha TEXT NOT NULL,freeze_sha TEXT NOT NULL,source TEXT NOT NULL)')
        db.execute('INSERT INTO authorization_changes VALUES (?,?,?,?)',(APPROVAL,NEW_POLICY.serialized(),POLICY.serialized(),clock()))
        db.execute('INSERT INTO batch_authorizations VALUES (?,?,?,?,?,?)',(APPROVAL,run_id,json.dumps(planned,sort_keys=True),DATA_SHA,freeze,'User confirmed cumulative 400 CNY for dev24 only on 2026-10-26 07:48 UTC; not an additional 400'))
        db.execute('UPDATE policy SET snapshot=? WHERE id=1',(POLICY.serialized(),))
        ledger.event(db,None,'approved_dev24_cumulative_limit_400')

class DevelopmentLedger(CNYLedger):
    def __init__(self,path,*,clock=time.time):
        self.path,self.policy,self.clock=Path(path),POLICY,clock
        if not self.path.is_file() or self.path.is_symlink():raise BudgetError('existing_ledger_required')
        self.policy.validate(clock())
        planned,self.run_id,self.freeze=frozen_scope()
        with self.transaction() as db:
            for approval,snapshot in [(LIMIT_APPROVAL,WEB_POLICY.serialized()),(APPROVAL,POLICY.serialized())]:
                if not db.execute('SELECT 1 FROM authorization_changes WHERE approval=? AND new_snapshot=?',(approval,snapshot)).fetchone():raise BudgetError('authorization_chain_missing')
            if not db.execute('SELECT 1 FROM price_refreshes WHERE review=? AND old_snapshot=? AND new_snapshot=?',(REVIEW,WEB_POLICY.serialized(),NEW_POLICY.serialized())).fetchone():raise BudgetError('price_chain_missing')
            row=db.execute('SELECT * FROM batch_authorizations WHERE approval=?',(APPROVAL,)).fetchone()
            if not row or row['run_id']!=self.run_id or row['plan_json']!=json.dumps(planned,sort_keys=True) or row['data_sha']!=DATA_SHA or row['freeze_sha']!=self.freeze:raise BudgetError('batch_scope_mismatch')
            self.admit(db)
    def authorize_batch(self,planned,run_id):
        expected,expected_id,freeze=frozen_scope()
        if planned!=expected or run_id!=expected_id or freeze!=self.freeze:raise BudgetError('development_only')
    def reserve(self,*a,**kw):raise BudgetError('atomic_authorized_batch_only')
    def dispatch(self,operation_id,**kw):
        with self.transaction() as db:
            row=db.execute('SELECT run_id FROM attempts WHERE operation_id=?',(operation_id,)).fetchone()
            if not row or row['run_id']!=self.run_id:raise BudgetError('operation_outside_authorized_batch')
        return super().dispatch(operation_id,**kw)
