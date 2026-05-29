from pdf_epub.domain.entities import ConversionJob
from pdf_epub.domain.exceptions import ExtractionError
from pdf_epub.domain.ports import JobRepositoryPort


class GetJobStatus:
    def __init__(self, repo: JobRepositoryPort) -> None:
        self._repo = repo

    def execute(self, job_id: str) -> ConversionJob:
        job = self._repo.get(job_id)
        if job is None:
            raise ExtractionError(f"Job {job_id} not found")
        return job
