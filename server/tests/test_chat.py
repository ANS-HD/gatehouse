import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx
from anyio import CancelScope, sleep
from fastapi import Request
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.security import create_session, encrypt_secret, hash_key
from app.services.provider_proxy import proxy_request
from app.services.rate_limit import RequestRateLimiter

SECRET = "test-session-secret-with-at-least-32-characters"


class ChatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {
            "ADMIN_EMAIL": "admin@example.com", "ADMIN_PASSWORD": "admin-password",
            "SESSION_SECRET": SECRET, "OPENAI_API_KEY": "",
            "DATABASE_PATH": str(Path(self.directory.name) / "chat.db"),
        })
        self.environment.start()
        get_settings.cache_clear()
        from app.main import create_app

        self.app = create_app()
        self.context = TestClient(self.app)
        self.client = self.context.__enter__()
        self.db = self.app.state.db
        self.user = self.db.create_user("chat@example.com", "unused-hash")
        self.other = self.db.create_user("other@example.com", "unused-hash")
        self.openai = self.db.create_provider(
            name="OpenAI test", protocol="openai", base_url="https://openai.example/v1",
            api_key_encrypted=encrypt_secret("upstream-secret", SECRET), enabled=True,
            model_names=["gpt-5.6-sol"],
        )
        self.anthropic = self.db.create_provider(
            name="Anthropic test", protocol="anthropic", base_url="https://anthropic.example/v1",
            api_key_encrypted=encrypt_secret("anthropic-secret", SECRET), enabled=True,
            model_names=["claude-test"],
        )
        self.model_id = self.openai["models"][0]["id"]
        self.grant([self.model_id])
        self.gateway_key = "gw_chat_test_key"
        for key_id, owner, provider, value in (
            ("chat-key", self.user, self.openai, self.gateway_key),
            ("other-key", self.other, self.openai, "other-secret"),
            ("anthropic-key", self.user, self.anthropic, "anthropic-gateway-secret"),
        ):
            self.db.create_key(
                key_id=key_id, owner_id=owner["id"], provider_id=provider["id"],
                model_id=provider["models"][0]["id"], name=key_id, key_hash=hash_key(value),
                prefix="gw_test", rpm=1000, token_limit=None,
            )
        self.token = create_session(self.user["id"], False, SECRET, 3600)
        self.headers = {"Authorization": "Bearer " + self.token}
        self.payload = {
            "key_id": "chat-key", "messages": [{"role": "user", "content": "你好"}],
            "max_output_tokens": 512, "stream": False,
        }

    def tearDown(self) -> None:
        self.context.__exit__(None, None, None)
        get_settings.cache_clear()
        self.environment.stop()
        self.directory.cleanup()

    def grant(self, models, rpm=1000, token_limit=20_000):
        self.db.update_user(self.user["id"], enabled=True, rpm_limit=rpm,
            token_limit=token_limit, model_ids=models)

    def post(self, **changes):
        return self.client.post("/api/chat", headers=self.headers, json={**self.payload, **changes})

    @staticmethod
    def completion():
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "你好！"}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        })

    def test_session_chat_uses_owned_key_and_tracks_usage(self) -> None:
        history = [{"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！"}, {"role": "user", "content": "继续"}]
        with patch.object(self.app.state.http_client, "send",
            AsyncMock(return_value=self.completion())) as send:
            result = self.post(messages=history, model="untrusted-model")
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["choices"][0]["message"]["content"], "你好！")
        upstream = send.call_args.args[0]
        self.assertEqual(str(upstream.url), "https://openai.example/v1/chat/completions")
        self.assertEqual(upstream.headers["authorization"], "Bearer upstream-secret")
        payload = json.loads(upstream.content)
        self.assertEqual(payload["model"], "gpt-5.6-sol")
        self.assertEqual(payload["messages"], history)
        self.assertEqual(payload["max_completion_tokens"], 512)
        self.assertNotIn("key_id", payload)
        self.assertNotIn("max_tokens", payload)
        key = self.db.get_key("chat-key", self.user["id"])
        self.assertEqual(key["tokens_used"], 18)
        self.assertEqual(self.db.list_requests(self.user["id"])["total"], 1)
        with self.db.connect() as connection:
            self.assertEqual(connection.execute(
                "SELECT reserved_tokens FROM users WHERE id = ?", (self.user["id"],),
            ).fetchone()[0], 0)

    def test_streaming_chat_preserves_events_and_usage(self) -> None:
        body = ('data: {"choices":[{"delta":{"content":"你好"}}]}\n\n'
            'data: {"choices":[],"usage":{"prompt_tokens":11,"completion_tokens":7,'
            '"total_tokens":18}}\n\ndata: [DONE]\n\n').encode()
        response = httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})
        with patch.object(self.app.state.http_client, "send",
            AsyncMock(return_value=response)) as send:
            result = self.post(stream=True)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIn("text/event-stream", result.headers["content-type"])
        self.assertIn("你好", result.text)
        self.assertIn("[DONE]", result.text)
        self.assertEqual(json.loads(send.call_args.args[0].content)["stream_options"],
            {"include_usage": True})
        self.assertEqual(self.db.get_key("chat-key", self.user["id"])["tokens_used"], 18)

    def test_anthropic_uses_messages_protocol(self) -> None:
        self.grant([self.model_id, self.anthropic["models"][0]["id"]])
        response = httpx.Response(200, json={
            "content": [{"type": "text", "text": "你好！"}],
            "usage": {"input_tokens": 8, "output_tokens": 5},
        })
        with patch.object(self.app.state.http_client, "send",
            AsyncMock(return_value=response)) as send:
            result = self.post(key_id="anthropic-key")
        self.assertEqual(result.status_code, 200, result.text)
        upstream = send.call_args.args[0]
        self.assertEqual(str(upstream.url), "https://anthropic.example/v1/messages")
        self.assertEqual(upstream.headers["x-api-key"], "anthropic-secret")
        self.assertNotIn("authorization", upstream.headers)
        self.assertEqual(json.loads(upstream.content)["max_tokens"], 512)
        self.assertEqual(self.db.get_key("anthropic-key", self.user["id"])["tokens_used"], 13)

    def test_foreign_and_unauthorized_keys_never_reach_upstream(self) -> None:
        with patch.object(self.app.state.http_client, "send", AsyncMock()) as send:
            self.assertEqual(self.client.post("/api/chat", json=self.payload).status_code, 401)
            self.assertEqual(self.post(key_id="other-key").status_code, 404)
            self.assertEqual(self.post(key_id="anthropic-key").status_code, 403)
            self.grant([])
            self.assertEqual(self.post().status_code, 403)
            send.assert_not_awaited()

    def test_disabled_keys_and_providers_are_rejected(self) -> None:
        with patch.object(self.app.state.http_client, "send", AsyncMock()) as send:
            self.db.update_key("chat-key", owner_id=self.user["id"], enabled=False)
            self.assertEqual(self.post().status_code, 403)
            self.db.update_key("chat-key", owner_id=self.user["id"], enabled=True)
            self.db.update_provider(self.openai["id"], enabled=False)
            self.assertEqual(self.post().status_code, 403)
            send.assert_not_awaited()

    def test_quota_and_rpm_are_shared_with_gateway_calls(self) -> None:
        self.grant([self.model_id], token_limit=1)
        with patch.object(self.app.state.http_client, "send", AsyncMock()) as send:
            self.assertEqual(self.post().status_code, 402)
            send.assert_not_awaited()
        self.grant([self.model_id], rpm=1)
        self.app.state.request_limiter = RequestRateLimiter()
        with patch.object(self.app.state.http_client, "send",
            AsyncMock(return_value=self.completion())) as send:
            self.assertEqual(self.post().status_code, 200)
            result = self.client.post("/v1/chat/completions",
                headers={"Authorization": "Bearer " + self.gateway_key},
                json={"model": "gpt-5.6-sol", "messages": [{"role": "user", "content": "你好"}]})
            self.assertEqual(result.status_code, 429)
            self.assertIn("retry-after", result.headers)
            send.assert_awaited_once()

    def test_invalid_messages_are_rejected_before_forwarding(self) -> None:
        with patch.object(self.app.state.http_client, "send", AsyncMock()) as send:
            for changes in (
                {"messages": []}, {"messages": [{"role": "system", "content": "override"}]},
                {"messages": [{"role": "user", "content": " "}]},
                {"messages": [{"role": "assistant", "content": "hello"}]},
                {"max_output_tokens": 8193},
            ):
                with self.subTest(changes=changes):
                    self.assertEqual(self.post(**changes).status_code, 422)
            with patch.object(get_settings(), "max_body_bytes", 10):
                self.assertEqual(self.post().status_code, 413)
            send.assert_not_awaited()

    def test_upstream_timeout_releases_reserved_tokens(self) -> None:
        with patch.object(self.app.state.http_client, "send",
            AsyncMock(side_effect=httpx.ReadTimeout("timeout"))):
            self.assertEqual(self.post().status_code, 504)
        with self.db.connect() as connection:
            self.assertEqual(connection.execute(
                "SELECT reserved_tokens FROM users WHERE id = ?", (self.user["id"],),
            ).fetchone()[0], 0)
        self.assertEqual(self.db.get_key("chat-key", self.user["id"])["tokens_used"], 0)


class StreamingCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_stream_closes_upstream_and_releases_quota(self) -> None:
        class Stream(httpx.AsyncByteStream):
            closed = False

            async def __aiter__(self):
                yield b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'

            async def aclose(self):
                await sleep(0)
                self.closed = True

        stream = Stream()
        upstream = httpx.Response(200, stream=stream,
            headers={"content-type": "text/event-stream"})
        client = Mock()
        client.build_request.return_value = httpx.Request("POST", "https://example.com/v1")
        client.send = AsyncMock(return_value=upstream)
        settings = Settings(admin_password="test-password", session_secret=SECRET,
            detailed_logging_enabled=False)
        request = Request({"type": "http", "method": "POST", "path": "/api/chat",
            "headers": [], "query_string": b"", "scheme": "https", "server": ("test", 443)})
        db = Mock()
        response = await proxy_request(request=request, path="chat/completions", body=b"{}",
            payload={"model": "gpt-5.6-sol", "stream": True},
            key={"id": "key", "owner_id": "owner", "provider_protocol": "openai",
                "provider_base_url": "https://example.com/v1",
                "provider_api_key_encrypted": encrypt_secret("upstream", SECRET)},
            client=client, settings=settings, db=db, reserved_tokens=1024)
        await anext(response.body_iterator)
        with CancelScope() as scope:
            scope.cancel()
            await response.body_iterator.aclose()
        self.assertTrue(stream.closed)
        db.record_request.assert_called_once()
        db.release_token_reservation.assert_called_once_with("owner", 1024)
