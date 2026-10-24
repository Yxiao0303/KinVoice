import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from app.ccare.config import Settings
from app.ccare.cny_ledger import CNYLedger, BudgetError
from app.ccare.provider import RemoteProvider
from app.ccare.smoke import POLICY, run_single


class SingleSmokeTests(unittest.TestCase):
    def run_fixture(self, response, *, again=False):
        requests = []
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ledger.db'
            ledger = CNYLedger(path, POLICY, clock=lambda: POLICY.verified_at + 100)
            def handler(request):
                import json
                requests.append(json.loads(request.content))
                self.assertEqual(ledger.snapshot()['reserved_cny'], '2.100352')
                self.assertEqual(ledger.snapshot()['attempts'][0]['phase'], 'dispatched')
                return response
            config = Settings(_env_file=None, api_key='offline-fixture', provider_kind='deepseek',
                              api_base='https://api.deepseek.com', model='deepseek-flash')
            client = httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False)
            with patch('app.ccare.provider.httpx.AsyncClient', return_value=client):
                result = asyncio.run(run_single(ledger, RemoteProvider(config)))
            if again:
                resumed = CNYLedger(path, POLICY, clock=lambda: POLICY.verified_at + 101)
                with self.assertRaises(BudgetError):
                    asyncio.run(run_single(resumed, RemoteProvider(config)))
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0]['thinking'], {'type': 'disabled'})
            self.assertEqual(requests[0]['max_tokens'], 400)
            self.assertEqual(requests[0]['response_format'], {'type': 'json_object'})
            self.assertEqual(requests[0]['model'], 'deepseek-flash')
            self.assertNotIn('tools', requests[0])
            self.assertEqual(result['reserved_cny'], '2.100352')
            return result

    @staticmethod
    def success(usage=True, content='{"ok":true,"case":"synthetic"}'):
        data = {'model':'deepseek-flash-fixture', 'choices':[{'message':{'content':content},'finish_reason':'stop'}]}
        if usage:
            data['usage'] = {'prompt_tokens':10, 'completion_tokens':20, 'total_tokens':30,
                            'prompt_cache_hit_tokens':0, 'prompt_cache_miss_tokens':10}
        return httpx.Response(200, json=data)

    def test_success_reserves_before_network_and_reopen_cannot_redispatch(self):
        report = self.run_fixture(self.success(), again=True)
        self.assertEqual(report['status'], 'completed')
        self.assertEqual(report['http_status'], 200)
        self.assertTrue(report['fixed_json_matched'])
        self.assertEqual(report['remaining_reservable_cny'], '7.899648')

    def test_http_failure_keeps_hold_halts_and_never_retries(self):
        report = self.run_fixture(httpx.Response(429, json={'error':'fixture'}), again=True)
        self.assertEqual(report['http_status'], 429)
        self.assertEqual(report['remaining_reservable_cny'], '0')
        self.assertEqual(report['halted'], 'provider_failure')

    def test_missing_usage_halts(self):
        report = self.run_fixture(self.success(usage=False), again=True)
        self.assertEqual(report['halted'], 'unknown_usage')

    def test_invalid_json_keeps_known_usage_and_full_hold(self):
        report = self.run_fixture(self.success(content='invalid'), again=True)
        self.assertFalse(report['json_parsed'])
        self.assertEqual(report['known_usage_estimate_cny'], '0.00018')
        self.assertEqual(report['http_status'], 200)
