"""Integration tests for UI HTML routes."""
import io


def _make_pdf_bytes() -> bytes:
    return (
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        b"xref\n0 1\n0000000000 65535 f \n"
        b"trailer\n<< /Size 1 /Root 1 0 R >>\nstartxref\n9\n%%EOF"
    )


def test_index_returns_200(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_job_page_returns_200_for_existing_job(client) -> None:
    pdf = io.BytesIO(_make_pdf_bytes())
    create_resp = client.post(
        "/api/v1/jobs", files={"file": ("test.pdf", pdf, "application/pdf")}
    )
    job_id = create_resp.json()["id"]

    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_job_page_returns_404_for_nonexistent_job(client) -> None:
    response = client.get("/jobs/nonexistent-id")
    assert response.status_code == 404
