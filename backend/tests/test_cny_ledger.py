"""Fictional/offline monetary reservations; never creates a live provider."""
import asyncio
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
import unittest

from app.ccare.cny_ledger import BudgetError, CNYLedger, FeePolicy, OfflineMonetaryProvider
from app.ccare.provider import Completion, ProviderUnavailable

NOW=1792818000  # within the documented 2026-10-24 snapshot
HASH=hashlib.sha256(b'fictional fixture').hexdigest()
USAGE={'prompt_tokens':10,'completion_tokens':20,'total_tokens':30,
       'completion_tokens_details':{'reasoning_tokens':5}}

# Separate processes exercise SQLite locking, not a shared Python lock.
def reserve_in_process(path, index):
    try:
        ledger=CNYLedger(path,clock=lambda:NOW)
        ledger.reserve(f'worker:{index}',HASH,run_id=f'process:{index}')
        return 'reserved'
    except BudgetError as exc: return exc.code

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'budget.db'
        self.ledger=CNYLedger(self.path,clock=lambda:NOW)
    def tearDown(self): self.tmp.cleanup()

    def attempt(self, operation='a', usage=USAGE):
        self.ledger.reserve(operation,HASH)
        self.ledger.dispatch(operation)
        self.ledger.settle(operation,usage)

    def test_exact_decimal_full_context_and_reasoning_not_double_counted(self):
        self.assertEqual(self.ledger.policy.amount(1048576,400),2100352000)
        self.attempt()
        state=self.ledger.snapshot()
        self.assertEqual(state['reserved_cny'],'2.100352')
        self.assertEqual(state['known_usage_estimate_cny'],'0.00018')
        self.assertEqual(state['remaining_reservable_cny'],'7.899648')
        self.assertIsNone(state['actual_billed_cny'])
        self.assertFalse(state['provider_bill_cap_guaranteed'])
        self.assertFalse(state['policy']['provider_bound_verified'])

    def test_cross_run_and_retry_reservations_never_reset_or_refund(self):
        for index in range(4):
            ledger=CNYLedger(self.path,clock=lambda:NOW)
            ledger.reserve(f'run:{index}:attempt:1',HASH,run_id=f'run:{index}')
            ledger.dispatch(f'run:{index}:attempt:1')
            ledger.settle(f'run:{index}:attempt:1',USAGE)
        with self.assertRaises(BudgetError) as caught:
            CNYLedger(self.path,clock=lambda:NOW).reserve('retry:2',HASH,run_id='retry')
        self.assertEqual(caught.exception.code,'cny_budget_exhausted')
        state=self.ledger.snapshot()
        self.assertEqual(state['reserved_cny'],'8.401408')
        self.assertEqual(state['remaining_reservable_cny'],'1.598592')
        self.assertIn('cny_budget_exhausted',[e['event'] for e in state['events']])

    def test_idempotent_reserve_and_settle_never_authorize_second_dispatch(self):
        a=self.ledger.reserve('same',HASH)
        self.assertEqual(a,self.ledger.reserve('same',HASH))
        with self.assertRaises(BudgetError): self.ledger.reserve('same','b'*64)
        self.ledger.dispatch('same')
        with self.assertRaises(BudgetError): self.ledger.dispatch('same')
        self.ledger.settle('same',USAGE)
        self.ledger.settle('same',USAGE)
        self.assertEqual(len(self.ledger.snapshot()['attempts']),1)

    def test_multiprocess_concurrent_reservations_cannot_overspend(self):
        with ProcessPoolExecutor(max_workers=6) as pool:
            futures=[pool.submit(reserve_in_process,str(self.path),i) for i in range(12)]
            outcomes=[f.result(timeout=15) for f in futures]
        self.assertEqual(outcomes.count('reserved'),4)
        self.assertEqual(outcomes.count('cny_budget_exhausted'),8)
        self.assertEqual(self.ledger.snapshot()['reserved_cny'],'8.401408')

    def test_only_unclaimed_cancellation_releases_money(self):
        self.ledger.reserve('a',HASH)
        self.ledger.cancel_before_dispatch('a')
        self.ledger.cancel_before_dispatch('a')
        self.assertEqual(self.ledger.snapshot()['reserved_cny'],'0')
        with self.assertRaises(BudgetError): self.ledger.dispatch('a')
        self.ledger.reserve('b',HASH)
        self.ledger.dispatch('b')
        with self.assertRaises(BudgetError): self.ledger.cancel_before_dispatch('b')
        self.ledger.mark_unknown('b','cancelled')
        self.assertEqual(self.ledger.snapshot()['reserved_cny'],'2.100352')
        with self.assertRaises(BudgetError): self.ledger.reserve('c',HASH)

    def test_expired_dispatch_recovered_after_restart_and_halt_is_durable(self):
        self.ledger.reserve('a',HASH)
        self.ledger.dispatch('a',lease_seconds=30)
        resumed=CNYLedger(self.path,clock=lambda:NOW+31)
        with self.assertRaises(BudgetError): resumed.reserve('b',HASH)
        state=CNYLedger(self.path,clock=lambda:NOW+32).snapshot()
        self.assertEqual(state['halted'],'dispatch_lease_expired')
        self.assertEqual(state['reserved_cny'],'2.100352')
        self.assertEqual(state['attempts'][0]['phase'],'unknown')

    def test_missing_invalid_and_out_of_bounds_usage_halt_with_no_refund(self):
        cases=[None, {'prompt_tokens':True,'completion_tokens':1,'total_tokens':2},
               {**USAGE,'total_tokens':1}, {**USAGE,'completion_tokens_details':{'reasoning_tokens':21}},
               {'prompt_tokens':1048577,'completion_tokens':20,'total_tokens':1048597},
               {'prompt_tokens':10,'completion_tokens':401,'total_tokens':411}]
        for i,usage in enumerate(cases):
            ledger=CNYLedger(Path(self.tmp.name)/f'bad{i}.db',clock=lambda:NOW)
            ledger.reserve('a',HASH); ledger.dispatch('a')
            with self.assertRaises(BudgetError): ledger.settle('a',usage)
            state=ledger.snapshot()
            self.assertIsNotNone(state['halted'])
            self.assertEqual(state['reserved_cny'],'2.100352')
            if state['attempts'][0]['reason']=='bound_exceeded':
                self.assertTrue(state['assumptions_breached'])
                self.assertIsNotNone(state['attempts'][0]['estimate_nano'])
            else:
                self.assertIsNone(state['attempts'][0]['estimate_nano'])
            self.assertEqual(state['remaining_reservable_cny'],'0')
            with self.assertRaises(BudgetError): ledger.reserve('b',HASH)

    def test_expired_price_blocks_dispatch_but_keeps_audit_readable(self):
        self.ledger.reserve('a',HASH)
        expired=CNYLedger(self.path,clock=lambda:FeePolicy().expires_at+1)
        with self.assertRaises(BudgetError): expired.dispatch('a')
        self.assertEqual(expired.snapshot()['reserved_cny'],'2.100352')
        with self.assertRaises(BudgetError):
            CNYLedger(Path(self.tmp.name)/'new-expired.db',clock=lambda:FeePolicy().expires_at+1)

    def test_policy_or_limit_change_cannot_reset_existing_authorization(self):
        for policy in [replace(FeePolicy(),input_per_million='3'),replace(FeePolicy(),max_cny='5')]:
            with self.assertRaises(BudgetError) as caught: CNYLedger(self.path,policy,clock=lambda:NOW)
            self.assertEqual(caught.exception.code,'ledger_policy_mismatch')
        with self.assertRaises(BudgetError): CNYLedger(Path(self.tmp.name)/'larger.db',replace(FeePolicy(),max_cny='11'),clock=lambda:NOW)

    def test_usd_requires_audited_conservative_fx_and_upward_rounding(self):
        policy=replace(FeePolicy(),currency='USD',input_per_million='0.3',output_per_million='1.2')
        with self.assertRaises(BudgetError): CNYLedger(Path(self.tmp.name)/'fx-missing.db',policy,clock=lambda:NOW)
        # Synthetic FX bound, not asserted as a verified real exchange quote.
        policy=replace(policy,fx_cny_per_usd_upper='10',fx_verified=True,fx_source='https://example.invalid/synthetic-fx',fx_expires_at=NOW+60)
        ledger=CNYLedger(Path(self.tmp.name)/'fx.db',policy,clock=lambda:NOW)
        ledger.reserve('a',HASH)
        self.assertEqual(ledger.snapshot()['reserved_cny'],'3.150528')
        expired=CNYLedger(Path(self.tmp.name)/'fx.db',policy,clock=lambda:NOW+61)
        with self.assertRaises(BudgetError): expired.dispatch('a')

    def test_only_numeric_usage_and_fingerprints_enter_ledger(self):
        self.attempt(usage={**USAGE,'raw_response':'PRIVATE_FIXTURE','completion_tokens_details':{'reasoning_tokens':5,'text':'PRIVATE_REASONING'}})
        serialized=str(self.ledger.snapshot())
        self.assertNotIn('PRIVATE_FIXTURE',serialized)
        self.assertNotIn('PRIVATE_REASONING',serialized)
        self.assertNotIn('fictional fixture',serialized)

class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_pre_reservation_limits_actual_fixture_dispatches_and_survives_restart(self):
        class Fixture:
            offline_budget_fixture=True
            def __init__(self): self.calls=0
            async def complete(self,*args,**kwargs):
                self.calls+=1
                return Completion('{}',USAGE,'offline-fixture')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'ledger.db'
            fixture=Fixture()
            for i in range(6):
                provider=OfflineMonetaryProvider(CNYLedger(path,clock=lambda:NOW),fixture,run_id=f'run{i}')
                try: await provider.complete([],max_tokens=400)
                except ProviderUnavailable as exc: self.assertEqual(exc.code,'cny_budget_exhausted')
            self.assertEqual(fixture.calls,4)
            with self.assertRaises(BudgetError): OfflineMonetaryProvider(CNYLedger(path,clock=lambda:NOW),object())

    async def test_unknown_usage_failure_and_cancel_halt_before_another_attempt(self):
        class Fixture:
            offline_budget_fixture=True
            def __init__(self,mode): self.mode,self.calls=mode,0
            async def complete(self,*args,**kwargs):
                self.calls+=1
                if self.mode=='failure': raise RuntimeError('DO_NOT_LOG_PRIVATE')
                if self.mode=='cancel': raise asyncio.CancelledError()
                return Completion('{}',None)
        for mode in ('failure','cancel','unknown'):
            with tempfile.TemporaryDirectory() as tmp:
                ledger=CNYLedger(Path(tmp)/'ledger.db',clock=lambda:NOW)
                fixture=Fixture(mode)
                provider=OfflineMonetaryProvider(ledger,fixture)
                with self.assertRaises((ProviderUnavailable,asyncio.CancelledError)):
                    await provider.complete([],max_tokens=400)
                with self.assertRaises(ProviderUnavailable): await provider.complete([],max_tokens=400)
                self.assertEqual(fixture.calls,1)
                self.assertIsNotNone(ledger.snapshot()['halted'])
                self.assertNotIn('DO_NOT_LOG_PRIVATE',str(ledger.snapshot()))

class AdditionalInvariantTests(unittest.TestCase):
    def test_lower_than_public_context_or_peak_price_is_not_admitted(self):
        for policy in [replace(FeePolicy(),max_prompt_tokens=1),replace(FeePolicy(),input_per_million='0.1'),replace(FeePolicy(),output_per_million='1')]:
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(BudgetError): CNYLedger(Path(tmp)/'ledger.db',policy,clock=lambda:NOW)

    def test_known_failed_usage_is_audited_but_never_refunded_or_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger=CNYLedger(Path(tmp)/'ledger.db',clock=lambda:NOW)
            ledger.reserve('a',HASH); ledger.dispatch('a')
            ledger.mark_unknown('a','provider_failure',usage=USAGE)
            state=ledger.snapshot()
            self.assertEqual(state['reserved_cny'],'2.100352')
            self.assertEqual(state['known_usage_estimate_cny'],'0.00018')
            self.assertEqual(state['halted'],'provider_failure')
            self.assertFalse(state['all_dispatched_usage_known'])
            with self.assertRaises(BudgetError): ledger.reserve('retry2',HASH)

class ProxyCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_production_client_keeps_proxy_ca_and_credential_placeholder(self):
        import httpx
        from unittest.mock import patch
        from app.ccare.provider import RemoteProvider
        from app.ccare.config import Settings
        config=Settings(_env_file=None,mode='remote',provider_kind='deepseek',api_key='synthetic-placeholder-never-send',
            api_base='https://api.deepseek.com',model='deepseek-flash',provider_label='DeepSeek',provider_privacy_url='https://example.org/privacy')
        captured=[]
        def handler(request): return httpx.Response(200,json={'model':'deepseek-flash','choices':[{'finish_reason':'stop','message':{'content':'{}'}}]})
        original=httpx.AsyncClient
        def factory(**kwargs):
            captured.append(kwargs.copy())
            return original(transport=httpx.MockTransport(handler),**{**kwargs,'trust_env':False})
        with patch('app.ccare.provider.httpx.AsyncClient',side_effect=factory):
            result=await RemoteProvider(config).complete([{'role':'user','content':'Return JSON'}],temperature=0,max_tokens=400,json_mode=True)
        self.assertTrue(captured[0]['trust_env'])
        self.assertFalse(captured[0]['follow_redirects'])
        self.assertNotIn('verify',captured[0])  # default verification stays on
        self.assertEqual(result.model,'deepseek-flash')

class StorageFailureTests(unittest.TestCase):
    def test_corruption_and_symlink_are_blocked_without_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'corrupt.db'
            path.write_bytes(b'not a database')
            with self.assertRaises(BudgetError) as caught: CNYLedger(path,clock=lambda:NOW)
            self.assertEqual(caught.exception.code,'ledger_unavailable')
            self.assertEqual(path.read_bytes(),b'not a database')
            link=Path(tmp)/'alias.db'
            link.symlink_to(path)
            with self.assertRaises(BudgetError): CNYLedger(link,clock=lambda:NOW)

class AmbiguousSettlementTests(unittest.TestCase):
    def test_conflicting_completed_receipt_freezes_remaining_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger=CNYLedger(Path(tmp)/'ledger.db',clock=lambda:NOW)
            ledger.reserve('a',HASH); ledger.dispatch('a'); ledger.settle('a',USAGE)
            with self.assertRaises(BudgetError):
                ledger.settle('a',{'prompt_tokens':11,'completion_tokens':20,'total_tokens':31})
            self.assertEqual(ledger.snapshot()['halted'],'settlement_conflict')
            self.assertEqual(ledger.snapshot()['reserved_cny'],'2.100352')
            self.assertEqual(ledger.snapshot()['remaining_reservable_cny'],'0')
            with self.assertRaises(BudgetError): ledger.reserve('b',HASH)
