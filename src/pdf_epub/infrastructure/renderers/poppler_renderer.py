import io
from pathlib import Path

from pdf_epub.domain.exceptions import ExtractionError
from pdf_epub.domain.ports import ImageRendererPort


class PopplerRenderer(ImageRendererPort):
    """Renders PDF pages as PNG images using pdf2image (poppler backend)."""

    def render_page(self, pdf_path: Path, page_number: int, dpi: int = 150) -> bytes:
        try:
            from pdf2image import convert_from_path

            images = convert_from_path(
                str(pdf_path),
                dpi=dpi,
                first_page=page_number,
                last_page=page_number,
            )
        except Exception as exc:
            raise ExtractionError(
                f"Failed to render page {page_number}: {exc}"
            ) from exc

        if not images:
            raise ExtractionError(f"No image returned for page {page_number}")

        buf = io.BytesIO()
        images[0].save(buf, format="PNG")
        return buf.getvalue()
