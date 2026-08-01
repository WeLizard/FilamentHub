"""Pure helpers for turning Wiki Markdown into article metadata."""

import html
import re

DERIVED_SUMMARY_MAX_LENGTH = 280
EXPLICIT_SUMMARY_MAX_LENGTH = 1000

_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
_IMAGE_ONLY_RE = re.compile(r"^\s*!\[[^\]]*\]\([^)]*\)\s*$")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")
_TABLE_DIVIDER_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*$")
_THEMATIC_BREAK_RE = re.compile(r"^\s{0,3}(?:[-*_]\s*){3,}$")


def markdown_inline_to_plain_text(value: str) -> str:
    """Remove common inline Markdown while preserving readable link labels."""
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", "", value)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\[[^\]]*\]", r"\1", text)
    text = re.sub(r"<((?:https?://|mailto:)[^>]+)>", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"(?<!\\)[*_~]+", "", text)
    text = re.sub(r"^\s{0,3}>\s?", "", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s+", "", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _truncate_at_word_boundary(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    shortened = value[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    if not shortened:
        shortened = value[:limit].rstrip()
    return f"{shortened}…"


def _first_prose_paragraph(content: str) -> str:
    paragraph: list[str] = []
    in_fence = False

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            if paragraph:
                break
            continue
        if in_fence:
            continue
        if not line:
            if paragraph:
                break
            continue
        if (
            _HEADING_RE.match(line)
            or _IMAGE_ONLY_RE.match(line)
            or _LIST_ITEM_RE.match(line)
            or _TABLE_DIVIDER_RE.match(line)
            or _THEMATIC_BREAK_RE.match(line)
            or line.startswith("|")
        ):
            if paragraph:
                break
            continue

        plain_line = markdown_inline_to_plain_text(line)
        if plain_line:
            paragraph.append(plain_line)

    return " ".join(paragraph)


def derive_wiki_summary(content: str, explicit_summary: object = None) -> str:
    """Return a plain-text card summary from frontmatter or the first prose paragraph."""
    if isinstance(explicit_summary, str) and explicit_summary.strip():
        return _truncate_at_word_boundary(
            markdown_inline_to_plain_text(explicit_summary),
            EXPLICIT_SUMMARY_MAX_LENGTH,
        )

    paragraph = _first_prose_paragraph(content)
    if not paragraph:
        paragraph = markdown_inline_to_plain_text(content)
    return _truncate_at_word_boundary(paragraph, DERIVED_SUMMARY_MAX_LENGTH)
