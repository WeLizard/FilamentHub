"""Durable queue and worker that verify proposal quotes outside the request.

One row per proposal in ``catalog_curation_quote_jobs`` coalesces repeated
requests. A worker leases the row, releases its transaction while it reads the
network, then writes the verdicts and removes or reschedules the row.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogCurationProposal
from app.models.catalog_quote_check import CatalogQuoteCheck, CatalogQuoteCheckJob
from app.services.catalog_quote_claims import (
    SOURCE_UNAVAILABLE,
    VERIFIED,
    Claim,
    Identity,
    extract_claims,
    load_checks,
    load_confirmations,
    proposal_claims,
)
from app.services.catalog_quote_verifier import QuoteVerifier, is_transient_reason

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 4
LEASE_SECONDS = 900
RETRY_BASE_SECONDS = 30
RETRY_MAX_SECONDS = 600
WORKER_IDLE_SECONDS = 5.0


def has_quotable_claims(proposal: CatalogCurationProposal) -> bool:
    return bool(
        extract_claims(
            draft=proposal.draft,
            evidence=proposal.evidence,
            unmapped_facts=proposal.unmapped_facts,
            source_facts=getattr(proposal, "source_facts", []) or [],
        )
    )


async def enqueue_quote_check(db: AsyncSession, proposal_id: int) -> None:
    """Request a verification inside the caller's transaction; repeats coalesce."""
    now = datetime.now(timezone.utc)
    values = {
        "proposal_id": proposal_id,
        "requested_at": now,
        "next_attempt_at": now,
        "attempt_count": 0,
        "last_error": None,
    }
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        statement: Any = postgresql_insert(CatalogQuoteCheckJob).values(**values)
    elif dialect == "sqlite":
        statement = sqlite_insert(CatalogQuoteCheckJob).values(**values)
    else:  # pragma: no cover - supported deployments/tests use PostgreSQL/SQLite
        raise RuntimeError(f"Unsupported database dialect: {dialect}")
    await db.execute(
        statement.on_conflict_do_update(
            index_elements=[CatalogQuoteCheckJob.proposal_id],
            set_={
                key: values[key]
                for key in ("requested_at", "next_attempt_at", "attempt_count", "last_error")
            },
        )
    )


async def enqueue_if_quotable(db: AsyncSession, proposal: CatalogCurationProposal) -> None:
    """Queue verification after a service-account write that cites quotes or images."""
    if has_quotable_claims(proposal):
        await enqueue_quote_check(db, proposal.id)
        await db.commit()


def _needs_check(claim: Claim, row: CatalogQuoteCheck | None, *, retry: bool) -> bool:
    if row is None or row.claim_hash != claim.claim_hash:
        return True
    if row.status == VERIFIED:
        return False
    if retry:
        # A retry only revisits pages that could not be read for a passing reason.
        return row.status == SOURCE_UNAVAILABLE and is_transient_reason(row.reason)
    return True


async def run_proposal_check(
    db: AsyncSession, verifier: QuoteVerifier, proposal_id: int, *, retry: bool
) -> bool:
    """Verify the proposal's open claims; True when a transient failure is worth retrying."""
    proposal = await db.get(CatalogCurationProposal, proposal_id)
    if proposal is None:
        return False
    revision = proposal.revision
    claims = await proposal_claims(db, proposal)
    checks = await load_checks(db, proposal_id)
    todo = [
        claim for claim in claims if _needs_check(claim, checks.get(claim.identity), retry=retry)
    ]
    # No transaction is held open across the network reads below.
    await db.commit()

    verdicts = await verifier.verify(todo)

    checks = await load_checks(db, proposal_id)
    live: set[Identity] = {claim.identity for claim in claims}
    for identity, row in checks.items():
        if identity not in live:
            await db.delete(row)
    for identity, confirmation in (await load_confirmations(db, proposal_id)).items():
        if identity not in live:
            await db.delete(confirmation)
    now = datetime.now(timezone.utc)
    for claim in todo:
        verdict = verdicts[claim.identity]
        row = checks.get(claim.identity)
        if row is None:
            scope, sheet, key, name = claim.identity
            row = CatalogQuoteCheck(
                proposal_id=proposal_id, scope=scope, sheet=sheet, key=key, field=name
            )
            db.add(row)
        row.claim_hash = claim.claim_hash
        row.status = verdict.status
        row.reason = verdict.reason
        row.url = verdict.url[:2048] if verdict.url else None
        row.page_sha256 = verdict.page_sha256
        row.revision = revision
        row.checked_at = now
    await db.commit()
    return any(
        verdict.status == SOURCE_UNAVAILABLE and is_transient_reason(verdict.reason)
        for verdict in verdicts.values()
    )


def _retry_delay(attempts: int) -> timedelta:
    return timedelta(seconds=min(RETRY_MAX_SECONDS, RETRY_BASE_SECONDS * 2 ** (attempts - 1)))


async def _claim_job(session_factory: Any) -> tuple[int, datetime, int] | None:
    async with session_factory() as db:
        now = datetime.now(timezone.utc)
        job = (
            await db.execute(
                select(CatalogQuoteCheckJob)
                .where(
                    CatalogQuoteCheckJob.next_attempt_at <= now,
                    or_(
                        CatalogQuoteCheckJob.claimed_at.is_(None),
                        CatalogQuoteCheckJob.claimed_at < now - timedelta(seconds=LEASE_SECONDS),
                    ),
                )
                .order_by(CatalogQuoteCheckJob.next_attempt_at, CatalogQuoteCheckJob.requested_at)
                .with_for_update(skip_locked=True)
                .limit(1)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if job is None:
            return None
        claimed = (job.proposal_id, job.requested_at, job.attempt_count)
        job.claimed_at = now
        await db.commit()
        return claimed


async def _finish_job(
    session_factory: Any,
    proposal_id: int,
    requested_at: datetime,
    attempt: int,
    *,
    failed: str | None,
    retry_needed: bool,
) -> None:
    async with session_factory() as db:
        job = await db.get(
            CatalogQuoteCheckJob, proposal_id, with_for_update=True, populate_existing=True
        )
        if job is None:
            return
        job.claimed_at = None
        # A request that arrived mid-run changed ``requested_at`` and is already due.
        if job.requested_at == requested_at:
            if (failed or retry_needed) and attempt + 1 < MAX_ATTEMPTS:
                job.attempt_count = attempt + 1
                job.last_error = failed
                job.next_attempt_at = datetime.now(timezone.utc) + _retry_delay(attempt + 1)
            else:
                await db.execute(
                    delete(CatalogQuoteCheckJob).where(
                        CatalogQuoteCheckJob.proposal_id == proposal_id
                    )
                )
        await db.commit()


async def process_quote_check_jobs(
    session_factory: Any, verifier: QuoteVerifier, *, max_jobs: int = 1
) -> int:
    """Run up to ``max_jobs`` due jobs; returns how many were attempted."""
    processed = 0
    while processed < max_jobs:
        claimed = await _claim_job(session_factory)
        if claimed is None:
            break
        processed += 1
        proposal_id, requested_at, attempt = claimed
        failed: str | None = None
        retry_needed = False
        try:
            async with session_factory() as db:
                retry_needed = await run_proposal_check(
                    db, verifier, proposal_id, retry=attempt > 0
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - the durable job row is the retry boundary
            failed = type(exc).__name__[:100]
            logger.warning("Quote verification failed for proposal %s", proposal_id, exc_info=True)
        await _finish_job(
            session_factory,
            proposal_id,
            requested_at,
            attempt,
            failed=failed,
            retry_needed=retry_needed,
        )
    return processed


async def run_quote_check_worker(session_factory: Any) -> None:
    """Continuously drain due verification jobs, one proposal at a time per process."""
    verifier = QuoteVerifier()
    while True:
        processed = 0
        try:
            processed = await process_quote_check_jobs(session_factory, verifier)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a later poll retries durable rows
            logger.warning("Quote verification worker failed", exc_info=True)
        await asyncio.sleep(0 if processed else WORKER_IDLE_SECONDS)
