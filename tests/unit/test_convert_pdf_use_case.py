"""Unit tests for ConvertPdf.execute() guard cases and custom overrides.

No HTTP, no real filesystem — all ports are mocked.
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pdf_epub.application.use_cases.convert_pdf import ConvertPdf
from pdf_epub.domain.entities import ConversionJob, Document, Page
from pdf_epub.domain.exceptions import ExtractionError, InvalidJobStateError
from pdf_epub.domain.value_objects import JobStatus


def _make_job(**kwargs) -> ConversionJob:
    defaults = dict(
        id="job-1",
        original_filename="book.pdf",
        pdf_path=Path("/tmp/book.pdf"),
    )
    return ConversionJob(**{**defaults, **kwargs})


def _make_uc(
    *,
    repo: MagicMock | None = None,
    storage: MagicMock | None = None,
    extractor: MagicMock | None = None,
    builder: MagicMock | None = None,
    epub_path: Path | None = None,
) -> tuple[ConvertPdf, dict]:
    mocks = {
        "repo":      repo or MagicMock(),
        "storage":   storage or MagicMock(),
        "extractor": extractor or MagicMock(),
        "renderer":  MagicMock(),
        "ocr":       MagicMock(),
        "builder":   builder or MagicMock(),
    }
    if epub_path:
        mocks["storage"].epub_output_path.return_value = epub_path
        mocks["builder"].build.return_value = epub_path

    uc = ConvertPdf(
        repo=mocks["repo"],
        storage=mocks["storage"],
        extractor=mocks["extractor"],
        renderer=mocks["renderer"],
        ocr=mocks["ocr"],
        builder=mocks["builder"],
    )
    return uc, mocks


# ── Guard cases ───────────────────────────────────────────────────────────────

def test_execute_raises_extraction_error_when_job_not_found() -> None:
    uc, mocks = _make_uc()
    mocks["repo"].get.return_value = None

    with pytest.raises(ExtractionError, match="not found"):
        uc.execute("job-1")


def test_execute_raises_invalid_state_when_not_pending() -> None:
    job = _make_job()
    job.start()  # PROCESSING

    uc, mocks = _make_uc()
    mocks["repo"].get.return_value = job

    with pytest.raises(InvalidJobStateError):
        uc.execute("job-1")


# ── Custom overrides ──────────────────────────────────────────────────────────

def _run_with_overrides(tmp_path: Path, **job_kwargs) -> tuple[ConversionJob, Document]:
    """Helper: run a successful (non-OCR) conversion with the given job overrides."""
    epub_file = tmp_path / "output.epub"
    epub_file.write_bytes(b"fake epub")

    document = Document(title="Original Title", author="Original Author", pages=[
        Page(number=1, blocks=[]),
    ])
    job = _make_job(**job_kwargs)

    uc, mocks = _make_uc(epub_path=epub_file)
    mocks["repo"].get.return_value = job
    mocks["extractor"].get_page_count.return_value = 1
    mocks["extractor"].is_scanned.return_value = False
    mocks["extractor"].extract.return_value = document

    uc.execute("job-1")
    return job, document


def test_execute_applies_custom_title(tmp_path: Path) -> None:
    _, document = _run_with_overrides(tmp_path, custom_title="My Custom Title")
    assert document.title == "My Custom Title"


def test_execute_applies_custom_author(tmp_path: Path) -> None:
    _, document = _run_with_overrides(tmp_path, custom_author="Jane Doe")
    assert document.author == "Jane Doe"


def test_execute_applies_custom_cover(tmp_path: Path) -> None:
    cover = b"\xff\xd8" + b"\x00" * 10  # minimal fake JPEG
    _, document = _run_with_overrides(tmp_path, custom_cover=cover)
    assert document.cover_image == cover


def test_execute_does_not_override_title_when_not_set(tmp_path: Path) -> None:
    _, document = _run_with_overrides(tmp_path)
    assert document.title == "Original Title"


# ── OCR path — progress callback branch coverage ─────────────────────────────

def test_execute_ocr_path_covers_milestone_and_non_milestone_pages(tmp_path: Path) -> None:
    """With total_pages=40 and N=2, odd pages skip the callback (false branch)."""
    epub_file = tmp_path / "output.epub"
    epub_file.write_bytes(b"fake epub")

    job = _make_job()
    uc, mocks = _make_uc(epub_path=epub_file)
    mocks["repo"].get.return_value = job
    mocks["extractor"].get_page_count.return_value = 40
    mocks["extractor"].is_scanned.return_value = True
    mocks["renderer"].render_page.return_value = b"\x89PNG\r\n"
    mocks["ocr"].extract_text.return_value = "page text"

    uc.execute("job-1")

    assert job.status == JobStatus.COMPLETED
    assert mocks["renderer"].render_page.call_count == 40
