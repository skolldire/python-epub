"""Unit tests that pin the error-sanitization contract of ConvertPdf.

Rules being tested:
  1. Raw infrastructure errors (OSError, MemoryError, etc.) must NOT reach
     job.error — a generic message is substituted instead.
  2. DomainError messages are user-safe and must be preserved verbatim.
  3. A job deleted while conversion is in progress must NOT be re-inserted
     by the finally block (no resurrection).
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pdf_epub.application.use_cases.convert_pdf import ConvertPdf
from pdf_epub.domain.entities import ConversionJob, Document, Page
from pdf_epub.domain.exceptions import BuildError, ExtractionError
from pdf_epub.domain.value_objects import JobStatus


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _run_with_extract_error(exc: Exception) -> ConversionJob:
    """Helper: run conversion where extractor.extract raises `exc`."""
    uc, mocks = _make_use_case()
    mocks["extractor"].get_page_count.return_value = 1
    mocks["extractor"].is_scanned.return_value = False
    mocks["extractor"].extract.side_effect = exc
    uc.execute("j1")
    return mocks["repo"].get.return_value


# ── Rule 1: infrastructure errors produce a generic client message ─────────────

@pytest.mark.parametrize("exc", [
    OSError("/internal/path: permission denied"),
    MemoryError("Cannot allocate 4 GB"),
    RuntimeError("pdfminer internal state corrupted"),
    ValueError("invalid literal from struct.unpack"),
])
def test_infrastructure_error_replaced_with_generic_message(exc):
    job = _run_with_extract_error(exc)
    assert job.status == JobStatus.FAILED
    # Raw exception detail must not reach the client
    assert str(exc) not in (job.error or "")
    # Must be a non-empty generic message
    assert job.error


def test_infrastructure_error_message_is_human_readable():
    job = _run_with_extract_error(OSError("No such file or directory: '/data/secret.pdf'"))
    assert job.status == JobStatus.FAILED
    assert "/data/secret.pdf" not in (job.error or "")
    assert "unexpected error" in (job.error or "").lower() or "please try" in (job.error or "").lower()


# ── Rule 2: DomainError messages are preserved (they are already user-safe) ────

def test_extraction_error_message_preserved():
    job = _run_with_extract_error(ExtractionError("PDF is password-protected"))
    assert job.status == JobStatus.FAILED
    assert "PDF is password-protected" in (job.error or "")


def test_build_error_message_preserved():
    uc, mocks = _make_use_case()
    mocks["extractor"].get_page_count.return_value = 1
    mocks["extractor"].is_scanned.return_value = False
    mocks["extractor"].extract.return_value = Document(
        title="T", author="A", pages=[Page(number=1, blocks=[])]
    )
    mocks["builder"].build.side_effect = BuildError("No content could be extracted")

    uc.execute("j1")

    job = mocks["repo"].get.return_value
    assert job.status == JobStatus.FAILED
    assert "No content could be extracted" in (job.error or "")


def test_page_limit_error_preserved():
    uc, mocks = _make_use_case(max_pages=5)
    mocks["extractor"].get_page_count.return_value = 6
    mocks["extractor"].is_scanned.return_value = False

    uc.execute("j1")

    job = mocks["repo"].get.return_value
    assert job.status == JobStatus.FAILED
    assert "6" in (job.error or "")   # page count in message
    assert "5" in (job.error or "")   # limit in message


# ── Rule 3: deleted job is not resurrected by the finally block ────────────────

def test_deleted_job_not_resurrected():
    """If the job is deleted while conversion runs, the finally block must not
    re-insert it into the repository.

    Note: ConversionJob is a mutable dataclass — all save() call_args point to
    the *same* object, so checking call_args after-the-fact reflects the final
    state. We capture the status *at call time* via a side_effect instead.
    """
    uc, mocks = _make_use_case()
    job = _make_job()

    get_call_count = 0

    def repo_get(job_id: str) -> ConversionJob | None:
        nonlocal get_call_count
        get_call_count += 1
        return job if get_call_count == 1 else None   # None on 2nd call = deleted

    # Capture enum value (immutable) at the moment each save() is called.
    saved_statuses: list[JobStatus] = []

    def capture_save(j: ConversionJob) -> None:
        saved_statuses.append(j.status)

    mocks["repo"].get.side_effect = repo_get
    mocks["repo"].save.side_effect = capture_save
    mocks["extractor"].get_page_count.return_value = 1
    mocks["extractor"].is_scanned.return_value = False
    mocks["extractor"].extract.side_effect = ExtractionError("error during conversion")

    uc.execute("j1")

    assert JobStatus.FAILED not in saved_statuses, (
        f"Deleted job was resurrected — statuses at save time: {saved_statuses}"
    )


def test_normal_job_is_saved_on_completion():
    """Sanity: a non-deleted job IS saved in FAILED state (finally block runs)."""
    uc, mocks = _make_use_case()

    saved_statuses: list[JobStatus] = []

    def capture_save(j: ConversionJob) -> None:
        saved_statuses.append(j.status)

    mocks["repo"].save.side_effect = capture_save
    mocks["extractor"].get_page_count.return_value = 1
    mocks["extractor"].is_scanned.return_value = False
    mocks["extractor"].extract.side_effect = ExtractionError("normal error")

    uc.execute("j1")

    assert saved_statuses.count(JobStatus.FAILED) == 1, (
        f"Expected exactly one FAILED save (from finally), got: {saved_statuses}"
    )
