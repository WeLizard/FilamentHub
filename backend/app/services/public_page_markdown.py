"""Wiki Markdown as plain semantic HTML for readers that do not run JavaScript.

The application renders articles itself; this is the text a search engine or
an AI crawler gets in the first response. It covers what the articles use:
headings, paragraphs, lists, tables, quotes, code, images and links. Every
piece of text is escaped first, and only http(s), site-root and article-slug
links become links, so stored content cannot inject markup.
"""

import re
from collections.abc import Callable
from html import escape

_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
_ORDERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_QUOTE = re.compile(r"^\s*>\s?(.*)$")
_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_DIVIDER = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")
_IMAGE_LINE = re.compile(r"^\s*!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)\s*$")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+&quot;.*?&quot;)?\)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;.*?&quot;)?\)")
_CODE = re.compile(r"`([^`]+)`")
_STRONG = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_EMPHASIS = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])|(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)")
_ARTICLE_SLUG = re.compile(r"^[a-z0-9-]+(?:#[\w-]+)?$")

ArticleHref = Callable[[str], str]


def _safe_href(raw: str, article_href: ArticleHref) -> str | None:
    href = raw.replace("&amp;", "&")
    if href.startswith(("https://", "http://", "/", "#")):
        return href
    if _ARTICLE_SLUG.match(href):
        return article_href(href)
    return None


def _inline(text: str, article_href: ArticleHref) -> str:
    """Escape one line of Markdown and turn its inline marks into HTML."""
    codes: list[str] = []

    def keep_code(match: re.Match[str]) -> str:
        codes.append(f"<code>{match.group(1)}</code>")
        return f"\x00{len(codes) - 1}\x00"

    html = _CODE.sub(keep_code, escape(text, quote=True))
    html = _IMAGE.sub(lambda m: m.group(1), html)

    def link(match: re.Match[str]) -> str:
        href = _safe_href(match.group(2), article_href)
        if href is None:
            return match.group(1)
        rel = ' rel="nofollow noopener"' if href.startswith("http") else ""
        return f'<a href="{escape(href, quote=True)}"{rel}>{match.group(1)}</a>'

    html = _LINK.sub(link, html)
    html = _STRONG.sub(lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>", html)
    html = _EMPHASIS.sub(lambda m: f"<em>{m.group(1) or m.group(2)}</em>", html)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], html)


def _cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def first_image(markdown: str) -> str | None:
    """The address of the first picture in an article, for social previews."""
    for line in markdown.splitlines():
        match = _IMAGE_LINE.match(line)
        if match and match.group(2).startswith(("https://", "/")):
            return match.group(2)
    return None


def render_markdown(markdown: str, article_href: ArticleHref) -> str:
    """Render article Markdown as escaped semantic HTML."""
    lines = markdown.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    paragraph: list[str] = []
    index = 0

    def flush() -> None:
        if paragraph:
            out.append(f"<p>{_inline(' '.join(paragraph), article_href)}</p>")
            paragraph.clear()

    while index < len(lines):
        line = lines[index]
        if not line.strip():
            flush()
            index += 1
            continue
        if _FENCE.match(line):
            flush()
            fence = _FENCE.match(line).group(1)  # type: ignore[union-attr]
            code: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith(fence):
                code.append(lines[index])
                index += 1
            out.append(f"<pre><code>{escape(chr(10).join(code))}</code></pre>")
            index += 1
            continue
        heading = _HEADING.match(line)
        if heading:
            flush()
            level = max(2, len(heading.group(1)))
            out.append(f"<h{level}>{_inline(heading.group(2), article_href)}</h{level}>")
            index += 1
            continue
        if _RULE.match(line):
            flush()
            out.append("<hr>")
            index += 1
            continue
        image = _IMAGE_LINE.match(line)
        if image:
            flush()
            src = image.group(2)
            if src.startswith(("https://", "/")):
                out.append(
                    f'<figure><img src="{escape(src, quote=True)}" '
                    f'alt="{escape(image.group(1), quote=True)}" loading="lazy"></figure>'
                )
            index += 1
            continue
        if _TABLE_ROW.match(line):
            flush()
            rows: list[str] = []
            while index < len(lines) and _TABLE_ROW.match(lines[index]):
                rows.append(lines[index])
                index += 1
            head: list[str] = []
            if len(rows) > 1 and _TABLE_DIVIDER.match(rows[1]):
                head = _cells(rows[0])
                rows = rows[2:]
            table = ["<table>"]
            if head:
                table.append(
                    "<thead><tr>"
                    + "".join(f"<th>{_inline(cell, article_href)}</th>" for cell in head)
                    + "</tr></thead>"
                )
            table.append("<tbody>")
            for row in rows:
                table.append(
                    "<tr>"
                    + "".join(f"<td>{_inline(cell, article_href)}</td>" for cell in _cells(row))
                    + "</tr>"
                )
            table.append("</tbody></table>")
            out.append("".join(table))
            continue
        for pattern, tag in ((_BULLET, "ul"), (_ORDERED, "ol")):
            if pattern.match(line):
                flush()
                items: list[str] = []
                while index < len(lines):
                    match = pattern.match(lines[index])
                    if match:
                        items.append(match.group(1))
                    elif lines[index].startswith((" ", "\t")) and lines[index].strip() and items:
                        # A continuation line or a nested item belongs to the last item.
                        items[-1] += " " + re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", lines[index])
                    else:
                        break
                    index += 1
                out.append(
                    f"<{tag}>"
                    + "".join(f"<li>{_inline(item, article_href)}</li>" for item in items)
                    + f"</{tag}>"
                )
                break
        else:
            quote = _QUOTE.match(line)
            if quote:
                flush()
                quoted: list[str] = []
                while index < len(lines) and _QUOTE.match(lines[index]):
                    quoted.append(_QUOTE.match(lines[index]).group(1))  # type: ignore[union-attr]
                    index += 1
                out.append(f"<blockquote><p>{_inline(' '.join(quoted), article_href)}</p></blockquote>")
                continue
            paragraph.append(line.strip())
            index += 1
    flush()
    return "".join(out)
