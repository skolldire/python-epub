"""Unit tests for LocalFileStorage.cleanup()."""
from pathlib import Path

import pytest

from pdf_epub.infrastructure.storage.local_file_storage import LocalFileStorage


def _storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(
        upload_dir=tmp_path / "uploads",
        epub_dir=tmp_path / "epubs",
    )


def test_cleanup_removes_epub(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    epub = tmp_path / "epubs" / "job-1.epub"
    epub.write_bytes(b"fake epub")

    storage.cleanup("job-1")

    assert not epub.exists()


def test_cleanup_removes_uploaded_pdf(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    upload = tmp_path / "uploads" / "job-1_book.pdf"
    upload.write_bytes(b"fake pdf")

    storage.cleanup("job-1")

    assert not upload.exists()


def test_cleanup_removes_all_files_for_job(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    f1 = tmp_path / "uploads" / "job-1_a.pdf"
    f2 = tmp_path / "uploads" / "job-1_b.pdf"
    epub = tmp_path / "epubs" / "job-1.epub"
    f1.write_bytes(b"pdf1")
    f2.write_bytes(b"pdf2")
    epub.write_bytes(b"epub")

    storage.cleanup("job-1")

    assert not f1.exists()
    assert not f2.exists()
    assert not epub.exists()


def test_cleanup_does_not_remove_other_job_files(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    keep = tmp_path / "uploads" / "job-2_book.pdf"
    keep.write_bytes(b"other job")

    storage.cleanup("job-1")

    assert keep.exists()


def test_cleanup_tolerates_missing_files(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    storage.cleanup("nonexistent-job")  # must not raise
