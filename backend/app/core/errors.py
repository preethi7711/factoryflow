"""One error shape for every failure: {"error": {"code", "message", "details"}}.

Clients (and the offline queue in P8) branch on `code`, never on the message text.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.units import UnitError
from app.core.wac import InsufficientStockError

_HTTP_CODES = {
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
}


class AppError(Exception):
    """An expected failure with a stable code, e.g. AppError(409, "DUPLICATE_CODE", "...")."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.headers = headers


def not_found(what: str, key: object) -> AppError:
    return AppError(404, "NOT_FOUND", f"{what} {key} not found")


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        body = error_body(exc.code, exc.message, exc.details)
        return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(InsufficientStockError)
    async def _insufficient(_: Request, exc: InsufficientStockError) -> JSONResponse:
        details = {
            "requested": str(exc.requested),
            "available": str(exc.available),
            "shortage": str(exc.requested - exc.available),
        }
        return JSONResponse(error_body("INSUFFICIENT_STOCK", str(exc), details), status_code=409)

    @app.exception_handler(UnitError)
    async def _unit(_: Request, exc: UnitError) -> JSONResponse:
        return JSONResponse(error_body("UNIT_ERROR", str(exc)), status_code=422)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = {"errors": jsonable_encoder(exc.errors())}
        body = error_body("VALIDATION_ERROR", "The request is not valid", details)
        return JSONResponse(body, status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, f"HTTP_{exc.status_code}")
        body = error_body(code, str(exc.detail))
        return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)
