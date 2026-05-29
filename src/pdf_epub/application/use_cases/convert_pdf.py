import time
from collections.abc import Callable
from pathlib import Path

from pdf_epub.domain.entities import Document, ImageBlock, Page, TextBlock
from pdf_epub.domain.exceptions import DomainError, ExtractionError, InvalidJobStateError
from pdf_epub.domain.ports import (
    EpubBuilderPort,
    FileStoragePort,
    ImageRendererPort,
    JobRepositoryPort,
    OcrPort,
    PdfExtractorPort,
)
from pdf_epub.domain.value_objects import BoundingBox, JobStatus
from pdf_epub.log import get_logger

log = get_logger(__name__)


class ConvertPdf:
    def __init__(
        self,
        repo: JobRepositoryPort,
        storage: FileStoragePort,
        extractor: PdfExtractorPort,
        renderer: ImageRendererPort,
        ocr: OcrPort,
        builder: EpubBuilderPort,
        ocr_lang: str = "spa+eng",
        max_pages: int = 1000,
        max_seconds: int = 300,
        default_language: str = "en",
    ) -> None:
        self._repo = repo
        self._storage = storage
        self._extractor = extractor
        self._renderer = renderer
        self._ocr = ocr
        self._builder = builder
        self._ocr_lang = ocr_lang
        self._max_pages = max_pages
        self._max_seconds = max_seconds
        self._default_language = default_language

    def execute(self, job_id: str) -> None:
        job = self._repo.get(job_id)
        if job is None:
            raise ExtractionError(f"Job {job_id} not found")

        if job.status != JobStatus.PENDING:
            raise InvalidJobStateError(
                f"Job {job_id} is {job.status}, expected pending"
            )

        job.start()
        self._repo.save(job)
        log.info("conversion_started", job_id=job_id, filename=job.original_filename)

        # Conversion deadline — enforced before each major step and each OCR page.
        deadline = time.monotonic() + self._max_seconds

        try:
            # ── Step 1: analyze ───────────────────────────────────────────
            job.update_step("analyzing")
            self._repo.save(job)

            page_count = self._extractor.get_page_count(job.pdf_path)
            if page_count > self._max_pages:
                raise ExtractionError(
                    f"PDF has {page_count} pages; the {self._max_pages}-page limit "
                    "protects the service from memory exhaustion"
                )

            if self._extractor.is_scanned(job.pdf_path):
                log.info("scanned_pdf_detected", job_id=job_id, pages=page_count)

                def ocr_progress(step: str) -> None:
                    job.update_step(step)
                    self._repo.save(job)

                # ── Step 2a: OCR ──────────────────────────────────────────
                job.update_step("ocr_0_?")
                self._repo.save(job)
                document = self._extract_with_ocr(
                    job.pdf_path, job.original_filename, page_count, ocr_progress, deadline
                )
            else:
                # ── Step 2b: text extraction ──────────────────────────────
                job.update_step("extracting")
                self._repo.save(job)
                document = self._extractor.extract(job.pdf_path)

            # Apply user-supplied overrides.
            if job.custom_title:
                document.title = job.custom_title
            if job.custom_author:
                document.author = job.custom_author
            if job.custom_cover:
                document.cover_image = job.custom_cover

            # ── Step 3: build EPUB ────────────────────────────────────────
            self._check_deadline(deadline, "EPUB assembly")
            job.update_step("building")
            self._repo.save(job)

            output_path = self._storage.epub_output_path(job_id)
            epub_path = self._builder.build(document, output_path)

            job.complete(epub_path)
            log.info("conversion_completed", job_id=job_id, epub=str(epub_path))

        except (Exception, MemoryError, RecursionError) as exc:
            internal_msg = str(exc) or type(exc).__name__
            log.error("conversion_failed", job_id=job_id, error=internal_msg, exc_info=True)
            # Domain errors already carry user-safe messages; everything else is opaque.
            safe_msg = (
                internal_msg
                if isinstance(exc, DomainError)
                else "An unexpected error occurred — please try again or use a different file"
            )
            job.fail(safe_msg)

        finally:
            # Guard against resurrecting a job that was explicitly deleted
            # while conversion was in progress.
            if self._repo.get(job_id) is not None:
                self._repo.save(job)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _check_deadline(deadline: float, step: str) -> None:
        if time.monotonic() > deadline:
            raise ExtractionError(f"Conversion timed out before: {step}")

    def _extract_with_ocr(
        self,
        pdf_path: Path,
        filename: str,
        total_pages: int,
        progress_cb: Callable[[str], None] | None,
        deadline: float,
    ) -> Document:
        """Renders each page with poppler then runs Tesseract OCR."""
        pages = []
        for page_num in range(1, total_pages + 1):
            self._check_deadline(deadline, f"OCR page {page_num}/{total_pages}")

            if progress_cb and page_num % max(1, total_pages // 20) == 0:
                progress_cb(f"ocr_{page_num}_{total_pages}")

            image_bytes = self._renderer.render_page(pdf_path, page_num)
            text = self._ocr.extract_text(image_bytes, lang=self._ocr_lang)

            block = TextBlock(
                page_number=page_num,
                bbox=BoundingBox(0, 0, 0, 0),
                text=text.strip(),
                font_size=12.0,
            )
            image_block = ImageBlock(
                page_number=page_num,
                bbox=BoundingBox(0, 0, 0, 0),
                data=image_bytes,
            )
            pages.append(Page(number=page_num, blocks=[image_block, block], is_scanned=True))

        title = filename.replace(".pdf", "").replace("_", " ").replace("-", " ").title()
        return Document(title=title, author="", pages=pages, language=self._default_language)
