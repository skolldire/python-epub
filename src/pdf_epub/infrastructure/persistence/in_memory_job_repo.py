import threading

from pdf_epub.domain.entities import ConversionJob
from pdf_epub.domain.ports import JobRepositoryPort


class InMemoryJobRepository(JobRepositoryPort):
    """Thread-safe in-memory store for ConversionJob instances.

    BackgroundTasks run in a threadpool, so a lock is required.
    """

    def __init__(self) -> None:
        self._store: dict[str, ConversionJob] = {}
        self._lock = threading.Lock()

    def save(self, job: ConversionJob) -> None:
        with self._lock:
            self._store[job.id] = job

    def get(self, job_id: str) -> ConversionJob | None:
        with self._lock:
            return self._store.get(job_id)

    def list_all(self) -> list[ConversionJob]:
        with self._lock:
            return list(self._store.values())

    def delete(self, job_id: str) -> None:
        with self._lock:
            self._store.pop(job_id, None)
