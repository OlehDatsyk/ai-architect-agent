"""Exercises the real Anthropic SDK against a mocked HTTP transport: request shape, response
parsing and error mapping, without network access or an API key."""

import json

import httpx2 as httpx  # the Anthropic SDK 1.x transport package
import pytest

from app.core.errors import AppError
from app.services.claude_service import AnthropicStructuredClient

SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"], "additionalProperties": False}


def api_message(text: str, stop_reason: str = "end_turn") -> dict:
    return {
        "id": "msg_01XyzTest", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
        "content": [{"type": "text", "text": text}], "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 3210, "output_tokens": 1650, "cache_read_input_tokens": 2900, "cache_creation_input_tokens": 0},
    }


def client_with(handler) -> AnthropicStructuredClient:
    return AnthropicStructuredClient(
        api_key="sk-ant-test", model="claude-sonnet-5-5", max_tokens=8000, timeout=10, max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


async def call(client: AnthropicStructuredClient):
    return await client.generate(system="You are a test.", messages=[{"role": "user", "content": "Hi"}], schema=SCHEMA)


async def test_request_uses_structured_outputs_and_caches_the_system_prompt() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=api_message('{"a": "ok"}'))

    reply = await call(client_with(handler))

    body = seen["body"]
    assert seen["url"].endswith("/v1/messages")
    assert seen["headers"]["x-api-key"] == "sk-ant-test"
    assert body["model"] == "claude-sonnet-5-5" and body["max_tokens"] == 8000
    assert body["output_config"] == {"format": {"type": "json_schema", "schema": SCHEMA}}
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "tool_choice" not in body and "tools" not in body
    assert reply.text == '{"a": "ok"}'
    assert reply.stop_reason == "end_turn"
    assert reply.usage.cache_read_input_tokens == 2900


async def test_refusal_stop_reason_is_passed_through() -> None:
    reply = await call(client_with(lambda r: httpx.Response(200, json=api_message("No.", "refusal"))))
    assert reply.stop_reason == "refusal"


@pytest.mark.parametrize(
    ("status", "error_type", "code"),
    [
        (401, "authentication_error", "CLAUDE_AUTH_ERROR"),
        (403, "permission_error", "CLAUDE_PERMISSION_ERROR"),
        (404, "not_found_error", "CLAUDE_MODEL_ERROR"),
        (429, "rate_limit_error", "CLAUDE_RATE_LIMIT"),
        (400, "invalid_request_error", "CLAUDE_BAD_REQUEST"),
        (529, "overloaded_error", "CLAUDE_UNAVAILABLE"),
        (500, "api_error", "CLAUDE_UNAVAILABLE"),
    ],
)
async def test_api_errors_map_to_clear_app_errors(status: int, error_type: str, code: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"type": "error", "error": {"type": error_type, "message": "test"}})

    with pytest.raises(AppError) as caught:
        await call(client_with(handler))
    assert caught.value.code == code
    assert "sk-ant-test" not in caught.value.message


async def test_network_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    with pytest.raises(AppError) as caught:
        await call(client_with(handler))
    assert caught.value.code == "CLAUDE_CONNECTION_ERROR"


def anthropic_error(status: int, message: str):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"type": "error", "error": {"type": "invalid_request_error", "message": message}})
    return handler


async def test_no_credit_says_what_to_do() -> None:
    with pytest.raises(AppError) as caught:
        await call(client_with(anthropic_error(400, "Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.")))
    assert caught.value.code == "CLAUDE_BILLING_ERROR" and caught.value.status_code == 402
    assert "console.anthropic.com" in caught.value.message and "subscription does not include API credit" in caught.value.message


async def test_other_rejections_show_anthropics_reason_in_development() -> None:
    reason = "messages: text content blocks must be non-empty"
    with pytest.raises(AppError) as caught:
        await call(client_with(anthropic_error(400, reason)))
    assert caught.value.code == "CLAUDE_BAD_REQUEST" and caught.value.message == "Anthropic rejected the request."
    assert caught.value.details["reason"] == reason and caught.value.details["anthropic_status"] == 400
    assert "sk-ant" not in json.dumps(caught.value.details)


def test_check_claude_explains_a_missing_key(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from app.core.config import get_settings
    from scripts import check_claude

    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    get_settings.cache_clear()
    try:
        assert check_claude.main() == 1
    finally:
        get_settings.cache_clear()
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().out


# ----------------------------------------------------------------------------- classification and fallbacks

from app.agents.architect_agent import OUTPUT_SCHEMA as INTERPRETATION_SCHEMA  # noqa: E402
from app.agents.modification_agent import OUTPUT_SCHEMA as MODIFICATION_SCHEMA  # noqa: E402
from app.services import claude_service  # noqa: E402
from app.services.claude_service import prepare_schema  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_fallback_memory():
    claude_service._json_only_schemas.clear()
    yield
    claude_service._json_only_schemas.clear()


@pytest.mark.parametrize(("message", "code"), [
    ("model: claude-sonnet-9 is not available for your organization", "CLAUDE_MODEL_ERROR"),
    ("output_config.format.schema: Schema is too complex for compilation", "CLAUDE_SCHEMA_ERROR"),
    ("Your credit balance is too low to access the Anthropic API.", "CLAUDE_BILLING_ERROR"),
])
async def test_bad_requests_are_classified_by_cause(message: str, code: str) -> None:
    with pytest.raises(AppError) as caught:
        await call(client_with(anthropic_error(400, message)))
    assert caught.value.code == code


async def test_failures_are_logged_with_status_type_and_request_id_but_never_the_key(caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, headers={"request-id": "req_011TEST"},
                              json={"type": "error", "error": {"type": "invalid_request_error", "message": "bad thing"}})
    with pytest.raises(AppError):
        await call(client_with(handler))
    logged = caplog.text
    assert "status=400" in logged and "type=invalid_request_error" in logged and "req_011TEST" in logged and "bad thing" in logged
    assert "sk-ant-test" not in logged


async def test_production_never_sends_anthropics_reason_to_the_browser() -> None:
    client = client_with(anthropic_error(400, "internal detail"))
    client.expose_details = False
    with pytest.raises(AppError) as caught:
        await call(client)
    assert caught.value.details == {} and "internal detail" not in caught.value.message


async def test_rejected_schema_falls_back_to_json_only_once_and_remembers() -> None:
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if "output_config" in body:
            return httpx.Response(400, json={"type": "error", "error": {"type": "invalid_request_error",
                                                                        "message": "output_config.format.schema: unsupported"}})
        return httpx.Response(200, json=api_message('Here it is:\n```json\n{"a": "x"}\n```'))

    client = client_with(handler)
    reply = await call(client)
    assert json.loads(reply.text) == {"a": "x"}
    assert "output_config" not in bodies[1] and "Reply with a single JSON object" in json.dumps(bodies[1]["system"])
    await call(client)  # the next request goes straight to the JSON-only path
    assert len(bodies) == 3 and "output_config" not in bodies[2]


@pytest.mark.parametrize("message", ["Your credit balance is too low.", "model: x is not available"])
async def test_account_and_model_errors_never_fall_back(message: str) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(400, json={"type": "error", "error": {"type": "invalid_request_error", "message": message}})

    with pytest.raises(AppError):
        await call(client_with(handler))
    assert len(calls) == 1


async def test_rejected_prompt_caching_is_dropped_and_the_request_retried() -> None:
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if isinstance(body["system"], list):
            return httpx.Response(400, json={"type": "error", "error": {"type": "invalid_request_error",
                                                                        "message": "system.0.cache_control: not supported"}})
        return httpx.Response(200, json=api_message('{"a": "y"}'))

    client = client_with(handler)
    assert json.loads((await call(client)).text) == {"a": "y"}
    assert bodies[1]["system"] == "You are a test." and "output_config" in bodies[1]
    assert client.prompt_caching is False


async def test_health_check_reports_verified_and_failed() -> None:
    def ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=api_message('{"status": "OK"}'))

    result = await client_with(ok).check()
    assert (result.status, result.structured_outputs) == ("verified", "ok")
    failed = await client_with(anthropic_error(400, "Your credit balance is too low.")).check()
    assert (failed.status, failed.code) == ("failed", "CLAUDE_BILLING_ERROR")


def test_the_apps_schemas_are_accepted_by_prepare_schema() -> None:
    assert prepare_schema(INTERPRETATION_SCHEMA) and prepare_schema(MODIFICATION_SCHEMA)


@pytest.mark.parametrize(("schema", "problem"), [
    ({"type": "object", "properties": {"n": {"type": "integer", "minimum": 0}}, "required": ["n"], "additionalProperties": False}, "minimum"),
    ({"type": "object", "properties": {}}, "additionalProperties"),
    ({"type": "object", "properties": {"x": {"$ref": "#/$defs/Missing"}}, "required": ["x"], "additionalProperties": False}, "unknown definition"),
    ({"$defs": {"Node": {"type": "object", "properties": {"child": {"$ref": "#/$defs/Node"}}, "required": ["child"], "additionalProperties": False}},
      "$ref": "#/$defs/Node"}, "recursive"),
    ({"type": "array", "items": {"type": "string"}, "minItems": 3}, "minItems"),
])
def test_prepare_schema_rejects_what_structured_outputs_cannot_take(schema: dict, problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        prepare_schema(schema)
