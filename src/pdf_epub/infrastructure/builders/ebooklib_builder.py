import uuid
from pathlib import Path

from ebooklib import epub

from pdf_epub.domain.entities import (
    Document,
    ImageBlock,
    TableBlock,
    TextBlock,
)
from pdf_epub.domain.exceptions import BuildError
from pdf_epub.domain.ports import EpubBuilderPort
from pdf_epub.log import get_logger
from pdf_epub.utils import escape_html as _escape

log = get_logger(__name__)

_CSS = """
body  { font-family: Georgia, serif; line-height: 1.6; margin: 2em; }
h1    { font-size: 1.8em; margin-top: 1.5em; }
h2    { font-size: 1.4em; margin-top: 1.2em; }
h3    { font-size: 1.15em; margin-top: 1em; }
p     { margin: 0.6em 0; }
p.left    { text-align: left; }
p.center  { text-align: center; }
p.right   { text-align: right; }
p.justify { text-align: justify; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
th, td { border: 1px solid #ccc; padding: 6px 10px; text-align: left; }
th    { background-color: #f0f0f0; }
figure              { margin: 1.2em 0; }
figure.center       { text-align: center; }
figure.left         { text-align: left; }
figure.right        { text-align: right; }
figure img          { max-width: 90%; height: auto; display: inline-block; }
figcaption          { font-size: 0.85em; color: #555; margin-top: 0.4em; }
sup { vertical-align: super; font-size: 0.75em; }
sub { vertical-align: sub;   font-size: 0.75em; }
"""

# Font-size tiers for heading-level detection (relative to median).
# Only headings above _HEADING_SIZE_FACTOR (already in extractor) enter here.
_H1_FACTOR = 1.6
_H2_FACTOR = 1.3
_H3_FACTOR = 1.1


class EbooklibBuilder(EpubBuilderPort):

    def build(self, document: Document, output_path: Path) -> Path:
        try:
            book = epub.EpubBook()
            book.set_identifier(str(uuid.uuid4()))
            book.set_title(document.title)
            book.set_language(document.language)
            if document.author:
                book.add_author(document.author)

            style = epub.EpubItem(
                uid="style",
                file_name="style/main.css",
                media_type="text/css",
                content=_CSS,
            )
            book.add_item(style)

            chapters: list[epub.EpubHtml] = []
            toc_entries: list[epub.Link] = []
            image_counter = 0
            median_size = self._document_median_size(document)

            # -- Cover --
            cover_chapter = self._build_cover(book, document, style)

            for page in document.pages:
                html_parts: list[str] = []

                for block in page.blocks:
                    if isinstance(block, ImageBlock):
                        image_counter += 1
                        img_name = f"images/img_{image_counter}.png"
                        book.add_item(epub.EpubImage(
                            uid=f"img_{image_counter}",
                            file_name=img_name,
                            media_type="image/png",
                            content=block.data,
                        ))
                        align_class = block.alignment if block.alignment in ("left", "center", "right") else "center"
                        html_parts.append(
                            f'<figure class="{align_class}">'
                            f'<img src="../{img_name}" alt=""/>'
                            f"</figure>"
                        )

                    elif isinstance(block, TableBlock):
                        html_parts.append(self._table_to_html(block.rows))

                    elif isinstance(block, TextBlock):
                        content = block.inline_html or _escape(block.text)
                        if not content.strip():
                            continue

                        if block.is_heading:
                            tag = self._heading_tag(block.font_size, median_size)
                            # Headings carry alignment too.
                            if block.alignment in ("center", "right"):
                                html_parts.append(
                                    f'<{tag} style="text-align:{block.alignment}">{content}</{tag}>'
                                )
                            else:
                                html_parts.append(f"<{tag}>{content}</{tag}>")
                        else:
                            align_class = block.alignment if block.alignment in (
                                "left", "center", "right", "justify"
                            ) else "left"
                            html_parts.append(
                                f'<p class="{align_class}">{content}</p>'
                            )

                if not html_parts:
                    continue

                chapter_id = f"page_{page.number}"
                chapter_title = f"Page {page.number}"
                body = "\n".join(html_parts)
                content_html = (
                    "<!DOCTYPE html>"
                    '<html xmlns="http://www.w3.org/1999/xhtml">'
                    "<head>"
                    f"<title>{_escape(chapter_title)}</title>"
                    '<link rel="stylesheet" type="text/css" href="../style/main.css"/>'
                    "</head>"
                    f"<body>{body}</body>"
                    "</html>"
                )

                chapter = epub.EpubHtml(
                    uid=chapter_id,
                    title=chapter_title,
                    file_name=f"text/{chapter_id}.xhtml",
                    content=content_html,
                    lang=document.language,
                )
                chapter.add_item(style)
                book.add_item(chapter)
                chapters.append(chapter)
                toc_entries.append(
                    epub.Link(f"text/{chapter_id}.xhtml", chapter_title, chapter_id)
                )

            if not chapters:
                raise BuildError("No content could be extracted to build an EPUB")

            book.toc = toc_entries  # type: ignore[assignment]
            book.add_item(epub.EpubNcx())
            book.add_item(epub.EpubNav())

            # Cover goes first in the spine (linear="no" keeps it out of reading flow
            # but e-readers still display it as the book thumbnail).
            if cover_chapter:
                book.spine = [cover_chapter, "nav", *chapters]
            else:
                book.spine = ["nav", *chapters]

            output_path.parent.mkdir(parents=True, exist_ok=True)
            epub.write_epub(str(output_path), book)
            log.info("epub_written", path=str(output_path), pages=len(chapters))
            return output_path

        except BuildError:
            raise
        except Exception as exc:
            raise BuildError(f"EPUB assembly failed: {exc}") from exc

    def _build_cover(
        self,
        book: epub.EpubBook,
        document: Document,
        style: epub.EpubItem,
    ) -> epub.EpubHtml | None:
        """Adds the cover image and a cover XHTML page to the book.

        Returns the cover EpubHtml chapter, or None if no cover image exists.
        Follows the EPUB3 standard:
          - The cover image item carries properties="cover-image".
          - The cover page is a minimal XHTML that fills the viewport.
          - A <meta name="cover"> entry is added for EPUB2 reader compatibility.
        """
        if not document.cover_image:
            return None

        # Detect format: JPEG starts with FF D8, otherwise treat as PNG.
        is_jpeg = document.cover_image[:2] == b"\xff\xd8"
        cover_ext = "jpg" if is_jpeg else "png"
        cover_file = f"images/cover.{cover_ext}"

        # set_cover registers the image with the EPUB3 cover-image OPF property
        # AND adds the EPUB2 <meta name="cover"> — both required for maximum
        # reader compatibility. create_page=False so we supply our own styled page.
        book.set_cover(cover_file, document.cover_image, create_page=False)

        # Cover XHTML page — fills the full viewport with no margins.
        cover_html = (
            "<!DOCTYPE html>"
            '<html xmlns="http://www.w3.org/1999/xhtml">'
            "<head>"
            f"<title>{_escape(document.title)}</title>"
            "<style>"
            "body{margin:0;padding:0;background:#000;}"
            "img{width:100%;height:100vh;object-fit:contain;display:block;}"
            "</style>"
            "</head>"
            f'<body><img src="../{cover_file}" alt="Cover"/></body>'
            "</html>"
        )
        cover_chapter = epub.EpubHtml(
            uid="cover",
            title="Cover",
            file_name="text/cover.xhtml",
            content=cover_html,
        )
        book.add_item(cover_chapter)
        log.info("cover_added", title=document.title)
        return cover_chapter

    def _heading_tag(self, font_size: float, median_size: float) -> str:
        """Maps the heading's font size to an h1/h2/h3 tag based on relative size."""
        ratio = font_size / max(median_size, 1.0)
        if ratio >= _H1_FACTOR:
            return "h1"
        if ratio >= _H2_FACTOR:
            return "h2"
        return "h3"

    def _document_median_size(self, document: Document) -> float:
        sizes: list[float] = []
        for page in document.pages:
            for block in page.blocks:
                if isinstance(block, TextBlock):
                    sizes.append(block.font_size)
        if not sizes:
            return 12.0
        sizes.sort()
        return sizes[len(sizes) // 2]

    def _table_to_html(self, rows: list[list[str | None]]) -> str:
        if not rows:
            return ""
        header, *body_rows = rows
        th_cells = "".join(f"<th>{_escape(str(c or ''))}</th>" for c in header)
        thead = f"<thead><tr>{th_cells}</tr></thead>"
        tbody_rows = "".join(
            "<tr>" + "".join(f"<td>{_escape(str(c or ''))}</td>" for c in row) + "</tr>"
            for row in body_rows
        )
        return f"<table><thead><tr>{th_cells}</tr></thead><tbody>{tbody_rows}</tbody></table>"


