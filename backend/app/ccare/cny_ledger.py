"""Durable fee-reservation guard; never a provider billing guarantee.

All cooperating attempts share one authorization ledger. Every dispatched attempt
retains its full worst-case reservation, even after success; no usage-based refund.
Missing/invalid usage, failed/cancelled attempts and expired dispatch leases halt
further dispatch. Actual billing remains unknown. Only the fixed smoke entry point
uses a reviewed public-contract policy for live dispatch; batch use stays blocked.
"""
from contextlib import contextmanager, closing
from dataclasses import dataclass, asdict, replace
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid
import asyncio

from .provider import ProviderUnavailable

SCALE = 10**9  # integer nanoyuan: no binary floating-point money arithmetic
AUTHORIZATION = 'kinvoice-deepseek-first-10cny-20261024'
LIMIT_APPROVAL = 'user-approved-cumulative-50cny-20261024'
DEFAULT_LEDGER = Path(__file__).resolve().parents[2] / 'data' / 'deepseek_first_run_budget.db'

class BudgetError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def number(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise BudgetError('invalid_policy') from None
    if not result.is_finite() or result < 0:
        raise BudgetError('invalid_policy')
    return result


def nano(value):
    return int((number(value) * SCALE).to_integral_value(rounding=ROUND_CEILING))


def yuan(value):
    return str(Decimal(value) / SCALE)


@dataclass(frozen=True)
class FeePolicy:
    version: str = 'deepseek-flash-20261024-peak-cny-context-reserve-v1'
    authorization: str = AUTHORIZATION
    model: str = 'deepseek-flash'
    currency: str = 'CNY'
    max_cny: str = '10.00'
    # Conservatively treat the full published 1M context as billable input.
    max_prompt_tokens: int = 1048576
    max_output_tokens: int = 400  # includes any reasoning tokens, not added twice
    input_per_million: str = '2'
    output_per_million: str = '8'
    price_source: str = 'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/'
    context_source: str = 'https://api-docs.deepseek.com/api/create-chat-completion/'
    verified_at: int = 1792800000  # 2026-10-24 00:00 UTC; snapshot date, not a price lock
    expires_at: int = 1792886400   # 2026-10-25 00:00 UTC; expires, never auto-refreshes
    fx_cny_per_usd_upper: str | None = None
    fx_source: str | None = None
    fx_verified: bool = False
    fx_expires_at: int | None = None
    provider_bound_verified: bool = False
    # Default is offline. The single-smoke policy verifies public token/rate
    # assumptions only, never a provider-side account spending lock.

    def validate(self, now):
        if self.model != 'deepseek-flash' or self.authorization != AUTHORIZATION:
            raise BudgetError('unsupported_authorization')
        if self.currency not in ('CNY', 'USD') or not (0 < number(self.max_cny) <= 10 or number(self.max_cny) == 50):
            raise BudgetError('invalid_policy')
        if type(self.max_prompt_tokens) is not int or not 1048576 <= self.max_prompt_tokens <= 2097152:
            raise BudgetError('invalid_policy')
        if type(self.max_output_tokens) is not int or not 1 <= self.max_output_tokens <= 400:
            raise BudgetError('invalid_policy')
        if not self.price_source.startswith('https://') or not self.context_source.startswith('https://'):
            raise BudgetError('invalid_policy')
        if type(self.verified_at) is not int or type(self.expires_at) is not int or not self.verified_at <= now < self.expires_at:
            raise BudgetError('price_snapshot_expired_or_not_yet_valid')
        minimum_input, minimum_output = ('2', '8') if self.currency == 'CNY' else ('0.3', '1.2')
        if number(self.input_per_million) < number(minimum_input) or number(self.output_per_million) < number(minimum_output):
            raise BudgetError('price_below_reviewed_peak')
        if self.currency == 'USD':
            if (type(self.fx_verified) is not bool or not self.fx_verified or not self.fx_source or not self.fx_source.startswith('https://')
                or type(self.fx_expires_at) is not int or now >= self.fx_expires_at
                or self.fx_cny_per_usd_upper is None or number(self.fx_cny_per_usd_upper) <= 0):
                raise BudgetError('conservative_fx_quote_unverified')
        elif self.fx_cny_per_usd_upper is not None:
            raise BudgetError('unexpected_fx_for_cny')

    def amount(self, prompt, completion):
        cost = (Decimal(prompt) * number(self.input_per_million) + Decimal(completion) * number(self.output_per_million)) / 1000000
        if self.currency == 'USD': cost *= number(self.fx_cny_per_usd_upper)
        return nano(cost)

    def serialized(self):
        return json.dumps(asdict(self), sort_keys=True, separators=(',', ':'))


class CNYLedger:
    def __init__(self, path, policy=None, *, clock=time.time):
        self.path, self.policy, self.clock = Path(path), policy or FeePolicy(), clock
        if number(self.policy.max_cny) > 50:
            raise BudgetError('use_scoped_audited_batch_ledger')
        if number(self.policy.max_cny) == 50 and not self.path.exists():
            raise BudgetError('limit_increase_requires_existing_ledger')
        try:
            self.policy.validate(self.clock())
        except BudgetError as exc:
            # Expiry blocks new authorizations, not read-only audit of old charges.
            if not self.path.exists() or exc.code not in ('price_snapshot_expired_or_not_yet_valid', 'conservative_fx_quote_unverified'):
                raise
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink(): raise BudgetError('unsafe_ledger_path')
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError:
            pass
        with self.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS policy (id INTEGER PRIMARY KEY CHECK(id=1), snapshot TEXT NOT NULL, halted TEXT)')
            db.execute('''CREATE TABLE IF NOT EXISTS attempts (
                operation_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                output_cap INTEGER NOT NULL, held_nano INTEGER NOT NULL, estimate_nano TEXT,
                phase TEXT NOT NULL, lease_until REAL, usage_json TEXT, reason TEXT)''')
            db.execute('''CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, operation_id TEXT, event TEXT NOT NULL, at REAL NOT NULL)''')
            row = db.execute('SELECT snapshot FROM policy WHERE id=1').fetchone()
            if row is None:
                db.execute('INSERT INTO policy VALUES (1, ?, NULL)', (self.policy.serialized(),))
            elif row[0] != self.policy.serialized():
                raise BudgetError('ledger_policy_mismatch')
            if number(self.policy.max_cny) == 50:
                exists = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='authorization_changes'").fetchone()
                if not exists or not db.execute('SELECT 1 FROM authorization_changes WHERE approval=? AND new_snapshot=?',
                    (LIMIT_APPROVAL,self.policy.serialized())).fetchone():
                    raise BudgetError('limit_increase_audit_missing')
            self.recover(db)

    def approve_cumulative_50(self, approval_reference):
        """Explicit operator action after user approval; retain all prior attempts.

        The approval reference is an audit label, not an authentication secret.
        No CLI or network request can silently invoke this transition.
        """
        if approval_reference != LIMIT_APPROVAL or number(self.policy.max_cny) != 10:
            raise BudgetError('limit_increase_not_authorized')
        revised = replace(self.policy,max_cny='50.00')
        with self.transaction() as db:
            self.admit(db)
            if db.execute("SELECT 1 FROM attempts WHERE phase NOT IN ('completed','cancelled_before_dispatch')").fetchone():
                raise BudgetError('limit_increase_requires_settled_attempts')
            if not db.execute('SELECT 1 FROM attempts').fetchone():
                raise BudgetError('limit_increase_requires_history')
            db.execute('CREATE TABLE IF NOT EXISTS authorization_changes (approval TEXT PRIMARY KEY, old_snapshot TEXT NOT NULL, new_snapshot TEXT NOT NULL, at REAL NOT NULL)')
            db.execute('INSERT INTO authorization_changes VALUES (?,?,?,?)',
                (approval_reference,self.policy.serialized(),revised.serialized(),self.clock()))
            db.execute('UPDATE policy SET snapshot=? WHERE id=1',(revised.serialized(),))
            self.event(db,None,'approved_cumulative_limit_50')
        self.policy=revised

    @contextmanager
    def transaction(self):
        if self.path.is_symlink(): raise BudgetError('unsafe_ledger_path')
        try:
            with closing(sqlite3.connect(self.path, timeout=10, isolation_level=None)) as db:
                db.row_factory = sqlite3.Row
                db.execute('PRAGMA synchronous=FULL')
                db.execute('BEGIN IMMEDIATE')
                try:
                    yield db
                except BudgetError:
                    # Expected refusals may have recorded a durable halt/recovery.
                    db.commit()
                    raise
                except BaseException:
                    db.rollback()
                    raise
                else:
                    db.commit()
        except sqlite3.Error:
            raise BudgetError('ledger_unavailable') from None

    def event(self, db, operation, code):
        db.execute('INSERT INTO events(operation_id,event,at) VALUES (?,?,?)', (operation, code, self.clock()))

    def recover(self, db):
        expired = db.execute("SELECT operation_id FROM attempts WHERE phase='dispatched' AND lease_until <= ?", (self.clock(),)).fetchall()
        for row in expired:
            db.execute("UPDATE attempts SET phase='unknown',reason='dispatch_lease_expired' WHERE operation_id=?", (row[0],))
            self.event(db, row[0], 'dispatch_lease_expired')
        if expired:
            db.execute("UPDATE policy SET halted=COALESCE(halted,'dispatch_lease_expired') WHERE id=1")

    def admit(self, db):
        # Revalidate on every dispatch, including reservations made before expiry.
        self.policy.validate(self.clock())
        row = db.execute('SELECT snapshot,halted FROM policy WHERE id=1').fetchone()
        if row['snapshot'] != self.policy.serialized(): raise BudgetError('ledger_policy_mismatch')
        self.recover(db)
        halted = db.execute('SELECT halted FROM policy WHERE id=1').fetchone()[0]
        if halted: raise BudgetError('ledger_halted')

    def reserve(self, operation_id, fingerprint, output_cap=400, *, run_id='offline'):
        if (not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', operation_id)
            or not re.fullmatch(r'[a-f0-9]{64}', fingerprint)
            or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', run_id)
            or type(output_cap) is not int or not 1 <= output_cap <= self.policy.max_output_tokens):
            raise BudgetError('invalid_attempt')
        with self.transaction() as db:
            self.admit(db)
            existing = db.execute('SELECT * FROM attempts WHERE operation_id=?', (operation_id,)).fetchone()
            if existing:
                if (existing['fingerprint'],existing['output_cap'],existing['run_id']) != (fingerprint,output_cap,run_id):
                    raise BudgetError('attempt_identity_conflict')
                return dict(existing)  # never authorizes a second dispatch
            held = self.policy.amount(self.policy.max_prompt_tokens, output_cap)
            total = db.execute('SELECT COALESCE(SUM(held_nano),0) FROM attempts').fetchone()[0]
            if total + held > nano(self.policy.max_cny):
                self.event(db, operation_id, 'cny_budget_exhausted')
                raise BudgetError('cny_budget_exhausted')
            db.execute('''INSERT INTO attempts VALUES (?,?,?,?,?,NULL,'reserved',NULL,NULL,NULL)''',
                       (operation_id,run_id,fingerprint,output_cap,held))
            self.event(db, operation_id, 'reserved')
            return dict(db.execute('SELECT * FROM attempts WHERE operation_id=?', (operation_id,)).fetchone())

    def dispatch(self, operation_id, *, lease_seconds=90):
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 120:
            raise BudgetError('invalid_dispatch_lease')
        with self.transaction() as db:
            self.admit(db)
            row = db.execute('SELECT phase FROM attempts WHERE operation_id=?', (operation_id,)).fetchone()
            if row is None or row['phase'] != 'reserved': raise BudgetError('attempt_not_dispatchable')
            db.execute("UPDATE attempts SET phase='dispatched',lease_until=? WHERE operation_id=?", (self.clock()+lease_seconds,operation_id))
            self.event(db, operation_id, 'dispatched')

    def cancel_before_dispatch(self, operation_id):
        with self.transaction() as db:
            row = db.execute('SELECT phase FROM attempts WHERE operation_id=?', (operation_id,)).fetchone()
            if row is None: raise BudgetError('attempt_not_found')
            if row['phase'] == 'cancelled_before_dispatch': return
            if row['phase'] != 'reserved': raise BudgetError('attempt_already_dispatched')
            db.execute("UPDATE attempts SET phase='cancelled_before_dispatch',held_nano=0 WHERE operation_id=?", (operation_id,))
            self.event(db, operation_id, 'cancelled_before_dispatch')

    def mark_unknown(self, operation_id, reason='unknown_usage', *, usage=None):
        if reason not in ('unknown_usage','provider_failure','cancelled','usage_invalid','bound_exceeded'):
            raise BudgetError('invalid_failure_category')
        with self.transaction() as db:
            row = db.execute('SELECT phase FROM attempts WHERE operation_id=?', (operation_id,)).fetchone()
            if row is None or row['phase'] not in ('dispatched','unknown'): raise BudgetError('attempt_not_dispatched')
            if usage is not None:
                try:
                    known = self.normalized_usage(usage)
                    estimate = self.policy.amount(known['prompt_tokens'],known['completion_tokens'])
                    db.execute('UPDATE attempts SET usage_json=?,estimate_nano=? WHERE operation_id=?',
                               (json.dumps(known,sort_keys=True),str(estimate),operation_id))
                except BudgetError:
                    pass  # malformed data is never logged; retain the full reserve
            db.execute("UPDATE attempts SET phase='unknown',reason=? WHERE operation_id=?", (reason,operation_id))
            db.execute('UPDATE policy SET halted=COALESCE(halted,?) WHERE id=1', (reason,))
            self.event(db, operation_id, reason)

    def settle(self, operation_id, usage):
        # Retain the complete reservation permanently; estimated usage is audit only.
        with self.transaction() as db:
            row = db.execute('SELECT * FROM attempts WHERE operation_id=?', (operation_id,)).fetchone()
            if row is None or row['phase'] not in ('dispatched','completed'):
                raise BudgetError('attempt_not_settleable')
            try:
                normalized = self.normalized_usage(usage)
                if normalized['prompt_tokens'] > self.policy.max_prompt_tokens or normalized['completion_tokens'] > row['output_cap']:
                    raise BudgetError('bound_exceeded')
            except BudgetError as exc:
                if exc.code == 'bound_exceeded':
                    # Preserve numeric evidence of a provider-bound breach; do not
                    # hide a possible bill above the contractual assumption.
                    db.execute('UPDATE attempts SET usage_json=?,estimate_nano=? WHERE operation_id=?',
                        (json.dumps(normalized,sort_keys=True),str(self.policy.amount(normalized['prompt_tokens'],normalized['completion_tokens'])),operation_id))
                db.execute("UPDATE attempts SET phase='unknown',reason=? WHERE operation_id=?", (exc.code,operation_id))
                db.execute('UPDATE policy SET halted=COALESCE(halted,?) WHERE id=1', (exc.code,))
                self.event(db, operation_id, exc.code)
                raise
            serialized = json.dumps(normalized, sort_keys=True)
            if row['phase'] == 'completed':
                if row['usage_json'] != serialized:
                    db.execute("UPDATE attempts SET phase='unknown',reason='settlement_conflict' WHERE operation_id=?", (operation_id,))
                    db.execute("UPDATE policy SET halted=COALESCE(halted,'settlement_conflict') WHERE id=1")
                    self.event(db,operation_id,'settlement_conflict')
                    raise BudgetError('settlement_conflict')
                return
            estimate = self.policy.amount(normalized['prompt_tokens'], normalized['completion_tokens'])
            db.execute("UPDATE attempts SET phase='completed',usage_json=?,estimate_nano=? WHERE operation_id=?", (serialized,str(estimate),operation_id))
            self.event(db, operation_id, 'completed_no_refund')

    @staticmethod
    def normalized_usage(usage):
        if not isinstance(usage, dict): raise BudgetError('unknown_usage')
        keys = ('prompt_tokens','completion_tokens','total_tokens')
        if not all(type(usage.get(key)) is int and usage[key] >= 0 for key in keys): raise BudgetError('usage_invalid')
        result = {key:usage[key] for key in keys}
        if result['prompt_tokens']+result['completion_tokens'] != result['total_tokens']: raise BudgetError('usage_invalid')
        details = usage.get('completion_tokens_details', {})
        if not isinstance(details, dict): raise BudgetError('usage_invalid')
        reasoning = details.get('reasoning_tokens')
        if reasoning is not None:
            if type(reasoning) is not int or not 0 <= reasoning <= result['completion_tokens']: raise BudgetError('usage_invalid')
            result['completion_tokens_details'] = {'reasoning_tokens':reasoning}
        # Cache hit/miss cannot reduce the conservative no-cache price or reserve.
        return result

    def snapshot(self):
        with self.transaction() as db:
            policy = db.execute('SELECT halted,snapshot FROM policy WHERE id=1').fetchone()
            rows = [dict(row) for row in db.execute('SELECT * FROM attempts ORDER BY operation_id')]
            held = sum(row['held_nano'] for row in rows)
            estimates = [int(row['estimate_nano']) if row['estimate_nano'] is not None else None for row in rows]
            return {'authorization':self.policy.authorization,'policy':json.loads(policy['snapshot']),
                    'mode':'public_bound_reservation' if self.policy.provider_bound_verified else 'offline_validation_only','halted':policy['halted'],
                    'reserved_cny':yuan(held),'remaining_reservable_cny':'0' if policy['halted'] else yuan(max(0,nano(self.policy.max_cny)-held)),
                    'unallocated_cny':yuan(max(0,nano(self.policy.max_cny)-held)),
                    'assumptions_breached':any(row['reason']=='bound_exceeded' for row in rows),
                    'known_usage_estimate_cny':yuan(sum(x for x in estimates if x is not None)),
                    'all_dispatched_usage_known':all(row['phase'] in ('reserved','cancelled_before_dispatch','completed') for row in rows),
                    'actual_billed_cny':None,'provider_bill_cap_guaranteed':False,
                    'attempts':rows,'events':[dict(row) for row in db.execute('SELECT * FROM events ORDER BY id')]}


class OfflineMonetaryProvider:
    """Offline end-to-end guard exercise; deliberately refuses real providers."""
    def __init__(self, ledger, provider, *, run_id=None):
        if getattr(provider, 'offline_budget_fixture', False) is not True:
            raise BudgetError('live_provider_not_enabled')
        self.ledger, self.provider = ledger, provider
        self.run_id = run_id or uuid.uuid4().hex
        self.attempt = 0

    async def complete(self, messages, **kwargs):
        self.attempt += 1
        operation = f'{self.run_id}:{self.attempt}'
        fingerprint = hashlib.sha256(json.dumps({'messages':messages,'params':kwargs},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        try:
            self.ledger.reserve(operation,fingerprint,kwargs.get('max_tokens'),run_id=self.run_id)
            self.ledger.dispatch(operation)
        except BudgetError as exc:
            raise ProviderUnavailable(exc.code) from None
        try:
            completion = await self.provider.complete(messages, **kwargs)
            self.ledger.settle(operation,completion.usage)
            return completion
        except BudgetError as exc:
            raise ProviderUnavailable(exc.code) from None
        except ProviderUnavailable as exc:
            self.ledger.mark_unknown(operation,'provider_failure',usage=exc.usage)
            raise
        except asyncio.CancelledError:
            self.ledger.mark_unknown(operation,'cancelled')
            raise
        except Exception:
            self.ledger.mark_unknown(operation,'provider_failure')
            raise ProviderUnavailable('provider_failure_budget_halted') from None
