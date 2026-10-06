"""FastAPI application factory and ASGI entry point.

Run with:  uvicorn app.main:app --reload   (from the backend/ directory)
"""

import logging

import anthropic
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import register_middleware

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    logging.getLogger(__name__).info(
        "Anthropic model: %s (SDK %s, API key %s, prompt caching %s)", settings.anthropic_model, anthropic.__version__,
        "configured" if settings.anthropic_configured else "not set", "on" if settings.anthropic_prompt_caching else "off")

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Natural language to structured architectural specification to procedural 3D building.",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    # Expose the active settings so dependency overrides in tests stay consistent.
    app.dependency_overrides[get_settings] = lambda: settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    register_middleware(app, settings.max_request_bytes)
    register_error_handlers(app)
    app.include_router(api_router)

    logger.info(
        "%s v%s started (env=%s, anthropic_configured=%s)",
        settings.app_name, __version__, settings.app_env, settings.anthropic_configured,
    )
    return app


app = create_app()
