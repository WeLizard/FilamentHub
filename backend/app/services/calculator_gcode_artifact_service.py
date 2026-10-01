"""Sweep what is left of the retired Calculator G-code upload path.

The calculator no longer stores uploaded G-code: the browser and the plugin
send excerpts. Rows and files written before that change still expire here;
this module, its model and table go once a release has swept them.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.concurrency import run_in_threadpool

from app.models.calculator_gcode_artifact import CalculatorGcodeArtifact
from app.services.file_service import get_upload_root_dir

logger = logging.getLogger(__name__)

ARTIFACT_TTL = timedelta(minutes=30)
ARTIFACT_SWEEP_INTERVAL_SECONDS = 300.0
ARTIFACT_SWEEP_BATCH_SIZE = 100
ORPHAN_FILE_GRACE = ARTIFACT_TTL


class ArtifactNotFoundError(Exception):
    pass


def artifact_storage_root() -> Path:
    """Private subtree of the persistent uploads volume."""
    return get_upload_root_dir() / "calculator_gcode_artifacts"


def _artifact_path(storage_key: str) -> Path:
    root = artifact_storage_root().resolve()
    path = (root / storage_key).resolve()
    if not path.is_relative_to(root):
        raise ArtifactNotFoundError
    return path


def _old_artifact_files(root: Path, *, before: datetime, limit: int) -> list[Path]:
    candidates: list[Path] = []
    for path in root.iterdir():
        try:
            is_old_file = (
                path.is_file()
                and datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) <= before
            )
        except FileNotFoundError:
            continue
        if is_old_file:
            candidates.append(path)
            if len(candidates) >= limit:
                break
    return candidates


async def cleanup_expired_artifacts(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    batch_size: int = ARTIFACT_SWEEP_BATCH_SIZE,
) -> int:
    """Remove one bounded batch of expired or terminal artifact records and blobs."""
    current_time = now or datetime.now(timezone.utc)
    await run_in_threadpool(artifact_storage_root().mkdir, parents=True, exist_ok=True)
    rows = (
        await db.execute(
            select(CalculatorGcodeArtifact)
            .where(
                (CalculatorGcodeArtifact.expires_at <= current_time)
                | CalculatorGcodeArtifact.state.in_(("failed", "cancelled"))
            )
            .order_by(CalculatorGcodeArtifact.expires_at, CalculatorGcodeArtifact.id)
            .limit(batch_size)
        )
    ).scalars().all()
    for artifact in rows:
        if artifact.storage_key:
            await run_in_threadpool(_artifact_path(artifact.storage_key).unlink, missing_ok=True)
        for partial in artifact_storage_root().glob(f"{artifact.id}.*.part"):
            await run_in_threadpool(partial.unlink, missing_ok=True)
        await db.delete(artifact)
    await db.flush()

    # Rows can disappear through owner cascade deletion, and a process can stop
    # between writing a temporary file and committing its row. Reclaim those
    # files after a full artifact lifetime, in the same bounded sweep.
    root = artifact_storage_root()
    orphan_candidates = await run_in_threadpool(
        _old_artifact_files,
        root,
        before=current_time - ORPHAN_FILE_GRACE,
        limit=batch_size,
    )
    candidate_ids = {path.name[:36] for path in orphan_candidates}
    persisted_ids = set()
    if candidate_ids:
        persisted_ids = set(
            (
                await db.execute(
                    select(CalculatorGcodeArtifact.id).where(
                        CalculatorGcodeArtifact.id.in_(candidate_ids)
                    )
                )
            ).scalars()
        )
    for path in orphan_candidates:
        if path.name[:36] not in persisted_ids:
            await run_in_threadpool(path.unlink, missing_ok=True)
    return len(rows)


async def run_gcode_artifact_sweeper(
    session_factory: async_sessionmaker[AsyncSession],
    interval_seconds: float = ARTIFACT_SWEEP_INTERVAL_SECONDS,
) -> None:
    while True:
        try:
            async with session_factory() as db:
                removed = await cleanup_expired_artifacts(db)
                await db.commit()
            if removed:
                logger.info("Removed %d expired Calculator G-code artifacts", removed)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Failed to sweep Calculator G-code artifacts", exc_info=True)
        await asyncio.sleep(interval_seconds)
