from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.error_locale import localize_detail
from app.api.router import api_router
from app.core.db import close_db
from app.core.request_body_limit import RequestBodyLimitMiddleware
from app.repositories.job_repository import ensure_job_indexes


def create_app() -> FastAPI:
    app = FastAPI(
        title="MOVO Document Processing Service",
        version="0.1.0",
        description="Async document preview conversion, parsing, chunking and indexing service for MOVO.",
    )
    app.add_middleware(RequestBodyLimitMiddleware)
    app.include_router(api_router, prefix="/api")

    @app.exception_handler(StarletteHTTPException)
    async def localized_http_error(request: Request, exc: StarletteHTTPException):
        detail = localize_detail(exc.detail, exc.status_code, request.headers.get("accept-language"))
        if detail == exc.detail:
            return await http_exception_handler(request, exc)
        translated = StarletteHTTPException(status_code=exc.status_code, detail=detail, headers=exc.headers)
        return await http_exception_handler(request, translated)

    @app.on_event("startup")
    def startup() -> None:
        ensure_job_indexes()

    @app.on_event("shutdown")
    def shutdown() -> None:
        close_db()

    return app


app = create_app()
