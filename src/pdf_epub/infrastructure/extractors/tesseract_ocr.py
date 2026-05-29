import io

from PIL import Image

from pdf_epub.domain.exceptions import ScannedPdfError
from pdf_epub.domain.ports import OcrPort


class TesseractOcr(OcrPort):
    """Extracts text from images using Tesseract via pytesseract."""

    def extract_text(self, image_bytes: bytes, lang: str = "spa+eng") -> str:
        try:
            import pytesseract

            image = Image.open(io.BytesIO(image_bytes))
            return str(pytesseract.image_to_string(image, lang=lang))
        except Exception as exc:
            raise ScannedPdfError(f"OCR failed: {exc}") from exc
