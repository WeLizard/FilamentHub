"""Catalogue and wiki pages as complete HTML for readers without JavaScript.

nginx sends the public catalogue and wiki routes here and fills the
``<!--# include -->`` lines with the site shell that the frontend build writes
to ``dist/_shell/<variant>/`` (scripts/generate-localized-seo.mjs). The page
gets its own title, description, canonical address, language alternates,
structured data and text, the same ones the application sets after it loads
(components/SEOHead.tsx), so a search engine or an AI crawler reads the page
itself instead of the empty application shell.

The application replaces the text inside ``#root`` on its first render, and
reuses the tags marked ``data-seo-base`` / ``data-seo-hreflang``.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.site import DEFAULT_LOCALE, SITE_LOCALES, SITE_ORIGINS, canonical_url, localized_path
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.filament_review import FilamentReview
from app.models.wiki_article import WikiArticle, WikiArticleStatus
from app.models.wiki_category import WikiCategory
from app.services.catalog_url_service import (
    brand_public_path,
    filament_public_path,
    resolve_filament_identifier,
)
from app.services.preset_ratings import filament_rating
from app.services.public_page_markdown import first_image, render_markdown

# Interface strings copied from frontend/src/locales by
# scripts/sync_public_page_texts.py; a contract test keeps them equal.
_TEXTS: dict[str, dict] = json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "public_page_texts.json").read_text(
        encoding="utf-8"
    )
)
OG_LOCALES = {"en": "en_US", "ru": "ru_RU", "zh": "zh_CN"}
DEFAULT_IMAGE = "/email/hero.jpg"
DEFAULT_IMAGE_SIZE = (1120, 625)
ROBOTS = "index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1"
ORGANIZATION = {
    "@type": "Organization",
    "@id": f"{SITE_ORIGINS[DEFAULT_LOCALE]}/#organization",
    "name": "FilamentHub",
    "url": f"{SITE_ORIGINS[DEFAULT_LOCALE]}/",
}
# A brand page lists its materials as links; far beyond any real brand.
MAX_LISTED_FILAMENTS = 2000


def _text(locale: str, key: str, **params: object) -> str:
    return re.sub(
        r"\{\{\s*(\w+)\s*\}\}",
        lambda match: str(params.get(match.group(1), "")),
        _TEXTS[locale][key],
    )


def _category_name(locale: str, category: WikiCategory) -> str:
    """The category name in the reader's language, as the wiki pages show it."""
    return _TEXTS[locale]["wikiAuthoring.categories"].get(category.slug, category.name)


def filament_variant_label(name: str, color_name: str | None) -> str:
    """The material name with its colour, as utils/catalogUrls.ts builds it."""
    name = name.strip()
    color = (color_name or "").strip()
    if not color:
        return name

    def words(value: str) -> str:
        return re.sub(r"[\W_]+", " ", value.lower()).strip()

    if words(color) and f" {words(color)} " in f" {words(name)} ":
        return name
    return f"{name} — {color}"


@dataclass(frozen=True)
class PageRequest:
    """One requested address, split the way nginx and the application split it."""

    path: str
    path_locale: str | None
    variant: str
    raw_path: str
    query: str

    @classmethod
    def parse(cls, original_uri: str) -> "PageRequest":
        parts = urlsplit(original_uri)
        raw_path = unquote(parts.path) or "/"
        segments = [segment for segment in raw_path.split("/") if segment]
        path_locale = None
        if segments and segments[0].lower() in SITE_LOCALES:
            path_locale = segments.pop(0).lower()
        lng = parse_qs(parts.query).get("lng", [""])[0].lower()
        if path_locale:
            variant = path_locale
        elif lng in SITE_LOCALES:
            variant = lng
        else:
            variant = "x-default"
        return cls(
            path="/" + "/".join(segments),
            path_locale=path_locale,
            variant=variant,
            raw_path=raw_path,
            query=parts.query,
        )

    @property
    def interface_locale(self) -> str:
        """The language of the shell and the interface strings."""
        return DEFAULT_LOCALE if self.variant == "x-default" else self.variant

    @property
    def canonical_locale(self) -> str:
        """Language whose address is canonical: the prefix, as SEOHead does."""
        return self.path_locale or DEFAULT_LOCALE

    def href(self, path: str) -> str:
        """A link that keeps the reader's language prefix."""
        return localized_path(path, self.canonical_locale)


@dataclass
class PageMeta:
    title: str
    description: str
    canonical: str
    alternates: dict[str, str]
    content_locale: str
    og_type: str = "website"
    keywords: str | None = None
    image: str | None = None
    article: dict[str, object] = field(default_factory=dict)
    json_ld: dict | None = None


@dataclass(frozen=True)
class RenderedPage:
    status: int
    html: str = ""
    location: str | None = None


NOT_FOUND = RenderedPage(status=404)


def _absolute(url: str, locale: str) -> str:
    return url if url.startswith(("https://", "http://")) else f"{SITE_ORIGINS[locale]}{url}"


def _every_language(path: str) -> dict[str, str]:
    return {
        "x-default": canonical_url(path, DEFAULT_LOCALE),
        **{locale: canonical_url(path, locale) for locale in SITE_LOCALES},
    }


def _breadcrumbs(items: list[tuple[str, str]]) -> dict:
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": position, "name": name, "item": url}
            for position, (name, url) in enumerate(items, start=1)
        ],
    }


def _breadcrumb_nav(items: list[tuple[str, str | None]]) -> str:
    crumbs = "".join(
        f'<li><a href="{escape(href, quote=True)}">{escape(name)}</a></li>'
        if href
        else f'<li aria-current="page">{escape(name)}</li>'
        for name, href in items
    )
    return f'<nav aria-label="breadcrumb"><ol>{crumbs}</ol></nav>'


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _render_head(meta: PageMeta, request: PageRequest) -> str:
    full_title = f"{meta.title} | FilamentHub"
    image = meta.image or _absolute(DEFAULT_IMAGE, meta.content_locale)

    def tag(attribute: str, key: str, content: str | None, extra: str = "") -> str:
        if not content:
            return ""
        return (
            f'    <meta data-seo-base="true"{extra} {attribute}="{escape(key, quote=True)}" '
            f'content="{escape(content, quote=True)}" />\n'
        )

    head = [
        tag("name", "description", meta.description, ' data-seo-field="description"'),
        tag("name", "keywords", meta.keywords, ' data-seo-field="keywords"'),
        tag("name", "author", "FilamentHub"),
        tag("property", "og:title", full_title),
        tag("property", "og:description", meta.description),
        tag("property", "og:image", image),
        tag("property", "og:image:alt", full_title),
    ]
    if meta.image is None:
        head.append(tag("property", "og:image:width", str(DEFAULT_IMAGE_SIZE[0])))
        head.append(tag("property", "og:image:height", str(DEFAULT_IMAGE_SIZE[1])))
    head += [
        tag("property", "og:url", meta.canonical),
        tag("property", "og:type", meta.og_type),
        tag("property", "og:site_name", "FilamentHub"),
        tag("property", "og:locale", OG_LOCALES[meta.content_locale]),
    ]
    for locale in SITE_LOCALES:
        if locale != meta.content_locale and locale in meta.alternates:
            head.append(
                tag("property", "og:locale:alternate", OG_LOCALES[locale], ' data-seo-og-alternate="true"')
            )
    for key, value in meta.article.items():
        values = value if isinstance(value, list) else [value]
        head += [tag("property", f"article:{key}", str(item)) for item in values if item]
    head += [
        tag("name", "twitter:card", "summary_large_image"),
        tag("name", "twitter:title", full_title),
        tag("name", "twitter:description", meta.description),
        tag("name", "twitter:image", image),
        tag("name", "twitter:image:alt", full_title),
        tag("name", "robots", ROBOTS),
        f'    <link data-seo-base="true" rel="canonical" href="{escape(meta.canonical, quote=True)}" />\n',
    ]
    for hreflang, href in meta.alternates.items():
        head.append(
            f'    <link data-seo-hreflang="{hreflang}" rel="alternate" hreflang="{hreflang}" '
            f'href="{escape(href, quote=True)}" />\n'
        )
    head.append(f'    <title data-seo-field="title">{escape(full_title)}</title>\n')
    if meta.json_ld:
        # "</" cannot end the script early once escaped; JSON reads "<\/" as "</".
        payload = json.dumps(meta.json_ld, ensure_ascii=False).replace("</", "<\\/")
        head.append(
            '    <script type="application/ld+json" data-seo-server="true" '
            f'data-seo-path="{escape(request.raw_path, quote=True)}">{payload}</script>\n'
        )
    return "".join(head)


def _document(meta: PageMeta, body: str, request: PageRequest) -> str:
    shell = f"/_shell/{request.variant}"
    return (
        "<!doctype html>\n"
        f'<html lang="{meta.content_locale}">\n  <head>\n'
        f'<!--# include virtual="{shell}/head.html" -->\n'
        f"{_render_head(meta, request)}"
        "  </head>\n  <body>"
        f'<!--# include virtual="{shell}/body-start.html" -->'
        f'<div id="root"><main class="fh-static">{body}'
        f'<!--# include virtual="{shell}/nav.html" --></main></div>'
        f'<!--# include virtual="{shell}/body-end.html" -->'
        "</body>\n</html>\n"
    )


def _page(meta: PageMeta, body: str, request: PageRequest) -> RenderedPage:
    return RenderedPage(status=200, html=_document(meta, body, request))


async def _filament_page(
    db: AsyncSession, request: PageRequest, brand_slug: str, filament_slug: str
) -> RenderedPage:
    resolved = await resolve_filament_identifier(
        db, brand_identifier=brand_slug, filament_identifier=filament_slug
    )
    if resolved is None or not resolved.filament.active or not resolved.brand.active:
        return NOT_FOUND
    filament, brand = resolved.filament, resolved.brand
    locale = request.interface_locale
    path = filament_public_path(filament, brand)
    canonical = canonical_url(path, request.canonical_locale)
    brand_url = canonical_url(brand_public_path(brand), request.canonical_locale)
    name = filament_variant_label(filament.name, filament.color_name)
    description = _text(
        locale, "filamentDetailPage.seoDescription",
        materialType=filament.material_type, name=name, brand=brand.name,
    )
    product: dict[str, object] = {
        "@type": "Product",
        "name": name,
        "url": canonical,
        "description": description,
        "brand": {"@type": "Brand", "name": brand.name},
        "category": f"3D Printing Filament - {filament.material_type}",
    }
    if filament.color_name:
        product["color"] = filament.color_name
    if filament.price_per_kg is not None and not brand.price_hidden:
        product["offers"] = {
            "@type": "Offer",
            "price": format(filament.price_per_kg, "f").rstrip("0").rstrip("."),
            "priceCurrency": brand.currency or "RUB",
        }
    reviews = (
        await db.execute(
            select(FilamentReview).where(
                FilamentReview.filament_id == filament.id, FilamentReview.active.is_(True)
            )
        )
    ).scalars().all()
    if reviews:
        # The same rating the page shows next to the material.
        rating, _success_rate = await filament_rating(filament.id, reviews, db)
        if rating is not None:
            product["aggregateRating"] = {
                "@type": "AggregateRating",
                "ratingValue": round(rating, 2),
                "reviewCount": len(reviews),
                "bestRating": 5,
                "worstRating": 1,
            }
    home = canonical_url("/", request.canonical_locale)
    meta = PageMeta(
        title=f"{name} - {brand.name}",
        description=description,
        keywords=_text(
            locale, "filamentDetailPage.seoKeywords",
            name=name, materialType=filament.material_type, brand=brand.name,
        ),
        canonical=canonical,
        alternates=_every_language(path),
        content_locale=locale,
        og_type="product",
        json_ld={
            "@context": "https://schema.org",
            "@graph": [
                product,
                _breadcrumbs([("FilamentHub", home), (brand.name, brand_url), (name, canonical)]),
            ],
        },
    )
    facts = [
        (_text(locale, "filamentDetailPage.brand"),
         f'<a href="{escape(request.href(brand_public_path(brand)), quote=True)}">{escape(brand.name)}</a>'),
        (_text(locale, "catalogPage.tableMaterial"), escape(filament.material_type)),
    ]
    if filament.color_name:
        facts.append((_text(locale, "filamentDetailPage.color"), escape(filament.color_name)))
    body = (
        _breadcrumb_nav([
            (_text(locale, "layout.nav_catalog"), request.href("/")),
            (brand.name, request.href(brand_public_path(brand))),
            (name, None),
        ])
        + f"<h1>{escape(name)}</h1>"
        + f"<p>{escape(filament.description or description)}</p>"
        + "<dl>" + "".join(f"<dt>{escape(term)}</dt><dd>{value}</dd>" for term, value in facts) + "</dl>"
    )
    return _page(meta, body, request)


async def _brand_page(db: AsyncSession, request: PageRequest, brand_slug: str) -> RenderedPage:
    brand = await db.scalar(select(Brand).where(Brand.slug == brand_slug))
    if brand is None or not brand.active:
        return NOT_FOUND
    filaments = (
        await db.execute(
            select(Filament)
            .where(Filament.brand_id == brand.id, Filament.active.is_(True))
            .order_by(Filament.material_type, Filament.name, Filament.slug)
            .limit(MAX_LISTED_FILAMENTS)
        )
    ).scalars().all()
    locale = request.interface_locale
    path = brand_public_path(brand)
    canonical = canonical_url(path, request.canonical_locale)
    description = (
        brand.description[:160]
        if brand.description
        else _text(locale, "brandDetailPage.seoDescription", name=brand.name, count=len(filaments))
    )
    image = _absolute(brand.logo_url, locale) if brand.logo_url else None
    brand_ld: dict[str, object] = {
        "@type": "Brand",
        "@id": f"{canonical}#brand",
        "name": brand.name,
        "url": canonical,
    }
    if image:
        brand_ld["logo"] = image
    if brand.description:
        brand_ld["description"] = brand.description
    if brand.website and brand.website.startswith(("https://", "http://")):
        brand_ld["sameAs"] = [brand.website]
    meta = PageMeta(
        title=brand.name,
        description=description,
        canonical=canonical,
        alternates=_every_language(path),
        content_locale=locale,
        image=image,
        json_ld={
            "@context": "https://schema.org",
            "@graph": [
                brand_ld,
                _breadcrumbs([
                    ("FilamentHub", canonical_url("/", request.canonical_locale)),
                    (brand.name, canonical),
                ]),
            ],
        },
    )
    items = "".join(
        f'<li><a href="{escape(request.href(filament_public_path(filament, brand)), quote=True)}">'
        f"{escape(filament_variant_label(filament.name, filament.color_name))}</a>"
        f" — {escape(filament.material_type)}</li>"
        for filament in filaments
    )
    body = (
        _breadcrumb_nav([(_text(locale, "layout.nav_catalog"), request.href("/")), (brand.name, None)])
        + f"<h1>{escape(brand.name)}</h1>"
        + f"<p>{escape(brand.description or description)}</p>"
        + (f"<h2>{escape(_text(locale, 'brandDetailPage.allMaterials'))}</h2><ul>{items}</ul>" if items else "")
    )
    return _page(meta, body, request)


def _published_articles(language: str):
    return (
        select(WikiArticle)
        .where(WikiArticle.status == WikiArticleStatus.PUBLISHED, WikiArticle.language == language)
        .order_by(WikiArticle.order, WikiArticle.title)
    )


def _article_links(articles, request: PageRequest) -> str:
    return "".join(
        f'<li><a href="{escape(request.href(f"/wiki/articles/{article.slug}"), quote=True)}">'
        f"{escape(article.title)}</a>: {escape(article.summary)}</li>"
        for article in articles
    )


async def _wiki_index_page(db: AsyncSession, request: PageRequest) -> RenderedPage:
    locale = request.interface_locale
    categories = (await db.execute(select(WikiCategory).order_by(WikiCategory.order))).scalars().all()
    articles = (await db.execute(_published_articles(locale))).scalars().all()
    by_category: dict[int, list[WikiArticle]] = {}
    for article in articles:
        by_category.setdefault(article.category_id, []).append(article)
    sections = "".join(
        f'<h3><a href="{escape(request.href(f"/wiki/{category.slug}"), quote=True)}">'
        f"{escape(_category_name(locale, category))}</a></h3><p>{escape(category.description)}</p>"
        f"<ul>{_article_links(by_category[category.id], request)}</ul>"
        for category in categories
        if category.id in by_category
    )
    title = _text(locale, "wikiPage.seoTitle")
    description = _text(locale, "wikiPage.seoDescription")
    meta = PageMeta(
        title=title,
        description=description,
        keywords=_text(locale, "wikiPage.seoKeywords"),
        canonical=canonical_url("/wiki", request.canonical_locale),
        alternates=_every_language("/wiki"),
        content_locale=locale,
    )
    body = (
        f"<h1>{escape(title)}</h1><p>{escape(description)}</p>"
        f"<h2>{escape(_text(locale, 'wikiPage.categories'))}</h2>{sections}"
    )
    return _page(meta, body, request)


async def _wiki_category_page(db: AsyncSession, request: PageRequest, slug: str) -> RenderedPage:
    category = await db.scalar(select(WikiCategory).where(WikiCategory.slug == slug))
    if category is None:
        return NOT_FOUND
    locale = request.interface_locale
    articles = (
        await db.execute(_published_articles(locale).where(WikiArticle.category_id == category.id))
    ).scalars().all()
    path = f"/wiki/{category.slug}"
    canonical = canonical_url(path, request.canonical_locale)
    wiki_title = _text(locale, "wikiPage.seoTitle")
    name = _category_name(locale, category)
    meta = PageMeta(
        title=f"{name} - {_text(locale, 'wikiCategoryPage.seoSuffix')}",
        description=category.description
        or _text(locale, "wikiCategoryPage.seoDescription", name=name.lower()),
        canonical=canonical,
        alternates=_every_language(path),
        content_locale=locale,
        json_ld={
            "@context": "https://schema.org",
            **_breadcrumbs([
                (wiki_title, canonical_url("/wiki", request.canonical_locale)),
                (name, canonical),
            ]),
        },
    )
    body = (
        _breadcrumb_nav([(wiki_title, request.href("/wiki")), (name, None)])
        + f"<h1>{escape(name)}</h1><p>{escape(category.description)}</p>"
        + (f"<ul>{_article_links(articles, request)}</ul>" if articles else "")
    )
    return _page(meta, body, request)


async def _wiki_article_page(db: AsyncSession, request: PageRequest, slug: str) -> RenderedPage:
    article = await db.scalar(
        select(WikiArticle).where(
            WikiArticle.slug == slug, WikiArticle.status == WikiArticleStatus.PUBLISHED
        )
    )
    if article is None:
        return NOT_FOUND
    editions = (
        await db.execute(
            select(WikiArticle.language, WikiArticle.slug).where(
                WikiArticle.content_key == article.content_key,
                WikiArticle.status == WikiArticleStatus.PUBLISHED,
            )
        )
    ).all()
    paths = {
        language: f"/wiki/articles/{edition_slug}"
        for language, edition_slug in editions
        if language in SITE_LOCALES
    }
    if request.path_locale and article.language != request.path_locale:
        # A language prefix asks for that language: open its edition, as the
        # application does, or report that there is none.
        target = paths.get(request.path_locale)
        if target is None:
            return NOT_FOUND
        location = localized_path(target, request.path_locale)
        if request.query:
            location = f"{location}?{request.query}"
        return RenderedPage(status=301, location=location)

    language = article.language if article.language in SITE_LOCALES else DEFAULT_LOCALE
    path = f"/wiki/articles/{article.slug}"
    canonical = canonical_url(path, language)
    alternates = {locale: canonical_url(paths[locale], locale) for locale in SITE_LOCALES if locale in paths}
    if DEFAULT_LOCALE in alternates:
        alternates = {"x-default": alternates[DEFAULT_LOCALE], **alternates}
    category = await db.get(WikiCategory, article.category_id)
    category_name = _category_name(language, category) if category is not None else None
    picture = first_image(article.content)
    image = _absolute(picture, language) if picture else None
    wiki_title = _text(language, "wikiPage.seoTitle")
    crumbs = [(wiki_title, canonical_url("/wiki", language))]
    if category is not None:
        crumbs.append((category_name, canonical_url(f"/wiki/{category.slug}", language)))
    crumbs.append((article.title, canonical))
    article_ld: dict[str, object] = {
        "@type": "Article",
        "@id": f"{canonical}#article",
        "headline": article.title,
        "description": article.summary,
        "inLanguage": language,
        "url": canonical,
        "datePublished": _iso(article.created_at),
        "dateModified": _iso(article.updated_at),
        "author": {"@type": "Person", "name": article.author} if article.author else ORGANIZATION,
        "publisher": ORGANIZATION,
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
        "isPartOf": {"@type": "WebSite", "@id": f"{canonical_url('/', language)}#website"},
        "articleSection": category_name or "Wiki",
    }
    if image:
        article_ld["image"] = [image]
    if article.tags:
        article_ld["keywords"] = ", ".join(article.tags)
    meta = PageMeta(
        title=article.title,
        description=article.summary,
        keywords=", ".join(article.tags) if article.tags else None,
        canonical=canonical,
        alternates=alternates,
        content_locale=language,
        og_type="article",
        image=image,
        article={
            "published_time": _iso(article.created_at),
            "modified_time": _iso(article.updated_at),
            "section": category_name,
            "tag": list(article.tags or []),
        },
        json_ld={"@context": "https://schema.org", "@graph": [article_ld, _breadcrumbs(crumbs)]},
    )
    # The stored text opens with the title as a level-one heading; the page
    # prints the title itself, as the application does.
    content = re.sub(r"\A\s*#\s+[^\n]*\n", "", article.content, count=1)
    nav = [(wiki_title, localized_path("/wiki", language))]
    if category is not None:
        nav.append((category_name, localized_path(f"/wiki/{category.slug}", language)))
    nav.append((article.title, None))
    body = (
        _breadcrumb_nav(nav)
        + f"<article><h1>{escape(article.title)}</h1><p>{escape(article.summary)}</p>"
        + render_markdown(content, lambda target: localized_path(f"/wiki/articles/{target}", language))
        + "</article>"
    )
    return _page(meta, body, request)


async def render_public_page(db: AsyncSession, original_uri: str) -> RenderedPage:
    """Render one catalogue or wiki address; unknown addresses are not found."""
    request = PageRequest.parse(original_uri)
    segments = [segment for segment in request.path.split("/") if segment]
    match segments:
        case ["brands", brand_slug]:
            return await _brand_page(db, request, brand_slug)
        case ["brands", brand_slug, "filaments", filament_slug]:
            return await _filament_page(db, request, brand_slug, filament_slug)
        case ["wiki"]:
            return await _wiki_index_page(db, request)
        case ["wiki", "articles", slug]:
            return await _wiki_article_page(db, request, slug)
        case ["wiki", slug]:
            return await _wiki_category_page(db, request, slug)
    return NOT_FOUND
