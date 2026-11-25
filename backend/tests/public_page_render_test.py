"""Server-rendered catalogue and wiki pages: what a reader without JavaScript gets."""

import json
import re
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.wiki_category import WikiCategory
from app.models.wiki_space import WikiSpace
from app.services.public_page_markdown import render_markdown
from app.services.wiki_sync_service import sync_article

RENDER = "/api/v1/public-pages/render"


async def _render(client: AsyncClient, uri: str):
    return await client.get(RENDER, headers={"X-Original-URI": uri})


def _json_ld(html: str) -> list[dict]:
    blocks = re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
    return [node for block in blocks for node in json.loads(block)["@graph"]]


async def _catalog(db_session: AsyncSession, *, price_hidden: bool) -> None:
    brand = Brand(
        name="HexFlow", slug="hexflow", active=True, price_hidden=price_hidden, currency="EUR"
    )
    db_session.add(brand)
    await db_session.flush()
    db_session.add(
        Filament(
            brand_id=brand.id,
            name="PLA",
            slug="pla-red",
            material_type="PLA",
            color_name="Red",
            price_per_kg=24.5,
            active=True,
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_filament_page_names_itself_in_the_requested_language(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _catalog(db_session, price_hidden=False)

    response = await _render(client, "/ru/brands/hexflow/filaments/pla-red")

    assert response.status_code == 200
    html = response.text
    assert '<html lang="ru">' in html
    assert "<title data-seo-field=\"title\">PLA — Red - HexFlow | FilamentHub</title>" in html
    assert 'rel="canonical" href="https://filamenthub.ru/ru/brands/hexflow/filaments/pla-red"' in html
    assert 'hreflang="en" href="https://filamenthub.club/brands/hexflow/filaments/pla-red"' in html
    # The shell parts stay with the frontend build; nginx fills them in.
    assert '<!--# include virtual="/_shell/ru/head.html" -->' in html
    assert '<!--# include virtual="/_shell/ru/body-end.html" -->' in html
    product = next(node for node in _json_ld(html) if node["@type"] == "Product")
    assert product["offers"] == {"@type": "Offer", "price": "24.5", "priceCurrency": "EUR"}
    assert "<h1>PLA — Red</h1>" in html


@pytest.mark.asyncio
async def test_hidden_price_stays_out_of_structured_data(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _catalog(db_session, price_hidden=True)

    html = (await _render(client, "/brands/hexflow/filaments/pla-red")).text

    product = next(node for node in _json_ld(html) if node["@type"] == "Product")
    assert "offers" not in product
    assert "24.5" not in html


@pytest.mark.asyncio
async def test_missing_or_inactive_pages_are_not_found(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    db_session.add(Brand(name="Gone", slug="gone", active=False))
    await db_session.commit()

    for uri in ("/brands/gone", "/brands/nobody", "/brands/nobody/filaments/x", "/catalog/whatever"):
        assert (await _render(client, uri)).status_code == 404, uri


async def _wiki(db_session: AsyncSession, author_id: int) -> None:
    db_session.add_all(
        [
            WikiSpace(id=1, key="guides", order=0, allows_community_authors=False),
            WikiSpace(id=2, key="knowledge", order=10, allows_community_authors=True),
        ]
    )
    db_session.add(WikiCategory(name="Materials", slug="materials", description="About materials", order=0))
    await db_session.commit()
    for language, slug, key, text in (
        ("ru", "pervye-shagi", "first-steps", "# Первые шаги\n\nТекст с <script>alert(1)</script>."),
        ("en", "first-steps", "first-steps", "# First steps\n\nSee [the other one](tolko-russkaya)."),
        ("ru", "tolko-russkaya", "russian-only", "# Только по-русски\n\nТекст."),
    ):
        await sync_article(
            db_session,
            Path(f"{slug}.md"),
            text,
            {
                "title": slug,
                "slug": slug,
                "content_key": key,
                "category": "materials",
                "status": "published",
                "language": language,
                "author_id": author_id,
            },
        )


@pytest.mark.asyncio
async def test_wiki_article_follows_its_own_language_and_real_translations(
    client: AsyncClient, db_session: AsyncSession, auth_user
) -> None:
    await _wiki(db_session, auth_user.id)

    russian = await _render(client, "/ru/wiki/articles/pervye-shagi")
    assert russian.status_code == 200
    assert 'rel="canonical" href="https://filamenthub.ru/ru/wiki/articles/pervye-shagi"' in russian.text
    assert 'hreflang="en" href="https://filamenthub.club/wiki/articles/first-steps"' in russian.text
    assert "<script>alert(1)</script>" not in russian.text
    assert "&lt;script&gt;" in russian.text

    only_russian = (await _render(client, "/ru/wiki/articles/tolko-russkaya")).text
    assert re.findall(r' hreflang="([^"]+)"', only_russian) == ["ru"]

    # Asking for another language opens that edition, or there is none.
    redirect = await _render(client, "/zh/wiki/articles/pervye-shagi")
    assert redirect.status_code == 404
    moved = await _render(client, "/ru/wiki/articles/first-steps")
    assert moved.status_code == 301
    assert moved.headers["location"] == "/ru/wiki/articles/pervye-shagi"

    # Without a prefix the article is served and points at its own language.
    plain = (await _render(client, "/wiki/articles/tolko-russkaya")).text
    assert '<html lang="ru">' in plain
    assert 'rel="canonical" href="https://filamenthub.ru/ru/wiki/articles/tolko-russkaya"' in plain

    # A link to another article by slug keeps the article's language.
    english = (await _render(client, "/wiki/articles/first-steps")).text
    assert '<a href="/wiki/articles/tolko-russkaya">the other one</a>' in english


@pytest.mark.asyncio
async def test_wiki_index_and_category_list_articles_of_the_language(
    client: AsyncClient, db_session: AsyncSession, auth_user
) -> None:
    await _wiki(db_session, auth_user.id)

    index = (await _render(client, "/ru/wiki")).text
    category = (await _render(client, "/wiki/materials")).text

    assert '/ru/wiki/articles/pervye-shagi"' in index
    assert "first-steps" not in index
    assert '/wiki/articles/first-steps"' in category
    assert "pervye-shagi" not in category
    assert (await _render(client, "/wiki/no-such-category")).status_code == 404


def test_markdown_keeps_only_safe_links_and_escapes_text() -> None:
    html = render_markdown(
        "## Head\n\n"
        "[ok](https://example.org) [bad](javascript:alert(1)) [slug](pla-guide) **b** `x<y`\n\n"
        "| A | B |\n|---|---|\n| 1 | <i>2</i> |\n\n"
        "- one\n- two\n\n"
        "```\n<tag>\n```\n\n"
        "![alt \"q\"](/img.webp)",
        lambda slug: f"/ru/wiki/articles/{slug}",
    )

    assert "<h2>Head</h2>" in html
    assert '<a href="https://example.org" rel="nofollow noopener">ok</a>' in html
    assert "javascript:" not in html
    assert '<a href="/ru/wiki/articles/pla-guide">slug</a>' in html
    assert "<strong>b</strong>" in html and "<code>x&lt;y</code>" in html
    assert "<th>A</th>" in html and "<td>&lt;i&gt;2&lt;/i&gt;</td>" in html
    assert "<ul><li>one</li><li>two</li></ul>" in html
    assert "<pre><code>&lt;tag&gt;</code></pre>" in html
    assert '<img src="/img.webp" alt="alt &quot;q&quot;" loading="lazy">' in html
