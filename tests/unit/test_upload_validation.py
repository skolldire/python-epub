"""Unit tests for UploadPdf validation rules.

No HTTP, no filesystem — ports are replaced with minimal fakes.
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pdf_epub.application.use_cases.upload_pdf import UploadPdf
from pdf_epub.domain.exceptions import ExtractionError

_VALID_PDF = b"%PDF-1.4\nminimal content"
_VALID_JPEG = b"\xff\xd8" + b"\x00" * 10
_VALID_PNG  = b"\x89PNG" + b"\x00" * 10
_ONE_MB = 1024 * 1024


def _make_use_case(max_mb: int = 50) -> tuple[UploadPdf, MagicMock, MagicMock]:
    repo    = MagicMock()
    storage = MagicMock()
    storage.save_upload.return_value = Path("/fake/job_id_upload.pdf")
    uc = UploadPdf(repo=repo, storage=storage, max_bytes=max_mb * _ONE_MB)
    return uc, repo, storage


# ── Happy path ────────────────────────────────────────────────────────────────

def test_valid_pdf_creates_job():
    uc, repo, storage = _make_use_case()
    job = uc.execute(filename="book.pdf", content=_VALID_PDF)
    assert job.original_filename == "book.pdf"
    repo.save.assert_called_once_with(job)
    storage.save_upload.assert_called_once()


def test_job_id_prefixes_storage_call():
    uc, _, storage = _make_use_case()
    job = uc.execute(filename="book.pdf", content=_VALID_PDF)
    call_args = storage.save_upload.call_args
    assert call_args.args[0] == job.id        # job_id is first positional arg
    assert call_args.args[1] == "book.pdf"    # filename is second


def test_optional_metadata_stored():
    uc, _, _ = _make_use_case()
    job = uc.execute("book.pdf", _VALID_PDF, custom_title="My Book", custom_author="  Alice  ")
    assert job.custom_title == "My Book"
    assert job.custom_author == "Alice"        # stripped


def test_valid_jpeg_cover_accepted():
    uc, _, _ = _make_use_case()
    uc.execute("book.pdf", _VALID_PDF, custom_cover=_VALID_JPEG)


def test_valid_png_cover_accepted():
    uc, _, _ = _make_use_case()
    uc.execute("book.pdf", _VALID_PDF, custom_cover=_VALID_PNG)


# ── Rejection cases ───────────────────────────────────────────────────────────

def test_rejects_non_pdf_extension():
    uc, _, _ = _make_use_case()
    with pytest.raises(ExtractionError, match="Only PDF"):
        uc.execute("document.txt", _VALID_PDF)


def test_rejects_fake_pdf_magic_bytes():
    uc, _, _ = _make_use_case()
    with pytest.raises(ExtractionError, match="not a valid PDF"):
        uc.execute("evil.pdf", b"PK\x03\x04fake zip content")


def test_rejects_oversized_file():
    uc, _, _ = _make_use_case(max_mb=1)
    oversized = _VALID_PDF + b"x" * (2 * _ONE_MB)
    with pytest.raises(ExtractionError, match="exceeds"):
        uc.execute("big.pdf", oversized)


def test_rejects_title_over_500_chars():
    uc, _, _ = _make_use_case()
    with pytest.raises(ExtractionError, match="Title"):
        uc.execute("book.pdf", _VALID_PDF, custom_title="A" * 501)


def test_rejects_author_over_500_chars():
    uc, _, _ = _make_use_case()
    with pytest.raises(ExtractionError, match="Author"):
        uc.execute("book.pdf", _VALID_PDF, custom_author="B" * 501)


def test_rejects_cover_with_invalid_magic_bytes():
    uc, _, _ = _make_use_case()
    with pytest.raises(ExtractionError, match="JPEG or PNG"):
        uc.execute("book.pdf", _VALID_PDF, custom_cover=b"GIF87a...")
