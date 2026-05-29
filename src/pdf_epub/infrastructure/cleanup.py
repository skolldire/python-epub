import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from pdf_epub.domain.ports import FileStoragePort, JobRepositoryPort
from pdf_epub.domain.value_objects import JobStatus
from pdf_epub.log import get_logger

log = get_logger(__name__)

_COMPLETED_TTL_HOURS = 24
_STUCK_TTL_HOURS = 1
_INTERVAL_SECONDS = 3600


async def cleanup_loop(repo: JobRepositoryPort, storage: FileStoragePort) -> None:
    """Hourly background task that removes stale jobs and their files.

    - completed / failed jobs older than 24 h → deleted
    - pending / processing jobs older than 1 h (crashed mid-run) → deleted
    """
    while True:
        await asyncio.sleep(_INTERVAL_SECONDS)
        with suppress(Exception):
            _run_cleanup(repo, storage)


def _run_cleanup(repo: JobRepositoryPort, storage: FileStoragePort) -> None:
    now = datetime.now(UTC)
    completed_cutoff = now - timedelta(hours=_COMPLETED_TTL_HOURS)
    stuck_cutoff = now - timedelta(hours=_STUCK_TTL_HOURS)

    removed = 0
    for job in repo.list_all():
        terminal = job.status in (JobStatus.COMPLETED, JobStatus.FAILED)
        stuck = job.status in (JobStatus.PENDING, JobStatus.PROCESSING)

        if (terminal and job.updated_at < completed_cutoff) or (
            stuck and job.updated_at < stuck_cutoff
        ):
            storage.cleanup(job.id)
            repo.delete(job.id)
            removed += 1

    if removed:
        log.info("cleanup_completed", removed=removed)
