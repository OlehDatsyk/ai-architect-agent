"""Application error type and handlers producing one consistent JSON error envelope.

Every error response looks like:
    {"error": {"code": "...", "message": "...", "request_id": "..."}}
User-facing messages stay friendly; details go to the server log.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """An expected failure with a stable machine-readable code and a user-safe message."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, object] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def _envelope(request: Request, code: str, message: str, status_code: int, **extra: object) -> JSONResponse:
    body: dict[str, object] = {
        "code": code,
        "message": message,
        "request_id": getattr(request.state, "request_id", None),
    }
    body.update(extra)
    return JSONResponse(status_code=status_code, content={"error": body})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.warning("AppError %s: %s", exc.code, exc.message)
        return _envelope(request, exc.code, exc.message, exc.status_code, **exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "http_error"
        return _envelope(request, code, str(exc.detail), exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"location": ".".join(str(p) for p in err["loc"]), "message": err["msg"]}
            for err in exc.errors()
        ]
        return _envelope(
            request,
            "invalid_request",
            "The request was not valid.",
            422,
            fields=fields,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error")
        return _envelope(
            request,
            "internal_error",
            "Something went wrong on the server. Check the backend log for details.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
