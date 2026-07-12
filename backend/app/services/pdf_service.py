"""HTML-to-PDF conversion service using WeasyPrint."""

import logging

logger = logging.getLogger(__name__)

MAX_HTML_SIZE = 500_000

_FONT_REPLACEMENT = (
    '"Segoe UI", Arial, sans-serif',
    '"Liberation Sans", "DejaVu Sans", Arial, sans-serif',
)


def _block_external_resources(url: str, **kwargs: object) -> dict[str, object]:
    """WeasyPrint url_fetcher that returns nothing for every URL.

    Quote HTML is user-supplied; the server-side renderer must never fetch
    http(s)/file resources embedded in it, otherwise a crafted document turns
    PDF generation into an SSRF / local-file-read primitive.
    """
    return {"string": b"", "mime_type": "text/plain"}


def generate_pdf_from_html(html_content: str) -> bytes:
    """Convert an HTML string to PDF bytes.

    Replaces Windows-specific fonts with Linux-compatible alternatives
    before rendering.
    """
    if len(html_content) > MAX_HTML_SIZE:
        raise ValueError(f"HTML content exceeds {MAX_HTML_SIZE} bytes")

    from weasyprint import HTML  # lazy: heavy native dep, keeps module importable without it

    safe_html = html_content.replace(_FONT_REPLACEMENT[0], _FONT_REPLACEMENT[1])
    return HTML(string=safe_html, url_fetcher=_block_external_resources).write_pdf()
