"""FastAPI entry point. Each module's router is mounted under /api/v1 here."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  (registers every table before the first request)
from app.auth.router import router as auth_router
from app.billing.router import router as billing_router
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.health import router as health_router
from app.core.spa import SPAStaticFiles
from app.inventory.router import router as stock_router
from app.masters.router import router as masters_router
from app.payments.router import router as payments_router
from app.production.router import router as production_router
from app.purchasing.router import router as purchasing_router
from app.sales.router import router as sales_router

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
    install_error_handlers(app)
    routers = (
        health_router,
        auth_router,
        masters_router,
        stock_router,
        purchasing_router,
        production_router,
        sales_router,
        billing_router,
        payments_router,
    )
    for router in routers:
        app.include_router(router, prefix=API_PREFIX)
    # Mounted last, so every /api route above wins over the static files.
    if settings.static_dir:
        app.mount("/", SPAStaticFiles(directory=settings.static_dir, html=True), name="web")
    return app


app = create_app()
