import asyncio
import json
import tempfile
import unittest

import httpx
from fastapi.testclient import TestClient

from app.ccare.api import create_app
from app.ccare.provider import Completion
from test_ccare import configuration, ScriptedProvider, GOOD_STATE, GOOD_REPLY, GOOD_CHECK


class StreamContractTests(unittest.TestCase):
    def request(self, mode="remote", outputs=None, **updates):
        with tempfile.TemporaryDirectory() as tmp:
            provider = ScriptedProvider(outputs or [GOOD_STATE, GOOD_REPLY, GOOD_CHECK])
            with TestClient(create_app(configuration(tmp, mode), provider)) as client:
                token = client.post('/auth/register', json={'username':'alice','password':'synthetic-password'}).json()['access_token']
                response = client.post('/support/stream', headers={'Authorization':'Bearer '+token},
                    json={'message':'很难过','eligible':True,'external_consent':True, **updates})
                return response, provider

    def test_only_checked_reply_is_sent_after_live_stage_metadata(self):
        response, provider = self.request()
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/x-ndjson', response.headers['content-type'])
        events = [json.loads(line) for line in response.text.splitlines()]
        self.assertEqual([e['sequence'] for e in events], list(range(1, len(events)+1)))
        self.assertEqual(events[0]['protocol'], 'ccare-stream-v1')
        self.assertEqual(events[-1]['type'], 'result')
        self.assertEqual(events[-1]['result']['mode'], 'remote')
        started = [e['stage'] for e in events if e.get('event') == 'started']
        self.assertEqual(started, ['state','generate','verify'])
        for event in events[:-1]:
            self.assertNotIn(GOOD_REPLY, json.dumps(event, ensure_ascii=False))
            self.assertNotIn('很难过', json.dumps(event, ensure_ascii=False))
        self.assertEqual(len(provider.calls), 3)

    def test_rejected_candidates_never_appear_in_stream(self):
        response, _ = self.request(outputs=[GOOD_STATE, '你必须向父母道歉', '你必须原谅父母'])
        self.assertNotIn('你必须向父母道歉', response.text)
        self.assertNotIn('你必须原谅父母', response.text)
        self.assertEqual(json.loads(response.text.splitlines()[-1])['result']['mode'], 'safe_fallback')

    def test_demo_has_zero_model_stages(self):
        response, provider = self.request(mode='demo')
        events = [json.loads(line) for line in response.text.splitlines()]
        self.assertEqual([e['type'] for e in events], ['start','policy','result'])
        self.assertEqual(provider.calls, [])
        self.assertEqual(events[-1]['result']['model_calls'], 0)

    def test_no_consent_fails_without_calls_or_private_error(self):
        response, provider = self.request(external_consent=False)
        events = [json.loads(line) for line in response.text.splitlines()]
        self.assertEqual(events[-1]['code'], 'model_unavailable')
        self.assertEqual(provider.calls, [])

    def test_scope_and_input_rejected_before_stream(self):
        response, provider = self.request(eligible=False)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(provider.calls, [])

    def test_unexpected_provider_error_is_sanitized(self):
        response, _ = self.request(outputs=[RuntimeError('private-provider-body')])
        self.assertNotIn('private-provider-body', response.text)
        self.assertEqual(json.loads(response.text.splitlines()[-1])['code'], 'processing_failed')


class DisconnectTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.entered, self.released, self.cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
        outer = self
        class PausingProvider(ScriptedProvider):
            async def complete(self, *args, **kwargs):
                outer.entered.set()
                try:
                    await outer.released.wait()
                    return await super().complete(*args, **kwargs)
                except asyncio.CancelledError:
                    outer.cancelled.set()
                    raise
        self.provider = PausingProvider([GOOD_STATE, GOOD_REPLY, GOOD_CHECK])
        self.app = create_app(configuration(self.tmp.name, 'remote'), self.provider)
        await self.app.state.store.initialize()
        self.uid = await self.app.state.store.register('alice', 'synthetic-password')
        self.token = await self.app.state.store.issue(self.uid)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def start_request(self):
        disconnected, progress = asyncio.Event(), asyncio.Event()
        body = json.dumps({'message':'很难过','eligible':True,'external_consent':True}).encode()
        sent, chunks = False, []
        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {'type':'http.request','body':body,'more_body':False}
            await disconnected.wait()
            return {'type':'http.disconnect'}
        async def send(event):
            if event['type'] == 'http.response.body' and event.get('body'):
                chunks.append(event['body'])
                if b'"started"' in event['body']:
                    progress.set()
        scope = {'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':'POST',
                 'scheme':'http','path':'/support/stream','raw_path':b'/support/stream','query_string':b'',
                 'root_path':'','server':('testserver',80),'client':('127.0.0.1',1000),
                 'headers':[(b'host',b'testserver'),(b'content-type',b'application/json'),
                            (b'authorization',('Bearer '+self.token).encode())]}
        task = asyncio.create_task(self.app(scope, receive, send))
        await asyncio.wait_for(self.entered.wait(), 2)
        await asyncio.wait_for(progress.wait(), 2)
        return task, disconnected, chunks

    async def test_disconnect_cancels_worker_and_releases_account_slot(self):
        task, disconnected, chunks = await self.start_request()
        disconnected.set()
        await asyncio.wait_for(task, 2)
        self.assertTrue(self.cancelled.is_set())
        self.assertEqual(self.provider.calls, [])
        self.assertNotIn(b'"type": "result"', b''.join(chunks))
        # A new request must be admitted immediately after worker cleanup.
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://testserver') as client:
            response = await client.post('/support/turn', headers={'Authorization':'Bearer '+self.token},
                json={'message':'我现在想自杀','eligible':True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['model_calls'], 0)

    async def test_second_request_is_busy_until_first_is_cancelled(self):
        task, disconnected, _ = await self.start_request()
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://testserver') as client:
                response = await client.post('/support/stream', headers={'Authorization':'Bearer '+self.token},
                    json={'message':'另一个请求','eligible':True,'external_consent':True})
            self.assertEqual(response.status_code, 409)
        finally:
            disconnected.set()
            await asyncio.wait_for(task, 2)

    async def test_logout_during_stream_never_returns_reply(self):
        task, _, chunks = await self.start_request()
        await self.app.state.store.revoke(self.token)
        self.released.set()
        await asyncio.wait_for(task, 2)
        text = b''.join(chunks).decode()
        self.assertNotIn(GOOD_REPLY, text)
        self.assertIn('session_expired', text)

