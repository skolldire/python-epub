"""Unit tests for the cleanup background task logic.

Covers TTL rules without requiring real filesystem or async runtime.
"""
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from pdf_epub.domain.entities import ConversionJob
from pdf_epub.domain.value_objects import JobStatus
from pdf_epub.infrastructure.cleanup import _run_cleanup


def _make_job(job_id: str, status: JobStatus, age_hours: float) -> ConversionJob:
    job = ConversionJob(
        id=job_id,
        original_filename="book.pdf",
        pdf_path=Path(f"/tmp/{job_id}.pdf"),
    )
    job.status = status
    job.updated_at = datetime.now(UTC) - timedelta(hours=age_hours)
    return job


def _repo_and_storage(jobs: list[ConversionJob]) -> tuple[MagicMock, MagicMock]:
    repo = MagicMock()
    repo.list_all.return_value = jobs
    return repo, MagicMock()


# ── Completed / failed TTL (24 h) ─────────────────────────────────────────────

def test_removes_completed_job_older_than_24h() -> None:
    job = _make_job("j1", JobStatus.COMPLETED, age_hours=25)
    repo, storage = _repo_and_storage([job])

    _run_cleanup(repo, storage)

    storage.cleanup.assert_called_once_with("j1")
    repo.delete.assert_called_once_with("j1")


def test_keeps_completed_job_younger_than_24h() -> None:
    job = _make_job("j1", JobStatus.COMPLETED, age_hours=23)
    repo, storage = _repo_and_storage([job])

    _run_cleanup(repo, storage)

    storage.cleanup.assert_not_called()
    repo.delete.assert_not_called()


def test_removes_failed_job_older_than_24h() -> None:
    job = _make_job("j1", JobStatus.FAILED, age_hours=25)
    repo, storage = _repo_and_storage([job])

    _run_cleanup(repo, storage)

    storage.cleanup.assert_called_once_with("j1")
    repo.delete.assert_called_once_with("j1")


def test_keeps_failed_job_younger_than_24h() -> None:
    job = _make_job("j1", JobStatus.FAILED, age_hours=23)
    repo, storage = _repo_and_storage([job])

    _run_cleanup(repo, storage)

    storage.cleanup.assert_not_called()
    repo.delete.assert_not_called()


# ── Stuck pending / processing TTL (1 h) ─────────────────────────────────────

def test_removes_stuck_pending_job_older_than_1h() -> None:
    job = _make_job("j1", JobStatus.PENDING, age_hours=2)
    repo, storage = _repo_and_storage([job])

    _run_cleanup(repo, storage)

    storage.cleanup.assert_called_once_with("j1")
    repo.delete.assert_called_once_with("j1")


def test_keeps_pending_job_younger_than_1h() -> None:
    job = _make_job("j1", JobStatus.PENDING, age_hours=0)
    repo, storage = _repo_and_storage([job])

    _run_cleanup(repo, storage)

    storage.cleanup.assert_not_called()
    repo.delete.assert_not_called()


def test_removes_stuck_processing_job_older_than_1h() -> None:
    job = _make_job("j1", JobStatus.PROCESSING, age_hours=2)
    repo, storage = _repo_and_storage([job])

    _run_cleanup(repo, storage)

    storage.cleanup.assert_called_once_with("j1")
    repo.delete.assert_called_once_with("j1")


def test_keeps_processing_job_younger_than_1h() -> None:
    job = _make_job("j1", JobStatus.PROCESSING, age_hours=0)
    repo, storage = _repo_and_storage([job])

    _run_cleanup(repo, storage)

    storage.cleanup.assert_not_called()
    repo.delete.assert_not_called()


# ── Multiple jobs ─────────────────────────────────────────────────────────────

def test_selectively_removes_expired_jobs() -> None:
    jobs = [
        _make_job("j1", JobStatus.COMPLETED, age_hours=25),  # expired
        _make_job("j2", JobStatus.COMPLETED, age_hours=10),  # fresh
        _make_job("j3", JobStatus.PENDING, age_hours=2),     # stuck
        _make_job("j4", JobStatus.PROCESSING, age_hours=0),  # active
    ]
    repo, storage = _repo_and_storage(jobs)

    _run_cleanup(repo, storage)

    assert storage.cleanup.call_count == 2
    assert repo.delete.call_count == 2
    storage.cleanup.assert_any_call("j1")
    storage.cleanup.assert_any_call("j3")


def test_empty_repo_does_nothing() -> None:
    repo, storage = _repo_and_storage([])

    _run_cleanup(repo, storage)

    storage.cleanup.assert_not_called()
    repo.delete.assert_not_called()
