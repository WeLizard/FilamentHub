"""Sitemap.xml and robots.txt endpoints for SEO."""

from datetime import datetime
from html import escape
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.wiki_article import WikiArticle, WikiArticleStatus
from app.models.wiki_category import WikiCategory

router = APIRouter(tags=["seo"])

BASE_URL = "https://filamenthub.ru"
SITEMAP_LOCALES = ("en", "ru", "zh")


def _localized_path(path: str, locale: str) -> str:
    if locale == "en":
        return path
    if path == "/":
        return f"/{locale}/"
    return f"/{locale}{path}"


def _append_url(
    xml_lines: list[str],
    *,
    path: str,
    lastmod: datetime | None,
    changefreq: str,
    priority: str,
) -> None:
    alternates = {
        "x-default": f"{BASE_URL}{_localized_path(path, 'en')}",
        **{
            locale: f"{BASE_URL}{_localized_path(path, locale)}"
            for locale in SITEMAP_LOCALES
        },
    }
    for locale in SITEMAP_LOCALES:
        xml_lines.append("  <url>")
        xml_lines.append(
            f"    <loc>{escape(f'{BASE_URL}{_localized_path(path, locale)}')}</loc>"
        )
        if lastmod is not None:
            xml_lines.append(f"    <lastmod>{lastmod.strftime('%Y-%m-%d')}</lastmod>")
        for hreflang, href in alternates.items():
            xml_lines.append(
                "    <xhtml:link rel=\"alternate\" "
                f"hreflang=\"{hreflang}\" href=\"{escape(href)}\" />"
            )
        xml_lines.append(f"    <changefreq>{changefreq}</changefreq>")
        xml_lines.append(f"    <priority>{priority}</priority>")
        xml_lines.append("  </url>")


@router.get("/sitemap.xml", response_class=PlainTextResponse)
async def sitemap_xml(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """
    Генерирует sitemap.xml для поисковых роботов.

    Включает:
    - Главную страницу
    - Каталог материалов
    - Страницы филаментов
    - Страницы брендов
    - Wiki категории
    - Wiki статьи
    """
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '         xmlns:xhtml="http://www.w3.org/1999/xhtml"',
        '         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        '         xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9',
        '         http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd">',
    ]

    # Статические страницы
    static_pages = [
        ("/", "1.0", "daily"),
        ("/features", "0.9", "monthly"),
        ("/wiki", "0.9", "weekly"),
        ("/download", "0.8", "monthly"),
    ]

    for path, priority, changefreq in static_pages:
        _append_url(
            xml_lines,
            path=path,
            lastmod=None,
            changefreq=changefreq,
            priority=priority,
        )

    # Филаменты
    filaments_result = await db.execute(
        select(Filament.slug, Filament.updated_at, Brand.slug)
        .join(Brand, Brand.id == Filament.brand_id)
        .where(Filament.active.is_(True), Brand.active.is_(True))
        .order_by(Brand.slug, Filament.slug)
    )
    for filament_slug, updated_at, brand_slug in filaments_result.all():
        _append_url(
            xml_lines,
            path=f"/brands/{brand_slug}/filaments/{filament_slug}",
            lastmod=updated_at,
            changefreq="weekly",
            priority="0.8",
        )

    # Бренды
    brands_result = await db.execute(
        select(Brand.slug, Brand.updated_at)
        .where(
            Brand.active.is_(True),
            exists().where(
                Filament.brand_id == Brand.id,
                Filament.active.is_(True),
            ),
        )
        .order_by(Brand.slug)
    )
    for brand_slug, updated_at in brands_result.all():
        _append_url(
            xml_lines,
            path=f"/brands/{brand_slug}",
            lastmod=updated_at,
            changefreq="monthly",
            priority="0.7",
        )

    # Wiki категории
    categories_result = await db.execute(
        select(WikiCategory.slug, WikiCategory.updated_at)
        .where(
            exists().where(
                WikiArticle.category_id == WikiCategory.id,
                WikiArticle.status == WikiArticleStatus.PUBLISHED,
            )
        )
        .order_by(WikiCategory.slug)
    )
    for category_slug, updated_at in categories_result.all():
        _append_url(
            xml_lines,
            path=f"/wiki/{category_slug}",
            lastmod=updated_at,
            changefreq="weekly",
            priority="0.8",
        )

    # Wiki статьи (только опубликованные)
    articles_result = await db.execute(
        select(WikiArticle.slug, WikiArticle.updated_at).where(
            WikiArticle.status == WikiArticleStatus.PUBLISHED
        )
    )
    articles = articles_result.all()

    for article_slug, updated_at in articles:
        _append_url(
            xml_lines,
            path=f"/wiki/articles/{article_slug}",
            lastmod=updated_at,
            changefreq="monthly",
            priority="0.9",
        )

    # Закрываем XML
    xml_lines.append('</urlset>')

    xml_content = '\n'.join(xml_lines)

    return PlainTextResponse(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Type": "application/xml; charset=utf-8"},
    )


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt() -> Response:
    """Allow public crawling while excluding service API and connector paths.

    Private web routes stay crawlable so their ``X-Robots-Tag: noindex``
    response can be observed and the URL can be removed from search indexes.
    """
    robots_content = """# robots.txt для FilamentHub
# https://filamenthub.ru/robots.txt

User-agent: *
Allow: /
Disallow: /api/
Disallow: /spool_compat/

# Sitemap
Sitemap: https://filamenthub.ru/sitemap.xml
"""

    return PlainTextResponse(
        content=robots_content,
        media_type="text/plain",
        headers={"Content-Type": "text/plain; charset=utf-8"},
    )

