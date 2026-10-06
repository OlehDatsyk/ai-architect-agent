"""Request ID and access-log middleware."""

import json
import logging
import time
import uuid

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        # Accept a client-supplied ID only if it is short and safe to log.
        request_id = incoming if incoming.isalnum() and len(incoming) <= 64 else uuid.uuid4().hex
        request.state.request_id = request_id

        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000

        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "%s %s -> %d (%.1f ms) [%s]",
            request.method, request.url.path, response.status_code, elapsed_ms, request_id,
        )
        return response


class _BodyTooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    """Rejects request bodies above max_bytes with 413, whether or not Content-Length is sent."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None:
            try:
                too_large = int(declared) > self.max_bytes
            except ValueError:
                await self._reject(scope, send, 400, "invalid_request", "The Content-Length header is not a number.")
                return
            if too_large:
                await self._reject(scope, send, 413, "request_too_large", self._too_large_message())
                return

        received = 0
        exceeded = False
        responded = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    exceeded = True
                    raise _BodyTooLarge
            return message

        async def guarded_send(message: Message) -> None:
            # Frameworks may catch the exception above and answer with their own error
            # (FastAPI returns a generic 400). Replace that response with a clear 413.
            nonlocal responded
            if exceeded:
                if not responded:
                    responded = True
                    await self._reject(scope, send, 413, "request_too_large", self._too_large_message())
                return
            responded = responded or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _BodyTooLarge:
            pass
        if exceeded and not responded:
            await self._reject(scope, send, 413, "request_too_large", self._too_large_message())

    def _too_large_message(self) -> str:
        return f"The request body is larger than the {self.max_bytes // 1024} KB limit."

    async def _reject(self, scope: Scope, send: Send, status: int, code: str, message: str) -> None:
        request_id = scope.get("state", {}).get("request_id")
        body = json.dumps({"error": {"code": code, "message": message, "request_id": request_id}}).encode()
        headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
        if request_id:
            headers.append((REQUEST_ID_HEADER.lower().encode(), request_id.encode()))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})


def register_middleware(app: FastAPI, max_request_bytes: int) -> None:
    # Added first so it runs inside RequestContextMiddleware and can reuse its request ID.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=max_request_bytes)
    app.add_middleware(RequestContextMiddleware)
