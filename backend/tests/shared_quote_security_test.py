"""Regression guards for shared-quote security.

Оба вектора уже закрыты в коде; тесты фиксируют инварианты, чтобы защиту
нельзя было снять незаметно:
- браузер: публичный HTML отдаётся со script-blocking CSP;
- сервер: PDF-рендер (weasyprint) не тянет внешние/локальные ресурсы (SSRF/LFI).
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.calculator import get_shared_quote
from app.models.shared_quote import SharedQuote


@pytest.mark.asyncio
async def test_shared_quote_served_with_script_blocking_csp(db_session: AsyncSession):
    """get_shared_quote должен отдавать CSP без script-src (→ default-src 'none') + nosniff."""
    quote = SharedQuote(
        user_id=1,
        title="Q",
        html_content="<script>alert(1)</script><p>hi</p>",
    )
    db_session.add(quote)
    await db_session.commit()
    await db_session.refresh(quote)

    resp = await get_shared_quote(quote.uuid, db_session)

    csp = resp.headers["Content-Security-Policy"]
    assert "default-src 'none'" in csp
    # никакого script-src (даже 'self'/'unsafe-inline') — иначе скрипты снова исполнятся
    assert "script-src" not in csp
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


def test_block_fetcher_blocks_ssrf_and_lfi():
    """url_fetcher должен глушить любой внешний/локальный URL (SSRF/LFI)."""
    from app.services.pdf_service import _block_external_resources

    for hostile in (
        "http://169.254.169.254/latest/meta-data/",
        "https://evil.example/x.png",
        "file:///etc/passwd",
        "http://localhost:8000/internal",
    ):
        assert _block_external_resources(hostile).get("string") == b"", f"must block {hostile}"


def test_generate_pdf_wires_blocking_fetcher(monkeypatch):
    """generate_pdf_from_html должен подключать именно блокирующий url_fetcher."""
    import sys
    import types

    from app.services.pdf_service import _block_external_resources

    captured: dict[str, object] = {}

    class FakeHTML:
        def __init__(self, string: str, url_fetcher):
            captured["fetcher"] = url_fetcher

        def write_pdf(self) -> bytes:
            return b"%PDF-fake"

    fake_weasyprint = types.ModuleType("weasyprint")
    fake_weasyprint.HTML = FakeHTML
    monkeypatch.setitem(sys.modules, "weasyprint", fake_weasyprint)

    from app.services.pdf_service import generate_pdf_from_html

    out = generate_pdf_from_html("<img src='http://169.254.169.254/latest/meta-data/'>")
    assert out == b"%PDF-fake"
    assert captured["fetcher"] is _block_external_resources
