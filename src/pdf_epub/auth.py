"""API key authentication dependency.

Authentication is disabled when ``API_KEY`` is not configured — safe for
local development. In production, set ``API_KEY`` to a strong random value
and pass it via ``Authorization: Bearer <key>``.
"""
import hmac

from fastapi import Depends, Request

from pdf_epub.config import Settings, get_settings
from pdf_epub.exceptions import AppError


async def verify_api_key(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    """FastAPI dependency — raises 401 when the request carries an invalid key.

    A missing or empty ``API_KEY`` setting disables auth entirely so that
    local development requires zero configuration.
    """
    if not settings.api_key:
        return

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise AppError(
            "API key required — use 'Authorization: Bearer <key>'",
            status_code=401,
            code="unauthorized",
        )

    token = auth.removeprefix("Bearer ").strip()
    # Constant-time comparison prevents timing-based key enumeration.
    if not hmac.compare_digest(token.encode(), settings.api_key.encode()):
        raise AppError("Invalid API key", status_code=401, code="unauthorized")
