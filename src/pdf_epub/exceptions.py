import structlog
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = structlog.get_logger(__name__)


class AppError(Exception):
    """HTTP-aware application error."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        code: str = "bad_request",
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.code = code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, resource: str) -> None:
        super().__init__(f"{resource} not found", status_code=404, code="not_found")


class ConflictError(AppError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail, status_code=409, code="conflict")


class UnprocessableError(AppError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail, status_code=422, code="unprocessable")


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    log.warning("app_error", code=exc.code, message=exc.message, path=request.url.path)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "detail": exc.errors(),
            }
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled_exception", path=request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"code": "internal_error", "message": "An unexpected error occurred"}},
    )
