"""Audited same-rate expiry refresh on the existing ledger; never a new budget."""
import json,time
from dataclasses import replace,asdict
from pathlib import Path
from app.ccare.cny_ledger import CNYLedger,BudgetError,LIMIT_APPROVAL
from app.ccare.web_budget import WEB_POLICY

NEW_POLICY=replace(WEB_POLICY,version='deepseek-flash-20261026-peak-cny-context-reserve-v1',
                   verified_at=1792972800,expires_at=1793059200)
REVIEW='official-docs-20261026-same-peak-rates-context'


def refresh(path,*,clock=time.time):
    # Opens the exact prior policy; expiry may block dispatch but not settled audit.
    ledger=CNYLedger(path,WEB_POLICY,clock=clock)
    NEW_POLICY.validate(clock())
    old,new=asdict(WEB_POLICY),asdict(NEW_POLICY)
    for key in old:
        if key not in ('version','verified_at','expires_at') and old[key]!=new[key]:
            raise BudgetError('refresh_must_preserve_financial_bounds')
    with ledger.transaction() as db:
        row=db.execute('SELECT snapshot,halted FROM policy WHERE id=1').fetchone()
        if row['snapshot']!=WEB_POLICY.serialized() or row['halted']:
            raise BudgetError('refresh_requires_unhalted_prior_policy')
        if db.execute("SELECT 1 FROM attempts WHERE phase!='completed'").fetchone():
            raise BudgetError('refresh_requires_completed_history')
        if not db.execute('SELECT 1 FROM attempts').fetchone():raise BudgetError('existing_history_required')
        db.execute('CREATE TABLE IF NOT EXISTS price_refreshes (review TEXT PRIMARY KEY,old_snapshot TEXT NOT NULL,new_snapshot TEXT NOT NULL,at REAL NOT NULL)')
        db.execute('INSERT INTO price_refreshes VALUES (?,?,?,?)',(REVIEW,WEB_POLICY.serialized(),NEW_POLICY.serialized(),clock()))
        db.execute('UPDATE policy SET snapshot=? WHERE id=1',(NEW_POLICY.serialized(),))
        ledger.event(db,None,'same_bounds_price_snapshot_refreshed_20261026')


class RefreshedLedger(CNYLedger):
    """Uses inherited reserve/dispatch/settle with a verified authorization chain.

    Does not initialize tables or a new ledger. Original approval -> old policy ->
    explicit same-bounds dated refresh must all exist; changing cap is impossible.
    """
    def __init__(self,path,*,clock=time.time):
        self.path,self.policy,self.clock=Path(path),NEW_POLICY,clock
        if not self.path.is_file() or self.path.is_symlink():raise BudgetError('existing_ledger_required')
        self.policy.validate(clock())
        with self.transaction() as db:
            if not db.execute('SELECT 1 FROM authorization_changes WHERE approval=? AND new_snapshot=?',
                (LIMIT_APPROVAL,WEB_POLICY.serialized())).fetchone():raise BudgetError('original_approval_missing')
            if not db.execute('SELECT 1 FROM price_refreshes WHERE review=? AND old_snapshot=? AND new_snapshot=?',
                (REVIEW,WEB_POLICY.serialized(),NEW_POLICY.serialized())).fetchone():raise BudgetError('refresh_audit_missing')
            self.admit(db)
