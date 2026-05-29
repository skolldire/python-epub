from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pdf_epub.domain.value_objects import BoundingBox, JobStatus


@dataclass
class ContentBlock:
    """Base for any content element extracted from a PDF page."""

    page_number: int
    bbox: BoundingBox


@dataclass
class TextBlock(ContentBlock):
    text: str                    # plain-text content (used as fallback and for search)
    font_size: float             # dominant font size of the block in points
    is_heading: bool = False
    alignment: str = "left"     # "left" | "center" | "right" | "justify"
    inline_html: str = ""       # rich inline HTML preserving bold/italic/sup/sub/size


@dataclass
class TableBlock(ContentBlock):
    """Table extracted from a PDF page. Cells may be None for empty cells."""

    rows: list[list[str | None]]


@dataclass
class ImageBlock(ContentBlock):
    data: bytes
    mime_type: str = "image/png"
    alignment: str = "center"   # "left" | "center" | "right"


@dataclass
class Page:
    number: int
    blocks: list[ContentBlock]
    is_scanned: bool = False


@dataclass
class Document:
    title: str
    author: str
    pages: list[Page]
    language: str = "en"
    cover_image: bytes | None = None   # PNG bytes of the book cover


@dataclass
class ConversionJob:
    id: str
    original_filename: str
    pdf_path: Path
    status: JobStatus = JobStatus.PENDING
    epub_path: Path | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # Optional user-supplied overrides applied during conversion.
    custom_title: str | None = None
    custom_author: str | None = None
    custom_cover: bytes | None = None
    progress_step: str | None = None

    def start(self) -> None:
        self.status = JobStatus.PROCESSING
        self.updated_at = datetime.now(UTC)

    def update_step(self, step: str) -> None:
        self.progress_step = step
        self.updated_at = datetime.now(UTC)

    def complete(self, epub_path: Path) -> None:
        self.status = JobStatus.COMPLETED
        self.epub_path = epub_path
        self.updated_at = datetime.now(UTC)

    def fail(self, error: str) -> None:
        self.status = JobStatus.FAILED
        self.error = error
        self.updated_at = datetime.now(UTC)
