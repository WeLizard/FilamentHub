"""Check that a quoted manufacturer statement really appears on the cited page.

Pages are read through the bounded ``CatalogSourceReader`` (public addresses,
size and time limits, robots policy). Their text is held in memory only while the
verdicts are computed; nothing but the verdict and the page hash is kept.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit

from app.services.catalog_quote_claims import (
    IMAGE_ONLY,
    NOT_OFFICIAL_DOMAIN,
    QUOTE_NOT_FOUND,
    QUOTE_TOO_SHORT,
    SOURCE_UNAVAILABLE,
    VALUE_NOT_IN_QUOTE,
    VERIFIED,
    Claim,
    host_domain,
    is_official_host,
)
from app.services.catalog_quote_matching import (
    contains_text,
    has_numbers,
    normalize_text,
    number_present,
    numbers_present,
    quote_long_enough,
    squash,
    text_present,
    words_present,
)
from app.services.catalog_source_reader import CatalogSourceReader, SourcePage, _canonical_url

logger = logging.getLogger(__name__)

GLOBAL_CONCURRENCY = 4
MAX_URLS_PER_CLAIM = 3
MAX_URLS_PER_RUN = 60
PAGE_TIMEOUT_SECONDS = 60.0
VERDICT_CACHE_SECONDS = 600.0
VERDICT_CACHE_MAX = 4000
# No new page read starts after this, so a run stays well inside the job lease
# (crawl delays and slow hosts could otherwise stretch 60 reads past it).
RUN_BUDGET_SECONDS = 600.0

# A refusal that retrying cannot change. Everything else that stops a read
# (timeouts, 5xx, 429, an unreadable robots.txt) is worth another attempt.
_PERMANENT_REASONS = frozenset(
    {
        "robots_disallowed",
        "non_page_resource",
        "non_html",
        "unsafe_url",
        "non_public_or_unresolved_host",
        "unexpected_peer_address",
        "peer_address_unavailable",
        "cross_origin",
        "cross_origin_redirect",
        "redirect_limit",
        "body_limit",
        "pdf_encrypted",
        "pdf_unreadable",
        "pdf_no_text",
        "pdf_timeout",
    }
)


def is_transient_reason(reason: str | None) -> bool:
    if not reason or reason in _PERMANENT_REASONS:
        return False
    # 4xx means the page is gone or refused us; only throttling may pass.
    return not (reason.startswith("http_4") and reason != "http_429")


@dataclass(frozen=True)
class PageText:
    normalized: str | None
    squashed: str = ""
    sha256: str | None = None
    reason: str | None = None
    # Canonical URLs of the images the page shows (and of their full-size links).
    images: frozenset[str] = frozenset()


def build_page_text(page: SourcePage) -> PageText:
    """CPU-bound normalization of a parsed page; run it off the event loop."""
    normalized = normalize_text(page.text)
    images = {
        url
        for image in page.images
        for url in (_canonical_url(image.url), _canonical_url(image.link_url or ""))
        if url
    }
    return PageText(
        normalized,
        squash(normalized),
        hashlib.sha256(normalized.encode()).hexdigest(),
        images=frozenset(images),
    )


@dataclass(frozen=True)
class Verdict:
    status: str
    url: str | None = None
    reason: str | None = None
    page_sha256: str | None = None


# When one claim cites several pages, keep the most informative outcome.
_RANK = {
    IMAGE_ONLY: 5,
    VALUE_NOT_IN_QUOTE: 4,
    SOURCE_UNAVAILABLE: 3,
    QUOTE_NOT_FOUND: 2,
    NOT_OFFICIAL_DOMAIN: 1,
}


def _value_matches(claim: Claim) -> bool:
    quote = claim.quote or ""
    if claim.value_kind == "number":
        return number_present(claim.value, quote)
    if claim.value_kind == "text":
        return text_present(str(claim.value), quote)
    if claim.value_kind == "summary":
        summary = str(claim.value)
        # A paraphrase is checked by its numbers; with none, by its words.
        return numbers_present(summary, quote) if has_numbers(summary) else words_present(summary, quote)
    return True


def evaluate_page(claim: Claim, url: str, page: PageText) -> Verdict:
    """Verdict of one claim against one page (no network, no storage).

    A quote must be on the page and carry the claimed value. An image counts only
    when it is one of this page's own images and is hosted on an official domain;
    even then it is ``image_only``, which an administrator still has to confirm.
    """
    if page.normalized is None:
        return Verdict(SOURCE_UNAVAILABLE, url, page.reason)
    text: Verdict | None = None
    if claim.quote:
        if not contains_text(page.normalized, page.squashed, claim.quote):
            text = Verdict(QUOTE_NOT_FOUND, url, None, page.sha256)
        elif not _value_matches(claim):
            return Verdict(VALUE_NOT_IN_QUOTE, url, None, page.sha256)
        else:
            return Verdict(VERIFIED, url, None, page.sha256)
    if claim.image_url:
        if not is_official_host(claim.image_url, claim.domains):
            return Verdict(NOT_OFFICIAL_DOMAIN, claim.image_url, None, page.sha256)
        if _canonical_url(claim.image_url) in page.images:
            return Verdict(IMAGE_ONLY, url, None, page.sha256)
    return text or Verdict(QUOTE_NOT_FOUND, url, None, page.sha256)


def decide(claim: Claim, pages: dict[str, PageText]) -> Verdict:
    official = [url for url in claim.urls if is_official_host(url, claim.domains)]
    if not official:
        return Verdict(NOT_OFFICIAL_DOMAIN, claim.urls[0])
    if claim.quote and not quote_long_enough(claim.quote):
        return Verdict(QUOTE_TOO_SHORT, official[0])
    best: Verdict | None = None
    for url in official[:MAX_URLS_PER_CLAIM]:
        verdict = evaluate_page(claim, url, pages[url])
        if verdict.status == VERIFIED:
            return verdict
        if best is None or _RANK[verdict.status] > _RANK[best.status]:
            best = verdict
    assert best is not None
    return best


def pages_to_fetch(claims: Iterable[Claim]) -> list[str]:
    """Distinct official pages a set of claims needs, in first-use order."""
    urls: dict[str, None] = {}
    for claim in claims:
        if claim.quote and not quote_long_enough(claim.quote):
            continue
        official = [url for url in claim.urls if is_official_host(url, claim.domains)]
        for url in official[:MAX_URLS_PER_CLAIM]:
            urls.setdefault(url)
    return list(urls)


class _HostGate:
    def __init__(self, reader: Any) -> None:
        self.reader = reader
        self.lock = asyncio.Lock()


class QuoteVerifier:
    """Fetches the needed pages once each and turns claims into verdicts.

    At most one request per host runs at a time, and at most
    ``GLOBAL_CONCURRENCY`` across hosts, in this process.
    """

    def __init__(
        self,
        *,
        reader_factory: Callable[[], Any] | None = None,
        concurrency: int = GLOBAL_CONCURRENCY,
        clock: Callable[[], float] = time.monotonic,
        run_budget: float = RUN_BUDGET_SECONDS,
    ) -> None:
        self._reader_factory = reader_factory or partial(CatalogSourceReader, www_alias=True)
        self._semaphore = asyncio.Semaphore(concurrency)
        self._hosts: dict[str, _HostGate] = {}
        self._clock = clock
        self._run_budget = run_budget
        self._cache: dict[str, tuple[float, Verdict]] = {}

    def _cache_key(self, claim: Claim) -> str:
        return hashlib.sha256(
            repr(
                (
                    sorted(url for url in claim.urls if is_official_host(url, claim.domains)),
                    claim.quote,
                    claim.image_url,
                    claim.value_kind,
                    claim.value,
                )
            ).encode()
        ).hexdigest()

    def _cached(self, claim: Claim) -> Verdict | None:
        entry = self._cache.get(self._cache_key(claim))
        if entry is None or self._clock() - entry[0] > VERDICT_CACHE_SECONDS:
            return None
        return entry[1]

    def _remember(self, claim: Claim, verdict: Verdict) -> None:
        # A failed read is never remembered: the next run should try the page again.
        if verdict.status == SOURCE_UNAVAILABLE:
            return
        if len(self._cache) >= VERDICT_CACHE_MAX:
            self._cache.clear()
        self._cache[self._cache_key(claim)] = (self._clock(), verdict)

    async def _read(self, url: str, deadline: float) -> PageText:
        # One gate per site: ``www.maker.example`` and ``maker.example`` share a server.
        host = host_domain(url) or (urlsplit(url).hostname or "").lower()
        gate = self._hosts.get(host)
        if gate is None:
            gate = self._hosts[host] = _HostGate(self._reader_factory())
        try:
            async with gate.lock, self._semaphore:
                if self._clock() > deadline:
                    return PageText(None, reason="run_budget")
                result = await asyncio.wait_for(gate.reader.read_page(url), PAGE_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            return PageText(None, reason="timeout")
        except Exception:  # noqa: BLE001 - one unreadable page must not stop the run
            logger.warning("Quote verification could not read %s", host, exc_info=True)
            return PageText(None, reason="fetch_error")
        if result.page is None:
            return PageText(None, reason=(result.reason or "unavailable")[:64])
        return await asyncio.to_thread(build_page_text, result.page)

    async def verify(self, claims: list[Claim]) -> dict[tuple[str, str, str, str], Verdict]:
        verdicts: dict[tuple[str, str, str, str], Verdict] = {}
        pending: list[Claim] = []
        for claim in claims:
            cached = self._cached(claim)
            if cached is not None:
                verdicts[claim.identity] = cached
            else:
                pending.append(claim)
        urls = pages_to_fetch(pending)
        pages: dict[str, PageText] = {}
        for url in urls[MAX_URLS_PER_RUN:]:
            pages[url] = PageText(None, reason="job_url_limit")
        batch = urls[:MAX_URLS_PER_RUN]
        deadline = self._clock() + self._run_budget
        for url, page in zip(
            batch, await asyncio.gather(*(self._read(url, deadline) for url in batch)), strict=True
        ):
            pages[url] = page
        for claim in pending:
            verdict = decide(claim, pages)
            verdicts[claim.identity] = verdict
            self._remember(claim, verdict)
        return verdicts
