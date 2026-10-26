import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from app.ccare.config import Settings
from app.ccare.core_smoke import run_core, existing_ledger, CoreBudgetProvider, scenario, TEXT
from app.ccare.cny_ledger import CNYLedger, BudgetError
from app.ccare.provider import Completion, ProviderUnavailable
from app.ccare.smoke import POLICY, OPERATION, FINGERPRINT
from app.ccare.engine import local_state, output_violations
from app.ccare.policy import validate_state, decide
from app.ccare.reviews import apply_reviews
from app.ccare.schemas import State

USAGE = {'prompt_tokens':10,'completion_tokens':20,'total_tokens':30,
         'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':10}


class CoreSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'budget.db'
        self.ledger = CNYLedger(self.path, POLICY, clock=lambda:POLICY.verified_at+100)
        self.ledger.reserve(OPERATION, FINGERPRINT, 400, run_id=OPERATION)
        self.ledger.dispatch(OPERATION)
        self.ledger.settle(OPERATION, USAGE)
        self.config = Settings(_env_file=None, mode='remote', api_key='offline-fixture',
            api_base='https://api.deepseek.com',model='deepseek-flash',provider_kind='deepseek',
            provider_label='fixture',provider_privacy_url='https://example.com',max_tokens=400)

    def tearDown(self):
        self.tmp.cleanup()

    def fixture(self, *, draft='我先听你说，不急着准备沟通措辞。', safe=True, failure=False, malformed=False):
        ledger = self.ledger
        class Fixture:
            calls = 0
            async def complete(self, messages, **params):
                self.calls += 1
                snapshot = ledger.snapshot()
                assert len(snapshot['attempts']) == self.calls+1
                assert any(a['phase']=='dispatched' for a in snapshot['attempts'])
                assert params['max_tokens'] == 400
                if failure:
                    raise ProviderUnavailable('rate_limited')
                if self.calls == 1:
                    text = 'invalid' if malformed else json.dumps({'emotion':'sad','evidence':['难过']})
                elif self.calls == 2:
                    data = json.loads(messages[1]['content'])
                    assert data['state']['emotion'] == 'unknown'
                    assert data['state']['support_intent'] == 'listen'
                    assert data['strategy'] == 'listen'
                    text = draft
                else:
                    text = json.dumps({'safe':safe,'violations':[] if safe else ['fixture_rejection']})
                return Completion(text, USAGE, 'offline-fixture', 200)
        return Fixture()

    def test_three_stage_success_and_no_reentry(self):
        fixture = self.fixture()
        report = asyncio.run(run_core(self.config,self.ledger,fixture))
        self.assertEqual(fixture.calls,3)
        self.assertEqual(report['result']['mode'],'remote')
        self.assertTrue(all(report['generation_review_propagation'].values()))
        self.assertEqual(report['cumulative']['reserved_cny'],'8.401408')
        self.assertEqual(report['cumulative']['remaining_reservable_cny'],'1.598592')
        with self.assertRaises(BudgetError): CoreBudgetProvider(self.ledger,fixture)

    def test_rule_rejection_falls_back_without_rewrite_or_verification_call(self):
        fixture=self.fixture(draft='你必须马上原谅父母。')
        report=asyncio.run(run_core(self.config,self.ledger,fixture))
        self.assertEqual(fixture.calls,2)
        self.assertEqual(report['result']['mode'],'safe_fallback')
        self.assertIn('draft_rule_rejected',report['result']['checks'])

    def test_model_rejection_falls_back_without_fourth_call(self):
        fixture=self.fixture(safe=False)
        report=asyncio.run(run_core(self.config,self.ledger,fixture))
        self.assertEqual(fixture.calls,3)
        self.assertEqual(report['result']['mode'],'safe_fallback')
        self.assertEqual(report['result']['failure_code'],'verification_rejected')

    def test_transport_failure_halts_after_one_attempt(self):
        fixture=self.fixture(failure=True)
        report=asyncio.run(run_core(self.config,self.ledger,fixture))
        self.assertEqual(fixture.calls,1)
        self.assertEqual(report['result']['mode'],'safe_fallback')
        self.assertEqual(report['cumulative']['remaining_reservable_cny'],'0')

    def test_malformed_state_halts_after_one_attempt(self):
        fixture=self.fixture(malformed=True)
        report=asyncio.run(run_core(self.config,self.ledger,fixture))
        self.assertEqual(fixture.calls,1)
        self.assertEqual(report['cumulative']['halted'],'provider_failure')

    def test_missing_ledger_is_not_created(self):
        missing=Path(self.tmp.name)/'missing.db'
        with self.assertRaises(BudgetError): existing_ledger(missing)
        self.assertFalse(missing.exists())

    def test_same_fixed_input_contains_reviews_for_future_comparisons(self):
        req=scenario()
        self.assertEqual(req.message,TEXT)
        self.assertEqual({r.action for r in req.reviews},{'correct','revoke'})

    def test_real_failure_replay_is_rejected_before_model_verifier(self):
        fixture = self.fixture(draft='听起来你有些难过，一边是父母希望你回家，一边是你想留校准备展示。你愿意多说一点这种难过吗？')
        report = asyncio.run(run_core(self.config,self.ledger,fixture))
        self.assertEqual(fixture.calls,2)
        self.assertEqual(report['result']['mode'],'safe_fallback')
        self.assertIn('revoked_emotion_reference',report['result']['checks'])

    def test_unrelated_quote_not_presented_as_reviewed_intent_evidence(self):
        req = scenario()
        state = State(emotion='sad', evidence=['这让我有些难过'],
                      support_intent='listen',intent_evidence=['这让我有些难过'])
        links = validate_state(req,state)
        self.assertEqual(state.support_intent,'unknown')
        self.assertEqual(state.intent_evidence,[])
        self.assertFalse(any(link.purpose == 'intent' for link in links))
        apply_reviews(req,state,links,local_state(req))
        self.assertEqual(state.support_intent,'listen')
        self.assertEqual(state.intent_evidence,[])
        self.assertTrue(any(a.field=='support_intent' and a.origin=='confirmed' for a in state.assessments))

    def test_current_supported_emotion_not_blocked_without_revocation(self):
        state = State(emotion='sad', evidence=['难过'])
        req = scenario().model_copy(update={'reviews':[]})
        links = validate_state(req,state)
        self.assertNotIn('revoked_emotion_reference', output_violations('听起来你有些难过。',decide(req,state,links),state))
