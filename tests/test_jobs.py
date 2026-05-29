import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from pdf_epub.dependencies import get_job_repo, get_storage
from pdf_epub.domain.entities import ConversionJob
from pdf_epub.domain.value_objects import JobStatus
from pdf_epub.infrastructure.persistence.in_memory_job_repo import InMemoryJobRepository
from pdf_epub.infrastructure.storage.local_file_storage import LocalFileStorage
from pdf_epub.main import create_app


def _make_pdf_bytes() -> bytes:
    """Minimal valid PDF bytes for upload validation tests."""
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nxref\n0 1\n0000000000 65535 f \ntrailer\n<< /Size 1 /Root 1 0 R >>\nstartxref\n9\n%%EOF"


def test_create_job_returns_201(client):
    pdf = io.BytesIO(_make_pdf_bytes())
    response = client.post("/api/v1/jobs", files={"file": ("test.pdf", pdf, "application/pdf")})
    assert response.status_code == 201
    body = response.json()
    assert "id" in body
    assert body["status"] in ("pending", "processing", "completed", "failed")
    assert body["original_filename"] == "test.pdf"


def test_get_job_returns_200(client):
    pdf = io.BytesIO(_make_pdf_bytes())
    create_resp = client.post("/api/v1/jobs", files={"file": ("test.pdf", pdf, "application/pdf")})
    job_id = create_resp.json()["id"]

    response = client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["id"] == job_id


def test_get_nonexistent_job_returns_404(client):
    response = client.get("/api/v1/jobs/does-not-exist")
    assert response.status_code == 404


def test_upload_non_pdf_returns_422(client):
    txt = io.BytesIO(b"not a pdf")
    response = client.post("/api/v1/jobs", files={"file": ("doc.txt", txt, "text/plain")})
    assert response.status_code == 422


def test_delete_job(client):
    pdf = io.BytesIO(_make_pdf_bytes())
    create_resp = client.post("/api/v1/jobs", files={"file": ("test.pdf", pdf, "application/pdf")})
    job_id = create_resp.json()["id"]

    del_resp = client.delete(f"/api/v1/jobs/{job_id}")
    assert del_resp.status_code == 204

    get_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert get_resp.status_code == 404


def test_download_epub_not_ready_returns_409(client):
    pdf = io.BytesIO(_make_pdf_bytes())
    create_resp = client.post("/api/v1/jobs", files={"file": ("test.pdf", pdf, "application/pdf")})
    job_id = create_resp.json()["id"]

    # Immediately attempt download — job may still be pending/processing
    status = client.get(f"/api/v1/jobs/{job_id}").json()["status"]
    if status in ("pending", "processing"):
        response = client.get(f"/api/v1/jobs/{job_id}/epub")
        assert response.status_code == 409


def test_download_epub_nonexistent_job_returns_404(client):
    response = client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000/epub")
    assert response.status_code == 404


def test_download_epub_invalid_uuid_returns_404(client):
    response = client.get("/api/v1/jobs/not-a-uuid/epub")
    assert response.status_code == 404


def test_delete_nonexistent_job_returns_404(client):
    response = client.delete("/api/v1/jobs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_delete_invalid_uuid_returns_404(client):
    response = client.delete("/api/v1/jobs/not-a-uuid")
    assert response.status_code == 404


def test_get_job_invalid_uuid_returns_404(client):
    response = client.get("/api/v1/jobs/not-a-uuid")
    assert response.status_code == 404


# ── Peek endpoint ─────────────────────────────────────────────────────────────

def test_peek_valid_pdf_returns_metadata(client):
    pdf = io.BytesIO(_make_pdf_bytes())
    response = client.post("/api/v1/jobs/peek", files={"file": ("doc.pdf", pdf, "application/pdf")})
    assert response.status_code == 200
    body = response.json()
    assert "title" in body
    assert "author" in body
    assert "page_count" in body
    assert isinstance(body["page_count"], int)


def test_peek_non_pdf_returns_zeroed_metadata(client):
    response = client.post(
        "/api/v1/jobs/peek",
        files={"file": ("doc.txt", io.BytesIO(b"plain text"), "text/plain")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["page_count"] == 0
    assert body["title"] == ""
    assert body["author"] == ""


# ── List endpoint ─────────────────────────────────────────────────────────────

def test_list_jobs_returns_empty_list_initially(client):
    response = client.get("/api/v1/jobs")
    assert response.status_code == 200
    assert response.json() == []


def test_list_jobs_includes_created_job(client):
    pdf = io.BytesIO(_make_pdf_bytes())
    create_resp = client.post("/api/v1/jobs", files={"file": ("test.pdf", pdf, "application/pdf")})
    job_id = create_resp.json()["id"]

    list_resp = client.get("/api/v1/jobs")
    assert list_resp.status_code == 200
    ids = [j["id"] for j in list_resp.json()]
    assert job_id in ids


def test_list_jobs_excludes_deleted_job(client):
    pdf = io.BytesIO(_make_pdf_bytes())
    create_resp = client.post("/api/v1/jobs", files={"file": ("test.pdf", pdf, "application/pdf")})
    job_id = create_resp.json()["id"]

    client.delete(f"/api/v1/jobs/{job_id}")

    list_resp = client.get("/api/v1/jobs")
    ids = [j["id"] for j in list_resp.json()]
    assert job_id not in ids


# ── Download completed job ────────────────────────────────────────────────────

# ── Cover image upload ────────────────────────────────────────────────────────

def test_create_job_with_cover_image(client) -> None:
    pdf = io.BytesIO(_make_pdf_bytes())
    cover = io.BytesIO(b"\xff\xd8" + b"\x00" * 20)  # minimal fake JPEG

    response = client.post(
        "/api/v1/jobs",
        files={
            "file": ("test.pdf", pdf, "application/pdf"),
            "cover": ("cover.jpg", cover, "image/jpeg"),
        },
    )
    assert response.status_code == 201


# ── Deterministic 409 from download ──────────────────────────────────────────

def test_download_epub_pending_job_returns_409_with_code(client) -> None:
    repo = client.app.dependency_overrides[get_job_repo]()
    job = ConversionJob(
        id="00000000-0000-0000-0000-000000000003",
        original_filename="pending.pdf",
        pdf_path=Path("/tmp/pending.pdf"),
    )
    repo.save(job)

    response = client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000003/epub")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_ready"


# ── Peek exception path ───────────────────────────────────────────────────────

def test_peek_pdfplumber_exception_returns_zeroed_metadata(client) -> None:
    from unittest.mock import patch

    with patch("pdfplumber.open", side_effect=RuntimeError("corrupted")):
        response = client.post(
            "/api/v1/jobs/peek",
            files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4\nfake"), "application/pdf")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["page_count"] == 0
    assert body["title"] == ""


# ── Rate limit handler ────────────────────────────────────────────────────────

async def test_rate_limit_handler_returns_429() -> None:
    import json
    from unittest.mock import MagicMock

    from fastapi import Request

    from pdf_epub.main import _rate_limit_handler

    request = MagicMock(spec=Request)
    response = await _rate_limit_handler(request, Exception("rate limit"))
    assert response.status_code == 429
    body = json.loads(response.body)
    assert body["error"]["code"] == "rate_limit_exceeded"


# ── Pagination ────────────────────────────────────────────────────────────────

def test_list_jobs_respects_limit(client) -> None:
    for i in range(5):
        pdf = io.BytesIO(_make_pdf_bytes())
        client.post("/api/v1/jobs", files={"file": (f"book{i}.pdf", pdf, "application/pdf")})

    response = client.get("/api/v1/jobs?limit=2")
    assert response.status_code == 200
    assert len(response.json()) <= 2


def test_list_jobs_respects_offset(client) -> None:
    for i in range(3):
        pdf = io.BytesIO(_make_pdf_bytes())
        client.post("/api/v1/jobs", files={"file": (f"book{i}.pdf", pdf, "application/pdf")})

    all_ids = [j["id"] for j in client.get("/api/v1/jobs").json()]
    offset_ids = [j["id"] for j in client.get("/api/v1/jobs?offset=1").json()]
    assert offset_ids == all_ids[1:]


# ── Error handlers via HTTP ───────────────────────────────────────────────────

def test_missing_file_field_triggers_validation_error_handler(client) -> None:
    response = client.post("/api/v1/jobs")  # required `file` field absent
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_broken_dependency_returns_500(tmp_dirs) -> None:
    upload_dir, epub_dir = tmp_dirs
    storage = LocalFileStorage(upload_dir=upload_dir, epub_dir=epub_dir)

    app = create_app()
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_job_repo] = lambda: (_ for _ in ()).throw(RuntimeError("db down"))

    with TestClient(app, raise_server_exceptions=False) as c:
        response = c.get("/api/v1/jobs")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"


def test_download_epub_completed_job_returns_file(client, tmp_dirs):
    from pdf_epub.dependencies import get_job_repo

    epub_dir = tmp_dirs[1]
    epub_file = epub_dir / "book.epub"
    epub_file.write_bytes(b"PK fake epub")

    # Inject a completed job directly into the repo
    repo = client.app.dependency_overrides[get_job_repo]()
    job = ConversionJob(
        id="00000000-0000-0000-0000-000000000001",
        original_filename="mybook.pdf",
        pdf_path=Path("/tmp/mybook.pdf"),
        status=JobStatus.COMPLETED,
        epub_path=epub_file,
    )
    repo.save(job)

    response = client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000001/epub")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/epub+zip"
