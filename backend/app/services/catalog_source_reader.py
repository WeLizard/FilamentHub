"""Bounded, policy-aware collection of public manufacturer catalog pages.

Page bodies are parsed in memory and are never persisted. This module collects
source structure only; it deliberately makes no product or material decisions.
"""

from __future__ import annotations

import asyncio
import codecs
import dataclasses
import io
import ipaddress
import logging
import re
import socket
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Awaitable, Callable
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = "FilamentHubCatalogResearch/1.0"
MAX_PAGES = 120
MAX_SITEMAPS = 8
MAX_DISCOVERED_URLS = MAX_PAGES * 25
MAX_BODY_BYTES = 1_500_000
# Datasheets are bigger than pages. Only quote verification reads them; a crawl never does.
MAX_PDF_BYTES = 10_000_000
MAX_PDF_PAGES = 200
MAX_PDF_TEXT_CHARS = 2_000_000
PDF_EXTRACTION_TIMEOUT_SECONDS = 30.0
MAX_IMAGES_PER_PAGE = 100
MAX_REDIRECTS = 5
# A readable robots policy is trusted for an hour; a failed read is retried soon.
ROBOTS_TTL_SECONDS = 3600.0
ROBOTS_ERROR_TTL_SECONDS = 120.0
DEFAULT_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 30.0
_ARCHIVE_TERMS = ("archive", "archived", "discontinued", "obsolete", "архив", "снят", "снятые")
_NON_PAGE_SUFFIXES = (
    ".pdf",
    ".zip",
    ".rar",
    ".7z",
    ".gz",
    ".tar",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
)


@dataclass(frozen=True)
class SourceLink:
    text: str
    url: str


@dataclass(frozen=True)
class SourceTable:
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class SourceImage:
    url: str
    alt: str
    title: str
    link_url: str | None = None
    link_text: str = ""


@dataclass(frozen=True)
class SourcePage:
    url: str
    title: str
    headings: tuple[str, ...]
    text: str
    links: tuple[SourceLink, ...]
    tables: tuple[SourceTable, ...]
    images: tuple[SourceImage, ...] = ()
    image_count: int = 0
    images_truncated: bool = False


@dataclass(frozen=True)
class SinglePageResult:
    """One page, or the reason it could not be read."""

    page: SourcePage | None
    reason: str | None


@dataclass
class CrawlManifest:
    visited: list[str] = field(default_factory=list)
    discovered: list[str] = field(default_factory=list)
    blocked: list[dict[str, str]] = field(default_factory=list)
    archive_candidates: list[str] = field(default_factory=list)
    partial: bool = False


@dataclass(frozen=True)
class SourceReadResult:
    pages: tuple[SourcePage, ...]
    manifest: CrawlManifest

    def model_dump(self) -> dict[str, object]:
        """Return a JSON-compatible in-memory payload for the compiler layer."""
        return dataclasses.asdict(self)


def extract_pdf_text(body: bytes) -> tuple[str | None, str | None]:
    """Text of a PDF as ``(text, None)``, or ``(None, reason)`` when it cannot be read.

    CPU-bound and written for a worker thread. Encrypted files (unless they open with
    an empty password), broken files and image-only scans give a reason, never raise.
    """
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(body), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            return None, "pdf_encrypted"
        parts: list[str] = []
        size = 0
        for page in reader.pages[:MAX_PDF_PAGES]:
            text = page.extract_text() or ""
            parts.append(text)
            size += len(text)
            if size > MAX_PDF_TEXT_CHARS:
                break
    except Exception as exc:  # noqa: BLE001 - pypdf raises many types on malformed input
        logger.info("PDF text extraction failed: %s", type(exc).__name__)
        return None, "pdf_unreadable"
    text = "\n".join(parts)[:MAX_PDF_TEXT_CHARS]
    return (text, None) if text.strip() else (None, "pdf_no_text")


class _PageParser(HTMLParser):
    """Extract readable page structure while dropping script/style payloads."""

    _DROP = {"script", "style", "noscript", "svg", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.headings: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.images: list[tuple[str, str, str, str | None, str]] = []
        self.image_count = 0
        self.image_refs_truncated = False
        self.tables: list[list[list[str]]] = []
        self._drop_depth = 0
        self._in_title = False
        self._heading: list[str] | None = None
        self._link_href: str | None = None
        self._link_text: list[str] = []
        self._link_title = ""
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        if tag in self._DROP:
            self._drop_depth += 1
            return
        if self._drop_depth:
            return
        if tag == "title":
            self._in_title = True
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._heading = []
        elif tag == "a" and attrs_map.get("href"):
            self._link_href = attrs_map["href"]
            self._link_text = []
            self._link_title = attrs_map.get("title") or ""
        elif tag == "img":
            self.image_count += 1
            raw_sources = [
                attrs_map.get(name)
                for name in ("src", "data-src", "data-lazy-src", "data-original")
            ]
            srcset = attrs_map.get("srcset") or attrs_map.get("data-srcset") or ""
            raw_sources.extend(
                candidate.strip().split()[0] for candidate in srcset.split(",") if candidate.strip()
            )
            for source in raw_sources:
                if not source:
                    continue
                if len(self.images) >= MAX_IMAGES_PER_PAGE * 4:
                    self.image_refs_truncated = True
                    continue
                self.images.append(
                    (
                        source,
                        attrs_map.get("alt") or "",
                        attrs_map.get("title") or "",
                        self._link_href,
                        _join_text(self._link_text) or self._link_title,
                    )
                )
        elif tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in self._DROP and self._drop_depth:
            self._drop_depth -= 1
            return
        if self._drop_depth:
            return
        if tag == "title":
            self._in_title = False
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self._heading is not None:
            value = _join_text(self._heading)
            if value:
                self.headings.append(value)
            self._heading = None
        elif tag == "a" and self._link_href is not None:
            self.links.append((_join_text(self._link_text) or self._link_title, self._link_href))
            self._link_href = None
            self._link_title = ""
        elif tag in {"td", "th"} and self._cell is not None:
            self._row.append(_join_text(self._cell))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None

    def handle_data(self, data: str) -> None:
        if self._drop_depth:
            return
        value = data.strip()
        if not value:
            return
        if self._in_title:
            self.title_parts.append(value)
        self.text_parts.append(value)
        if self._heading is not None:
            self._heading.append(value)
        if self._link_href is not None:
            self._link_text.append(value)
        if self._cell is not None:
            self._cell.append(value)


def _join_text(parts: list[str]) -> str:
    return " ".join(" ".join(parts).split())


def _decode_html(body: bytes, content_type: str) -> str:
    """Honor a site's declared character set before parsing its page text."""
    declared = re.search(r"charset\s*=\s*['\"]?([a-zA-Z0-9._-]+)", content_type, re.I)
    if declared is None:
        declared = re.search(rb"charset\s*=\s*['\"]?([a-zA-Z0-9._-]+)", body[:4096], re.I)
    if declared is not None:
        name = declared.group(1)
        if isinstance(name, bytes):
            name = name.decode("ascii")
        try:
            codecs.lookup(name)
        except LookupError:
            pass
        else:
            return body.decode(name, errors="replace")
    return body.decode("utf-8", errors="replace")


def _canonical_url(url: str) -> str | None:
    """Normalize an HTTP(S) URL and reject credentials, IPs and local hosts."""
    try:
        if any(char in url for char in ('"', "'", "<", ">")) or any(ord(char) < 32 for char in url):
            return None
        parts = urlsplit(url.strip())
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            return None
        if parts.username is not None or parts.password is not None:
            return None
        host = parts.hostname.rstrip(".").lower()
        try:
            ipaddress.ip_address(host)
            return None
        except ValueError:
            pass
        if host in {"localhost", "localhost.localdomain"} or "." not in host:
            return None
        port = parts.port
        netloc = (
            host
            if port is None
            or (parts.scheme == "https" and port == 443)
            or (parts.scheme == "http" and port == 80)
            else f"{host}:{port}"
        )
        path = parts.path or "/"
        return urldefrag(urlunsplit((parts.scheme.lower(), netloc, path, parts.query, ""))).url
    except (ValueError, UnicodeError):
        return None


def _same_origin(candidate: str, origin: str, *, www_alias: bool = False) -> bool:
    left, right = urlsplit(candidate), urlsplit(origin)
    if www_alias:
        # ``www.maker.example`` and ``maker.example`` are the same site.
        hosts = ((host or "").removeprefix("www.") for host in (left.hostname, right.hostname))
        return (left.scheme, left.port) == (right.scheme, right.port) and len(set(hosts)) == 1
    return (left.scheme, left.hostname, left.port) == (right.scheme, right.hostname, right.port)


async def _resolve_public(host: str, port: int) -> set[str]:
    try:
        records = await asyncio.get_running_loop().getaddrinfo(
            host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
        )
    except OSError:
        return set()
    addresses = {record[4][0] for record in records}
    try:
        if not addresses or not all(ipaddress.ip_address(value).is_global for value in addresses):
            return set()
    except ValueError:
        return set()
    return addresses


class CatalogSourceReader:
    """Read a bounded same-origin set of HTML pages and discover sitemap URLs.

    A caller may inject an AsyncClient, resolver and sleep function for tests.
    The provided client is not closed by this service.
    """

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        resolver: Callable[[str, int], Awaitable[set[str]]] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        max_pages: int = MAX_PAGES,
        max_sitemaps: int = MAX_SITEMAPS,
        default_delay: float = DEFAULT_DELAY_SECONDS,
        www_alias: bool = False,
    ) -> None:
        if max_pages < 1 or max_pages > MAX_PAGES:
            raise ValueError(f"max_pages must be between 1 and {MAX_PAGES}")
        if max_sitemaps < 1 or max_sitemaps > MAX_SITEMAPS:
            raise ValueError(f"max_sitemaps must be between 1 and {MAX_SITEMAPS}")
        self._client = client
        self._owns_client = client is None
        self._resolver = resolver or _resolve_public
        self._sleep = sleep
        self.max_pages = max_pages
        self.max_sitemaps = max_sitemaps
        self.default_delay = min(max(default_delay, 0.0), MAX_DELAY_SECONDS)
        self._request_delay = self.default_delay
        self._last_request_at = 0.0
        self._robots: dict[str, tuple[RobotFileParser, bool, float]] = {}
        self._robots_clock = time.monotonic
        self._www_alias = www_alias

    async def read(self, start_url: str) -> SourceReadResult:
        start = _canonical_url(start_url)
        if not start:
            raise ValueError("start_url must be a public HTTP(S) hostname without credentials")
        origin = start
        manifest = CrawlManifest(discovered=[start])
        pages: list[SourcePage] = []
        queue = [start]
        seen: set[str] = set()
        parser = RobotFileParser()
        robots_loaded = False
        sitemaps: list[str] = []
        sitemap_candidates: list[str] = []

        client = self._client or self._make_client()
        try:
            robots_url = urljoin(origin, "/robots.txt")
            try:
                robots_body, robots_final, _ = await self._fetch(
                    client, robots_url, origin, manifest
                )
                if robots_body is not None:
                    parser.set_url(robots_final)
                    parser.parse(robots_body.decode("utf-8", errors="replace").splitlines())
                    robots_loaded = True
                    sitemaps.extend(
                        self._robots_sitemaps(
                            robots_body.decode("utf-8", errors="replace"), origin, manifest
                        )
                    )
                    crawl_delay = parser.crawl_delay(USER_AGENT) or parser.crawl_delay("*")
                    if crawl_delay is not None:
                        self._request_delay = min(max(float(crawl_delay), 0.0), MAX_DELAY_SECONDS)
                elif not any(
                    entry["url"] == robots_url and entry["reason"] == "http_404"
                    for entry in manifest.blocked
                ):
                    parser.parse(["User-agent: *", "Disallow: /"])
                    robots_loaded = True
            except httpx.HTTPError:
                manifest.blocked.append({"url": robots_url, "reason": "robots_unavailable"})
                parser.parse(["User-agent: *", "Disallow: /"])
                robots_loaded = True

            sitemap_queue = sitemaps + [urljoin(origin, "/sitemap.xml")]
            sitemap_seen: set[str] = set()
            while sitemap_queue and len(sitemap_seen) < self.max_sitemaps:
                candidate = _canonical_url(sitemap_queue.pop(0))
                if not candidate or candidate in sitemap_seen:
                    continue
                if not _same_origin(candidate, origin):
                    manifest.blocked.append({"url": candidate, "reason": "cross_origin"})
                    continue
                sitemap_seen.add(candidate)
                if robots_loaded and not parser.can_fetch(USER_AGENT, candidate):
                    manifest.blocked.append({"url": candidate, "reason": "robots_disallowed"})
                    continue
                try:
                    body, final, content_type = await self._fetch(
                        client, candidate, origin, manifest
                    )
                except httpx.HTTPError:
                    continue
                if body is None:
                    continue
                if "xml" not in content_type and not body.lstrip().startswith(b"<"):
                    continue
                urls, nested = self._parse_sitemap(body, final, origin, manifest)
                for url in urls:
                    if url not in sitemap_candidates:
                        sitemap_candidates.append(url)
                        if url not in manifest.discovered:
                            if len(manifest.discovered) >= MAX_DISCOVERED_URLS:
                                manifest.blocked.append({"url": url, "reason": "discovery_limit"})
                            else:
                                manifest.discovered.append(url)
                        if any(term in url.casefold() for term in _ARCHIVE_TERMS):
                            if url not in manifest.archive_candidates:
                                manifest.archive_candidates.append(url)
                sitemap_queue.extend(nested)
            if sitemap_queue:
                manifest.partial = True
                manifest.blocked.extend(
                    {"url": url, "reason": "sitemap_limit"} for url in sitemap_queue
                )

            while queue and len(pages) < self.max_pages:
                url = queue.pop(0)
                if url in seen:
                    continue
                seen.add(url)
                if robots_loaded and not parser.can_fetch(USER_AGENT, url):
                    manifest.blocked.append({"url": url, "reason": "robots_disallowed"})
                    continue
                try:
                    body, final_url, content_type = await self._fetch(client, url, origin, manifest)
                except httpx.HTTPError as exc:
                    logger.info("Catalog source request failed for %s: %s", url, type(exc).__name__)
                    continue
                if body is None:
                    continue
                if "html" not in content_type and not body.lstrip().lower().startswith(
                    (b"<!doctype html", b"<html")
                ):
                    manifest.blocked.append({"url": final_url, "reason": "non_html"})
                    continue
                page = self._parse_page(final_url, body, content_type, origin, manifest, queue)
                pages.append(page)
            # Sitemap-only pages are fallbacks; prioritize the navigational graph
            # exposed from the supplied seed and pages already reached.
            for url in sitemap_candidates:
                if len(pages) >= self.max_pages:
                    break
                if url not in seen:
                    queue.append(url)
                while queue and len(pages) < self.max_pages:
                    candidate = queue.pop(0)
                    if candidate in seen:
                        continue
                    seen.add(candidate)
                    if robots_loaded and not parser.can_fetch(USER_AGENT, candidate):
                        manifest.blocked.append({"url": candidate, "reason": "robots_disallowed"})
                        continue
                    try:
                        body, final_url, content_type = await self._fetch(
                            client, candidate, origin, manifest
                        )
                    except httpx.HTTPError as exc:
                        logger.info(
                            "Catalog source request failed for %s: %s",
                            candidate,
                            type(exc).__name__,
                        )
                        continue
                    if body is None:
                        continue
                    if "html" not in content_type and not body.lstrip().lower().startswith(
                        (b"<!doctype html", b"<html")
                    ):
                        manifest.blocked.append({"url": final_url, "reason": "non_html"})
                        continue
                    page = self._parse_page(final_url, body, content_type, origin, manifest, queue)
                    pages.append(page)
            remaining = [url for url in queue if url not in seen]
            remaining.extend(url for url in sitemap_candidates if url not in seen)
            if remaining:
                manifest.partial = True
                for url in remaining:
                    manifest.blocked.append({"url": url, "reason": "page_limit"})
        finally:
            if self._owns_client:
                await client.aclose()
        return SourceReadResult(tuple(pages), manifest)

    @staticmethod
    def _make_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            follow_redirects=False,
            trust_env=False,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.1",
            },
        )

    async def read_page(self, url: str) -> SinglePageResult:
        """Read exactly one page under the same public-address and robots rules.

        Nothing else on the site is requested besides ``robots.txt`` (cached per
        origin on this instance). A page that cannot be read yields the reason it
        was blocked instead of raising, so callers can tell a transient failure
        from a permanent refusal.
        """
        canonical = _canonical_url(url)
        if not canonical:
            return SinglePageResult(None, "unsafe_url")
        manifest = CrawlManifest()
        origin_key = "{0.scheme}://{0.netloc}".format(urlsplit(canonical))
        client = self._client or self._make_client()
        try:
            cached = self._robots.get(origin_key)
            if cached is not None and self._robots_clock() - cached[2] > (
                ROBOTS_ERROR_TTL_SECONDS if cached[1] else ROBOTS_TTL_SECONDS
            ):
                cached = None
            if cached is None:
                loaded = await self._load_robots(client, canonical, manifest)
                cached = (*loaded, self._robots_clock())
                self._robots[origin_key] = cached
            parser, robots_error, _ = cached
            if not parser.can_fetch(USER_AGENT, canonical):
                return SinglePageResult(
                    None, "robots_unavailable" if robots_error else "robots_disallowed"
                )
            try:
                body, final_url, content_type = await self._fetch(
                    client, canonical, canonical, manifest, allow_pdf=True
                )
            except httpx.HTTPError as exc:
                logger.info(
                    "Catalog source request failed for %s: %s", canonical, type(exc).__name__
                )
                return SinglePageResult(None, "fetch_error")
            if body is None:
                reason = manifest.blocked[-1]["reason"] if manifest.blocked else "unavailable"
                return SinglePageResult(None, reason)
            if body.startswith(b"%PDF-"):
                return await self._read_pdf(final_url, body)
            if "html" not in content_type and not body.lstrip().lower().startswith(
                (b"<!doctype html", b"<html")
            ):
                return SinglePageResult(None, "non_html")
            # Parsing a large page is CPU work: keep it off the event loop.
            page = await asyncio.to_thread(
                self._parse_page, final_url, body, content_type, canonical, manifest, []
            )
            return SinglePageResult(page, None)
        finally:
            if self._owns_client:
                await client.aclose()

    @staticmethod
    async def _read_pdf(url: str, body: bytes) -> SinglePageResult:
        """Extract a datasheet's text off the event loop, within a time limit."""
        try:
            text, reason = await asyncio.wait_for(
                asyncio.to_thread(extract_pdf_text, body), PDF_EXTRACTION_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            return SinglePageResult(None, "pdf_timeout")
        if text is None:
            return SinglePageResult(None, reason)
        return SinglePageResult(SourcePage(url, "", (), text, (), ()), None)

    async def _load_robots(
        self, client: httpx.AsyncClient, origin: str, manifest: CrawlManifest
    ) -> tuple[RobotFileParser, bool]:
        """Return the origin's robots policy and whether it was unreadable (deny-all)."""
        parser = RobotFileParser()
        robots_url = urljoin(origin, "/robots.txt")
        try:
            body, final, _ = await self._fetch(client, robots_url, origin, manifest)
        except httpx.HTTPError:
            parser.parse(["User-agent: *", "Disallow: /"])
            return parser, True
        if body is not None:
            parser.set_url(final)
            parser.parse(body.decode("utf-8", errors="replace").splitlines())
            crawl_delay = parser.crawl_delay(USER_AGENT) or parser.crawl_delay("*")
            if crawl_delay is not None:
                self._request_delay = min(max(float(crawl_delay), 0.0), MAX_DELAY_SECONDS)
            return parser, False
        # A redirected robots.txt (www to the bare host) reports its final address.
        if any(
            entry["reason"] == "http_404" and urlsplit(entry["url"]).path == "/robots.txt"
            for entry in manifest.blocked
        ):
            parser.parse([])  # no robots.txt: everything may be fetched
            return parser, False
        parser.parse(["User-agent: *", "Disallow: /"])
        return parser, True

    async def _fetch(
        self,
        client: httpx.AsyncClient,
        url: str,
        origin: str,
        manifest: CrawlManifest,
        *,
        allow_pdf: bool = False,
    ) -> tuple[bytes | None, str, str]:
        current = _canonical_url(url)
        if not current:
            manifest.blocked.append({"url": url, "reason": "unsafe_url"})
            return None, url, ""
        for redirect_count in range(MAX_REDIRECTS + 1):
            if not _same_origin(current, origin, www_alias=self._www_alias):
                manifest.blocked.append({"url": current, "reason": "cross_origin"})
                return None, current, ""
            parts = urlsplit(current)
            resolved = await self._resolver(
                parts.hostname or "", parts.port or (443 if parts.scheme == "https" else 80)
            )
            if not resolved:
                manifest.blocked.append({"url": current, "reason": "non_public_or_unresolved_host"})
                return None, current, ""
            elapsed = time.monotonic() - self._last_request_at
            if self._last_request_at and elapsed < self._request_delay:
                await self._sleep(self._request_delay - elapsed)
            async with client.stream("GET", current, follow_redirects=False) as response:
                self._last_request_at = time.monotonic()
                connected = response.extensions.get("network_stream")
                stream = connected.get_extra_info("server_addr") if connected else None
                peer_ip = stream[0] if stream else None
                if peer_ip is None and self._owns_client:
                    manifest.blocked.append({"url": current, "reason": "peer_address_unavailable"})
                    return None, current, ""
                if peer_ip and (
                    peer_ip not in resolved or not ipaddress.ip_address(peer_ip).is_global
                ):
                    manifest.blocked.append({"url": current, "reason": "unexpected_peer_address"})
                    return None, current, ""
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location or redirect_count >= MAX_REDIRECTS:
                        manifest.blocked.append({"url": current, "reason": "redirect_limit"})
                        return None, current, ""
                    next_url = _canonical_url(urljoin(current, location))
                    if not next_url or not _same_origin(
                        next_url, origin, www_alias=self._www_alias
                    ):
                        manifest.blocked.append(
                            {"url": location, "reason": "cross_origin_redirect"}
                        )
                        return None, current, ""
                    current = next_url
                    continue
                if response.status_code != 200:
                    manifest.blocked.append(
                        {"url": current, "reason": f"http_{response.status_code}"}
                    )
                    return None, current, response.headers.get("content-type", "")
                content_type = response.headers.get("content-type", "").lower()
                is_pdf = allow_pdf and (
                    "application/pdf" in content_type
                    or urlsplit(current).path.lower().endswith(".pdf")
                )
                if not is_pdf and any(
                    urlsplit(current).path.lower().endswith(suffix) for suffix in _NON_PAGE_SUFFIXES
                ):
                    manifest.blocked.append({"url": current, "reason": "non_page_resource"})
                    return None, current, content_type
                limit = MAX_PDF_BYTES if is_pdf else MAX_BODY_BYTES
                declared = response.headers.get("content-length", "")
                if declared.isdigit() and int(declared) > limit:
                    manifest.blocked.append({"url": current, "reason": "body_limit"})
                    return None, current, content_type
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > limit:
                        manifest.blocked.append({"url": current, "reason": "body_limit"})
                        return None, current, content_type
                return bytes(body), current, content_type
        return None, current, ""

    @staticmethod
    def _robots_sitemaps(text: str, origin: str, manifest: CrawlManifest) -> list[str]:
        result = []
        for line in text.splitlines():
            key, sep, value = line.partition(":")
            if sep and key.strip().lower() == "sitemap":
                url = _canonical_url(urljoin(origin, value.strip()))
                if url and _same_origin(url, origin):
                    result.append(url)
                elif value.strip():
                    manifest.blocked.append(
                        {"url": value.strip(), "reason": "unsafe_sitemap_location"}
                    )
        return result

    @staticmethod
    def _parse_sitemap(
        body: bytes, base_url: str, origin: str, manifest: CrawlManifest
    ) -> tuple[list[str], list[str]]:
        if b"<!doctype" in body[:4096].lower() or b"<!entity" in body[:4096].lower():
            manifest.blocked.append({"url": base_url, "reason": "unsafe_sitemap_markup"})
            return [], []
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            manifest.blocked.append({"url": base_url, "reason": "invalid_sitemap"})
            return [], []
        locs = [
            element.text.strip()
            for element in root.iter()
            if element.tag.rsplit("}", 1)[-1] == "loc" and element.text
        ]
        nested: list[str] = []
        pages: list[str] = []
        is_index = root.tag.rsplit("}", 1)[-1] == "sitemapindex"
        for loc in locs:
            absolute = _canonical_url(urljoin(base_url, loc))
            if not absolute or not _same_origin(absolute, origin):
                manifest.blocked.append({"url": loc, "reason": "unsafe_sitemap_entry"})
            elif is_index:
                nested.append(absolute)
            elif not any(urlsplit(absolute).path.lower().endswith(s) for s in _NON_PAGE_SUFFIXES):
                pages.append(absolute)
        return pages, nested

    def _discover(self, url: str, origin: str, queue: list[str], manifest: CrawlManifest) -> None:
        canonical = _canonical_url(url)
        if not canonical:
            manifest.blocked.append({"url": url, "reason": "unsafe_url"})
        elif not _same_origin(canonical, origin):
            manifest.blocked.append({"url": canonical, "reason": "cross_origin"})
        elif any(
            urlsplit(canonical).path.lower().endswith(suffix) for suffix in _NON_PAGE_SUFFIXES
        ):
            manifest.blocked.append({"url": canonical, "reason": "non_page_resource"})
        else:
            if canonical not in manifest.discovered:
                if len(manifest.discovered) >= MAX_DISCOVERED_URLS:
                    manifest.blocked.append({"url": canonical, "reason": "discovery_limit"})
                    return
                manifest.discovered.append(canonical)
            if canonical not in queue:
                queue.append(canonical)

    def _parse_page(
        self,
        url: str,
        body: bytes,
        content_type: str,
        origin: str,
        manifest: CrawlManifest,
        queue: list[str],
    ) -> SourcePage:
        parser = _PageParser()
        parser.feed(_decode_html(body, content_type))
        parser.close()
        links: list[SourceLink] = []
        for text, href in parser.links:
            target = _canonical_url(urljoin(url, href))
            if target:
                links.append(SourceLink(text, target))
                self._discover(target, origin, queue, manifest)
                if any(term in f"{text} {target}".casefold() for term in _ARCHIVE_TERMS):
                    if target not in manifest.archive_candidates:
                        manifest.archive_candidates.append(target)
            elif href:
                manifest.blocked.append({"url": href, "reason": "unsafe_link"})
        images: list[SourceImage] = []
        image_urls: set[str] = set()
        for src, alt, title, link_href, link_text in parser.images:
            if len(src) > 2048:
                continue
            image_url = _canonical_url(urljoin(url, src))
            if not image_url or image_url in image_urls:
                continue
            image_urls.add(image_url)
            if len(images) >= MAX_IMAGES_PER_PAGE:
                continue
            link_url = _canonical_url(urljoin(url, link_href)) if link_href else None
            images.append(
                SourceImage(
                    url=image_url,
                    alt=" ".join(alt.split())[:500],
                    title=" ".join(title.split())[:500],
                    link_url=link_url,
                    link_text=" ".join(link_text.split())[:500],
                )
            )
        tables = tuple(
            SourceTable(tuple(tuple(cell for cell in row) for row in table))
            for table in parser.tables
        )
        if url not in manifest.visited:
            manifest.visited.append(url)
        return SourcePage(
            url=url,
            title=_join_text(parser.title_parts),
            headings=tuple(parser.headings),
            text=_join_text(parser.text_parts),
            links=tuple(links),
            tables=tables,
            images=tuple(images),
            image_count=len(image_urls),
            images_truncated=(len(image_urls) > MAX_IMAGES_PER_PAGE or parser.image_refs_truncated),
        )


async def read_catalog_sources(start_url: str, **kwargs: object) -> SourceReadResult:
    """Convenience API for one bounded source-reading run."""
    return await CatalogSourceReader(**kwargs).read(start_url)


async def read_source_site(
    seed_urls: list[str], *, max_pages: int = MAX_PAGES, **reader_options: object
) -> SourceReadResult:
    """Read one or more explicitly supplied official entry points.

    Each seed is crawled independently with same-origin navigation. No links
    discovered from one seed may cause a fetch on another hostname. The total
    number of returned HTML pages is capped by ``max_pages``.
    """
    if not seed_urls:
        raise ValueError("at least one official seed URL is required")
    if len(seed_urls) > MAX_PAGES:
        raise ValueError(f"at most {MAX_PAGES} official seed URLs are allowed")
    if max_pages < 1 or max_pages > MAX_PAGES:
        raise ValueError(f"max_pages must be between 1 and {MAX_PAGES}")
    all_pages: list[SourcePage] = []
    page_urls: set[str] = set()
    combined = CrawlManifest()
    for index, seed in enumerate(seed_urls):
        canonical_seed = _canonical_url(seed)
        if canonical_seed in page_urls:
            continue
        # Keep one slot for every remaining explicit entry point. A broad
        # first site must not consume the entire budget before other seeds.
        remaining = max_pages - len(all_pages) - (len(seed_urls) - index - 1)
        if remaining <= 0:
            combined.partial = True
            combined.blocked.extend(
                {"url": url, "reason": "page_limit"} for url in seed_urls[index:]
            )
            break
        run = await CatalogSourceReader(max_pages=remaining, **reader_options).read(seed)
        for page in run.pages:
            if page.url not in page_urls:
                all_pages.append(page)
                page_urls.add(page.url)
        combined.partial = combined.partial or run.manifest.partial
        combined.visited.extend(url for url in run.manifest.visited if url not in combined.visited)
        combined.discovered.extend(
            url for url in run.manifest.discovered if url not in combined.discovered
        )
        combined.blocked.extend(run.manifest.blocked)
        combined.archive_candidates.extend(
            url for url in run.manifest.archive_candidates if url not in combined.archive_candidates
        )
    return SourceReadResult(tuple(all_pages), combined)
