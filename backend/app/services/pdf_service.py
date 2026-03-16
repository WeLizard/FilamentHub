"""HTML-to-PDF conversion service using WeasyPrint."""

import logging

from weasyprint import HTML

logger = logging.getLogger(__name__)

MAX_HTML_SIZE = 500_000

_FONT_REPLACEMENT = (
    '"Segoe UI", Arial, sans-serif',
    '"Liberation Sans", "DejaVu Sans", Arial, sans-serif',
)


def generate_pdf_from_html(html_content: str) -> bytes:
    """Convert an HTML string to PDF bytes.

    Replaces Windows-specific fonts with Linux-compatible alternatives
    before rendering.
    """
    if len(html_content) > MAX_HTML_SIZE:
        raise ValueError(f"HTML content exceeds {MAX_HTML_SIZE} bytes")

    safe_html = html_content.replace(_FONT_REPLACEMENT[0], _FONT_REPLACEMENT[1])

    def _block_fetcher(url: str, **kwargs: object) -> dict[str, object]:
        return {"string": b"", "mime_type": "text/plain"}

    html_doc = HTML(string=safe_html, url_fetcher=_block_fetcher)
    return html_doc.write_pdf()
