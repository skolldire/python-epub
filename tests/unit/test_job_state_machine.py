"""Unit tests for ConversionJob state machine and domain invariants.

No infrastructure dependencies.
"""
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pdf_epub.domain.entities import ConversionJob
from pdf_epub.domain.value_objects import JobStatus


def _make_job(**kwargs) -> ConversionJob:
    defaults = dict(
        id="test-id",
        original_filename="book.pdf",
        pdf_path=Path("/fake/book.pdf"),
    )
    return ConversionJob(**{**defaults, **kwargs})


# ── Initial state ──────────────────────────────────────────────────────────────

def test_new_job_is_pending():
    job = _make_job()
    assert job.status == JobStatus.PENDING


def test_new_job_has_no_epub_path():
    job = _make_job()
    assert job.epub_path is None


def test_new_job_has_no_error():
    job = _make_job()
    assert job.error is None


def test_new_job_has_no_progress_step():
    job = _make_job()
    assert job.progress_step is None


# ── start() ───────────────────────────────────────────────────────────────────

def test_start_moves_to_processing():
    job = _make_job()
    job.start()
    assert job.status == JobStatus.PROCESSING


def test_start_updates_updated_at():
    job = _make_job()
    before = job.updated_at
    job.start()
    assert job.updated_at >= before


# ── update_step() ─────────────────────────────────────────────────────────────

def test_update_step_records_step_name():
    job = _make_job()
    job.update_step("extracting")
    assert job.progress_step == "extracting"


def test_update_step_updates_timestamp():
    job = _make_job()
    before = job.updated_at
    job.update_step("building")
    assert job.updated_at >= before


# ── complete() ────────────────────────────────────────────────────────────────

def test_complete_moves_to_completed():
    job = _make_job()
    job.start()
    epub = Path("/fake/output.epub")
    job.complete(epub)
    assert job.status == JobStatus.COMPLETED


def test_complete_sets_epub_path():
    job = _make_job()
    epub = Path("/fake/output.epub")
    job.complete(epub)
    assert job.epub_path == epub


def test_complete_updates_timestamp():
    job = _make_job()
    before = job.updated_at
    job.complete(Path("/fake/out.epub"))
    assert job.updated_at >= before


# ── fail() ────────────────────────────────────────────────────────────────────

def test_fail_moves_to_failed():
    job = _make_job()
    job.start()
    job.fail("tesseract not found")
    assert job.status == JobStatus.FAILED


def test_fail_stores_error_message():
    job = _make_job()
    job.fail("out of memory")
    assert job.error == "out of memory"


def test_fail_updates_timestamp():
    job = _make_job()
    before = job.updated_at
    job.fail("some error")
    assert job.updated_at >= before


# ── Immutability of id / filename ─────────────────────────────────────────────

def test_job_id_stable_across_transitions():
    job = _make_job(id="stable-id")
    job.start()
    job.update_step("building")
    job.complete(Path("/epub"))
    assert job.id == "stable-id"


def test_original_filename_stable_across_transitions():
    job = _make_job(original_filename="my_book.pdf")
    job.start()
    job.fail("error")
    assert job.original_filename == "my_book.pdf"
