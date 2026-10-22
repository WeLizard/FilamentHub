"""Quote claims made by a proposal, and what the server has verified about them.

A claim is one piece of evidence or one manufacturer fact that cites a quote. The
verdicts live in ``catalog_curation_quote_checks``; a verdict only counts while it
matches the claim's current content, so editing a quote or a value after a check
sends the claim back to ``pending``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Brand, CatalogCurationProposal
from app.models.catalog_quote_check import (
    CatalogImageConfirmation,
    CatalogQuoteCheck,
    CatalogQuoteCheckJob,
)
from app.services.catalog_curation_service import SHEETS, row_key
from app.services.catalog_quote_matching import leading_quote

VERIFIED = "verified"
QUOTE_NOT_FOUND = "quote_not_found"
VALUE_NOT_IN_QUOTE = "value_not_in_quote"
SOURCE_UNAVAILABLE = "source_unavailable"
IMAGE_ONLY = "image_only"
NOT_OFFICIAL_DOMAIN = "not_official_domain"
QUOTE_TOO_SHORT = "quote_too_short"
PENDING = "pending"

STORED_STATUSES = (
    VERIFIED,
    QUOTE_NOT_FOUND,
    VALUE_NOT_IN_QUOTE,
    SOURCE_UNAVAILABLE,
    IMAGE_ONLY,
    NOT_OFFICIAL_DOMAIN,
    QUOTE_TOO_SHORT,
)
# Only a verified quote passes by itself. ``image_only`` passes once an administrator
# has confirmed that claim by eye (see ``CatalogImageConfirmation``).
PASSING_STATUSES = frozenset({VERIFIED})

# Text fields whose value the source is expected to repeat verbatim. Enums,
# colours, flags, lists and long descriptions are not compared with the quote.
TEXT_VALUE_FIELDS = frozenset({"name", "line", "color_name", "ral_code", "material_type"})

Identity = tuple[str, str, str, str]

# Part of every claim hash: raising it sends verdicts reached under older, looser
# matching rules back to ``pending`` so they are checked again.
RULES_VERSION = 2


@dataclass(frozen=True)
class Claim:
    scope: str  # evidence | source_fact | unmapped_fact
    sheet: str
    key: str
    field: str
    urls: tuple[str, ...]
    quote: str | None
    image_url: str | None
    # ``number``/``text`` look for the field value in the quote, ``summary`` for
    # the numbers written in a fact's paraphrased value, ``none`` skips the check.
    value_kind: str
    value: Any
    # False for a quote recovered from a legacy ``explanation``: it is verified
    # for information but never blocks a row, as legacy proposals must keep working.
    gating: bool
    domains: tuple[str, ...] = field(default=())

    @property
    def identity(self) -> Identity:
        return (self.scope, self.sheet, self.key, self.field)

    @property
    def claim_hash(self) -> str:
        payload = [
            RULES_VERSION,
            self.identity,
            sorted(self.urls),
            self.quote,
            self.image_url,
            self.value_kind,
            self.value,
            sorted(self.domains),
        ]
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":")).encode()
        ).hexdigest()


def host_domain(value: str | None) -> str | None:
    """Lower-case host without a leading ``www.``; None when there is no hostname."""
    if not value:
        return None
    candidate = value.strip()
    if "//" not in candidate:
        candidate = "//" + candidate
    try:
        host = urlsplit(candidate).hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.rstrip(".").lower()
    return host[4:] if host.startswith("www.") else host


def is_official_host(url: str, domains: Iterable[str]) -> bool:
    host = host_domain(url)
    if host is None:
        return False
    return any(host == domain or host.endswith("." + domain) for domain in domains)


async def official_domains(db: AsyncSession, draft: dict[str, Any]) -> tuple[str, ...]:
    """Websites of the proposed brands, and of the existing brands they update."""
    domains: set[str] = set()
    existing: list[str] = []
    for name in ("brands", "brand_markets"):
        for row in draft.get(name) or []:
            domain = host_domain(row.get("website"))
            if domain:
                domains.add(domain)
            reference = str(row.get("existing_brand") or "").strip() if name == "brands" else ""
            if reference:
                existing.append(reference)
    for reference in existing:
        if reference.isdecimal():
            clause = Brand.id == int(reference)
        else:
            clause = func.lower(Brand.slug) == reference.casefold()
        website = await db.scalar(select(Brand.website).where(clause))
        domain = host_domain(website)
        if domain:
            domains.add(domain)
    return tuple(sorted(domains))


def _row_index(draft: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """One pass over the draft, so each evidence item finds its row in O(1)."""
    return {
        (sheet, row_key(sheet, row)): row
        for sheet, (field, _) in SHEETS.items()
        for row in draft.get(field) or []
    }


def _evidence_value(
    item: dict[str, Any], rows: dict[tuple[str, str], dict[str, Any]]
) -> tuple[str, Any]:
    if item.get("kind") == "inferred":
        return "none", None
    value = (rows.get((item["sheet"], item["key"])) or {}).get(item["field"])
    if isinstance(value, bool) or value is None:
        return "none", None
    if isinstance(value, (int, float)):
        return "number", value
    if isinstance(value, str) and item["field"] in TEXT_VALUE_FIELDS and value.strip():
        return "text", value.strip()
    return "none", None


def extract_claims(
    *,
    draft: dict[str, Any],
    evidence: list[dict[str, Any]],
    unmapped_facts: list[dict[str, Any]],
    source_facts: list[dict[str, Any]],
    domains: tuple[str, ...] = (),
) -> list[Claim]:
    claims: list[Claim] = []
    rows = _row_index(draft)
    for item in evidence or []:
        explicit = item.get("quote")
        quote = explicit or leading_quote(item.get("explanation"))
        image_url = item.get("image_url")
        if not quote and not image_url:
            continue
        kind, value = _evidence_value(item, rows)
        claims.append(
            Claim(
                scope="evidence",
                sheet=item["sheet"],
                key=item["key"],
                field=item["field"],
                urls=tuple(str(url) for url in item["source_urls"]),
                quote=quote,
                image_url=str(image_url) if image_url else None,
                value_kind=kind,
                value=value,
                gating=bool(explicit or image_url),
                domains=domains,
            )
        )
    for scope, facts in (("source_fact", source_facts), ("unmapped_fact", unmapped_facts)):
        for fact in facts or []:
            explicit = fact.get("quote")
            quote = explicit or (
                leading_quote(fact.get("explanation")) if scope == "unmapped_fact" else None
            )
            image_url = fact.get("image_url")
            if not quote and not image_url:
                continue
            inferred = fact.get("kind") == "inferred"
            claims.append(
                Claim(
                    scope=scope,
                    sheet="",
                    key=fact["filament_key"],
                    field=str(fact["property_name"]).casefold(),
                    urls=tuple(str(url) for url in fact["source_urls"]),
                    quote=quote,
                    image_url=str(image_url) if image_url else None,
                    value_kind="none" if inferred else "summary",
                    value=None if inferred else fact["value_summary"],
                    gating=bool(explicit or image_url),
                    domains=domains,
                )
            )
    return claims


async def proposal_claims(db: AsyncSession, proposal: CatalogCurationProposal) -> list[Claim]:
    domains = await official_domains(db, proposal.draft)
    return extract_claims(
        draft=proposal.draft,
        evidence=proposal.evidence,
        unmapped_facts=proposal.unmapped_facts,
        source_facts=getattr(proposal, "source_facts", []) or [],
        domains=domains,
    )


@dataclass(frozen=True)
class ClaimState:
    claim: Claim
    status: str
    reason: str | None = None
    url: str | None = None
    checked_at: Any = None
    confirmed: bool = False

    @property
    def passes(self) -> bool:
        return self.status in PASSING_STATUSES or (self.status == IMAGE_ONLY and self.confirmed)


async def load_checks(db: AsyncSession, proposal_id: int) -> dict[Identity, CatalogQuoteCheck]:
    rows = await db.scalars(
        select(CatalogQuoteCheck).where(CatalogQuoteCheck.proposal_id == proposal_id)
    )
    return {(row.scope, row.sheet, row.key, row.field): row for row in rows}


async def load_confirmations(
    db: AsyncSession, proposal_id: int
) -> dict[Identity, CatalogImageConfirmation]:
    rows = await db.scalars(
        select(CatalogImageConfirmation).where(CatalogImageConfirmation.proposal_id == proposal_id)
    )
    return {(row.scope, row.sheet, row.key, row.field): row for row in rows}


def claim_states(
    claims: list[Claim],
    checks: dict[Identity, CatalogQuoteCheck],
    confirmations: dict[Identity, CatalogImageConfirmation] | None = None,
) -> list[ClaimState]:
    states = []
    for claim in claims:
        row = checks.get(claim.identity)
        if row is None or row.claim_hash != claim.claim_hash:
            states.append(ClaimState(claim, PENDING))
            continue
        confirmation = (confirmations or {}).get(claim.identity)
        confirmed = confirmation is not None and confirmation.claim_hash == claim.claim_hash
        states.append(
            ClaimState(claim, row.status, row.reason, row.url, row.checked_at, confirmed)
        )
    return states


@dataclass(frozen=True)
class QuoteGate:
    """Which gating claims currently stop a row from being applied."""

    blocked: dict[Identity, str]

    def blocking(self, scope: str, sheet: str, key: str, name: str) -> str | None:
        return self.blocked.get((scope, sheet, key, name))


async def quote_gate(
    db: AsyncSession, proposal: CatalogCurationProposal, claims: list[Claim] | None = None
) -> QuoteGate:
    if claims is None:
        claims = await proposal_claims(db, proposal)
    gating = [claim for claim in claims if claim.gating]
    if not gating:
        return QuoteGate({})
    states = claim_states(
        gating, await load_checks(db, proposal.id), await load_confirmations(db, proposal.id)
    )
    return QuoteGate(
        {
            state.claim.identity: (
                "image_unconfirmed" if state.status == IMAGE_ONLY else state.status
            )
            for state in states
            if not state.passes
        }
    )


def gated_source_facts(facts: list[dict[str, Any]], gate: QuoteGate) -> list[dict[str, Any]]:
    """Source facts whose quote is not verified count as unresolved, whatever they claim."""
    result = []
    for fact in facts:
        if gate.blocking(
            "source_fact", "", fact["filament_key"], str(fact["property_name"]).casefold()
        ):
            fact = {**fact, "disposition": "unresolved"}
        result.append(fact)
    return result


def summarize_states(states: list[ClaimState]) -> dict[str, int]:
    counts = {status: 0 for status in (*STORED_STATUSES, PENDING)}
    for state in states:
        counts[state.status] += 1
    total = len(states)
    return {
        "total": total,
        **counts,
        "verified_percent": counts[VERIFIED] * 100 // total if total else 0,
    }


async def job_pending(db: AsyncSession, proposal_id: int) -> bool:
    return (
        await db.scalar(
            select(CatalogQuoteCheckJob.proposal_id).where(
                CatalogQuoteCheckJob.proposal_id == proposal_id
            )
        )
        is not None
    )
