from abc import ABC, abstractmethod
from pathlib import Path

from pdf_epub.domain.entities import ConversionJob, Document


class PdfExtractorPort(ABC):
    """Extracts structured content from a text-based PDF."""

    @abstractmethod
    def is_scanned(self, pdf_path: Path) -> bool:
        """Returns True when the PDF has no machine-readable text (scanned)."""

    @abstractmethod
    def extract(self, pdf_path: Path) -> Document:
        """Returns a fully structured Document from the given PDF."""


class ImageRendererPort(ABC):
    """Renders individual PDF pages as raster images."""

    @abstractmethod
    def render_page(self, pdf_path: Path, page_number: int, dpi: int = 150) -> bytes:
        """Returns PNG bytes for the given 1-based page number."""


class OcrPort(ABC):
    """Runs optical character recognition on a page image."""

    @abstractmethod
    def extract_text(self, image_bytes: bytes, lang: str = "spa+eng") -> str:
        """Returns the recognized text from the image."""


class EpubBuilderPort(ABC):
    """Assembles an EPUB file from a structured Document."""

    @abstractmethod
    def build(self, document: Document, output_path: Path) -> Path:
        """Writes the EPUB to output_path and returns that path."""


class JobRepositoryPort(ABC):
    """Persists ConversionJob instances."""

    @abstractmethod
    def save(self, job: ConversionJob) -> None: ...

    @abstractmethod
    def get(self, job_id: str) -> ConversionJob | None: ...

    @abstractmethod
    def list_all(self) -> list[ConversionJob]: ...

    @abstractmethod
    def delete(self, job_id: str) -> None: ...


class FileStoragePort(ABC):
    """Manages uploaded PDFs and generated EPUB files on disk."""

    @abstractmethod
    def save_upload(self, filename: str, content: bytes) -> Path:
        """Persists the uploaded PDF bytes and returns its path."""

    @abstractmethod
    def epub_output_path(self, job_id: str) -> Path:
        """Returns the expected output path for a job's EPUB."""

    @abstractmethod
    def cleanup(self, job_id: str) -> None:
        """Removes all files associated with the given job."""
