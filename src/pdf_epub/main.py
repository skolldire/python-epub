from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from pdf_epub.config import get_settings
from pdf_epub.exceptions import (
    AppError,
    app_error_handler,
    unhandled_exception_handler,
    validation_error_handler,
)
from pdf_epub.infrastructure.api.routers import health, jobs, ui
from pdf_epub.log import configure_logging, get_logger
from pdf_epub.middleware import RequestContextMiddleware

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    configure_logging(level=settings.log_level, json=settings.is_production)

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.epub_dir.mkdir(parents=True, exist_ok=True)

    log.info(
        "service_starting",
        environment=settings.environment,
        version=settings.app_version,
    )
    yield
    log.info("service_stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)

    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(health.router)
    app.include_router(jobs.router)
    app.include_router(ui.router)

    return app


app = create_app()
