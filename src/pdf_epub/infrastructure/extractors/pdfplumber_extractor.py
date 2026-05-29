import io
import logging
import re
import unicodedata
from pathlib import Path

import pdfplumber

# Suppress noisy pdfminer font-descriptor warnings that don't affect extraction.
logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pdfplumber").setLevel(logging.ERROR)

from pdf_epub.domain.entities import (
    ContentBlock,
    Document,
    ImageBlock,
    Page,
    TableBlock,
    TextBlock,
)
from pdf_epub.domain.exceptions import ExtractionError
from pdf_epub.domain.ports import PdfExtractorPort
from pdf_epub.domain.value_objects import BoundingBox
from pdf_epub.log import get_logger
from pdf_epub.utils import escape_html as _escape

log = get_logger(__name__)

# ── Scan detection ──────────────────────────────────────────────────────────
_SCAN_SAMPLE_PAGES = 3
_SCAN_CHAR_THRESHOLD = 50

# ── Image extraction guard ───────────────────────────────────────────────────
# Pages with more images than this threshold (e.g. vector-heavy cover pages
# exported from Notes / Keynote) contain thousands of tiny graphic elements.
# Cropping each one individually would hang; skip image extraction for such pages.
_MAX_IMAGES_PER_PAGE = 50

# ── Heading detection ───────────────────────────────────────────────────────
# A line is a heading when its font size exceeds median × this factor.
_HEADING_SIZE_FACTOR = 1.2

# ── Paragraph merging ───────────────────────────────────────────────────────
# Gap between consecutive lines larger than font_size × this → paragraph break.
_PARAGRAPH_GAP_FACTOR = 1.4
# Short tokens that end with a period but are NOT sentence ends.
_ABBREVIATION_RE = re.compile(
    r"\b("
    r"Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|Ave|Blvd|Dept|Est|"
    r"vs|etc|e\.g|i\.e|approx|fig|vol|no|pp|ca|cf|"
    r"[A-Z]"           # single capital initial: A. B. C. …
    r")\.$",
    re.IGNORECASE,
)

# ── CID garbage ─────────────────────────────────────────────────────────────
_CID_PATTERN = re.compile(r"\(cid:\d+\)")

# ── Unicode normalization ────────────────────────────────────────────────────
# Private Use Area ligatures found in professional fonts (MinionPro, etc.).
# Mapped by inspecting surrounding context in real PDFs.
_PUA_LIGATURES: dict[str, str] = {
    "": "fi",   "": "fl",  "": "ff",
    "": "ffi",  "": "ffl",
    "": "fi",   "": "fl",
    "": "Th",   # uppercase Th  (MinionPro / ChaparralPro)
    "": "fi",   "": "fl",
    "": "ft",   # ft ligature variant 1
    "": "th",   # lowercase th  (MinionPro)
    "": "ff",   "": "fi",  "": "fl",
    "": "ft",   # ft ligature variant 2
}
# All Unicode Private Use Area (U+E000–U+F8FF).
_PUA_RE = re.compile(r"[-]")

# Patterns after a null byte that indicate an "fl" ligature rather than "fi".
# The fi/fl distinction is resolved by the characters that follow the glyph.
_FL_AFTER_RE = re.compile(r"^(?:ag|aw|air|ee|ew|ig|ipp|oat|oc|oo|ow|y(?:[^a-z]|$)|ying|ies|akes|ames)")


def _resolve_null_ligature(text: str) -> str:
    """Replaces \\x00 (null byte) with the most likely ligature for context.

    Many professional fonts (MinionPro, ChaparralPro) emit U+0000 for glyphs
    that have no ToUnicode entry. In English text this is almost always the
    'fi' or 'fl' OpenType ligature. Context after the null byte determines
    which replacement to apply; 'fi' is the default.
    """
    if "\x00" not in text:
        return text
    parts: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "\x00":
            following = text[i + 1 : i + 5]
            parts.append("fl" if _FL_AFTER_RE.match(following) else "fi")
        else:
            parts.append(text[i])
        i += 1
    return "".join(parts)


def _normalize_text(text: str) -> str:
    """Normalizes extracted PDF text for clean EPUB output.

    Steps applied in order:
    1. Resolve null-byte ligatures (\\x00) — used by fonts like MinionPro for
       fi/fl glyphs without a ToUnicode mapping; determined by context.
    2. NFKC Unicode normalization — decomposes standard Alphabetic Presentation
       Forms ligatures (U+FB00-U+FB06: ff fi fl ffi ffl st → plain ASCII).
    3. Known PUA ligature substitution — replaces codepoints from the Unicode
       Private Use Area emitted by professional fonts.
    4. Strip any remaining PUA characters that could not be mapped.
    5. Remove Unicode replacement characters (U+FFFD) left by lxml or pdfminer.
    """
    text = _resolve_null_ligature(text)
    text = unicodedata.normalize("NFKC", text)
    for pua_char, replacement in _PUA_LIGATURES.items():
        if pua_char in text:
            text = text.replace(pua_char, replacement)
    if _PUA_RE.search(text):
        text = _PUA_RE.sub("", text)
    if "�" in text:
        text = text.replace("�", "")
    return text


# ── Rich text formatting ─────────────────────────────────────────────────────
_BOLD_RE = re.compile(r"bold|black|heavy|demi|bd(?=[^a-z]|$)|bk(?=[^a-z]|$)", re.I)
_ITALIC_RE = re.compile(r"italic|oblique|slanted|(?<![a-z])it(?![a-z])", re.I)
# A word is sub/superscript when its size is smaller than this ratio of the line size.
_SUB_SUPER_SIZE_RATIO = 0.80
# Fraction of line height by which the word must be shifted vertically.
_VERTICAL_SHIFT_RATIO = 0.20

# ── Alignment detection ─────────────────────────────────────────────────────
# How close the text center must be to the page center (fraction of page width).
_CENTER_TOLERANCE = 0.07
# Minimum indent (fraction of available text width) to consider as intentional.
_INDENT_THRESHOLD = 0.12


def _is_sentence_end(text: str) -> bool:
    """Returns True when text ends with genuine sentence-closing punctuation.

    Avoids false positives on common abbreviations (Mrs., Dr., etc.) and
    on numeric list items (1., 42.) that end with a period.
    """
    stripped = text.rstrip()
    if not stripped:
        return False
    last = stripped[-1]
    if last in "?!":
        return True
    if last == ":":
        # Colons often introduce a list or quote — treat as paragraph end.
        return True
    if last == ".":
        words = stripped.split()
        last_word = words[-1] if words else ""
        # Numeric item: "1." "42."
        if re.match(r"^\d+\.$", last_word):
            return False
        # Known abbreviation pattern
        if _ABBREVIATION_RE.search(stripped):
            return False
        return True
    return False


def _is_cid_garbage(text: str) -> bool:
    """Returns True when most characters are undecodable CID glyph references."""
    cid_count = len(_CID_PATTERN.findall(text))
    if cid_count == 0:
        return False
    clean = _CID_PATTERN.sub("", text)
    total = cid_count + len(clean.replace(" ", ""))
    return cid_count / max(total, 1) > 0.3


class PdfPlumberExtractor(PdfExtractorPort):

    def get_page_count(self, pdf_path: Path) -> int:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                return len(pdf.pages)
        except Exception as exc:
            log.warning("pdf_page_count_failed", error=str(exc), path=str(pdf_path))
            raise ExtractionError(
                "The PDF could not be opened — it may be corrupted or password-protected"
            ) from exc

    def is_scanned(self, pdf_path: Path) -> bool:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                total = len(pdf.pages)
                if not total:
                    return True

                # Sample first 10 pages + 3 pages from the document's midpoint.
                # Many PDFs have blank/image-only cover pages at the start; relying
                # solely on the first few pages misclassifies those as scanned.
                indices = list(range(min(10, total)))
                if total > 20:
                    mid = total // 2
                    indices += list(range(mid, min(mid + 3, total)))

                char_counts = [
                    len(_CID_PATTERN.sub("", pdf.pages[i].extract_text() or ""))
                    for i in indices
                ]
                # If ANY sampled page has substantial readable text, it's not scanned.
                return max(char_counts, default=0) < _SCAN_CHAR_THRESHOLD
        except Exception as exc:
            log.warning("pdf_scan_check_failed", error=str(exc), path=str(pdf_path))
            raise ExtractionError(
                "The PDF could not be read — it may be corrupted or password-protected"
            ) from exc

    def extract(self, pdf_path: Path) -> Document:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                all_sizes = self._collect_font_sizes(pdf)
                heading_threshold = self._heading_threshold(all_sizes)
                median_size = self._median_size(all_sizes)

                meta_title = (pdf.metadata or {}).get("Title") or ""
                title = (
                    meta_title.strip()
                    or self._extract_title_from_first_page(pdf)
                    or pdf_path.stem.replace("_", " ").replace("-", " ")
                )
                author = (pdf.metadata or {}).get("Author") or ""

                cover_image, cover_page_idx = self._extract_cover(pdf, pdf_path)

                pages = [
                    self._extract_page(page, heading_threshold, median_size)
                    for i, page in enumerate(pdf.pages)
                    if i != cover_page_idx  # skip the dedicated cover page
                ]
        except ExtractionError:
            raise
        except Exception as exc:
            log.warning("pdf_extraction_failed", error=str(exc), path=str(pdf_path))
            raise ExtractionError(
                "Text extraction failed — the PDF structure may be unsupported or the file is damaged"
            ) from exc

        return Document(
            title=str(title),
            author=str(author),
            pages=pages,
            cover_image=cover_image,
        )

    # ── Private helpers ──────────────────────────────────────────────────────

    def _collect_font_sizes(self, pdf: pdfplumber.PDF) -> list[float]:
        sizes: list[float] = []
        for page in pdf.pages:
            for w in page.extract_words(extra_attrs=["size"]) or []:
                if w.get("size"):
                    sizes.append(float(w["size"]))
        return sizes

    def _median_size(self, sizes: list[float]) -> float:
        if not sizes:
            return 12.0
        s = sorted(sizes)
        return s[len(s) // 2]

    def _heading_threshold(self, sizes: list[float]) -> float:
        return self._median_size(sizes) * _HEADING_SIZE_FACTOR

    def _extract_title_from_first_page(self, pdf: pdfplumber.PDF) -> str | None:
        """Infers the book title from the largest readable text on the first page.

        Falls back to None when no clean text can be found (e.g. fully scanned page).
        """
        if not pdf.pages:
            return None
        words = pdf.pages[0].extract_words(extra_attrs=["size"]) or []
        readable = [w for w in words if not _CID_PATTERN.search(str(w.get("text", "")))]
        if not readable:
            return None
        max_size = max(float(w.get("size", 0)) for w in readable)
        title_words = [
            w["text"]
            for w in readable
            if float(w.get("size", 0)) >= max_size * 0.90
        ]
        title = " ".join(title_words).strip()
        return title or None

    def _extract_cover(
        self, pdf: pdfplumber.PDF, pdf_path: Path
    ) -> tuple[bytes | None, int | None]:
        """Detects and extracts the book cover image from the first few pages.

        Returns (image_bytes, page_index_to_skip).
        - Full-page cover (≥40% page area, <100 readable chars): rendered at high
          resolution via poppler and the page is excluded from chapter extraction.
        - Prominent image on page 1 (≥10% coverage, page has text): extracted as
          the cover but the page is NOT skipped so content is preserved.
        - No suitable image: returns (None, None).
        """
        for page_idx in range(min(3, len(pdf.pages))):
            page = pdf.pages[page_idx]
            text = _CID_PATTERN.sub("", page.extract_text() or "").strip()
            imgs = page.images or []
            if not imgs:
                continue

            # Vector-heavy pages (e.g. Notes exports) have thousands of tiny elements.
            # Fall back to a full-page poppler render rather than trying to find a
            # single "largest" image among thousands of graphic primitives.
            if len(imgs) > _MAX_IMAGES_PER_PAGE and len(text) < 100:
                cover_bytes = self._render_page_jpeg(pdf_path, page_idx + 1, dpi=150)
                if cover_bytes:
                    log.info("cover_extracted_vector", page=page_idx + 1,
                             image_count=len(imgs), size_kb=len(cover_bytes) // 1024)
                    return cover_bytes, page_idx
                continue

            pw, ph = float(page.width), float(page.height)
            largest = max(imgs, key=lambda img: (img["x1"] - img["x0"]) * (img["bottom"] - img["top"]))
            iw = largest["x1"] - largest["x0"]
            ih = largest["bottom"] - largest["top"]
            coverage = (iw * ih) / (pw * ph)

            if coverage >= 0.40 and len(text) < 100:
                # Full-page cover: render via poppler, save as JPEG for compact size.
                cover_bytes = self._render_page_jpeg(pdf_path, page_idx + 1, dpi=150)
                if cover_bytes:
                    log.info("cover_extracted", page=page_idx + 1, coverage=f"{coverage:.0%}",
                             size_kb=len(cover_bytes) // 1024)
                    return cover_bytes, page_idx

            elif page_idx == 0 and coverage >= 0.10:
                # Partial cover on page 1: crop the image region.
                try:
                    bbox = (largest["x0"], largest["top"], largest["x1"], largest["bottom"])
                    pil_img = page.within_bbox(bbox).to_image(resolution=150).original
                    buf = io.BytesIO()
                    pil_img.convert("RGB").save(buf, format="JPEG", quality=90, optimize=True)
                    log.info("cover_extracted_partial", page=1, coverage=f"{coverage:.0%}",
                             size_kb=len(buf.getvalue()) // 1024)
                    return buf.getvalue(), None  # keep page in content
                except Exception:
                    log.debug("partial_cover_extraction_failed", page=1, exc_info=True)

        return None, None

    @staticmethod
    def _render_page_jpeg(pdf_path: Path, page_number: int, dpi: int = 150) -> bytes | None:
        """Renders a single PDF page as JPEG bytes using poppler (pdf2image).

        JPEG is used for covers because it compresses photographic/illustrative
        content far more efficiently than PNG (typically 5-10× smaller).
        """
        try:
            from pdf2image import convert_from_path
            images = convert_from_path(str(pdf_path), dpi=dpi,
                                       first_page=page_number, last_page=page_number)
            if images:
                buf = io.BytesIO()
                images[0].convert("RGB").save(buf, format="JPEG", quality=90, optimize=True)
                return buf.getvalue()
        except Exception:
            log.debug("page_render_failed", page=page_number, path=str(pdf_path), exc_info=True)
        return None

    def _extract_page(
        self,
        page: pdfplumber.page.Page,
        heading_threshold: float,
        median_size: float,
    ) -> Page:
        """Extracts all content blocks from a page sorted by vertical position.

        Items are collected with their y0 coordinate and sorted before being
        returned, so images, text, and tables appear in reading order rather
        than by type.
        """
        page_width = float(page.width)
        page_height = float(page.height)
        # Items: (y0, ContentBlock)
        items: list[tuple[float, ContentBlock]] = []

        # -- Images --
        # Pages with more than _MAX_IMAGES_PER_PAGE entries are typically
        # vector-heavy exports (Notes, Keynote) whose tiny graphic elements
        # would take hours to crop individually. Skip image extraction for
        # such pages; their text content is still extracted normally.
        page_imgs = page.images or []
        if len(page_imgs) <= _MAX_IMAGES_PER_PAGE:
            for img in page_imgs:
                try:
                    bbox = BoundingBox(
                        x0=float(img["x0"]),
                        y0=float(img["top"]),
                        x1=float(img["x1"]),
                        y1=float(img["bottom"]),
                    )
                    cropped = page.within_bbox((bbox.x0, bbox.y0, bbox.x1, bbox.y1))
                    buf = io.BytesIO()
                    cropped.to_image(resolution=150).original.save(buf, format="PNG")
                    img_align = self._detect_image_alignment(bbox.x0, bbox.x1, page_width)
                    block = ImageBlock(
                        page_number=page.page_number,
                        bbox=bbox,
                        data=buf.getvalue(),
                        alignment=img_align,
                    )
                    items.append((bbox.y0, block))
                except Exception:
                    log.debug("image_block_extraction_failed", page=page.page_number, exc_info=True)
        else:
            log.debug(
                "image_extraction_skipped",
                page=page.page_number,
                image_count=len(page_imgs),
                reason="exceeds _MAX_IMAGES_PER_PAGE",
            )

        # -- Tables (use y=0 as fallback since pdfplumber doesn't expose table bbox reliably) --
        for table in page.extract_tables() or []:
            if not table:
                continue
            rows: list[list[str | None]] = [[cell for cell in row] for row in table]
            bbox = BoundingBox(0, 0, page_width, page_height)
            items.append((0.0, TableBlock(page_number=page.page_number, bbox=bbox, rows=rows)))

        # -- Text --
        words = page.extract_words(
            extra_attrs=["size", "fontname", "top", "bottom"]
        ) or []
        left_margin, right_margin = self._compute_margins(words, page_width)
        lines = self._group_words_into_lines(words)
        paragraphs = self._merge_lines_into_paragraphs(lines, heading_threshold)

        for para_text, font_size, para_bbox, para_words in paragraphs:
            if _is_cid_garbage(para_text):
                log.debug("cid_garbage_skipped", page=page.page_number, snippet=para_text[:40])
                continue
            clean_text = _CID_PATTERN.sub("", para_text).strip()
            if not clean_text:
                continue

            is_heading = font_size >= heading_threshold
            alignment = self._detect_alignment(
                para_bbox[0], para_bbox[2], page_width, left_margin, right_margin, is_heading
            )
            inline_html = self._build_inline_html(
                para_words, font_size, median_size, skip_size=is_heading
            )
            items.append((
                para_bbox[1],  # y0 of the paragraph
                TextBlock(
                    page_number=page.page_number,
                    bbox=BoundingBox(*para_bbox),
                    text=clean_text,
                    font_size=font_size,
                    is_heading=is_heading,
                    alignment=alignment,
                    inline_html=inline_html,
                ),
            ))

        # Sort everything by vertical position so reading order is preserved.
        items.sort(key=lambda x: x[0])
        return Page(number=page.page_number, blocks=[b for _, b in items])

    # ── Word grouping ────────────────────────────────────────────────────────

    def _group_words_into_lines(
        self, words: list[dict]
    ) -> list[tuple[str, float, tuple[float, float, float, float], list[dict]]]:
        """Groups words by vertical proximity into raw text lines.

        Returns (text, font_size, bbox, word_list) per line.
        """
        if not words:
            return []

        lines: list[tuple[str, float, tuple[float, float, float, float], list[dict]]] = []
        current: list[dict] = [words[0]]

        for word in words[1:]:
            if abs(float(word.get("top", 0)) - float(current[-1].get("top", 0))) <= 3:
                current.append(word)
            else:
                lines.append(self._line_from_words(current))
                current = [word]
        lines.append(self._line_from_words(current))
        return lines

    def _line_from_words(
        self, words: list[dict]
    ) -> tuple[str, float, tuple[float, float, float, float], list[dict]]:
        # Normalize each word's text before joining (ligatures, PUA chars).
        text = " ".join(_normalize_text(str(w.get("text", ""))) for w in words)
        sizes = [float(w["size"]) for w in words if w.get("size")]
        font_size = max(sizes) if sizes else 12.0
        x0 = min(float(w.get("x0", 0)) for w in words)
        y0 = min(float(w.get("top", 0)) for w in words)
        x1 = max(float(w.get("x1", 0)) for w in words)
        y1 = max(float(w.get("bottom", 0)) for w in words)
        return text, font_size, (x0, y0, x1, y1), words

    # ── Paragraph merging ────────────────────────────────────────────────────

    def _merge_lines_into_paragraphs(
        self,
        lines: list[tuple[str, float, tuple[float, float, float, float], list[dict]]],
        heading_threshold: float,
    ) -> list[tuple[str, float, tuple[float, float, float, float], list[dict]]]:
        """Merges consecutive lines into paragraph blocks based on punctuation and spacing."""
        if not lines:
            return []

        paragraphs = []
        acc_text, acc_size, acc_bbox, acc_words = lines[0]

        for i in range(1, len(lines)):
            curr_text, curr_size, curr_bbox, curr_words = lines[i]
            _, prev_size, prev_bbox, _ = lines[i - 1]

            gap = curr_bbox[1] - prev_bbox[3]
            large_gap = gap > prev_size * _PARAGRAPH_GAP_FACTOR
            size_shift = abs(curr_size - acc_size) > acc_size * 0.12
            terminal = _is_sentence_end(acc_text)

            # Drop-cap detection: a single alphanumeric character at a larger
            # font size is a typographic drop cap — the first letter of the
            # paragraph rendered oversized. It must be joined directly to the
            # next line (no space) and the body-text size adopted so the merged
            # block is NOT mis-classified as a heading.
            stripped = acc_text.strip()
            is_drop_cap = (
                len(stripped) == 1
                and stripped.isalnum()
                and size_shift
                and not large_gap
                and not terminal
            )

            if is_drop_cap:
                # Join without space: "I" + "n the summer" → "In the summer"
                acc_text = acc_text.rstrip() + curr_text.lstrip()
                acc_size = curr_size   # body text size, not drop-cap size
                acc_bbox = (
                    min(acc_bbox[0], curr_bbox[0]),
                    acc_bbox[1],
                    max(acc_bbox[2], curr_bbox[2]),
                    curr_bbox[3],
                )
                acc_words = acc_words + curr_words
            elif terminal or large_gap or size_shift:
                paragraphs.append((acc_text, acc_size, acc_bbox, acc_words))
                acc_text, acc_size, acc_bbox, acc_words = curr_text, curr_size, curr_bbox, curr_words
            else:
                # Join with or without space (handle hyphenation).
                if acc_text.rstrip().endswith("-"):
                    acc_text = acc_text.rstrip()[:-1] + curr_text.lstrip()
                else:
                    acc_text = acc_text.rstrip() + " " + curr_text.lstrip()
                acc_bbox = (
                    min(acc_bbox[0], curr_bbox[0]),
                    acc_bbox[1],
                    max(acc_bbox[2], curr_bbox[2]),
                    curr_bbox[3],
                )
                acc_words = acc_words + curr_words

        paragraphs.append((acc_text, acc_size, acc_bbox, acc_words))
        return paragraphs

    # ── Alignment detection ──────────────────────────────────────────────────

    def _compute_margins(self, words: list[dict], page_width: float) -> tuple[float, float]:
        """Returns (left_margin, right_margin) in points based on the page's word positions."""
        if not words:
            return 36.0, 36.0
        left = min(float(w.get("x0", page_width)) for w in words)
        right = page_width - max(float(w.get("x1", 0)) for w in words)
        return left, max(right, 0.0)

    def _detect_alignment(
        self,
        x0: float,
        x1: float,
        page_width: float,
        left_margin: float,
        right_margin: float,
        is_heading: bool,
    ) -> str:
        available = page_width - left_margin - right_margin
        if available <= 0:
            return "left"

        text_center = (x0 + x1) / 2
        page_center = page_width / 2
        left_indent = x0 - left_margin
        right_indent = (page_width - right_margin) - x1

        # Centered: text center is close to page center AND has symmetric indentation.
        if (
            abs(text_center - page_center) < page_width * _CENTER_TOLERANCE
            and left_indent > available * _INDENT_THRESHOLD
        ):
            return "center"

        # Right-aligned: large left indent with small right indent.
        if (
            left_indent > available * _INDENT_THRESHOLD
            and right_indent < available * _INDENT_THRESHOLD
            and left_indent > right_indent * 2
        ):
            return "right"

        return "left"

    def _detect_image_alignment(
        self, x0: float, x1: float, page_width: float
    ) -> str:
        """Returns the visual alignment of an image based on its horizontal position.

        Uses page center as the reference; no dependency on text margins since
        images may span different widths than body text.
        """
        img_center = (x0 + x1) / 2
        page_center = page_width / 2
        img_width = x1 - x0

        # Centered: image center within ±10% of page width from page center.
        if abs(img_center - page_center) < page_width * 0.10:
            return "center"
        # Right: image sits in the right half and its right edge is close to the right margin.
        if img_center > page_center and (page_width - x1) < page_width * 0.15:
            return "right"
        return "left"

    # ── Rich inline HTML ─────────────────────────────────────────────────────

    def _build_inline_html(
        self,
        words: list[dict],
        line_size: float,
        median_size: float,
        skip_size: bool = False,
    ) -> str:
        """Builds inline HTML for a paragraph preserving bold, italic, sup, sub, and font size.

        When skip_size=True (headings), font-size spans are omitted because the
        heading tag (h1/h2/h3) already encodes the size through CSS.
        """
        if not words:
            return ""

        # Compute line baseline metrics for sub/superscript detection.
        tops = [float(w.get("top", 0)) for w in words if w.get("size")]
        bottoms = [float(w.get("bottom", 0)) for w in words if w.get("size")]
        if not tops:
            return _escape(" ".join(str(w.get("text", "")) for w in words))

        line_top = min(tops)
        line_bottom = max(bottoms)
        line_height = max(line_bottom - line_top, 1.0)

        # Group consecutive words with identical formatting to reduce tag noise.
        # Each entry: (text, fmt_key, x0, x1) — positions drive spacing decisions below.
        groups: list[tuple[str, str, float, float]] = []

        for word in words:
            raw = _normalize_text(str(word.get("text", "")))
            if not raw:
                continue
            fontname = str(word.get("fontname") or "")
            size = float(word.get("size") or line_size)
            top = float(word.get("top") or line_top)
            bottom = float(word.get("bottom") or line_bottom)
            wx0 = float(word.get("x0") or 0.0)
            wx1 = float(word.get("x1") or wx0)

            is_bold = bool(_BOLD_RE.search(fontname))
            is_italic = bool(_ITALIC_RE.search(fontname))

            # Superscript: smaller AND shifted upward.
            is_super = (
                size < line_size * _SUB_SUPER_SIZE_RATIO
                and top < line_top + line_height * (0.5 - _VERTICAL_SHIFT_RATIO)
            )
            # Subscript: smaller AND shifted downward.
            is_sub = (
                size < line_size * _SUB_SUPER_SIZE_RATIO
                and bottom > line_bottom - line_height * (0.5 - _VERTICAL_SHIFT_RATIO)
                and not is_super
            )

            # Relative font size — only emit for body text, not headings (skip_size=True),
            # and only when the size differs from the document median by > 5%.
            size_em: str | None = None
            if not is_super and not is_sub and not skip_size:
                ratio = size / median_size
                if abs(ratio - 1.0) > 0.05:
                    size_em = f"{ratio:.2f}em"

            fmt_key = f"{is_bold},{is_italic},{is_super},{is_sub},{size_em}"
            groups.append((_escape(raw), fmt_key, wx0, wx1))

        # Merge consecutive words with the same format into single tokens.
        # x0 tracks the left edge of the group; x1 tracks the rightmost edge.
        merged: list[tuple[str, str, float, float]] = []
        for text, fmt, wx0, wx1 in groups:
            if merged and merged[-1][1] == fmt:
                pt, pf, px0, _ = merged[-1]
                merged[-1] = (pt + " " + text, pf, px0, wx1)
            else:
                merged.append((text, fmt, wx0, wx1))

        # Render each group to HTML.
        parts: list[str] = []
        for text, fmt, _gx0, _gx1 in merged:
            bold_s, italic_s, super_s, sub_s, size_em_s = fmt.split(",")
            is_bold = bold_s == "True"
            is_italic = italic_s == "True"
            is_super = super_s == "True"
            is_sub = sub_s == "True"
            size_em = None if size_em_s == "None" else size_em_s

            span = text
            if is_super:
                span = f"<sup>{span}</sup>"
            elif is_sub:
                span = f"<sub>{span}</sub>"
            if size_em:
                span = f'<span style="font-size:{size_em}">{span}</span>'
            if is_bold and is_italic:
                span = f"<strong><em>{span}</em></strong>"
            elif is_bold:
                span = f"<strong>{span}</strong>"
            elif is_italic:
                span = f"<em>{span}</em>"
            parts.append(span)

        if not parts:
            return ""

        # Join groups using a space only when there is an actual visual gap between
        # them (> 1 pt).  This fixes drop-cap merging: the single large letter "T"
        # and the following "he…" share the same x-boundary, so they are joined
        # directly ("The…") instead of producing "T he…" which epub readers render
        # with the oversized letter on its own visual line.
        result = parts[0]
        for i in range(1, len(parts)):
            _, _, curr_x0, _ = merged[i]
            _, _, _, prev_x1 = merged[i - 1]
            separator = " " if curr_x0 - prev_x1 > 1.0 else ""
            result += separator + parts[i]
        return result
