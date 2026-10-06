"""The only module that talks to the Anthropic API.

Agents depend on the StructuredClaudeClient protocol, so tests can substitute a scripted
client and the rest of the application never imports the SDK.

Requests:
    generate()         structured JSON for the agents: structured outputs (output_config.format),
                       with a JSON-only fallback used *only* when Anthropic rejects the schema itself
    structured_once()  one structured request, no fallback (diagnostics)
    generate_text()    a plain text request
    check()            health check: a tiny text request, then a tiny structured request

Every request goes through _create(), and every failure through classify(), so errors are
reported the same way everywhere: a stable code, a safe message, and (outside production)
Anthropic's own reason. The API key is never logged or returned.
"""

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import anthropic

from app.core.errors import AppError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass(frozen=True)
class StructuredReply:
    text: str
    stop_reason: str | None
    model: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    request_id: str | None = None


class StructuredClaudeClient(Protocol):
    async def generate(
        self, *, system: str, messages: list[dict[str, Any]], schema: dict[str, Any]
    ) -> StructuredReply: ...


# ----------------------------------------------------------------------------- errors

# code -> (HTTP status for our API, message safe to show anywhere)
CLAUDE_ERRORS: dict[str, tuple[int, str]] = {
    "CLAUDE_AUTH_ERROR": (502, "Anthropic authentication failed. Check ANTHROPIC_API_KEY in .env."),
    "CLAUDE_PERMISSION_ERROR": (502, "This Anthropic API key is not allowed to use the configured model."),
    "CLAUDE_MODEL_ERROR": (502, "The configured Claude model is unavailable. Check ANTHROPIC_MODEL in .env."),
    "CLAUDE_BILLING_ERROR": (402, "Your Anthropic account has no API credit. Add credit at console.anthropic.com "
                                  "(Settings, Billing). A Claude.ai subscription does not include API credit."),
    "CLAUDE_SCHEMA_ERROR": (502, "Anthropic rejected the structured-output schema."),
    "CLAUDE_RATE_LIMIT": (429, "Claude API rate limit reached. Please try again shortly."),
    "CLAUDE_CONNECTION_ERROR": (503, "Claude could not be reached. Check your internet connection and try again."),
    "CLAUDE_UNAVAILABLE": (503, "Claude is temporarily unavailable. Try again shortly."),
    "CLAUDE_BAD_REQUEST": (502, "Anthropic rejected the request."),
}
# Codes that a JSON-only retry cannot fix: they are about the account, key, model or limits.
NO_FALLBACK = {"CLAUDE_AUTH_ERROR", "CLAUDE_PERMISSION_ERROR", "CLAUDE_MODEL_ERROR", "CLAUDE_BILLING_ERROR",
               "CLAUDE_RATE_LIMIT", "CLAUDE_CONNECTION_ERROR", "CLAUDE_UNAVAILABLE"}

_SCHEMA_WORDS = ("schema", "output_config", "json_schema", "output_format", "structured output", "grammar")
_MODEL_WORDS = re.compile(r"\bmodel\b.*\b(not found|not available|unavailable|does not exist|invalid|not supported)", re.I)


class ClaudeError(AppError):
    """An Anthropic failure, classified. `reason` is Anthropic's own message (never contains the key)."""

    def __init__(self, code: str, reason: str, *, http_status: int | None, error_type: str | None,
                 request_id: str | None, expose_details: bool) -> None:
        status_code, message = CLAUDE_ERRORS[code]
        details: dict[str, object] = {}
        if expose_details:  # development only: production never sends Anthropic's text to the browser
            details = {"reason": reason, "anthropic_status": http_status, "anthropic_type": error_type,
                       "anthropic_request_id": request_id}
        super().__init__(code, message, status_code, details={k: v for k, v in details.items() if v is not None})
        self.reason, self.http_status, self.error_type, self.request_id = reason, http_status, error_type, request_id


def anthropic_reason(exc: anthropic.APIStatusError) -> str:
    """Anthropic's own explanation of an error, from the response body (never contains the key)."""
    body = exc.body if isinstance(exc.body, dict) else {}
    error = body.get("error") if isinstance(body.get("error"), dict) else body
    reason = error.get("message") if isinstance(error, dict) else None
    return str(reason or exc.message or "no reason given")[:400]


def _error_type(exc: anthropic.APIStatusError) -> str | None:
    body = exc.body if isinstance(exc.body, dict) else {}
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    return error.get("type") if isinstance(error, dict) else None


def classify(exc: Exception) -> tuple[str, str]:
    """(code, reason) for any exception the Anthropic SDK raises."""
    if isinstance(exc, (anthropic.APITimeoutError, anthropic.APIConnectionError)):
        return "CLAUDE_CONNECTION_ERROR", str(exc)[:400]
    if not isinstance(exc, anthropic.APIStatusError):
        return "CLAUDE_UNAVAILABLE", str(exc)[:400]
    reason = anthropic_reason(exc)
    lowered = reason.lower()
    if isinstance(exc, anthropic.AuthenticationError):
        return "CLAUDE_AUTH_ERROR", reason
    if isinstance(exc, anthropic.PermissionDeniedError):
        return "CLAUDE_PERMISSION_ERROR", reason
    if isinstance(exc, anthropic.NotFoundError):
        return "CLAUDE_MODEL_ERROR", reason
    if isinstance(exc, anthropic.RateLimitError):
        return "CLAUDE_RATE_LIMIT", reason
    if isinstance(exc, anthropic.BadRequestError):
        if "credit balance" in lowered or "billing" in lowered:
            return "CLAUDE_BILLING_ERROR", reason
        if _MODEL_WORDS.search(reason):
            return "CLAUDE_MODEL_ERROR", reason
        if "cache_control" in lowered:
            return "CLAUDE_CACHE", reason  # internal: retried without prompt caching
        if any(word in lowered for word in _SCHEMA_WORDS):
            return "CLAUDE_SCHEMA_ERROR", reason
        return "CLAUDE_BAD_REQUEST", reason
    return "CLAUDE_UNAVAILABLE", reason


def explain_bad_request(exc: anthropic.BadRequestError, expose_details: bool = True) -> ClaudeError:
    """Kept for callers of the earlier API: a 400 from Anthropic as a classified error."""
    code, reason = classify(exc)
    return ClaudeError("CLAUDE_BAD_REQUEST" if code == "CLAUDE_CACHE" else code, reason, http_status=exc.status_code,
                       error_type=_error_type(exc), request_id=getattr(exc, "request_id", None), expose_details=expose_details)


# ----------------------------------------------------------------------------- schemas

UNSUPPORTED_KEYWORDS = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minLength",
                        "maxLength", "maxItems", "uniqueItems", "contains", "patternProperties", "if", "then", "else",
                        "not", "oneOf", "dependentRequired", "dependentSchemas"}


def prepare_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Check a schema against what Anthropic structured outputs accept, and return it.

    Raises ValueError listing every problem: unsupported keywords, objects that allow extra
    properties, minItems other than 0 or 1, unresolvable or recursive references."""
    problems: list[str] = []
    defs = schema.get("$defs", {})

    def walk(node: Any, path: str, stack: frozenset[str]) -> None:
        if isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]", stack)
            return
        if not isinstance(node, dict):
            return
        for key in node.keys() & UNSUPPORTED_KEYWORDS:
            problems.append(f"{path}: unsupported keyword '{key}'")
        if node.get("minItems", 0) not in (0, 1):
            problems.append(f"{path}: minItems must be 0 or 1")
        if (node.get("type") == "object" or "properties" in node) and node.get("additionalProperties") is not False:
            problems.append(f"{path}: objects must set additionalProperties to false")
        if "$ref" in node:
            ref = node["$ref"].rsplit("/", 1)[-1]
            if ref not in defs:
                problems.append(f"{path}: reference to unknown definition '{ref}'")
            elif ref in stack:
                problems.append(f"{path}: recursive reference to '{ref}'")
            else:
                walk(defs[ref], f"{path}->{ref}", stack | {ref})
        for key, value in node.items():
            if key not in ("$defs", "$ref", "enum", "const", "default", "description", "title", "required"):
                walk(value, f"{path}.{key}", stack)

    walk({k: v for k, v in schema.items() if k != "$defs"}, "schema", frozenset())
    if problems:
        raise ValueError("Schema not accepted by structured outputs: " + "; ".join(problems[:10]))
    return schema


def schema_fingerprint(schema: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()[:16]


# Schemas Anthropic rejected in this process: they go straight to the JSON-only path next time.
_json_only_schemas: set[str] = set()

JSON_ONLY_INSTRUCTIONS = """

## Output format

Reply with a single JSON object and nothing else: no prose, no Markdown code fences. It must match
this JSON Schema exactly, including every required property and no others:

{schema}"""

TINY_SCHEMA = {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"], "additionalProperties": False}


def extract_json_object(text: str) -> str:
    """The JSON object in a reply that should be only JSON (tolerates code fences or a stray sentence)."""
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    start, end = stripped.find("{"), stripped.rfind("}")
    return stripped[start:end + 1] if 0 <= start < end else stripped


@dataclass(frozen=True)
class ClaudeCheck:
    status: str  # "verified" or "failed"
    model: str
    checked_at: float
    structured_outputs: str = "not_checked"  # "ok", "failed" or "not_checked"
    code: str | None = None
    message: str | None = None


# ----------------------------------------------------------------------------- client

class AnthropicStructuredClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int,
        timeout: float,
        max_retries: int,
        http_client: Any = None,
        prompt_caching: bool = True,
        expose_details: bool = True,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key, timeout=timeout, max_retries=max_retries, http_client=http_client
        )
        self.model = model
        self.max_tokens = max_tokens
        self.prompt_caching = prompt_caching
        self.expose_details = expose_details

    # ---------------------------------------------------------------- the one request path
    async def _create(self, *, system: str | None, messages: list[dict[str, Any]], max_tokens: int,
                      schema: dict[str, Any] | None = None, cache: bool = False) -> Any:
        params: dict[str, Any] = {"model": self.model, "max_tokens": max_tokens, "messages": messages}
        if system is not None:
            # The system prompt is identical on every call; caching it cuts cost and latency.
            params["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}] if cache else system
        if schema is not None:
            params["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
        try:
            return await self._client.messages.create(**params)
        except anthropic.AnthropicError as exc:
            code, reason = classify(exc)
            http_status = getattr(exc, "status_code", None)
            error_type = _error_type(exc) if isinstance(exc, anthropic.APIStatusError) else None
            request_id = getattr(exc, "request_id", None)
            logger.error("Anthropic request failed: code=%s status=%s type=%s request_id=%s model=%s structured=%s cached=%s message=%s",
                         code, http_status, error_type, request_id, self.model, schema is not None, cache, reason)
            raise ClaudeError(code if code in CLAUDE_ERRORS else "CLAUDE_BAD_REQUEST", reason, http_status=http_status,
                              error_type=error_type, request_id=request_id, expose_details=self.expose_details) from (
                _CacheRejected(reason) if code == "CLAUDE_CACHE" else exc)

    def _reply(self, response: Any, text: str | None = None) -> StructuredReply:
        usage = response.usage
        reply = StructuredReply(
            text=text if text is not None else "".join(b.text for b in response.content if b.type == "text"),
            stop_reason=response.stop_reason,
            model=response.model,
            usage=TokenUsage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_input_tokens=usage.cache_read_input_tokens or 0,
                cache_creation_input_tokens=usage.cache_creation_input_tokens or 0,
            ),
            request_id=getattr(response, "_request_id", None),
        )
        logger.info("Claude %s replied (stop=%s, in=%d, out=%d, cache_read=%d, request=%s)", reply.model, reply.stop_reason,
                    usage.input_tokens, usage.output_tokens, reply.usage.cache_read_input_tokens, reply.request_id)
        return reply

    # ---------------------------------------------------------------- public requests
    async def generate_text(self, prompt: str, *, system: str | None = None, max_tokens: int = 64, cache: bool = False) -> StructuredReply:
        response = await self._create(system=system, messages=[{"role": "user", "content": prompt}], max_tokens=max_tokens, cache=cache)
        return self._reply(response)

    async def structured_once(self, *, system: str | None, messages: list[dict[str, Any]], schema: dict[str, Any],
                              max_tokens: int | None = None, cache: bool = False) -> StructuredReply:
        """One structured-output request with no fallback: a schema problem surfaces as CLAUDE_SCHEMA_ERROR."""
        response = await self._create(system=system, messages=messages, schema=schema, cache=cache,
                                      max_tokens=max_tokens or self.max_tokens)
        return self._reply(response)

    async def generate(self, *, system: str, messages: list[dict[str, Any]], schema: dict[str, Any]) -> StructuredReply:
        """Structured JSON for the agents. Prompt caching is dropped if Anthropic objects to it; the
        JSON-only path is used only if Anthropic rejects the schema itself. Either way the agents
        still validate the reply against their Pydantic models."""
        fingerprint = schema_fingerprint(schema)
        if fingerprint not in _json_only_schemas:
            try:
                return await self.structured_once(system=system, messages=messages, schema=schema, cache=self.prompt_caching)
            except ClaudeError as exc:
                if isinstance(exc.__cause__, _CacheRejected):
                    logger.warning("Anthropic rejected prompt caching (%s); continuing without it.", exc.reason)
                    self.prompt_caching = False
                    return await self.generate(system=system, messages=messages, schema=schema)
                if exc.code != "CLAUDE_SCHEMA_ERROR":
                    raise
                logger.warning("Anthropic rejected the structured-output schema (%s); using JSON-only replies for it.", exc.reason)
                _json_only_schemas.add(fingerprint)
        return await self._generate_json_only(system=system, messages=messages, schema=schema)

    async def _generate_json_only(self, *, system: str, messages: list[dict[str, Any]], schema: dict[str, Any]) -> StructuredReply:
        instructions = system + JSON_ONLY_INSTRUCTIONS.format(schema=json.dumps(schema, separators=(",", ":")))
        response = await self._create(system=instructions, messages=messages, max_tokens=self.max_tokens, cache=self.prompt_caching)
        raw = "".join(b.text for b in response.content if b.type == "text")
        return self._reply(response, text=extract_json_object(raw))

    async def check(self) -> ClaudeCheck:
        """Does Anthropic accept our requests? A tiny text request (key, credit, model, network),
        then a tiny structured request (structured outputs). Costs a fraction of a cent."""
        now = time.time()
        try:
            await self.generate_text("Reply with OK", max_tokens=8)
        except ClaudeError as exc:
            return ClaudeCheck("failed", self.model, now, code=exc.code, message=exc.message)
        try:
            await self.structured_once(system=None, messages=[{"role": "user", "content": "Reply with status OK."}],
                                       schema=TINY_SCHEMA, max_tokens=32)
        except ClaudeError as exc:
            return ClaudeCheck("failed", self.model, now, structured_outputs="failed", code=exc.code, message=exc.message)
        return ClaudeCheck("verified", self.model, now, structured_outputs="ok")


class _CacheRejected(Exception):
    """Marks a ClaudeError caused by Anthropic rejecting cache_control."""
