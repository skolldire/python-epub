from pathlib import Path

from pdf_epub.domain.exceptions import ExtractionError, InvalidJobStateError
from pdf_epub.domain.ports import JobRepositoryPort
from pdf_epub.domain.value_objects import JobStatus


class DownloadEpub:
    def __init__(self, repo: JobRepositoryPort) -> None:
        self._repo = repo

    def execute(self, job_id: str) -> Path:
        job = self._repo.get(job_id)
        if job is None:
            raise ExtractionError(f"Job {job_id} not found")

        if job.status != JobStatus.COMPLETED:
            raise InvalidJobStateError(
                f"Job {job_id} is not completed yet (status: {job.status})"
            )

        if job.epub_path is None or not job.epub_path.exists():
            raise ExtractionError(f"EPUB file for job {job_id} is missing")

        return job.epub_path
