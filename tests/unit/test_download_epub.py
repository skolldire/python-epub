"""Unit tests for DownloadEpub use case.

No infrastructure dependencies — uses mock repository only.
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pdf_epub.application.use_cases.download_epub import DownloadEpub
from pdf_epub.domain.entities import ConversionJob
from pdf_epub.domain.exceptions import ExtractionError, InvalidJobStateError
from pdf_epub.domain.value_objects import JobStatus


def _make_job(**kwargs) -> ConversionJob:
    defaults = dict(
        id="job-1",
        original_filename="book.pdf",
        pdf_path=Path("/tmp/book.pdf"),
    )
    return ConversionJob(**{**defaults, **kwargs})


def _repo_with(job: ConversionJob | None) -> MagicMock:
    repo = MagicMock()
    repo.get.return_value = job
    return repo


# ── Happy path ────────────────────────────────────────────────────────────────

def test_returns_epub_path_when_completed(tmp_path: Path) -> None:
    epub = tmp_path / "book.epub"
    epub.write_bytes(b"fake epub content")

    job = _make_job()
    job.complete(epub)

    result = DownloadEpub(_repo_with(job)).execute("job-1")

    assert result == epub


# ── Not found ─────────────────────────────────────────────────────────────────

def test_raises_extraction_error_when_job_not_found() -> None:
    with pytest.raises(ExtractionError, match="not found"):
        DownloadEpub(_repo_with(None)).execute("job-1")


# ── Wrong state ───────────────────────────────────────────────────────────────

def test_raises_invalid_state_when_pending() -> None:
    job = _make_job()
    assert job.status == JobStatus.PENDING

    with pytest.raises(InvalidJobStateError):
        DownloadEpub(_repo_with(job)).execute("job-1")


def test_raises_invalid_state_when_processing() -> None:
    job = _make_job()
    job.start()

    with pytest.raises(InvalidJobStateError):
        DownloadEpub(_repo_with(job)).execute("job-1")


def test_raises_invalid_state_when_failed() -> None:
    job = _make_job()
    job.fail("extraction error")

    with pytest.raises(InvalidJobStateError):
        DownloadEpub(_repo_with(job)).execute("job-1")


# ── File missing ──────────────────────────────────────────────────────────────

def test_raises_extraction_error_when_epub_file_missing(tmp_path: Path) -> None:
    epub = tmp_path / "missing.epub"
    # epub does not exist on disk

    job = _make_job()
    job.complete(epub)

    with pytest.raises(ExtractionError, match="missing"):
        DownloadEpub(_repo_with(job)).execute("job-1")
