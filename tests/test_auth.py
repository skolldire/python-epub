"""Integration tests for API key authentication.

Tests cover: no auth configured (pass-through), valid key, invalid key,
missing header, and malformed header.
"""
import io

import pytest
from fastapi.testclient import TestClient

from pdf_epub.config import Settings, get_settings
from pdf_epub.dependencies import get_job_repo, get_storage
from pdf_epub.infrastructure.persistence.in_memory_job_repo import InMemoryJobRepository
from pdf_epub.infrastructure.storage.local_file_storage import LocalFileStorage
from pdf_epub.main import create_app

_SECRET = "test-secret-key-abc123"
_VALID_PDF = (
    b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    b"xref\n0 1\n0000000000 65535 f \n"
    b"trailer\n<< /Size 1 /Root 1 0 R >>\nstartxref\n9\n%%EOF"
)


@pytest.fixture()
def authed_client(tmp_path):
    upload_dir = tmp_path / "uploads"
    epub_dir   = tmp_path / "epubs"
    repo    = InMemoryJobRepository()
    storage = LocalFileStorage(upload_dir=upload_dir, epub_dir=epub_dir)

    app = create_app()
    app.dependency_overrides[get_job_repo] = lambda: repo
    app.dependency_overrides[get_storage]  = lambda: storage
    app.dependency_overrides[get_settings] = lambda: Settings(
        api_key=_SECRET,
        upload_dir=upload_dir,
        epub_dir=epub_dir,
    )

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _pdf_upload():
    return {"file": ("book.pdf", io.BytesIO(_VALID_PDF), "application/pdf")}


# ── Auth disabled (no API_KEY set) ────────────────────────────────────────────

def test_no_auth_configured_allows_request(client):
    """When API_KEY is not set requests pass through without a header."""
    resp = client.post("/api/v1/jobs", files=_pdf_upload())
    assert resp.status_code == 201


# ── Auth enabled ──────────────────────────────────────────────────────────────

def test_valid_key_allows_request(authed_client):
    resp = authed_client.post(
        "/api/v1/jobs",
        headers={"Authorization": f"Bearer {_SECRET}"},
        files=_pdf_upload(),
    )
    assert resp.status_code == 201


def test_missing_auth_header_returns_401(authed_client):
    resp = authed_client.post("/api/v1/jobs", files=_pdf_upload())
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"] == "unauthorized"


def test_wrong_key_returns_401(authed_client):
    resp = authed_client.post(
        "/api/v1/jobs",
        headers={"Authorization": "Bearer completely-wrong-key"},
        files=_pdf_upload(),
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_malformed_header_returns_401(authed_client):
    """Header present but not 'Bearer <token>' format."""
    resp = authed_client.post(
        "/api/v1/jobs",
        headers={"Authorization": _SECRET},   # missing "Bearer " prefix
        files=_pdf_upload(),
    )
    assert resp.status_code == 401


def test_get_job_status_also_requires_key(authed_client):
    """Auth applies to all /api/v1/jobs/* endpoints."""
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    resp = authed_client.get(f"/api/v1/jobs/{fake_uuid}")
    assert resp.status_code == 401


def test_response_body_does_not_leak_key(authed_client):
    """Error response must not echo the expected key or any secret."""
    resp = authed_client.post(
        "/api/v1/jobs",
        headers={"Authorization": "Bearer wrong"},
        files=_pdf_upload(),
    )
    assert _SECRET not in resp.text
