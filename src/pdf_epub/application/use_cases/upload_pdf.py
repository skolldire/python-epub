import uuid

from pdf_epub.domain.entities import ConversionJob
from pdf_epub.domain.exceptions import ExtractionError
from pdf_epub.domain.ports import FileStoragePort, JobRepositoryPort

_ALLOWED_IMAGE_SIGNATURES = (
    b"\xff\xd8",   # JPEG
    b"\x89PNG",    # PNG
)


class UploadPdf:
    def __init__(self, repo: JobRepositoryPort, storage: FileStoragePort, max_bytes: int) -> None:
        self._repo = repo
        self._storage = storage
        self._max_bytes = max_bytes

    def execute(
        self,
        filename: str,
        content: bytes,
        custom_title: str | None = None,
        custom_author: str | None = None,
        custom_cover: bytes | None = None,
    ) -> ConversionJob:
        if not filename.lower().endswith(".pdf"):
            raise ExtractionError("Only PDF files are accepted")

        if not content.startswith(b"%PDF-"):
            raise ExtractionError("Uploaded file is not a valid PDF")

        if len(content) > self._max_bytes:
            raise ExtractionError(
                f"File exceeds the {self._max_bytes // (1024 * 1024)} MB limit"
            )

        if custom_title and len(custom_title) > 500:
            raise ExtractionError("Title must not exceed 500 characters")

        if custom_author and len(custom_author) > 500:
            raise ExtractionError("Author must not exceed 500 characters")

        if custom_cover is not None:
            if not any(custom_cover.startswith(sig) for sig in _ALLOWED_IMAGE_SIGNATURES):
                raise ExtractionError("Cover must be a JPEG or PNG image")

        # Generate the job ID first so the upload path is unique per job,
        # preventing filename collisions between concurrent uploads.
        job_id = str(uuid.uuid4())
        pdf_path = self._storage.save_upload(job_id, filename, content)

        job = ConversionJob(
            id=job_id,
            original_filename=filename,
            pdf_path=pdf_path,
            custom_title=custom_title.strip() if custom_title else None,
            custom_author=custom_author.strip() if custom_author else None,
            custom_cover=custom_cover,
        )
        self._repo.save(job)
        return job
