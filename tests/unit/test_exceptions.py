"""Unit tests for HTTP exception classes and async error handlers."""
from unittest.mock import MagicMock

import pytest
from fastapi import Request
from fastapi.exceptions import RequestValidationError

from pdf_epub.exceptions import (
    ConflictError,
    UnprocessableError,
    app_error_handler,
    unhandled_exception_handler,
    validation_error_handler,
)


def _mock_request() -> MagicMock:
    r = MagicMock(spec=Request)
    r.url.path = "/test"
    return r


# ── ConflictError ─────────────────────────────────────────────────────────────

def test_conflict_error_status_code() -> None:
    err = ConflictError("already exists")
    assert err.status_code == 409


def test_conflict_error_code() -> None:
    err = ConflictError("duplicate")
    assert err.code == "conflict"


def test_conflict_error_message() -> None:
    err = ConflictError("resource conflict")
    assert "resource conflict" in str(err)


# ── validation_error_handler ──────────────────────────────────────────────────

async def test_validation_error_handler_returns_422() -> None:
    exc = RequestValidationError([])
    response = await validation_error_handler(_mock_request(), exc)
    assert response.status_code == 422


async def test_validation_error_handler_body_code() -> None:
    import json

    exc = RequestValidationError([])
    response = await validation_error_handler(_mock_request(), exc)
    body = json.loads(response.body)
    assert body["error"]["code"] == "validation_error"


# ── unhandled_exception_handler ───────────────────────────────────────────────

async def test_unhandled_exception_handler_returns_500() -> None:
    response = await unhandled_exception_handler(_mock_request(), RuntimeError("boom"))
    assert response.status_code == 500


async def test_unhandled_exception_handler_body_code() -> None:
    import json

    response = await unhandled_exception_handler(_mock_request(), ValueError("unexpected"))
    body = json.loads(response.body)
    assert body["error"]["code"] == "internal_error"
