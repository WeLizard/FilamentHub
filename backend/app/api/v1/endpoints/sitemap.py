"""Sitemap.xml and robots.txt endpoints for SEO."""

from datetime import datetime
from html import escape
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.site import (
    DEFAULT_LOCALE,
    SITE_LOCALES,
    SITE_ORIGINS,
    canonical_url,
    origin_for_host,
)
from app.db.session import get_db
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.wiki_article import WikiArticle, WikiArticleStatus
from app.models.wiki_category import WikiCategory

router = APIRouter(tags=["seo"])

def _append_url(
    xml_lines: list[str],
    *,
    origin: str,
    path: str | None = None,
    paths: dict[str, str] | None = None,
    lastmod: datetime | None | dict[str, datetime | None],
    changefreq: str,
    priority: str,
) -> None:
    """Add one page in every language it exists in.

    ``path`` is a page that exists under the same address in every language;
    ``paths`` maps each language to its own address when only some languages
    have the page (a wiki article and its translations); ``lastmod`` may then
    give each language its own date.
    """
    if paths is None:
        assert path is not None
        paths = dict.fromkeys(SITE_LOCALES, path)
    languages = [locale for locale in SITE_LOCALES if locale in paths]
    alternates = {locale: canonical_url(paths[locale], locale) for locale in languages}
    if DEFAULT_LOCALE in paths:
        alternates = {"x-default": alternates[DEFAULT_LOCALE], **alternates}
    # A sitemap lists only addresses of its own host: the languages whose
    # canonical host is the one being asked.
    for locale in languages:
        if SITE_ORIGINS[locale] != origin:
            continue
        xml_lines.append("  <url>")
        xml_lines.append(f"    <loc>{escape(alternates[locale])}</loc>")
        stamp = lastmod.get(locale) if isinstance(lastmod, dict) else lastmod
        if stamp is not None:
            xml_lines.append(f"    <lastmod>{stamp.strftime('%Y-%m-%d')}</lastmod>")
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
    request: Request,
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
    origin = origin_for_host(request.headers.get("host"))
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
        ("/for-brands", "0.8", "monthly"),
        ("/about", "0.6", "monthly"),
        ("/wiki", "0.9", "weekly"),
        ("/download", "0.8", "monthly"),
        ("/download/octoprint", "0.6", "monthly"),
        ("/download/print-farm", "0.6", "monthly"),
        ("/download/edge", "0.6", "monthly"),
    ]

    for path, priority, changefreq in static_pages:
        _append_url(
            xml_lines,
            origin=origin,
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
            origin=origin,
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
            origin=origin,
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
            origin=origin,
            path=f"/wiki/{category_slug}",
            lastmod=updated_at,
            changefreq="weekly",
            priority="0.8",
        )

    # Wiki статьи (только опубликованные). Each edition has its own language
    # and address; the editions of one material are each other's alternates.
    articles_result = await db.execute(
        select(
            WikiArticle.content_key,
            WikiArticle.language,
            WikiArticle.slug,
            WikiArticle.updated_at,
        )
        .where(WikiArticle.status == WikiArticleStatus.PUBLISHED)
        .order_by(WikiArticle.content_key, WikiArticle.language)
    )
    editions: dict[str, dict[str, tuple[str, datetime | None]]] = {}
    for content_key, language, article_slug, updated_at in articles_result.all():
        if language in SITE_ORIGINS:
            editions.setdefault(content_key, {})[language] = (article_slug, updated_at)

    for material in editions.values():
        paths = {
            language: f"/wiki/articles/{article_slug}"
            for language, (article_slug, _updated_at) in material.items()
        }
        _append_url(
            xml_lines,
            origin=origin,
            paths=paths,
            lastmod={language: updated_at for language, (_slug, updated_at) in material.items()},
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
async def robots_txt(request: Request) -> Response:
    """Allow public crawling while excluding service API and connector paths.

    Private web routes stay crawlable so their ``X-Robots-Tag: noindex``
    response can be observed and the URL can be removed from search indexes.
    """
    origin = origin_for_host(request.headers.get("host"))
    robots_content = f"""# robots.txt для FilamentHub
# {origin}/robots.txt

User-agent: *
Allow: /
Disallow: /api/
Disallow: /spool_compat/

# Sitemap
Sitemap: {origin}/sitemap.xml
"""

    return PlainTextResponse(
        content=robots_content,
        media_type="text/plain",
        headers={"Content-Type": "text/plain; charset=utf-8"},
    )

