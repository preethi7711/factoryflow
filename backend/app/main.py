"""FastAPI entry point. Each module's router is mounted under /api/v1 here."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.health import router as health_router

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="FactoryFlow", version="0.1.0")
    # Only matters in local dev (Vite on :5173). In production one URL serves both, so no CORS.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix=API_PREFIX)
    return app


app = create_app()
