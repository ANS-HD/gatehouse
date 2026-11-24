import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.routes.gateway import router
from app.core.config import Settings, get_settings
from app.services.rate_limit import RequestRateLimiter


class GatewayRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        settings = Settings(
            admin_password="test-admin-password",
            session_secret="test-session-secret-with-at-least-32-characters",
        )
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_settings] = lambda: settings
        self.db = Mock()
        self.db.get_key_by_hash.return_value = {
            "id": "test-key", "enabled": True, "owner_id": "test-owner",
            "owner_enabled": True, "owner_rpm_limit": 10_000,
            "provider_enabled": True, "provider_protocol": "openai",
            "model_id": "test-model", "model_enabled": True, "model_name": "gpt-5.6-sol",
        }
        self.db.reserve_tokens.return_value = True
        app.state.db = self.db
        app.state.request_limiter = RequestRateLimiter()
        app.state.http_client = Mock()
        self.context = TestClient(app)
        self.client = self.context.__enter__()
        self.proxy = AsyncMock(return_value=JSONResponse({"ok": True}))
        self.proxy_patch = patch("app.api.routes.gateway.proxy_request", self.proxy)
        self.proxy_patch.start()

    def tearDown(self) -> None:
        self.proxy_patch.stop()
        self.context.__exit__(None, None, None)

    def post(self, body: bytes, content_type: str | None = "application/json"):
        headers = {"Authorization": "Bearer gw_test"}
        if content_type is not None:
            headers["Content-Type"] = content_type
        return self.client.post("/v1/chat/completions", content=body, headers=headers)

    def test_json_media_types_preserve_model_and_token_reservation(self) -> None:
        payload = {
            "model": "gpt-5.6-sol",
            "messages": [{"role": "user", "content": "你好，请简单介绍一下自己。"}],
            "max_completion_tokens": 512,
        }
        body = json.dumps(payload, ensure_ascii=False).encode()
        for content_type in (
            "application/json", "Application/JSON; charset=utf-8", "application/vnd.api+json",
        ):
            with self.subTest(content_type=content_type):
                self.assertEqual(self.post(body, content_type).status_code, 200)
                forwarded = self.proxy.call_args.kwargs
                self.assertEqual(forwarded["body"], body)
                self.assertEqual(forwarded["payload"], payload)
                self.assertEqual(forwarded["reserved_tokens"], len(body) + 512)

    def test_invalid_requests_are_actionable_and_never_reach_upstream(self) -> None:
        cases = (
            (b"", "application/json", 400, "Request body is empty"),
            (b'{"model":"gpt-5.6-sol"}', None, 415, "Content-Type: application/json"),
            (b'{"model":"gpt-5.6-sol"}', "text/plain", 415, "Content-Type: application/json"),
            (b'{"model":"gpt-5.6-sol"}', "application/x-www-form-urlencoded", 415,
             "Content-Type: application/json"),
            (b'{"model":', "application/json", 400, "Invalid JSON body"),
            (b'{"model":"\xff"}', "application/json", 400, "Invalid JSON body"),
            (b'"{\\"model\\":\\"gpt-5.6-sol\\"}"', "application/json", 400,
             "JSON body must be an object"),
            (b"[]", "application/json", 400, "JSON body must be an object"),
            (b"null", "application/json", 400, "JSON body must be an object"),
            (b"{}", "application/json", 400, "non-empty string model"),
            (b'{"model":42}', "application/json", 400, "non-empty string model"),
            (b'{"model":" "}', "application/json", 400, "non-empty string model"),
        )
        for body, content_type, expected_status, message in cases:
            with self.subTest(body=body, content_type=content_type):
                result = self.post(body, content_type)
                self.assertEqual(result.status_code, expected_status, result.text)
                self.assertIn(message, result.json()["detail"])
        self.proxy.assert_not_awaited()
        self.db.reserve_tokens.assert_not_called()

    def test_model_assignment_remains_enforced(self) -> None:
        result = self.post(b'{"model":"another-model"}')
        self.assertEqual(result.status_code, 403)
        self.proxy.assert_not_awaited()
        self.db.reserve_tokens.assert_not_called()

    def test_multipart_model_still_reaches_upstream(self) -> None:
        body = (
            b'--boundary\r\nContent-Disposition: form-data; name="model"\r\n\r\n'
            b'gpt-5.6-sol\r\n--boundary--\r\n'
        )
        result = self.post(body, "multipart/form-data; boundary=boundary")
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(self.proxy.call_args.kwargs["payload"])
        self.assertEqual(self.proxy.call_args.kwargs["body"], body)
