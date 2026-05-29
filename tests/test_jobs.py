import io


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
