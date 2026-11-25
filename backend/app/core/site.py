"""Public addresses of the site: one canonical host per language.

Both hosts serve every language. The same mapping drives the page metadata in
the frontend (frontend/src/data/siteOrigins.json); scripts/tests keeps the two
equal.
"""

from urllib.parse import urlsplit

SITE_ORIGINS = {
    "en": "https://filamenthub.club",
    "ru": "https://filamenthub.ru",
    "zh": "https://filamenthub.club",
}
SITE_LOCALES = tuple(SITE_ORIGINS)
DEFAULT_LOCALE = "en"
FALLBACK_ORIGIN = SITE_ORIGINS["ru"]


def origin_for_host(host: str | None) -> str:
    """Return the public origin a request arrived on, or the fallback one."""
    name = (host or "").split(":")[0].lower().removeprefix("www.")
    for origin in SITE_ORIGINS.values():
        if urlsplit(origin).hostname == name:
            return origin
    return FALLBACK_ORIGIN


def localized_path(path: str, locale: str) -> str:
    """Add the language prefix; the default language has none."""
    if locale == DEFAULT_LOCALE:
        return path
    if path == "/":
        return f"/{locale}/"
    return f"/{locale}{path}"


def canonical_url(path: str, locale: str) -> str:
    """The canonical address of a page in one language."""
    return f"{SITE_ORIGINS[locale]}{localized_path(path, locale)}"
