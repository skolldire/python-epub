"""Unit tests for ConvertPdf safety limits (max_pages, deadline).

No HTTP, no real filesystem — all ports are mocked.
"""
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pdf_epub.application.use_cases.convert_pdf import ConvertPdf
from pdf_epub.domain.entities import ConversionJob, Document, Page
from pdf_epub.domain.exceptions import ExtractionError
from pdf_epub.domain.value_objects import JobStatus


def _make_job(job_id: str = "j1") -> ConversionJob:
    return ConversionJob(
        id=job_id,
        original_filename="book.pdf",
        pdf_path=Path("/fake/book.pdf"),
    )


def _make_use_case(max_pages: int = 100, max_seconds: int = 300) -> tuple[ConvertPdf, dict]:
    mocks = {
        "repo":      MagicMock(),
        "storage":   MagicMock(),
        "extractor": MagicMock(),
        "renderer":  MagicMock(),
        "ocr":       MagicMock(),
        "builder":   MagicMock(),
    }
    job = _make_job()
    mocks["repo"].get.return_value = job
    mocks["storage"].epub_output_path.return_value = Path("/fake/out.epub")

    uc = ConvertPdf(
        repo=mocks["repo"],
        storage=mocks["storage"],
        extractor=mocks["extractor"],
        renderer=mocks["renderer"],
        ocr=mocks["ocr"],
        builder=mocks["builder"],
        max_pages=max_pages,
        max_seconds=max_seconds,
    )
    return uc, mocks


# ── Page limit ────────────────────────────────────────────────────────────────

def test_exceeding_max_pages_fails_job():
    uc, mocks = _make_use_case(max_pages=10)
    mocks["extractor"].get_page_count.return_value = 11
    mocks["extractor"].is_scanned.return_value = False

    uc.execute("j1")

    job = mocks["repo"].get.return_value
    assert job.status == JobStatus.FAILED
    assert "11" in job.error
    assert "10" in job.error


def test_exactly_at_max_pages_succeeds():
    uc, mocks = _make_use_case(max_pages=5)
    mocks["extractor"].get_page_count.return_value = 5
    mocks["extractor"].is_scanned.return_value = False
    mocks["extractor"].extract.return_value = Document(
        title="T", author="A", pages=[Page(number=1, blocks=[])]
    )
    mocks["builder"].build.return_value = Path("/fake/out.epub")

    uc.execute("j1")

    job = mocks["repo"].get.return_value
    assert job.status == JobStatus.COMPLETED


# ── Deadline timeout ──────────────────────────────────────────────────────────

def test_expired_deadline_before_build_fails_job():
    uc, mocks = _make_use_case(max_seconds=300)
    mocks["extractor"].get_page_count.return_value = 1
    mocks["extractor"].is_scanned.return_value = False
    mocks["extractor"].extract.return_value = Document(
        title="T", author="A", pages=[Page(number=1, blocks=[])]
    )

    # execute() call pattern (non-OCR path):
    #   call 1 → deadline = base + 300
    #   call 2 → _check_deadline before build  (we make this expire)
    base = time.monotonic()
    with patch("pdf_epub.application.use_cases.convert_pdf.time.monotonic",
               side_effect=[base, base + 9999]):
        uc.execute("j1")

    job = mocks["repo"].get.return_value
    assert job.status == JobStatus.FAILED
    assert "timed out" in job.error.lower()


def test_ocr_deadline_per_page_fails_job():
    uc, mocks = _make_use_case(max_seconds=300)
    mocks["extractor"].get_page_count.return_value = 3
    mocks["extractor"].is_scanned.return_value = True
    mocks["renderer"].render_page.return_value = b"\x89PNG\r\n"
    mocks["ocr"].extract_text.return_value = "text"

    # execute() call pattern (OCR path, 3 pages):
    #   call 1 → deadline = base + 300
    #   call 2 → _check_deadline page 1   (passes)
    #   call 3 → _check_deadline page 2   (expires)
    base = time.monotonic()
    with patch("pdf_epub.application.use_cases.convert_pdf.time.monotonic",
               side_effect=[base, base, base + 9999]):
        uc.execute("j1")

    job = mocks["repo"].get.return_value
    assert job.status == JobStatus.FAILED
    assert "timed out" in job.error.lower()
