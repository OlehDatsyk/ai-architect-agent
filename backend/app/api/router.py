"""Aggregates all API routers under the /api prefix."""

from fastapi import APIRouter

from app.api.routes import designs, examples, health, projects, specifications

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(specifications.router)
api_router.include_router(examples.router)
api_router.include_router(designs.router)
api_router.include_router(projects.router)
