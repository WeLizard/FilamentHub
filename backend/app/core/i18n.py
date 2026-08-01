"""Localized text catalogs for outgoing email."""

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from markupsafe import Markup, escape

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = ("ru", "en", "zh")
DEFAULT_LANGUAGE = "en"

_CATALOG_DIR = Path(__file__).resolve().parent.parent / "locales" / "emails"


def normalize_language(value: str | None) -> str | None:
    """Reduce a language tag to a supported code, or None when unsupported."""
    if not value:
        return None
    code = value.strip().lower().replace("_", "-").split("-")[0]
    return code if code in SUPPORTED_LANGUAGES else None


def resolve_language(*candidates: str | None) -> str:
    """Pick the first supported language among the candidates."""
    for candidate in candidates:
        code = normalize_language(candidate)
        if code:
            return code
    return DEFAULT_LANGUAGE


@lru_cache(maxsize=len(SUPPORTED_LANGUAGES))
def _catalog(language: str) -> dict[str, Any]:
    with (_CATALOG_DIR / f"{language}.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def _lookup(language: str, key: str) -> Any:
    node: Any = _catalog(language)
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _entry(key: str, language: str | None, expected: type) -> Any:
    lang = resolve_language(language)
    value = _lookup(lang, key)
    if not isinstance(value, expected) and lang != DEFAULT_LANGUAGE:
        logger.warning("Email text %r missing for %r, falling back to %r", key, lang, DEFAULT_LANGUAGE)
        value = _lookup(DEFAULT_LANGUAGE, key)
    if not isinstance(value, expected):
        logger.error("Email text %r missing from every catalog", key)
        return None
    return value


def translate(key: str, language: str | None = None, **params: object) -> str:
    """Return one localized string with `{name}` placeholders filled in."""
    text = _entry(key, language, str)
    if text is None:
        return key
    if not params:
        return text
    try:
        return text.format(**params)
    except (KeyError, IndexError):
        logger.error("Email text %r does not accept params %r", key, sorted(params))
        return text


def translate_html(key: str, language: str | None = None, **params: object) -> Markup:
    """Same as `translate`, for catalog entries that carry their own inline markup.

    Params are escaped one by one, so caller-supplied values stay inert while the
    markup written in the catalog survives.
    """
    escaped = {name: escape(value) for name, value in params.items()}
    return Markup(translate(key, language, **escaped))


def translate_list(key: str, language: str | None = None) -> list[str]:
    """Return a localized list of strings (bullet lists in email bodies)."""
    items = _entry(key, language, list)
    return [str(item) for item in items] if items else []
