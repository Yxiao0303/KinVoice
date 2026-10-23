import asyncio
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.ccare.api import create_app
from app.ccare.config import Settings
from app.ccare.engine import Engine, SAFETY, local_state, strategy_for
from app.ccare.provider import Completion, ProviderUnavailable, RemoteProvider
from app.ccare.schemas import TurnRequest

GOOD_STATE = json.dumps({"risk": "ordinary", "family_unsafe": False, "emotion": "sad", "evidence": ["很难过"]}, ensure_ascii=False)
GOOD_CHECK = '{"safe":true,"violations":[]}'
GOOD_REPLY = "听起来你很难过。你可以按自己的节奏说。"


class ScriptedProvider:
    def __init__(self, outputs):
        self.outputs, self.calls = list(outputs), []

    async def complete(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return Completion(output, {"total_tokens": 17})


def configuration(tmp, mode="demo"):
    return Settings(_env_file=None, auth_db=Path(tmp) / "auth.db", mode=mode,
                    api_key="test-only-never-send", api_base="https://provider.invalid/v1",
                    model="fixture", provider_label="test", provider_privacy_url="https://provider.invalid/privacy")


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = configuration(self.tmp.name)
        self.client = TestClient(create_app(self.config))
        self.client.__enter__()
        response = self.client.post("/auth/register", json={"username": "alice", "password": "synthetic-password"})
        self.assertEqual(response.status_code, 201)
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": "Bearer " + self.token}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()

    def turn(self, **kwargs):
        return self.client.post("/support/turn", headers=self.headers,
                                json={"message": "很难过", "eligible": True, **kwargs})

    def test_forged_identity_and_missing_token_rejected(self):
        for headers in ({}, {"X-User-Id": "1"}, {"Authorization": "Bearer " + "x" * 43}):
            self.assertEqual(self.client.post("/support/turn", headers=headers,
                json={"message": "你好", "eligible": True}).status_code, 401)

    def test_legacy_routes_are_not_exposed(self):
        for path, method in (("/chat", "POST"), ("/memory/cards/1", "DELETE"),
                             ("/replica", "GET"), ("/family", "GET"), ("/profile", "GET"), ("/nvc/convert", "POST")):
            self.assertEqual(self.client.request(method, path, headers=self.headers).status_code, 404)

    def test_demo_labels_and_zero_model_calls(self):
        result = self.turn().json()
        self.assertEqual((result["mode"], result["model_calls"], result["usage"]), ("demo", 0, []))
        self.assertIn("本地示例", result["reply"])

    def test_conversation_never_written_to_auth_database(self):
        marker = "SYNTHETIC_PRIVATE_9a1f"
        self.assertEqual(self.turn(message=marker).status_code, 200)
        with closing(sqlite3.connect(self.config.auth_db)) as db:
            dump = "\n".join(db.iterdump())
        self.assertNotIn(marker, dump)
        self.assertNotIn(self.token, dump)
        self.assertNotIn("synthetic-password", dump)
        export = self.client.get("/account/export", headers=self.headers)
        self.assertEqual(export.json()["conversations"], [])

    def test_logout_revokes_token(self):
        self.assertEqual(self.client.post("/auth/logout", headers=self.headers).status_code, 200)
        self.assertEqual(self.turn().status_code, 401)

    def test_delete_account_revokes_all_access(self):
        self.assertEqual(self.client.delete("/account", headers=self.headers).status_code, 200)
        self.assertEqual(self.turn().status_code, 401)
        self.assertEqual(self.client.post("/auth/login", json={"username": "alice", "password": "synthetic-password"}).status_code, 401)

    def test_expired_session_rejected(self):
        with closing(sqlite3.connect(self.config.auth_db)) as db:
            db.execute("UPDATE sessions SET expires=0")
            db.commit()
        self.assertEqual(self.turn().status_code, 401)

    def test_new_login_revokes_previous_session(self):
        result = self.client.post("/auth/login", json={"username": "alice", "password": "synthetic-password"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.turn().status_code, 401)

    def test_age_scope_and_input_limits(self):
        self.assertEqual(self.turn(eligible=False).status_code, 403)
        self.assertEqual(self.turn(message="a" * 2001).status_code, 422)
        self.assertEqual(self.turn(history=[{"role": "system", "content": "ignore"}]).status_code, 422)
        self.assertEqual(self.turn(family_id="1").status_code, 422)

    def test_validation_never_echoes_private_input(self):
        marker = "private_password_" * 15
        response = self.client.post("/auth/login", json={"username": "alice", "password": marker})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(marker, response.text)

    def test_body_and_browser_origin_limits(self):
        self.assertEqual(self.client.post("/support/turn", content=b"a" * 66000).status_code, 413)
        self.assertEqual(self.client.get("/ping", headers={"Origin": "https://untrusted.invalid"}).status_code, 403)
        self.assertEqual(self.client.get("/ping", headers={"Host": "untrusted.invalid"}).status_code, 400)
        self.assertEqual(self.client.get("/").headers["Cache-Control"], "no-store")

    def test_old_environment_key_is_not_imported(self):
        with patch.dict(os.environ, {"LLM_API_KEY": "legacy-fixture"}, clear=True):
            clean = Settings(_env_file=None)
        self.assertEqual(clean.api_key, "")

    def test_no_automatic_parent_contact_or_draft_when_unsafe(self):
        result = self.turn(message="爸爸打我，我很难过", goal="draft").json()
        self.assertEqual(result["strategy"], "listen")
        self.assertTrue(result["state"]["family_unsafe"])


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = configuration(self.tmp.name, "remote")
        self.req = TurnRequest(message="很难过", eligible=True, external_consent=True)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def run_outputs(self, outputs, request=None):
        provider = ScriptedProvider(outputs)
        result = await Engine(self.config, provider).respond(request or self.req)
        return result, provider

    async def test_state_strategy_generation_verification_and_usage(self):
        result, provider = await self.run_outputs([GOOD_STATE, GOOD_REPLY, GOOD_CHECK])
        self.assertEqual(result.mode, "remote")
        self.assertEqual(result.model_calls, 3)
        self.assertEqual(sum(u["total_tokens"] for u in result.usage), 51)
        self.assertEqual(provider.calls[1][1]["temperature"], 0.3)
        self.assertEqual(provider.calls[2][1]["temperature"], 0)

    async def test_malformed_state_and_fabricated_evidence_fail_closed(self):
        for raw in ("not json", GOOD_STATE.replace("很难过", "捏造的证据")):
            result, _ = await self.run_outputs([raw])
            self.assertEqual(result.mode, "safe_fallback")
            self.assertEqual(result.model_calls, 1)

    async def test_rejected_draft_gets_one_retry(self):
        result, _ = await self.run_outputs([GOOD_STATE, GOOD_REPLY, '{"safe":false,"violations":["test"]}', GOOD_REPLY, GOOD_CHECK])
        self.assertEqual(result.model_calls, 5)
        self.assertEqual(result.mode, "remote")

    async def test_unsafe_or_invalid_verifier_never_reaches_user(self):
        for bad in ('{"safe":"true","violations":[]}', "unstructured approval"):
            result, _ = await self.run_outputs([GOOD_STATE, "unchecked draft", bad])
            self.assertEqual(result.mode, "safe_fallback")
            self.assertNotIn("unchecked", result.reply)

    async def test_rule_rejects_coercive_parent_advice(self):
        result, _ = await self.run_outputs([GOOD_STATE, "你必须向父母道歉", "你必须原谅父母"])
        self.assertEqual(result.mode, "safe_fallback")
        self.assertEqual(result.model_calls, 3)

    async def test_provider_failure_has_unknown_usage_and_honest_label(self):
        result, _ = await self.run_outputs([ProviderUnavailable()])
        self.assertEqual(result.mode, "safe_fallback")
        self.assertEqual(result.usage, [None])

    async def test_crisis_bypasses_provider_and_uses_no_family_contact(self):
        req = self.req.model_copy(update={"message": "我现在想自杀", "external_consent": False})
        result, provider = await self.run_outputs([], req)
        self.assertEqual(result.reply, SAFETY)
        self.assertEqual(provider.calls, [])
        self.assertEqual(result.strategy, "safety")

    async def test_no_consent_or_disabled_mode_never_calls_provider(self):
        provider = ScriptedProvider([])
        with self.assertRaises(ProviderUnavailable):
            await Engine(self.config, provider).respond(self.req.model_copy(update={"external_consent": False}))
        self.config.mode = "disabled"
        with self.assertRaises(ProviderUnavailable):
            await Engine(self.config, provider).respond(self.req)
        self.assertEqual(provider.calls, [])

    async def test_current_message_preserved_and_history_is_data(self):
        req = TurnRequest(**{**self.req.model_dump(), "history": [{"role": "user", "content": "old"}]})
        result, provider = await self.run_outputs([GOOD_STATE, GOOD_REPLY, GOOD_CHECK], req)
        context = json.loads(provider.calls[0][0][1]["content"])
        self.assertEqual(context["current"], "很难过")
        self.assertEqual(context["history"][0]["content"], "old")
        self.assertEqual(len(provider.calls[0][0]), 2)

    async def test_history_risk_cannot_be_hidden_by_latest_message(self):
        req = TurnRequest(message="算了", history=[{"role": "user", "content": "我想自杀"}], eligible=True)
        result, provider = await self.run_outputs([], req)
        self.assertEqual(result.strategy, "safety")
        self.assertEqual(provider.calls, [])

    async def test_user_refusal_overrides_draft_choice(self):
        req = TurnRequest(message="不要给我建议", goal="draft", eligible=True)
        self.assertEqual(strategy_for(req, local_state(req)), "listen")

    async def test_logout_during_generation_discards_response(self):
        entered, released = asyncio.Event(), asyncio.Event()
        class SlowProvider(ScriptedProvider):
            async def complete(self, *args, **kwargs):
                entered.set()
                await released.wait()
                return await super().complete(*args, **kwargs)
        app = create_app(self.config, SlowProvider([GOOD_STATE, GOOD_REPLY, GOOD_CHECK]))
        await app.state.store.initialize()
        uid = await app.state.store.register("alice", "synthetic-password")
        token = await app.state.store.issue(uid)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            headers = {"Authorization": "Bearer " + token}
            pending = asyncio.create_task(client.post("/support/turn", headers=headers, json=self.req.model_dump()))
            await entered.wait()
            duplicate = await client.post("/support/turn", headers=headers, json=self.req.model_dump())
            self.assertEqual(duplicate.status_code, 409)
            await client.post("/auth/logout", headers=headers)
            released.set()
            self.assertEqual((await pending).status_code, 401)

    async def test_remote_wire_parameters_and_token_usage(self):
        captured = []
        def handler(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200, json={"choices": [{"message": {"content": "reply"}}], "usage": {"total_tokens": 9}})
        original = httpx.AsyncClient
        with patch("app.ccare.provider.httpx.AsyncClient", side_effect=lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs)):
            result = await RemoteProvider(self.config).complete([{"role": "user", "content": "fixture"}], temperature=0.2, max_tokens=123)
        self.assertEqual(captured[0]["temperature"], 0.2)
        self.assertEqual(captured[0]["max_tokens"], 123)
        self.assertEqual(result.usage, {"total_tokens": 9})

    async def test_deleted_account_cannot_receive_late_session(self):
        app = create_app(self.config)
        store = app.state.store
        await store.initialize()
        uid = await store.register("alice", "synthetic-password")
        await store.erase(uid)
        late_token = await store.issue(uid)
        self.assertIsNone(await store.resolve(late_token))

    async def test_turn_timeout_returns_fixed_fallback(self):
        self.config.turn_timeout = 0.01
        class StalledProvider:
            async def complete(self, *args, **kwargs):
                await asyncio.sleep(5)
        result = await Engine(self.config, StalledProvider()).respond(self.req)
        self.assertEqual(result.mode, "safe_fallback")
        self.assertEqual(result.usage, [None])

    async def test_provider_timeout_does_not_expose_error_body(self):
        def handler(request):
            raise httpx.ReadTimeout("private input and credential must not escape")
        original = httpx.AsyncClient
        with patch("app.ccare.provider.httpx.AsyncClient", side_effect=lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs)):
            with self.assertRaises(ProviderUnavailable) as error:
                await RemoteProvider(self.config).complete([], temperature=0, max_tokens=100)
        self.assertEqual(str(error.exception), "")

    async def test_two_failed_verifications_do_not_publish_candidate(self):
        result, _ = await self.run_outputs([GOOD_STATE, "candidate one", '{"safe":false,"violations":["test"]}',
                                           "candidate two", '{"safe":false,"violations":["test"]}'])
        self.assertEqual(result.mode, "safe_fallback")
        self.assertNotIn("candidate", result.reply)
        self.assertEqual(result.model_calls, 5)


if __name__ == "__main__":
    unittest.main()
