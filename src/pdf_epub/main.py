import asyncio
import pathlib
from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi.errors import RateLimitExceeded

from pdf_epub.config import get_settings
from pdf_epub.dependencies import _file_storage, _job_repo
from pdf_epub.exceptions import (
    AppError,
    app_error_handler,
    unhandled_exception_handler,
    validation_error_handler,
)
from pdf_epub.infrastructure.api.limiter import limiter
from pdf_epub.infrastructure.api.routers import health, jobs, ui
from pdf_epub.infrastructure.cleanup import cleanup_loop
from pdf_epub.log import configure_logging, get_logger
from pdf_epub.middleware import RequestContextMiddleware

log = get_logger(__name__)

_STATIC_DIR = pathlib.Path(__file__).parent / "infrastructure" / "api" / "static"


async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "rate_limit_exceeded",
                "message": "Too many requests — please slow down and try again shortly.",
            }
        },
    )


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
        auth_enabled=bool(settings.api_key),
    )

    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="conv")
    app.state.executor = executor

    cleanup_task = asyncio.create_task(cleanup_loop(_job_repo(), _file_storage()))

    yield

    cleanup_task.cancel()
    with suppress(asyncio.CancelledError):
        await cleanup_task

    # Don't wait for in-flight conversions; stale jobs are cleaned up on next start.
    executor.shutdown(wait=False)

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

    app.state.limiter = limiter

    # Credentials must not be sent to a wildcard origin — the browser enforces
    # this, but we also enforce it server-side for correctness.
    allow_credentials = settings.cors_origins != ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)

    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)      # type: ignore[arg-type]
    app.add_exception_handler(AppError, app_error_handler)                  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    app.include_router(health.router)
    app.include_router(jobs.router)
    app.include_router(ui.router)

    if settings.metrics_enabled:
        Instrumentator(
            should_group_status_codes=True,
            should_ignore_untemplated=True,
            excluded_handlers=["/metrics", "/health", "/static"],
        ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    return app


app = create_app()
